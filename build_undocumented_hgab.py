#!/usr/bin/env python3
"""Build an investigative review page for HGAB rows without combined Transparency records."""
import hashlib, json, os, re, unicodedata
from pathlib import Path
from uniform_report_menu import apply_page as apply_report_chrome
from report_table_presentation import apply_page as apply_table_presentation, publish_assets as publish_table_assets
from project_documents.senate_document_title_coverage import load_coverage, load_match_ids
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'; STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def read(name): return json.loads((OUT/name).read_text())
def key(s): return ' '.join(unicodedata.normalize('NFKC',str(s or '')).split())

def supporting_file_presence():
    """Count file links from the local Cloudflare manifest; never walk T5."""
    categories={'POW':0,'Development Council':0,'Geotagged photos':0,'BP':0,
                'Certificate of Implementability':0,'Other':0}
    from download_dpwh_nep_attachments import manifest_rows
    rows,_=manifest_rows(); codes=set(); files=0
    files_by_code={}; types_by_code={}
    for row in rows:
        files+=1;code=row.get('projectCode');kind=row['documentType']
        label={'BP 202':'BP'}.get(kind,kind)
        categories.setdefault(label,0);categories[label]+=1
        if not code:continue
        codes.add(code);files_by_code[code]=files_by_code.get(code,0)+1
        code_types=types_by_code.setdefault(code,{name:0 for name in categories})
        code_types[label]=code_types.get(label,0)+1
    return {'available':True,'source':'Cloudflare-file-links.jsonl; no live T5 folder scan',
            'files':files,'projectCodes':len(codes),'byType':categories,
            'filesByCode':files_by_code,'typesByCode':types_by_code}

