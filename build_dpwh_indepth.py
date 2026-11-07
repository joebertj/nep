#!/usr/bin/env python3
"""Publish whitelisted parsed document evidence; never publish raw cache files."""
import json,html,shutil,hashlib,uuid,re,unicodedata,statistics,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
CACHE=ROOT/'data_sources/dpwh_project_documents/on_demand'
BULK_CACHE=ROOT/'data_sources/dpwh_project_documents/parsed_pow'
UNMATCHED={'not_found','no_verified_match','candidate_match','ambiguous_match','outside_snapshot_scope'}
PRIMARY_POW_PROJECT_GROUPS=('Bridges','Roads','Irrigation','Multi-Purpose Buildings (MPB)')
def title_key(value):return ' '.join(unicodedata.normalize('NFKC',str(value or '')).split())
def category_base_key(value):
    key=unicodedata.normalize('NFKC',str(value or '')).casefold()
    return re.sub(r'[^a-z0-9]+',' ',key).strip()

CATEGORY_MERGE_DATA=json.loads((ROOT/'project_documents/pow_summary_category_merges.json').read_text())
CATEGORY_MERGES={}
CATEGORY_LABELS={}
for group in CATEGORY_MERGE_DATA.get('groups',[]):
    canonical=category_base_key(group.get('canonical'))
    if not canonical:continue
    CATEGORY_LABELS[canonical]=str(group.get('canonical'))
    CATEGORY_MERGES[canonical]=canonical
    for variant in group.get('variants',[]):CATEGORY_MERGES[category_base_key(variant)]=canonical

BILL_MERGE_DATA=json.loads((ROOT/'project_documents/pow_bill_merges.json').read_text())
BILL_MERGES={}
BILL_LABELS={}
for group in BILL_MERGE_DATA.get('groups',[]):
    canonical=category_base_key(group.get('canonical'))
    if not canonical:continue
    BILL_LABELS[canonical]=str(group.get('canonical'))
    BILL_MERGES[canonical]=canonical
    for variant in group.get('variants',[]):BILL_MERGES[category_base_key(variant)]=canonical

def category_key(value):
    base=category_base_key(value)
    return CATEGORY_MERGES.get(base,base)

def has_kind(project,kind):
    for d in project.get('documentLinks',[]):
        t=' '.join(str(d.get('type') or '').lower().split())
        if kind=='development_council' and re.search(
                r'\b(?:rdc|pdc|ldc)\d*\b|\b(?:regional|provincial|local) development council\b',t):
            return True
        if kind=='pow' and (t=='pow' or 'program of work' in t):return True
        if kind=='photos' and 'geotagged' in t and 'photo' in t:return True
        if kind=='rdc' and ('rdc' in t or 'regional development council' in t):return True
        if kind=='bp202' and re.search(r'(?<!\w)bp\s*202(?!\w)',t):return True
        if kind=='implementability' and 'certificate of implementability' in t:return True
    return False
def unit_key(value):
    s=unicodedata.normalize('NFKC',str(value or '')).lower().strip().replace('²','2').replace('³','3')
    s=re.sub(r'[^a-z0-9]+',' ',s).strip()
    aliases={'kg':'kg','kgs':'kg','kilogram':'kg','kilograms':'kg','cu m':'cu m','cubic meter':'cu m','cubic meters':'cu m','m3':'cu m','sq m':'sq m','square meter':'sq m','square meters':'sq m','m2':'sq m','ls':'lump sum','l s':'lump sum','lump sum':'lump sum','ea':'each','each':'each','unit':'each'}
    return aliases.get(s,s)

def summary_peer_family(name):
    """Group major project types; retain shared titles for other projects."""
    value=title_key(name)
    if re.search(r'\b(?:multi\s*[- ]?purpose\s+building|mpb)\b',value,re.I):return 'Multi-Purpose Buildings (MPB)'
    if re.search(r'\birrigation\b',value,re.I):return 'Irrigation'
    if re.search(r'\bbridges?\b',value,re.I):return 'Bridges'
    if re.search(r'\broads?\b',value,re.I):return 'Roads'
    value=re.sub(r'\s+[–—-]\s+.*\b(?:District Engineering Office|Regional Office)\b.*$', '', value, flags=re.I)
    value=re.sub(r'\s+[–—-]\s+.*\b(?:National Capital Region|Cordillera Administrative Region|Region\s+[IVXLC0-9-]+|NCR|CAR)\s*$', '', value, flags=re.I)
    value=re.sub(r'\s+',' ',value).strip(' -–—,;')
    return value

def summary_peer_groups(projects):
    """Keep peer POW projects and each printed category/page as traceable evidence."""
    grouped={}
    for project in projects:
        docs=[d for d in project.get('documents',[]) if d.get('kind')=='pow']
        if not docs:continue
        family=summary_peer_family(project.get('name',''))
        if not family:continue
        key=family.casefold()
        group=grouped.setdefault(key,{'family':family,'projects':{},'summaryProjects':set(),'detailProjects':set(),'observations':[]})
        group['projects'][project.get('code')]={'code':project.get('code'),'name':project.get('name'),'office':project.get('office')}
        for doc in docs:
            if doc.get('rows'):group['detailProjects'].add(project.get('code'))
            for category in doc.get('costCategoryBreakdown',[]):
                observation={'code':project.get('code'),'name':project.get('name'),'office':project.get('office'),
                    'family':family,'category':category.get('label'),'sharePct':category.get('sharePct'),
                    'submittedAmountPesos':category.get('submittedAmountPesos',category.get('amountPesos')),
                    'evaluatedAmountPesos':category.get('evaluatedAmountPesos'),'sourcePage':category.get('sourcePage'),
                    'url':doc.get('url'),'manualReview':bool(category.get('manualReview'))}
                group['summaryProjects'].add(project.get('code'))
                group['observations'].append(observation)
    results=[]
    for key,group in grouped.items():
        if key not in {x.casefold() for x in PRIMARY_POW_PROJECT_GROUPS} and len(group['projects'])<2:continue
        results.append({'id':hashlib.sha1(key.encode()).hexdigest()[:12],'family':group['family'],
                        'projectCount':len(group['projects']),'summaryProjectCount':len(group['summaryProjects']),
                        'detailProjectCount':len(group['detailProjects']),
                        'projects':sorted(group['projects'].values(),key=lambda p:(str(p.get('office') or '').casefold(),str(p.get('code') or ''))),
                        'observations':group['observations']})
    existing={g['family'].casefold() for g in results}
    for family in PRIMARY_POW_PROJECT_GROUPS:
        if family.casefold() not in existing:
            key=family.casefold()
            results.append({'id':hashlib.sha1(key.encode()).hexdigest()[:12],'family':family,
                            'projectCount':0,'summaryProjectCount':0,'detailProjectCount':0,'projects':[],'observations':[]})
    return sorted(results,key=lambda g:(-g['projectCount'],g['family'].casefold()))

