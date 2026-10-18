#!/usr/bin/env python3
"""Paced, resumable read-only archive of the user-selected ArcGIS directory."""
import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import gzip
import hashlib
import http.client
import json
import os
from pathlib import Path
import random
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE='https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services'
PRIORITY='Detailed_Bridge_Inventory_Final/FeatureServer/1'
ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT/'data_sources/arcgis_dpwh/archive'

@contextmanager
def download_slot():
    """Hard cap of two downloading workers, including manual launches."""
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    chosen=None
    for index in range(2):
        handle=(ARCHIVE/f'worker-slot-{index}.lock').open('a+')
        try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:handle.close();continue
        chosen=handle;break
    if chosen is None:raise RuntimeError('Both download slots are occupied. Use start_arcgis_downloads.py to queue selections.')
    try:yield
    finally:chosen.close()

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)
def read(path):return json.loads(path.read_text())
def safe(name):
    return ''.join(c if c.isalnum() or c in '-_.' else '_' for c in name).strip('.')[:160]+'-'+hashlib.sha256(name.encode()).hexdigest()[:8]

def reuse_layer_cache(root,path,relative):
    if (path/'metadata.json').exists():return
    if root!=ARCHIVE and root.parent!=ARCHIVE/'selected':return
    candidates=[ARCHIVE/'layers'/safe(relative)]+list((ARCHIVE/'selected').glob('*/layers/'+safe(relative)))
    for source in candidates:
        if source==path or not(source/'metadata.json').exists():continue
        for item in source.rglob('*'):
            if not item.is_file() or item.name.endswith('.tmp'):continue
            target=path/item.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():continue
            try:os.link(item,target)
            except OSError:shutil.copy2(item,target)
        break

class RemoteError(Exception):pass
class Unavailable(RemoteError):pass

