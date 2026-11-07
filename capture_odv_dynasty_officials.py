"""Capture public ODV official-role records and the local dynasty source export."""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlencode
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data_sources/odv_dynasty'
ODV=ROOT.parent/'open-data-visualization'
BASE='https://research.bettergov.ph/api/dynasty'

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 source=ODV/'data/parquet/political_dynasties.parquet'
 shutil.copy2(source,OUT/source.name)
 manifests=[]
 for position in ['governor','mayor','engineer']:
  rows=[];page=1
  while True:
   url=BASE+'?'+urlencode({'position':position,'limit':1000,'page':page})
   target=OUT/f'{position}-page-{page:03d}.json';part=target.with_suffix('.part')
   subprocess.run(['curl','--fail','--silent','--show-error','--location','--retry','3','--max-time','90',url,'-o',str(part)],check=True)
   data=json.loads(part.read_text())
   if not data.get('success'):raise RuntimeError(f'Public dynasty API failed for {position} page {page}')
   part.replace(target);rows.extend(data['data'])
   if not data['pagination'].get('has_next'):break
   page+=1;time.sleep(.25)
  if len(rows)!=data['pagination']['total_count']:raise RuntimeError('Pagination count mismatch')
  manifests.append({'filter':position,'records':len(rows),'pages':page,'url':BASE+'?'+urlencode({'position':position,'limit':1000})})
  print(position,len(rows),flush=True)
 files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(OUT.iterdir()) if p.suffix in ('.json','.parquet') and p.name!='manifest.json']
 manifest={'capturedAtUtc':datetime.now(timezone.utc).isoformat(),'page':'https://research.bettergov.ph/dynasty#table','localSource':'open-data-visualization/data/parquet/political_dynasties.parquet','tableSource':'visualization.py dynasty_data_api; PostgreSQL dynasty.political_dynasties','captures':manifests,'files':files,'limits':'API table applies its own elected/BAC/engineer position screen; local Parquet preserves additional source rows. Source years are historical records, not current appointment verification.'}
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
