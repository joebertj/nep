"""Build location-quality evidence from the dated NIA geolocation workbook."""
from __future__ import annotations

from collections import Counter
from html import escape
import json
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
WORKBOOK = ROOT / 'data_sources' / '2026-11-10--with geolocation_bettergov-house-bill-2027-nia-projects.xlsx'
PSGC_PATH = ROOT / 'data_sources' / 'bettergov-psgc-locations.jsonl'
OUT = ROOT / 'analysis_output' / 'nia_geolocation_audit.json'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _column_index(ref: str) -> int:
    value = 0
    for char in re.match(r'[A-Z]+', ref).group(0):
        value = value * 26 + ord(char) - 64
    return value - 1


def _workbook_rows() -> list[dict[str, str]]:
    with ZipFile(WORKBOOK) as book:
        shared_root = ET.fromstring(book.read('xl/sharedStrings.xml'))
        shared = [''.join(t.text or '' for t in item.findall('.//m:t', NS))
                  for item in shared_root.findall('m:si', NS)]
        sheet = ET.fromstring(book.read('xl/worksheets/sheet2.xml'))
    rows = sheet.findall('.//m:sheetData/m:row', NS)
    if not rows:
        return []

    def unpack(row: ET.Element) -> list[str]:
        cells = row.findall('m:c', NS)
        values = [''] * (max((_column_index(c.attrib['r']) for c in cells), default=-1) + 1)
        for cell in cells:
            value = cell.find('m:v', NS)
            text = value.text if value is not None else ''
            if cell.attrib.get('t') == 's' and text:
                text = shared[int(text)]
            values[_column_index(cell.attrib['r'])] = text
        return values

    headers = unpack(rows[0])
    return [dict(zip(headers, unpack(row))) for row in rows[1:]]


def _normal(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.lower())


