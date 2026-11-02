#!/usr/bin/env python3
"""Build a barangay-level MPB allocation and repeat-title inventory."""
import hashlib
import json
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static' / 'nep-preview'
OUT = ROOT / 'analysis_output'
LOCATIONS = ODV / 'static' / 'data' / 'unified_locations.json'
PROJECTS = STATIC / 'integrated-project-data.json'
HGAB_PROJECTS = ROOT / 'hb10858_3rd_dpwh_projects.json'
DATA_NAME = 'mpb-barangay-data.json'
PAGE_NAME = 'mpb-barangay.html'
BASE_DATA_NAME = 'mpb-barangay-base-data.json'
BASE_PAGE_NAME = 'mpb-base.html'
LEGACY_MPB = ROOT / 'data_sources' / 'mpb-historical-2017-2018.json'
HISTORICAL_GAA = ROOT / 'data_sources' / 'gaa-dpwh-project-families-2016-2018.json'
BASE_ASSETS = ROOT / 'report_assets' / 'mpb-assets'

MARKER = re.compile(r'\b(?:barangay|brgy\.?|bgy\.?)\s+([^,;()]+)', re.I)
COORDS = re.compile(r'(?<!\w)-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}(?!\w)')
ACTION = re.compile(r'\b(?:construction|construct|completion|complete|rehabilitation|rehabilitate|repair|improvement|improve|upgrading|upgrade|renovation|renovate|phase|of)\b')
GENERIC_PLACES = {'hall', 'covered court', 'multipurpose building', 'multi purpose building', 'multi purpose', 'building'}


