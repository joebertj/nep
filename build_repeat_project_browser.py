"""Prepare the historical repeats browser from the report's retained evidence."""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
from shutil import copyfile
from urllib.parse import urlencode, urlsplit

from analyze_mpb_proximity import PAIR, coordinates
from analyze_priority_repeats import classify
from location_data.repeat_browser_places import RepeatPlaces
from scr_page_shard_builder import normalize

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUTPUT = ROOT / 'analysis_output'
ASSETS = ROOT / 'report_assets'
ASSET_NAMES = ('repeat-project-browser.css', 'repeat-project-browser.js')
DATA_NAME = 'repeat-project-browser-data.json'
CURRENT_DATA_NAME = 'repeat-project-browser-2027-data.json'
PAGE_SIZE = 100
CATEGORY_KEYS = {'Road': 'roads', 'Bridge': 'bridges', 'Multi-purpose building': 'mpb', 'Flood control': 'flood'}
HISTORICAL_NOTE = ('Ranked by distinct matched GAA lines, then by their combined allocation. The 2027 stages are shown '
                   'separately. Title matches are candidates for review.')
CURRENT_NOTE = ('Ranked by FY2027 candidate pairs, then by allocation in the latest linked stage. Selected counterparts '
                'show how lines carried forward. Similar titles are candidates for review.')


def read(name):
    return json.loads((STATIC / name).read_bytes())


def amount(value):
    return int(float(value)) if value not in ('', None) else None


def points_in_title(title):
    points = []
    for match in PAIR.finditer(title):
        if min(len(value.split('.')[1]) for value in match.groups()) < 4:
            continue
        lat, lon = map(float, match.groups())
        if 116 <= lat <= 127 and 4 <= lon <= 22:
            lat, lon = lon, lat
        if 4 <= lat <= 22 and 116 <= lon <= 127 and [lat, lon] not in points:
            points.append([lat, lon])
    if not points:
        point = coordinates(title)
        if point['status'] == 'Usable printed point':
            points.append([point['latitude'], point['longitude']])
    return points


def row(stage, title, pesos, source='', url='', status=''):
    item = {'stage': stage, 'title': title, 'pesos': amount(pesos)}
    if source:
        item['source'] = source
    if url:
        item['url'] = url
    if status:
        item['status'] = status
    points = points_in_title(title)
    if points:
        item['points'] = points
    return item


