#!/usr/bin/env python3
"""Build a barangay-level MPB allocation and repeat-title inventory."""
import csv
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
MAP_LINES = ROOT / 'data_sources' / 'bettergov-mpb-years-lines.csv'
MAP_SUMMARY = ROOT / 'data_sources' / 'bettergov-mpb-years-summary.json'
PSGC_LOCATIONS = ROOT / 'data_sources' / 'bettergov-psgc-locations.jsonl'
DATA_NAME = 'mpb-barangay-data.json'
INDEX_NAME = 'mpb-barangay-index.json'
DETAIL_SHARD_DIR = 'mpb-barangay-detail-shards'
DETAIL_SHARD_SIZE = 100
PAGE_NAME = 'mpb-barangay.html'
BASE_DATA_NAME = 'mpb-barangay-base-data.json'
BASE_PAGE_NAME = 'mpb-base.html'
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


REGION_LABELS = {
    '01': 'REGION 1', '02': 'REGION 2', '03': 'REGION 3', '04': 'REGION 4A',
    '05': 'REGION 5', '06': 'REGION 6', '07': 'REGION 7', '08': 'REGION 8',
    '09': 'REGION 9', '10': 'REGION 10', '11': 'REGION 11', '12': 'REGION 12',
    '13': 'NCR', '14': 'CAR', '16': 'REGION 13', '17': 'MIMAROPA',
    '18': 'NIR', '19': 'BARMM',
}


def psgc_place_record(code, psgc, local_by_name):
    """Resolve a published PSGC barangay code to the page's official place row."""
    entry = psgc.get(code)
    if not entry or entry.get('level') != 'barangay':
        return None
    parent = psgc.get(entry.get('parent_code'), {})
    if parent.get('level') == 'sub_municipality':
        locality = psgc.get(parent.get('parent_code'), {})
    else:
        locality = parent
    ancestor = psgc.get(locality.get('parent_code'), {})
    if locality.get('level') == 'city' and ancestor.get('level') == 'region':
        province = locality.get('name') or ''
    else:
        province = ancestor.get('name') or ''
    region_code = next((r.get('code', '') for r in (entry, parent, locality, ancestor)
                        if r.get('level') == 'region'), '')
    region = REGION_LABELS.get(region_code[:2], '')
    barangay = entry.get('name') or ''
    candidates = local_by_name.get(norm(barangay), [])
    locality_key = norm(locality.get('name'))
    province_key = norm(province)
    narrowed = [row for row in candidates if
                locality_key in (norm(row.get('municipality')), norm(row.get('province'))) and
                (not province_key or province_key in (norm(row.get('province')), norm(row.get('municipality'))))]
    if len(narrowed) == 1:
        return {**narrowed[0], 'id': f'psgc:{code}', 'psgc': code}
    # A source PSGC row remains an official place even when the site location
    # crosswalk lacks it or uses an older spelling. Preserve it with a stable
    # normalized ID rather than dropping its matched allocations.
    municipality = locality.get('name') or ''
    return {
        'region': region or 'Unspecified region',
        'province': province or municipality,
        'municipality': municipality,
        'barangay': barangay,
        'district': '',
        'id': f'psgc:{code}',
        'psgc': code,
    }


def load_map_projects(local_locations):
    """Read the published MPB map line file, retaining barangay-level rows only."""
    psgc = {row['code']: row for row in
            (json.loads(line) for line in PSGC_LOCATIONS.read_text(encoding='utf-8').splitlines() if line.strip())}
    local_by_name = defaultdict(list)
    for row in local_locations:
        local_by_name[norm(row.get('barangay'))].append(row)
    projects, skipped_places, non_barangay = [], 0, 0
    by_year = defaultdict(lambda: {'classified': 0, 'unmapped': 0, 'nonBarangay': 0, 'amount': 0})
    with MAP_LINES.open(encoding='utf-8-sig', newline='') as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            year = int(row.get('fiscal_year') or 0)
            if not year:
                continue
            by_year[year]['classified'] += 1
            psgc_code = str(row.get('place_psgc') or '').strip()
            location = psgc_place_record(psgc_code, psgc, local_by_name)
            if location is None:
                if psgc_code and psgc.get(psgc_code, {}).get('level') != 'barangay':
                    non_barangay += 1
                    by_year[year]['nonBarangay'] += 1
                else:
                    skipped_places += 1
                    by_year[year]['unmapped'] += 1
                continue
            amount_key = 'house_bill_php' if year == 2027 else 'gaa_php'
            amount = int(float(row.get(amount_key) or 0))
            by_year[year]['amount'] += amount
            title = row.get('title') or row.get('title_as_published') or ''
            projects.append({
                'year': year,
                'stage': 'HGAB 3rd' if year == 2027 else 'GAA',
                'category': 'Multi-purpose building',
                'name': title,
                'amountPesos': amount,
                'source': f"BetterGov MPB map · FY{year} {'House Bill 10858' if year == 2027 else 'GAA'} · line {row.get('line_id') or index}",
                'sourceId': row.get('line_id') or str(index),
                'sourcePage': row.get('house_bill_pdf_page') if year == 2027 else row.get('gaa_pdf_page'),
                'locationBasis': row.get('placed_by') or '',
                'placePsgc': psgc_code,
                'longitude': row.get('longitude') or None,
                'latitude': row.get('latitude') or None,
                'flags': [flag for flag in (row.get('flags') or '').split('|') if flag],
                'placeId': location['id'],
                'identityTitle': identity_title(title),
                'projectIndex': index,
                'sharedBarangayLine': False,
            })
    return projects, skipped_places, non_barangay, by_year, psgc