def norm(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().casefold()
    value = re.sub(r'\b(?:sta|st)\.?\b', 'santa', value)
    value = re.sub(r'\bsto\.?\b', 'santo', value)
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def has_phrase(haystack, phrase):
    return f' {phrase} ' in f' {haystack} '


def location_phrase(haystack, value):
    value = norm(value)
    variants = {value}
    for suffix in (' city', ' municipality', ' municipal district', ' district'):
        if value.endswith(suffix):
            variants.add(value[:-len(suffix)].strip())
    if value.startswith('city of '):
        variants.add(value[8:])
    return any(x and has_phrase(haystack, x) for x in variants)


def place_id(row):
    return '|'.join(norm(row.get(k)) for k in ('region', 'province', 'municipality', 'barangay'))


def identity_title(title):
    """Normalize a named project title; no coordinates or distance are used."""
    title = COORDS.sub(' ', str(title or ''))
    title = re.sub(r'\b(?:brgy\.?|bgy\.?)\b', 'barangay', title, flags=re.I)
    value = norm(title)
    value = ACTION.sub(' ', value)
    return ' '.join(value.split())


def main():
    locations = json.loads(LOCATIONS.read_text(encoding='utf-8'))
    source = json.loads(PROJECTS.read_text(encoding='utf-8'))
    known = {}
    place_rows = []
    for loc in locations:
        row = {k: str(loc.get(k) or '').strip() for k in ('region', 'province', 'municipality', 'barangay', 'district')}
        if not all(row[k] for k in ('region', 'province', 'municipality', 'barangay')):
            continue
        row['id'] = place_id(row)
        known.setdefault(norm(row['barangay']), []).append(row)
        place_rows.append(row)
    names_by_first = defaultdict(set)
    for name in known:
        if name:
            names_by_first[name.split()[0]].add(name)

    projects = [r for r in source.get('projects', [])
                if r.get('category') == 'Multi-purpose building' and 2020 <= int(r.get('year') or 0) <= 2026]
    legacy = json.loads(LEGACY_MPB.read_text(encoding='utf-8'))
    projects.extend(legacy.get('records', []))
    historical_gaa = json.loads(HISTORICAL_GAA.read_text(encoding='utf-8'))
    projects.extend({
        'year': 2016, 'stage': 'GAA', 'category': row['category'],
        'name': row['name'], 'amountPesos': int(row.get('amountPesos') or 0),
        'source': row.get('source') or 'FY2016 GAA Explorer DPWH project line',
        'sourceId': row.get('sourceId') or '',
    } for row in historical_gaa.get('records', [])
        if int(row.get('year') or 0) == 2016 and row.get('category') == 'Multi-purpose building')
    hgab = json.loads(HGAB_PROJECTS.read_text(encoding='utf-8'))['data']['data']
    for row in hgab:
        if row.get('pap3') != 'BIP - Multi-Purpose Buildings/ Facilities to support Social Services':
            continue
        projects.append({
            'year': 2027, 'stage': 'HGAB 3rd', 'category': 'Multi-purpose building',
            'name': row.get('projectName') or row.get('sourceTitle') or '',
            'amountPesos': int(row.get('amountPesos') or 0),
            'source': f"HGAB 3rd · {row.get('sourceVolume') or 'source volume'} · PDF p. {row.get('sourcePage') or 'not listed'}",
            'sourceId': row.get('id') or row.get('code'),
        })
    mapped, unassigned, multi_place = [], [], 0
    for number, project in enumerate(projects):
        title = str(project.get('name') or '')
        markers = list(MARKER.finditer(title))
        candidate_names = []
        for match in markers:
            candidate = re.sub(r'\s+(?:health station|health center|covered court|multi[- ]?purpose building|hall)$', '', match.group(1), flags=re.I).strip(' .,-')
            if norm(candidate) not in GENERIC_PLACES and len(norm(candidate)) >= 2:
                candidate_names.append(candidate)
        candidate_names = list(dict.fromkeys(candidate_names))
        candidates = []
        title_norm = norm(title)
        for candidate in candidate_names:
            options = known.get(norm(candidate), [])
            for loc in options:
                if not location_phrase(title_norm, loc['municipality']):
                    continue
                # When the province is printed, it must agree; many titles omit it.
                if location_phrase(title_norm, loc['province']) or norm(loc['province']) in {'metro manila', 'quezon city'}:
                    candidates.append(loc)
                elif len(options) == 1:
                    candidates.append(loc)
        if not candidate_names:
            # A subset of titles name an official barangay in the comma-delimited
            # location tail without spelling out "Barangay" or "Brgy.".
            for segment in title.split(',')[1:]:
                segment = re.sub(r'\([^)]*\)', ' ', segment)
                words = norm(segment).split()
                for start in range(len(words)):
                    for end in range(start + 1, min(len(words), start + 5) + 1):
                        candidate = ' '.join(words[start:end])
                        if candidate not in names_by_first.get(words[start], set()):
                            continue
                        options = known.get(candidate, [])
                        for loc in options:
                            if location_phrase(title_norm, loc['municipality']) and (
                                location_phrase(title_norm, loc['province']) or
                                norm(loc['province']) in {'metro manila', 'quezon city'} or len(options) == 1
                            ):
                                candidates.append(loc)
        unique = {x['id']: x for x in candidates}
        if not unique:
            unassigned.append(project)
            continue
        if len(unique) > 1:
            multi_place += 1
        for loc in unique.values():
            item = dict(project)
            item.update({'placeId': loc['id'], 'projectIndex': number,
                         'identityTitle': identity_title(title), 'sharedBarangayLine': len(unique) > 1})
            mapped.append(item)

    # A building identity requires the same normalized project wording and the same official barangay.
    # Coordinates are stripped and never used as evidence. Duplicate identical titles in one year
    # stay separate so they cannot manufacture an upgrade level.
    by_identity_year = defaultdict(list)
    for item in mapped:
        by_identity_year[(item['placeId'], item['identityTitle'], int(item['year']))].append(item)
    buildings = defaultdict(list)
    for (pid, title, year), rows in by_identity_year.items():
        if not title or len(rows) != 1:
            for row in rows:
                row['buildingKey'] = f"{pid}|row:{row['projectIndex']}"
                row['identityConfidence'] = 'Unresolved: duplicate or generic title in the same year'
                buildings[row['buildingKey']].append(row)
            continue
        key = f'{pid}|{title}'
        row = rows[0]
        row['buildingKey'] = key
        row['identityConfidence'] = 'Same normalized title and official barangay; physical site not independently verified'
        buildings[key].append(row)

    for records in buildings.values():
        years = sorted({int(r['year']) for r in records})
        for row in records:
            row['level'] = years.index(int(row['year'])) + 1
            row['repeat'] = len(years) > 1 and int(row['year']) != years[0]
            row['repeatYears'] = years

    by_place = defaultdict(list)
    for row in mapped:
        by_place[row['placeId']].append(row)
    barangays = []
    for loc in place_rows:
        rows = by_place.get(loc['id'], [])
        building_rows = {r['buildingKey']: r for r in rows}
        barangays.append({
            **loc,
            'projectRows': len(rows),
            'buildingCount': len(building_rows),
            'highestLevel': max((r['level'] for r in rows), default=0),
            'allocationPesos': sum(int(r.get('amountPesos') or 0) for r in rows),
            'projects': sorted(rows, key=lambda r: (int(r['year']), r['name'].casefold(), r.get('source', ''))),
        })
    barangays.sort(key=lambda b: (b['region'].casefold(), b['province'].casefold(), b['municipality'].casefold(), b['barangay'].casefold()))
    years_summary = []
    for year in sorted({int(r['year']) for r in projects}):
        source_rows = [r for r in projects if int(r['year']) == year]
        rows = {r['projectIndex']: r for r in mapped if int(r['year']) == year}
        years_summary.append({'year': year, 'stage': 'HGAB 3rd' if year == 2027 else 'GAA',
                              'classifiedRows': len(source_rows), 'linkedRows': len(rows),
                              'unlinkedRows': len(source_rows) - len(rows),
                              'allocationPesos': sum(int(r.get('amountPesos') or 0) for r in rows.values())})
    result = {
        'title': 'MPB allocations by official barangay',
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'source': 'ODV unified location hierarchy; FY2016 DPWH family extract and FY2017–FY2018 BetterGov GAA Explorer DPWH title rows; FY2020–FY2026 integrated GAA project records; exact FY2027 HGAB MPB PAP rows',
        'periods': years_summary,
        'summary': {
            'officialBarangays': len(barangays), 'barangaysWithMpb': sum(bool(x['projectRows']) for x in barangays),
            'mappedProjectRows': len({r['projectIndex'] for r in mapped}), 'mappedBarangayLinks': len(mapped), 'classifiedProjectRows': len(projects),
            'unmappedProjectRows': len(unassigned), 'sharedMultiBarangayProjectRows': multi_place,
            'buildingIdentities': len(buildings),
            'allocationPesos': sum(int(r.get('amountPesos') or 0) for r in {r['projectIndex']: r for r in mapped}.values()),
            'allocationAcrossBarangayLinksPesos': sum(int(r.get('amountPesos') or 0) for r in mapped),
            'caveat': 'Allocation records are not expenditures or verified construction costs. Repeat levels use matching normalized titles and official barangay identity, never proximity; they are review signals, not proof that physical construction occurred. A line naming multiple barangays is associated with each named barangay at its full amount, so barangay totals overlap and must not be added together.'
        },
        'repeatMethod': 'Same normalized MPB project title in the same official barangay across distinct fiscal years. Coordinate text is removed and proximity is never used. Identical titles duplicated within one year are kept separate and marked unresolved.',
        'periodScope': 'Eleven fiscal-year slices with project-level MPB data: FY2016–FY2018 GAA Explorer title-classified DPWH rows and FY2020–FY2026 GAA plus FY2027 HGAB 3rd-reading rows. FY2019 is omitted because the manifest snapshot does not provide named DPWH project rows. FY2016–FY2018 are a separate published-source baseline; earlier unobserved repeats are not implied to be the first physical construction.',
        'historicalSource': {'manifestUrl': legacy.get('manifestUrl'), 'periods': legacy.get('periods'), 'classification': legacy.get('classification'), 'gaps': legacy.get('gaps')},
        'historicalGaaBaseline': {'manifestUrl': 'https://budget-assets.bettergov.ph/gaa-explorer/manifest.json', 'years': [2016, 2017, 2018], 'scope': 'DPWH current-new-appropriation project-family rows classified from PAP titles; a separate historical layer, assigned to current barangay identities where the title names one.'},
        'barangays': barangays,
    }
    payload = json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n'
    data_path = STATIC / DATA_NAME
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(payload, encoding='utf-8')
    (OUT / DATA_NAME).write_text(payload, encoding='utf-8')

    # A compact per-barangay payload keeps the shareable base page fast and avoids
    # downloading the full project-record inventory for every base view.
    base_barangays = []
    for b in barangays:
        per_year = defaultdict(int)
        per_year_project = {}
        by_building = defaultdict(list)
        for row in b['projects']:
            year = int(row['year'])
            per_year_project[(year, row['projectIndex'])] = int(row.get('amountPesos') or 0)
            by_building[row['buildingKey']].append(row)
        for (year, _), amount in per_year_project.items():
            per_year[year] += amount
        base_barangays.append({
            'id': b['id'], 'barangay': b['barangay'], 'municipality': b['municipality'],
            'province': b['province'], 'region': b['region'],
            'allocationByYear': [{'year': y, 'amountPesos': amount} for y, amount in sorted(per_year.items())],
            'buildings': [{
                'name': sorted(rows, key=lambda r: (int(r['year']), str(r.get('name') or '').casefold()))[-1].get('name') or 'Named MPB structure',
                'levelHistory': [{'year': int(r['year']), 'level': int(r.get('level') or 0), 'amountPesos': int(r.get('amountPesos') or 0)}
                                 for r in sorted(rows, key=lambda r: int(r['year']))],
            } for rows in by_building.values()],
        })
    base_data = {'generatedAtUtc': result['generatedAtUtc'], 'periods': years_summary, 'barangays': base_barangays}
    base_payload = json.dumps(base_data, ensure_ascii=False, separators=(',', ':')) + '\n'
    base_data_path = STATIC / BASE_DATA_NAME
    base_data_path.write_text(base_payload, encoding='utf-8')
    (OUT / BASE_DATA_NAME).write_text(base_payload, encoding='utf-8')
    for destination in (STATIC, OUT):
        shutil.copytree(BASE_ASSETS, destination / 'mpb-assets', dirs_exist_ok=True)
    html = (ROOT / 'report_assets' / PAGE_NAME).read_text(encoding='utf-8')
    version = hashlib.sha256(data_path.read_bytes()).hexdigest()[:12]
    html = html.replace('mpb-barangay-data.json?v=1', f'mpb-barangay-data.json?v={version}')
    base_template = (ROOT / 'report_assets' / BASE_PAGE_NAME).read_bytes()
    base_page_version = hashlib.sha256(base_template + base_payload.encode('utf-8')).hexdigest()[:12]
    html = html.replace('mpb-base.html?v=1&amp;place=', f'mpb-base.html?v={base_page_version}&amp;place=')
    from uniform_report_menu import NAV, apply_page
    if 'report-disclaimer.css' not in html:
        html = html.replace('</head>', '<link rel="stylesheet" href="report-disclaimer.css?v=20261029-01"></head>', 1)
    html = apply_page(html, PAGE_NAME)
    for path in (STATIC / PAGE_NAME, OUT / PAGE_NAME):
        path.write_text(html, encoding='utf-8')
    base_html = (ROOT / 'report_assets' / BASE_PAGE_NAME).read_text(encoding='utf-8')
    base_version = hashlib.sha256(base_data_path.read_bytes()).hexdigest()[:12]
    base_html = base_html.replace('mpb-barangay-base-data.json?v=1', f'mpb-barangay-base-data.json?v={base_version}')
    from uniform_report_menu import apply_mpb_source_footer, apply_page, apply_share_build_meta
    base_html = apply_mpb_source_footer(base_html)
    base_html = apply_page(base_html, BASE_PAGE_NAME)
    # This is a shareable detail page: keep its compact deployment footer instead
    # of the full research-status banner already supplied by the common template.
    base_html = re.sub(r'<aside\b[^>]*class="research-status"[^>]*>.*?</aside>', '', base_html, flags=re.S)
    base_html = re.sub(r'<style id="research-status-style">.*?</style>', '', base_html, flags=re.S)
    base_html = re.sub(r'<script\b[^>]*id="research-status-script"[^>]*>.*?</script>', '', base_html, flags=re.S)
    base_html = apply_share_build_meta(base_html)
    for path in (STATIC / BASE_PAGE_NAME, OUT / BASE_PAGE_NAME):
        path.write_text(base_html, encoding='utf-8')
    # Keep the shared top-level report menu in sync, and mirror generated pages locally.
    for path in STATIC.glob('*.html'):
        if path.name in {'budget-trivia.html', PAGE_NAME}:
            continue
        text = path.read_text(encoding='utf-8')
        updated = re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>', lambda _: NAV, text, flags=re.S)
        if updated != text:
            path.write_text(updated, encoding='utf-8')
            mirror = OUT / path.name
            if mirror.exists():
                mirror.write_text(updated, encoding='utf-8')
    print(json.dumps({**result['summary'], 'dataBytes': len(payload.encode()), 'topByBudget': [
        {'barangay': b['barangay'], 'municipality': b['municipality'], 'province': b['province'], 'pesos': b['allocationPesos']}
        for b in sorted(barangays, key=lambda x: -x['allocationPesos'])[:5]
    ]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