def main():
    stage=read('dpwh_hgab_2nd_vs_3rd.json')['rows']
    mapping=read('hb_nep_comparison_3rd_mapping.json')
    indepth=read('dpwh-in-depth-data.json')
    pow_crosswalk=read('hgab_pow_title_crosswalk.json')
    coverage=read('dpwh_transparency_document_coverage.json')
    review=read('line_item_review_queue.json')
    repeats=read('within_stage_repeats.json')
    historical=read('repeat-hgab-historical-gaa.json')
    crosswalk=read('deo_leg_boundary_crosswalk.json')
    file_inventory=supporting_file_presence()
    file_presence={k:v for k,v in file_inventory.items() if k not in {'filesByCode','typesByCode'}}
    senate_title_coverage=load_coverage(OUT) or {}
    senate_title_matches=load_match_ids(OUT,include_relaxed=True)
    legacy_senate_title_matches={hid:set(files) for hid,files in senate_title_matches.items()}
    hgab_only_projects=[r for r in mapping.get('hgabWithoutSelectedCounterpart',[]) if r.get('allocationKind')=='project']
    hgab_only_ids={r.get('id') for r in hgab_only_projects if r.get('id')}
    title_matched_ids=set(legacy_senate_title_matches)
    title_match_total_pesos=sum(float(r.get('amountPesos') or 0) for r in hgab_only_projects)
    title_match_pesos=sum(float(r.get('amountPesos') or 0) for r in hgab_only_projects if r.get('id') in title_matched_ids)
    title_match_allocation={'totalPesos':round(title_match_total_pesos),'matchedPesos':round(title_match_pesos),
        'unmatchedPesos':round(title_match_total_pesos-title_match_pesos),
        'matchedProjectRows':len(title_matched_ids),'unmatchedProjectRows':max(0,len(hgab_only_projects)-len(title_matched_ids))}
    supporting_scan_path=OUT/'senate_supporting_documents_hgab_only_scan.json'
    supporting_scan=read(supporting_scan_path.name) if supporting_scan_path.is_file() else {}
    supporting_match_ids=set()
    for document in supporting_scan.get('documents',[]):
        if document.get('matchStatus') not in {'exact_title_match','relaxed_title_match','same_code_sibling_file_match'}:continue
        for hgab_id in document.get('matchedHgabIds',[]):
            supporting_match_ids.add(hgab_id)
            senate_title_matches.setdefault(hgab_id,set()).add(('supporting',document.get('file')))
    deo_legs={}
    for cp in crosswalk.get('pairs',[]):
        deo_legs.setdefault(key(cp.get('deo')).casefold(),[]).append({k:cp.get(k) for k in ('leg','legProvince','status','deoAreaFraction','legAreaFraction')})
    pair_by={p.get('hgabId'):p for p in mapping.get('pairs',[]) if p.get('hgabId')}
    unpaired={p.get('id') for p in mapping.get('hgabWithoutSelectedCounterpart',[]) if p.get('allocationKind')=='project'}
    by_code={p.get('code'):p for p in indepth.get('projects',[]) if p.get('code')}
    source_rows={r.get('sourceId'):r for r in coverage.get('rows',[]) if r.get('sourceId')}
    titles=coverage.get('titles',{})
    queue={r['hgabId']:r for r in review.get('rankedOccurrences',[]) if r.get('hgabId')}
    hist={}
    for r in historical.get('rows',[]): hist.setdefault(r['hgabId'],[]).append(r)
    same_stage={}
    for pair in repeats.get('pairs',[]):
        for side in ('left','right'):
            item=pair.get(side) or {}; hid=item.get('hgabId') or item.get('id')
            if hid: same_stage.setdefault(hid,[]).append(pair)
    pow_by_hgab={};pow_ambiguous={}
    for parsed in indepth.get('hgabPowResults',[]):
        if parsed.get('hgabId'):
            pow_by_hgab.setdefault(parsed['hgabId'],[]).append(parsed)
        elif parsed.get('matchStatus')=='ambiguous_exact_title_match':
            for candidate in parsed.get('candidateHgabIds',[]):pow_ambiguous.setdefault(candidate,[]).append(parsed)
    exact_advanceCopy_by_hgab={}
    for doc in pow_crosswalk.get('files',[]):
        if doc.get('status')=='exact_title_match':
            for hid in doc.get('hgabIds',[]):exact_advanceCopy_by_hgab.setdefault(hid,[]).append(doc)
    title_match_unassessed=int(indepth.get('hgabPowSummary',{}).get('titleMatchNotAssessedFiles') or 0)>0
    allrows=[]
    legacy_no_document_ids=set()
    for entry in stage:
        row=entry.get('third')
        if not row or row.get('allocationKind')!='project': continue
        # This page is specifically the HGAB-only cohort. Do not let rows with
        # a selected NEP counterpart leak into the undocumented project queue.
        if row.get('id') not in hgab_only_ids: continue
        title=titles.get(key(row.get('projectName')))
        status=title.get('status','unmapped') if title else 'unmapped'
        direct=None
        if title and title.get('code') and status not in {'not_found','no_verified_match','candidate_match','ambiguous_match','outside_snapshot_scope'}:
            direct=by_code.get(title['code'])
        pair=pair_by.get(row.get('id'))
        nep=source_rows.get((pair.get('nep') or {}).get('id')) if pair else None
        paired=by_code.get(nep.get('code')) if nep and nep.get('code') else None
        urls={str(d.get('url')) for p in (direct,paired) if p for d in p.get('documentLinks',[]) if d.get('url')}
        advanceCopy_files=exact_advanceCopy_by_hgab.get(row.get('id'),[])
        hgab_id=row.get('id')
        if not urls and not advanceCopy_files and not legacy_senate_title_matches.get(hgab_id):
            legacy_no_document_ids.add(hgab_id)
        if urls or advanceCopy_files or senate_title_matches.get(hgab_id): continue
        q=queue.get(row.get('id'),{})
        project={
            'id':row.get('id'),'title':row.get('projectName'),'amountPesos':row.get('amountPesos') or 0,
            'program':row.get('pap3') or row.get('pap2') or row.get('pap1') or '',
            'office':row.get('office') or '', 'region':row.get('region') or '',
            'sourceVolume':row.get('sourceVolume') or '', 'sourcePage':row.get('sourcePage'),
            'documentStatus':status,'nepPairStatus':pair.get('kind') if pair else 'no selected NEP counterpart',
            'nepTitle':(pair or {}).get('nep',{}).get('projectName','') if pair else '',
            'nepHasDocumentLinks':bool(paired and paired.get('documentLinks')),
            'flags':[{'id':f.get('id'),'label':f.get('label'),'evidence':f.get('evidence'),'summaryFinding':f.get('summaryFinding')} for f in q.get('flags',[])],
            'flagCount':q.get('flagCount',0),'evidenceCautions':q.get('evidenceCautions',[]),
            'districts':q.get('districts',[]),
            'deoLegCrosswalk':deo_legs.get(key(row.get('office')).casefold(),[]),
            'historicalMatches':[{'gaaYear':m.get('gaaYear'),'gaaTitle':m.get('gaaTitle'),'gaaAmountPesos':m.get('gaaAmountPesos'),'chainageStatus':m.get('chainageStatus')} for m in hist.get(row.get('id'),[])],
            'advanceCopyPowMatchStatus':'exact_title_match' if pow_by_hgab.get(row.get('id')) else 'ambiguous_title_match' if pow_ambiguous.get(row.get('id')) else 'title_match_not_assessed' if title_match_unassessed else 'no_exact_title_match',
            'advanceCopyPow':[{'code':doc.get('code'),'status':doc.get('status'),'pageCount':doc.get('pageCount'),
                'rows':doc.get('rows',[]),'costCategoryBreakdown':doc.get('costCategoryBreakdown',[])} for doc in pow_by_hgab.get(row.get('id'),[])],
            'advanceCopyPowAmbiguousCodes':[doc.get('code') for doc in pow_ambiguous.get(row.get('id'),[])],
            'withinStageRepeatPairs':[{'kind':p.get('kind'),'titleSimilarity':p.get('titleSimilarity'),'left':{'projectName':(p.get('left') or {}).get('projectName'),'title':(p.get('left') or {}).get('title')},'right':{'projectName':(p.get('right') or {}).get('projectName'),'title':(p.get('right') or {}).get('title')}} for p in same_stage.get(row.get('id'),[])]
        }
        allrows.append(project)
    allrows.sort(key=lambda r:(-r['flagCount'],-r['amountPesos'],r['title'].casefold()))
    expected=len(legacy_no_document_ids-supporting_match_ids)
    if len(allrows)!=expected: raise SystemExit(f'No-doc reconciliation mismatch: built {len(allrows)}, expected {expected}')
    hgab_only_pow_results=[d for d in indepth.get('hgabPowResults',[]) if d.get('cohortStatus')=='in_transparency_link_gap_cohort']
    hgab_only_pow_summary={
        'parsedDocuments':len(hgab_only_pow_results),
        'documentsWithBillRows':sum(bool(d.get('rows')) for d in hgab_only_pow_results),
        'billRows':sum(len(d.get('rows',[])) for d in hgab_only_pow_results),
        'exactTitleMatchedFiles':sum(d.get('matchStatus')=='exact_title_match' for d in hgab_only_pow_results),
        'relaxedTitleMatchedFiles':sum(d.get('matchStatus')=='relaxed_title_match' for d in hgab_only_pow_results),
        'titleMatchAssessedFiles':len(hgab_only_pow_results),
        'titleScanDocuments':len(hgab_only_pow_results),
        'scope':'Only parsed POW files assigned to the HGAB-only / former portal-document-gap cohort.'}
    supporting_coverage={k:supporting_scan.get(k) for k in ('denominatorProjectRows','projectsWithAtLeastOneMatchedDocument','projectsWithAtLeastOneMatchedDocumentPct','projectRowsWithoutMatchedDocument','matchedFileRecords','byType','signatoryCandidateCounts','signatoryCandidatesByDocumentType','deduplication','matchingMethod') if k in supporting_scan}
    senate_project_stats=read('senate-hgab-only-document-stats.json')
    senate_stats_by_id={p.get('hgabId'):p for p in senate_project_stats.get('projects',[]) if p.get('hgabId')}
    coverage_rows=[]
    for row in hgab_only_projects:
        hgab_id=row.get('id')
        title_match=titles.get(key(row.get('projectName')))
        direct_status=title_match.get('status','unmapped') if title_match else 'unmapped'
        direct=(by_code.get(title_match.get('code')) if title_match and title_match.get('code') and
                direct_status not in {'not_found','no_verified_match','candidate_match','ambiguous_match','outside_snapshot_scope'} else None)
        pair=pair_by.get(hgab_id)
        nep=source_rows.get((pair.get('nep') or {}).get('id')) if pair else None
        paired=by_code.get(nep.get('code')) if nep and nep.get('code') else None
        related_proposals=[]
        if direct and direct.get('documentLinks'):
            related_proposals.append(('Direct Proposal title match',direct))
        if paired and paired.get('documentLinks'):
            related_proposals.append(('Selected NEP counterpart Proposal',paired))
        proposal_types=sorted({str(d.get('type')) for _,p in related_proposals for d in p.get('documentLinks',[]) if d.get('type')})
        senate=senate_stats_by_id.get(hgab_id,{})
        senate_types=sorted(t for t,v in senate.get('documentTypes',{}).items() if v.get('present'))
        signatories={}
        def add_signatory(name,role,source):
            name=str(name or '').strip(); role=str(role or '').strip()
            if not name:return
            sig_key=(name.casefold(),role.casefold())
            record=signatories.setdefault(sig_key,{'name':name,'role':role,'sources':set()})
            if source:record['sources'].add(source)
        for person in senate.get('signatories',[]):
            role=str(person.get('role') or '').replace('_',' ').title()
            doc_types=person.get('documentTypes') or ['Senate HGAB document']
            for doc_type in doc_types:add_signatory(person.get('name'),role,'Senate HGAB · '+str(doc_type))
        for proposal_source,proposal in related_proposals:
            for document in proposal.get('documents',[]):
                doc_type=document.get('kind') or document.get('documentType') or 'document'
                source='Proposal · '+str(doc_type)
                for person in document.get('people',[]):
                    add_signatory(person.get('name'),person.get('roleText') or person.get('role') or person.get('kind'),source)
        sig_rows=[{'name':v['name'],'role':v['role'],'sources':sorted(v['sources'])}
                  for _,v in sorted(signatories.items(),key=lambda item:(item[1]['name'].casefold(),item[1]['role'].casefold()))]
        coverage_rows.append({
            'hgabId':hgab_id,'title':row.get('projectName'),'office':row.get('office') or '',
            'region':row.get('region') or '', 'amountPesos':round(float(row.get('amountPesos') or 0)),
            'proposalDocumentsMatched':bool(related_proposals),
            'proposalDocumentSources':[source for source,_ in related_proposals],
            'proposalDocumentTypes':proposal_types,
            'senateHgabDocumentsMatched':bool(senate.get('hasAtLeastOneTitleMatchedDocument')),
            'senateDocumentTypes':senate_types,
            'senateMatchedFileRecords':int(senate.get('matchedDocumentFileRecords') or 0),
            'signatories':sig_rows})
    coverage_rows.sort(key=lambda r:(-r['amountPesos'],str(r.get('title') or '').casefold(),str(r.get('hgabId') or '')))
    if len(coverage_rows)!=len(hgab_only_projects):
        raise SystemExit(f'HGAB-only coverage export mismatch: built {len(coverage_rows)}, expected {len(hgab_only_projects)}')
    coverage_export={'generatedAtUtc':senate_project_stats.get('generatedAtUtc'),
        'scope':'FY2027 HGAB project rows without a selected NEP counterpart. Proposal status means linked Proposal document records on a direct title match or selected NEP counterpart. Senate status uses title-linked HGAB support files. Signatories are document-extracted candidates, not verified current officeholders or project sponsors.',
        'denominatorProjectRows':len(coverage_rows),'projects':coverage_rows}
    coverage_export_json=json.dumps(coverage_export,ensure_ascii=False,indent=2)+'\n'
    coverage_export_version=hashlib.sha256(coverage_export_json.encode('utf-8')).hexdigest()[:12]
    # The local GAB comparison is only aggregate evidence; do not invent project-level exclusions.
    data={'summary':{'noDocumentProjects':len(allrows),'amountPesos':sum(r['amountPesos'] for r in allrows),
        'withReviewFlags':sum(bool(r['flags']) for r in allrows),'withNoSelectedNep':sum(r['nepPairStatus']=='no selected NEP counterpart' for r in allrows),
        'withinStageRepeatCandidates':sum(bool(r['withinStageRepeatPairs']) for r in allrows),
        'gabRemovedItemsReported':295,'gabRemovedPesosReported':8836000000,
        'senateTitleMatchAllocation':title_match_allocation,
        'portalOnlyGapProjects':indepth['hgabCoverage'].get('portalOnlyMissingListedDocumentsRows',len(allrows)),
        'portalOnlyGapPesos':indepth['hgabCoverage'].get('portalOnlyMissingListedDocumentsAmountPesos',sum(r['amountPesos'] for r in allrows)),
        'advanceCopyMatchedRows':indepth['hgabCoverage'].get('advanceCopyExactTitleMatchedRows',0),
        'advanceCopyNewlyCoveredProjects':indepth['hgabCoverage'].get('portalOnlyMissingListedDocumentsRows',0)-len(allrows),
        'advanceCopyFilesInPortalOnlyGap':sum(1 for d in pow_crosswalk.get('files',[]) if d.get('status')=='exact_title_match' and d.get('cohortStatus')=='in_transparency_link_gap_cohort'),
        'advanceCopyParsedBillRowsInPortalOnlyGap':sum(len(d.get('rows',[])) for d in indepth.get('hgabPowResults',[]) if d.get('cohortStatus')=='in_transparency_link_gap_cohort' and d.get('matchStatus')=='exact_title_match'),
        'advanceCopyPowMatchedProjects':sum(bool(x.get('advanceCopyPow')) for x in allrows),
        'advanceCopyPowMatchedFiles':sum(len(x.get('advanceCopyPow',[])) for x in allrows),
        'advanceCopyPowBillRows':sum(len(doc.get('rows',[])) for x in allrows for doc in x.get('advanceCopyPow',[])),
        'localFilePresence':file_presence,'senateDocumentTitleCoverage':senate_title_coverage,
        'senateSupportingDocumentCoverage':supporting_coverage},
        'hgabPowSummary':hgab_only_pow_summary,
        'provenance':{'hgab':'FY2027 HGAB 3rd-reading DPWH project ledger','documents':'DPWH Transparency portal metadata and Senate-provided HGAB POW documents; matching is ongoing and PDF links are not published','documentSnapshot':indepth['hgabCoverage'].get('snapshotRetrievedAtUtc'),
        'deoLegCrosswalk':'Spatial district crosswalk evidence; source dates unverified',
        'gab':'User-provided aggregate (295 items / ₱8.836B); no item-level Senate/GAB rows are available, so individual HGAB records are not identified as removed.'}}
    shard_rows=200
    project_shards=[allrows[i:i+shard_rows] for i in range(0,len(allrows),shard_rows)]
    shard_payloads=[json.dumps(part,ensure_ascii=False,separators=(',',':')) for part in project_shards]
    pow_fields=('code','status','matchStatus','hgabTitle','hgabId','cohortStatus','rows')
    bill_fields=('itemCode','description','quantity','unit','amountPesos','costCategory','sourcePage')
    pow_results=[]
    for source_doc in hgab_only_pow_results:
        doc={k:source_doc.get(k) for k in pow_fields if k!='rows'}
        doc['rows']=[{k:row.get(k) for k in bill_fields} for row in source_doc.get('rows',[])]
        pow_results.append(doc)
    pow_chunk_size=200
    pow_chunks=[pow_results[i:i+pow_chunk_size] for i in range(0,len(pow_results),pow_chunk_size)]
    pow_payloads=[json.dumps(part,ensure_ascii=False,separators=(',',':')) for part in pow_chunks]
    version_source=json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n'.join(shard_payloads+pow_payloads)
    data_version=hashlib.sha256(version_source.encode('utf-8')).hexdigest()[:12]
    shard_names=[f'undocumented-hgab-projects-{data_version}-{i:02d}.json' for i in range(len(shard_payloads))]
    pow_shard_names=[f'undocumented-hgab-pow-{data_version}-{i:02d}.json' for i in range(len(pow_payloads))]
    data['projectShards']=shard_names
    data['powShards']=pow_shard_names
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'))
    if supporting_scan:
        project_stats=[]
        for project in supporting_scan.get('projects',[]):
            signatories=[]
            role_counts={}
            for candidate in project.get('signatories',[]):
                role=candidate.get('role') or 'unknown';role_counts[role]=role_counts.get(role,0)+1
                signatories.append({'name':candidate.get('name'),'role':role,'sourcePages':candidate.get('sourcePages',[]),
                    'sourceFiles':[Path(path).name for path in candidate.get('sourceFiles',[])],
                    'documentTypes':candidate.get('documentTypes',[]),
                    'verificationStatuses':candidate.get('verificationStatuses',[])})
            project_stats.append({k:project.get(k) for k in ('hgabId','title','office','region','amountPesos','hasAtLeastOneTitleMatchedDocument','matchedDocumentFileRecords','documentTypes','t5FileCodes','t5FileCount','t5FilePresenceByType')} | {'signatoryCountsByRole':role_counts,'signatories':signatories})
        compact_stats={'generatedAtUtc':supporting_scan.get('generatedAtUtc'),'scope':supporting_scan.get('scope'),
            'matchingMethod':supporting_scan.get('matchingMethod'),'denominatorProjectRows':supporting_scan.get('denominatorProjectRows'),
            'projectsWithAtLeastOneMatchedDocument':supporting_scan.get('projectsWithAtLeastOneMatchedDocument'),
            'projectsWithAtLeastOneMatchedDocumentPct':supporting_scan.get('projectsWithAtLeastOneMatchedDocumentPct'),
            'projectRowsWithoutMatchedDocument':supporting_scan.get('projectRowsWithoutMatchedDocument'),
            'matchedFileRecords':supporting_scan.get('matchedFileRecords'),'byType':supporting_scan.get('byType'),
            'deduplication':supporting_scan.get('deduplication'),'signatoryCandidateCounts':supporting_scan.get('signatoryCandidateCounts'),
            'signatoryCandidatesByDocumentType':supporting_scan.get('signatoryCandidatesByDocumentType'),
            'photoMetadataNote':'Geotagged-photo file presence is based on Cloudflare-indexed filenames and unique-code linkage. The prior parser snapshot records PDF page count and first-page image count; it does not verify image GPS/EXIF coordinates or photo contents.',
            'signatoryNote':'Names and roles are extracted from a candidate name above an explicit role in a signature column. They identify document signers, not project sponsors, beneficiaries or people responsible for the work. Confirm against the source page.',
            'projects':project_stats}
        support_payload=json.dumps(compact_stats,ensure_ascii=False,separators=(',',':'))
    else:support_payload=None
    coverage=data['summary'].get('senateSupportingDocumentCoverage') or {}
    coverage_denominator=int(coverage.get('denominatorProjectRows') or 0)
    coverage_matched=int(coverage.get('projectsWithAtLeastOneMatchedDocument') or 0)
    coverage_unmatched=max(0,coverage_denominator-coverage_matched)
    coverage_pct=float(coverage.get('projectsWithAtLeastOneMatchedDocumentPct') or 0)
    coverage_types=coverage.get('byType') or {}
    coverage_type_labels=['POW','BP 202','Development Council','Geotagged photos','Certificate of Implementability','Other']
    coverage_type_summary=' · '.join(f"{label} {int((coverage_types.get(label) or {}).get('matchedProjectRows') or 0):,} ({100*int((coverage_types.get(label) or {}).get('matchedProjectRows') or 0)/coverage_denominator:.1f}%)" for label in coverage_type_labels) if coverage_denominator else 'Type-level scan totals unavailable.'
    coverage_fallback=(f"<strong>All-document scan:</strong> {coverage_matched:,} of {coverage_denominator:,} HGAB-only rows ({coverage_pct:.2f}%) have at least one matched file; {coverage_unmatched:,} ({100*coverage_unmatched/coverage_denominator:.2f}%) have no current match. This covers {int(coverage.get('matchedFileRecords') or 0):,} matched file records. By type (project rows overlap): {coverage_type_summary}. Document presence does not verify file contents." if coverage_denominator else '<strong>All-document scan:</strong> Current HGAB-only coverage is unavailable.')
    html='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HGAB projects without DPWH Transparency links · BetterGov</title><style>
