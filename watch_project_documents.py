#!/usr/bin/env python3
"""Watch external cached PDFs, enrich parsed evidence, and publish DPWH Indepth.
No network requests, Git commands or deployment. Photos stay source links.
"""
import argparse,fcntl,hashlib,json,os,time,importlib
from pathlib import Path
from storage.external_storage import BASE,guard
ROOT=Path(__file__).resolve().parent
CACHE=BASE/'nep/data_sources/dpwh_project_documents/on_demand'
STATE=CACHE.parent/'watcher-state.json'

def read(path,default):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return default

def save(path,data):
    guard();temp=path.with_name(path.name+'.watcher.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

def stamp(path):
    stat=path.stat();return [stat.st_size,stat.st_mtime_ns]

def digest(path):
    result=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):result.update(chunk)
    return result.hexdigest()

def parser_version():
    return hashlib.sha256(b''.join((ROOT/'project_documents'/name).read_bytes() for name in ('pow.py','signatories.py'))).hexdigest()

def active_project():
    # Compatibility with the already-running downloader, started before cache locks.
    jobs=read(BASE/'jobs/processes.json',[])
    for job in jobs:
        if job['name']!='pow-rdc-download':continue
        try:os.kill(job['pid'],0)
        except (ProcessLookupError,PermissionError):continue
        queue=read(CACHE.parent/'queue-status.json',{})
        if not queue.get('complete') and not queue.get('paused'):return queue.get('current')
    return None

def scan(state):
    from project_documents.cache_lock import project_lock
    from project_documents import pow as pow_parser,signatories
    version=parser_version()
    if state.get('loadedParserVersion')!=version:
        importlib.reload(pow_parser);importlib.reload(signatories);state['loadedParserVersion']=version
    parse_pdf=pow_parser.parse_pdf;extract=signatories.extract
    active=active_project();changed=0;reused=0;failed=0;busy=0
    ledger=state.setdefault('pdfs',{})
    for metadata_path in sorted(CACHE.glob('*/metadata.json')):
        guard();folder=metadata_path.parent;code=folder.name
        if code==active:busy+=1;continue
        metadata=read(metadata_path,{})
        if not metadata.get('code')==code:continue
        from project_documents.service import kinds
        candidates=[]
        for document in metadata.get('documents',[]):
            kind=kinds(document)
            if not kind or kind=='photos':continue
            asset_version=hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest()[:16]
            pdf=folder/'assets'/asset_version/(kind+'.pdf')
            if pdf.is_file() and not pdf.is_symlink():candidates.append((document,kind,asset_version,pdf))
        if not candidates:continue
        try:
            with project_lock(folder,blocking=False):
                result_path=folder/'result.json';original_stamp=stamp(result_path) if result_path.exists() else None
                result=read(result_path,{'projectCode':code,'documents':[]})
                changed_result=False
                for document,kind,asset_version,pdf in candidates:
                    key=str(pdf.relative_to(CACHE));signature=[*stamp(pdf),version]
                    previous=ledger.get(key,{})
                    if previous.get('signature')==signature:continue
                    old=next((d for d in result.get('documents',[]) if d.get('kind')==kind and d.get('metadata',{}).get('id')==document.get('id')),None)
                    sha=digest(pdf)
                    # Reuse completed downloader output, including an honest zero-row extraction.
                    reusable=old and old.get('sha256')==sha and old.get('status')=='available' and (kind=='photos' or ('pow' in old and 'signatories' in old if kind=='pow' else 'signatories' in old))
                    force=bool(previous and previous.get('signature',[])[-1:]!=[version])
                    if reusable and not force:
                        ledger[key]={'signature':signature,'sha256':sha,'status':'reused_downloader_result'};reused+=1;continue
                    try:
                        guard()
                        with pdf.open('rb') as stream:
                            if b'%PDF-' not in stream.read(1024):raise ValueError('Not a PDF')
                        if document.get('sizeBytes') is not None and pdf.stat().st_size!=document['sizeBytes']:raise ValueError('PDF byte count differs from metadata')
                        row={**(old or {}),'kind':kind,'metadata':document,'version':asset_version,'pdfAsset':asset_version+'/'+pdf.name,'sha256':sha,'parsedBy':'offline_watcher','parserVersion':version}
                        state['current']={'projectCode':code,'kind':kind};save(STATE,state)
                        if kind=='pow':
                            row['pow']=parse_pdf(pdf,pdf.parent,round(float(metadata['amount'])*1000))
                            row['signatories']=extract(pdf,'pow',pdf.parent)
                        elif kind=='rdc':row['signatories']=extract(pdf,'rdc',pdf.parent)
                        else:
                            row['directLink']=document['url'];row['displayPolicy']='direct_source_link; externally cached PDF only'
                        row['status']='available';row.pop('error',None)
                        result['documents']=[d for d in result.get('documents',[]) if not (d.get('kind')==kind and d.get('metadata',{}).get('id')==document.get('id'))]+[row]
                        ledger[key]={'signature':signature,'sha256':sha,'status':'parsed'};changed_result=True;changed+=1
                    except Exception as exc:
                        failed+=1;ledger[key]={'signature':signature,'sha256':sha,'status':'parse_error','error':type(exc).__name__+': '+str(exc)[:300]}
                if changed_result:
                    # Do not overwrite a result touched by an older, non-locking worker.
                    if (stamp(result_path) if result_path.exists() else None)!=original_stamp:
                        for _,_,_,pdf in candidates:ledger.pop(str(pdf.relative_to(CACHE)),None)
                        busy+=1;continue
                    result['updatedByWatcherAtUtc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                    save(result_path,result)
        except BlockingIOError:busy+=1
    state['current']=None
    return {'parsed':changed,'reused':reused,'parseErrors':failed,'busyProjects':busy}

def publication_signature():
    source=[(str(p.relative_to(ROOT)),stamp(p)) for p in [ROOT/'build_dpwh_indepth.py',ROOT/'uniform_report_menu.py',ROOT/'report_teasers.py',ROOT/'project_documents/indepth.html',ROOT/'project_documents/indepth.js',ROOT/'project_documents/pow_reviewed_category_totals.json']]
    results=[(str(p.relative_to(CACHE)),stamp(p)) for p in sorted(CACHE.glob('*/result.json'))]
    return hashlib.sha256(json.dumps([source,results]).encode()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--interval',type=int,default=30);parser.add_argument('--once',action='store_true');args=parser.parse_args()
    guard();CACHE.parent.mkdir(parents=True,exist_ok=True)
    with (CACHE.parent/'watcher.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=read(STATE,{'pdfs':{}})
        while True:
            guard();state.update(running=True,pid=os.getpid(),lastScanStarted=time.time())
            summary=scan(state);current=publication_signature()
            if current!=state.get('publicationSignature'):
                import build_dpwh_indepth
                importlib.reload(build_dpwh_indepth)
                state['publishedSummary']=build_dpwh_indepth.build();state['publicationSignature']=current;state['lastPublishedAt']=time.time()
            state.update(lastScanFinished=time.time(),lastScan=summary);save(STATE,state)
            print(json.dumps({k:v for k,v in state.items() if k!='pdfs'},ensure_ascii=False),flush=True)
            if args.once:break
            time.sleep(max(10,args.interval))
if __name__=='__main__':main()
