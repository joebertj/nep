#!/usr/bin/env python3
"""Import local analyst exports as qualified location evidence, never boundary facts."""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from hgab_matching import normalize
from location_data.build_database import Builder, norm, uid
from location_data.location_text import geographic_title

SQL = '''
CREATE TABLE IF NOT EXISTS analyst_candidate_evidence(
 id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),locator TEXT NOT NULL,
 external_id TEXT,record_kind TEXT,title TEXT NOT NULL,amount_pesos INTEGER,
 office TEXT,source_page INTEGER,link_status TEXT NOT NULL,raw_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analyst_native_links(
 evidence_id TEXT REFERENCES analyst_candidate_evidence(id),native_id TEXT,
 native_source_id TEXT REFERENCES sources(id),link_basis TEXT,own_comparison TEXT,
 geography_status TEXT,districts_json TEXT,native_json TEXT,
 PRIMARY KEY(evidence_id,native_id));
CREATE TABLE IF NOT EXISTS analyst_location_candidates(
 evidence_id TEXT REFERENCES analyst_candidate_evidence(id),place_id TEXT REFERENCES places(id),
 role TEXT NOT NULL,basis TEXT NOT NULL,PRIMARY KEY(evidence_id,place_id,role));
CREATE TABLE IF NOT EXISTS analyst_location_review(
 id TEXT PRIMARY KEY,evidence_id TEXT REFERENCES analyst_candidate_evidence(id),
 kind TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',detail_json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS analyst_location_review_kind ON analyst_location_review(kind,status);
'''