def hgab_statistics(document_projects):
    stage=json.loads((OUT/'dpwh_hgab_2nd_vs_3rd.json').read_text())
    coverage=json.loads((OUT/'dpwh_transparency_document_coverage.json').read_text())
    nep_map=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    projects=[r['third'] for r in stage['rows'] if r.get('third') and r['third'].get('allocationKind')=='project']
    pow_crosswalk=json.loads((OUT/'hgab_pow_title_crosswalk.json').read_text())
    from project_documents.senate_document_title_coverage import load_match_ids
    senate_document_by_hgab=load_match_ids(OUT,include_relaxed=True)
    advanceCopy_by_hgab={}
    for item in pow_crosswalk.get('files',[]):
        if item.get('status')=='exact_title_match':
            for hid in item.get('hgabIds',[]):
                advanceCopy_by_hgab.setdefault(hid,[]).append(item)
    unpaired_ids={r.get('id') for r in nep_map.get('hgabWithoutSelectedCounterpart',[]) if r.get('allocationKind')=='project'}
    titles=coverage.get('titles',{});linked=[];status_counts={}
    by_code={p['code']:p for p in document_projects if p.get('code')}
    source_rows={r['sourceId']:r for r in coverage.get('rows',[]) if r.get('sourceId')}
    pair_by_hgab={p.get('hgabId'):p for p in nep_map.get('pairs',[]) if p.get('hgabId')}
    unpaired=missing_listed=double_flag=0
    direct_listed=paired_listed=listed_any=0
    portal_only_missing=combined_advanceCopy_rows=0
    advanceCopy_file_records=set()
    portal_only_missing_amount=combined_missing_amount=0
    document_urls=set()
    for row in projects:
        entry=titles.get(title_key(row.get('projectName')))
        status=entry.get('status','unmapped') if entry else 'unmapped'
        status_counts[status]=status_counts.get(status,0)+1
        no_selected_nep=row.get('id') in unpaired_ids
        direct_project=by_code.get(entry.get('code')) if entry and entry.get('code') and status not in UNMATCHED else None
        direct_links=direct_project.get('documentLinks',[]) if direct_project else []
        pair=pair_by_hgab.get(row.get('id'))
        nep_row=source_rows.get((pair.get('nep') or {}).get('id')) if pair else None
        paired_project=by_code.get(nep_row.get('code')) if nep_row and nep_row.get('code') else None
        paired_links=paired_project.get('documentLinks',[]) if paired_project else []
        direct_has_docs=bool(direct_links)
        paired_has_docs=bool(paired_links)
        linked_docs={str(d.get('url')):d for d in [*direct_links,*paired_links] if d.get('url')}
        portal_docs_listed=bool(linked_docs)
        advanceCopy_files=advanceCopy_by_hgab.get(row.get('id'),[])
        scanned_senate_files=senate_document_by_hgab.get(row.get('id'),set())
        docs_listed=portal_docs_listed or bool(advanceCopy_files) or bool(scanned_senate_files)
        direct_listed+=direct_has_docs
        paired_listed+=paired_has_docs
        listed_any+=docs_listed
        if advanceCopy_files or scanned_senate_files:
            combined_advanceCopy_rows+=1
            advanceCopy_file_records.update(scanned_senate_files)
            advanceCopy_file_records.update(('pow',item.get('code')) for item in advanceCopy_files if item.get('code'))
        document_urls.update(linked_docs)
        unpaired+=no_selected_nep
        missing_listed+=not docs_listed
        portal_only_missing+=not portal_docs_listed
        if not portal_docs_listed:portal_only_missing_amount+=float(row.get('amountPesos') or 0)
        if not docs_listed:combined_missing_amount+=float(row.get('amountPesos') or 0)
        double_flag+=no_selected_nep and not docs_listed
        if entry and entry.get('code') and status not in UNMATCHED:
            linked.append((row,entry))
    inspected=[(row,entry,by_code[entry['code']]) for row,entry in linked
               if entry['code'] in by_code and by_code[entry['code']].get('documentLinks')]
    required_types=('bp202','implementability','pow','photos','development_council')
    types={k:sum(has_kind(p,k) for _,_,p in inspected) for k in required_types}
    missing_any=sum(not all(has_kind(p,k) for k in required_types) for _,_,p in inspected)
    coverage_data={'stage':'HGAB 3rd reading','projectRows':len(projects),'linkedRows':len(linked),'linkedPct':round(100*len(linked)/len(projects),1) if projects else 0,
      'directListedRows':direct_listed,'pairedNepRowsWithListedDocuments':paired_listed,
      'listedAnyRows':listed_any,'listedAnyPct':round(100*listed_any/len(projects),1) if projects else 0,
      'portalOnlyListedAnyRows':len(projects)-portal_only_missing,
      'portalOnlyMissingListedDocumentsRows':portal_only_missing,
      'portalOnlyMissingListedDocumentsAmountPesos':round(portal_only_missing_amount),
      'advanceCopyExactTitleMatchedRows':combined_advanceCopy_rows,
      'advanceCopyExactTitleMatchedFiles':len(advanceCopy_file_records),
      'combinedMissingListedDocumentsAmountPesos':round(combined_missing_amount),
      'listedDocumentRecords':len(document_urls),
      'inspectedRows':len(inspected),'inspectedPct':round(100*len(inspected)/len(linked),1) if linked else 0,
      'missingAnyTypeRows':missing_any,'missingAnyTypePct':round(100*missing_any/len(inspected),1) if inspected else 0,
      'noSelectedNepRows':unpaired,'noSelectedNepPct':round(100*unpaired/len(projects),1) if projects else 0,
      'missingListedDocumentsRows':missing_listed,'doubleRedFlagRows':double_flag,'doubleRedFlagPct':round(100*double_flag/len(projects),1) if projects else 0,
      'missingTypes':{k:{'count':len(inspected)-v,'pct':round(100*(len(inspected)-v)/len(inspected),1) if inspected else 0} for k,v in types.items()},
      'statusCounts':status_counts,'sourceCommit':coverage.get('sourceCommit'),'snapshotRetrievedAtUtc':coverage.get('snapshotRetrievedAtUtc'),
      'documentCoverageMethod':'A project is counted as having Senate document evidence when a first-page native-text scan finds an exact normalized title or conservative relaxed POW title candidate in a Senate-provided BP 202 or POW file, or the existing advance-copy POW crosswalk assigns a unique exact title. DPWH Transparency Proposal links remain separate. This is file-presence evidence, not content verification; POW bill extraction may lag.'}
    grouped={};display_names={}
    for row,entry,project in inspected:
        docs=[d for d in project.get('documents',[]) if d.get('kind')=='pow']
        for doc in docs:
            candidates={}
            for bill in doc.get('rows',[]):
                desc=' '.join(unicodedata.normalize('NFKC',str(bill.get('description') or '')).split())
                unit=unit_key(bill.get('unit'));basis=bill.get('costBasis') or 'not_stated'
                try:q=float(bill.get('quantity'));amount=float(bill.get('amountPesos'))
                except (TypeError,ValueError):continue
                if not desc or not unit or q<=0 or amount<=0:continue
                key=(re.sub(r'[^a-z0-9]+',' ',desc.lower()).strip(),unit,basis)
                display_names.setdefault(key,desc)
                g=candidates.setdefault(key,{'description':desc,'unit':unit,'basis':basis,'quantity':0.0,'amount':0.0,'url':doc.get('url'),'pages':set()})
                g['quantity']+=q;g['amount']+=amount
                if bill.get('sourcePage'):g['pages'].add(bill['sourcePage'])
            for key,g in candidates.items():
                if g['quantity']<=0:continue
                grouped.setdefault(key,[]).append({'code':entry['code'],'name':row.get('projectName'),'office':row.get('office'),'region':row.get('region'),'quantity':round(g['quantity'],4),'amountPesos':round(g['amount'],2),'ratePesos':round(g['amount']/g['quantity'],4),'url':g['url'],'pages':sorted(g['pages'])})
    peer_groups=[]
    for (norm,unit,basis),obs in grouped.items():
        # One HGAB project proposal per peer observation.
        unique={o['code']:o for o in obs};obs=list(unique.values())
        if len(obs)<5:continue
        rates=[o['ratePesos'] for o in obs];q1,med,q3=statistics.quantiles(rates,n=4,method='inclusive')[0],statistics.median(rates),statistics.quantiles(rates,n=4,method='inclusive')[2]
        low=q1-1.5*(q3-q1);high=q3+1.5*(q3-q1)
        for o in obs:o['outlier']=o['ratePesos']<low or o['ratePesos']>high
        first=obs[0]
        peer_groups.append({'id':hashlib.sha1((norm+'|'+unit+'|'+basis).encode()).hexdigest()[:12],'description':display_names[(norm,unit,basis)],
          'unit':unit,'basis':basis,'count':len(obs),'min':min(rates),'q1':q1,'median':med,'q3':q3,'max':max(rates),'fenceLow':low,'fenceHigh':high,'observations':sorted(obs,key=lambda o:o['ratePesos'])})
    peer_groups.sort(key=lambda g:(-g['count'],g['description'].lower(),g['unit'],g['basis']))
    return coverage_data,peer_groups

