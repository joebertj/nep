#!/usr/bin/env python3
"""Mine historical GAA names as location evidence; never infer LEG boundaries from a title."""
from __future__ import annotations
import argparse
import csv
import json
import re
import shutil
import sqlite3
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from build_database import Builder, DATA, OUT, norm, uid

SQL='''
CREATE TABLE IF NOT EXISTS gaa_name_evidence(id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(id),fiscal_year INTEGER,budget_stage TEXT,title TEXT,source_locator TEXT,source_row_count INTEGER,context_json TEXT,classification TEXT);
CREATE TABLE IF NOT EXISTS gaa_location_mentions(id TEXT PRIMARY KEY,evidence_id TEXT REFERENCES gaa_name_evidence(id),mention TEXT,start_offset INTEGER,end_offset INTEGER,role TEXT,candidate_place_ids_json TEXT);
CREATE TABLE IF NOT EXISTS gaa_location_chains(id TEXT PRIMARY KEY,evidence_id TEXT REFERENCES gaa_name_evidence(id),child_id TEXT REFERENCES places(id),parent_id TEXT REFERENCES places(id),basis TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS location_review_queue(id TEXT PRIMARY KEY,kind TEXT,mention TEXT,context_key TEXT,example_evidence_id TEXT REFERENCES gaa_name_evidence(id),occurrences INTEGER,status TEXT,decision_json TEXT);
CREATE INDEX IF NOT EXISTS gaa_year ON gaa_name_evidence(fiscal_year);
CREATE INDEX IF NOT EXISTS gaa_mentions_evidence ON gaa_location_mentions(evidence_id);
'''

def quote(value):return "'"+str(value).replace("'","''")+"'"

def parquet(sql):
    result=subprocess.run(['duckdb','-json','-c',sql],capture_output=True,text=True,check=True)
    return json.loads(result.stdout or '[]')