:root{--navy:#00246a;--blue:#0648a8;--gold:#fcd116;--ink:#18232d;--muted:#586877;--line:#d9e1e8;--paper:#f3f6f8;--red:#a43c25}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 system-ui,sans-serif}header{background:var(--navy);color:white;padding:28px clamp(16px,4vw,54px);border-bottom:6px solid var(--gold)}h1{margin:4px 0;font-size:clamp(28px,4vw,44px)}header p{max-width:950px;color:#edf3ff}main{padding:20px clamp(12px,3vw,40px);max-width:1800px;margin:auto}.warning,.card,.stat{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}.warning{border-left:5px solid var(--gold)}.warning.red{border-left-color:var(--red);background:#fff8f5}.document-summary h2{margin:0 0 8px}.document-summary p{margin:8px 0}.document-summary p:last-child{margin-bottom:0}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}.stat{margin:0}.gab-title{display:flex;justify-content:space-between;align-items:center;gap:16px}.gab-title strong{font-size:clamp(30px,5vw,48px);color:var(--navy);white-space:normal;text-align:right;max-width:55%}.gab-title strong span{display:block}.gab-title h2,#gab-highlight{font-size:clamp(18px,1.5vw,22px);line-height:1.3}.gab-highlight span{display:block}.gab-count-line{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:12px;margin-top:3px;font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}.gab-count-line strong{font-size:inherit;white-space:nowrap;color:var(--ink);text-align:right}.gab-reference-label,.gab-reference-label strong{color:#111!important;font-weight:750}.gab-bars{display:grid;gap:18px;margin-top:18px}.gab-bar-row{display:grid;grid-template-columns:minmax(180px,1fr) 2fr;gap:16px;align-items:center}.gab-bar-label strong,.gab-bar-label span{display:block}.gab-bar-label span{font-size:13px;color:var(--muted)}.gab-stack{position:relative;display:flex;height:26px;overflow:visible;border-radius:7px;background:#e7edf2}.gab-stack .gab-reference-marker{position:absolute;top:-5px;bottom:-5px;width:3px;background:#111;z-index:3;transform:translateX(-1px);box-shadow:0 0 0 1px #fff}.gab-legend .gab-reference-key:before{background:#111}.gab-removed{background:#2e8b57}.gab-remain{background:var(--red)}.gab-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--muted);margin-top:12px}.gab-legend span:before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;background:#2e8b57;margin-right:6px}.gab-legend span+span:before{background:var(--red)}.stat strong{display:block;font-size:26px;color:var(--navy)}.muted,.small{color:var(--muted)}.small{font-size:13px}.document-computation{margin:10px 0;padding:12px 14px;border:1px solid var(--line);border-radius:8px;background:#fff}.document-computation summary{font-weight:700;cursor:pointer}.document-computation p{margin:8px 0 0}.filters{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.filters input,.filters select{padding:9px;border:1px solid #aab8c5;border-radius:7px;background:white;font:inherit}.filters input{flex:1;min-width:230px}.tablewrap{overflow-x:auto;overflow-y:visible;max-height:none;border:1px solid var(--line);border-radius:8px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{position:sticky;top:0;background:#edf2f7;z-index:1}td.num{text-align:right;white-space:nowrap}.tag{display:inline-block;background:#eef3fa;padding:2px 7px;border-radius:20px;margin:2px;font-size:12px}.redtag{background:#ffebe6;color:#8c2917}.pagination{display:flex;justify-content:flex-end;align-items:center;gap:10px;padding:10px}.pagination button{padding:7px 11px;background:white;border:1px solid #aab8c5;border-radius:6px}details{margin:8px 0}h2{color:var(--navy);margin:0 0 8px}@media(max-width:750px){.stats{grid-template-columns:1fr 1fr}.gab-bar-row{grid-template-columns:minmax(0,1fr);gap:8px}.gab-title{align-items:flex-start}.gab-title strong{font-size:clamp(22px,5vw,32px);max-width:58%}}
</style></head><body><header><div>FY2027 · HOUSE GAB (HGAB) · DPWH</div><h1>HGAB projects without a current document match</h1><p>Projects listed here have no current DPWH Transparency Proposal link or accepted title match in the Cloudflare-indexed Senate HGAB supporting-document files. A title match is a document-presence lead; document contents remain under verification.</p></header><main><section class="warning document-summary"><h2>Senate-provided HGAB documents · verification and coverage</h2><p><strong>Senate-provided HGAB documents are being verified.</strong> We are checking whether these records match projects currently labeled HGAB-only; potentially most may have supporting documentation. That remains unverified while title matches and document contents are reviewed. This is a gain for transparency. We thank the Senate for providing these records.</p><p><strong>No title match is not proof that documents do not exist.</strong> The expanded scan reads first-page native PDF text across POW, BP 202, Development Council, geotagged-photo, implementability-certificate and other PDFs. Image-only or damaged files and titles outside the first page may remain unmatched. Source PDF links remain unpublished.</p><p><strong>Senate/GAB scope note.</strong> The reported Senate/GAB removal is 295 items totaling ₱8.836B. A separate BP 202/POW-only title scan identified matches for 3,287 of 6,105 HGAB-only rows (53.84%); the expanded all-document scan below reports its deduplicated result separately. The reported removals are aggregate-only; the local inputs do not identify which individual rows were removed.</p><p id="file-presence">__HGAB_DOCUMENT_COVERAGE__</p></section><details class="document-computation"><summary>How Senate document coverage is counted</summary><p>The expanded scan uses exact or relaxed first-page title matches and unique HGAB-code sibling files. The all-document total deduplicates by House project row; per-type counts overlap. T5 filename-code inventory shows file presence only. PDF contents and geotagged photo coordinates are not verified; unmatched rows may still have documents.</p></details><div id="stats" class="stats"></div><section class="card"><div class="gab-title"><div><p class="small" style="text-transform:uppercase;letter-spacing:.08em">Senate files · HGAB-only coverage</p><h2 id="senate-coverage-heading">Loading Senate title-match coverage…</h2></div><strong id="gab-highlight"></strong></div><div id="gab-bars" class="gab-bars"></div><div class="gab-legend"><span>BP 202 / POW title match</span><span>No BP 202 / POW title match yet</span><span class="gab-reference-key">Reported Senate/GAB removal · aggregate only</span></div><p class="small muted">This chart shows the narrower BP 202 / POW title-match subset. The all-document scan and per-type coverage are summarized above. Black markers show the reported 295 items and ₱8.836B on the chart scales for reference; those removals have not been matched to individual HGAB-only rows.</p><details class="document-computation"><summary>How the project and allocation chart is calculated</summary><p>The colored bars compare BP 202/POW title matches with no title match across 6,105 HGAB-only House project rows. Allocation totals sum those same House rows, split by BP 202/POW title-match status. The black markers represent the separate reported Senate/GAB aggregate (295 items; ₱8.836B). They are not subtracted from either bar and do not imply project-level overlap. The broader all-document result is shown separately above and deduplicated by House row ID.</p></details></section><section class="card" id="parsed-hgab-pow"><h2>Senate-provided HGAB POW documents · parsed results</h2><p class="muted">This parsed-results table is limited to Senate POW files assigned to the HGAB-only project cohort with a Proposal document gap. The broader parser inventory is not included here. Parsed line items are machine-extracted review evidence; verify amounts and descriptions against the source page. PDF links and source paths are not published.</p><div id="pow-stats" class="stats"></div><p id="pow-match-scope" class="muted" aria-live="polite"></p><p id="pow-load-status" class="small muted" aria-live="polite">Loading parsed POW results…</p><div class="filters"><input id="pow-q" type="search" placeholder="Search HGAB code, item, or category"></div><div class="tablewrap"><table><thead><tr><th>HGAB file code</th><th>House ledger match</th><th>Parse status</th><th>Bill item</th><th>Quantity</th><th>Unit</th><th>Amount</th><th>Category</th><th>POW page</th></tr></thead><tbody id="pow-rows"><tr><td colspan="9">Loading parsed POW results…</td></tr></tbody></table></div><div class="pagination"><button id="pow-prev">Previous</button><span id="pow-page"></span><button id="pow-next">Next</button></div></section><section class="card"><h2>Investigation queue</h2><p class="muted">Sort starts with the number of independent review signals, then allocation. Signals are screening leads, not findings. Select a row for the source context and individual methods.</p><div class="filters"><input id="q" type="search" placeholder="Search title, office, region, program, district"><select id="flag"><option value="">All review-flag counts</option></select><select id="program"><option value="">All programs</option></select><select id="region"><option value="">All regions</option></select><select id="crosswalk"><option value="">All DEO–LEG coverage</option><option value="mapped">Has spatial crosswalk row</option><option value="unmapped">No spatial crosswalk row</option></select><select id="sort"><option value="flags">Most flags</option><option value="amount">Largest allocation</option><option value="title">Project title</option></select><button id="export" type="button">Export filtered CSV</button></div><div class="tablewrap"><table><thead><tr><th>Project / source</th><th>Office · region</th><th>Program</th><th>Allocation</th><th>Flags</th><th>Repeat evidence</th><th>NEP / document route</th><th>advance-copy HGAB POW</th><th>DEO → LEG crosswalk evidence</th></tr></thead><tbody id="rows"></tbody></table></div><div class="pagination"><button id="prev">Previous</button><span id="page"></span><button id="next">Next</button></div></section><section class="card"><h2>Methods and limits</h2><ul><li><b>Combined DPWH Transparency source:</b> Online portal links and advance-copy POW documents are treated as one document source. PDF URLs are withheld; uniquely exact-title-matched files count as document evidence.</li><li><b>advance-copy HGAB POW documents:</b> parsed rows are attached only when the normalized full project title in the POW text exactly matches one unique House ledger title. Ambiguous repeated titles and unmatched files are not assigned. PDF links are not published.</li><li><b>Document screen:</b> a document record counts when present directly on the HGAB title match, on the selected NEP counterpart, or as a uniquely exact-title-matched advance-copy POW document. Pairing does not prove the NEP documents have identical scope to the HGAB line.</li><li><b>Red flags and cost clustering:</b> exact HGAB ID join to the existing line-item review queue. This carries its repeated-allocation clusters, high unit-cost signals, historical comparisons and related cautions. Candidate flags need source and scope review.</li><li><b>Repeated projects:</b> within-stage repeat pairs and prior-GAA title candidates are attached where exact HGAB IDs match. Similar titles or costs alone do not prove duplicate scope.</li><li><b>DEO clustering:</b> the review queue's district/representative associations are shown as leads. A DEO may serve multiple legislative districts; the office total is not split or attributed to an individual legislator.</li><li><b>LEG crosswalk:</b> the DEO is joined to spatially intersecting legislative districts using the existing boundary crosswalk. Overlap does not assign a project to a district, member, sponsor or controller; boundary dates are unverified and multi-district DEOs remain shared.</li><li><b>Senate/GAB removal:</b> only the aggregate 295 / ₱8.836B figure is available in the local inputs. Project-level inclusion remains unresolved until the Senate/GAB rows are matched.</li></ul><p class="small">Sources: HGAB 3rd-reading DPWH ledger; DPWH Transparency project/document snapshot; selected NEP–HGAB mapping; line-item review queue; within-stage repeat screen; historical GAA repeat screen; DEO–LEG boundary crosswalk. Snapshot: __SNAPSHOT__.</p></section><div id="detail" class="card" hidden></div></main><script>
fetch('undocumented-hgab-data.json?v=__DATA_VERSION__').then(r=>{if(!r.ok)throw new Error('Could not load the project data manifest');return r.json()}).then(async D=>{D.projects=(await Promise.all((D.projectShards||[]).map(name=>fetch(name+'?v=__DATA_VERSION__').then(r=>{if(!r.ok)throw new Error('Could not load project shard '+name);return r.json()})))).flat();D.projects=(Array.isArray(D.projects)?D.projects:[]).map(x=>({...x,flags:Array.isArray(x.flags)?x.flags:[],districts:Array.isArray(x.districts)?x.districts:[],evidenceCautions:Array.isArray(x.evidenceCautions)?x.evidenceCautions:[],deoLegCrosswalk:Array.isArray(x.deoLegCrosswalk)?x.deoLegCrosswalk:[],historicalMatches:Array.isArray(x.historicalMatches)?x.historicalMatches:[],withinStageRepeatPairs:Array.isArray(x.withinStageRepeatPairs)?x.withinStageRepeatPairs:[],advanceCopyPow:Array.isArray(x.advanceCopyPow)?x.advanceCopyPow.map(d=>({...d,rows:Array.isArray(d.rows)?d.rows:[],costCategoryBreakdown:Array.isArray(d.costCategoryBreakdown)?d.costCategoryBreakdown:[]})):[],advanceCopyPowAmbiguousCodes:Array.isArray(x.advanceCopyPowAmbiguousCodes)?x.advanceCopyPowAmbiguousCodes:[]}));const S=D.summary||{},presence=S.localFilePresence||{},scan=S.senateDocumentTitleCoverage||{},allDocs=S.senateSupportingDocumentCoverage||{},fmt=n=>Number(n||0).toLocaleString('en-PH'),peso=n=>'₱'+fmt(Math.round(Number(n||0))),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));document.getElementById('file-presence').innerHTML=presence.available?`<strong>T5 inventory by HGAB filename code (file presence only; contents unverified):</strong> ${fmt(presence.files)} files across ${fmt(presence.projectCodes)} HGAB file codes · POW ${fmt(presence.byType?.POW)} · Development Council ${fmt(presence.byType?.['Development Council'])} · geotagged photos ${fmt(presence.byType?.['Geotagged photos'])} · BP ${fmt(presence.byType?.BP)} · Certificates of Implementability ${fmt(presence.byType?.['Certificate of Implementability'])} · other ${fmt(presence.byType?.Other)}. <strong>First-page Senate title scan for HGAB-only rows:</strong> BP 202 ${fmt(scan.byType?.bp202?.matchedProjectRows)} / ${fmt(scan.denominatorProjectRows)} (${fmt(scan.byType?.bp202?.coveragePct)}%) from ${fmt(scan.byType?.bp202?.documentsScanned)} PDFs · POW ${fmt(scan.byType?.pow?.matchedProjectRows)} / ${fmt(scan.denominatorProjectRows)} (${fmt(scan.byType?.pow?.coveragePct)}%) from ${fmt(scan.byType?.pow?.documentsScanned)} PDFs · either ${fmt(scan.combinedMatchedProjectRows)} / ${fmt(scan.denominatorProjectRows)} (${fmt(scan.combinedCoveragePct)}%), deduplicated. Relaxed POW title candidates are included in the either-source estimate. This BP 202/POW estimate is file-presence evidence only. <strong>All-document scan:</strong> ${fmt(allDocs.projectsWithAtLeastOneMatchedDocument)} of ${fmt(allDocs.denominatorProjectRows)} HGAB-only rows (${fmt(allDocs.projectsWithAtLeastOneMatchedDocumentPct)}%) have at least one title-linked Senate file across all scanned types, counting each House row once; ${fmt(Math.max(0,Number(allDocs.denominatorProjectRows||0)-Number(allDocs.projectsWithAtLeastOneMatchedDocument||0)))} rows (${allDocs.denominatorProjectRows?((100*Math.max(0,Number(allDocs.denominatorProjectRows)-Number(allDocs.projectsWithAtLeastOneMatchedDocument||0)))/Number(allDocs.denominatorProjectRows)).toFixed(2):0}%) have no current match. By type: ${Object.entries(allDocs.byType||{}).map(([type,stats])=>`${esc(type)} ${fmt(stats.matchedProjectRows)} projects`).join(' · ')}. <a href="senate-hgab-only-document-stats.json" download>Per-project document types and signatory candidates ↗</a>. An unmatched title is not proof a file is absent; contents remain unverified.`:'<strong>T5 file inventory unavailable.</strong> The current no-document list uses the latest completed evidence build.';document.getElementById('stats').innerHTML=[[fmt(S.noDocumentProjects),'HGAB-only rows without a Proposal or scanned Senate document match'],[peso(S.amountPesos),'combined listed allocation'],[fmt(S.withNoSelectedNep),'without a selected NEP counterpart'],[fmt(S.withinStageRepeatCandidates),'with a within-stage repeat candidate']].map(x=>`<div class="stat"><strong>${esc(x[0])}</strong><span>${esc(x[1])}</span></div>`).join('');const denominator=Number(scan.denominatorProjectRows||allDocs.denominatorProjectRows||0),matched=Number(scan.combinedMatchedProjectRows||0),unmatched=Math.max(0,denominator-matched),matchedPct=denominator?100*matched/denominator:0,unmatchedPct=100-matchedPct,allocation=S.senateTitleMatchAllocation||{},totalPesos=Number(allocation.totalPesos||0),matchedPesos=Number(allocation.matchedPesos||0),unmatchedPesos=Math.max(0,totalPesos-matchedPesos),reportedItems=Number(S.gabRemovedItemsReported||295),reportedPesos=Number(S.gabRemovedPesosReported||8836000000),itemMarker=denominator?100*reportedItems/denominator:0,pesoMarker=totalPesos?100*reportedPesos/totalPesos:0;document.getElementById('senate-coverage-heading').textContent=`${fmt(matched)} of ${fmt(denominator)} HGAB-only project rows (${matchedPct.toFixed(2)}%) now have a Senate document title match.`;document.getElementById('gab-highlight').innerHTML=`<span>${matchedPct.toFixed(2)}% have a BP 202 / POW title match</span><span>${fmt(allDocs.projectsWithAtLeastOneMatchedDocument||0)} have any supporting-file match across all types</span>`;document.getElementById('gab-bars').innerHTML=[[`Project rows`,fmt(matched),fmt(unmatched),matchedPct,unmatchedPct,`${fmt(reportedItems)} items`,itemMarker],[`HGAB allocation`,peso(matchedPesos),peso(unmatchedPesos),totalPesos?100*matchedPesos/totalPesos:0,totalPesos?100*unmatchedPesos/totalPesos:0,peso(reportedPesos),pesoMarker]].map(([label,found,notFound,foundPct,notFoundPct,markerValue,markerPct])=>`<div class="gab-bar-row"><div class="gab-bar-label"><strong>${label}</strong><div class="gab-count-line"><span>title match</span><strong>${found}</strong></div><div class="gab-count-line"><span>no title match</span><strong>${notFound}</strong></div><div class="gab-count-line gab-reference-label"><span>reported Senate/GAB removal</span><strong>${markerValue}</strong></div></div><div class="gab-stack" role="img" aria-label="${foundPct.toFixed(2)} percent title matched; ${notFoundPct.toFixed(2)} percent without title match; ${markerValue}, shown as an unmatched aggregate reference"><span class="gab-remain" style="width:${foundPct}%"></span><span class="gab-removed" style="width:${notFoundPct}%"></span><span class="gab-reference-marker" style="left:${Math.max(0,Math.min(100,markerPct))}%" title="${markerValue}"></span></div></div>`).join('');
const hs=D.hgabPowSummary||{};let powRows=[],powLoaded=false,powLoadedFiles=0;document.getElementById('pow-stats').innerHTML=[[fmt(hs.parsedDocuments),'Senate POW files in the HGAB-only document-gap cohort'],[fmt(hs.documentsWithBillRows),'files with recovered bill rows'],[fmt(hs.billRows),'machine-extracted bill rows in this HGAB-only cohort']] .map(a=>`<div class="stat"><strong>${esc(a[0])}</strong><span>${esc(a[1])}</span></div>`).join('');document.getElementById('pow-match-scope').textContent=`This table covers ${fmt(hs.parsedDocuments)} files assigned to HGAB-only project rows with a Proposal document gap: ${fmt(hs.exactTitleMatchedFiles)} exact-title matches and ${fmt(hs.relaxedTitleMatchedFiles)} reviewed relaxed-title matches. Other parsed HGAB files are excluded from this page.`;let pp=0;function drawPow(){const term=document.getElementById('pow-q').value.trim().toLowerCase(),rows=powRows.filter(r=>[r.code,r.hgabTitle,r.hgabId,r.description,r.costCategory,r.status,r.itemCode].join(' ').toLowerCase().includes(term)),size=25,pages=Math.max(1,Math.ceil(rows.length/size));pp=Math.min(pp,pages-1);document.getElementById('pow-rows').innerHTML=rows.slice(pp*size,(pp+1)*size).map(r=>`<tr><td>${esc(r.code)}</td><td>${r.hgabId?`${esc(r.hgabTitle||r.hgabId)}<div class="small">${esc(r.hgabId)}${r.cohortStatus==='outside_transparency_link_gap_cohort'?' · outside this link-gap cohort':''}</div>`:esc(r.matchStatus==='ambiguous_exact_title_match'?'Ambiguous repeated title · not assigned':'No exact title match')}</td><td>${esc(r.status)}</td><td>${esc(r.description||'Unrecovered description')}${r.itemCode?`<div class="small">Item ${esc(r.itemCode)}</div>`:''}</td><td class="num">${r.quantity==null?'—':fmt(r.quantity)}</td><td>${esc(r.unit||'—')}</td><td class="num">${r.amountPesos==null?'—':peso(r.amountPesos)}</td><td>${esc(r.costCategory||'—')}</td><td>${r.sourcePage==null?'—':fmt(r.sourcePage)}</td></tr>`).join('')||(powLoaded?'<tr><td colspan="9">No parsed records match this filter.</td></tr>':'<tr><td colspan="9">Loading parsed POW results…</td></tr>');document.getElementById('pow-page').textContent=rows.length?`Page ${pp+1} of ${pages} · ${fmt(rows.length)} loaded records`:(powLoaded?'No records':'Loading…');document.getElementById('pow-prev').disabled=pp===0;document.getElementById('pow-next').disabled=pp+1>=pages}document.getElementById('pow-q').oninput=()=>{pp=0;drawPow()};document.getElementById('pow-prev').onclick=()=>{pp--;drawPow()};document.getElementById('pow-next').onclick=()=>{pp++;drawPow()};drawPow();const powLoadStatus=document.getElementById('pow-load-status'),powShardNames=D.powShards||[];async function loadPowShards(){if(!powShardNames.length){powLoaded=true;powLoadStatus.textContent='No parsed POW data shards are listed in the current manifest.';drawPow();return}try{for(let i=0;i<powShardNames.length;i+=2){const names=powShardNames.slice(i,i+2),chunks=await Promise.all(names.map(name=>fetch(name+'?v=__DATA_VERSION__').then(r=>{if(!r.ok)throw Error('Could not load parsed POW shard '+name+' ('+r.status+')');return r.json()})));for(const chunk of chunks){for(const doc of chunk){if(doc.rows?.length)for(const row of doc.rows)powRows.push({...row,code:doc.code,status:doc.status,matchStatus:doc.matchStatus,hgabTitle:doc.hgabTitle,hgabId:doc.hgabId,cohortStatus:doc.cohortStatus});else powRows.push({code:doc.code,status:doc.status,matchStatus:doc.matchStatus,hgabTitle:doc.hgabTitle,hgabId:doc.hgabId,cohortStatus:doc.cohortStatus,description:'No bill rows recovered'})}}powLoadedFiles+=chunks.reduce((n,chunk)=>n+chunk.length,0);powLoaded=powLoadedFiles>=Number(hs.parsedDocuments||0);powLoadStatus.textContent=`Loaded ${fmt(powRows.length)} parsed rows from ${fmt(powLoadedFiles)} of ${fmt(hs.parsedDocuments)} POW files${powLoaded?' · complete':' · loading more…'}`;drawPow()}}catch(e){powLoadStatus.textContent=`Parsed POW results are incomplete: ${e.message}`;powLoaded=true;drawPow();console.error(e)}}loadPowShards();
const q=document.getElementById('q'),flag=document.getElementById('flag'),program=document.getElementById('program'),region=document.getElementById('region'),crosswalk=document.getElementById('crosswalk'),sort=document.getElementById('sort');[...new Set(D.projects.map(x=>x.flagCount))].sort((a,b)=>a-b).forEach(x=>flag.insertAdjacentHTML('beforeend',`<option value="${x}">${x} flags</option>`));[...new Set(D.projects.map(x=>x.program).filter(Boolean))].sort().forEach(x=>program.insertAdjacentHTML('beforeend',`<option>${esc(x)}</option>`));[...new Set(D.projects.map(x=>x.region).filter(Boolean))].sort().forEach(x=>region.insertAdjacentHTML('beforeend',`<option>${esc(x)}</option>`));let pg=0,selected=null;function filtered(){let a=D.projects.filter(x=>(!q.value||[x.title,x.office,x.region,x.program,(x.districts||[]).join(' ')].join(' ').toLowerCase().includes(q.value.toLowerCase()))&&(!flag.value||String(x.flagCount)===flag.value)&&(!program.value||x.program===program.value)&&(!region.value||x.region===region.value)&&(!crosswalk.value||(crosswalk.value==='mapped'?x.deoLegCrosswalk.length>0:x.deoLegCrosswalk.length===0)));if(sort.value==='amount')a.sort((x,y)=>y.amountPesos-x.amountPesos);else if(sort.value==='title')a.sort((x,y)=>x.title.localeCompare(y.title));else a.sort((x,y)=>y.flagCount-x.flagCount||y.amountPesos-x.amountPesos);return a}function exportCsv(){const rows=filtered(),cols=['HGAB ID','Project','Allocation pesos','Program','DEO','Region','Source volume','Source page','Document lookup status','NEP pairing','NEP counterpart','Review flags','Flag evidence','Historical GAA candidates','Within-stage repeat candidates','LEG crosswalk evidence','Senate-provided HGAB POW match status','advance-copy HGAB POW bill rows'];const cell=v=>'\"'+String(v??'').replaceAll('\"','\"\"')+'\"';const lines=[cols,...rows.map(x=>[x.id,x.title,x.amountPesos,x.program,x.office,x.region,x.sourceVolume,x.sourcePage,x.documentStatus,x.nepPairStatus,x.nepTitle,x.flags.map(f=>f.label).join('; '),x.flags.map(f=>f.evidence).join('; '),x.historicalMatches.map(m=>`FY${m.gaaYear}: ${m.gaaTitle} (\u20b1${m.gaaAmountPesos})`).join('; '),x.withinStageRepeatPairs.map(p=>`${p.kind}: ${(p.left?.projectName||p.left?.title||'')} / ${(p.right?.projectName||p.right?.title||'')}`).join('; '),x.deoLegCrosswalk.map(c=>`${c.leg} [${c.status}; DEO overlap ${fmt(Number(c.deoAreaFraction||0)*100)}%]`).join('; '),x.advanceCopyPowMatchStatus,x.advanceCopyPow.reduce((n,d)=>n+d.rows.length,0)])].map(r=>r.map(cell).join(',')).join('\\r\\n');const blob=new Blob(['\ufeff',lines],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='undocumented-hgab-filtered.csv';a.click();URL.revokeObjectURL(url)}document.getElementById('export').onclick=exportCsv;function draw(){let a=filtered(),size=20,pages=Math.max(1,Math.ceil(a.length/size));pg=Math.min(pg,pages-1);document.getElementById('rows').innerHTML=a.slice(pg*size,(pg+1)*size).map((x,i)=>`<tr data-id="${esc(x.id)}"><td><button class="open">${esc(x.title)}</button><div class="small">${esc(x.id)} · ${esc(x.sourceVolume)} p.${esc(x.sourcePage)}</div></td><td>${esc(x.office)}<br>${esc(x.region)}</td><td>${esc(x.program)}</td><td class="num">${peso(x.amountPesos)}</td><td>${x.flags.map(f=>`<span class="tag redtag" title="${esc(f.evidence)}">${esc(f.label)}</span>`).join('')||'No queue flag'}</td><td>${x.historicalMatches.length?`${x.historicalMatches.length} historical GAA candidate(s)`:''}${x.withinStageRepeatPairs.length?`${x.historicalMatches.length?'<br>':''}${x.withinStageRepeatPairs.length} within-stage pair(s)`:''}${!x.historicalMatches.length&&!x.withinStageRepeatPairs.length?'No repeat candidate':''}</td><td>${esc(x.nepPairStatus)}${x.nepHasDocumentLinks?'<br>Selected NEP counterpart has Transparency links':''}</td><td>${x.advanceCopyPow.length?x.advanceCopyPow.map(d=>`${esc(d.code)} · ${fmt(d.rows.length)} parsed bill rows · PDF link not published`).join('<br>'):x.advanceCopyPowMatchStatus==='ambiguous_title_match'?'Ambiguous exact-title match · not assigned':x.advanceCopyPowMatchStatus==='title_match_not_assessed'?'Title match not assessed for all parsed POW files':'No exact-title advance-copy POW match in parsed files'}</td><td>${x.deoLegCrosswalk.length?x.deoLegCrosswalk.slice(0,5).map(c=>`${esc(c.leg)} (${esc(c.status)})`).join('<br>')+(x.deoLegCrosswalk.length>5?`<br>+${x.deoLegCrosswalk.length-5} more`: ''):'No spatial DEO–LEG row'}<div class="small">Queue district lead: ${esc(x.districts.join('; ')||'none')}</div></td></tr>`).join('');document.getElementById('page').textContent=`${a.length?pg*size+1:0}–${Math.min((pg+1)*size,a.length)} of ${fmt(a.length)}`;document.getElementById('prev').disabled=pg===0;document.getElementById('next').disabled=pg>=pages-1;document.querySelectorAll('.open').forEach(b=>b.onclick=()=>{selected=b.closest('tr').dataset.id;detail()})}function detail(){const x=D.projects.find(p=>p.id===selected),d=document.getElementById('detail');if(!x)return;d.hidden=false;d.innerHTML=`<h2>${esc(x.title)}</h2><p>${esc(x.office)} · ${esc(x.region)} · ${esc(x.program)} · ${peso(x.amountPesos)}</p><p><b>Document result:</b> no document record was found in the DPWH Transparency portal or Senate-provided HGAB files verified against this project, either directly or through a selected NEP counterpart. <b>DEO–LEG crosswalk:</b> ${x.deoLegCrosswalk.length?x.deoLegCrosswalk.map(c=>`${esc(c.leg)} · ${esc(c.status)} · DEO overlap ${fmt(Number(c.deoAreaFraction||0)*100)}%`).join('; '):'No spatially intersecting LEG row in the current crosswalk.'} This is spatial evidence, not project attribution. <b>NEP pairing:</b> ${esc(x.nepPairStatus)} ${x.nepTitle?`· ${esc(x.nepTitle)}`:''}</p><h3>Review flags</h3>${x.flags.length?x.flags.map(f=>`<p><b>${esc(f.label)}</b> · ${esc(f.evidence)}</p>`).join(''):'No line-item review-queue flags joined by HGAB ID.'}<h3>Senate-provided HGAB POW parsed results</h3>${x.advanceCopyPow.length?x.advanceCopyPow.map(d=>`<p><b>${esc(d.code)}</b> · ${esc(d.status)} · ${fmt(d.rows.length)} recovered bill rows · PDF link not published. Match: exact normalized project title in POW text.</p>${d.costCategoryBreakdown.length?`<p>Printed category totals: ${d.costCategoryBreakdown.map(c=>`${esc(c.label)} ${c.sharePct==null?'':fmt(c.sharePct)+'%'} · ${peso(c.amountPesos)}`).join('; ')}</p>`:''}<div class="tablewrap"><table><thead><tr><th>Item</th><th>Description</th><th>Quantity</th><th>Unit</th><th>Amount</th><th>Page</th></tr></thead><tbody>${d.rows.map(r=>`<tr><td>${esc(r.itemCode||'—')}</td><td>${esc(r.description||'—')}</td><td>${r.quantity==null?'—':fmt(r.quantity)}</td><td>${esc(r.unit||'—')}</td><td class="num">${r.amountPesos==null?'—':peso(r.amountPesos)}</td><td>${r.sourcePage==null?'—':fmt(r.sourcePage)}</td></tr>`).join('')||'<tr><td colspan="6">No bill rows recovered.</td></tr>'}</tbody></table></div>`).join(''):x.advanceCopyPowMatchStatus==='ambiguous_title_match'?`<p>Potential exact-title matches in advance-copy POW documents (${x.advanceCopyPowAmbiguousCodes.map(esc).join(', ')}); repeated House titles make the row assignment ambiguous, so no parsed values are attached.</p>`:'<p>No exact-title match in the parsed Senate-provided HGAB POW files currently loaded.</p>'}<h3>Repeat candidates</h3>${x.historicalMatches.map(m=>`<p>FY${esc(m.gaaYear)} · ${esc(m.gaaTitle)} · ${peso(m.gaaAmountPesos)} · ${esc(m.chainageStatus||'title candidate')}</p>`).join('')||'<p>No historical GAA candidate joined.</p>'}${x.withinStageRepeatPairs.map(p=>`<p>${esc(p.kind)} · ${esc(p.left?.projectName||p.left?.title||'')} ↔ ${esc(p.right?.projectName||p.right?.title||'')} · title similarity ${fmt((p.titleSimilarity||0)*100)}%</p>`).join('')}${x.evidenceCautions?.length?`<h3>Cautions</h3><ul>${x.evidenceCautions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul>`:''}`}document.getElementById('prev').onclick=()=>{pg--;draw()};document.getElementById('next').onclick=()=>{pg++;draw()};[q,flag,program,region,crosswalk,sort].forEach(x=>x.oninput=x.onchange=()=>{pg=0;draw()});document.getElementById('source-note');draw();}).catch(e=>{document.querySelector('main').insertAdjacentHTML('afterbegin',`<div class="warning red">${e.message}</div>`)});</script></body></html>'''
    coverage_table='''<section id="all-hgab-document-coverage" class="card" data-hgab-coverage-source="hgab-only-document-coverage.json?v=__COVERAGE_EXPORT_VERSION__"><h2>All HGAB-only projects · document matches and signatories</h2><p>One row per HGAB-only project. Proposal links and Senate-provided HGAB files are marked separately. Signatories are document-extracted candidates, not verified current officials or project sponsors. Document presence does not verify contents.</p><p><a href="hgab-only-document-coverage.json?v=__COVERAGE_EXPORT_VERSION__" download>Download all HGAB-only rows as JSON ↗</a></p><div class="controls"><label for="coverage-search">Search projects or signatories</label><input id="coverage-search" type="search" placeholder="HGAB code, title, office, signatory…"><span id="coverage-count" aria-live="polite"></span></div><div class="tablewrap"><table><thead><tr><th>HGAB code</th><th>Project</th><th>Office · region</th><th>HGAB allocation</th><th>Proposal docs</th><th>Senate HGAB docs</th><th>Signatories in related documents</th></tr></thead><tbody id="coverage-rows"><tr><td colspan="7">Loading HGAB-only document coverage…</td></tr></tbody></table></div><div class="pagination"><button id="coverage-prev" type="button" disabled>Previous</button><span id="coverage-page"></span><button id="coverage-next" type="button" disabled>Next</button><label for="coverage-page-size">Rows</label><select id="coverage-page-size"><option>25</option><option selected>50</option><option>100</option></select></div></section>'''
    marker='<div id="detail" class="card" hidden></div></main><script>'
    if marker not in html: raise SystemExit('Could not find the bottom insertion point for HGAB-only coverage table')
    html=html.replace(marker,'<div id="detail" class="card" hidden></div>'+coverage_table+'</main><script>',1)
    html=html.replace('__COVERAGE_EXPORT_VERSION__',coverage_export_version)
    html=html.replace('__HGAB_DOCUMENT_COVERAGE__',coverage_fallback)
    html=html.replace('__SNAPSHOT__',indepth['hgabCoverage'].get('snapshotRetrievedAtUtc') or 'not stated')
    html=html.replace('__DATA_VERSION__',data_version)
    html=apply_table_presentation(
        apply_report_chrome(html,'undocumented-hgab.html'),
        publish_table_assets(),
        'undocumented-hgab.html',
    )
    coverage_section=re.search(r'<section[^>]*id="all-hgab-document-coverage"[^>]*>.*?</section>',html,re.S)
    coverage_head=re.search(r'<thead>(.*?)</thead>',coverage_section.group(0),re.S) if coverage_section else None
    coverage_headers=[re.sub(r'<[^>]+>','',header).strip() for header in re.findall(r'<th\b[^>]*>(.*?)</th>',coverage_head.group(1),re.S)] if coverage_head else []
    expected_coverage_headers=['HGAB code','Project','Office · region','HGAB allocation','Proposal docs','Senate HGAB docs','Signatories in related documents']
    coverage_project_rows=len(coverage_export.get('projects',[]))
    coverage_renderer=(ROOT/'project_documents/hgab-document-coverage.js').read_text()
    coverage_renderer_version=hashlib.sha256(coverage_renderer.encode('utf-8')).hexdigest()[:12]
    if 'src=\"hgab-document-coverage.js' not in html:
        html=html.replace('</body></html>',f'<script src=\"hgab-document-coverage.js?v={coverage_renderer_version}\"></script></body></html>',1)
    else:
        html=re.sub(r'src=\"hgab-document-coverage\.js(?:\?v=[^\"]*)?\"',f'src=\"hgab-document-coverage.js?v={coverage_renderer_version}\"',html,count=1)
    if (coverage_headers != expected_coverage_headers or not coverage_project_rows
            or 'id="report-table-readability-style"' not in html
            or 'id="report-table-readability-script"' not in html):
        raise RuntimeError(
            'HGAB-only coverage table validation failed: '
            f'headers={coverage_headers!r}, {coverage_project_rows} project rows, '
            'or shared table styling is missing'
        )
    for folder in (OUT,STATIC):
        (folder/'undocumented-hgab-data.json').write_text(payload)
        (folder/'hgab-only-document-coverage.json').write_text(coverage_export_json)
        (folder/'hgab-document-coverage.js').write_text(coverage_renderer)
        if support_payload is not None:
            (folder/'senate-hgab-only-document-stats.json').write_text(support_payload)
        keep=set(shard_names)
        for old_shard in folder.glob('undocumented-hgab-projects-*.json'):
            if old_shard.name not in keep: old_shard.unlink()
        keep_pow=set(pow_shard_names)
        for old_shard in folder.glob('undocumented-hgab-pow-*.json'):
            if old_shard.name not in keep_pow: old_shard.unlink()
        for name,content in zip(shard_names,shard_payloads):
            (folder/name).write_text(content)
        for name,content in zip(pow_shard_names,pow_payloads):
            (folder/name).write_text(content)
    for p in (OUT/'undocumented-hgab.html',STATIC/'undocumented-hgab.html'): p.write_text(html)
    print(json.dumps(data['summary'],indent=2))
if __name__=='__main__':main()