def collect_hgab_pow_results(document_projects):
    """Expose parsed HGAB POW evidence and link uniquely selected proposal counterparts."""
    results=[]
    title_crosswalk=json.loads((OUT/'hgab_pow_title_crosswalk.json').read_text())
    title_scan_path=OUT/'senate_pow_hgab_only_title_scan.json'
    title_scan=json.loads(title_scan_path.read_text()) if title_scan_path.is_file() else {'records':[]}
    mapping=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    stage=json.loads((OUT/'dpwh_hgab_2nd_vs_3rd.json').read_text())
    coverage=json.loads((OUT/'dpwh_transparency_document_coverage.json').read_text())
    matches={item.get('code'):item for item in title_crosswalk.get('files',[])}
    scan_by_file={str(item.get('file') or '').replace('\\','/'):item
                  for item in title_scan.get('records',[]) if item.get('file')}
    proposal_by_title={}
    for project in document_projects:
        key=category_base_key(project.get('name'))
        if key:proposal_by_title.setdefault(key,[]).append(project.get('code'))
    proposal_by_nep_id={}
    for row in coverage.get('rows',[]):
        if row.get('sourceId') and row.get('code') and row.get('status') not in UNMATCHED:
            proposal_by_nep_id.setdefault(row['sourceId'],set()).add(row['code'])
    proposal_by_hgab_id={}
    hgab_title_by_id={}
    for row in stage.get('rows',[]):
        third=row.get('third') or {}
        if third.get('id') and third.get('projectName'):
            hgab_title_by_id[third['id']]=third['projectName']
    for pair in mapping.get('pairs',[]):
        hgab_id,nep_id=pair.get('hgabId'),pair.get('nepId')
        if hgab_id and nep_id:
            proposal_by_hgab_id.setdefault(hgab_id,set()).update(proposal_by_nep_id.get(nep_id,set()))
    allowed_rows=('itemCode','description','quantity','unit','printedUnitCostPesos',
                  'calculatedUnitCostPesos','amountPesos','sourcePage','arithmeticStatus',
                  'verificationStatus','costBasis','amountBasis','costCategory')
    allowed_categories=('label','sharePct','amountPesos','sourcePage','verificationStatus')
    for path in sorted(BULK_CACHE.glob('2027DPWH-HGAB-*/*/result.json')):
        try:
            parsed=json.loads(path.read_text())
            marker=json.loads((path.parent/'status.json').read_text())
        except (OSError,ValueError):
            continue
        if marker.get('status')!='parsed' or marker.get('parserVersion')!=parsed.get('parserVersion'):
            continue
        if marker.get('sourceSha256')!=parsed.get('sourceSha256'):
            continue
        code=parsed.get('projectCode')
        if not re.fullmatch(r'2027DPWH-HGAB-\d{5}',str(code or '')):
            continue
        rows=[{k:r.get(k) for k in allowed_rows if k in r} for r in parsed.get('rows',[])]
        categories=[{k:r.get(k) for k in allowed_categories if k in r} for r in parsed.get('costCategoryBreakdown',[])]
        # Prefer the current broad first-page scan for the exact source file.
        # The legacy crosswalk covers only a small earlier subset.
        legacy_match=matches.get(code) or {'status':'not_assessed','hgabIds':[]}
        match=legacy_match
        relative_path=str(parsed.get('sourceRelativePath') or '').replace('\\','/')
        marker='Supporting Documents (IO)/'
        if marker in relative_path:
            relative_path=relative_path.split(marker,1)[1]
        scanned=scan_by_file.get(relative_path)
        if scanned is not None:
            match={'status':scanned.get('matchStatus','not_assessed'),
                   'hgabIds':scanned.get('matchedHgabIds',[]),
                   'matchedTitle':(scanned.get('matchedHgabTitles') or [None])[0],
                   'cohortStatus':'in_transparency_link_gap_cohort' if scanned.get('matchedHgabIds') else None}
        exact=match.get('status')=='exact_title_match'
        unique_candidate=match.get('status') in {'exact_title_match','relaxed_title_match'}
        # The broad title scan is newer than the legacy crosswalk. Use its
        # matched title to link a unique Proposal counterpart when possible.
        title_code=proposal_by_title.get(category_base_key(match.get('matchedTitle')),[]) if match.get('status')=='exact_title_match' else []
        linked_proposals=set().union(*(proposal_by_hgab_id.get(hid,set()) for hid in legacy_match.get('hgabIds',[]))) if legacy_match.get('status')=='exact_title_match' else set()
        # Exact proposal-title matches take precedence. Otherwise use only the
        # existing selected NEP–HGAB pairing, and publish a link when it resolves
        # to one Proposal code without ambiguity.
        proposal_code=title_code[0] if exact and len(title_code)==1 else next(iter(linked_proposals)) if len(linked_proposals)==1 else None
        proposal_link_basis=('exact_title_match' if exact and len(title_code)==1 else
                             'selected_nep_hgab_pair' if proposal_code else None)
        results.append({'code':code,'status':parsed.get('status'),'pageCount':parsed.get('pageCount'),
                        'matchStatus':match.get('status','no_exact_title_match'),
                        'hgabId':match.get('hgabIds',[None])[0] if unique_candidate and match.get('hgabIds') else None,
                        'candidateHgabIds':match.get('hgabIds',[]) if match.get('status')=='ambiguous_exact_title_match' else [],
                        'cohortStatus':match.get('cohortStatus'),
                        'hgabTitle':(match.get('matchedTitle') if unique_candidate else None) or hgab_title_by_id.get(match.get('hgabIds',[None])[0] if match.get('hgabIds') else None),
                        'proposalCode':proposal_code,'proposalLinkBasis':proposal_link_basis,
                        'allocationPesos':parsed.get('allocationPesos'),'rows':rows,
                        'costCategoryBreakdown':categories})
    results.sort(key=lambda x:x['code'])
    return results

def merge_pow_results(existing,bulk):
    """Merge bulk extraction evidence without discarding richer saved fields."""
    def norm(value):return re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKC',str(value or '')).casefold()).strip()
    def blank(value):return value is None or value=='' or value==[] or value=={}
    def merge_list(old_rows,new_rows,key):
        merged=[dict(row) for row in old_rows or []]
        for incoming in new_rows or []:
            incoming=dict(incoming);identity=key(incoming)
            match=next((row for row in merged if key(row)==identity),None)
            if match is None and identity[0] is not None and len(identity)>1 and identity[1]:
                match=next((row for row in merged if key(row)[:2]==identity[:2]),None)
            if match is None:
                merged.append(incoming);continue
            for field,value in incoming.items():
                if blank(match.get(field)) and not blank(value):match[field]=value
        return merged
    def row_key(row):
        return (row.get('sourcePage'),str(row.get('itemCode') or ''),norm(row.get('description')),
                str(row.get('quantity') or ''),str(row.get('amountPesos') or ''))
    def category_key(row):return (row.get('sourcePage'),norm(row.get('label')))
    def page_key(row):return (row.get('page'),)
    def control_key(row):return (row.get('sourcePage'),norm(row.get('basis')),norm(row.get('amountBasis')))
    merged=dict(existing)
    merged['rows']=merge_list(existing.get('rows'),bulk.get('rows'),row_key)
    merged['costCategoryBreakdown']=merge_list(existing.get('costCategoryBreakdown'),bulk.get('costCategoryBreakdown'),category_key)
    merged['pages']=merge_list(existing.get('pages'),bulk.get('pages'),page_key)
    merged['itemizedDirectCostControls']=merge_list(existing.get('itemizedDirectCostControls'),bulk.get('itemizedDirectCostControls'),control_key)
    for field,value in bulk.items():
        if field in {'rows','costCategoryBreakdown','pages','itemizedDirectCostControls'}:continue
        if blank(merged.get(field)) and not blank(value):merged[field]=value
    return merged

