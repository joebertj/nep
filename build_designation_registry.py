"""Merge captured ODV official-role evidence with source years and exact-name keys."""
import collections,csv,hashlib,json,re,sqlite3,subprocess,unicodedata
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'data_sources/odv_dynasty'
OUT=ROOT/'data_sources/designation_registry'

def clean(value):
 return re.sub(r'\s+',' ',str(value or '')).strip()

def name_key(value):
 value=unicodedata.normalize('NFKC',clean(value)).upper().replace('’',"'")
 return re.sub(r'[^A-Z0-9]+',' ',value).strip()

def canonical_role(position,organization=''):
 s=clean(position).upper()
 if re.search(r'\b(?:VICE|DEPUTY|FORMER|RETIRED)\b',s):return None
 s=re.sub(r'^(?:(?:OIC|ACTING|OFFICER[ -]IN[ -]CHARGE)[ ,:.-]*)+','',s)
 if re.match(r'^ASSISTANT DISTRICT ENGINEER\b',s):return 'assistant_district_engineer'
 if re.match(r'^(?:NCR )?DISTRICT ENGINEER\b',s):return 'district_engineer'
 if re.match(r'^(?:CITY |MUNICIPAL )?MAYOR\b',s):return 'mayor'
 if re.match(r'^(?:PROVINCIAL )?GOVERNOR\b',s) and not re.search(r'MONETARY|CENTRAL BANK|BANGKO',s+' '+organization.upper()):return 'governor'
 return None

