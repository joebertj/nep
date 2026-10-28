#!/usr/bin/env python3
"""Resumably reparse every cached project POW with the current parser."""
import hashlib, json, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'data_sources/dpwh_project_documents/on_demand'
SNAPSHOT=ROOT/'analysis_output/dpwh-in-depth-data.json'
PROGRESS=CACHE.parent/'.reparse-all-pow-progress.json'

def atomic_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(path)

def main():
    from storage.external_storage import guard
    from project_documents.cache_lock import project_lock
    from project_documents import pow as parser
    from project_documents.service import kinds
    from project_documents.signatories import extract
    guard()
    version=hashlib.sha256((ROOT/'project_documents/pow.py').read_bytes()+(ROOT/'project_documents/ocr_vision.swift').read_bytes()).hexdigest()
    snapshot=json.loads(SNAPSHOT.read_text())
    progress=json.loads(PROGRESS.read_text()) if PROGRESS.is_file() else {}
    if progress.get('parserVersion')!=version:
        progress={'startedAtUtc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'parserVersion':version,'codes':[],'processed':{},'skippedBusy':[],'missing':[],'errors':{}}
        for project in snapshot.get('projects',[]):
            code=project['code'];folder=CACHE/code;mp=folder/'metadata.json';rp=folder/'result.json'
            if not mp.is_file() or not rp.is_file():continue
            try:
                metadata=json.loads(mp.read_text());result=json.loads(rp.read_text())
                source=next((d for d in metadata.get('documents',[]) if kinds(d)=='pow'),None)
                if source is None:continue
                old=next((d for d in result.get('documents',[]) if d.get('kind')=='pow' and d.get('metadata',{}).get('url')==source.get('url')), {})
                asset_version=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()[:16]
                pdf=folder/'assets'/asset_version/'pow.pdf'
                if not pdf.is_file() and old.get('version'):
                    pdf=folder/'assets'/old['version']/'pow.pdf'
                if not pdf.is_file():progress['missing'].append(code)
                elif old.get('parserVersion')==version:progress['processed'][code]={'status':'already_current'}
                else:progress['codes'].append(code)
            except Exception as e:progress['errors'][code]=f'{type(e).__name__}: {e}'
        atomic_json(PROGRESS,progress)
    for index,code in enumerate(progress['codes'],1):
        if code in progress['processed'] or code in progress['errors']:continue
        guard();folder=CACHE/code
        try:
            with project_lock(folder,blocking=False):
                metadata=json.loads((folder/'metadata.json').read_text());result=json.loads((folder/'result.json').read_text())
                source=next((d for d in metadata.get('documents',[]) if kinds(d)=='pow'),None)
                if source is None:progress['missing'].append(code);continue
                old=next((d for d in result.get('documents',[]) if d.get('kind')=='pow' and d.get('metadata',{}).get('url')==source.get('url')), {})
                asset_version=hashlib.sha256(json.dumps(source,sort_keys=True).encode()).hexdigest()[:16]
                pdf=folder/'assets'/asset_version/'pow.pdf'
                if not pdf.is_file() and old.get('version'):
                    pdf=folder/'assets'/old['version']/'pow.pdf';asset_version=old['version']
                if not pdf.is_file():progress['missing'].append(code);continue
                doc={**old,'kind':'pow','metadata':source,'version':asset_version,'pdfAsset':asset_version+'/pow.pdf','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'parsedBy':'all_cached_pow_batch_reparse','parserVersion':version}
                doc['pow']=parser.parse_pdf(pdf,pdf.parent,round(float(metadata['amount'])*1000))
                doc['signatories']=old.get('signatories') or extract(pdf,'pow',pdf.parent);doc['status']='available';doc.pop('error',None)
                result['documents']=[d for d in result.get('documents',[]) if not(d.get('kind')=='pow' and d.get('metadata',{}).get('url')==source.get('url'))]
                result['documents'].append(doc);result['updatedByAllCachedPowReparseAtUtc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                atomic_json(folder/'result.json',result)
                parsed=doc['pow'];progress['processed'][code]={'status':parsed.get('status'),'pages':parsed.get('pagesProcessed'),'rows':len(parsed.get('rows',[])),'categories':len(parsed.get('costCategoryBreakdown',[])),'reviewPages':sum(p.get('status')=='needs_manual_review' for p in parsed.get('pages',[]))}
                progress['skippedBusy']=[x for x in progress['skippedBusy'] if x!=code]
        except BlockingIOError:
            if code not in progress['skippedBusy']:progress['skippedBusy'].append(code)
        except Exception as e:progress['errors'][code]=f'{type(e).__name__}: {e}'
        atomic_json(PROGRESS,progress)
        print(json.dumps({'current':index,'total':len(progress['codes']),'code':code,'result':progress['processed'].get(code,'busy' if code in progress['skippedBusy'] else progress['errors'].get(code,'missing'))},ensure_ascii=False),flush=True)
    progress['completedAtUtc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime());progress['completed']=not progress['skippedBusy'] and len(progress['processed'])>=len(progress['codes'])
    atomic_json(PROGRESS,progress);guard()
    import build_dpwh_indepth
    summary=build_dpwh_indepth.build()
    print(json.dumps({'complete':progress['completed'],'scheduled':len(progress['codes']),'processed':len(progress['processed']),'missing':len(progress['missing']),'busy':len(progress['skippedBusy']),'errors':progress['errors'],'publishedPowProjects':summary.get('projectsWithParsedPow'),'progressFile':str(PROGRESS)},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
