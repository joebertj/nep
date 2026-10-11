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

if __name__=='__main__':build()