def collect():
    from project_documents.signatories import qualified_role
    reviewed_path=ROOT/'project_documents/pow_reviewed_category_totals.json'
    reviewed_config=json.loads(reviewed_path.read_text()) if reviewed_path.exists() else {}
    reviewed=reviewed_config.get('projects',{})
    projects=[];attempted=failed=available=empty=0;errors={}
    bulk_by_code={}
    for bulk_path in sorted(BULK_CACHE.glob('2027DPWH-Proposal-*/*/result.json')):
        try:
            bulk=json.loads(bulk_path.read_text())
            marker=json.loads((bulk_path.parent/'status.json').read_text())
        except (OSError,ValueError):continue
        code=bulk.get('projectCode');doc_id=str(bulk.get('documentId',''))
        if (bulk.get('documentType') or '').strip().casefold()!='pow':continue
        if marker.get('status')!='parsed' or marker.get('parseStatus')=='parser_dependency_missing':continue
        if marker.get('parserVersion')!=bulk.get('parserVersion') or marker.get('sourceSha256')!=bulk.get('sourceSha256'):continue
        if not re.fullmatch(r'2027DPWH-Proposal-\d{5}',str(code or '')) or not doc_id.isdigit():continue
        bulk_by_code.setdefault(code,{})[doc_id]=bulk

    source_projects={}
    for path in sorted(CACHE.glob('*/result.json')):
        try:
            result=json.loads(path.read_text());meta=json.loads((path.parent/'metadata.json').read_text())
        except (OSError,ValueError):continue
        source_projects[meta.get('code')]=(result,meta)
    for code in bulk_by_code:
        if code in source_projects:continue
        try:meta=json.loads((CACHE/code/'metadata.json').read_text())
        except (OSError,ValueError):continue
        source_projects[code]=({'projectCode':code,'documents':[]},meta)

    for code,(result,meta) in sorted(source_projects.items()):
        documents=[]
        source_docs=result.setdefault('documents',[])
        metadata_docs={str(d.get('id')):d for d in meta.get('documents',[]) if d.get('id') is not None}
        for doc_id,bulk in bulk_by_code.get(code,{}).items():
            current_metadata=metadata_docs.get(doc_id)
            if not current_metadata or current_metadata.get('url')!=bulk.get('sourceUrl'):continue
            existing=next((d for d in source_docs if d.get('kind')=='pow' and
                           str((d.get('metadata') or {}).get('id'))==doc_id),None)
            if existing:
                old_sha=existing.get('sha256')
                if old_sha==bulk.get('sourceSha256'):
                    existing['pow']=merge_pow_results(existing.get('pow') or {},bulk)
                    if bulk.get('rows'):
                        existing.pop('previousVersionPow',None)
                else:
                    old_pow=existing.get('pow') or {}
                    if old_pow.get('rows') and not bulk.get('rows'):
                        existing['previousVersionPow']={'sha256':old_sha,'version':existing.get('version'),
                                                        'parsedAtUtc':old_pow.get('parsedAtUtc'),
                                                        'pow':old_pow}
                    existing.update({'status':'available','metadata':current_metadata,
                                     'sha256':bulk.get('sourceSha256'),'pow':bulk,'signatories':{}})
                    if bulk.get('rows'):
                        existing.pop('previousVersionPow',None)
            else:
                source_docs.append({'kind':'pow','status':'available','metadata':current_metadata,
                                    'sha256':bulk.get('sourceSha256'),'pow':bulk,'signatories':{}})
        for d in result.get('documents',[]):
            status=d['status']
            if status not in ('link_only',):
                attempted+=1
                if status=='available':available+=1
                else:
                    failed+=1;key=d.get('error','Unknown').split(':',1)[0];errors[key]=errors.get(key,0)+1
            parsed=d.get('pow',{})
            previous=d.get('previousVersionPow') or {}
            previous_parsed=previous.get('pow') or {}
            row_source_status='current_source_version'
            row_source_sha=d.get('sha256')
            parsed_for_rows=parsed
            if not parsed.get('rows') and previous_parsed.get('rows'):
                parsed_for_rows=previous_parsed
                row_source_status='prior_source_version_retained_current_parse_empty'
                row_source_sha=previous.get('sha256')
            excluded_component_pages=set(reviewed_config.get('excludedComponentBreakdownPages',{}).get(meta.get('code'),[])) if d['kind']=='pow' else set()
            rows=[{k:r.get(k) for k in ('itemCode','description','componentContext','componentContexts','costCategory','quantity','unit','printedUnitCostPesos','inclusiveUnitCostPesos','calculatedUnitCostPesos','amountPesos','directCostSharePct','manualReview','sourcePage','observedPages','extractionMethod','arithmeticStatus','verificationStatus','costBasis','amountBasis')} for r in parsed_for_rows.get('rows',[]) if int(r.get('sourcePage') or 0) not in excluded_component_pages]
            people=[{k:p.get(k) for k in ('name','roleText','kind','sourcePage','extractionMethod','verificationStatus','designationRegistry')} for p in d.get('signatories',{}).get('people',[]) if qualified_role(p.get('roleText',''),d['kind'])]
            controls=[{k:c.get(k) for k in ('sourcePage','basis','amountBasis','printedPesos','recoveredItemRows','recoveredPesos','differencePesos','reconciled')} for c in parsed_for_rows.get('itemizedDirectCostControls',[])]
            categories=list(parsed_for_rows.get('costCategoryBreakdown',[]))
            if d['kind']=='pow':
                for correction in reviewed.get(meta.get('code'),[]):
                    match=next((c for c in categories if category_key(c.get('label'))==category_key(correction.get('label'))),None)
                    if match:match.update(correction)
                    else:categories.append(correction)
            review_pages=[{'page':p.get('page'),'note':p.get('reviewNote')} for p in parsed.get('pages',[]) if p.get('status')=='needs_manual_review']
            categories.sort(key=lambda c:-float(c.get('amountPesos') or 0))
            summary_metadata=parsed_for_rows.get('summaryMetadata',{}) if d['kind']=='pow' else {}
            declared=[f for f in summary_metadata.get('qualitativeFacts',[]) if f.get('kind')=='declared_count']
            has_named=any(f.get('kind')=='named_component' for f in summary_metadata.get('qualitativeFacts',[]))
            generated_scope_note=('The POW states '+', '.join(f.get('printedText','') for f in declared)+'; no named school/building/site breakdown was detected in the parsed pages.' if declared and not has_named else None)
            scope_note=(reviewed_config.get('projectScopeNotes',{}).get(meta.get('code')) or generated_scope_note) if d['kind']=='pow' else None
            parsed_pages=[dict(page) for page in parsed.get('pages',[])]
            for page in parsed_pages:
                if int(page.get('page') or 0) in excluded_component_pages:
                    page.update({'pageRole':'supporting_detail','status':'no_bill_rows_recovered','rows':0,'reviewNote':None})
                    page['method']=(page.get('method') or 'source table')+' · detailed component breakdown; supporting cost analysis excluded from bill rows'
            documents.append({'kind':d['kind'],'status':status,'url':d.get('metadata',{}).get('url'),'sha256':d.get('sha256'),'rowSourceSha256':row_source_sha,'rowSourceStatus':row_source_status,'currentParseStatus':parsed.get('status'),'pageCount':parsed.get('pageCount',d.get('signatories',{}).get('sourcePages')),'pages':parsed_pages,'rows':rows,'costCategoryBreakdown':categories,'summaryMetadata':summary_metadata,'scopeNote':scope_note,'controls':controls,'reviewPages':review_pages,'people':people,'signatoryStatus':d.get('signatories',{}).get('status'),'errorType':d.get('error','').split(':',1)[0] or None})
        if not documents:empty+=1
        projects.append({'code':meta['code'],'name':meta['projectName'],'office':meta.get('office'),'region':meta.get('region'),'allocationPesos':round(float(meta['amount'])*1000),'preparedAt':result.get('preparedAtUtc'),'documents':documents,'documentLinks':[{'type':d.get('documentType'),'url':d.get('url')} for d in meta.get('documents',[])]})
    prepared=[p for p in projects if any(d['rows'] for d in p['documents'])]
    retained_projects=sum(1 for p in projects if any(d['kind']=='pow' and d['rows'] and d.get('rowSourceStatus')=='prior_source_version_retained_current_parse_empty' for d in p['documents']))
    return {'generatedAtUtc':datetime.now(timezone.utc).isoformat(),'stage':'NEP FY2027 proposal documents','projects':projects,'summary':{'projectsWithParsedPow':len(prepared),'projectsWithRetainedPriorPowRows':retained_projects,'parsedPowRows':sum(len(d['rows']) for p in projects for d in p['documents'] if d['kind']=='pow'),'projectsWithSavedResults':len(projects),'projectsWithoutSelectedAttachments':empty,'availableDocuments':available,'failedDocuments':failed,'attemptedDocuments':attempted,'errorTypes':errors},'source':'https://api.dpwh.bettergov.ph','scope':'This snapshot covers linked DPWH project-document records available for review; it is not a whole-program inventory. Original files remain available through cited sources.'}
def atomic_write(path,text):
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temporary.write_text(text);temporary.replace(path)

def publish_split_data():
    # The data refresh watcher consumes this command's stdout as one JSON
    # summary. Keep the splitter's own report from becoming a second JSON value.
    subprocess.run([sys.executable,str(ROOT/'split_dpwh_indepth_data.py')],cwd=ROOT,
                   check=True,capture_output=True,text=True)

def publish_pccp_price_reference():
    """Publish the separately parsed regional price-list rows as standalone JSON."""
    source=OUT/'pccp_price_list_parse.json'
    if not source.is_file():return
    try:parsed=json.loads(source.read_text())
    except (OSError,ValueError):return
    rows=[]
    for row in parsed.get('rows',[]):
        rows.append({key:row.get(key) for key in (
            'section','surfaceType','scope','assumption','unit',
            'regionalUnitCostsPesos','sourcePage','verificationStatus')})
    payload={
        'title':'DPWH cost estimates for work items of projects · Table 10',
        'sourceNote':'The source notes material prices from 2022 and road data as of 14 October 2022; it labels rates per kilometer or per linear meter. Verify each row and assumption in the original PDF.',
        'sourceSha256':parsed.get('sourceSha256'),
        'parserStatus':parsed.get('status'),
        'rows':rows,
    }
    serialized=json.dumps(payload,ensure_ascii=False,indent=2)+'\n'
    for target in (OUT,STATIC):atomic_write(target/'pccp-price-reference.json',serialized)