def photo(kind, url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    if parsed.hostname == 's3.infrawatch.ph' and parsed.path.startswith('/nep/fy2027/') and kind == 'Proposal':
        label = 'DPWH Transparency · Proposal'
    elif parsed.hostname == 'budget-assets.bettergov.ph' and parsed.path.startswith('/hgab/2027/dpwh/supporting-documents/') and kind == 'HGAB':
        label = 'Senate HGAB supporting documents'
    else:
        return None
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in {'.pdf', '.jpg', '.jpeg', '.png', '.webp'}:
        return None
    item = {'stage': kind, 'label': label, 'url': url, 'format': 'pdf' if suffix == '.pdf' else 'image'}
    digest = hashlib.sha256(url.encode()).hexdigest()[:16]
    preview = f'repeat-project-photos/{digest}.webp'
    if (STATIC / preview).is_file():
        item['preview'] = preview
    return item


def photo_indexes(nep_codes, hgab_ids):
    proposal = defaultdict(list)
    hgab = defaultdict(list)
    index = read('dpwh-in-depth-data.json')
    project_shards = index.get('arrayShards', {}).get('projects', [])
    projects = (read(shard['path']) for shard in project_shards) if project_shards else [index.get('projects', [])]
    for shard in projects:
        for project in shard:
            if project['code'] not in nep_codes:
                continue
            for document in project.get('documentLinks', []):
                if 'photo' in document.get('type', '').lower():
                    attachment = photo('Proposal', document['url'])
                    if attachment:
                        proposal[project['code']].append(attachment)
    for project in read('hgab-document-coverage.json')['projects']:
        if project['hgabId'] not in hgab_ids:
            continue
        for document in project.get('senateDocuments', []):
            if 'photo' in document.get('documentType', '').lower() and document.get('url'):
                attachment = photo('HGAB', document['url'])
                if attachment:
                    hgab[project['hgabId']].append(attachment)
    return proposal, hgab


def scr_index(records=None):
    index = defaultdict(list)
    for record in records if records is not None else read('scr-data.json')['rows']:
        if record['program'] == 'dpwh' and record['house_title'] and record['house_php']:
            key = normalize(record['house_title']), amount(record['house_php'])
            index[key].append(record)
    return index


def find_scr(index, project):
    candidates = index.get((normalize(project['title']), project['pesos']), [])
    page = project.get('page')
    if len(candidates) > 1 and page:
        candidates = [record for record in candidates if record['house_page'] == str(page)]
    return candidates[0] if len(candidates) == 1 else None


def add_history(project, year, title, pesos, source, evidence):
    item = row(f'{year} GAA', title, pesos, source, status=evidence)
    # The two comparisons use the same GAA extracts. Keep a source line once.
    key = year, source, normalize(title), item['pesos']
    project['history'][key] = item


def category_key(title, program='', fallback=None):
    family = classify(program)
    if family in {'Multi-purpose building', 'Flood control'}:
        return CATEGORY_KEYS[family]
    if re.search(r'\b(?:viaduct|overpass|flyover)\b|\bbr\.\s*\d+', title, re.I):
        return 'bridges'
    title_category = classify(title)
    if not title_category and re.search(r'\b(?:highway|street|avenue)\b', title, re.I):
        title_category = 'Road'
    # A combined roads/bridges program does not identify the work by itself.
    if re.search(r'\broads?\b', program or '', re.I) and re.search(r'\bbridges?\b', program or '', re.I):
        family = None
    return CATEGORY_KEYS.get(title_category or fallback or family)


def fill_nep_counterparts(projects):
    missing = {project['hgabId']: project for project in projects.values()
               if 'nep' not in project and project.get('hgabId')}
    if not missing:
        return
    path = OUTPUT / 'hb_nep_comparison_3rd.csv'
    if not path.is_file():
        return
    with path.open(newline='', encoding='utf-8-sig') as stream:
        for match in csv.DictReader(stream):
            project = missing.get(match['hgab_id'])
            if not project or match['paired_one_to_one'] != 'True':
                continue
            code = match['nep_api_id']
            project['nepCode'] = code
            source = f"NEP · p. {match['nep_source_page']}" if match['nep_source_page'] else code
            url = 'project-documents.html?' + urlencode({'project': code}) if code else ''
            project['nep'] = row('2027 NEP', match['closest_nep_title'],
                                 match['closest_nep_amount_pesos'], source, url)
            project['house']['status'] = ('Clear retained link' if match['comparison'] == 'Exact normalized title found in NEP'
                                          else 'Potential retained link')
            del missing[match['hgab_id']]


def build(payload):
    projects = {}
    linked_hgab = {}
    retention = {link['sourceCode']: link for link in read('repeat-nep-hgab-survival.json')['proposals']}
    for record in payload['nepVsGaa']['rows']:
        code = record['source_code']
        if code not in projects:
            link = retention.get(code) or {}
            project = {'office': record['office'], 'history': {}, 'nepCode': code,
                       'reportedRegions': {record.get('region', '')},
                       'hgabId': link.get('hgabId'), 'nepCategory': record['category']}
            projects[code] = project
            project['nep'] = row('2027 NEP', record['project'], record['amount_2027'], code,
                                 'project-documents.html?' + urlencode({'project': code}))
            if link.get('hgabId'):
                linked_hgab[link['hgabId']] = project
                project['house'] = row('2027 HGAB', link['hgabTitle'], link['hgabPesos'],
                                       f"House 3rd reading · p. {link['hgabPage']}", status=link['status'])
                project['house']['page'] = link['hgabPage']
        add_history(projects[code], record['comparison_year'], record['prior_project'],
                    record['prior_amount'], record['prior_source'],
                    f"NEP title candidate · {record['similarity_pct']:g}%")
    for record in payload['hgabVsGaa']['rows']:
        code = record['hgabId']
        project = linked_hgab.get(code)
        if project is None:
            project = projects.setdefault(code, {'office': record['office'], 'history': {}, 'hgabId': code,
                                                 'reportedRegions': set()})
        project['reportedRegions'].add(record.get('region', ''))
        project['program'] = record['program']
        prior_status = project.get('house', {}).get('status', '')
        project['house'] = row('2027 HGAB', record['projectName'], record['amountPesos'],
                               f"{record['sourceVolume']} · p. {record['sourcePage']}", status=prior_status)
        project['house']['page'] = record['sourcePage']
        add_history(project, record['gaaYear'], record['gaaTitle'], record['gaaAmountPesos'],
                    record['gaaSource'], 'HGAB exact title and place')
    fill_nep_counterparts(projects)
    proposal_photos, house_photos = photo_indexes(
        {project.get('nepCode') for project in projects.values()},
        {project.get('hgabId') for project in projects.values()},
    )
    senate_rows = scr_index()
    for project in projects.values():
        house = project.pop('house', None)
        nep = project.pop('nep', None)
        scr = find_scr(senate_rows, house) if house else None
        stages = []
        if scr:
            stages.append(row('2027 SCR', scr['title'], scr['senate_php'], f"Senate committee report · p. {scr['senate_page']}",
                              scr['senate_pdf_url'], scr['status_label']))
            house['url'] = scr['house_pdf_url']
            project['reportedRegions'].add(scr.get('region', ''))
        if house:
            house.pop('page')
            stages.append(house)
        if nep:
            if (scr and scr['nep_pdf_url'] and normalize(nep['title']) == normalize(house['title'])
                    and nep['pesos'] is not None and nep['pesos'] == amount(scr['nep_php'])):
                nep['url'] = scr['nep_pdf_url']
            stages.append(nep)
        history = project.pop('history')
        staged = defaultdict(list)
        for key, value in sorted(history.items(), key=lambda entry: (-entry[0][0], -(entry[0][3] or 0), entry[0][1])):
            staged[key[0]].append(value)
        project['title'] = (house or nep)['title']
        project['category'] = category_key(project['title'], project.pop('program', '') or (scr or {}).get('pap'),
                                           project.pop('nepCategory', None))
        project['repeatCount'] = len(history)
        project['total'] = sum(item['pesos'] or 0 for item in history.values())
        project['stages'] = stages
        project['years'] = list(staged.items())
        docs = house_photos.get(project.pop('hgabId', None), []) + proposal_photos.get(project.pop('nepCode', None), [])
        if docs:
            project['photos'] = list({document['url']: document for document in docs}.values())
    return sorted(projects.values(), key=lambda project: (-project['repeatCount'], -project['total'], normalize(project['title'])))


def publish_index(records, data_name, mode):
    geography = RepeatPlaces().index(records)
    filters = {key: [] for key in CATEGORY_KEYS.values()}
    for i, record in enumerate(records):
        category = record.pop('category')
        if category:
            filters[category].append(i)
    files = {name: (ASSETS / name).read_bytes() for name in ASSET_NAMES}
    pages = []
    for start in range(PAGE_SIZE, len(records), PAGE_SIZE):
        content = json.dumps(records[start:start + PAGE_SIZE], ensure_ascii=False, separators=(',', ':')).encode()
        digest = hashlib.sha256(content).hexdigest()[:16]
        name = f'repeat-project-browser/{digest}.json'
        files[name] = content
        pages.append(name)
    index = {'mode': mode, 'total': len(records), 'pageSize': PAGE_SIZE, 'first': records[:PAGE_SIZE],
             'pages': pages, 'filters': filters, 'geography': geography}
    files[data_name] = json.dumps(index, ensure_ascii=False, separators=(',', ':')).encode()
    for name, content in files.items():
        for folder in (STATIC, OUTPUT):
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    previews = {document['preview'] for project in records for document in project.get('photos', []) if document.get('preview')}
    for name in previews:
        path = OUTPUT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        copyfile(STATIC / name, path)


def publish(payload):
    publish_index(build(payload), DATA_NAME, 'historical')
    return browser_markup(DATA_NAME, '#nep-historical', HISTORICAL_NOTE)


def browser_markup(data_name, comparison_href, note):
    names = (data_name, *ASSET_NAMES)
    versions = {name: hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12] for name in names}
    return (ASSETS / 'repeat-project-browser.html').read_text().format(
        comparison_href=comparison_href,
        note=note,
        data=f'{data_name}?v={versions[data_name]}',
        css=f'{ASSET_NAMES[0]}?v={versions[ASSET_NAMES[0]]}',
        script=f'{ASSET_NAMES[1]}?v={versions[ASSET_NAMES[1]]}',
    )
