#!/usr/bin/env python3
"""Read-only inspection of qualified places, LEG evidence and DEO crosswalks."""
import argparse
import json
import sqlite3
from pathlib import Path
from build_database import norm, district

ROOT=Path(__file__).resolve().parent

def ancestors(db,pid):
    rows=[]
    while pid:
        row=db.execute('SELECT * FROM places WHERE id=?',(pid,)).fetchone()
        if not row:break
        rows.append(dict(row));pid=row['parent_id']
    return rows

def memberships(db,pid):
    rows=[]
    for r in db.execute('SELECT m.*,d.jurisdiction,d.designation,s.path,s.family FROM leg_memberships m JOIN leg_districts d ON m.leg_id=d.id JOIN sources s ON m.source_id=s.id WHERE m.place_id=? ORDER BY s.path,m.locator',(pid,)):
        row=dict(r);row.pop('raw_json');rows.append(row)
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=ROOT/'philippine_locations.sqlite')
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--name');mode.add_argument('--deo');mode.add_argument('--leg',help='exact LEG jurisdiction name');mode.add_argument('--case',help='source project ID for an imported location edge case');mode.add_argument('--summary',action='store_true')
    mode.add_argument('--gaa',help='search original historical GAA titles (substring)')
    mode.add_argument('--review',help='search grouped location questions (substring)')
    parser.add_argument('--level',choices=['region','province','city','municipality','locality','barangay'])
    parser.add_argument('--province');parser.add_argument('--municipality');parser.add_argument('--district');parser.add_argument('--limit',type=int,default=20)
    args=parser.parse_args();db=sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    if args.summary:
        out={'placesByClaimedLevel':dict(db.execute('SELECT level,COUNT(*) FROM places GROUP BY level').fetchall()),'issuesByKind':dict(db.execute('SELECT kind,COUNT(*) FROM issues GROUP BY kind').fetchall()),'warning':'Counts include source variants and disputed identities, not official administrative totals.'}
    elif args.gaa:
        records=[]
        for row in db.execute('SELECT e.*,s.path FROM gaa_name_evidence e JOIN sources s ON s.id=e.source_id WHERE instr(lower(e.title),lower(?))>0 ORDER BY fiscal_year,source_locator LIMIT ?',(args.gaa,max(0,args.limit))):
            item=dict(row)
            item['mentions']=[dict(r) for r in db.execute('SELECT * FROM gaa_location_mentions WHERE evidence_id=?',(row['id'],))]
            item['chains']=[dict(r) for r in db.execute('SELECT c.*,p.name child_name,a.name parent_name FROM gaa_location_chains c JOIN places p ON p.id=c.child_id JOIN places a ON a.id=c.parent_id WHERE c.evidence_id=?',(row['id'],))]
            records.append(item)
        out={'evidence':records,'warning':'Historical title evidence, not a current LEG attribution. Repeated source rows are not project counts.'}
    elif args.review:
        out={'questions':[dict(r) for r in db.execute('SELECT q.*,e.fiscal_year,e.title,e.source_locator FROM location_review_queue q JOIN gaa_name_evidence e ON e.id=q.example_evidence_id WHERE instr(lower(q.mention),lower(?))>0 ORDER BY occurrences DESC LIMIT ?',(args.review,max(0,args.limit)))]}
    elif args.case:
        out={'cases':[{'source':r['path'],'evidence':json.loads(r['raw_json'])} for r in db.execute("SELECT s.path,o.raw_json FROM observations o JOIN sources s ON s.id=o.source_id WHERE o.kind='location_edge_case' AND o.locator=?",(args.case,))]}
    elif args.deo:
        rows=db.execute('SELECT DISTINCT d.* FROM deos d JOIN deo_aliases a ON d.id=a.deo_id WHERE a.name_key=? OR d.name_key=?',(norm(args.deo),norm(args.deo))).fetchall()
        out={'candidates':[]}
        for row in rows:
            item=dict(row);item['legClaims']=[dict(x) for x in db.execute('SELECT c.*,d.jurisdiction,d.designation,s.path FROM deo_leg_claims c JOIN leg_districts d ON c.leg_id=d.id JOIN sources s ON c.source_id=s.id WHERE c.deo_id=?',(row['id'],))]
            out['candidates'].append(item)
        out['warning']='DEO coverage and transcribed amounts are reference claims; no project allocation or ownership is inferred.'
    elif args.leg:
        sql='SELECT * FROM leg_districts WHERE jurisdiction_key=?';params=[norm(args.leg)]
        if args.district:sql+=' AND designation=?';params.append(district(args.district))
        out={'districts':[]}
        for row in db.execute(sql,params).fetchall():
            item=dict(row);item['representativeClaims']=[dict(x) for x in db.execute('SELECT r.name,t.term_label,t.start_year,t.end_year,s.path,t.locator FROM representative_terms t JOIN representatives r ON r.id=t.representative_id JOIN sources s ON s.id=t.source_id WHERE t.leg_id=? GROUP BY r.name,t.term_label,t.start_year,t.end_year,s.path',(row['id'],))]
            item['placeClaimCount']=db.execute('SELECT COUNT(*) FROM leg_memberships WHERE leg_id=?',(row['id'],)).fetchone()[0]
            item['deoClaims']=[dict(x) for x in db.execute('SELECT d.name,c.amount_pesos,c.fiscal_year,c.budget_stage,c.status,s.path FROM deo_leg_claims c JOIN deos d ON d.id=c.deo_id JOIN sources s ON s.id=c.source_id WHERE c.leg_id=?',(row['id'],))];out['districts'].append(item)
    else:
        sql='SELECT DISTINCT p.* FROM places p JOIN aliases a ON p.id=a.place_id WHERE a.name_key=?';params=[norm(args.name)]
        if args.level:sql+=' AND p.level=?';params.append(args.level)
        matched=[]
        for row in db.execute(sql,params).fetchall():
            chain=ancestors(db,row['id'])
            def parent_matches(name,levels):
                return any(db.execute('SELECT 1 FROM aliases WHERE place_id=? AND name_key=?',(p['id'],norm(name))).fetchone() for p in chain[1:] if p['level'] in levels)
            if args.province and not parent_matches(args.province,('province',)):continue
            if args.municipality and not parent_matches(args.municipality,('city','municipality','locality')):continue
            item=dict(row);item['geographicPath']=' > '.join(p['name'] for p in reversed(chain))
            item['legClaims']=memberships(db,row['id']);item['membershipReview']=dict(review) if (review:=db.execute('SELECT * FROM leg_membership_review WHERE place_id=?',(row['id'],)).fetchone()) else None
            matched.append(item)
        out={'candidateCount':len(matched),'status':'ambiguous_name' if len(matched)>1 else 'unique_place_candidate' if matched else 'unresolved_name','candidates':matched[:max(0,args.limit)],'warning':'Exact alias candidates only. A unique place candidate does not verify its LEG boundary or the role of the name in a project title. Dates and provenance must be reviewed.'}
    print(json.dumps(out,ensure_ascii=False,indent=2));db.close()

if __name__=='__main__':main()