def build_data():
    data=collect();data['powCategoryMerges']=CATEGORY_MERGES;data['powCategoryLabels']=CATEGORY_LABELS;data['powBillMerges']=BILL_MERGES;data['powBillLabels']=BILL_LABELS;data['hgabCoverage'],data['powPeers']=hgab_statistics(data['projects'])
    data['hgabPowResults']=collect_hgab_pow_results(data['projects'])
    cost_row_fields=('description','quantity','unit','amountPesos','sourcePage','costBasis')
    cost_category_fields=('label','sharePct','amountPesos','submittedAmountPesos','evaluatedAmountPesos','sourcePage')
    data['costUnitHgabResults']=[{'code':doc.get('code'),'proposalCode':doc.get('proposalCode'),'hgabId':doc.get('hgabId'),
      'hgabTitle':doc.get('hgabTitle'),'rows':[{k:r.get(k) for k in cost_row_fields if k in r} for r in doc.get('rows',[])],
      'costCategoryBreakdown':[{k:r.get(k) for k in cost_category_fields if k in r} for r in doc.get('costCategoryBreakdown',[])]}
      for doc in data['hgabPowResults'] if doc.get('rows') or doc.get('costCategoryBreakdown')]
    from project_documents.senate_document_title_coverage import load_coverage
    data['senateDocumentTitleCoverage']=load_coverage(OUT)
    supporting_scan_path=OUT/'senate_supporting_documents_hgab_only_scan.json'
    supporting_scan=json.loads(supporting_scan_path.read_text()) if supporting_scan_path.is_file() else {}
    data['senateSupportingDocumentCoverage']={k:supporting_scan.get(k) for k in (
      'denominatorProjectRows','projectsWithAtLeastOneMatchedDocument',
      'projectsWithAtLeastOneMatchedDocumentPct','projectRowsWithoutMatchedDocument',
      'matchedFileRecords','byType','signatoryCandidateCounts',
      'signatoryCandidatesByDocumentType','deduplication','matchingMethod') if k in supporting_scan}
    title_scan_path=OUT/'senate_pow_hgab_only_title_scan.json'
    title_scan=json.loads(title_scan_path.read_text()) if title_scan_path.is_file() else {}
    data['hgabPowSummary']={'parsedDocuments':len(data['hgabPowResults']),
      'documentsWithBillRows':sum(bool(x['rows']) for x in data['hgabPowResults']),
      'billRows':sum(len(x['rows']) for x in data['hgabPowResults']),
      'printedCategories':sum(len(x['costCategoryBreakdown']) for x in data['hgabPowResults']),
      'titleScanDocuments':int(title_scan.get('senateDocumentsScanned') or 0),
      'exactTitleMatchedFiles':int(title_scan.get('exactlyMatchedDocuments') or 0),
      'relaxedTitleMatchedFiles':int(title_scan.get('relaxedMatchedDocuments') or 0),
      'proposalLinkedFiles':sum(bool(x.get('proposalCode')) for x in data['hgabPowResults']),
      'exactTitleMatchedFilesInGapCohort':sum(x.get('cohortStatus')=='in_transparency_link_gap_cohort' and x['matchStatus']=='exact_title_match' for x in data['hgabPowResults']),
      'ambiguousTitleMatchedFiles':int(title_scan.get('ambiguousDocuments') or 0),
      'titleMatchAssessedFiles':int(title_scan.get('senateDocumentsScanned') or 0),
      'titleMatchNotAssessedFiles':0,
      'titleMatchNoExactFiles':int(title_scan.get('documentsWithNoExactTitleMatch') or 0),
      'titleScanErrors':int(title_scan.get('documentsWithScanErrors') or 0),
      'titleScanNoNativeText':int(title_scan.get('documentsWithNoNativeFirstPageText') or 0)}
    data['summaryPeerGroups']=summary_peer_groups(data['projects'])
    data['documentReconciliation']=document_reconciliation(data['projects'])
    return data

def public_data(data):
    """Publish evidence values and source links without internal processing state."""
    public=dict(data)
    summary=data.get('summary',{})
    public['summary']={'projectsWithBillRows':int(summary.get('projectsWithParsedPow') or 0),
                       'billRowCount':int(summary.get('parsedPowRows') or 0),
                       'projectsInReviewSet':int(summary.get('projectsWithSavedResults') or 0),
                       'powCategoryCount':sum(len(doc.get('costCategoryBreakdown') or []) for project in data.get('projects',[]) for doc in project.get('documents',[]) if doc.get('kind')=='pow')}
    row_fields=('itemCode','description','componentContext','componentContexts','costCategory','quantity','unit',
                'printedUnitCostPesos','inclusiveUnitCostPesos','calculatedUnitCostPesos','amountPesos',
                'directCostSharePct','manualReview','sourcePage','observedPages','arithmeticStatus','costBasis','amountBasis')
    category_fields=('label','sharePct','amountPesos','submittedAmountPesos','evaluatedAmountPesos',
                     'sourcePage','manualReview','basis','costBasis','amountBasis')
    public_projects=[]
    for project in data.get('projects',[]):
        docs=[]
        for doc in project.get('documents',[]):
            docs.append({'kind':doc.get('kind'),'status':doc.get('status'),'url':doc.get('url'),'pageCount':doc.get('pageCount'),
                         'pages':[{'page':page.get('page'),'pageRole':page.get('pageRole')} for page in doc.get('pages',[]) if page.get('pageRole')],
                         'rows':[{k:row.get(k) for k in row_fields if k in row} for row in doc.get('rows',[])],
                         'costCategoryBreakdown':[{k:item.get(k) for k in category_fields if k in item} for item in doc.get('costCategoryBreakdown',[])],
                         'summaryMetadata':doc.get('summaryMetadata',{}),'scopeNote':doc.get('scopeNote'),
                         'controls':doc.get('controls',[]),'reviewPages':doc.get('reviewPages',[]),
                         'people':[{k:person.get(k) for k in ('name','roleText','kind','sourcePage','verificationStatus','designationRegistry') if k in person} for person in doc.get('people',[])]})
        public_projects.append({'code':project.get('code'),'name':project.get('name'),'office':project.get('office'),
                                'region':project.get('region'),'allocationPesos':project.get('allocationPesos'),
                                'documents':docs,'documentLinks':project.get('documentLinks',[])})
    public['projects']=public_projects
    public['projectDirectory']=[{k:project.get(k) for k in ('code','name','office','region')} for project in public_projects]
    public['scope']='This snapshot covers linked Proposal records and parsed HGAB POW line-item data available for review; it is not a whole-program inventory. Proposal source documents link to DPWH Transparency. HGAB PDF links are NR and are not published.'
    return public

