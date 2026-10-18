#!/usr/bin/env python3
"""Read-only reachability probe using the existing deployed host; no remote files."""
import json,re,shlex,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
script=(ROOT/'deployment/deploy_odv_git.sh').read_text()
def config(name):return re.search(r'^'+name+r'="\$\{[^:]+:-([^}]+)\}"',script,re.M)[1]
host=config('REMOTE_HOST');user=config('REMOTE_USER')
payload=json.loads((ROOT/'data_sources/dpwh_project_documents/manifest.json').read_text())
urls=[d['metadata']['url'] for r in payload['projects'].values() for d in r['documents']][:4]
remote='''import json,sys,urllib.request
out=[]
for url in json.load(sys.stdin):
 try:
  req=urllib.request.Request(url,headers={'Range':'bytes=0-1023','User-Agent':'BetterGov-document-probe/1.0'})
  with urllib.request.urlopen(req,timeout=20) as r:out.append({'url':url,'status':r.status,'contentType':r.headers.get('Content-Type'),'pdfHeader':r.read(1024).startswith(b'%PDF')})
 except Exception as e:out.append({'url':url,'error':str(e)})
print(json.dumps(out,indent=2))'''
r=subprocess.run(['ssh','-i',str(Path.home()/'.ssh/klti'),'-o','BatchMode=yes','-o','ConnectTimeout=10',user+'@'+host,'python3 -c '+shlex.quote(remote)],input=json.dumps(urls),text=True,capture_output=True)
print(re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b','[server address]',r.stdout+r.stderr));raise SystemExit(r.returncode)
