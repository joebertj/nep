#!/usr/bin/env python3
"""Import dated-unknown boundary evidence without changing accepted memberships."""
import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from build_database import Builder, ROOT, OUT, norm, uid

EVIDENCE = ROOT/'analysis_output/deo_leg_boundary_crosswalk.json'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS boundary_deo_leg_evidence(
 id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),deo_id TEXT REFERENCES deos(id),
 leg_id TEXT REFERENCES leg_districts(id),deo_object_id INTEGER,leg_object_id INTEGER,
 leg_label TEXT,status TEXT,intersection_m2 REAL,deo_fraction REAL,leg_fraction REAL,
 valid_from TEXT,valid_to TEXT,raw_json TEXT);
CREATE INDEX IF NOT EXISTS boundary_crosswalk_deo ON boundary_deo_leg_evidence(deo_id);
CREATE TABLE IF NOT EXISTS boundary_locality_evidence(
 id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),place_id TEXT REFERENCES places(id),
 deo_id TEXT REFERENCES deos(id),leg_id TEXT REFERENCES leg_districts(id),
 province_label TEXT,locality_label TEXT,status TEXT,candidates_json TEXT,raw_json TEXT);
'''

def leg_candidates(db, label):
    match = re.fullmatch(r'(.+?)\s*\(([^()]+)\)',str(label or '').strip())
    if not match:
        return []
    jurisdiction, designation = match.groups()
    words = ['Lone','First','Second','Third','Fourth','Fifth','Sixth','Seventh','Eighth','Ninth','Tenth','Eleventh','Twelfth']
    ordinals = ['Lone','1st','2nd','3rd','4th','5th','6th','7th','8th','9th','10th','11th','12th']
    des = dict(zip([norm(w)+' district' for w in words],[w+' District' for w in ordinals])).get(norm(designation))
    if not des:
        return []
    # Exact jurisdiction first. City-label alternatives are restricted to an
    # explicit city jurisdiction; they do not match an identically named province.
    found = db.execute('SELECT id FROM leg_districts WHERE jurisdiction_key=? AND designation=?',(norm(jurisdiction),des)).fetchall()
    if not found and re.search(r'\bcity\b',jurisdiction,re.I):
        base = re.sub(r'^city of\s+|\s+city$','',jurisdiction,flags=re.I)
        found = db.execute('SELECT id FROM leg_districts WHERE jurisdiction_key=? AND designation=?',(norm('City of '+base),des)).fetchall()
        if not found:
            found = db.execute('SELECT DISTINCT l.id FROM leg_districts l JOIN leg_jurisdiction_claims j ON j.leg_id=l.id JOIN places p ON p.id=j.place_id JOIN aliases a ON a.place_id=p.id WHERE p.level=\'city\' AND a.name_key IN (?,?,?) AND l.designation=?',
                (norm(base),norm(base+' City'),norm('City of '+base),des)).fetchall()
    return sorted({r[0] for r in found})

def ingest(db):
    if not EVIDENCE.exists():
        return None
    db.executescript(SCHEMA)
    builder = Builder(db)
    payload = json.loads(EVIDENCE.read_text())
    sid = builder.source(EVIDENCE,'dpwh_arcgis_boundaries','boundary_overlay',note='Cached boundary overlap, effective dates unknown; not FY2027 attribution or allocation weights.')
    for label, source in payload['sources'].items():
        builder.source(ROOT/source['path'],'dpwh_arcgis_boundaries','boundary_'+label,note=json.dumps(source,ensure_ascii=False))
    db.execute('DELETE FROM boundary_deo_leg_evidence WHERE source_id=?',(sid,))
    db.execute('DELETE FROM boundary_locality_evidence WHERE source_id=?',(sid,))
    unresolved_legs = set()
    for row in payload['pairs']:
        did = builder.deo(row['deo'],sid)
        candidates = leg_candidates(db,row['leg'])
        lid = candidates[0] if len(candidates)==1 else None
        if not lid:
            unresolved_legs.add(row['leg'])
        db.execute('INSERT INTO boundary_deo_leg_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (uid(sid,row['deoObjectId'],row['legObjectId']),sid,did,lid,row['deoObjectId'],row['legObjectId'],row['leg'],row['status'],row['intersectionAreaSquareMeters'],row['deoAreaFraction'],row['legAreaFraction'],None,None,json.dumps(row,ensure_ascii=False)))
    resolved_places = 0
    for row in payload['municipalityLabels']:
        candidates = []
        # Parent-qualified exact aliases only. Do not create or merge identities
        # from unverified municipal codes, province labels or similar names.
        for parent in builder.find(row['province'],('province',)):
            candidates += builder.find(row['municipality'],('city','municipality','locality'),parent)
        candidates = sorted(set(candidates))
        pid = candidates[0] if len(candidates)==1 else None
        resolved_places += bool(pid)
        legs = leg_candidates(db,row['leg'])
        lid = legs[0] if len(legs)==1 else None
        did = builder.deo(row['deo'],sid) if row['deo'] else None
        db.execute('INSERT INTO boundary_locality_evidence VALUES(?,?,?,?,?,?,?,?,?,?)',
            (uid(sid,'municipality',row['objectId']),sid,pid,did,lid,row['province'],row['municipality'],row['status'],json.dumps(candidates),json.dumps(row,ensure_ascii=False)))
    summary = {'boundarySummary':payload['summary'],'municipalLabels':len(payload['municipalityLabels']),
        'uniqueExistingPlaceMatches':resolved_places,'unresolvedLegLabels':sorted(unresolved_legs),
        'referencePairsAlsoOverlapping':db.execute("SELECT COUNT(*) FROM deo_leg_claims c WHERE EXISTS(SELECT 1 FROM boundary_deo_leg_evidence e WHERE e.deo_id=c.deo_id AND e.leg_id=c.leg_id AND e.status='spatial_overlap_dates_unverified')").fetchone()[0],
        'referencePairsWithoutSubstantialBoundaryMatch':[dict(r) for r in db.execute("SELECT DISTINCT d.name AS deo,l.jurisdiction,l.designation FROM deo_leg_claims c JOIN deos d ON d.id=c.deo_id JOIN leg_districts l ON l.id=c.leg_id WHERE NOT EXISTS(SELECT 1 FROM boundary_deo_leg_evidence e WHERE e.deo_id=c.deo_id AND e.leg_id=c.leg_id AND e.status='spatial_overlap_dates_unverified')")],
        'policy':'Evidence tables only. Existing memberships, project allocations and public rankings unchanged.'}
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=OUT/'philippine_locations.sqlite')
    args=parser.parse_args();temp=args.database.with_suffix('.boundary-import.sqlite')
    with sqlite3.connect(args.database) as src,sqlite3.connect(temp) as dst:
        src.backup(dst)
    db=sqlite3.connect(temp);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON')
    summary=ingest(db)
    if summary is None:
        raise FileNotFoundError(EVIDENCE)
    db.commit()
    if db.execute('PRAGMA foreign_key_check').fetchone() or db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise ValueError('Database integrity failure')
    db.close();os.replace(temp,args.database)
    (OUT/'boundary_import_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