class NameEvidence:
    def __init__(self,builder,reset_evidence=True):
        self.b=builder;self.db=builder.db;self.db.executescript(SQL)
        self.places={r['id']:dict(r) for r in self.db.execute('SELECT id,parent_id,level,name FROM places')}
        # Replace only the addon tables on a rerun; never retain stale extraction
        # classifications. Human decisions are reapplied from their private file.
        for table in ['location_review_queue','gaa_location_chains','gaa_location_mentions']+(['gaa_name_evidence'] if reset_evidence else []):
            self.db.execute('DELETE FROM '+table)
        aliases=defaultdict(set)
        for row in self.db.execute("SELECT a.name_key,a.place_id FROM aliases a JOIN places p ON p.id=a.place_id WHERE p.level IN ('province','city','municipality','locality','barangay')"):
            if len(row[0])>=4 or (row[0] and re.fullmatch(r'[\w .-]+',row[0])):aliases[row[0]].add(row[1])
        # Marker spelling variants retain the same source place ID. Bare numeric
        # forms still require an explicit marker at the mention position.
        for name,pids in list(aliases.items()):
            marker=re.fullmatch(r'(?:barangay|brgy\.?|bgy\.?)\s+(.+)',name)
            if marker:
                aliases[marker[1]].update(p for p in pids if self.places[p]['level']=='barangay')
        self.first=defaultdict(list)
        for name,pids in aliases.items():
            token=re.search(r'\w+',name)
            if token:self.first[token.group()].append((name,sorted(pids),re.compile(r'(?<!\w)'+re.escape(name)+r'(?!\w)')))
        self.year_counts=Counter();self.class_counts=Counter();self.queue={}
        self.total_source_rows=0

    def review(self,kind,mention,eid,context=''):
        key=uid('review',kind,norm(mention),context)
        if key not in self.queue:self.queue[key]=dict(kind=kind,mention=mention,context=context,example=eid,count=0)
        self.queue[key]['count']+=1

    def classify(self,eid,title,year):
        text=norm(title);matches=[]
        for first in sorted(set(re.findall(r'\w+',text))):
            for alias,pids,pattern in self.first.get(first,()):
                for match in pattern.finditer(text):
                    start,end=match.span();prefix=text[max(0,start-24):start]
                    role='name_mention'
                    if re.search(r'\b(?:barangay|brgy\.?|bgy\.?)\s*$',prefix) or re.match(r'^(?:barangay|brgy\.?|bgy\.?)\s+',alias):role='explicit_barangay'
                    elif re.search(r'\bmunicipality of\s*$',prefix):role='explicit_municipality'
                    elif re.search(r'\bcity of\s*$',prefix) or re.search(r'\bcity$',alias):role='explicit_city'
                    elif re.search(r'\bprovince of\s*$',prefix):role='explicit_province'
                    levels={'explicit_barangay':{'barangay'},'explicit_municipality':{'municipality','locality'},'explicit_city':{'city'},'explicit_province':{'province'}}
                    # Short names and numeric barangays need an explicit geographic marker.
                    # Unmarked 122 in chainage or an amount is never a barangay.
                    if len(alias)<4 and role not in levels:continue
                    candidates=[p for p in pids if role not in levels or self.places[p]['level'] in levels[role]]
                    if not candidates:continue
                    matches.append(dict(alias=alias,start=start,end=end,role=role,pids=candidates))
        # Puerto inside Puerto Princesa / Quezon inside Quezon City stays a
        # fragment, never an independent location claim.
        for m in matches:
            if any(n['start']<=m['start'] and m['end']<=n['end'] and n['end']-n['start']>m['end']-m['start'] for n in matches):
                m['role']='nested_name_fragment'
        active=[m for m in matches if m['role']!='nested_name_fragment']
        chains=set()
        for child in active:
            for cid in child['pids']:
                parent_id=self.places[cid]['parent_id']
                for parent in active:
                    if parent_id not in parent['pids'] or parent['start']<child['end']:continue
                    between=text[child['end']:parent['start']]
                    # Location evidence needs adjacent geographic fields, not
                    # two names scattered across a road or institution title.
                    if not re.fullmatch(r'\s*[,;]\s*',between):continue
                    if self.places[cid]['level']=='barangay' and child['role']!='explicit_barangay':continue
                    chains.add((cid,parent_id))
        for cid,pid in sorted(chains):
            self.db.execute('INSERT OR IGNORE INTO gaa_location_chains VALUES(?,?,?,?,?,?)',
                            (uid(eid,cid,pid),eid,cid,pid,'Exact adjacent name fields and existing parent relationship','historical_title_location_evidence'))
        for m in matches:
            self.db.execute('INSERT OR IGNORE INTO gaa_location_mentions VALUES(?,?,?,?,?,?,?)',
                            (uid(eid,m['start'],m['end'],m['alias']),eid,m['alias'],m['start'],m['end'],m['role'],json.dumps(m['pids'])))
        linked={p for pair in chains for p in pair}
        # Queue patterns rather than sending thousands of per-title questions.
        for m in active:
            if m['role'].startswith('explicit_') and not any(p in linked for p in m['pids']):
                self.review('marked_place_without_qualified_chain',m['alias'],eid,','.join(sorted({self.places[p]['level'] for p in m['pids']})))
        markers=list(re.finditer(r'\b(barangay|brgy\.?|bgy\.?|municipality of|city of|province of)\s+([^,;()]{2,70})',text))
        for match in markers:
            name=match.group(2).strip()
            # Avoid inventing a new place from a sentence or a route segment.
            if match.group(1) in {'barangay','brgy','brgy.','bgy','bgy.'} and re.fullmatch(r'(?:hall|road|health (?:center|station)|multipurpose (?:hall|building))',name):
                continue
            if not any((m['start']>=match.start(2) and m['end']<=match.end(2)) or m['start']<=match.start(2)<m['end'] for m in active):
                self.review('unrecognized_marked_place',name,eid,match.group(1))
        if re.search(r'(?<!\w)rtr(?!\w)',text):self.review('unresolved_acronym','RTR',eid,'geographic interpretation and scope')
        route_names=[m for m in active if self.places[m['pids'][0]]['level'] in {'city','municipality','locality'}]
        if len({m['alias'] for m in route_names})>1 and re.search(r'\b(?:road|rd|route|highway|bridge)\b',text) and not chains:
            self.review('route_endpoints_without_located_segment',title,eid,'segment versus route scope')
        status='qualified_location_evidence' if chains else 'mentions_without_qualified_chain' if active else 'no_recognized_location'
        return status

    def ingest_rows(self,path,year,rows,sid):
        for row in rows:
            title=row.pop('title');locator=str(row.get('source_locator') or row.get('first_id') or row.get('first_row'))
            eid=uid('GAA_name',sid,year,title,row.get('agency_desc'),row.get('department_desc'),row.get('region_id'),locator)
            if self.db.execute('SELECT 1 FROM gaa_name_evidence WHERE id=?',(eid,)).fetchone():continue
            count=int(row.get('source_rows') or 1)
            self.db.execute('INSERT INTO gaa_name_evidence VALUES(?,?,?,?,?,?,?,?,?)',(eid,sid,year,'GAA',title,locator,count,json.dumps(row,ensure_ascii=False),'pending_extraction'))
            status=self.classify(eid,title,year)
            self.db.execute('UPDATE gaa_name_evidence SET classification=? WHERE id=?',(status,eid))
            self.year_counts[year]+=1;self.class_counts[status]+=1;self.total_source_rows+=count
            if self.year_counts[year]%5000==0:print(f'Classified {year}: {self.year_counts[year]:,} description groups',flush=True)

    def run(self):
        if not shutil.which('duckdb'):raise RuntimeError('The local DuckDB CLI is required to read the workspace Parquet files.')
        for year in range(2020,2026):
            path=DATA.parent.parent/'data/parquet'/f'budget_{year}.parquet'
            if not path.exists():
                self.b.source(path,'GAA_'+str(year),'budget_names','missing','No local source available.');continue
            sid=self.b.source(path,'GAA_'+str(year),'historical_budget_names',note='Repeated descriptions grouped with exact agency/department/region context. Not certified leaf-project counts or boundary evidence.')
            print('Extracting GAA',year,flush=True)
            rows=parquet(f'''SELECT description AS title,department_desc,agency_desc,region_id,min(id) AS first_id,max(id) AS last_id,count(*) AS source_rows,string_agg(DISTINCT source_file,'; ') AS original_source_files
              FROM read_parquet({quote(path)}) WHERE description IS NOT NULL AND trim(description)<>''
              GROUP BY description,department_desc,agency_desc,region_id ORDER BY first_id''')
            self.ingest_rows(path,year,rows,sid);self.db.commit();print('Imported',year,len(rows),'description groups',flush=True)
        path=DATA.parent.parent/'data/parquet/parsed_dpwh_2026.parquet'
        if path.exists():
            sid=self.b.source(path,'GAA_2026_DPWH','historical_budget_name_fragments',note='DPWH enrolled-copy schedule only. col_J can be a wrapped title fragment; original row and qualifier context retained. Other-agency FY2026 GAA coverage is not implied.')
            rows=parquet(f'''SELECT col_J AS title,_excel_row AS first_row,latest_qualifier_column,latest_qualifier_value,col_B,col_C,col_D,col_E,col_F,col_G,col_H,col_I FROM read_parquet({quote(path)}) WHERE col_J IS NOT NULL AND trim(col_J)<>'' ORDER BY _excel_row''')
            print('Extracting GAA 2026 DPWH',flush=True);self.ingest_rows(path,2026,rows,sid)
        self.publish_queue()

    def publish_queue(self):
        for key,v in self.queue.items():
            self.db.execute('INSERT OR IGNORE INTO location_review_queue VALUES(?,?,?,?,?,?,?,?)',(key,v['kind'],v['mention'],v['context'],v['example'],v['count'],'pending_user_classification',None))
        decisions_path=OUT/'manual_location_decisions.json'
        if decisions_path.exists():
            sid=self.b.source(decisions_path,'human_location_review','human_classification',note='Scoped user decisions; no automatic boundary or alias changes.')
            for decision in json.loads(decisions_path.read_text()).get('decisions',[]):
                self.db.execute('UPDATE location_review_queue SET status=?,decision_json=? WHERE id=?',('user_classified',json.dumps(decision,ensure_ascii=False),decision['review_id']))
                if decision.get('scope',{}).get('titles'):
                    # A user answer about two examples must not resolve every
                    # occurrence of the same acronym in the historical archive.
                    for title in decision['scope']['titles']:
                        self.db.execute('UPDATE location_review_queue SET status=?,decision_json=? WHERE example_evidence_id IN (SELECT id FROM gaa_name_evidence WHERE title=?) AND kind=?',
                                        ('example_user_classified_scope_only',json.dumps(decision,ensure_ascii=False),title,'unresolved_acronym'))
        self.db.commit()

    def reclassify(self):
        """Keep original title/context/locators; rebuild mentions and review groups only."""
        cursor=self.db.execute('SELECT id,title,fiscal_year,source_row_count FROM gaa_name_evidence ORDER BY fiscal_year,source_locator')
        for row in cursor:
            status=self.classify(row['id'],row['title'],row['fiscal_year'])
            self.db.execute('UPDATE gaa_name_evidence SET classification=? WHERE id=?',(status,row['id']))
            self.year_counts[row['fiscal_year']]+=1;self.class_counts[status]+=1
            self.total_source_rows+=row['source_row_count']
            if sum(self.year_counts.values())%5000==0:print('Reclassified',sum(self.year_counts.values()),'historical description groups',flush=True)
        self.publish_queue()

    def export(self):
        rows=[dict(r) for r in self.db.execute('SELECT q.*,e.fiscal_year,e.title,e.source_locator,s.path FROM location_review_queue q JOIN gaa_name_evidence e ON e.id=q.example_evidence_id JOIN sources s ON s.id=e.source_id ORDER BY q.occurrences DESC,q.id')]
        with (OUT/'gaa_location_review_queue.csv').open('w',encoding='utf-8-sig',newline='') as f:
            fields=['id','kind','mention','context_key','occurrences','status','fiscal_year','title','source_locator','path']
            w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
        summary={'years':[dict(r) for r in self.db.execute('SELECT fiscal_year,COUNT(*) description_groups,SUM(source_row_count) source_rows FROM gaa_name_evidence GROUP BY fiscal_year ORDER BY fiscal_year')],
                 'classifications':dict(self.db.execute('SELECT classification,COUNT(*) FROM gaa_name_evidence GROUP BY classification').fetchall()),
                 'reviewGroups':len(rows),'reviewStatus':'Unanswered groups remain unresolved; no LEG assignment, alias creation or public budget recalculation is performed.',
                 'limitations':['Description groups are not project counts.','FY2026 coverage is DPWH only; col_J may be a title fragment.','Historic title evidence does not establish current LEG boundaries.','Mention offsets refer to normalized lookup text, not original title character positions.','Only existing exact aliases generate candidates; unknown spellings and acronyms require review.'],
                 'firstReviewExamples':rows[:15]}
        (OUT/'gaa_name_import_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in summary.items() if k!='firstReviewExamples'},ensure_ascii=False,indent=2))

def ingest(builder):
    importer=NameEvidence(builder);importer.run();importer.export()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,default=OUT/'philippine_locations.sqlite');parser.add_argument('--reclassify',action='store_true',help='Reclassify existing historical evidence without rereading source Parquet');args=parser.parse_args()
    temporary=args.database.with_suffix('.gaa-building.sqlite')
    with sqlite3.connect(args.database) as original,sqlite3.connect(temporary) as copy:original.backup(copy)
    con=sqlite3.connect(temporary);con.row_factory=sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    from apply_spelling_decisions import apply as apply_spelling
    apply_spelling(con)
    if args.reclassify:
        importer=NameEvidence(Builder(con),reset_evidence=False);importer.reclassify();importer.export()
    else:ingest(Builder(con))
    if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('GAA import foreign key integrity failure')
    con.close();temporary.replace(args.database)

if __name__=='__main__':main()
