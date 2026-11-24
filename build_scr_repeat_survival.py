"""Trace distinct HGAB repeat candidates into the Senate committee report."""
from collections import Counter, defaultdict
import hashlib
import json

from analyze_within_stage_repeats import HGAB_STAGE, SCR_DATA
from build_repeat_project_browser import STATIC, OUTPUT, amount, find_scr, scr_index

FILE_NAME = 'repeat-hgab-scr-survival.json'
NEP_SURVIVAL = STATIC / 'repeat-nep-hgab-survival.json'
HGAB_HISTORICAL = STATIC / 'repeat-hgab-historical-gaa.json'
OUTCOMES = {
    'unchanged': 'Unchanged',
    'renamed': 'Renamed',
    'raised': 'Increased',
    'reduced': 'Reduced',
    'cut': 'Removed',
    'unresolved': 'Unresolved',
}
RETAINED = {'unchanged', 'renamed', 'raised', 'reduced'}


def cohort_summary(rows, occurrences):
    return {
        'lines': len(occurrences),
        'retained': sum(rows[key]['status'] in RETAINED for key in occurrences),
        'removed': sum(rows[key]['status'] == 'cut' for key in occurrences),
        'unresolved': sum(rows[key]['status'] == 'unresolved' for key in occurrences),
    }


