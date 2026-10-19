#!/usr/bin/env python3
"""Publish the on-demand document UI and worker sources; never fetch PDFs."""
import hashlib,json,re,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'
def build():
    from build_external_reference_review import Snapshot
    snap=Snapshot();tree=snap.load('analysis/data/dpwh_transparency_nep_tree.json')
    claims={}
    for r in tree['nodes']:
        if r['kind']=='project' and r['source'].get('document_count',0):claims.setdefault(r['label'],[]).append(r['source']['project_code'])
    index={title:codes[0] for title,codes in claims.items() if len(codes)==1}
    from project_documents.transparency_status import build_status
    coverage,coverage_rows=build_status(snap,tree)
    (OUT/'dpwh_transparency_document_coverage.json').write_text(json.dumps({**coverage,'rows':coverage_rows},ensure_ascii=False,indent=2)+'\n')
    index_data={'coverage':coverage,'source':'https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS','sourceCommit':snap.manifest['commit'],'scope':'Unique complete NEP project titles with indexed documents. Links refer to NEP source documents; funded scope at other stages is not assumed identical.','projects':index}
    (STATIC/'project-document-index.json').write_text(json.dumps(index_data,ensure_ascii=False)+'\n')
    for source,dest in [('page.html','project-documents.html'),('client.js','project-documents.js'),('burol_reviewed_rows.json','burol-reviewed-pow-rows.json')]:
        text=(ROOT/'project_documents'/source).read_text()
        if source=='page.html':
            client_version=hashlib.sha256((ROOT/'project_documents/client.js').read_bytes()).hexdigest()[:12]
            text=text.replace('src="project-documents.js"',f'src="project-documents.js?v={client_version}"')
        if source=='page.html':
            from uniform_report_menu import apply_page as uniform_header
            text=uniform_header(text,'project-documents.html')
            from report_table_presentation import publish_assets,apply_page
            text=apply_page(text,publish_assets())
        (STATIC/dest).write_text(text);(OUT/dest).write_text(text)
    worker=ROOT.parent/'open-data-visualization/analysis/project_documents';worker.mkdir(parents=True,exist_ok=True)
    for name in ['__init__.py','service.py','pow.py','requirements.txt','burol_reviewed_rows.json','ocr_vision.swift','browser_fetch.py','signatories.py','curl_fetch.py','cache_lock.py']:shutil.copy2(ROOT/'project_documents'/name,worker/name)
    links=(ROOT/'project_documents/table_links.js').read_text();(STATIC/'project-document-links.js').write_text(links);v=hashlib.sha256(links.encode()).hexdigest()[:12]
    for path in STATIC.glob('*.html'):
        if path.name in ['project-documents.html','index.html']:continue
        text=path.read_text();text=re.sub(r'<script[^>]*src="project-document-links.js[^\"]*"[^>]*></script>','',text)
        text=text.replace('</body>',f'<script src="project-document-links.js?v={v}"></script></body>',1);path.write_text(text)
        mirror=OUT/path.name
        if mirror.exists():mirror.write_text(text)
    from build_dpwh_indepth import build as indepth
    indepth()
    return {'linkedTitles':len(index),'documentCoverage':coverage['summary'],'documentsFetched':0}
if __name__=='__main__':print(json.dumps(build(),indent=2))
