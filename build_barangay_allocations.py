#!/usr/bin/env python3
"""Build HGAB 3rd-reading DPWH allocations associated with named barangays."""
import json
import re
import hashlib
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
OUT = ROOT / 'analysis_output'
SOURCE = ROOT / 'hb10858_3rd_dpwh_projects.json'
BARANGAY = re.compile(r'\b(?:barangay|brgy\.?)\s+(.+?)(?=,|;|\(|\b(?:barangay|brgy\.?)\b|\s+(?:section|road|rd\.?|fmr|sta\.?|station|chainage|km\.?|bridge|phase)\b|$)', re.I)
MPB_DATA = STATIC / 'mpb-barangay-data.json'
GENERIC = {
    'health station', 'health center', 'health centre', 'health station bhs',
    'barangay health station', 'health station with birthing home', 'health center bhs',
    'hall', 'covered court', 'multipurpose building', 'multi purpose building',
    'road', 'bridge', 'drainage', 'flood control', 'health facility',
}
CUT_WORDS = re.compile(r'\b(?:section|road|rd\.?|fmr|sta\.?|station|chainage|km\.?|phase|bridge|project)\b', re.I)


def clean_name(value):
    value = re.sub(r'\s+', ' ', value).strip(' .,-–—')
    value = re.sub(r'\s*-\s*', '-', value)
    value = re.sub(r'\s+(?:to|and|&)$', '', value, flags=re.I).strip(' .,-–—')
    value = re.sub(r'\s*[-–—]\s*$', '', value).strip()
    value = re.sub(r'\s+-\s+(?:poblacion|pob\.?|brgy\.?|barangay)\b.*$', '', value, flags=re.I).strip()
    return value


def context_for(title, matches, names, region, office):
    tail = title[matches[-1].end():]
    # The first non-chainage parenthetical after the last named barangay often gives its municipality.
    parens = re.findall(r'\(([^()]*)\)', tail)
    locality = ''
    for item in parens:
        if re.search(r'\d|sta\.?|chainage|km\.?|section|\bto\b|\bfrom\b', item, re.I):
            continue
        item = re.sub(r'\b(?:barangay|brgy\.?)\b', '', item, flags=re.I).strip(' ,.-')
        if item:
            locality = item
            break
    parts = []
    for part in tail.split(','):
        part = re.sub(r'\([^)]*\)', ' ', part)
        part = re.sub(r'\b(?:sta\.?|chainage|km\.?)\b.*', ' ', part, flags=re.I)
        part = re.sub(r'\b(?:section|segment)\b.*', ' ', part, flags=re.I)
        part = re.sub(r'\b(?:start|end)(?:\s+[NSEW])*(?:\s+\b(?:start|end)\b.*)?', ' ', part, flags=re.I)
        part = re.sub(r'\b[NSEW]\b', ' ', part, flags=re.I)
        part = part.replace('°', ' ')
        part = re.sub(r'\d[\d+.,\s-]*', ' ', part)
        part = re.sub(r'[()]', ' ', part)
        part = re.sub(r'\s+', ' ', part).strip(' .,-–—')
        if part and not CUT_WORDS.search(part) and not re.fullmatch(r'(?i)(?:barangay|brgy)', part):
            parts.append(part)
    normalized_names = {re.sub(r'[^a-z0-9]+', ' ', n.casefold()).strip() for n in names}
    parts = [part for part in parts if re.sub(r'[^a-z0-9]+', ' ', part.casefold()).strip() not in normalized_names]
    if locality:
        context_parts = [locality] + [p for p in parts[-2:] if p.casefold() != locality.casefold()]
        context = ', '.join(context_parts[-2:])
    else:
        context = ', '.join(parts[-2:])
    context = re.sub(r'\s+', ' ', context).strip(' ,.-')
    if not re.search(r'[A-Za-z]', context or '') or context.casefold() in {'start', 'end', 'start end'}:
        context = ''
    if not context:
        context = f'{office or "Locality not stated"} · {region or "Region not stated"}'
    return context