class Downloader:
    def __init__(self,args):
        self.args=args;self.root=args.output;self.last=0
        self.status=read(self.root/'status.json') if (self.root/'status.json').exists() else {'startedAt':now(),'layers':{},'services':{}}
    def save(self):self.status['updatedAt']=now();write(self.root/'status.json',self.status)
    def log(self,message):print(now()+' '+message,flush=True)
    def open_paced(self,request):
        """Serialize and pace requests across all selected-feature workers."""
        ARCHIVE.mkdir(parents=True,exist_ok=True)
        with (ARCHIVE/'network.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            stamp=ARCHIVE/'last_request.txt'
            previous=float(stamp.read_text()) if stamp.exists() else 0
            time.sleep(max(0,min(self.args.delay,self.args.delay-(time.time()-previous))))
            try:
                with urllib.request.urlopen(request,timeout=90) as response:
                    raw=response.read()
                    return gzip.decompress(raw) if 'gzip' in response.headers.get('Content-Encoding','').lower() else raw
            finally:stamp.write_text(str(time.time()))
    def request(self,url,params=None,binary=False):
        if not url.startswith(BASE+'/') and url!=BASE:raise ValueError('URL outside authorized directory')
        query=urllib.parse.urlencode(params or {})
        target=url+('?' +query if query else '')
        for attempt in range(7):
            time.sleep(max(0,self.last+self.args.delay-time.monotonic()))
            if shutil.disk_usage(self.root).free<2*1024**3:raise OSError('Less than 2 GiB free; resume after freeing disk space')
            self.last=time.monotonic()
            try:
                request=urllib.request.Request(target,headers={'User-Agent':'NEP-local-public-data-archive/1.0','Accept':'*/*' if binary else 'application/json','Accept-Encoding':'gzip'})
                raw=self.open_paced(request)
                with (self.root/'requests.jsonl').open('a') as f:
                    f.write(json.dumps({'at':now(),'url':target,'bytes':len(raw)})+'\n')
                if binary:return raw
                data=json.loads(raw)
                if 'error' in data:
                    code=data['error'].get('code');message=str(data['error'])
                    if code in [401,403,404,498,499]:raise Unavailable(message)
                    raise RemoteError(message)
                return data
            except Unavailable:raise
            except (urllib.error.URLError,TimeoutError,RemoteError,json.JSONDecodeError,http.client.IncompleteRead,ConnectionError,EOFError) as error:
                if isinstance(error,urllib.error.HTTPError) and error.code in [401,403,404]:raise Unavailable(str(error))
                if params and ',' in str(params.get('objectIds','')) and isinstance(error,(urllib.error.URLError,TimeoutError,http.client.IncompleteRead,ConnectionError,EOFError)):
                    raise
                if attempt==6:raise
                retry_after=error.headers.get('Retry-After','') if isinstance(error,urllib.error.HTTPError) else ''
                wait=min(300,float(retry_after)) if retry_after.isdigit() else min(60,2**(attempt+1))+random.random()
                self.log(f'Retry {attempt+1}: {url}: {error}; backing off {wait:.1f}s');time.sleep(wait)
    def cached(self,url,path):
        if path.exists():return read(path)
        data=self.request(url,{'f':'json'});write(path,data);return data
    def features(self,url,ids,oid,geometry):
        try:
            result=self.request(url+'/query',{'f':'json','objectIds':','.join(map(str,ids)),'outFields':'*','returnGeometry':str(geometry).lower(),'returnZ':'true','returnM':'true'})
        except (urllib.error.URLError,TimeoutError,http.client.IncompleteRead,ConnectionError,EOFError) as error:
            if isinstance(error,Unavailable) or len(ids)<=1:raise
            self.log(f'Splitting interrupted batch of {len(ids)} IDs into smaller requests')
            n=len(ids)//2
            return self.features(url,ids[:n],oid,geometry)+self.features(url,ids[n:],oid,geometry)
        records=result.get('features',[]);found=[r.get('attributes',{}).get(oid) for r in records]
        if result.get('exceededTransferLimit') or set(found)!=set(ids) or len(found)!=len(ids):
            if len(ids)>1:
                n=len(ids)//2
                return self.features(url,ids[:n],oid,geometry)+self.features(url,ids[n:],oid,geometry)
            raise RemoteError(f'ID {ids[0]} not returned exactly once; source may have changed')
        return records
    def attachments(self,url,path,ids):
        for oid in ids:
            directory=path/'attachments'/str(oid);listing=directory/'index.json'
            if not listing.exists():write(listing,self.request(url+'/'+str(oid)+'/attachments',{'f':'json'}))
            for info in read(listing).get('attachmentInfos',[]):
                aid=info['id'];name=str(aid)+'-'+safe(info.get('name','attachment'))
                target=directory/name
                if target.exists():continue
                body=self.request(url+'/'+str(oid)+'/attachments/'+str(aid),binary=True)
                tmp=target.with_name(target.name+'.tmp');tmp.write_bytes(body);tmp.replace(target)
    def layer(self,relative):
        if self.status['layers'].get(relative,{}).get('state')=='complete':return
        url=BASE+'/'+urllib.parse.quote(relative,safe='/');path=self.root/'layers'/safe(relative)
        reuse_layer_cache(self.root,path,relative)
        self.status['activeLayer']=relative;self.status['layers'][relative]={'state':'downloading','path':str(path.relative_to(self.root))};self.save()
        try:
            meta=self.cached(url,path/'metadata.json')
            if meta.get('type')=='Group Layer':
                self.status['layers'][relative].update(state='group-layer',name=meta.get('name'));self.save();return
            ids_path=path/'object_ids.json'
            if not ids_path.exists():
                snapshot=self.request(url+'/query',{'f':'json','where':'1=1','returnIdsOnly':'true'})
                if 'objectIds' not in snapshot:raise RemoteError('Query did not provide an object-ID snapshot')
                snapshot['objectIds']=sorted(snapshot['objectIds'] or []);snapshot['capturedAt']=now();write(ids_path,snapshot)
            snapshot=read(ids_path);ids=snapshot['objectIds']
            oid=snapshot.get('objectIdFieldName') or meta.get('objectIdField') or next((f['name'] for f in meta.get('fields',[]) if f['type']=='esriFieldTypeOID'),None)
            if not oid:raise RemoteError('Object-ID field not identified')
            count_path=path/'count_at_start.json'
            if not count_path.exists():write(count_path,self.request(url+'/query',{'f':'json','where':'1=1','returnCountOnly':'true'}))
            batch=min(self.args.batch_size,int(meta.get('maxRecordCount') or self.args.batch_size));seen=set();parts=[]
            if meta.get('geometryType')=='esriGeometryPolygon':batch=min(batch,10)
            start=0
            self.status['layers'][relative].update(name=meta.get('name'),downloaded=0,expected=len(ids),requestBatchSize=batch);self.save()
            while start<len(ids):
                subset=ids[start:start+batch];part=path/'batches'/f'{start:010d}.json.gz';part.parent.mkdir(parents=True,exist_ok=True)
                if part.exists():
                    with gzip.open(part,'rt') as f:records=json.load(f)
                    subset=ids[start:start+len(records)]
                    if not records:raise RemoteError('Empty cached batch cannot advance snapshot')
                    if {r['attributes'][oid] for r in records}!=set(subset):raise RemoteError('Cached batch IDs disagree with snapshot')
                else:
                    self.log(f'Fetching {relative}: snapshot positions {start+1}–{start+len(subset)}')
                    records=self.features(url,subset,oid,bool(meta.get('geometryType')))
                    tmp=part.with_name(part.name+'.tmp')
                    with gzip.open(tmp,'wt',encoding='utf-8') as f:json.dump(records,f,ensure_ascii=False)
                    tmp.replace(part)
                found=[r['attributes'][oid] for r in records]
                if len(found)!=len(set(found)) or seen.intersection(found):raise RemoteError('Duplicate IDs in archive')
                seen.update(found);parts.append(part)
                self.status['layers'][relative].update(name=meta.get('name'),downloaded=len(seen),expected=len(ids));self.save()
                self.log(f'{relative}: {len(seen):,}/{len(ids):,} records')
                start+=len(records)
            if seen!=set(ids):raise RemoteError('Final ID coverage mismatch')
            # Stream exports, retaining native coordinates and original field values.
            jsonl=path/'features.jsonl';esri=path/'features.esrijson'
            jt=jsonl.with_suffix('.jsonl.tmp');et=esri.with_suffix('.esrijson.tmp')
            header={k:meta[k] for k in ['geometryType','spatialReference','fields','hasZ','hasM'] if k in meta}
            if 'spatialReference' not in header and meta.get('extent',{}).get('spatialReference'):header['spatialReference']=meta['extent']['spatialReference']
            header['objectIdFieldName']=oid
            with jt.open('w') as lines,et.open('w') as feature_set:
                feature_set.write(json.dumps(header,ensure_ascii=False)[:-1]+',"features":[');first=True
                for part in parts:
                    with gzip.open(part,'rt') as f:records=json.load(f)
                    for record in records:
                        text=json.dumps(record,ensure_ascii=False);lines.write(text+'\n');feature_set.write(('' if first else ',')+text);first=False
                feature_set.write(']}\n')
            jt.replace(jsonl);et.replace(esri)
            if meta.get('hasAttachments'):self.attachments(url,path,ids)
            end=self.request(url,{'f':'json'});write(path/'metadata_at_end.json',end)
            end_count=self.request(url+'/query',{'f':'json','where':'1=1','returnCountOnly':'true'});write(path/'count_at_end.json',end_count)
            manifest={'url':url,'completedAt':now(),'records':len(seen),'snapshotAt':snapshot.get('capturedAt'),'objectIdField':oid,
                'sourceCountAtStart':read(count_path).get('count'),'sourceCountAtEnd':end_count.get('count'),
                'editingInfoAtStart':meta.get('editingInfo'),'editingInfoAtEnd':end.get('editingInfo'),
                'sourceChangedDuringDownload':meta.get('editingInfo')!=end.get('editingInfo') or len(ids)!=end_count.get('count'),
                'nativeSpatialReference':header.get('spatialReference'),'attachmentsRequested':bool(meta.get('hasAttachments')),
                'sha256':{p.name:hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in [jsonl,esri]}}
            write(path/'manifest.json',manifest)
            self.status['layers'][relative].update(state='complete',downloaded=len(seen),expected=len(ids),sourceChangedDuringDownload=manifest['sourceChangedDuringDownload']);self.save()
            self.log(f'COMPLETE {relative}: {len(seen):,} records')
        except (Unavailable,RemoteError,urllib.error.URLError,ValueError,KeyError) as error:
            state='unavailable' if isinstance(error,Unavailable) else 'failed'
            self.status['layers'][relative].update(state=state,error=str(error));self.save();self.log(f'{state.upper()} {relative}: {error}')
    def run(self):
        self.layer(PRIORITY)
        if self.args.mode=='priority':return
        catalog=self.cached(BASE,self.root/'catalog.json');services=list(catalog.get('services',[]))
        folders=list(catalog.get('folders',[]))
        while folders:
            folder=folders.pop(0);data=self.cached(BASE+'/'+urllib.parse.quote(folder,safe='/'),self.root/'folders'/ (safe(folder)+'.json'))
            services.extend(data.get('services',[]));folders.extend(data.get('folders',[]))
        self.status['catalogServices']=len(services);self.save()
        services.sort(key=lambda r:(not r['name'].startswith('Detailed_Bridge_Inventory_Final'),r['name']))
        for service in services:
            relative=service['name']+'/'+service['type']
            try:
                meta=self.cached(BASE+'/'+urllib.parse.quote(relative,safe='/'),self.root/'services'/(safe(relative)+'.json'))
                self.status['services'][relative]={'state':'cataloged','layers':len(meta.get('layers',[])),'tables':len(meta.get('tables',[]))};self.save()
                for layer in meta.get('layers',[])+meta.get('tables',[]):self.layer(relative+'/'+str(layer['id']))
            except (Unavailable,RemoteError,urllib.error.URLError,ValueError) as error:
                self.status['services'][relative]={'state':'unavailable','error':str(error)};self.save();self.log(f'SERVICE UNAVAILABLE {relative}: {error}')
        self.status['finishedAt']=now();self.status.pop('activeLayer',None);self.save();self.log('Catalog traversal finished; inspect status.json for failed/unavailable layers')

    def service(self,relative):
        url=BASE+'/'+urllib.parse.quote(relative,safe='/')
        meta=self.cached(url,self.root/'services'/(safe(relative)+'.json'))
        self.status['services'][relative]={'state':'cataloged','layers':len(meta.get('layers',[])),'tables':len(meta.get('tables',[]))};self.save()
        for layer in meta.get('layers',[])+meta.get('tables',[]):self.layer(relative+'/'+str(layer['id']))
        self.status['services'][relative]['state']='visited';self.save()

def main(selected_layer=None,profile=None,selected_service=None):
    selected=selected_layer or selected_service
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',nargs='?',default='priority',choices=['priority','status'] if selected else ['priority','all','status'])
    parser.add_argument('--delay',type=float,default=3);parser.add_argument('--batch-size',type=int,default=200);parser.add_argument('--output',type=Path,default=ARCHIVE/'selected'/profile if profile else ARCHIVE)
    args=parser.parse_args()
    if args.mode=='all':parser.error('Whole-catalog downloads are disabled by the selected-only collection policy. Use start_arcgis_downloads.py.')
    if args.mode=='status':
        status=read(args.output/'status.json') if (args.output/'status.json').exists() else {}
        print(json.dumps(status,indent=2));return
    if args.delay<1 or not 1<=args.batch_size<=1000:parser.error('Use delay >=1 second and batch size 1–1000')
    args.output.mkdir(parents=True,exist_ok=True)
    with download_slot(), (args.output/'download.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:parser.error('Another downloader already holds this archive lock')
        (args.output/'worker.pid').write_text(str(os.getpid())+'\n')
        downloader=Downloader(args)
        downloader.status.pop('finishedAt',None);downloader.status.pop('workerError',None)
        try:
            if selected:
                if selected_layer:downloader.layer(selected_layer)
                else:downloader.service(selected_service)
                downloader.status.pop('activeLayer',None);downloader.status['finishedAt']=now();downloader.save()
            else:downloader.run()
        except KeyboardInterrupt:downloader.status['interruptedAt']=now();downloader.save();downloader.log('Interrupted; cached batches retained')
        except Exception as error:downloader.status['workerError']=str(error);downloader.save();raise

if __name__=='__main__':main()
