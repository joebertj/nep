#!/usr/bin/env python3
"""Local overpass comparators, retaining stage, source, units and scope limits."""
import csv,json,re
from pathlib import Path
from analyze_priority_repeats import query
from build_cost_per_km import lengths
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output';ODV=ROOT.parent/'open-data-visualization'
TERM=re.compile(r'over\s*pass|flyover',re.I)

def build():
    rows=[]
    def add(title,amount,stage,source):
        if not TERM.search(title) or amount<=0:return
        km,status,method,_=lengths(title)
        meters=km*1000 if km else None
        pedestrian=bool(re.search(r'pedestrian|foot[ -]?bridge',title,re.I))
        rows.append({'title':title,'allocationPesos':int(amount),'stage':stage,'source':source,
            'statedMeters':meters,'allocationPerStatedMeter':round(amount/meters,2) if meters else None,
            'lengthStatus':status,'lengthMethod':method,'pedestrianExplicit':pedestrian,
            'workType':'Rehabilitation/repair' if re.search(r'rehab|repair|retrofit',title,re.I) else 'Construction stated' if re.search(r'\bconstruction\b',title,re.I) else 'Work type not explicit in title'})
    with (OUT/'hb_nep_comparison_3rd.csv').open() as f:
        for r in csv.DictReader(f):add(r['projectName'],int(r['amountPesos']),'FY2027 HGAB 3rd',r['sourceVolume']+' · p. '+r['sourcePage']+' · '+r['hgab_id'])
    for r in json.loads((OUT/'nep_dpwh_baseline.json').read_text())['data']['data']:
        add(r['projectName'],r['amountPesos'],'FY2027 NEP',r['id']+' · p. '+str(r['sourcePage']))
    for year in range(2020,2026):
        p=ODV/f'data/parquet/budget_{year}.parquet'
        if not p.exists():continue
        for r in query(f"SELECT id,description,amount,source_file FROM read_parquet('{p}') WHERE department_desc ILIKE '%Public Works%' AND regexp_matches(description,'(?i)over\\s*pass|flyover')"):
            add(r['description'],float(r['amount'] or 0)*1000,f'FY{year} GAA',str(r['source_file'])+' · row '+str(r['id'])+' · amount converted from thousands')
    p=ODV/'data/parquet/parsed_dpwh_2026.parquet'
    for r in query(f"SELECT _excel_row,col_J,amount FROM read_parquet('{p}') WHERE regexp_matches(col_J,'(?i)over\\s*pass|flyover')"):
        add(r['col_J'],float(r['amount'] or 0),'FY2026 GAA','DPWH enacted schedule · Excel row '+str(r['_excel_row']))
    comparable=[r for r in rows if not r['pedestrianExplicit'] and r['statedMeters'] is not None]
    comparable.sort(key=lambda r:(abs(r['statedMeters']-25),r['stage'],r['allocationPesos']))
    data={'target':'Burol Overpass rehabilitation · 25 stated meters · HGAB allocation ₱150M',
        'closestLengthCandidates':comparable,'allOverpassOccurrences':rows,
        'limits':['No pedestrian overpasses in the nearest-length candidate list. Absence of pedestrian wording does not independently authenticate vehicle use.',
            'Station differences are stated intervals, not verified bridge spans. Width, lanes, foundations, approaches, utilities and funding phase remain unknown.',
            'NEP and HGAB occurrences can be the same project at two stages; do not treat them as independent peers. GAA allocations are annual appropriations, not certified full construction costs.',
            'Search is confined to locally available DPWH descriptions and project titles. GAA 2020–2025 generic files may lack detailed station information.']}
    (OUT/'burol_overpass_comparators.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return data
if __name__=='__main__':
    d=build();print(json.dumps({'occurrences':len(d['allOverpassOccurrences']),'nearest':d['closestLengthCandidates'][:12],
        'burolHistory':[r for r in d['allOverpassOccurrences'] if re.search(r'burol|borol',r['title'],re.I)]},ensure_ascii=False,indent=2))