def main():
    raw = json.loads(SOURCE.read_text())['data']['data']
    mpb_data = json.loads(MPB_DATA.read_text())
    mpb_2027 = next((period for period in mpb_data.get('periods', []) if period.get('year') == 2027), {})
    grouped = {}
    project_places = defaultdict(list)
    source_projects = [r for r in raw if r.get('allocationKind') == 'project' and isinstance(r.get('amountPesos'), (int, float)) and r['amountPesos'] > 0]
    mentioned_projects = set()
    for row in source_projects:
        title = str(row.get('projectName') or '')
        matches = list(BARANGAY.finditer(title))
        if not matches:
            continue
        names = []
        for match in matches:
            name = clean_name(match.group(1))
            # Remove common title descriptors where “Barangay” names a facility type, not a place.
            name = re.sub(r'\s+(?:Health Station|Health Center|Health Centre|Covered Court|Multi[- ]Purpose Building|Hall|FMR)$', '', name, flags=re.I).strip()
            if not name or name.casefold() in GENERIC or len(name) < 2 or re.fullmatch(r'\d+', name):
                continue
            if re.fullmatch(r'(?i)(?:no\.?|various|different|selected|identified|several)\s+barangays?', name):
                continue
            names.append(name)
        names = list(dict.fromkeys(names))
        if not names:
            continue
        context = context_for(title, matches, names, row.get('region', ''), row.get('office', ''))
        for name in names:
            key = (re.sub(r'[^a-z0-9]+', ' ', name.casefold()).strip(), re.sub(r'[^a-z0-9]+', ' ', context.casefold()).strip())
            item = grouped.setdefault(key, {'barangay': name, 'localityContext': context, 'region': row.get('region', ''), 'officeExamples': set(), 'projects': {}, 'sourcePages': set()})
            item['projects'][row['id']] = row
            if row.get('office'):
                item['officeExamples'].add(row['office'])
            if row.get('sourcePage'):
                item['sourcePages'].add(row['sourcePage'])
            project_places[row['id']].append(name)
            mentioned_projects.add(row['id'])
    # Include FY2027 MPB rows that the shared official-location matcher resolves
    # even when their printed titles omit the literal Barangay/Brgy prefix.
    explicit_project_count = len(mentioned_projects)
    source_by_id = {str(row['id']): row for row in source_projects}
    names_by_project = defaultdict(set)
    for item in grouped.values():
        normalized_name = re.sub(r'[^a-z0-9]+', ' ', item['barangay'].casefold()).strip()
        for project_id in item['projects']:
            names_by_project[str(project_id)].add(normalized_name)
    mpb_added_projects = set()
    for place in mpb_data.get('barangays', []):
        locality = ', '.join(x for x in (place.get('municipality'), place.get('province')) if x)
        for project in place.get('projects', []):
            if int(project.get('year') or 0) != 2027:
                continue
            project_id = str(project.get('sourceId') or '')
            source_row = source_by_id.get(project_id)
            barangay_name = str(place.get('barangay') or '').strip()
            normalized_name = re.sub(r'[^a-z0-9]+', ' ', barangay_name.casefold()).strip()
            if not source_row or not normalized_name or normalized_name in names_by_project[project_id]:
                continue
            key = (normalized_name, re.sub(r'[^a-z0-9]+', ' ', locality.casefold()).strip())
            item = grouped.setdefault(key, {'barangay': barangay_name, 'localityContext': locality,
                'region': place.get('region', ''), 'officeExamples': set(), 'projects': {}, 'sourcePages': set()})
            item['projects'][source_row['id']] = source_row
            if source_row.get('office'):
                item['officeExamples'].add(source_row['office'])
            for page in source_row.get('sourcePages') or ([source_row['sourcePage']] if source_row.get('sourcePage') else []):
                item['sourcePages'].add(page)
            names_by_project[project_id].add(normalized_name)
            mentioned_projects.add(source_row['id'])
            mpb_added_projects.add(project_id)
    places = []
    for item in grouped.values():
        projects = sorted(item['projects'].values(), key=lambda r: (-r['amountPesos'], r['projectName']))
        places.append({
            'barangay': item['barangay'], 'localityContext': item['localityContext'], 'region': item['region'],
            'officeExamples': sorted(item['officeExamples']), 'projectCount': len(projects),
            'allocationPesos': sum(r['amountPesos'] for r in projects),
            'projects': [{'id': r['id'], 'projectName': r['projectName'], 'amountPesos': r['amountPesos'], 'office': r.get('office',''), 'sourceVolume': r.get('sourceVolume',''), 'sourcePages': r.get('sourcePages') or ([r['sourcePage']] if r.get('sourcePage') else [])} for r in projects]
        })
    places.sort(key=lambda x: (-x['allocationPesos'], -x['projectCount'], x['barangay'].casefold(), x['localityContext'].casefold()))
    project_total = sum(r['amountPesos'] for r in source_projects if r['id'] in mentioned_projects)
    result = {
        'title': 'HGAB 3rd-reading DPWH project allocations associated with named barangays',
        'source': 'House Bill No. 10858, General Appropriations Bill FY 2027, 3rd-reading DPWH project rows',
        'sourceFile': SOURCE.name,
        'generatedFromProjectRows': len(source_projects), 'projectsWithBarangayMentions': len(mentioned_projects),
        'projectsWithExplicitBarangayMarker': explicit_project_count,
        'mpbProjectsAddedFromOfficialLocationMatch': len(mpb_added_projects),
        'mpb2027LinkedProjectRows': int(mpb_2027.get('linkedRows') or 0),
        'mpb2027LinkedAllocationPesos': int(mpb_2027.get('allocationPesos') or 0),
        'barangayPlaceCount': len(places), 'allocationAcrossMentionedProjectsPesos': project_total,
        'placeAllocationTotalPesos': sum(x['allocationPesos'] for x in places),
        'countingNote': 'Project rows explicitly naming a barangay are associated with each distinct title name. For FY2027 MPB PAP rows only, the shared MPB matcher also supplies official-barangay matches where the title omits the Barangay/Brgy prefix. If a project names multiple barangays, its full amount appears under each named place; place totals must not be added together as a program total. Locality context is taken from the printed title or the ODV unified location list; ambiguous title contexts remain separate.',
        'places': places
    }
    for path in [OUT / 'barangay-allocation-data.json', STATIC / 'barangay-allocation-data.json']:
        path.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    from uniform_report_menu import NAV, apply_page
    template = (ROOT / 'report_assets' / 'barangay.html').read_text()
    data_version = hashlib.sha256((STATIC / 'barangay-allocation-data.json').read_bytes()).hexdigest()[:12]
    page = apply_page(template, 'barangay.html').replace('barangay-allocation-data.json?v=1', f'barangay-allocation-data.json?v={data_version}')
    page = page.replace('</head>', '<link rel=\"stylesheet\" href=\"report-disclaimer.css?v=20261031-01\"></head>', 1) if 'report-disclaimer.css' not in page else page
    for path in [STATIC / 'barangay.html', OUT / 'barangay.html']:
        path.write_text(page)
    # Add the new page consistently to existing top-level report navigation.
    for path in STATIC.glob('*.html'):
        if path.name in {'budget-trivia.html', 'barangay.html'}:
            continue
        text = path.read_text()
        updated = re.sub(r'<nav\b[^>]*class=\"report-nav\"[^>]*>.*?</nav>', lambda m: NAV, text, flags=re.S)
        if updated != text:
            path.write_text(updated)
            mirror = OUT / path.name
            if mirror.exists(): mirror.write_text(updated)
    print(json.dumps({k: result[k] for k in ['generatedFromProjectRows','projectsWithBarangayMentions','barangayPlaceCount','allocationAcrossMentionedProjectsPesos','placeAllocationTotalPesos']}, indent=2))
    print('top 15:')
    for x in places[:15]: print(x['barangay'], '|', x['localityContext'], '|', x['projectCount'], '|', x['allocationPesos'])

if __name__ == '__main__': main()
