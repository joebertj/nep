#!/usr/bin/env python3
"""Record changes between two strict congressional attribution builds."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before',type=Path,required=True)
    parser.add_argument('--after',type=Path,default=ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json')
    parser.add_argument('--out',type=Path,default=ROOT/'analysis_output/congress_balanced_metadata_changes.json')
    args=parser.parse_args()
    before={r['id']:r for r in json.loads(args.before.read_text())['projects']}
    after={r['id']:r for r in json.loads(args.after.read_text())['projects']}
    if before.keys()!=after.keys():raise ValueError('Allocation inventory changed; cannot isolate attribution changes')
    added=[];removed=[];reassigned=[];shared=[]
    for key,row in after.items():
        old=before[key]
        if row['amountPesos']!=old['amountPesos'] or row['projectName']!=old['projectName']:
            raise ValueError('Source allocation/title changed; cannot isolate attribution changes')
        entry={'id':key,'projectName':row['projectName'],'amountPesos':row['amountPesos'],
               'beforeStatus':old['status'],'afterStatus':row['status'],
               'beforeDistricts':old['districts'],'afterDistricts':row['districts'],'evidence':row.get('evidence',[])}
        if row['status']=='unique' and old['status']!='unique':added.append(entry)
        elif old['status']=='unique' and row['status']!='unique':removed.append(entry)
        elif old['status']=='unique' and row['status']=='unique' and old['districts']!=row['districts']:reassigned.append(entry)
        elif old['status']!=row['status'] or old['districts']!=row['districts']:shared.append(entry)
    summary={'newStrictLines':len(added),'newStrictPesos':sum(r['amountPesos'] for r in added),
             'lostStrictLines':len(removed),'lostStrictPesos':sum(r['amountPesos'] for r in removed),
             'changedAcceptedDistrictLines':len(reassigned),'otherChangedLines':len(shared)}
    output={'summary':summary,'newStrict':sorted(added,key=lambda r:-r['amountPesos']),
            'lostStrict':removed,'changedAcceptedDistrict':reassigned,'otherChanges':shared,
            'sources':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [args.before,args.after]]}
    args.out.write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
