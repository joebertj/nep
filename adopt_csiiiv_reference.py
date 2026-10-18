#!/usr/bin/env python3
"""Prefer the supplied analyst's reviewed extraction over older local parsing.
Retain manual decisions/flags, original provenance, and an adoption ledger.
"""
import csv,hashlib,json,re,subprocess
from pathlib import Path
from build_external_reference_review import Snapshot
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output';BASE=ROOT/'data_sources/csiiiv'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
PDFS=[ROOT/'HB 10858 FOR 2ND READING/2 - HB 10858 VOL IB.pdf',ROOT/'HB 10858 FOR 3RD READING/2- HB 10858 FOR 3RD READING VOL I-B.pdf']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,data):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def equivalence():
    path=OUT/'reviewed_annex_equivalence.json';hashes=[digest(p) for p in PDFS]
    old=json.loads(path.read_text()) if path.exists() else {}
    if old.get('pdfSha256')==hashes and old.get('allEqual'):return old
    records={}
    for name,first,last in [('nia',896,941),('hfep',877,893)]:
        values=[]
        for i,p in enumerate(PDFS):
            temp=Path('/private/tmp')/f'nep-reviewed-{name}-{i}.txt'
            subprocess.run(['gs','-q','-dBATCH','-dNOPAUSE','-sDEVICE=txtwrite',f'-dFirstPage={first}',f'-dLastPage={last}',f'-sOutputFile={temp}',str(p)],check=True,capture_output=True)
            text=re.sub(r'\s+',' ','\n'.join(l for l in temp.read_text().splitlines() if '.indd' not in l)).strip()
            values.append(hashlib.sha256(text.encode()).hexdigest())
        records[name]={'pdfPages':[first,last],'normalizedTextSha256':values,'equal':values[0]==values[1]}
    data={'pdfSha256':hashes,'sources':[str(p.relative_to(ROOT)) for p in PDFS],'annexes':records,'allEqual':all(r['equal'] for r in records.values()),'normalization':'Remove InDesign production footer lines containing .indd; collapse whitespace. No project rows removed.','limits':'Bounded reading equivalence only; source extraction retains the analyst’s manual decisions and unresolved flags.'};write(path,data)
    if not data['allEqual']:raise ValueError('Annex readings differ; preserve separate sources instead of transferring records')
    return data

def sync_fmr_csvs(raw,stage,projects,history):
    """Regenerate local CSV views from the accepted reviewed JSON, not old points."""
    for suffix,kind in [('projects_normalized','project'),('points','point'),('segments','segment')]:
        path=raw/f'{stage}_fmr_{suffix}.csv'
        with path.open(newline='') as stream:columns=csv.DictReader(stream).fieldnames
        backup=history/path.name
        if not backup.exists():backup.write_bytes(path.read_bytes())
        rows=[]
        for project in projects:
            members=[project] if kind=='project' else project[kind+'s']
            for member in members:
                row={**member,'project_id':project['project_id'],'pdf_page':project['source']['pdf_page'],'printed_page':project['source']['printed_page']}
                if kind=='project':row['source_pdf']=project['source']['source_pdf']
                if kind=='segment':row.update({'title':project['title'],'region':project['region']})
                row['coordinates_json']=json.dumps(member.get('coordinates'),ensure_ascii=False,separators=(',',':'))
                rows.append({k:' | '.join(map(str,row[k])) if isinstance(row.get(k),list) else row.get(k) for k in columns})
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=columns);writer.writeheader();writer.writerows(rows)