def build():
 OUT.mkdir(parents=True,exist_ok=True)
 manifest=json.loads((SOURCE/'manifest.json').read_text())
 parquet=SOURCE/'source_officials.parquet'
 if not parquet.exists():parquet=SOURCE/'political_dynasties.parquet'
 query=f"SELECT * FROM read_parquet('{parquet.as_posix()}')"
 local=json.loads(subprocess.check_output(['duckdb','-json','-c',query],text=True))
 records=[]
 for row in local:records.append((row,'odv_source_dump','source_officials.parquet'))
 legacy=SOURCE/'political_dynasties.parquet'
 if legacy.exists() and legacy!=parquet:
  previous=json.loads(subprocess.check_output(['duckdb','-json','-c',f"SELECT * FROM read_parquet('{legacy.as_posix()}')"],text=True))
  for row in previous:records.append((row,'odv_legacy_parquet',legacy.name))
 for path in sorted(SOURCE.glob('*-page-*.json')):
  for row in json.loads(path.read_text())['data']:records.append((row,'odv_public_api',path.name))
 merged={};rejected=collections.Counter();review=[]
 for row,source_kind,file in records:
  position=clean(row.get('position'));organization=clean(row.get('organization'))
  role=canonical_role(position,organization)
  if not role:
   if re.search(r'GOVERNOR|MAYOR|DISTRICT ENGINEER',position,re.I):rejected[position]+=1
   continue
  names=[clean(row.get(k)) for k in ('first_name','middle_name','last_name')]
  source_name=clean(' '.join(x for x in names if x))
  full=re.sub(r'^(?:SGD[., ]*|SIGNED[ ,:]*)','',source_name,flags=re.I).strip()
  if not full or not row.get('last_name'):continue
  year=row.get('year')
  try:year=int(float(year)) if year is not None else None
  except (ValueError,TypeError,OverflowError):year=None
  if year is not None and not 1900<=year<=2100:year=None
  tokens=re.findall(r"[A-Za-zÀ-ÿ]+",full)
  eligible=sum(len(t)>1 for t in tokens)>=2 and len(tokens)<=6
  item={'sourceName':source_name,'matchEligible':eligible,'nameQuality':'full_name_candidate' if eligible else 'incomplete_or_compound_name_review','name':full,'first_name':names[0],'middle_name':names[1],'last_name':names[2],
        'nickname':clean(row.get('nickname')),'nameKey':name_key(full),'role':role,'position':position,
        'organization':organization,'province':clean(row.get('province')),'municipality_city':clean(row.get('municipality_city')),
        'region':clean(row.get('region')),'year':year,'verification':'source_designation_record; locality and date require document confirmation'}
  key=tuple(item[k] for k in ('nameKey','role','position','organization','province','municipality_city','year'))
  record=merged.setdefault(key,{**item,'sources':[]})
  provenance={'kind':source_kind,'recordId':row.get('id'),'file':file,'url':manifest['page']}
  if provenance not in record['sources']:record['sources'].append(provenance)
 rows=sorted(merged.values(),key=lambda r:(r['role'],r['nameKey'],r['year'] or 0,r['province'],r['municipality_city']))
 for row in rows:row['id']=hashlib.sha256(json.dumps({k:v for k,v in row.items() if k!='sources'},sort_keys=True).encode()).hexdigest()[:20]
 summary={'sourceRowsRead':len(records),'sourceLocalParquetRows':len(local),'designationRecords':len(rows),
          'roles':dict(collections.Counter(r['role'] for r in rows)),'years':dict(sorted(collections.Counter(str(r['year']) for r in rows).items())),
          'matchEligibleRecords':sum(r['matchEligible'] for r in rows),'nameReviewRecords':sum(not r['matchEligible'] for r in rows),
          'recordsWithOrganization':sum(bool(r['organization']) for r in rows),'recordsWithLiveApiEvidence':sum(any(s['kind']=='odv_public_api' for s in r['sources']) for r in rows)}
 payload={'generatedAtUtc':datetime.now(timezone.utc).isoformat(),'sourceManifest':'../odv_dynasty/source-table-manifest.json','sourcePage':manifest['page'],'summary':summary,
          'policy':'Exact normalized full names and explicit designations only. DE/ADE are distinct. Vice, former, monetary-board governor and roles only mentioned within another job title are excluded. Source years are observations, not inferred term intervals. Dynasty flags do not establish family relationships or involvement in a project.',
          'rows':rows,'excludedPositionCounts':dict(rejected)}
 (OUT/'officials.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n')
 fields=['id','name','role','position','organization','region','province','municipality_city','year','verification']
 with (OUT/'officials.csv').open('w',newline='') as stream:
  writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows({k:r.get(k) for k in fields} for r in rows)
 db=sqlite3.connect(OUT/'officials.sqlite');db.execute('DROP TABLE IF EXISTS officials');db.execute('DROP TABLE IF EXISTS official_sources')
 db.execute('CREATE TABLE officials (id TEXT PRIMARY KEY,name TEXT,name_key TEXT,role TEXT,position TEXT,organization TEXT,region TEXT,province TEXT,municipality_city TEXT,year INTEGER)')
 db.execute('CREATE TABLE official_sources (official_id TEXT,source_kind TEXT,source_record_id TEXT,source_file TEXT,source_url TEXT)')
 for r in rows:
  db.execute('INSERT INTO officials VALUES (?,?,?,?,?,?,?,?,?,?)',tuple(r.get(k) for k in ('id','name','nameKey','role','position','organization','region','province','municipality_city','year')))
  for p in r['sources']:db.execute('INSERT INTO official_sources VALUES (?,?,?,?,?)',(r['id'],p['kind'],str(p['recordId']),p['file'],p['url']))
 db.execute('CREATE INDEX official_name_role ON officials(name_key,role)');db.commit();db.close()
 (OUT/'README.md').write_text('# Official designation evidence\n\nCaptured from ODV dynasty source exports and public API. Use officials.sqlite for queries, officials.csv for interchange, and officials.json for the signatory matcher. Every record preserves its source year; it is not a verified current roster. DE and ADE are separate. A name match provides designation context, not confirmation of document signature, council appointment, or project responsibility.\n\n'+json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary),flush=True)
 return payload
if __name__=='__main__':build()
