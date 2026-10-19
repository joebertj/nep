#!/usr/bin/env python3
"""Sequential, resumable POW/RDC/photo cache on external storage; tables retain source links."""
import fcntl,json,os,time
from pathlib import Path
from storage.external_storage import BASE,guard
# Set before service import so all metadata, PDFs, OCR and parsed results stay external.
guard()
# Curl was verified with the PH VPN; retain standard certificate verification.
os.environ['DPWH_DOCUMENT_TRANSPORT']='curl'
os.environ['DPWH_DOCUMENT_CACHE_PHOTOS']='1'
os.environ['DPWH_EXTERNAL_VOLUME']='/Volumes/T5 EVO'
os.environ['DPWH_DOCUMENT_CACHE']=str(BASE/'nep/data_sources/dpwh_project_documents/on_demand')
from project_documents.service import CACHE,JOBS,process,save

def document_complete(document):
    if document.get('status')=='available':return True
    if document.get('status')!='link_only':return False
    if document.get('kind')!='photos':return True
    # Keep retrying link-only photo attachments when external caching is
    # enabled; successful raw downloads are marked available.
    return os.environ.get('DPWH_DOCUMENT_CACHE_PHOTOS')!='1'

def main():
    guard();root=CACHE.parent;root.mkdir(parents=True,exist_ok=True)
    with (root/'queue.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        queue=json.loads((root/'queue.json').read_text())['projects']
        statusfile=root/'queue-status.json';status={'total':len(queue),'processed':0,'skipped':0,'errors':0,'startedAt':time.time(),'complete':False}
        failure_streak=0
        for entry in queue:
            guard();code=entry['projectCode'];status['current']=code
            cached=CACHE/code/'result.json'
            if cached.exists():
                result=json.loads(cached.read_text())
                if result.get('documents') and all(document_complete(d) for d in result.get('documents',[])):
                    status['skipped']+=1;save(statusfile,status);continue
            save(statusfile,status);process(code)
            status['processed']+=1
            if JOBS.get(code,{}).get('hasErrors') or JOBS.get(code,{}).get('status')=='error':status['errors']+=1
            result=json.loads(cached.read_text()) if cached.exists() else {}
            failed=[d for d in result.get('documents',[]) if d['status'] not in ('available','link_only')]
            failure_streak=failure_streak+1 if failed or JOBS.get(code,{}).get('status')=='error' else 0
            rate_limited=any('HTTP 429' in d.get('error','') for d in failed)
            if rate_limited or failure_streak>=3:
                status.update(paused=True,reason='HTTP 429 rate limit' if rate_limited else 'Three consecutive project failures; inspect document errors before resuming')
                save(statusfile,status);print(json.dumps(status),flush=True);return
            save(statusfile,status);print(json.dumps(status),flush=True);time.sleep(3)
        status.update(complete=True,finishedAt=time.time(),current=None);save(statusfile,status)
if __name__=='__main__':main()
