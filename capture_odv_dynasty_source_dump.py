"""Capture public official fields from ODV's local PostgreSQL source dump."""
import csv,gzip,hashlib,json,re,subprocess
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'open-data-visualization/database/dynasty_dump.sql.gz'
OUT=ROOT/'data_sources/odv_dynasty'
FIELDS=['id','first_name','middle_name','last_name','suffix','nickname','position','year','fat','region','province','municipality_city','district','party','government_branch','position_category','appointment_type','government_level','department','organization','winner']
def decode(value):
 if value=='\\N':return ''
 return re.sub(r'\\([\\tnr])',lambda m:{'\\':'\\','t':'\t','n':'\n','r':'\r'}[m[1]],value)
def main():
 OUT.mkdir(parents=True,exist_ok=True);active=False;count=0
 target=OUT/'source_officials.csv.gz'
 with gzip.open(SOURCE,'rt',encoding='utf-8') as stream,gzip.open(target,'wt',encoding='utf-8',newline='') as output:
  writer=csv.writer(output);writer.writerow(FIELDS)
  for line in stream:
   if line.startswith('COPY ') and 'political_dynasties (' in line:
    columns=[v.strip().strip('"') for v in line.partition('(')[2].partition(') FROM')[0].split(',')];indices=[columns.index(k) for k in FIELDS];active=True;continue
   if not active:continue
   if line.rstrip('\n')=='\\.':break
   values=line.rstrip('\n').split('\t');writer.writerow([decode(values[i]) for i in indices]);count+=1
 parquet=OUT/'source_officials.parquet'
 sql=f"COPY (SELECT * FROM read_csv('{target.as_posix()}',header=true,all_varchar=true)) TO '{parquet.as_posix()}' (FORMAT PARQUET,COMPRESSION ZSTD)"
 subprocess.run(['duckdb','-c',sql],check=True,capture_output=True)
 manifest={'capturedAtUtc':datetime.now(timezone.utc).isoformat(),'sourceTable':'PostgreSQL public.political_dynasties','sourceDump':'open-data-visualization/database/dynasty_dump.sql.gz','sourceDumpSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'sourcePage':'https://research.bettergov.ph/dynasty#table','records':count,'fields':FIELDS,'files':{p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [target,parquet]},'scope':'All positions in the source table. Only whitelisted public official/designation fields are captured. Source years and winner flags are preserved as source claims; no current tenure is inferred.'}
 (OUT/'source-table-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'sourceRows':count,'files':manifest['files']}),flush=True)
if __name__=='__main__':main()
