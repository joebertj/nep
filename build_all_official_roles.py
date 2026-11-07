"""Build a queryable all-role registry from the full ODV source and public captures."""
import json,subprocess,tempfile
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'data_sources/odv_dynasty'
OUT=ROOT/'data_sources/designation_registry'
FIELDS=['id','first_name','middle_name','last_name','suffix','nickname','position','year','fat','region','province','municipality_city','district','party','government_branch','position_category','appointment_type','government_level','department','organization','winner']
def sqlquote(value):return "'"+str(value).replace("'","''")+"'"
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='nep-officials-') as folder:
  api=Path(folder)/'api.jsonl';seen=set();n=0
  with api.open('w') as stream:
   for p in sorted(SOURCE.glob('*-page-*.json')):
    for row in json.loads(p.read_text()).get('data',[]):
     signature=json.dumps(row,sort_keys=True)
     if signature in seen:continue
     seen.add(signature)
     item={k:None if row.get(k) is None else str(row[k]) for k in FIELDS}
     item.update(source_kind='public_api',source_file=p.name)
     stream.write(json.dumps(item,ensure_ascii=False)+'\n');n+=1
  db=OUT/'all_official_roles.duckdb';parquet=OUT/'all_official_roles.parquet'
  columns=','.join('"'+k+'"' for k in FIELDS)
  types='{'+','.join(sqlquote(k)+':'+sqlquote('VARCHAR') for k in FIELDS+['source_kind','source_file'])+'}'
  priority="CASE source_kind WHEN 'public_api' THEN 0 WHEN 'source_dump' THEN 1 ELSE 2 END"
  priority_s=priority.replace('source_kind','s.source_kind')
  enrichment=','.join(f"arg_min(nullif(s.\"{key}\",''),concat({priority_s},s.source_file)) AS \"{key}\"" for key in FIELDS if key!='id')
  script=f"""CREATE OR REPLACE TABLE source_records AS
   SELECT {columns},'source_dump' AS source_kind,'source_officials.parquet' AS source_file FROM read_parquet({sqlquote(SOURCE/'source_officials.parquet')})
   UNION ALL BY NAME SELECT * FROM read_json({sqlquote(api)},format='newline_delimited',columns={types})
   UNION ALL BY NAME SELECT *, 'legacy_parquet' AS source_kind,'political_dynasties.parquet' AS source_file FROM read_parquet({sqlquote(SOURCE/'political_dynasties.parquet')});
   CREATE OR REPLACE TEMP TABLE preferred AS SELECT * EXCLUDE(source_rank) FROM (
    SELECT *,row_number() OVER(PARTITION BY id ORDER BY {priority},source_file) AS source_rank FROM source_records
   ) WHERE source_rank=1;
   CREATE OR REPLACE TABLE all_officials AS
    SELECT md5(concat(s.id,'|',upper(trim(coalesce(s.first_name,''))),'|',upper(trim(coalesce(s.last_name,''))))) AS registry_id,s.id,{enrichment},arg_min(s.source_kind,concat({priority_s},s.source_file)) AS source_kind,
           arg_min(s.source_file,concat({priority_s},s.source_file)) AS source_file
    FROM source_records s
    GROUP BY s.id,upper(trim(coalesce(s.first_name,''))),upper(trim(coalesce(s.last_name,'')));
   CREATE OR REPLACE TABLE source_identity_conflicts AS
    SELECT id,count(DISTINCT concat(upper(trim(coalesce(first_name,''))),'|',upper(trim(coalesce(last_name,''))))) AS name_variants
    FROM source_records GROUP BY id HAVING name_variants>1;
   ALTER TABLE all_officials ADD COLUMN has_identity_conflict BOOLEAN;
   UPDATE all_officials SET has_identity_conflict = id IN (SELECT id FROM source_identity_conflicts);
   COPY all_officials TO {sqlquote(parquet)} (FORMAT PARQUET,COMPRESSION ZSTD);
   CREATE OR REPLACE TABLE role_counts AS SELECT position,count(*) AS records FROM all_officials GROUP BY position;
   CHECKPOINT;"""
  result=subprocess.run(['duckdb',str(db),'-c',script],capture_output=True,text=True)
  if result.returncode:raise RuntimeError(result.stderr)
  summary=json.loads(subprocess.check_output(['duckdb','-readonly',str(db),'-json','-c','SELECT (SELECT count(*) FROM source_records) AS source_records,(SELECT count(*) FROM all_officials) AS official_role_records,(SELECT count(*) FROM role_counts) AS distinct_position_labels,(SELECT count(*) FROM source_identity_conflicts) AS source_ids_with_name_conflicts'],text=True))[0]
  manifest={'generatedAtUtc':datetime.now(timezone.utc).isoformat(),'sourceTable':'ODV dynasty.political_dynasties','sourcePage':'https://research.bettergov.ph/dynasty#table','sourceSnapshotRows':312761,'capturedApiDistinctRecords':n,**summary,'database':'all_official_roles.duckdb','table':'all_officials','provenanceTable':'source_records','interchange':'all_official_roles.parquet','sourceFields':FIELDS,'policy':'All politicians and original position labels retained. Source years, winner flags and designations are source claims. Non-empty public API fields take precedence only for the same source-table ID and matching first/last names. Changed names remain separate registry_id records with has_identity_conflict=true. All original snapshots remain in source_records; source_identity_conflicts lists conflicting IDs. No family relationships, current office or document signature are inferred. The Governor/Mayor/DE/ADE signatory matcher separately uses officials.json.'}
  (OUT/'all-roles-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
  (OUT/'README.md').write_text('# Official and designation database\n\nAll politicians and roles: query `all_official_roles.duckdb` (`all_officials`, `source_records`, `role_counts`) or `all_official_roles.parquet`. Original position labels, source years, locality and public organization fields are preserved.\n\nFor RDC/PDC/LDC and POW signatories, `officials.json`, `officials.csv` and `officials.sqlite` contain explicit Governor, Mayor, District Engineer and Assistant District Engineer designation candidates. These are historical source records, not current appointments or proof of a signature.\n\nSource capture: `../odv_dynasty/source-table-manifest.json` and the public API page snapshots. Private date-of-birth fields from the original SQL dump are excluded.\n\n'+json.dumps(summary,indent=2)+'\n')
  print(json.dumps(manifest),flush=True)
if __name__=='__main__':main()
