"""Index repeat-browser projects under the same PSGC hierarchy as education-health."""
from collections import defaultdict
from functools import lru_cache
import json
from pathlib import Path
import re

from location_data.location_text import barangay_key, geographic_title, place_key, text_key

PSGC = Path(__file__).resolve().parents[1] / 'data_sources/bettergov-psgc-locations.jsonl'
LEVELS = {'region', 'province', 'city', 'municipality', 'barangay'}
TOWNS = {'city', 'municipality'}
REGIONS = ('I', 'II', 'III', 'IV-A', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII')
BARANGAY = re.compile(r'\b(?:barangay|brgy\.?|bgy\.?)\s+')


def variants(name, level):
    if level == 'region':
        key = text_key(name)
        extras = {'metro manila', 'ncr'} if 'national capital region' in key else set()
        if key == 'mimaropa region':
            extras |= {'mimaropa', 'region iv-b', 'region 4b'}
        if 'caraga' in key:
            extras.add('region 13')
        for number, roman in enumerate(REGIONS, 1):
            if key.split(' (')[0] == 'region ' + roman.lower():
                extras.add('region ' + str(number))
                if number == 4:
                    extras.update({'region 4a', 'region 4-a', 'region iva'})
        return {text_key(part).strip() for part in re.split(r'[()]', name) if part.strip()} | {key} | extras
    key = barangay_key if level == 'barangay' else place_key
    parts = re.fullmatch(r'(.+?)\s*\(([^()]+)\)', name)
    if not parts:
        return {key(name)}
    base, alternate = parts.groups()
    return {key(name), key(base)} | ({key(alternate)} if alternate.lower() not in {'pob.', 'poblacion'} else set())


class RepeatPlaces:
    def __init__(self):
        with PSGC.open(encoding='utf-8') as stream:
            self.places = {row['code']: row for row in map(json.loads, stream)}
        self.names = defaultdict(set)
        for code, place in self.places.items():
            level = place['level']
            if level not in LEVELS:
                continue
            for name in variants(place['name'], level):
                self.names[level, name].add(code)

    @lru_cache(maxsize=None)
    def lineage(self, code):
        path = {}
        while code:
            place = self.places[code]
            level = place['level']
            if level in LEVELS:
                path['municipality' if level in TOWNS else level] = code
            code = place['parent_code']
        return path

    def towns(self, name):
        key = place_key(name)
        if re.search(r'^city of\b|\bcity$', name):
            return self.names['city', key]
        if name.startswith('municipality of '):
            return self.names['municipality', key]
        if name.startswith('province of '):
            return set()
        return self.names['city', key] | self.names['municipality', key]

    @lru_cache(maxsize=None)
    def region(self, name):
        match = self.names['region', text_key(name)]
        return next(iter(match)) if len(match) == 1 else None

    @lru_cache(maxsize=None)
    def resolve(self, title, reported_region=''):
        text, _ = geographic_title(title)
        fields = [part.strip(' .;') for part in text.split(',') if part.strip(' .;')]
        if len(fields) < 2:
            return ()
        region = self.region(fields[-1])
        if region:
            fields.pop()
        if len(fields) < 2:
            return (region,) if region else ()
        last = fields[-1]
        province = self.names['province', place_key(last)]
        towns = self.towns(last)
        if re.search(r'^(?:city|municipality) of\b|\bcity$', last):
            province = set()
        # A full municipality/province pair supplies the parent identity.
        qualified = set()
        if province:
            qualified = {town for town in self.towns(fields[-2])
                         if self.lineage(town).get('province') in province}
            if not qualified:
                # Independent cities sit directly beneath their region in PSGC.
                qualified = {town for town in self.towns(fields[-2])
                             if self.places[town]['level'] == 'city' and 'province' not in self.lineage(town)
                             and self.lineage(town).get('region')
                             in {self.lineage(code).get('region') for code in province}}
        if qualified:
            towns = qualified
            prefix = fields[:-2]
        else:
            prefix = fields[:-1]
            if province and not towns:
                return tuple(province) if len(province) == 1 else ()
            if province and towns and not region:
                return ()
        context = region or self.region(reported_region)
        if context and len(towns) > 1:
            towns = {town for town in towns if self.lineage(town).get('region') == context}
        if len(towns) != 1:
            return (region,) if region else ()
        town = next(iter(towns))
        names = BARANGAY.split(','.join(prefix))[1:]
        if not names and prefix:
            names = prefix[-1:]
        barangays = set()
        for name in names:
            name = barangay_key(name.split(',')[0].strip())
            hits = {code for code in self.names['barangay', name] if self.lineage(code).get('municipality') == town}
            if len(hits) == 1:
                barangays.update(hits)
        return tuple(sorted(barangays)) or (town,)

    def parent(self, code):
        parent = self.places[code]['parent_code']
        while parent and self.places[parent]['level'] not in LEVELS:
            parent = self.places[parent]['parent_code']
        return parent

    def index(self, projects):
        offsets = defaultdict(list)
        for index, project in enumerate(projects):
            regions = {code for name in project.pop('reportedRegions', []) if (code := self.region(name))}
            region = next(iter(regions)) if len(regions) == 1 else None
            places = set()
            for row in project['stages']:
                places.update(self.resolve(row['title'], self.places[region]['name'] if region else ''))
            for _, rows in project['years']:
                for row in rows:
                    places.update(self.resolve(row['title']))
            if not places and region:
                places.add(region)
            for code in {ancestor for place in places for ancestor in self.lineage(place).values()}:
                offsets[code].append(index)
        nodes = []
        for code in sorted(offsets):
            place = self.places[code]
            level = 'municipality' if place['level'] in TOWNS else place['level']
            nodes.append([code, place['name'], level, self.parent(code), offsets[code]])
        return nodes
