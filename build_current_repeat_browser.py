"""Build the project browser for FY2027 within-stage repeat candidates."""
from collections import Counter, defaultdict
import csv
import json

from analyze_within_stage_repeats import HGAB_STAGE, NEP_STAGE, SCR_STAGE
from build_repeat_project_browser import (
    CURRENT_DATA_NAME, CURRENT_NOTE, OUTPUT, browser_markup, category_key,
    find_scr, photo_indexes, publish_index, read, row,
)
from scr_page_shard_builder import normalize

STAGES = (SCR_STAGE, HGAB_STAGE, NEP_STAGE)
LABELS = {SCR_STAGE: '2027 SCR', HGAB_STAGE: '2027 HGAB', NEP_STAGE: '2027 NEP'}


def build(within):
    nep = {r['id']: r for r in json.loads((OUTPUT / 'nep_dpwh_baseline.json').read_bytes())['data']['data']}
    with (OUTPUT / 'hb_nep_comparison_3rd.csv').open(newline='', encoding='utf-8-sig') as stream:
        house = {r['hgab_id']: r for r in csv.DictReader(stream)}
    senate = {r['id']: r for r in read('scr-data.json')['rows'] if r['program'] == 'dpwh'}
    sources = {NEP_STAGE: nep, HGAB_STAGE: house, SCR_STAGE: senate}
    from build_repeat_project_browser import scr_index
    senate_index = scr_index(senate.values())

    edges = defaultdict(set)
    candidate_counts = Counter()

    def connect(left, right):
        edges[left].add(right)
        edges[right].add(left)

    for pair in within['pairs']:
        left, right = ((pair['stage'], pair[side]['id']) for side in ('left', 'right'))
        connect(left, right)
        candidate_counts.update((left, right))

    api_ids = defaultdict(list)
    for record in nep.values():
        if record.get('apiId'):
            api_ids[record['apiId']].append(record['id'])
    nep_links, senate_links = {}, {}
    for key, record in house.items():
        if record['paired_one_to_one'] == 'True':
            native = record['nep_id']
            by_code = api_ids[record['nep_api_id']]
            if native in nep:
                nep_links[key] = native
            elif len(by_code) == 1:
                nep_links[key] = by_code[0]
        matched = find_scr(senate_index, {'title': record['projectName'], 'pesos': int(record['amountPesos']),
                                         'page': record['sourcePage']})
        if matched:
            senate_links[key] = matched['id']

    uses = Counter(nep_links.values())
    for key, target in nep_links.items():
        if uses[target] == 1:
            connect((HGAB_STAGE, key), (NEP_STAGE, target))
    uses = Counter(senate_links.values())
    for key, target in list(senate_links.items()):
        if uses[target] == 1:
            connect((HGAB_STAGE, key), (SCR_STAGE, target))
        else:
            del senate_links[key]

    groups = []
    seen = set()
    for seed in candidate_counts:
        if seed in seen:
            continue
        group = []
        pending = [seed]
        seen.add(seed)
        while pending:
            node = pending.pop()
            group.append(node)
            for neighbor in edges[node] - seen:
                pending.append(neighbor)
                seen.add(neighbor)
        groups.append(group)

    proposal_photos, house_photos = photo_indexes(
        {nep[key].get('apiId') for group in groups for stage, key in group if stage == NEP_STAGE},
        {key for group in groups for stage, key in group if stage == HGAB_STAGE},
    )

    def budget_record(stage, key):
        source = sources[stage][key]
        if stage == SCR_STAGE:
            page = source['senate_page']
            url = source['senate_pdf_url'] if page else source['house_pdf_url']
            citation = f'SCR Annex A-4 · p. {page}' if page else 'House schedule · carried into SCR'
            return row(LABELS[stage], source['title'], source['senate_php'], citation, url, source['status_label'])
        if stage == HGAB_STAGE:
            match = senate.get(senate_links.get(key), {})
            return row(LABELS[stage], source['projectName'], source['amountPesos'],
                       f"{key} · House p. {source['sourcePage']}", match.get('house_pdf_url', ''))
        code = source.get('apiId')
        url = f'project-documents.html?project={code}' if code else ''
        return row(LABELS[stage], source['projectName'], source['amountPesos'],
                   f"{key} · NEP p. {source['sourcePage']}", url)

    projects = []
    for group in groups:
        evidence = [(stage, key, budget_record(stage, key)) for stage, key in group]
        evidence.sort(key=lambda item: (STAGES.index(item[0]), -(item[2]['pesos'] or 0), item[1]))
        latest, key, anchor = evidence[0]
        source = sources[latest][key]
        photos = {}
        for stage, key, record in evidence:
            if stage == HGAB_STAGE:
                matches = house_photos.get(key, [])
            elif stage == NEP_STAGE:
                matches = proposal_photos.get(nep[key].get('apiId'), [])
            else:
                continue
            for attachment in matches:
                photos.setdefault(attachment['url'], {**attachment, 'projectTitle': record['title']})
        projects.append({
            'title': anchor['title'], 'office': source['office'],
            'reportedRegions': {sources[stage][key].get('region', '') for stage, key in group},
            'category': category_key(anchor['title'], source.get('pap3') or source.get('pap')),
            'repeatCount': sum(candidate_counts[node] for node in group) // 2,
            'total': sum(record['pesos'] or 0 for stage, _, record in evidence if stage == latest),
            'totalLabel': LABELS[latest] + ' allocation',
            'stages': [record for _, _, record in evidence], 'years': [], 'photos': list(photos.values()),
        })
    return sorted(projects, key=lambda project: (-project['repeatCount'], -project['total'], normalize(project['title'])))


def publish(within):
    publish_index(build(within), CURRENT_DATA_NAME, '2027')
    return browser_markup(CURRENT_DATA_NAME, '#within-stage-repeats', CURRENT_NOTE)