def document_reconciliation(projects):
    """Build public aggregate document counts from portal and stage snapshots."""
    catalog=json.loads((STATIC/'dpwh-portal-document-catalog.json').read_text())
    coverage=json.loads((OUT/'dpwh_transparency_document_coverage.json').read_text())
    mapping=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    hgab_pow_crosswalk=json.loads((OUT/'hgab_pow_title_crosswalk.json').read_text())
    stage=json.loads((OUT/'dpwh_hgab_2nd_vs_3rd.json').read_text())
    try:
        from build_undocumented_hgab import supporting_file_presence
        local_file_inventory=supporting_file_presence()
    except (ImportError,OSError):
        local_file_inventory={'available':False,'filesByCode':{},'typesByCode':{}}
    links_by_code={p.get('code'):p.get('documentLinks',[]) for p in projects if p.get('code')}
    portal_rows={r.get('sourceId'):r for r in coverage.get('rows',[]) if r.get('sourceId') and r.get('code')}
    selected_codes={portal_rows[p.get('nep',{}).get('id')]['code'] for p in mapping.get('pairs',[])
                    if p.get('nep',{}).get('id') in portal_rows}
    senate_files_by_hgab={}
    for item in hgab_pow_crosswalk.get('files',[]):
        if item.get('status')=='exact_title_match':
            for hgab_id in item.get('hgabIds',[]):
                senate_files_by_hgab.setdefault(hgab_id,[]).append(item.get('code'))
    # The older crosswalk covers only a small subset. Reuse the completed
    # first-page POW scan's extracted titles against selected HGAB titles too;
    # this adds no new PDF reads and assigns only unique normalized titles.
    pow_scan_path=OUT/'senate_pow_hgab_only_title_scan.json'
    if pow_scan_path.is_file():
        selected_title_ids={}
        for pair in mapping.get('pairs',[]):
            hgab=pair.get('hgab') or {}
            title_key_value=category_base_key(hgab.get('projectName'))
            if title_key_value:selected_title_ids.setdefault(title_key_value,set()).add(pair.get('hgabId'))
        pow_scan=json.loads(pow_scan_path.read_text())
        for record in pow_scan.get('records',[]):
            code=record.get('projectCode')
            ids=selected_title_ids.get(category_base_key(record.get('extractedTitle')),set())
            if code and len(ids)==1:
                senate_files_by_hgab.setdefault(next(iter(ids)),[]).append(code)
    selected_match_files=[{
        'nepProject':p.get('nep',{}).get('officialNepTitle') or p.get('nep',{}).get('projectName'),
        'hgabProject':p.get('hgab',{}).get('projectName'),
        'hgabLedgerCode':p.get('hgabId'),
        'senateFiles':sorted(set(senate_files_by_hgab.get(p.get('hgabId'),[]))),
    } for p in mapping.get('pairs',[]) if senate_files_by_hgab.get(p.get('hgabId'))]
    types_by_code=local_file_inventory.get('typesByCode',{})
    files_by_code=local_file_inventory.get('filesByCode',{})
    selected_match_hgab_documents=[]
    for pair in mapping.get('pairs',[]):
        hgab_id=pair.get('hgabId')
        codes=sorted(set(senate_files_by_hgab.get(hgab_id,[])))
        if not codes:continue
        type_counts={}
        for code in codes:
            for label,count in types_by_code.get(code,{}).items():
                type_counts[label]=type_counts.get(label,0)+int(count or 0)
        selected_match_hgab_documents.append({
            'nepProject':(pair.get('nep') or {}).get('officialNepTitle') or (pair.get('nep') or {}).get('projectName'),
            'hgabProject':(pair.get('hgab') or {}).get('projectName'),
            'hgabLedgerCode':hgab_id,
            'senateFileCodes':codes,
            'fileCount':sum(int(files_by_code.get(code,0)) for code in codes),
            'byType':type_counts,
        })
    selected_hgab_codes={code for item in selected_match_hgab_documents for code in item['senateFileCodes']}
    direct_codes=set()
    for row in stage.get('rows',[]):
        project=row.get('third')
        if not project or project.get('allocationKind')!='project':continue
        title=title_key(project.get('projectName'))
        entry=coverage.get('titles',{}).get(title)
        if entry and entry.get('code') and entry.get('status') not in UNMATCHED:
            direct_codes.add(entry['code'])

    portal_types={str(row.get('type') or 'Unknown'):int(row.get('records') or 0)
                  for row in catalog.get('documentTypes',[])}
    top_types=[name for name,_ in sorted(portal_types.items(),key=lambda item:(-item[1],item[0].casefold()))[:10]]
    def url_sets(codes,excluded=False):
        result={}
        for code in codes:
            for record in links_by_code.get(code,[]):
                label=str(record.get('type') or 'Unknown')
                url=record.get('url')
                if not url or (label in top_types)==excluded:continue
                result.setdefault(label,set()).add(url)
        return result
    selected=url_sets(selected_codes)
    direct=url_sets(direct_codes)
    selected_other=url_sets(selected_codes,excluded=True)
    direct_other=url_sets(direct_codes,excluded=True)
    rows=[]
    def append_row(label,portal,selected_set,direct_set):
        unique=selected_set|direct_set
        rows.append({'type':label,'transparencyRecords':int(portal),'selectedPairRecords':len(selected_set),
                     'directHgabRecords':len(direct_set),'uniqueMatchedRecords':len(unique),
                     'wastedRecords':int(portal)-len(unique)})
    for label in top_types:
        append_row(label,portal_types.get(label,0),selected.get(label,set()),direct.get(label,set()))
    other_portal=sum(count for label,count in portal_types.items() if label not in top_types)
    append_row('Other document types',other_portal,
               set().union(*selected_other.values()) if selected_other else set(),
               set().union(*direct_other.values()) if direct_other else set())
    council_types=('RDC Endorsement','PDC Endorsement','LDC Endorsement')
    council_portal=sum(portal_types.get(label,0) for label in council_types)
    council_selected=set().union(*(selected.get(label,set()) for label in council_types))
    council_direct=set().union(*(direct.get(label,set()) for label in council_types))
    council_unique=council_selected|council_direct
    development_council={
        'portalRecords':council_portal,
        'selectedPairRecords':len(council_selected),
        'directHgabRecords':len(council_direct),
        'uniqueMatchedRecords':len(council_unique),
        'wastedRecords':council_portal-len(council_unique),
        'byType':{
            'RDC':next((row for row in rows if row['type']=='RDC Endorsement'),{}),
            'PDC':next((row for row in rows if row['type']=='PDC Endorsement'),{}),
            'LDC':next((row for row in rows if row['type']=='LDC Endorsement'),{}),
        },
    }
    transparency=catalog.get('summary',{})
    pair_summary=mapping.get('summary',{})
    return {'transparencyProjects':int(transparency.get('projectsInMetadataSnapshot') or 0),
            'transparencyRecords':int(transparency.get('documentRecords') or 0),
            'projectsWithDocumentLinksInLoadedSnapshot':sum(bool(p.get('documentLinks')) for p in projects),
            'loadedProjectRecords':len(projects),
            'nepProjectRecords':int(pair_summary.get('nepRecords') or 0),
            'nepTransparencyRecords':int(pair_summary.get('transparencyNepRecords') or 0),
            'selectedPairs':len(mapping.get('pairs',[])),
            'selectedMatchSenateFiles':selected_match_files,
            'selectedMatchHgabDocuments':selected_match_hgab_documents,
            'selectedPairHgabProjectsWithFiles':sum(bool(item['fileCount']) for item in selected_match_hgab_documents),
            'selectedPairHgabFileCodes':len(selected_hgab_codes),
            'selectedPairHgabFileRecords':sum(int(files_by_code.get(code,0)) for code in selected_hgab_codes),
            'selectedPairHgabFileInventoryAvailable':bool(local_file_inventory.get('available')),
            'selectedPairPortalProjects':len(selected_codes),
            'selectedPairProjectsWithLoadedDocuments':sum(bool(links_by_code.get(code)) for code in selected_codes),
            'selectedPairDocumentRecords':sum(len(values) for values in selected.values()),
            'directHgabProjectsWithLoadedDocuments':sum(bool(links_by_code.get(code)) for code in direct_codes),
            'directHgabDocumentRecords':sum(len(values) for values in direct.values()),
            'uniqueMatchedDocumentRecords':sum(row['uniqueMatchedRecords'] for row in rows),
            'wastedDocumentRecords':sum(row['wastedRecords'] for row in rows),
            'developmentCouncil':development_council,
            'rows':rows,
            'note':'Every record in this reconciliation is a DPWH Transparency Proposal document link; Senate-provided HGAB POW files are reported separately. Selected-pair and direct-HGAB counts use project-level Proposal links present in the loaded snapshot and deduplicate by source URL. Direct HGAB matches can overlap selected-pair records; the unmatched Proposal inventory is the residual after taking their unique union and does not establish literal waste.'}

def refresh_data_only():
    """Refresh whitelisted project JSON while preserving the hand-maintained page HTML."""
    data=build_data()
    serialized=json.dumps(public_data(data),ensure_ascii=False,indent=2)+'\n'
    atomic_write(OUT/'dpwh-in-depth-data.json',serialized)
    publish_split_data()
    return data['summary']