def ingest(con, paths=None):
    """Refresh evidence atomically in the caller's transaction; preserve review statuses."""
    con.executescript(SQL)
    paths = paths or [ROOT/'analysis_output/dpwh-projects-filtered.json',
                      ROOT/'analysis_output/all_house_only_candidates.json']
    native_path = ROOT/'hb10858_3rd_dpwh_projects.json'
    match_path = ROOT/'analysis_output/hb_nep_comparison_3rd.csv'
    geo_path = ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json'
    if not all(p.exists() for p in [native_path, match_path, geo_path]):
        return {'status': 'missing native comparison or geography; no import'}
    b = Builder(con)
    decisions_path = ROOT/'location_data/manual_location_decisions.json'
    decisions = json.loads(decisions_path.read_text()).get('decisions',[]) if decisions_path.exists() else []
    decision_sid = b.source(decisions_path, 'human_location_review', 'human_classification', note='Title-scoped corrections; no global alias or boundary change.') if decisions_path.exists() else None
    native_sid = b.source(native_path, 'HGAB_3rd_native', 'allocation_extract')
    b.source(match_path, 'local_nep_hgab_comparison', 'derived_comparison', note='Local matching output, not external insertion proof.')
    b.source(geo_path, 'local_strict_leg_audit', 'derived_geography', note='Current strict audit; undated memberships are not promoted.')
    native = json.loads(native_path.read_text())['data']['data']
    index = defaultdict(list)
    for row in native:
        index[normalize(row['projectName']), row['amountPesos'], row['sourcePage']].append(row)
    with match_path.open() as f:
        comparison = {r['hgab_id']: r for r in csv.DictReader(f)}
    geography = {r['id']: r for r in json.loads(geo_path.read_text())['projects']}
    alias_index = defaultdict(list)
    for r in con.execute('SELECT * FROM qualified_alias_candidates'):
        alias_index[r['name_key']].append(dict(r))
    summaries = []
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        sid = b.source(path, 'external_analyst_export', 'comparison_rows',
                       note='External candidate labels are assertions, not verified insertion or LEG facts. Original records retained.')
        source_counts, links_count, reasons = Counter(), Counter(), Counter()
        total = matched_pesos = linked_native_records = 0
        reports = []
        for i, row in enumerate(data['rows']):
            s = row.get('third') or row.get('second')
            if not s:
                raise ValueError(f'Missing source allocation: {path.name}, row {i}')
            eid = uid('analyst_candidate', sid, row.get('id'), i)
            kind = s.get('record_kind', 'unknown')
            amount = s['amount_php']
            total += amount
            source_counts[kind] += 1
            parts = s.get('records') or [s]
            hits, group_ok = [], True
            used = set()
            for part in parts:
                found = index[normalize(part['title']), part['amount_php'], part['pdf_page']]
                # Identical occurrences can link as a complete group only when
                # all occurrences are represented, without choosing an arbitrary one.
                if len(parts) == 1 and len(found) != 1:
                    group_ok = False
                available = [r for r in found if r['id'] not in used]
                if not available:
                    group_ok = False
                    continue
                h = available[0]
                hits.append(h); used.add(h['id'])
                if len(found) > 1 and sum(normalize(p['title']) == normalize(part['title'])
                    and p['amount_php'] == part['amount_php'] and p['pdf_page'] == part['pdf_page']
                    for p in parts) != len(found):
                    group_ok = False
            if sum(p['amount_php'] for p in parts) != amount:
                group_ok = False
            if kind not in {'project', 'fap_project'}:
                group_ok = False
            if not group_ok:
                hits = []
            status = ('exact_allocation_group' if len(hits)>1 else 'exact_unique_allocation') if hits else 'source_review'
            con.execute('INSERT OR REPLACE INTO analyst_candidate_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (eid,sid,f'rows[{i}]',row.get('id'),kind,s['title'],amount,s.get('office'),s.get('pdf_page'),status,json.dumps(row,ensure_ascii=False)))
            con.execute('DELETE FROM analyst_native_links WHERE evidence_id=?',(eid,))
            con.execute('DELETE FROM analyst_location_candidates WHERE evidence_id=?',(eid,))
            reviews = []
            if not hits:
                reviews.append(('non_project_source_record' if kind not in {'project','fap_project'} else 'source_link_discrepancy',
                                {'title':s['title'],'amountPesos':amount,'page':s.get('pdf_page'),'recordKind':kind}))
            for h in hits:
                c, g = comparison.get(h['id'], {}), geography.get(h['id'], {})
                con.execute('INSERT INTO analyst_native_links VALUES(?,?,?,?,?,?,?,?)',
                            (eid,h['id'],native_sid,status,c.get('comparison'),g.get('status'),json.dumps(g.get('districts',[]),ensure_ascii=False),json.dumps(h,ensure_ascii=False)))
            links_count[status] += 1
            if hits:
                matched_pesos += amount
                linked_native_records += len(hits)
            titles = [('external_title', s['title'])] + [('native_title', h['projectName']) for h in hits]
            places = set()
            for role, title in titles:
                address, separated_metadata = geographic_title(title)
                correction = next((d for d in decisions if row.get('third') and d.get('address_replacement')
                                   and 2027 in d.get('scope',{}).get('years',[])
                                   and 'HGAB 3rd Reading' in d.get('scope',{}).get('stages',[])
                                   and title in d.get('scope',{}).get('titles',[])), None)
                if correction:
                    address, separated_metadata = geographic_title(title.replace(correction['address_replacement']['from'],correction['address_replacement']['to']))
                    b.observed(decision_sid,eid,'title_scoped_address_correction',correction)
                b.observed(sid,eid+':'+role,'analyst_parsed_address',
                           {'originalTitle':title,'addressLookup':address,'metadata':separated_metadata,
                            'correctionReviewId':correction['review_id'] if correction else None})
                fields = [f.strip(' .') for f in address.split(',')]
                provinces = [r for r in alias_index.get(norm(fields[-1]),[]) if r['level']=='province']
                towns = [r for p in provinces for r in alias_index.get(norm(re.sub(r'^municipality of\s+','',fields[-2])),[])
                         if r['parent_id']==p['place_id'] and r['level'] in {'city','municipality','locality'}] if len(fields)>=2 else []
                candidates = provinces + towns
                markers = re.findall(r'\b(?:barangay|brgy\.?|bgy\.?)\s+([^,;()]+)', ','.join(fields[:-2]))
                for marker in markers:
                    if re.search(r'\b(?:to|and|road|bridge|section|system|school|phase)\b|[/&]', marker):
                        continue
                    keys = [norm(marker.strip(' .')), norm('Barangay '+marker.strip(' .')), norm('Brgy. '+marker.strip(' .'))]
                    candidates += [r for t in towns for key in keys for r in alias_index.get(key,[])
                                   if r['parent_id']==t['place_id'] and r['level']=='barangay']
                for r in candidates:
                    places.add(r['place_id'])
                    con.execute('INSERT OR IGNORE INTO analyst_location_candidates VALUES(?,?,?,?)',
                                (eid,r['place_id'],role,('User-confirmed title-scoped spelling correction; ' if correction else '')+'Exact alias with province and municipal parent constraints; candidate identity, not funded segment or LEG assignment.'))
                if not towns:
                    reviews.append(('qualified_location_unresolved', {'role':role,'title':title,'provinceCandidates':[p['place_id'] for p in provinces]}))
                if re.search(r'\([^)]*(?:\d+\.\d+|\bsta\.?\s*\d)[^)]*\)\s*$',address):
                    reviews.append(('trailing_address_metadata_review',{'role':role,'title':title,'note':'Parenthesized coordinates/chainage retained; never interpret coordinates as district evidence.'}))
            if any(geography.get(h['id'],{}).get('status') != 'unique' for h in hits):
                reviews.append(('leg_or_construction_scope_unresolved',{'nativeIds':[h['id'] for h in hits]}))
            if kind=='fap_project':
                reviews.append(('fap_separate_review',{'note':'Not counted as domestic insertion; external absence of NEP anchor is not proof.'}))
            for reason, detail in reviews:
                reasons[reason] += 1
                con.execute('INSERT INTO analyst_location_review VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET detail_json=excluded.detail_json',
                            (uid('analyst_review',eid,reason,detail.get('role')),eid,reason,'pending',json.dumps(detail,ensure_ascii=False)))
            reports.append({'evidenceId':eid,'externalId':row.get('id'),'title':s['title'],'amountPesos':amount,'recordKind':kind,
                            'sourcePage':s.get('pdf_page'),'sourceLink':status,'nativeIds':[h['id'] for h in hits],
                            'ownComparison':[comparison.get(h['id'],{}).get('comparison') for h in hits],
                            'placeCandidateIds':sorted(places),'reviewKinds':sorted(set(k for k,_ in reviews))})
            current_review_ids = {uid('analyst_review',eid,k,d.get('role')) for k,d in reviews}
            for old in con.execute('SELECT id,status FROM analyst_location_review WHERE evidence_id=?',(eid,)).fetchall():
                if old['id'] not in current_review_ids and old['status']=='pending':
                    con.execute('DELETE FROM analyst_location_review WHERE id=?',(old['id'],))
        active_ids = {r['evidenceId'] for r in reports}
        for old in con.execute('SELECT id FROM analyst_candidate_evidence WHERE source_id=?',(sid,)).fetchall():
            if old['id'] not in active_ids:
                for table in ['analyst_native_links','analyst_location_candidates','analyst_location_review']:
                    con.execute(f'DELETE FROM {table} WHERE evidence_id=?',(old['id'],))
                con.execute('DELETE FROM analyst_candidate_evidence WHERE id=?',(old['id'],))
        summary = {'source':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                   'comparisonRows':len(reports),'externalAllocationPesos':total,'recordKinds':dict(source_counts),
                   'sourceLinks':dict(links_count),'linkedNativeAllocationRecords':linked_native_records,
                   'linkedExternalAllocationPesos':matched_pesos,'reviewReasons':dict(reasons),
                   'rowsWithQualifiedPlaceCandidates':sum(bool(r['placeCandidateIds']) for r in reports),
                   'linkedNativeComparisonStatuses':dict(Counter(status for r in reports for status in r['ownComparison'])),
                   'newAliases':0,'newBoundaryClaims':0,'newAutomaticLEGAssignments':0}
        out = ROOT/'analysis_output'/f'{path.stem}_location_evidence.json'
        out.write_text(json.dumps({'method':'External assertions retained separately; exact source linkage and parent-qualified existing identities only. Comparison rows may group allocation records.',
                                  'summary':summary,'rows':reports},ensure_ascii=False,indent=2)+'\n')
        with out.with_name(out.stem+'_review.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=['evidenceId','externalId','title','amountPesos','recordKind','sourcePage','sourceLink','nativeIds','reviewKinds'])
            writer.writeheader()
            writer.writerows({k:'; '.join(r[k]) if isinstance(r[k],list) else r[k] for k in writer.fieldnames}
                            for r in reports if r['reviewKinds'])
        summaries.append(summary)
    return {'sources':summaries,'externalStatusesAdopted':False,'publicPagesChanged':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,default=ROOT/'location_data/philippine_locations.sqlite')
    parser.add_argument('--external',type=Path,action='append')
    args=parser.parse_args()
    temp=args.database.with_suffix('.analyst-import.sqlite')
    if temp.exists():temp.unlink()
    with sqlite3.connect(args.database) as original,sqlite3.connect(temp) as copy:original.backup(copy)
    con=sqlite3.connect(temp);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
    summary=ingest(con,args.external);con.commit()
    if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Analyst import foreign-key failure')
    con.close();temp.replace(args.database)
    (ROOT/'location_data/analyst_candidate_import_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
