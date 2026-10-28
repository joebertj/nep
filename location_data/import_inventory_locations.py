#!/usr/bin/env python3
"""Persist screened asset locations in PH location DB; not municipal memberships."""
import json
import os
import sqlite3
from build_database import Builder, ROOT, OUT, uid, norm

EVIDENCE=ROOT/'analysis_output/inventory_location_evidence.json'

def ingest(db):
    if not EVIDENCE.exists():return None
    db.execute('''CREATE TABLE IF NOT EXISTS inventory_location_contexts(
        id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),title_key TEXT UNIQUE,
        original_title TEXT,place_id TEXT REFERENCES places(id),leg_id TEXT REFERENCES leg_districts(id),
        status TEXT,valid_from TEXT,valid_to TEXT,raw_json TEXT)''')
    b=Builder(db);data=json.loads(EVIDENCE.read_text())
    sid=b.source(EVIDENCE,'dpwh_inventory_asset_locations','screened_physical_asset_context',
        note='Exact assets and full municipal containment; current local-map screening. Not official boundary verification or historic officeholder evidence.')
    db.execute('DELETE FROM inventory_location_contexts WHERE source_id=?',(sid,))
    for title,row in data['contexts'].items():
        places=[]
        for parent in b.find(row['province'],('province',)):
            places+=b.find(row['municipality'],('municipality','locality','city'),parent)
        places=sorted(set(places))
        jurisdiction,designation=row['seatKeys'][0]
        lid=b.leg(jurisdiction,designation,sid,title)
        db.execute('INSERT INTO inventory_location_contexts VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid(sid,title),sid,title,row['originalTitle'],places[0] if len(places)==1 else None,lid,
             'screened_asset_context_current_map_consensus',None,None,json.dumps(row,ensure_ascii=False)))
    db.execute('''CREATE TABLE IF NOT EXISTS bridge_district_contexts(
        id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),title_key TEXT,
        bridge_id TEXT,arcgis_object_id INTEGER,deo_id TEXT REFERENCES deos(id),
        leg_id TEXT REFERENCES leg_districts(id),arcgis_deo TEXT,arcgis_cong_dist TEXT,
        status TEXT,raw_json TEXT)''')
    bridge_path=next((ROOT/'data_sources/arcgis_dpwh/archive/selected/bridge_inventory').glob('layers/*/features.jsonl'))
    bridge_sid=b.source(bridge_path,'dpwh_arcgis_bridge_inventory','bridge_record_deo_cong_dist',
        note='Exact bridge-ID join to an ArcGIS row listing DEO and CONG_DIST. Source labels can be outdated or conflict with title geography; not a general one-to-one DEO-to-LEG membership.')
    db.execute('DELETE FROM bridge_district_contexts WHERE source_id=?',(bridge_sid,))
    bridge_rows=data.get('bridgeDistrictContexts',{})
    for title,row in bridge_rows.items():
        jurisdiction,designation=row['seatKeys'][0]
        did=b.deo(row['deo'],bridge_sid)
        lid=b.leg(jurisdiction,designation,bridge_sid,title)
        db.execute('INSERT INTO bridge_district_contexts VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (uid(bridge_sid,title),bridge_sid,title,row['bridgeId'],row.get('objectId'),did,lid,
             row['deo'],row['congDist'],'source_field_maps_to_current_leg_roster',json.dumps(row,ensure_ascii=False)))
    return {'supportedTitles':len(data['contexts']),'bridgeDistrictContexts':len(bridge_rows),
        'additionalHGABCandidates':data['summary']['additionalHGABOccurrences'],
        'policy':'Project-specific geographic evidence, not replacement LEG boundaries or ownership. A bridge DEO and LEG pair is recorded per exact bridge row, not generalized as one LEG per DEO.'}

def main():
    target=OUT/'philippine_locations.sqlite';temp=target.with_suffix('.asset-import.sqlite')
    with sqlite3.connect(target) as src,sqlite3.connect(temp) as dst:src.backup(dst)
    db=sqlite3.connect(temp);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
    summary=ingest(db)
    if summary is None:raise FileNotFoundError(EVIDENCE)
    db.commit()
    if db.execute('PRAGMA foreign_key_check').fetchone() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise ValueError('PH location DB integrity failure')
    db.close();os.replace(temp,target)
    (OUT/'inventory_location_import_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
