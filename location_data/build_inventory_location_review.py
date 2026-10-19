#!/usr/bin/env python3
"""Retain the inventory-attribution audit without a public progress section."""
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def build():
    old_path=ROOT/'analysis_output/congress_before_inventory_locations.json'
    new_path=ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json'
    if not old_path.exists():return None
    old=json.loads(old_path.read_text());new=json.loads(new_path.read_text())
    previous={r['id']:r for r in old['projects']};current={r['id']:r for r in new['projects']}
    if previous.keys()!=current.keys():raise ValueError('Inventory before/after source IDs differ; review the baseline')
    added=[];changed=[]
    for pid,row in current.items():
        prior=previous[pid]
        if row['projectName']!=prior['projectName'] or row['amountPesos']!=prior['amountPesos']:raise ValueError('Inventory before/after source content differs')
        if prior['districts'] and row['districts']!=prior['districts']:changed.append(pid)
        elif not prior['districts'] and row['status']=='unique':
            added.append(row)
    if changed:raise ValueError('Inventory supplement changed existing districts: '+str(changed))
    groups=defaultdict(lambda:{'lineItems':0,'amountPesos':0,'representatives':set()})
    for row in added:
        g=groups[row['districts'][0]];g['lineItems']+=1;g['amountPesos']+=row['amountPesos'];g['representatives'].update(row['representatives'])
    district_rows=sorted([{'district':k,**v,'representatives':sorted(v['representatives'])} for k,v in groups.items()],key=lambda r:(-r['amountPesos'],r['district']))
    doc={'summary':{'previousUniqueLines':old['summary']['uniquelyAssignedLines'],
        'currentUniqueLines':new['summary']['uniquelyAssignedLines'],'additionalLines':len(added),
        'additionalAttributedPesos':sum(r['amountPesos'] for r in added),'existingAssignedDistrictsChanged':len(changed),
        'previousCoveragePct':old['summary']['strictCoveragePct'],'currentCoveragePct':new['summary']['strictCoveragePct']},
        'methodology':['This is improved geographic attribution of already-extracted budget lines, not additional appropriations or newly discovered insertions.',
            'Exact bridge IDs or full measured road alignments identify physical assets. Their checked extent must remain inside one municipal polygon, with a safety margin.',
            'Inventory municipality/province must agree with geometry. Current local district maps must agree, and PH location DB must resolve the qualified location uniquely.',
            'Old CONG_DIST polygon labels, DEO numbers, similarly named places, representative names and political roles never determine an assignment.',
            'Border-crossing assets, scope contradictions, ambiguous locations, unsupported chainage and the existing multi-place scope hold remain unresolved.',
            'Inventory geometry can be dated. These are screening estimates, not independent official verification of current district boundaries or construction scope.'],
        'districts':district_rows,'projects':added,
        'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [old_path,new_path,ROOT/'analysis_output/inventory_location_evidence.json']]}
    text=json.dumps(doc,ensure_ascii=False,indent=2)+'\n'
    (ROOT/'analysis_output/congress_inventory_location_update.json').write_text(text)
    (STATIC/'congress-inventory-location-update.json').write_text(text)
    fields=['id','projectName','amountPesos','districts','representatives','sourceVolume','sourcePage','geographicEvidence']
    import io
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    writer.writerows({k:json.dumps(r.get(k),ensure_ascii=False) if isinstance(r.get(k),(dict,list)) else r.get(k) for k in fields} for r in added)
    (ROOT/'analysis_output/congress_inventory_location_update.csv').write_text(stream.getvalue())
    (STATIC/'congress-inventory-location-update.csv').write_text(stream.getvalue())
    # Coverage improvements belong to the location DB audit, not the public
    # budget findings. Keep source data and the attribution audit available.
    for path in [STATIC/'congress.html',ROOT/'analysis_output/congress.html']:
        page=path.read_text()
        page=re.sub(r'<section id="inventory-location-method".*?</section>','',page,flags=re.S)
        page=re.sub(r'congress-data\.json\?attribution=[^\x27\"]+', 'congress-data.json?attribution=qualified-location-consensus-v6-inventory-asset-context',page)
        path.write_text(page)
    print(json.dumps(doc['summary'],indent=2))
    return doc

if __name__=='__main__':build()