def identity_title(title):
    """Normalize a named project title; no coordinates or distance are used."""
    title = COORDS.sub(' ', str(title or ''))
    title = re.sub(r'\b(?:brgy\.?|bgy\.?)\b', 'barangay', title, flags=re.I)
    value = norm(title)
    value = ACTION.sub(' ', value)
    return ' '.join(value.split())


def main():
    local_locations = json.loads(LOCATIONS.read_text(encoding='utf-8'))
    local_rows = []
    for loc in local_locations:
        row = {k: str(loc.get(k) or '').strip() for k in ('region', 'province', 'municipality', 'barangay', 'district')}
        if all(row[k] for k in ('region', 'province', 'municipality', 'barangay')):
            row['id'] = place_id(row)
            local_rows.append(row)
    projects, skipped_places, non_barangay, source_years, psgc = load_map_projects(local_rows)
    local_by_name = defaultdict(list)
    for row in local_rows:
        local_by_name[norm(row.get('barangay'))].append(row)
    # Keep the site location list complete, while adding any current official
    # PSGC barangays missing from the older unified crosswalk.
    place_by_id = {}
    for code, entry in psgc.items():
        if entry.get('level') != 'barangay':
            continue
        row = psgc_place_record(code, psgc, local_by_name)
        if row:
            row = dict(row)
            row['id'] = f'psgc:{code}'
            row['psgc'] = code
            place_by_id.setdefault(row['id'], row)
    place_rows = list(place_by_id.values())
    place_ids = {row['id'] for row in place_rows}
    mapped = [project for project in projects if project['placeId'] in place_ids]
    multi_place = 0

    # Keep the existing title-based repeat signal after adopting the published
    # map export's exact line-to-PSGC barangay assignments.
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
        row['identityConfidence'] = 'Same normalized project title and source-assigned official barangay; physical site not independently verified'
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
    for year in sorted(source_years):
        rows = [r for r in mapped if int(r['year']) == year]
        years_summary.append({'year': year, 'stage': 'HGAB 3rd' if year == 2027 else 'GAA',
                              'classifiedRows': source_years[year]['classified'], 'linkedRows': len(rows),
                              'unlinkedRows': source_years[year]['classified'] - len(rows),
                              'rowsAtBroaderOrUnplacedLevels': source_years[year].get('nonBarangay', 0) + source_years[year]['unmapped'],
                              'allocationPesos': sum(int(r.get('amountPesos') or 0) for r in rows)})
    map_summary = json.loads(MAP_SUMMARY.read_text(encoding='utf-8'))
    result = {
        'title': 'MPB allocations by official barangay',
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'source': 'BetterGov FY2015–FY2027 multi-purpose-building map line export. FY2015–FY2026 rows use listed GAA allocations; FY2027 rows use House Bill allocations. Barangay assignments use the export PSGC code and stated place basis (title or GPS); rows assigned only to broader administrative levels or no place are excluded from barangay rankings.',
        'mapSourceBuiltAtUtc': map_summary.get('built_at'),
        'mapSourceCommit': map_summary.get('source', {}).get('commit'),
        'periods': years_summary,
        'summary': {
            'officialBarangays': len(barangays), 'barangaysWithMpb': sum(bool(x['projectRows']) for x in barangays),
            'mappedProjectRows': len({r['projectIndex'] for r in mapped}), 'mappedBarangayLinks': len(mapped), 'classifiedProjectRows': len(projects),
            'unmappedProjectRows': sum(period['unlinkedRows'] for period in years_summary),
            'rowsAtBroaderOrUnplacedLevels': non_barangay + skipped_places,
            'sharedMultiBarangayProjectRows': multi_place,
            'buildingIdentities': len(buildings),
            'allocationPesos': sum(int(r.get('amountPesos') or 0) for r in {r['projectIndex']: r for r in mapped}.values()),
            'allocationAcrossBarangayLinksPesos': sum(int(r.get('amountPesos') or 0) for r in mapped),
            'caveat': 'Allocation records are not expenditures or verified construction costs. Repeat levels use matching normalized titles and official barangay identity, never proximity; they are review signals, not proof that physical construction occurred. A line naming multiple barangays is associated with each named barangay at its full amount, so barangay totals overlap and must not be added together.'
        },
        'repeatMethod': 'Same normalized MPB project title in the same official barangay across distinct fiscal years. Coordinate text is removed and proximity is never used. Identical titles duplicated within one year are kept separate and marked unresolved.',
        'periodScope': 'Uses BetterGov public MPB map line export for FY2015–FY2026 GAA amounts and FY2027 House Bill amounts. Barangay assignment follows the export’s official PSGC code and place basis (title or GPS); rows assigned to broader administrative areas or without a barangay PSGC assignment are excluded from barangay rankings.',
        'barangays': barangays,
    }
    payload = json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n'
    data_path = OUT / DATA_NAME
    data_path.parent.mkdir(parents=True, exist_ok=True)
    (OUT / DATA_NAME).write_text(payload, encoding='utf-8')

    # The page starts with an aggregate index. Full project histories are stored
    # in small place-group shards and fetched only for expanded rows or lookups.
    index_rows = []
    detail_groups = []
    years = [int(period['year']) for period in years_summary]
    for start in range(0, len(barangays), DETAIL_SHARD_SIZE):
        group = barangays[start:start + DETAIL_SHARD_SIZE]
        shard_name = f'barangays-{start // DETAIL_SHARD_SIZE + 1:03d}.json'
        detail_groups.append((shard_name, [
            {'id': b['id'], 'projects': b['projects']} for b in group if b['projects']
        ]))
        for offset, b in enumerate(group):
            by_year = defaultdict(list)
            for project in b['projects']:
                by_year[int(project['year'])].append(project)
            levels = {}
            cumulative_rows = 0
            year_stats = []
            for year_index, year in enumerate(years):
                yearly = by_year.get(year, [])
                if yearly:
                    cumulative_rows += len(yearly)
                    for project in yearly:
                        key = project['buildingKey']
                        levels[key] = max(levels.get(key, 0), int(project.get('level') or 0))
                    year_stats.append([
                        year_index,
                        sum(int(project.get('amountPesos') or 0) for project in yearly),
                        len(yearly), cumulative_rows, len(levels),
                        max(levels.values(), default=0), sum(levels.values()),
                    ])
            shard_index = start // DETAIL_SHARD_SIZE
            index_rows.append([
                b['id'], b['barangay'], b['municipality'], b['province'], b['region'],
                f'barangays-{shard_index + 1:03d}.json', year_stats,
            ])
    index_payload = json.dumps({
        'generatedAtUtc': result['generatedAtUtc'], 'periods': years_summary,
        'summary': result['summary'], 'barangayRows': index_rows,
    }, ensure_ascii=False, separators=(',', ':')) + '\n'
    index_bytes = index_payload.encode('utf-8')
    for destination in (STATIC / DETAIL_SHARD_DIR, OUT / DETAIL_SHARD_DIR):
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True, exist_ok=True)
    for destination in (STATIC, OUT):
        (destination / INDEX_NAME).write_bytes(index_bytes)
    for destination in (STATIC / DETAIL_SHARD_DIR, OUT / DETAIL_SHARD_DIR):
        for name, rows in detail_groups:
            shard_payload = json.dumps({'barangays': rows}, ensure_ascii=False, separators=(',', ':'))
            if len(shard_payload.encode('utf-8')) > 10_000_000:
                raise RuntimeError(f'MPB detail shard exceeds 10 MB: {name}')
            (destination / name).write_text(shard_payload, encoding='utf-8')
    stale_published_data = STATIC / DATA_NAME
    if stale_published_data.exists():
        stale_published_data.unlink()

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
    version = hashlib.sha256(index_bytes).hexdigest()[:12]
    html = html.replace('mpb-barangay-index.json?v=1', f'mpb-barangay-index.json?v={version}')
    app_js_text = (ROOT / 'report_assets' / 'mpb-barangay.js').read_text(encoding='utf-8')
    app_js_text = app_js_text.replace(
        'mpb-barangay-index.json?v=1',
        f'mpb-barangay-index.json?v={version}',
    )
    app_js = app_js_text.encode('utf-8')
    app_js_version = hashlib.sha256(app_js).hexdigest()[:12]
    html = html.replace('mpb-barangay.js?v=1', f'mpb-barangay.js?v={app_js_version}')
    (STATIC / 'mpb-barangay.js').write_bytes(app_js)
    (OUT / 'mpb-barangay.js').write_bytes(app_js)
    plotly_path = STATIC / 'plotly-2.35.2.min.js'
    if plotly_path.is_file():
        plotly_version = hashlib.sha256(plotly_path.read_bytes()).hexdigest()[:12]
        html = html.replace('plotly-2.35.2.min.js?v=1', f'plotly-2.35.2.min.js?v={plotly_version}')
    base_template = (ROOT / 'report_assets' / BASE_PAGE_NAME).read_bytes()
    base_page_version = hashlib.sha256(base_template + base_payload.encode('utf-8')).hexdigest()[:12]
    html = html.replace('mpb-base.html?v=1&amp;place=', f'mpb-base.html?v={base_page_version}&amp;place=')
    from uniform_report_menu import apply_page
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
    # This builder owns the MPB barangay pages only. Other reports get shared menu markup from their own builders.
    print(json.dumps({**result['summary'], 'dataBytes': len(payload.encode()), 'topByBudget': [
        {'barangay': b['barangay'], 'municipality': b['municipality'], 'province': b['province'], 'pesos': b['allocationPesos']}
        for b in sorted(barangays, key=lambda x: -x['allocationPesos'])[:5]
    ]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
