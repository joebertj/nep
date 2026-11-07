"""Retain official venue listings and attach exact, sourced map-name matches."""
import hashlib
import json
import re
import unicodedata
from html.parser import HTMLParser

URL = 'https://www.sanjuanbatangas.gov.ph/tourism/dot-accredited-enterprises'
GROUPS = {'Resorts': 'Resort', 'Mabuhay Accommodations': 'Visitor accommodation',
          'Tourism Recreation Center': 'Adventure park', 'Agri-Tourism Farm Site': 'Agri-tourism venue'}
ALIASES = {
    'Acuatico Beach Resort & Hotel, Inc.': ['Acuatico Resort', 'Acuatico Beach Resort'],
    'Doña Nena Beach Resort': ['Dona Nena Family Beach Resort'],
    'Punta Aguila Resort & Hotel': ['Punta Aguila'],
}


def name_key(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value) if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]', '', value.upper())


class Headings(HTMLParser):
    def __init__(self):
        super().__init__(); self.active = False; self.buffer = []; self.headings = []

    def handle_starttag(self, tag, attrs):
        if tag == 'h2': self.active = True; self.buffer = []

    def handle_data(self, data):
        if self.active: self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'h2' and self.active:
            self.headings.append(' '.join(''.join(self.buffer).split())); self.active = False


def enrich(venues, raw_directory, inputs, retrieved_at):
    path = raw_directory / 'san-juan-dot-directory.html'
    if not path.exists(): return []
    raw = path.read_bytes(); parser = Headings(); parser.feed(raw.decode('utf-8'))
    inputs.append({'file': str(path.relative_to(raw_directory.parent.parent)), 'endpoint': URL,
                   'sha256': hashlib.sha256(raw).hexdigest(), 'sourceKind': 'Municipal tourism directory',
                   'retrievedAtUtc': retrieved_at})
    names = {}
    for venue in venues: names.setdefault(name_key(venue['name']), []).append(venue)
    rows, group = [], None
    for heading in parser.headings:
        if heading in GROUPS: group = GROUPS[heading]; continue
        if heading in {'Travel and Tour Agency', 'Restaurant', 'Contact Us', 'Hotlines', 'Social Media', 'Government Links'}:
            group = None; continue
        if not group or not heading: continue
        candidates = {v['id']: v for alias in [heading, *ALIASES.get(heading, [])]
                      for v in names.get(name_key(alias), [])
                      if not v.get('province') or name_key(v['province']) == 'BATANGAS'}
        # A name in two map locations is unresolved even within the province.
        matches = list(candidates.values()) if len(candidates) == 1 else []
        row = {'id': 'san-juan-tourism:' + hashlib.sha256(heading.encode()).hexdigest()[:16],
               'name': heading, 'type': group, 'recordKind': 'Official venue listing',
               'province': 'Batangas', 'municipality': 'San Juan', 'region': 'Region IV-A',
               'adminType': 'Municipality', 'source': 'San Juan municipal tourism directory', 'sourceUrl': URL,
               'evidence': 'Listed as DOT-accredited by the municipal tourism office; accreditation validity dates are not supplied.',
               'coordinateBasis': 'Directory location only; no coordinates inferred', 'latitude': None, 'longitude': None,
               'matchedOsmIds': [v['id'] for v in matches], 'retrievedAtUtc': retrieved_at}
        for venue in matches:
            evidence = {'name': heading, 'sourceUrl': URL, 'source': row['source'],
                        'province': row['province'], 'municipality': row['municipality'],
                        'identityBasis': 'Unique exact normalized venue name or explicit reviewed brand alias within Batangas',
                        'locationStatus': 'Directory and map boundary agree' if name_key(venue.get('municipality', '')) == 'SANJUAN'
                                          else 'Municipal directory and map boundary differ; location requires review'}
            venue.setdefault('directoryEvidence', []).append(evidence)
        rows.append(row)
    return rows
