#!/usr/bin/env python3
"""Build contextual lookup and province-transition review records from local source claims."""
import argparse
import json
import re
import sqlite3
from pathlib import Path
from build_database import norm,uid
ROOT=Path(__file__).resolve().parent
SQL='''
CREATE TABLE IF NOT EXISTS administrative_transition_review(
 id TEXT PRIMARY KEY,predecessor_id TEXT REFERENCES places(id),successor_id TEXT REFERENCES places(id),
 relation TEXT NOT NULL,valid_from TEXT,valid_to TEXT,status TEXT NOT NULL,
 evidence_json TEXT NOT NULL,review_note TEXT NOT NULL);
CREATE VIEW IF NOT EXISTS qualified_alias_candidates AS
 SELECT a.name_key,p.id place_id,p.name,p.level,p.parent_id,parent.name parent_name,parent.level parent_level,
 province.id province_id,province.name province_name
 FROM aliases a JOIN places p ON p.id=a.place_id
 LEFT JOIN places parent ON parent.id=p.parent_id
 LEFT JOIN places grandparent ON grandparent.id=parent.parent_id
 LEFT JOIN places province ON province.id=CASE WHEN p.level='province' THEN p.id
 WHEN parent.level='province' THEN parent.id WHEN grandparent.level='province' THEN grandparent.id END
 GROUP BY a.name_key,p.id;
CREATE VIEW IF NOT EXISTS alias_ambiguity_review AS
 SELECT name_key,COUNT(DISTINCT place_id) candidate_places,COUNT(DISTINCT level) geographic_levels,
 COUNT(DISTINCT province_id) provinces,COUNT(DISTINCT parent_id) parent_contexts
 FROM qualified_alias_candidates GROUP BY name_key HAVING COUNT(DISTINCT place_id)>1;
'''

def refine(con):
    con.executescript(SQL)
    from apply_spelling_decisions import apply
    spelling=apply(con)
    # Keep proposed relations separate from aliases and dated administrative claims.
    con.execute("DELETE FROM administrative_transition_review WHERE relation='candidate_directional_split' AND status='unresolved_dates_and_legal_lineage'")
    provinces={norm(r['name']):dict(r) for r in con.execute("SELECT * FROM places WHERE level='province'")}
    for name,row in provinces.items():
        m=re.fullmatch(r'(.+?) del (?:norte|sur)',name)
        if not m or m[1] not in provinces:continue
        old=provinces[m[1]]
        evidence=[]
        for p,role in [(old,'possible predecessor'),(row,'possible successor')]:
            for c in con.execute('SELECT s.path,s.sha256,s.family,c.locator,c.claimed_level FROM place_claims c JOIN sources s ON s.id=c.source_id WHERE c.place_id=? ORDER BY s.path,c.locator',(p['id'],)):
                evidence.append(dict(c,place_id=p['id'],name=p['name'],role=role))
        con.execute('INSERT OR IGNORE INTO administrative_transition_review VALUES(?,?,?,?,?,?,?,?,?)',
                    (uid('transition_review',old['id'],row['id']),old['id'],row['id'],'candidate_directional_split',None,None,
                     'unresolved_dates_and_legal_lineage',json.dumps(evidence,ensure_ascii=False),
                     'Exact base-name relationship in local province claims only. Not proof of a split, effective date, municipality transfer or LEG continuity. Never use as an alias or allocation crosswalk.'))
    summary={'spellingDecisions':spelling,'shortMarkedAliasRule':'Names shorter than four characters require an explicit geographic marker; unmarked numbers never identify barangays.',
             'ambiguousAliasKeys':con.execute('SELECT count(*) FROM alias_ambiguity_review').fetchone()[0],
             'transitionReview':[dict(r) for r in con.execute('SELECT t.id,p.name predecessor,c.name successor,t.relation,t.valid_from,t.valid_to,t.status,t.review_note FROM administrative_transition_review t JOIN places p ON p.id=t.predecessor_id JOIN places c ON c.id=t.successor_id ORDER BY p.name,c.name')],
             'automaticBoundaryTransfers':0,'automaticPlaceMerges':0,'publicAllocationChanges':0}
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='gaa_location_mentions'").fetchone():
        summary['historicalProvinceMentionYears']={}
        for name in ['Maguindanao','Maguindanao del Norte','Maguindanao del Sur','Compostela Valley','Davao de Oro','Shariff Kabunsuan']:
            summary['historicalProvinceMentionYears'][name]=[dict(r) for r in con.execute(
                "SELECT e.fiscal_year,COUNT(DISTINCT e.id) description_groups FROM gaa_location_mentions m JOIN gaa_name_evidence e ON e.id=m.evidence_id WHERE m.mention=? GROUP BY e.fiscal_year ORDER BY e.fiscal_year",(norm(name),))]
        summary['historicalEvidenceWarning']='Mention years are source-title evidence, not administrative effective dates or verified project counts.'
    # High-impact names are reported with full level and parent context, never collapsed.
    summary['priorityNameContexts']={}
    for name in ['Quezon','Isabela','San Jose','Cagayan de Oro City','Butuan City','Maguindanao','Compostela Valley','Davao de Oro']:
        summary['priorityNameContexts'][name]=[dict(r) for r in con.execute('SELECT * FROM qualified_alias_candidates WHERE name_key=? ORDER BY level,province_name,parent_name,name',(norm(name),))]
    return summary

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,default=ROOT/'philippine_locations.sqlite');args=parser.parse_args()
    temporary=args.database.with_suffix('.refining.sqlite')
    with sqlite3.connect(args.database) as original,sqlite3.connect(temporary) as copy:original.backup(copy)
    con=sqlite3.connect(temporary);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
    summary=refine(con);con.commit()
    if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Refinement foreign key integrity failure')
    con.close();temporary.replace(args.database)
    (ROOT/'refinement_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='priorityNameContexts'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