def adopt():
    snapshot=Snapshot();commit=snapshot.manifest['commit'];eq=equivalence()
    accepted=BASE/'accepted';accepted.mkdir(exist_ok=True)
    history=BASE/'accepted_prior'/commit;history.mkdir(parents=True,exist_ok=True)
    policy={'preferredExtraction':'csiiiv documented reviewed NIA/HFEP/FMR datasets','source':'https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS','commit':commit,'rule':'Documented human adjudication takes precedence over conflicting older local automated extraction. Preserve source/raw values, repair history and unresolved flags. This does not imply every row was manually reviewed. Project identity and geographic attribution remain separate from PDF extraction quality.'}
    # Preserve the project-wide source strategy across subsequent adoptions.
    previous_policy=BASE/'source_policy.json'
    if previous_policy.exists():policy={**json.loads(previous_policy.read_text()),**policy}
    write(BASE/'source_policy.json',policy)
    imported={}
    for family,paths in {'nia':['analysis-nia/data/nep_nia_dataset.json','analysis-nia/data/hgab_nia_tree.json','analysis-nia/data/hgab_nia_audit.json'], 'hfep':['analysis-hfep/data/nep_hfep_data_list.json','analysis-hfep/data/hgab_hfep_data_list.json']}.items():
        imported[family]=[snapshot.load(p) for p in paths]
        for path,data in zip(paths,imported[family]):write(accepted/Path(path).name,data)
    nia,house,nia_audit=imported['nia'];nodes={r['id']:r for r in house['nodes']};projects=[r for r in house['nodes'] if r['kind']=='project']
    if not nia_audit['passed'] or sum(r['printed_amount_php'] for r in projects)!=nia_audit['summary']['project_ledger_total_php']:raise ValueError('Reviewed NIA ledger/control mismatch')
    if house['metadata']['source_sha256']!=eq['pdfSha256'][0]:raise ValueError('Reviewed NIA source PDF differs')
    for stage,filename in [('2nd','hgab_2nd_editions.json'),('3rd','hgab_3rd_editions.json')]:
        path=ROOT/filename;payload=json.loads(path.read_text());old=payload['nia_irrigation']
        backup=history/f'{stage}_nia_irrigation.json'
        if not backup.exists():write(backup,old)
        rows=[]
        for r in projects:
            program=next((nodes[i]['label'] for i in r['path_ids'] if nodes[i]['kind']=='subprogram_control'),'FY2027 Irrigation Program')
            source=r['source'];ident=f'NIA-{stage}-{r["id"]}'
            rows.append({'id':ident,'code':ident,'fiscalYear':2027,'edition':stage,'agency':'National Irrigation Administration','program':program,'pap1':'National Irrigation Administration','pap2':'FY2027 Irrigation Program','pap3':program,'region':'','office':'','projectName':r['label'],'amountPesos':r['printed_amount_php'],'amount':r['printed_amount_php']/1000,'amountUnit':'thousand pesos','sourcePage':source['pdf_page'],'printedPage':source['printed_page'],'sourceVolume':PDFS[stage=='3rd'].name,'sourceText':r.get('label_raw',r['label']),'sourceContext':r.get('label_raw',r['label']),'analystSourceId':r['id'],'reviewStatus':r.get('image_review_status','Source-specific extraction with documented human review'),'sourceEvidenceStatus':r.get('source_evidence_status'),'sourceAttribution':policy['source'],'sourceCommit':commit})
        payload['nia_irrigation']=rows;payload['niaIrrigationProvenance']={'policy':policy,'annexEquivalence':eq};write(path,payload)
    from build_hgab_revision_pages import compare_rows
    second=json.loads((ROOT/'hgab_2nd_editions.json').read_text())['nia_irrigation'];third=json.loads((ROOT/'hgab_3rd_editions.json').read_text())['nia_irrigation'];revision=compare_rows(second,third,'nia_irrigation')
    path=STATIC/'nia-irrigation-data.json';d=json.loads(path.read_text());d['revision']=revision;d['projects']=second+third;d['nepProjects']=nia['projects'];d['sourcePolicy']=policy;write(path,d)
    path=STATIC/'hgab-revision-data.json';d=json.loads(path.read_text());d['nia_irrigation']=revision;write(path,d)
    path=OUT/'hgab_reading_revision_summary.json';d=json.loads(path.read_text());d['nia_irrigation']=revision['summary'];write(path,d)
    # Keep all accepted human coordinate repairs and their original review flags.
    raw=ROOT/'data_sources/fmr_analyst';fmr_changes=[]
    for stage in ['nep','hgab']:
        for suffix in ['coordinates_normalized.json','audit.json','coordinate_normalization_audit.json']:
            name=f'{stage}_fmr_{suffix}';new=snapshot.load('other-analysis/data/'+name);path=raw/name
            backup=history/name
            if path.exists() and not backup.exists():backup.write_bytes(path.read_bytes())
            before=digest(path) if path.exists() else None
            write(path,new);fmr_changes.append({'file':name,'beforeSha256':digest(backup) if backup.exists() else before,'previousAdoptedSha256':before,'afterSha256':digest(path)})
    for stage in ['nep','hgab']:
        current=json.loads((raw/f'{stage}_fmr_coordinates_normalized.json').read_text())
        sync_fmr_csvs(raw,stage,current['projects'],history)
    adoption={'sourcePolicy':policy,'nia':{'previousHouseRows':len(json.loads((history/'3rd_nia_irrigation.json').read_text())),'houseRows':len(third),'housePesos':sum(r['amountPesos'] for r in third),'nepRows':len(nia['projects']),'nepPesos':sum(r['amount_php'] for r in nia['projects'])},'hfep':{'nepFacilities':len(imported['hfep'][0]['items']),'houseFacilities':len(imported['hfep'][1]['items'])},'fmr':fmr_changes,'annexEquivalence':eq,'inputs':list(snapshot.used.values())}
    write(OUT/'reviewed_source_adoption.json',adoption);write(STATIC/'reviewed-source-adoption.json',adoption)
    return adoption
if __name__=='__main__':print(json.dumps(adopt()['nia'],indent=2))
