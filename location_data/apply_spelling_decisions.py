#!/usr/bin/env python3
"""Apply user-confirmed spelling variants to existing place identities, keeping all parents."""
import argparse
import json
import re
import sqlite3
from pathlib import Path
from build_database import Builder,norm
ROOT=Path(__file__).resolve().parent

def apply(con):
    path=ROOT/'name_spelling_decisions.json';b=Builder(con)
    sid=b.source(path,'human_spelling_review','user_confirmed_name_variants',note='Spelling equivalence only; no place merging, location inference or boundary assignment.')
    report=[]
    for decision in json.loads(path.read_text())['decisions']:
        keys={norm(v) for v in decision['variants']};places=set()
        for r in con.execute("SELECT DISTINCT p.id,a.name_key FROM places p JOIN aliases a ON a.place_id=p.id WHERE p.level IN ('barangay','municipality','locality','city')"):
            bare=re.sub(r'^(?:barangay|brgy\.?|bgy\.?)\s+','',r['name_key'])
            if bare in keys:places.add(r['id'])
        before=con.total_changes
        for pid in sorted(places):
            for variant in decision['variants']:
                b.alias(pid,variant,sid,'user_confirmed_spelling_variant')
                if con.execute('SELECT level FROM places WHERE id=?',(pid,)).fetchone()[0]=='barangay':
                    for prefix in ['Barangay ','Brgy. ']:b.alias(pid,prefix+variant,sid,'user_confirmed_marked_spelling_variant')
        report.append({'decision':decision['id'],'existingPlaceIdentities':len(places),'aliasesAdded':con.total_changes-before})
    # Resolve the spelling question only; the actual geographic classification remains separate.
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='location_review_queue'").fetchone():
        for decision in json.loads(path.read_text())['decisions']:
            for variant in decision['variants']:
                con.execute("UPDATE location_review_queue SET status='spelling_user_classified_location_pending',decision_json=? WHERE kind='unrecognized_marked_place' AND mention=?",(json.dumps(decision,ensure_ascii=False),norm(variant)))
    return {'decisions':report,'placeMerges':0,'boundaryAssignments':0,'publicAllocationChanges':0}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--database',type=Path,default=ROOT/'philippine_locations.sqlite');args=p.parse_args()
    temporary=args.database.with_suffix('.spelling.sqlite')
    with sqlite3.connect(args.database) as src,sqlite3.connect(temporary) as dst:src.backup(dst)
    con=sqlite3.connect(temporary);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON');summary=apply(con);con.commit()
    if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Spelling import foreign key integrity failure')
    con.close();temporary.replace(args.database)
    (ROOT/'spelling_decision_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
