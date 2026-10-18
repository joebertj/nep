#!/usr/bin/env python3
"""Refresh historical repeat data without replacing the hand-refined DPWH page."""
import csv,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
def build():
    p=STATIC/'dpwh-data.json';d=json.loads(p.read_text());old={(r['source_code'],r['comparison_year'],r['prior_project']):r for r in d['priorityRepeats']};out=[]
    with (ROOT/'analysis_output/priority_program_year_on_year_candidates.csv').open() as f:
        for r in csv.DictReader(f):
            if r['rank']!='1' or float(r['similarity'])<.90:continue
            if r['category']=='Bridge' and r['chainage_status']!='overlap':continue
            x={'category':r['category'],'project':r['name'],'source_code':r['source'],'office':r['office'],'region':r['region'],'amount_2027':int(float(r['amount'])),'comparison_year':int(r['prior_year']),'prior_project':r['prior_name'],'prior_amount':int(float(r['prior_amount'])),'prior_source':r['prior_source'],'similarity_pct':round(float(r['similarity'])*100)}
            for k in ['current_chainage','prior_chainage','chainage_overlap','chainage_status','tranche_status','tranche_detail']:x[k]=r.get(k,'')
            x['tranche_conflict']=r.get('tranche_conflict','False').lower()=='true'
            previous=old.get((x['source_code'],x['comparison_year'],x['prior_project']),{})
            x['congressional_representatives']=previous.get('congressional_representatives',[]);out.append(x)
    out.sort(key=lambda r:(-r['similarity_pct'],r['category'],r['project']))
    d['priorityRepeats']=out;p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    return {'beforePairs':len(old),'afterPairs':len(out)}
if __name__=='__main__':print(json.dumps(build(),indent=2))
