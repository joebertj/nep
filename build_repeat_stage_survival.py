#!/usr/bin/env python3
"""Trace NEP repeat-screen proposals to current selected HGAB 3rd-reading links."""
import csv
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def build():
    repeat_path=STATIC/'dpwh-data.json';match_path=ROOT/'analysis_output/hb_nep_comparison_3rd.csv'
    api_path=ROOT/'2027.json'
    repeats=json.loads(repeat_path.read_text())['priorityRepeats']
    api={r['code']:r for r in json.loads(api_path.read_text())['data']['data']}
    selected=defaultdict(list);candidates=defaultdict(list)
    with match_path.open() as f:
        for row in csv.DictReader(f):
            code=row['nep_api_id']
            if not code:continue
            if row['paired_one_to_one']=='True':selected[code].append(row)
            else:candidates[code].append(row)
    unique={}
    for r in repeats:
        code=r['source_code']
        if code not in api:raise ValueError(f'Repeat source code absent from original NEP extract: {code}')
        if code in unique:continue
        links=selected[code]
        if len(links)>1:raise ValueError(f'Multiple selected HGAB links for one NEP occurrence: {code}')
        if links:
            h=links[0]
            status='Clear retained link' if h['comparison']=='Exact normalized title found in NEP' else 'Potential retained link'
        else:
            h=None;status='Unselected counterpart requires review' if candidates[code] else 'No selected or cited counterpart'
        unique[code]={'sourceCode':code,'nepTitle':r['project'],'nepPesos':r['amount_2027'],'category':r['category'],
                      'status':status,'hgabId':h['hgab_id'] if h else None,'hgabTitle':h['projectName'] if h else None,
                      'hgabPesos':int(h['amountPesos']) if h else None,'nepPage':h['nep_source_page'] if h else None,
                      'hgabPage':h['sourcePage'] if h else None,'chainageStatus':h['chainage_status'] if h else None,
                      'trancheStatus':h['tranche_status'] if h else None,
                      'unselectedCandidateIds':[c['hgab_id'] for c in candidates[code]]}
    pair_counts=Counter(unique[r['source_code']]['status'] for r in repeats)
    counts=Counter(r['status'] for r in unique.values())
    groups=[]
    for status in ['Clear retained link','Potential retained link','Unselected counterpart requires review','No selected or cited counterpart']:
        rows=[r for r in unique.values() if r['status']==status]
        groups.append({'status':status,'comparisonPairs':pair_counts[status],'uniqueNEPProposals':len(rows),
                       'nepPesos':sum(r['nepPesos'] for r in rows),'selectedHgabPesos':sum(r['hgabPesos'] or 0 for r in rows) if 'retained' in status else None})
    if sum(counts.values())!=len(unique) or sum(pair_counts.values())!=len(repeats):raise ValueError('Survival status partition failure')
    output={'method':'Join repeat source_code to the NEP API code carried by the current native HGAB comparison. Selected one-to-one links only establish retention classes. Closest unselected candidates do not establish survival. Missing links do not certify removal.',
            'scope':'FY2027 DPWH NEP repeat candidates compared with HGAB 3rd reading; historical GAA comparison pairs retained as separate occurrences.',
            'summary':{'comparisonPairs':len(repeats),'uniqueNEPProposals':len(unique),'pairStatuses':dict(pair_counts),'uniqueStatuses':dict(counts)},
            'groups':groups,'proposals':list(unique.values()),
            'comparisonPairs':[{**r,'hgabRetention':unique[r['source_code']]} for r in repeats],
            'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [repeat_path,match_path,api_path]]}
    for p in [ROOT/'analysis_output/repeat_nep_hgab_survival.json',STATIC/'repeat-nep-hgab-survival.json']:
        p.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    for name,rows,columns in [('repeat-nep-hgab-proposals.csv',list(unique.values()),['sourceCode','nepTitle','nepPesos','category','status','hgabId','hgabTitle','hgabPesos','nepPage','hgabPage','chainageStatus','trancheStatus'])]:
        for path in [STATIC/name,ROOT/'analysis_output'/name]:
            with path.open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader();w.writerows(rows)
    print(json.dumps(output['summary'],indent=2))
    return output


def render(data):
    from build_investigation_summary import esc, section, table

    summary = data['summary']
    groups = data['groups']
    pair_count = summary['comparisonPairs']
    proposal_count = summary['uniqueNEPProposals']
    clear_pairs = summary['pairStatuses'].get('Clear retained link', 0)
    clear_proposals = summary['uniqueStatuses'].get('Clear retained link', 0)
    body = (
        f'<p>The historical NEP screen contains {pair_count:,} GAA comparisons for {proposal_count:,} distinct proposals. '
        f'<strong>{clear_pairs:,} comparisons representing {clear_proposals:,} proposals</strong> have a clear selected '
        'counterpart in HGAB 3rd reading.</p>'
    )

    colors = ('#0038A8', '#b65b09', '#777', '#355b92')
    body += (
        f'<svg class="evidence-graphic" viewBox="0 0 850 340" role="img" '
        f'aria-label="HGAB retention classes for {pair_count:,} comparison pairs and {proposal_count:,} distinct proposals">'
    )
    peak = max(pair_count, proposal_count, 1)
    for x, field, total, label in [
        (95, 'comparisonPairs', pair_count, 'Comparison pairs'),
        (250, 'uniqueNEPProposals', proposal_count, 'Distinct proposals'),
    ]:
        y = 280
        for group, color in zip(groups, colors):
            count = group[field]
            height = 220 * count / peak
            if height:
                y -= height
                body += (
                    f'<rect x="{x}" y="{y:.2f}" width="86" height="{height:.2f}" fill="{color}">'
                    f'<title>{esc(group["status"])} · {count:,}</title></rect>'
                )
        body += (
            f'<text x="{x + 43}" y="{y - 8:.2f}" text-anchor="middle">{total:,}</text>'
            f'<text x="{x + 43}" y="305" text-anchor="middle">{label}</text>'
        )
    for i, (group, color) in enumerate(zip(groups, colors)):
        y = 76 + 34 * i
        body += (f'<rect x="405" y="{y - 12}" width="14" height="14" fill="{color}"/>'
                 f'<text x="432" y="{y}">{esc(group["status"])}</text>')
    body += '</svg>'
    body += table(
        ['HGAB retention class', 'Original GAA comparison pairs', 'Distinct NEP proposals',
         'Original NEP allocation pesos', 'Selected HGAB allocation pesos'],
        [[group['status'], group['comparisonPairs'], group['uniqueNEPProposals'], f'₱{group["nepPesos"]:,}',
          'No selected allocation' if group['selectedHgabPesos'] is None else f'₱{group["selectedHgabPesos"]:,}']
         for group in groups],
    )
    body += (
        '<p>Each historical comparison counts once. A proposal with several matches contributes one distinct proposal. '
        'Clear retention uses the selected scope-compatible title link. Potential links remain provisional. '
        'Projects without a selected counterpart need source review before assigning a disposition.</p>'
        f'<p><a class="export-btn" href="repeat-nep-hgab-proposals.csv" download>Export all {proposal_count:,} proposal traces CSV</a> '
        '· <a href="repeat-nep-hgab-survival.json">Full pair and proposal evidence JSON</a></p>'
    )
    return section('repeat-hgab-survival', 'Of the NEP repeat candidates, how many survived into HGAB?', body)

if __name__=='__main__':build()