def build_all_hgab_document_coverage(indepth=None):
    """Build one deduplicated row per HGAB project with Proposal/Senate matches and extracted signatories."""
    mapping=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    portal=json.loads((OUT/'dpwh_transparency_document_coverage.json').read_text())
    indepth=indepth or json.loads((OUT/'dpwh-in-depth-data.json').read_text())
    scan_path=OUT/'senate_supporting_documents_hgab_only_scan.json'
    scan=json.loads(scan_path.read_text()) if scan_path.is_file() else {}
    old_path=OUT/'hgab-only-document-coverage.json'
    old=json.loads(old_path.read_text()).get('projects',[]) if old_path.is_file() else []
    old_by_id={r.get('hgabId'):r for r in old if r.get('hgabId')}
    projects={}
    pairs={}
    for pair in mapping.get('pairs',[]):
        h=pair.get('hgab') or {}
        if h.get('allocationKind')=='project' and h.get('id'):
            projects[h['id']]=h
            pairs[h['id']]=pair
    for h in mapping.get('hgabWithoutSelectedCounterpart',[]):
        if h.get('allocationKind')=='project' and h.get('id'):
            projects[h['id']]=h

    proposal_by_code={r.get('code'):r for r in indepth.get('projects',[]) if r.get('code')}
    proposal_by_nep={r.get('sourceId'):r for r in portal.get('rows',[]) if r.get('sourceId')}
    portal_titles=portal.get('titles',{})
    proposal_matches={}
    signatories_by_id={hid:{} for hid in projects}

    def add_signatory(hid,name,role,source):
        name=str(name or '').strip();role=str(role or '').strip()
        if not name:return
        key=(name.casefold(),role.casefold())
        value=signatories_by_id[hid].setdefault(key,{'name':name,'role':role,'sources':set()})
        if source:value['sources'].add(source)

    for hid,h in projects.items():
        matches={}
        direct=portal_titles.get(title_key(h.get('projectName')))
        if direct and direct.get('code'):
            code=direct['code']; record=proposal_by_code.get(code)
            if record and record.get('documentLinks') and int(direct.get('documentCount') or 0)>0:
                matches[code]='Direct Proposal title match'
        pair=pairs.get(hid)
        if pair:
            nep=proposal_by_nep.get(pair.get('nepId'))
            codes={str(pair.get('apiId') or ''),str((nep or {}).get('code') or '')}
            for code in codes-{''}:
                record=proposal_by_code.get(code)
                if record and record.get('documentLinks'):
                    matches[code]='Selected NEP counterpart Proposal'
        proposal_matches[hid]=matches
        for code,label in matches.items():
            record=proposal_by_code[code]
            for doc in record.get('documents',[]):
                kind=doc.get('kind') or doc.get('documentType') or 'document'
                source='Proposal · '+str(kind)
                for person in doc.get('people',[]):
                    add_signatory(hid,person.get('name'),person.get('roleText') or person.get('role') or person.get('kind'),source)

    # Resolve Senate supporting files by title or by a uniquely title-matched
    # sibling file code. Ambiguous project titles are deliberately left unassigned.
    title_ids={}
    for hid,h in projects.items():
        title_ids.setdefault(title_key(h.get('projectName')).casefold(),set()).add(hid)
    code_ids={}
    for doc in indepth.get('hgabPowResults',[]):
        if doc.get('code') and doc.get('hgabId') in projects:
            code_ids.setdefault(doc['code'],set()).add(doc['hgabId'])
    records=scan.get('documents',[])
    for doc in records:
        status=doc.get('matchStatus')
        ids=set(doc.get('matchedHgabIds') or []) & projects.keys()
        code=doc.get('projectCode')
        if status not in {'exact_title_match','relaxed_title_match','same_code_sibling_file_match'}:
            ids=set()
        if code and len(ids)==1:
            code_ids.setdefault(code,set()).update(ids)
    senate_files={hid:{} for hid in projects}
    for doc in records:
        status=doc.get('matchStatus')
        ids=set(doc.get('matchedHgabIds') or []) & projects.keys()
        if status not in {'exact_title_match','relaxed_title_match','same_code_sibling_file_match'}:
            ids=set()
        if not ids:
            extracted=doc.get('extractedTitle')
            exact=title_ids.get(title_key(extracted).casefold(),set()) if extracted else set()
            if len(exact)==1:ids=set(exact)
        code=doc.get('projectCode')
        if not ids and code and len(code_ids.get(code,set()))==1:
            ids=set(code_ids[code])
        for hid in ids:
            file_key=str(doc.get('file') or ((code or '')+'|'+str(doc.get('documentType') or 'Other')))
            if file_key:
                senate_files[hid][file_key]=doc
            kind=str(doc.get('documentType') or 'Other')
            for person in doc.get('signatories',[]):
                role=person.get('role') or person.get('kind') or person.get('roleText')
                if role and '_' in str(role):role=str(role).replace('_',' ').title()
                add_signatory(hid,person.get('name'),role,'Senate HGAB · '+kind)

    rows=[]
    for hid,h in projects.items():
        prior=old_by_id.get(hid,{})
        proposal=proposal_matches.get(hid,{})
        if prior:
            # Keep the established HGAB-only table's match decisions and metadata.
            proposal_matched=bool(prior.get('proposalDocumentsMatched'))
            proposal_sources=list(prior.get('proposalDocumentSources') or [])
            proposal_types=set(prior.get('proposalDocumentTypes') or [])
            senate_types=set(prior.get('senateDocumentTypes') or [])
            senate_matched=bool(prior.get('senateHgabDocumentsMatched'))
            senate_count=max(int(prior.get('senateMatchedFileRecords') or 0),len(senate_files[hid]))
            for sig in prior.get('signatories',[]):
                for source in sig.get('sources',[]):add_signatory(hid,sig.get('name'),sig.get('role'),source)
        else:
            proposal_matched=bool(proposal)
            proposal_sources=sorted(set(proposal.values()))
            proposal_types={str(d.get('type')) for code in proposal for d in proposal_by_code[code].get('documentLinks',[]) if d.get('type')}
            senate_types={str(d.get('documentType') or 'Other') for d in senate_files[hid].values()}
            senate_matched=bool(senate_files[hid])
            senate_count=len(senate_files[hid])
        for doc in senate_files[hid].values():
            senate_types.add(str(doc.get('documentType') or 'Other'))
        sig_rows=[{'name':v['name'],'role':v['role'],'sources':sorted(v['sources'])}
                  for _,v in sorted(signatories_by_id[hid].items(),key=lambda item:(item[1]['name'].casefold(),item[1]['role'].casefold()))]
        proposal_file_records={str(d.get('url') or (d.get('type'),d.get('title'),d.get('fileName')))
                               for code in proposal for d in proposal_by_code[code].get('documentLinks',[])}
        document_match_status=('Both sources' if proposal_matched and senate_matched else
                               'Proposal only' if proposal_matched else
                               'Senate HGAB only' if senate_matched else 'No current match')
        rows.append({'hgabId':hid,'title':h.get('projectName') or '',
            'office':h.get('office') or '', 'region':h.get('region') or '',
            'amountPesos':round(float(h.get('amountPesos') or 0)),
            'documentMatchStatus':document_match_status,
            'proposalDocumentsMatched':proposal_matched,'proposalDocumentSources':proposal_sources,
            'proposalDocumentTypes':sorted(proposal_types),'proposalMatchedFileRecords':len(proposal_file_records),
            'senateHgabDocumentsMatched':senate_matched,'senateDocumentTypes':sorted(senate_types),
            'senateMatchedFileRecords':senate_count,'signatoryCandidateCount':len(sig_rows),
            'signatories':sig_rows})
    rows.sort(key=lambda r:(-r['amountPesos'],str(r['title']).casefold(),r['hgabId']))
    return {'generatedAtUtc':datetime.now(timezone.utc).isoformat(),
        'scope':'All FY2027 HGAB 3rd-reading DPWH project rows, deduplicated by House ledger row ID.',
        'denominatorProjectRows':len(rows),
        'method':'Proposal matches use direct Proposal title links or the selected NEP counterpart with linked Proposal documents. Senate HGAB matches use title-linked supporting files and uniquely resolved HGAB-code sibling files. Signatory names and roles are extracted document candidates, not verified unique people, current officials or project sponsors. Document presence does not verify contents.',
        'projects':rows}