def build(within, trace):
    historical = json.loads(HGAB_HISTORICAL.read_bytes())['rows']
    nep_pairs = Counter(record['hgabRetention']['hgabId'] for record in trace['comparisonPairs']
                        if record['hgabRetention']['hgabId'])
    occurrences = {}
    for proposal in trace['proposals']:
        if proposal['hgabId']:
            occurrences[proposal['hgabId']] = {
                'title': proposal['hgabTitle'], 'pesos': proposal['hgabPesos'],
                'page': proposal['hgabPage'], 'nepRetentionClass': proposal['status'],
            }
    historical_counts = Counter()
    for row in historical:
        row_id = row['hgabId']
        historical_counts[row_id] += 1
        occurrences.setdefault(row_id, {'title': row['projectName'], 'pesos': row['amountPesos'],
                                        'page': row['sourcePage']})
    pair_ids = []
    within_ids = set()
    for pair in within['pairs']:
        if pair['stage'] != HGAB_STAGE:
            continue
        members = tuple(pair[side]['id'] for side in ('left', 'right'))
        pair_ids.append(members)
        within_ids.update(members)
        for side in ('left', 'right'):
            row = pair[side]
            occurrences.setdefault(row['id'], {'title': row['projectName'], 'pesos': row['amountPesos'],
                                               'page': row['sourcePage']})
    index = scr_index()
    links = {key: find_scr(index, project) for key, project in occurrences.items()}
    uses = Counter(source['id'] for source in links.values() if source)
    pairs = defaultdict(list)
    rows = {}
    for key, project in occurrences.items():
        scr = links[key]
        status = 'unresolved'
        if scr and uses[scr['id']] == 1:
            if scr['status'] in RETAINED and (amount(scr['senate_php']) or 0) > 0:
                status = scr['status']
            elif scr['status'] == 'cut':
                status = 'cut'
        row = {
            'hgabId': key, 'hgabTitle': project['title'], 'hgabPesos': project['pesos'],
            'hgabPage': project['page'], 'nepComparisons': nep_pairs[key],
            'hgabComparisons': historical_counts[key], 'withinHgabPair': key in within_ids,
            'status': status,
        }
        if project.get('nepRetentionClass'):
            row['nepRetentionClass'] = project['nepRetentionClass']
        if status != 'unresolved':
            row.update(scrId=scr['id'], scrTitle=scr['title'],
                       scrPesos=0 if status == 'cut' else amount(scr['senate_php']),
                       scrPage=scr['senate_page'], scrSource=scr['senate_pdf_url'] if scr['senate_page'] else '',
                       hgabSource=scr['house_pdf_url'], scrRecord=scr['page_url'],
                       scrMatchBasis=scr['matched_by'])
        elif scr and uses[scr['id']] > 1:
            row['unresolvedReason'] = 'Multiple HGAB lines select the same SCR row'
        else:
            row['unresolvedReason'] = 'No unique HGAB title-and-allocation match with a usable SCR status'
        rows[key] = row
        if key in nep_pairs:
            pairs[status].append(row)

    grouped = []
    for status, label in OUTCOMES.items():
        members = pairs[status]
        grouped.append({
            'status': label, 'comparisonPairs': sum(row['nepComparisons'] for row in members),
            'lines': len(members), 'hgabPesos': sum(row['hgabPesos'] for row in members),
            'scrPesos': None if status == 'unresolved' else sum(row['scrPesos'] for row in members),
        })
    within_both_retained = sum(all(rows[key]['status'] in RETAINED for key in pair) for pair in pair_ids)
    data = {
        'nepLinked': cohort_summary(rows, nep_pairs),
        'nepComparisonPairs': sum(nep_pairs.values()),
        'nepLinkedBreakdown': grouped,
        'directHistorical': cohort_summary(rows, historical_counts),
        'withinHgab': {**cohort_summary(rows, within_ids), 'pairs': len(pair_ids), 'bothRetainedPairs': within_both_retained},
        'rows': list(rows.values()),
        'sources': [{'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                    for path in (NEP_SURVIVAL, HGAB_HISTORICAL, SCR_DATA, STATIC / 'within-stage-repeats.json')],
    }
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    for destination in (STATIC, OUTPUT):
        (destination / FILE_NAME).write_text(serialized, encoding='utf-8')
    return data


def render(data):
    from build_investigation_summary import section, table
    primary = data['nepLinked']
    share = primary['retained'] / primary['lines'] if primary['lines'] else 0
    body = (
        f'<p><strong>{primary["retained"]:,} of {primary["lines"]:,} distinct HGAB lines ({share:.1%})</strong> '
        f'carried a positive allocation into SCR. The starting cohort is the set of selected HGAB counterparts to '
        f'the historical NEP repeat candidates below. It covers {data["nepComparisonPairs"]:,} original GAA comparisons '
        f'and includes the provisional HGAB links. SCR marks {primary["removed"]:,} lines removed. '
        f'{primary["unresolved"]:,} remain unresolved.</p>'
    )
    body += table(
        ['SCR disposition', 'Original GAA comparison pairs', 'Distinct HGAB lines', 'HGAB allocation pesos', 'SCR allocation pesos'],
        [[entry['status'], entry['comparisonPairs'], entry['lines'], f'₱{entry["hgabPesos"]:,}',
          'Unresolved' if entry['scrPesos'] is None else f'₱{entry["scrPesos"]:,}']
         for entry in data['nepLinkedBreakdown']],
    )
    within = data['withinHgab']
    body += '<h3>Other HGAB repeat screens</h3>'
    body += table(['Cohort', 'Distinct HGAB lines', 'Retained in SCR', 'Removed in SCR', 'Unresolved'], [
        [name, cohort['lines'], cohort['retained'], cohort['removed'], cohort['unresolved']]
        for name, cohort in [('HGAB-to-GAA exact-title and place matches', data['directHistorical']),
                             ('Similar line items within HGAB 3rd reading', within)]
    ])
    body += (
        f'<p>Both allocation lines carried forward in {within["bothRetainedPairs"]:,} of the '
        f'{within["pairs"]:,} within-HGAB pairs. The cohorts can overlap. Use the '
        '<a href="#inter-scr">within-SCR screen</a> to review similar titles and segment evidence in the later stage.</p>'
        '<p>The join uses the normalized House title and exact HGAB allocation. A cited House page can resolve '
        'multiple candidates. If several HGAB lines point to one SCR row, the link stays unresolved. '
        'Retained lines include unchanged, renamed, increased and reduced allocations.</p>'
        f'<p><a href="{FILE_NAME}" download>Download the complete HGAB-to-SCR traces and source links (JSON)</a> '
        '· <a href="scr.html#scr-project-comparison">Open the SCR project comparison</a></p>'
    )
    return section('repeat-scr-survival', 'Of the HGAB repeat candidates, how many survived into SCR?', body)
