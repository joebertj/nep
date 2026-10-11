#!/usr/bin/env python3
"""Trace DEO RCS allocations and retain LEG crosswalks as reference context only."""
import csv
import hashlib
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from location_data.build_database import norm

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def build():
    source=ROOT/'2027.json';comparison=ROOT/'analysis_output/hb_nep_comparison_3rd.csv'
    scenario=STATIC/'rcs-data.json';dbpath=ROOT/'location_data/philippine_locations.sqlite'
    api=json.loads(source.read_text())['data']['data'];bytitle=defaultdict(list)
    for row in api:bytitle[row['projectName']].append(row)
    matches=defaultdict(list)
    with comparison.open() as f:
        for row in csv.DictReader(f):
            if row['paired_one_to_one']=='True':matches[row['nep_api_id']].append(row)
    db=sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[]
    for d in json.loads(scenario.read_text())['districts']:
        candidates=bytitle[d['projectName']]
        if len(candidates)!=1:raise ValueError('Nonunique RCS NEP source title')
        n=candidates[0];links=matches[n['code']]
        if len(links)>1:raise ValueError('Multiple selected counterparts for one RCS line')
        h=links[0] if links else None
        if h and h['comparison']=='Exact normalized title found in NEP':
            status='Retained unchanged' if int(h['amountPesos'])==d['currentPesos'] else 'Retained with allocation adjustment'
        else:status='Potential counterpart' if h else 'No selected counterpart; removal unconfirmed'
        key=norm(d['office'])
        claims=[dict(r) for r in db.execute('SELECT DISTINCT l.jurisdiction,l.designation,s.path,c.status FROM deos d JOIN deo_leg_claims c ON c.deo_id=d.id JOIN leg_districts l ON l.id=c.leg_id JOIN sources s ON s.id=c.source_id WHERE d.name_key=?',(key,))]
        rows.append({'sourceCode':n['code'],'office':d['office'],'provinceProxy':d['province'],'nepTitle':n['projectName'],
                     'nepPesos':d['currentPesos'],'hgabId':h['hgab_id'] if h else None,'hgabTitle':h['projectName'] if h else None,
                     'hgabPesos':int(h['amountPesos']) if h else None,'hgabPage':h['sourcePage'] if h else None,'status':status,
                     'rainfallScenarioUnits':d['recommendedUnits'],'scenarioLostUnit':d['recommendedUnits']==0,
                     'LEGReferenceCandidates':sorted({r['jurisdiction']+' · '+r['designation'] for r in claims}),
                     'LEGReferenceEvidence':claims,'LEGAttribution':'Unresolved: office title does not locate the funded installation.'})
    db.close()
    output={'summary':{'districtOfficeLines':len(rows),'unchangedInHGAB':sum(r['status']=='Retained unchanged' for r in rows),
                       'withoutSelectedCounterpart':sum(r['hgabId'] is None for r in rows),'allocationDecreases':sum(r['hgabPesos'] is not None and r['hgabPesos']<r['nepPesos'] for r in rows),
                       'provinceFirstScenarioZeroUnitOffices':sum(r['scenarioLostUnit'] for r in rows),'confirmedLEGLosses':None},
            'method':'Source-code join to selected native HGAB 3rd links. Loss in actual HGAB is separate from zero units in a hypothetical scenario. Exact DEO crosswalk claims are reference candidates, not site-level LEG attribution.',
            'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [source,comparison,scenario,dbpath]],'rows':rows}
    for path in [ROOT/'analysis_output/rcs_stage_trace.json',STATIC/'rcs-stage-trace.json']:path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    for path in [ROOT/'analysis_output/rcs-stage-trace.csv',STATIC/'rcs-stage-trace.csv']:
        with path.open('w',encoding='utf-8-sig',newline='') as f:
            columns=['sourceCode','office','provinceProxy','nepPesos','hgabPesos','hgabPage','status','rainfallScenarioUnits','scenarioLostUnit','LEGReferenceCandidates','LEGAttribution']
            w=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');w.writeheader()
            w.writerows({**r,'LEGReferenceCandidates':'; '.join(r['LEGReferenceCandidates'])} for r in rows)
    return output

if __name__=='__main__':print(json.dumps(build()['summary'],indent=2))
