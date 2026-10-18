#!/usr/bin/env python3
"""Snapshot the linked analyst's current JSON, source methods and application views.
Does not execute downloaded code or modify the local production analysis.
"""
import argparse, concurrent.futures, hashlib, json, time, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data_sources/csiiiv'
REPO='csiiiv/DPWH-NEP-HB-2027-ANALYSIS'
def request(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BetterGov-source-review/1.0'}),timeout=120) as response:return response.read()
        except Exception:
            if attempt==3:raise
            time.sleep(2*(attempt+1))
def selected(path):
    if '/archive/' in path or '.test.' in path:return False
    if path in ['README.md','analysis/README.md','scripts/build_pages.py']:return True
    if path.startswith('analysis/docs/') and path.endswith('.md'):return True
    if path.startswith('analysis/builders/') and path.endswith('.py'):return True
    if path.startswith('analysis/web/src/') and path.endswith(('.jsx','.js')):return True
    if path.endswith('.json') and any(path.startswith(prefix) for prefix in ['analysis/data/','analysis-nia/data/','analysis-hfep/data/','other-analysis/data/','gps-analysis/data/']):
        return '/shareable/' not in path and not path.endswith('hb_dpwh_leaves_corrected_v5.json')
    return path.endswith('.md') and any(path.startswith(prefix) for prefix in ['analysis-nia/','analysis-hfep/','other-analysis/','gps-analysis/'])
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tree',type=Path);args=parser.parse_args()
    BASE.mkdir(exist_ok=True,parents=True)
    tree=json.loads(args.tree.read_text()) if args.tree else json.loads(request(f'https://api.github.com/repos/{REPO}/git/trees/HEAD?recursive=1'))
    previous=json.loads((BASE/'manifest.json').read_text()) if (BASE/'manifest.json').exists() else {}
    if tree.get('truncated'):raise ValueError('Incomplete GitHub tree')
    commit=tree['sha'];target=BASE/'snapshots'/commit;target.mkdir(parents=True,exist_ok=True)
    (target/'github-tree.json').write_text(json.dumps(tree,indent=2)+'\n')
    entries=[e for e in tree['tree'] if e['type']=='blob' and selected(e['path'])]
    cached={r['repositoryPath']:r for r in previous.get('files',[]) if r.get('localPath')}
    existing={}
    for folder in [ROOT/'analysis_output',ROOT/'data_sources/fmr_analyst']:
        for p in folder.glob('*.json'):existing.setdefault(p.name,[]).append(p)
    def download(entry):
        path=entry['path'];size=entry.get('size',0);url=f'https://raw.githubusercontent.com/{REPO}/{commit}/{path}'
        record={'repositoryPath':path,'gitBlobSha':entry['sha'],'sizeBytes':size,'sourceUrl':url}
        if size>100_000_000:return {**record,'status':'deferred-over-100MB'}
        dest=target/path
        prior=cached.get(path)
        candidates=[dest]+([ROOT/prior['localPath']] if prior and prior.get('gitBlobSha')==entry['sha'] else [])+existing.get(Path(path).name,[])
        for candidate in candidates:
            if candidate.exists() and candidate.stat().st_size==size:
                raw=candidate.read_bytes()
                if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()==entry['sha']:
                    return {**record,'status':'already-present','localPath':str(candidate.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest()}
        raw=request(url)
        if hashlib.sha1(f'blob {len(raw)}\0'.encode()+raw).hexdigest()!=entry['sha']:raise ValueError(f'Git blob checksum mismatch: {path}')
        if path.endswith('.json'):json.loads(raw)
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        return {**record,'status':'downloaded','localPath':str(dest.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest()}
    records=[]
    print(f'Pinned commit {commit}: {len(entries)} selected current files, {sum(e.get("size",0) for e in entries)/1e6:.1f} MB; at most two downloads concurrently.',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(download,e):e for e in entries}
        for future in concurrent.futures.as_completed(futures):
            e=futures[future]
            try:records.append(future.result())
            except Exception as exc:records.append({'repositoryPath':e['path'],'status':'error','error':str(exc)})
            if len(records)%20==0:print(f'{len(records)}/{len(entries)} files processed',flush=True)
    manifest={'repository':'https://github.com/'+REPO,'website':'https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#overview','commit':commit,'retrievedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'Current JSON and source methods/views; no PDFs, Git history, superseded archives or execution of downloaded code. Existing byte-identical local files referenced instead of duplicated.','files':sorted(records,key=lambda r:r['repositoryPath'])}
    old={r['repositoryPath']:r for r in previous.get('files',[])}
    new={r['repositoryPath']:r for r in records}
    changed=[{'path':k,'change':'added' if k not in old else 'changed','previousGitBlobSha':old.get(k,{}).get('gitBlobSha'),'gitBlobSha':r.get('gitBlobSha')} for k,r in new.items() if k not in old or r.get('gitBlobSha')!=old[k].get('gitBlobSha')]
    changed += [{'path':k,'change':'removed','previousGitBlobSha':r.get('gitBlobSha')} for k,r in old.items() if k not in new]
    manifest['previousCommit']=previous.get('commit')
    manifest['changes']=changed
    def affected(path):
        if path.startswith('analysis-nia/'):return ['nia-irrigation.html','nia.html','summary.html']
        if path.startswith('analysis-hfep/'):return ['hfep.html','summary.html']
        if path.startswith('other-analysis/'):return ['fmr.html','cost-per-km.html','cost-matching.html','repeats.html','summary.html']
        if 'chainage' in path:return ['repeats.html','cost-per-km.html','cost-matching.html']
        if path.startswith('gps-analysis/'):return ['congress.html','cost-matching.html','mpb.html']
        return ['dpwh.html','dpwh-hgab.html','dpwh-hgab-comparison.html','congress.html','summary.html']
    manifest['potentiallyAffectedPages']=sorted({page for change in changed for page in affected(change['path'])})
    serialized=json.dumps(manifest,indent=2)+'\n'
    # Keep the last complete snapshot active if a request failed.
    history=BASE/'manifests';history.mkdir(exist_ok=True)
    (history/(commit+('-incomplete' if any(r['status']=='error' for r in records) else '')+'.json')).write_text(serialized)
    if not any(r['status']=='error' for r in records):
        temporary=BASE/'manifest.json.tmp';temporary.write_text(serialized);temporary.replace(BASE/'manifest.json')
    print(json.dumps({'files':len(records),'downloaded':sum(r['status']=='downloaded' for r in records),'alreadyPresent':sum(r['status']=='already-present' for r in records),'errors':[r for r in records if r['status']=='error']},indent=2),flush=True)
    if any(r['status']=='error' for r in records):raise SystemExit(1)
if __name__=='__main__':main()
