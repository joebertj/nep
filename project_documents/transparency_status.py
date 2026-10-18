"""Snapshot-based document coverage; never infer absence from a title mismatch."""
import re,unicodedata
from collections import Counter,defaultdict

def normalize(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(value or ''))).strip()

def build_status(snap, tree):
    reconciliation=snap.load('analysis/data/nep_2027_api_reconciliation.json')
    source=snap.load('analysis/data/nep_2027_source_projects.json')
    portals={r['source']['project_code']:r for r in tree['nodes'] if r['kind']=='project'}
    pairs={r['source_id']:r for r in reconciliation['api_pairs']}
    missing={r['source_id'] for r in reconciliation['unpaired_source']}
    by_title=defaultdict(dict);rows=[]
    def claim(title,key,entry):
        by_title[normalize(title)][key]=entry
    for code,node in portals.items():
        count=node['source'].get('document_count')
        entry={'code':code,'documentCount':count,'status':'documents_unknown' if count is None else 'incomplete_documents' if count<5 else 'five_or_more_listed','matchBasis':'Unique complete portal title','portalTitle':node['label']}
        claim(node['label'],code,entry)
    for row in source['projects']:
        sid=row['source_id'];pair=pairs.get(sid)
        if pair and pair['api_code'] in portals:
            node=portals[pair['api_code']];count=node['source'].get('document_count');candidate=pair['kind']!='exact_title_amount'
            entry={'code':pair['api_code'],'documentCount':count,'status':'candidate_match' if candidate else 'documents_unknown' if count is None else 'incomplete_documents' if count<5 else 'five_or_more_listed','matchBasis':pair['kind'],'portalTitle':node['label']}
            # Preserve a candidate alias without overriding an exact portal title.
            key=pair['api_code']
            existing=by_title[normalize(row['title'])].get(key)
            if not existing or existing['status']=='candidate_match':claim(row['title'],key,entry)
        else:
            entry={'code':None,'documentCount':None,'status':'not_found' if sid in missing else 'outside_snapshot_scope','matchBasis':'Unpaired NEP source row in retained API reconciliation' if sid in missing else 'FAP or source row outside retained domestic API reconciliation','portalTitle':None}
            claim(row['title'],sid,entry)
        rows.append({'sourceId':sid,'title':row['title'],'amountPesos':row['amount_php'],'sourcePage':row['pdf_page'],**entry})
    titles={}
    for title,claims in by_title.items():
        entries=list(claims.values())
        titles[title]=entries[0] if len(entries)==1 else {'status':'ambiguous_match','code':None,'documentCount':None,'matchBasis':'Multiple source records share this complete title','candidateCodes':sorted({r['code'] for r in entries if r.get('code')})}
    house=snap.load('analysis/data/hb_dpwh_native_ic_projects_3rd_reading.json')
    def visit(node):
        if node.get('kind') in ('project','fap_project'):
            title=normalize(node['label'])
            if title not in titles:titles[title]={'status':'no_verified_match','code':None,'documentCount':None,'matchBasis':'HGAB 3rd-reading title without a verified portal counterpart; renamed or new scope remains unresolved'}
        for child in node.get('children',[]):visit(child)
    visit(house['root'])
    summary={'portalProjects':len(portals),'portalDocumentStatuses':dict(Counter('documents_unknown' if r['source'].get('document_count') is None else 'incomplete_documents' if r['source']['document_count']<5 else 'five_or_more_listed' for r in portals.values())),'nepSourceRows':len(rows),'nepStatuses':dict(Counter(r['status'] for r in rows)),'ambiguousTitles':sum(r['status']=='ambiguous_match' for r in titles.values())}
    return {'expectedMinimumDocuments':5,'sourceCommit':snap.manifest['commit'],'snapshotRetrievedAtUtc':snap.manifest['retrievedAtUtc'],'scope':'DPWH NEP FY2027 transparency listing retained through BetterGov; not an HGAB publication register.','methodology':['Use retained NEP/API reconciliation and unique complete portal titles. Whitespace/Unicode normalization only; retain numbers, directions and geography.','Not found means an explicitly unpaired NEP row in this snapshot, not a live portal 404. HGAB title differences are not proof of absence.','OCR-title candidate links and duplicate titles remain provisional. FAP rows outside this domestic listing are not tagged missing.','Fewer than five listed documents is incomplete under the requested screening threshold. Five or more does not certify document types, accessibility, authenticity or completeness.','Counts are snapshot metadata. The current PDF-host outage does not change document counts. Historical GAA rows and non-DPWH agencies are not screened against this FY2027 listing.'],'summary':summary,'titles':titles},rows
