#!/usr/bin/env python3
"""Refresh the public bridge-ID → DEO / LEG context without spatial dependencies."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from location_data.bridge_district_contexts import build_contexts
from location_data.enrich_report_tables import PHLocations, STATIC

def main():
    projects={}
    for source in [ROOT/'hb10858_3rd_dpwh_projects.json',ROOT/'2027.json']:
        data=json.loads(source.read_text())
        for row in data['data']['data']:
            title=row.get('projectName')
            if title:projects.setdefault(title,row)
    bridge_path=next((ROOT/'data_sources/arcgis_dpwh/archive/selected/bridge_inventory').glob('layers/*/features.jsonl'))
    bridges=[json.loads(line) for line in bridge_path.open()]
    contexts,counts=build_contexts(projects,bridges,PHLocations().seats)
    evidence_path=ROOT/'analysis_output/inventory_location_evidence.json'
    evidence=json.loads(evidence_path.read_text())
    evidence['schemaVersion']=2
    evidence['bridgeDistrictContexts']=contexts
    evidence['summary'].update(counts)
    bridge_methodology=[
        'An exact bridge ID can link a project title to the ArcGIS bridge record, which lists both DEO and CONG_DIST.',
        'A bridge-record CONG_DIST is used only when title geography does not independently resolve and the label maps to exactly one current LEG roster entry. When sources disagree, the title-based result is retained.',
        'The DEO is the bridge record’s source-listed office; a DEO is not assumed to map to one LEG because a DEO may cover multiple legislative districts.'
    ]
    evidence['methodology']=[line for line in evidence.get('methodology',[])
        if 'CONG_DIST and DEO labels are never used' not in line and line not in bridge_methodology]
    evidence['methodology'][:0]=bridge_methodology
    evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    public={k:evidence[k] for k in ['schemaVersion','mapHashes','hierarchySha256','methodology','summary','sources','contexts','bridgeDistrictContexts']}
    target=STATIC.parent/'data/inventory_location_contexts.json'
    target.write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'bridgeProjectsConsidered':len(projects),'sourceContexts':len(contexts),'counts':counts},indent=2))

if __name__=='__main__':main()
