#!/usr/bin/env python3
"""Continuously refresh the indexed DPWH project queue and fetch newly listed documents."""
import argparse,fcntl,json,os,time
from pathlib import Path
from storage.external_storage import BASE,guard
# Set before service import so all metadata, PDFs, OCR and parsed results stay external.
guard()
# Curl was verified with the PH VPN; retain standard certificate verification.
os.environ['DPWH_DOCUMENT_TRANSPORT']='curl'
os.environ['DPWH_DOCUMENT_CACHE_PHOTOS']='1'
os.environ['DPWH_EXTERNAL_VOLUME']='/Volumes/T5 EVO'
os.environ['DPWH_DOCUMENT_CACHE']=str(BASE/'nep/data_sources/dpwh_project_documents/on_demand')
from project_documents.service import CACHE,JOBS,kinds,metadata,process,save

def document_complete(document):
    if document.get('status')=='available':return True
    if document.get('status')!='link_only':return False
    if document.get('kind')!='photos':return True
    # Keep retrying link-only photo attachments when external caching is
    # enabled; successful raw downloads are marked available.
    return os.environ.get('DPWH_DOCUMENT_CACHE_PHOTOS')!='1'

def documents_match(project, result):
    """True when the cached result represents the project's latest selected links."""
    expected=[d for d in project.get('documents',[]) if kinds(d) and
              (kinds(d)!='photos' or os.environ.get('DPWH_DOCUMENT_CACHE_PHOTOS')=='1')]
    actual=[d.get('metadata') for d in result.get('documents',[])]
    return expected==actual and len(expected)==len(result.get('documents',[]))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval-hours',type=float,default=6,
                        help='wait this many hours after each full metadata refresh (default: 6)')
    args=parser.parse_args()
    if args.interval_hours<0.1:parser.error('--interval-hours must be at least 0.1')
    guard();root=CACHE.parent;root.mkdir(parents=True,exist_ok=True)
    with (root/'queue.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        statusfile=root/'queue-status.json';started=time.time();cycle=0
        while True:
            guard();cycle+=1
            queue=json.loads((root/'queue.json').read_text())['projects']
            status={'total':len(queue),'processed':0,'skipped':0,'errors':0,
                    'startedAt':started,'cycle':cycle,'cycleStartedAt':time.time(),
                    'complete':False,'looping':True,'intervalHours':args.interval_hours}
            failure_streak=0;rate_limited=False
            for entry in queue:
                guard();code=entry['projectCode'];status['current']=code;save(statusfile,status)
                try:
                    # Always refresh the project metadata before deciding whether its
                    # selected document links changed since the previous cycle.
                    project=metadata(code,refresh=True)
                    cached=CACHE/code/'result.json'
                    result=json.loads(cached.read_text()) if cached.exists() else None
                    if result and documents_match(project,result) and all(document_complete(d) for d in result.get('documents',[])):
                        status['skipped']+=1;failure_streak=0;save(statusfile,status)
                        print(json.dumps(status),flush=True);time.sleep(1);continue
                    process(code)
                    status['processed']+=1
                    result=json.loads(cached.read_text()) if cached.exists() else {}
                    failed=[d for d in result.get('documents',[]) if d['status'] not in ('available','link_only')]
                    job=JOBS.get(code,{})
                    has_error=bool(failed or job.get('status')=='error' or job.get('hasErrors'))
                    if has_error:
                        status['errors']+=1;failure_streak+=1
                    else:failure_streak=0
                    rate_limited=any('HTTP 429' in d.get('error','') for d in failed) or 'HTTP 429' in str(job.get('error',''))
                except Exception as exc:
                    status['errors']+=1;failure_streak+=1
                    rate_limited='HTTP 429' in str(exc)
                    status['lastError']=type(exc).__name__+': '+str(exc)[:220]
                status['consecutiveFailures']=failure_streak;status['rateLimited']=rate_limited
                save(statusfile,status);print(json.dumps(status),flush=True)
                if rate_limited or failure_streak>=3:
                    status['cycleStoppedEarly']=True
                    status['reason']='HTTP 429 rate limit' if rate_limited else 'Three consecutive project failures; inspect source errors before next cycle'
                    break
                time.sleep(3)
            status['current']=None;status['cycleCompletedAt']=time.time()
            status['nextCycleAt']=status['cycleCompletedAt']+args.interval_hours*3600
            status['complete']=False;status['looping']=True;save(statusfile,status)
            print(json.dumps(status),flush=True)
            # A later cycle starts from the beginning, including after a short failure
            # streak, so transient portal or file-host issues are retried resumably.
            time.sleep(max(60,args.interval_hours*3600))
if __name__=='__main__':main()
