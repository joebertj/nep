#!/usr/bin/env python3
"""Reconcile an external office-filter export with native HGAB, local NEP matching and strict LEG geography."""
import argparse
import csv
import hashlib
import json
from collections import Counter,defaultdict
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from hgab_matching import normalize,UNMATCHED

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--external',type=Path,default=ROOT/'analysis_output/dpwh-projects-filtered.json');parser.add_argument('--leg',default='Nueva Ecija · 1st District');parser.add_argument('--out',type=Path,default=ROOT/'analysis_output/mika_external_100_reconciliation.json');args=parser.parse_args()
    native_path=ROOT/'hb10858_3rd_dpwh_projects.json';match_path=ROOT/'analysis_output/hb_nep_comparison_3rd.csv';geo_path=ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json'
    native=json.loads(native_path.read_text())['data']['data'];index=defaultdict(list)
    for r in native:index[normalize(r['projectName']),r['amountPesos'],r['sourcePage']].append(r)
    with match_path.open() as f:comparison={r['hgab_id']:r for r in csv.DictReader(f)}
    geographic=json.loads(geo_path.read_text())['projects'];geo={r['id']:r for r in geographic};reports=[]
    external=json.loads(args.external.read_text())
    for r in external['rows']:
        source=r.get('third') or r['second'];hits=index[normalize(source['title']),source['amount_php'],source['pdf_page']]
        if len(hits)!=1:reports.append({'externalTitle':r['title'],'sourceLookup':'unresolved or nonunique'});continue
        h=hits[0];c=comparison[h['id']];g=geo[h['id']]
        reports.append({'id':h['id'],'title':h['projectName'],'amountPesos':h['amountPesos'],'externalOffice':source['office'],
            'status':c['comparison'],'nepId':c['nep_id'],'nepTitle':c['closest_nep_title'],'nepPesos':c['closest_nep_amount_pesos'],
            'geographicStatus':g['status'],'districts':g['districts'],'sourcePage':h['sourcePage']})
    assigned=[r for r in geographic if r['status']=='unique' and r['districts']==[args.leg]]
    inserted=[r for r in assigned if comparison[r['id']]['comparison']==UNMATCHED]
    summary={'externalRows':len(reports),'externalAllocationPesos':sum(r.get('amountPesos',0) for r in reports),
        'comparisonStatuses':dict(Counter(r.get('status','unresolved source') for r in reports)),
        'LEGStatuses':dict(Counter('; '.join(r.get('districts',[])) or 'Unresolved' for r in reports)),
        'requestedLEG':args.leg,'requestedLEGExternalInsertionRows':sum(r.get('districts')==[args.leg] and r.get('status')==UNMATCHED for r in reports),
        'requestedLEGAllAssignedHGABRows':len(assigned),'requestedLEGAllAssignedHGABPesos':sum(r['amountPesos'] for r in assigned),
        'requestedLEGInsertionRows':len(inserted),'requestedLEGInsertionPesos':sum(r['amountPesos'] for r in inserted)}
    output={'method':'Exact normalized full title + HGAB allocation + physical PDF page. The external DEO filter is not treated as LEG attribution. No external match labels are adopted.',
            'summary':summary,'rows':reports,'requestedLEGInsertions':inserted,
            'sources':[{'file':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.external,native_path,match_path,geo_path]]}
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    with args.out.with_suffix('.csv').open('w',encoding='utf-8-sig',newline='') as f:
        cols=['id','title','amountPesos','externalOffice','status','nepId','nepTitle','nepPesos','geographicStatus','districts','sourcePage']
        w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows([{**r,'districts':'; '.join(r.get('districts',[]))} for r in reports])
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
