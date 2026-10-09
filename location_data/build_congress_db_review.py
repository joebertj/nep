#!/usr/bin/env python3
"""Audit HGAB attribution against private location evidence; export only supported scope holds."""
import argparse
import hashlib
import json
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
ODV=ROOT.parent/'open-data-visualization'
sys.path.insert(0,str(ODV/'analysis'))
from strict_congress_geography import GeographicAttribution, text_key, place_key, seat_key


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-scope-review',action='store_true',help='copy supported scope holds to the static ODV build input')
    args=parser.parse_args()
    database=ROOT/'location_data/philippine_locations.sqlite'
    db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    source=ROOT/'hb10858_3rd_dpwh_projects.json'
    projects=json.loads(source.read_text())['data']['data']
    roster=json.loads((ODV/'static/data/20th_congress_representatives.json').read_text())
    seats={}
    for row in roster:
        if seat_key(row['district']) and row.get('representative') and text_key(row['representative'])!='special election':
            seats[text_key(row['province']),seat_key(row['district'])]={'province':row['province'],'districtLabel':row['district'],'representative':row['representative']}
    seats=sorted(seats.values(),key=lambda r:(text_key(r['province']),r['districtLabel']))
    legacy=GeographicAttribution(ODV/'static/data',seats)

    @lru_cache(maxsize=None)
    def lookup(label,parent=None):
        # Full comma-delimited fields only. Preserve geographic level and parent.
        keys={text_key(label)}
        for prefix in ['province of ','municipality of ']:
            if text_key(label).startswith(prefix):keys.add(text_key(label)[len(prefix):])
        result={}
        for key in keys:
            for r in db.execute('SELECT DISTINCT p.* FROM places p JOIN aliases a ON a.place_id=p.id WHERE a.name_key=?',(key,)):
                if parent is not None and r['parent_id']!=parent:continue
                result[r['id']]=dict(r)
        return tuple(result.values())

    @lru_cache(maxsize=None)
    def memberships(pid):
        return tuple(dict(r) for r in db.execute('SELECT d.jurisdiction,d.designation,s.family,m.valid_from,m.valid_to,m.scope,m.status,s.sha256,m.locator FROM leg_memberships m JOIN leg_districts d ON d.id=m.leg_id JOIN sources s ON s.id=m.source_id WHERE m.place_id=? AND m.status=?',(pid,'located_source_claim')))

    issues={}
    manual_path=ROOT/'location_data/manual_location_decisions.json'
    manual=json.loads(manual_path.read_text()).get('decisions',[]) if manual_path.exists() else []
    for r in db.execute("SELECT i.*,s.sha256 FROM issues i JOIN sources s ON s.id=i.source_id WHERE i.kind='project_route_scope_review'"):
        issues[r['entity_id']]=dict(r)
    evidence={};review=[];held=[];qualified=0;blocked_baseline=0
    for row in projects:
        title=row['projectName'];baseline=legacy.resolve(row)
        fields=[f.strip(' .') for f in title.split(',')]
        candidates=[]
        if len(fields)>=2:
            for parent in lookup(fields[-1]):
                if parent['level']!='province':continue
                for child in lookup(fields[-2],parent['id']):
                    if child['level'] not in {'city','municipality','locality'}:continue
                    claims=list(memberships(child['id']))
                    candidates.append({'placeId':child['id'],'name':child['name'],'level':child['level'],
                                       'provinceId':parent['id'],'province':parent['name'],'legClaims':claims})
        extra=[]
        if candidates:
            qualified+=1
            extra.append({'basis':'Private DB exact adjacent municipality/city and province fields; geographic evidence only',
                          'candidatePlaces':[dict((k,v) for k,v in c.items() if k!='legClaims') for c in candidates]})
            if not baseline['indices']:
                review.append({'id':row['id'],'projectName':title,'amountPesos':row['amountPesos'],
                               'baselineReasons':baseline['reasons'],'candidatePlaces':candidates,
                               'status':'No new assignment: membership dates or conflicting/ambiguous identities require review'})
        hold=False;reasons=[]
        if row['id'] in issues:
            issue=issues[row['id']];detail=json.loads(issue['detail_json'])
            if detail['title']!=title:raise ValueError('Scope-review title differs from current HGAB record')
            observed=db.execute("SELECT raw_json FROM observations WHERE kind='location_edge_case' AND locator=?",(row['id'],)).fetchone()
            if not observed or json.loads(observed[0])['amountPesos']!=row['amountPesos']:raise ValueError('Scope-review amount not corroborated')
            hold=True;reasons=['Route includes a separately located endpoint without chainage or an allocation split proving the full amount belongs to the named city']
            extra.append({'basis':'Unresolved project construction scope recorded in the private location database',
                          'issueId':issue['id'],'sourceSha256':issue['sha256'],'sourcePage':row.get('sourcePage'),
                          'RTRInterpretation':'User confirmed Remedios T. Romualdez for this title; construction segment remains unestablished'})
            for decision in manual:
                if row['id'] in decision.get('scope',{}).get('project_ids',[]):
                    extra.append({'basis':'Scoped user location review','decisionId':decision['review_id'],
                                  'supportingUserAnswer':decision['supporting_user_answer'],
                                  'interpretation':decision['interpretation']})
            blocked_baseline+=bool(baseline['indices'])
            held.append({'id':row['id'],'projectName':title,'amountPesos':row['amountPesos'],
                         'previousDistricts':[f"{seats[i]['province']} · {seats[i]['districtLabel']}" for i in baseline['indices']],
                         'reasons':reasons})
        if extra:
            evidence[row['id']]={'projectName':title,'amountPesos':row['amountPesos'],'evidence':extra,'holdUnresolved':hold,'reasons':reasons}
    dated=db.execute('SELECT COUNT(*) FROM leg_memberships WHERE valid_from IS NOT NULL').fetchone()[0]
    summary={'databaseSha256':hashlib.sha256(database.read_bytes()).hexdigest(),
             'manualReviewSha256':hashlib.sha256(manual_path.read_bytes()).hexdigest() if manual_path.exists() else None,
             'hgabSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'qualifiedLocationRows':qualified,
             'unresolvedWithQualifiedPlaceCandidates':len(review),'scopeHolds':len(held),
             'previouslyAcceptedScopeHolds':blocked_baseline,'datedMembershipClaims':dated,
             'newAssignmentsFromUndatedDbClaims':0,'policy':'Geographic evidence and scope exclusions only. Undated LEG claims, DEOs and historic GAA titles do not establish new current district assignments.'}
    out=ROOT/'analysis_output/congress_location_db_review.json'
    out.write_text(json.dumps({'summary':summary,'decisions':evidence,'candidateReview':review,'heldRows':held},ensure_ascii=False,indent=2)+'\n')
    if args.write_scope_review:
        public={'summary':summary,'decisions':{k:v for k,v in evidence.items() if v['holdUnresolved']}}
        (ODV/'static/data/congress_location_scope_reviews.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'summary':summary,'heldRows':held},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
