#!/usr/bin/env python3
"""Attach a shared, framework-free overlap viewer to generated report tables."""
import csv
import hashlib
import json
import re
from pathlib import Path
from chainage import parse_chainage

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def build():
    records=[];seen=set()
    def add(left,right,left_label,right_label,left_source='',right_source='',required_ids=None,year=None,reject_house_ids=False,row_key=None):
        a,_=parse_chainage(left);b,_=parse_chainage(right)
        intersections=sorted(set((max(x,u),min(y,v)) for x,y in a for u,v in b if min(y,v)>max(x,u)))
        if not intersections:return
        key=(left,right,left_label,right_label,left_source,right_source)
        if key in seen:return
        seen.add(key)
        records.append({'left':left,'right':right,'leftLabel':left_label,'rightLabel':right_label,
                        'leftSource':left_source,'rightSource':right_source,'leftRanges':a,'rightRanges':b,
                        'overlapRanges':intersections,'requiredIds':required_ids or [],'year':year,'rejectHouseIds':reject_house_ids,'rowKey':row_key})
    within=json.loads((OUT/'within_stage_repeats.json').read_text())
    for r in within['pairs']:
        a,b=r['left'],r['right']
        add(a['projectName'],b['projectName'],r['stage']+' · first item',r['stage']+' · second item',
            str(a['id'])+' · p. '+str(a['sourcePage']),str(b['id'])+' · p. '+str(b['sourcePage']),[a['id'],b['id']])
    dpwh=json.loads((STATIC/'dpwh-data.json').read_text())
    for r in dpwh['priorityRepeats']:
        add(r['project'],r['prior_project'],'FY2027 NEP','FY'+str(r['comparison_year'])+' GAA',
            r['source_code'],r['prior_source'],year=r['comparison_year'],reject_house_ids=True,
            row_key=json.dumps([r['source_code'],str(r['comparison_year']),r['prior_source']],ensure_ascii=False,separators=(',',':')))
    queue=json.loads((OUT/'line_item_review_queue.json').read_text())
    for r in queue['rankedOccurrences']:
        for m in r['historicalMatches']:
            add(r['projectName'],m['title'],'FY2027 HGAB 3rd','FY'+str(m['year'])+' GAA',
                r['hgabId']+' · p. '+str(r['sourcePage']),m['source'],[r['hgabId']],m['year'])
    # Include agency historical comparisons when both titles have full ranges.
    for p in OUT.glob('*year_on_year_candidates.csv'):
        if p.name.startswith('priority_'):continue
        with p.open() as f:
            for r in csv.DictReader(f):
                if r.get('chainage_status')!='overlap':continue
                add(r.get('name',''),r.get('prior_name',''),'FY2027 HGAB 3rd','FY'+r.get('prior_year','2025')+' GAA',r.get('source',''),r.get('prior_source',''))
    template=(ROOT/'report_assets/chainage_overlap.js').read_text()
    asset=template.replace('__CHAINAGE_RECORDS__',json.dumps(records,ensure_ascii=False).replace('</','<\\/'))
    (STATIC/'chainage-overlap.js').write_text(asset)
    (OUT/'chainage-overlap.js').write_text(asset)
    version=hashlib.sha256(asset.encode()).hexdigest()[:12]
    for p in STATIC.glob('*.html'):
        text=re.sub(r'<script\b[^>]*id="chainage-overlap-viewer"[^>]*>.*?</script>','',p.read_text(),flags=re.S)
        text=text.replace('</body>',f'<script id="chainage-overlap-viewer" src="chainage-overlap.js?v={version}" defer></script></body>')
        p.write_text(text)
        mirror=OUT/p.name
        if mirror.exists():mirror.write_text(text)
    return {'overlapComparisons':len(records),'pages':len(list(STATIC.glob('*.html')))}

if __name__=='__main__':print(json.dumps(build(),indent=2))
