"""Capture every page exposed by ODV's public officials table, with checkpoints."""
import concurrent.futures,hashlib,json,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'data_sources/odv_dynasty'
BASE='https://research.bettergov.ph/api/dynasty?limit=1000&page='
def fetch(page):
 target=OUT/f'all-page-{page:03d}.json'
 if target.exists():
  data=json.loads(target.read_text())
 else:
  part=target.with_suffix('.part')
  subprocess.run(['curl','--fail','--silent','--show-error','--location','--retry','3','--max-time','120',BASE+str(page),'-o',str(part)],check=True)
  data=json.loads(part.read_text())
  if not data.get('success'):raise RuntimeError('API returned an error')
  part.replace(target)
 return target,data

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 first,data=fetch(1);pages=data['pagination']['total_pages'];total=data['pagination']['total_count']
 records=[];ids=set();files=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  for index,(path,doc) in enumerate(pool.map(fetch,range(1,pages+1)),1):
   rows=doc['data'];records.extend(rows);ids.update(r['id'] for r in rows)
   files.append({'path':path.name,'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
   if index%25==0:print('pages',index,'/',pages,flush=True)
 result={'capturedAtUtc':datetime.now(timezone.utc).isoformat(),'sourceUrl':BASE+'1','page':'https://research.bettergov.ph/dynasty#table','reportedRows':total,'capturedRows':len(records),'uniqueSourceIds':len(ids),'pages':pages,'files':files,'limits':'The public API has an elected/BAC/engineer display filter and offset pagination. This captures the table exposed by that API; the local full Parquet snapshot also preserves other source roles. Source years are not verified term intervals.'}
 (OUT/'all-roles-manifest.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:result[k] for k in ['reportedRows','capturedRows','uniqueSourceIds','pages']}),flush=True)
if __name__=='__main__':main()
