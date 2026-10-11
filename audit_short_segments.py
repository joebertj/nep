#!/usr/bin/env python3
"""Audit short-length denominators and high-rate display selection against PDFs."""
import json
import hashlib
import statistics
import subprocess
import tempfile
from pathlib import Path
from hgab_native import page_boxes, visible_rows
from hgab_matching import normalize

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'


def build():
    data=json.loads((OUT/'cost_per_km.json').read_text())
    stats=[]
    samples=[]
    for category in ['Roads','Bridges','FMR','Mixed roads / bridges']:
        all_rows=[r for r in data['projects'] if r['category']==category]
        known=[r for r in all_rows if r['lengthMeters'] is not None]
        top=sorted([r for r in known if r['allocationPerStatedMeter'] is not None],key=lambda r:-r['allocationPerStatedMeter'])[:25]
        stats.append({'category':category,'allLines':len(all_rows),'knownLengths':len(known),
                      'below100m':sum(r['lengthMeters']<100 for r in known),
                      'below100PctOfKnown':round(100*sum(r['lengthMeters']<100 for r in known)/len(known),2) if known else None,
                      'medianMeters':statistics.median(r['lengthMeters'] for r in known) if known else None,
                      'top25HighRateRows':len(top),'below100InTop25HighRates':sum(r['lengthMeters']<100 for r in top),
                      'bins':{label:sum(low<=r['lengthMeters']<high for r in known) for label,low,high in
                              [('<10m',0,10),('10–<100m',10,100),('100–<1,000m',100,1000),('1,000–<5,000m',1000,5000),('≥5,000m',5000,float('inf'))]}})
        if category in ['Roads','Bridges']:
            samples.extend(sorted(known,key=lambda r:r['lengthMeters'])[:3])
    boxes={}
    evidence=[]
    with tempfile.TemporaryDirectory(prefix='short-segment-audit-') as directory:
        for r in samples:
            pdf=ROOT/'HB 10858 FOR 3RD READING'/r['sourceVolume']
            if pdf not in boxes:boxes[pdf]=page_boxes('gs',pdf)
            page=int(r['sourcePage']);output=Path(directory)/f'{page}.xml'
            subprocess.run(['gs','-q','-dNOPAUSE','-dBATCH','-dTextFormat=1','-sDEVICE=txtwrite',
                            f'-dFirstPage={page}',f'-dLastPage={page}',f'-sOutputFile={output}',str(pdf)],
                           capture_output=True,check=True)
            rows,_=visible_rows(output.read_text(),boxes[pdf][page-1])
            visible=' '.join(row['title'] for row in rows)
            matched=normalize(r['projectName']) in normalize(visible)
            # Preserve actual visible fragments around the title, not merely
            # the current extracted title being checked.
            words=r['projectName'].split(',')[0][:45].lower()
            fragments=[row['title'] for row in rows]
            hit=next((i for i,t in enumerate(fragments) if words in t.lower()),None)
            evidence.append({'id':r['id'],'projectName':r['projectName'],'sourceVolume':r['sourceVolume'],
                             'sourcePage':page,'lengthMeters':r['lengthMeters'],
                             'fullTitlePresentInVisiblePDFText':matched,
                             'amountPesos':r['amountPesos'],
                             'allocationPresentOnPDFPage':any(v.get('amount')==r['amountPesos'] for v in rows),
                             'visibleFragments':fragments[max(0,hit-1):hit+6] if hit is not None else [],
                             'limit':'Visible PDF text check verifies printed notation, not the engineering meaning, intended funded extent or absence of source-document errors.'})
    audit={'categories':stats,'sourceChecks':evidence,
           'conclusion':'Most known road segments are not below 100m. High allocation-per-meter sorting selects short denominators. Most known bridge segments are below 100m, which alone is not an abnormal bridge-length finding.',
           'summaryDecision':'A ninth finding may document verified very short printed road ranges, not a majority-short-road claim or certified physical lengths. Printed notation requires engineering clarification.',
           'comparisonCsvSha256':hashlib.sha256((OUT/'hb_nep_comparison_3rd.csv').read_bytes()).hexdigest()}
    (OUT/'short_segment_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    (ROOT.parent/'open-data-visualization/static/nep-preview/short-segment-audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    return audit

if __name__=='__main__':
    d=build();print(json.dumps({'categories':d['categories'],'checked':len(d['sourceChecks']),
                              'visibleTitleAgreement':sum(r['fullTitlePresentInVisiblePDFText'] for r in d['sourceChecks'])},indent=2))