def build() -> dict:
    records = _workbook_rows()
    places = {item['code']: item for item in
              (json.loads(line) for line in PSGC_PATH.read_text(encoding='utf-8').splitlines() if line.strip())}
    granularity: Counter[str] = Counter()
    review_rows = []
    located = 0
    valid_codes = 0
    name_mismatch_count = 0
    hierarchy_mismatch_count = 0
    rows_with_length = sum(bool((row.get('length_m') or '').strip()) for row in records)
    for row in records:
        raw_code = (row.get('10-digit PSGC') or '').strip()
        if not raw_code:
            continue
        located += 1
        code = raw_code.zfill(10)
        place = places.get(code)
        if not place:
            review_rows.append({
                'id': row.get('id', ''), 'title': row.get('title', ''),
                'name': row.get('Name', ''), 'municipality': row.get('City/Municipality', ''),
                'province': row.get('Province', ''), 'psgc': raw_code,
                'referencePlace': 'No exact match in the current PSGC reference list',
                'issue': 'Provided PSGC code could not be resolved; verify the location code.',
                'issueType': 'unresolved_psgc',
            })
            continue

        valid_codes += 1
        granularity[place['level']] += 1
        chain = [place]
        parent = place.get('parent_code')
        while parent and parent in places:
            ancestor = places[parent]
            chain.append(ancestor)
            parent = ancestor.get('parent_code')
        by_level = {item['level']: item['name'] for item in chain}
        mismatches = []
        hierarchy_mismatches = []
        supplied_name = (row.get('Name') or '').strip()
        canonical_name = place.get('name', '')
        if supplied_name and canonical_name and _normal(supplied_name) != _normal(canonical_name):
            name_mismatch_count += 1
            mismatches.append(f'Name: provided “{supplied_name}”; PSGC entity says “{canonical_name}”.')
        for field, hierarchy_level, label in (
            ('City/Municipality', 'municipality', 'Municipality'),
            ('City/Municipality', 'city', 'City'),
            ('Province', 'province', 'Province'),
        ):
            provided = (row.get(field) or '').strip()
            canonical = by_level.get(hierarchy_level, '')
            if provided and canonical and _normal(provided) != _normal(canonical):
                # A municipal value is compared with the municipal ancestor where present;
                # city-level PSGC entries use their city ancestor instead.
                if field == 'City/Municipality' and hierarchy_level == 'city' and by_level.get('municipality'):
                    continue
                detail = f'{label}: provided “{provided}”; PSGC hierarchy says “{canonical}”.'
                mismatches.append(detail)
                hierarchy_mismatches.append(detail)
        if mismatches:
            if hierarchy_mismatches:
                hierarchy_mismatch_count += 1
            review_rows.append({
                'id': row.get('id', ''), 'title': row.get('title', ''),
                'name': row.get('Name', ''), 'municipality': row.get('City/Municipality', ''),
                'province': row.get('Province', ''), 'psgc': raw_code,
                'referencePlace': ' · '.join(by_level.get(key, '') for key in ('barangay', 'municipality', 'city', 'province') if by_level.get(key)),
                'issue': ' '.join(mismatches), 'issueType': 'hierarchy_mismatch',
            })

    missing = len(records) - located
    result = {
        'source': WORKBOOK.name,
        'sourceSheet': 'bettergov-house-bill-2027-nia-p',
        'sourceRows': len(records),
        'rowsWithPsgc': located,
        'rowsWithoutPsgc': missing,
        'rowsWithLength': rows_with_length,
        'resolvedPsgcRows': valid_codes,
        'granularityCounts': dict(sorted(granularity.items())),
        'reviewFlagRows': review_rows,
        'hierarchyMismatchCount': hierarchy_mismatch_count,
        'placeNameMismatchCount': name_mismatch_count,
        'unresolvedPsgcCount': sum(r['issueType'] == 'unresolved_psgc' for r in review_rows),
        'method': 'PSGC values were matched to the local official-place reference. Supplied City/Municipality and Province text was compared with the resolved administrative hierarchy. PSGC is an administrative place key, not a surveyed project point or route alignment.',
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    OUT.write_text(serialized, encoding='utf-8')
    (STATIC / 'nia-geolocation-audit.json').write_text(serialized, encoding='utf-8')
    return result


def render() -> str:
    data = build()
    total = data['sourceRows']
    located = data['rowsWithPsgc']
    valid = data['resolvedPsgcRows']
    mismatches = data['hierarchyMismatchCount']
    unresolved = data['unresolvedPsgcCount']
    missing = data['rowsWithoutPsgc']
    total_conflicts = data['hierarchyMismatchCount']
    name_conflicts = data['placeNameMismatchCount']
    table_rows = []
    for row in data['reviewFlagRows']:
        table_rows.append(
            '<tr><td>' + escape(row['title']) + '<small>' + escape(row['id']) + '</small></td>'
            '<td>' + escape(row['name']) + ' · ' + escape(row['municipality']) + ' · ' + escape(row['province']) + '</td>'
            '<td>' + escape(row['psgc']) + '</td><td>' + escape(row['referencePlace']) + '</td>'
            '<td>' + escape(row['issue']) + '</td></tr>'
        )
    return f'''<style id="nia-geolocation-flags-style">.nia-geolocation-flags .nia-location-metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}}.nia-geolocation-flags .nia-location-metrics>div{{display:grid;gap:3px;padding:13px;border:1px solid #dce4e1;border-radius:10px;background:#fff}}.nia-geolocation-flags .nia-location-metrics strong{{font-size:22px;color:#8f1d16;font-variant-numeric:tabular-nums}}.nia-geolocation-flags .nia-location-metrics span,.nia-geolocation-flags small{{display:block;color:#637381;font-size:12px}}.nia-geolocation-flags .nia-location-method{{padding:12px 14px;border-left:4px solid #0038A8;background:#EAF0FF}}.nia-geolocation-flags .tablewrap{{overflow:auto}}.nia-geolocation-flags table{{width:100%;border-collapse:collapse;font-size:13px}}.nia-geolocation-flags th{{background:#00246A;color:#fff;text-align:left}}.nia-geolocation-flags th,.nia-geolocation-flags td{{padding:9px 11px;border-bottom:1px solid #dce4e1;vertical-align:top}}.nia-geolocation-flags td:first-child{{min-width:260px}}.nia-geolocation-flags td:last-child{{min-width:250px}}.nia-geolocation-flags .export-btn{{display:inline-block;padding:9px 13px;border-radius:8px;background:#0038A8;color:#fff;text-decoration:none;font-weight:650}}.nia-geolocation-flags .export-btn:hover{{background:#00246A}}@media(max-width:600px){{.nia-geolocation-flags{{overflow:hidden}}.nia-geolocation-flags .nia-location-metrics{{grid-template-columns:1fr 1fr}}}}</style>
<section id="nia-geolocation-flags" class="card nia-geolocation-flags">
<h2>NIA location coverage and administrative consistency flags</h2>
<p>The 10 November 2026 BetterGov House-bill geolocation workbook assigns an administrative PSGC place to <strong>{located:,} of {total:,}</strong> rows; <strong>{valid:,}</strong> codes resolve in the current PSGC reference. This improves locality-level review, but does not provide project coordinates or canal/dam alignments.</p>
<div class="nia-location-metrics"><div><strong>{located:,}/{total:,}</strong><span>rows with a PSGC value</span></div><div><strong>{missing:,}</strong><span>rows without a PSGC value</span></div><div><strong>{mismatches:,}</strong><span>province/municipality hierarchy conflicts</span></div><div><strong>{name_conflicts:,}</strong><span>Name-to-PSGC entity conflicts</span></div><div><strong>{unresolved:,}</strong><span>PSGC values not found in the reference</span></div></div>
<p class="nia-location-method">Location granularity among resolved codes: {data['granularityCounts'].get('barangay', 0):,} barangay, {data['granularityCounts'].get('municipality', 0):,} municipality, and {data['granularityCounts'].get('city', 0):,} city codes. A municipal or city key locates a project only to that administrative area. None of the {total:,} rows has a stated length. We therefore do not apply FMR road-distance, road-overlap, crop-proximity, endpoint, venue, or connectivity flags to these NIA rows. Those checks need project-level points or line geometry.</p>
<p><a class="export-btn" href="nia-geolocation-audit.json" download>Download NIA location flag data ↗</a></p>
<h3>Rows to verify against the source schedule</h3><p>These flags identify a disagreement between workbook administrative text and its PSGC hierarchy, or a PSGC value not found in the current reference. They are location-data checks, not findings about project validity.</p>
<div class="tablewrap"><table><thead><tr><th>NIA project · source row</th><th>Workbook location labels</th><th>PSGC</th><th>Resolved administrative hierarchy</th><th>Review flag</th></tr></thead><tbody>{''.join(table_rows) or '<tr><td colspan="5">No administrative hierarchy conflicts found.</td></tr>'}</tbody></table></div>
<p class="muted">Method: {escape(data['method'])} Source: {escape(data['source'])}. Current PSGC reference checked during page build.</p>
</section>'''