def build():
    import importlib
    from build_report_heroes import hero,STYLE
    import uniform_report_menu
    # This builder also runs inside the long-lived document watcher. Reload the
    # shared page normalizer so regenerated DPWH pages cannot retain stale menus
    # or stale shared header/hero styling from the watcher's startup import.
    importlib.invalidate_caches()
    uniform_report_menu=importlib.reload(uniform_report_menu)
    apply_page=uniform_report_menu.apply_page
    from report_table_presentation import apply_page as tables,publish_assets
    data=build_data();s=data['summary']
    all_hgab_coverage=build_all_hgab_document_coverage(data)
    all_hgab_coverage_json=json.dumps(all_hgab_coverage,ensure_ascii=False,separators=(',',':'))+'\n'
    all_hgab_coverage_version=hashlib.sha256(all_hgab_coverage_json.encode('utf-8')).hexdigest()[:12]
    all_hgab_coverage_js=(ROOT/'project_documents/hgab-document-coverage.js').read_text().replace('__COVERAGE_VERSION__',all_hgab_coverage_version)
    all_hgab_coverage_js_version=hashlib.sha256(all_hgab_coverage_js.encode('utf-8')).hexdigest()[:12]
    public_data_json=json.dumps(public_data(data),ensure_ascii=False,indent=2)+'\n'
    public_data_version=hashlib.sha256(public_data_json.encode('utf-8')).hexdigest()[:12]
    coverage=data['hgabCoverage']
    all_rows=all_hgab_coverage['projects']
    all_denominator=len(all_rows)
    if len({row.get('hgabId') for row in all_rows}) != all_denominator:
        raise ValueError('All-HGAB document coverage export contains duplicate or missing project IDs')
    expected_all_rows=int(data['hgabCoverage'].get('projectRows') or 0)
    if all_denominator!=expected_all_rows:
        raise ValueError(f'All-HGAB document export has {all_denominator} rows but DPWH coverage has {expected_all_rows}')
    proposal_count=sum(bool(row.get('proposalDocumentsMatched')) for row in all_rows)
    senate_count=sum(bool(row.get('senateHgabDocumentsMatched')) for row in all_rows)
    any_document_count=sum(bool(row.get('proposalDocumentsMatched') or row.get('senateHgabDocumentsMatched')) for row in all_rows)
    overlap_count=sum(bool(row.get('proposalDocumentsMatched') and row.get('senateHgabDocumentsMatched')) for row in all_rows)
    proposal_pct=100*proposal_count/all_denominator if all_denominator else 0
    senate_pct=100*senate_count/all_denominator if all_denominator else 0
    any_document_pct=100*any_document_count/all_denominator if all_denominator else 0
    senate_title=data.get('senateDocumentTitleCoverage') or {}
    senate_types=senate_title.get('byType',{})
    senate_pow=senate_types.get('pow',{})
    senate_bp=senate_types.get('bp202',{})
    supporting=data.get('senateSupportingDocumentCoverage') or {}
    hgab_only_denominator=int(senate_title.get('denominatorProjectRows') or supporting.get('denominatorProjectRows') or 0)
    HERO_STYLE='''<style id="hgab-coverage-hero-style">.hgab-coverage-hero{margin:20px 0 24px;padding:clamp(22px,3vw,36px);border-left:8px solid #FCD116;border-radius:16px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff;box-shadow:0 14px 34px #00246a20}.hgab-coverage-kicker{display:block;margin-bottom:14px;color:#FCD116;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.hgab-coverage-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.hgab-coverage-metric{display:flex;min-height:132px;flex-direction:column;justify-content:center;gap:7px;padding:18px;border:1px solid #ffffff45;border-radius:12px;background:#ffffff12}.hgab-coverage-metric strong{color:#FCD116;font-size:clamp(32px,4vw,52px);line-height:1;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.hgab-coverage-metric span{font-size:clamp(15px,1.6vw,18px);font-weight:700;line-height:1.3}.hgab-coverage-metric small,.hgab-coverage-note{color:#e8eef8;font-size:13px;line-height:1.45}.hgab-coverage-note{margin:14px 0 0}@media(max-width:850px){.hgab-coverage-metrics{grid-template-columns:1fr}.hgab-coverage-metric{min-height:100px}}</style>'''+'''<style id="all-hgab-document-table-style">#all-hgab-document-coverage .tablewrap{overflow-x:auto;max-height:none}#all-hgab-document-coverage table{width:100%;min-width:1180px;table-layout:fixed}#all-hgab-document-coverage th:nth-child(1),#all-hgab-document-coverage td:nth-child(1){width:11%}#all-hgab-document-coverage th:nth-child(2),#all-hgab-document-coverage td:nth-child(2){width:23%}#all-hgab-document-coverage th:nth-child(3),#all-hgab-document-coverage td:nth-child(3){width:15%}#all-hgab-document-coverage th:nth-child(4),#all-hgab-document-coverage td:nth-child(4){width:12%}#all-hgab-document-coverage th:nth-child(5),#all-hgab-document-coverage td:nth-child(5){width:13%}#all-hgab-document-coverage th:nth-child(6),#all-hgab-document-coverage td:nth-child(6){width:13%}#all-hgab-document-coverage th:nth-child(7),#all-hgab-document-coverage td:nth-child(7){width:13%}#all-hgab-document-coverage th,#all-hgab-document-coverage td{padding:9px;vertical-align:top;overflow-wrap:anywhere}#all-hgab-document-coverage td small{display:block;color:#526c78;font-size:12px}#all-hgab-document-coverage .coverage-controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:12px 0}#all-hgab-document-coverage .coverage-controls input{flex:1;min-width:240px}#all-hgab-document-coverage .coverage-pagination{display:flex;gap:10px;align-items:center;justify-content:flex-end;margin-top:10px}@media(max-width:650px){#all-hgab-document-coverage{padding:14px}}</style>'''
    lead=f'''<section class="hgab-coverage-hero" aria-label="All HGAB document reconciliation"><span class="hgab-coverage-kicker">All HGAB project rows · Proposal and Senate HGAB document reconciliation</span><div class="hgab-coverage-metrics"><div class="hgab-coverage-metric"><strong>{any_document_count:,}</strong><span>have at least one Proposal or Senate HGAB document</span><small>{any_document_pct:.2f}% of {all_denominator:,} HGAB project rows · deduplicated</small></div><div class="hgab-coverage-metric"><strong>{proposal_count:,}</strong><span>have linked Proposal documents</span><small>{proposal_pct:.2f}% of all HGAB project rows</small></div><div class="hgab-coverage-metric"><strong>{senate_count:,}</strong><span>have matched Senate HGAB documents</span><small>{senate_pct:.2f}% of all HGAB project rows</small></div></div><p class="hgab-coverage-note">The union counts rows once; {overlap_count:,} rows match both sources and {all_denominator-any_document_count:,} have no current match in either. Proposal links use direct title matches or selected NEP counterparts; Senate matches use title-linked support files and uniquely resolved file-code siblings. File presence does not verify document contents.</p></section>'''
    text=(ROOT/'project_documents/indepth.html').read_text().replace('<!--HERO_STYLE-->',STYLE+HERO_STYLE).replace('<!--HERO-->',lead)
    version=hashlib.sha256((ROOT/'project_documents/indepth.js').read_bytes()).hexdigest()[:12]
    text=text.replace('src="dpwh-in-depth.js"',f'src="dpwh-in-depth.js?v={version}"')
    text=tables(apply_page(text,'dpwh.html'),publish_assets())
    loader=(ROOT/'project_documents/dpwh-data-loader.js').read_text()
    loader_version=hashlib.sha256((loader+'\n'+public_data_version).encode()).hexdigest()[:12]
    text=text.replace('src="hgab-document-coverage.js"',f'src="hgab-document-coverage.js?v={all_hgab_coverage_js_version}"')
    text=text.replace('__COVERAGE_VERSION__',all_hgab_coverage_version)
    indepth_js=(ROOT/'project_documents/indepth.js').read_text()
    atomic_write(OUT/'dpwh-in-depth-data.json',public_data_json)
    publish_split_data()
    text=re.sub(r'src="dpwh-data-loader\.js(?:\?v=[^"]*)?"',f'src="dpwh-data-loader.js?v={loader_version}"',text)
    # Table presentation can touch report chrome; keep the shared navigation as
    # the last HTML transformation before publishing these DPWH report pages.
    text=apply_page(text,'dpwh.html')
    # Keep the initial coverage script cache-busted after shared page transforms.
    text=re.sub(r'src="dpwh-in-depth\.js(?:\?v=[^"]*)?"',f'src="dpwh-in-depth.js?v={version}"',text,count=1)
    coverage_section=re.search(r'<section[^>]*id="all-hgab-document-coverage"[^>]*>.*?</section>',text,re.S)
    main_match=re.search(r'<main\b[^>]*>(.*?)</main>',text,re.S)
    main_sections=re.findall(r'<section\b[^>]*id="([^"]+)"[^>]*>',main_match.group(1),re.S) if main_match else []
    coverage_head= re.search(r'<thead>(.*?)</thead>',coverage_section.group(0),re.S) if coverage_section else None
    coverage_headers=[re.sub(r'<[^>]+>','',header).strip() for header in re.findall(r'<th\b[^>]*>(.*?)</th>',coverage_head.group(1),re.S)] if coverage_head else []
    expected_coverage_headers=['HGAB code','Project','Office · region','HGAB allocation','Proposal docs','Senate HGAB docs','Signatories in related documents']
    if coverage_headers != expected_coverage_headers or not all_rows or not main_sections or main_sections[-1] != 'all-hgab-document-coverage':
        raise RuntimeError(f'All-HGAB coverage table validation failed: headers={coverage_headers!r}, {len(all_rows)} rows, final section={main_sections[-1:]!r}')
    for target in (OUT,STATIC):
        atomic_write(target/'dpwh-in-depth.js',(ROOT/'project_documents/indepth.js').read_text())
        atomic_write(target/'dpwh-data-loader.js',loader)
        atomic_write(target/'hgab-document-coverage.js',all_hgab_coverage_js)
        atomic_write(target/'hgab-document-coverage.json',all_hgab_coverage_json)
        atomic_write(target/'dpwh.html',text)
    return s
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--data-only',action='store_true');args=parser.parse_args()
    print(json.dumps(refresh_data_only() if args.data_only else build(),indent=2))
