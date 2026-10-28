#!/usr/bin/env python3
"""Publish whitelisted parsed document evidence; never publish raw cache files."""
import json,html,shutil,hashlib,uuid,re,unicodedata,statistics
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
CACHE=ROOT/'data_sources/dpwh_project_documents/on_demand'
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

def category_key(value):
    base=category_base_key(value)
    return CATEGORY_MERGES.get(base,base)

def has_kind(project,kind):
    for d in project.get('documentLinks',[]):
        t=' '.join(str(d.get('type') or '').lower().split())
        if kind=='pow' and (t=='pow' or 'program of work' in t):return True
        if kind=='photos' and 'geotagged' in t and 'photo' in t:return True
        if kind=='rdc' and ('rdc' in t or 'regional development council' in t):return True
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

def hgab_statistics():
    stage=json.loads((OUT/'dpwh_hgab_2nd_vs_3rd.json').read_text())
    coverage=json.loads((OUT/'dpwh_transparency_document_coverage.json').read_text())
    nep_map=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    snapshot=json.loads((OUT/'dpwh-in-depth-data.json').read_text())
    projects=[r['third'] for r in stage['rows'] if r.get('third') and r['third'].get('allocationKind')=='project']
    unpaired_ids={r.get('id') for r in nep_map.get('hgabWithoutSelectedCounterpart',[]) if r.get('allocationKind')=='project'}
    titles=coverage.get('titles',{});linked=[];status_counts={}
    unpaired=missing_listed=double_flag=0
    for row in projects:
        entry=titles.get(title_key(row.get('projectName')))
        status=entry.get('status','unmapped') if entry else 'unmapped'
        status_counts[status]=status_counts.get(status,0)+1
        no_selected_nep=row.get('id') in unpaired_ids
        docs_listed=bool(entry and entry.get('code') and status not in UNMATCHED and (entry.get('documentCount') or 0)>0)
        unpaired+=no_selected_nep
        missing_listed+=not docs_listed
        double_flag+=no_selected_nep and not docs_listed
        if entry and entry.get('code') and status not in UNMATCHED:
            linked.append((row,entry))
    by_code={p['code']:p for p in snapshot['projects']}
    inspected=[(row,entry,by_code[entry['code']]) for row,entry in linked if entry['code'] in by_code]
    types={k:sum(has_kind(p,k) for _,_,p in inspected) for k in ('pow','photos','rdc')}
    missing_any=sum(not all(has_kind(p,k) for k in ('pow','photos','rdc')) for _,_,p in inspected)
    coverage_data={'stage':'HGAB 3rd reading','projectRows':len(projects),'linkedRows':len(linked),'linkedPct':round(100*len(linked)/len(projects),1) if projects else 0,
      'listedAnyRows':sum((entry.get('documentCount') or 0)>0 for _,entry in linked),'listedAnyPct':round(100*sum((entry.get('documentCount') or 0)>0 for _,entry in linked)/len(linked),1) if linked else 0,
      'inspectedRows':len(inspected),'inspectedPct':round(100*len(inspected)/len(linked),1) if linked else 0,
      'missingAnyTypeRows':missing_any,'missingAnyTypePct':round(100*missing_any/len(inspected),1) if inspected else 0,
      'noSelectedNepRows':unpaired,'noSelectedNepPct':round(100*unpaired/len(projects),1) if projects else 0,
      'missingListedDocumentsRows':missing_listed,'doubleRedFlagRows':double_flag,'doubleRedFlagPct':round(100*double_flag/len(projects),1) if projects else 0,
      'missingTypes':{k:{'count':len(inspected)-v,'pct':round(100*(len(inspected)-v)/len(inspected),1) if inspected else 0} for k,v in types.items()},
      'statusCounts':status_counts,'sourceCommit':coverage.get('sourceCommit'),'snapshotRetrievedAtUtc':coverage.get('snapshotRetrievedAtUtc')}
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
def collect():
    from project_documents.signatories import qualified_role
    reviewed_path=ROOT/'project_documents/pow_reviewed_category_totals.json'
    reviewed_config=json.loads(reviewed_path.read_text()) if reviewed_path.exists() else {}
    reviewed=reviewed_config.get('projects',{})
    projects=[];attempted=failed=available=empty=0;errors={}
    for path in sorted(CACHE.glob('*/result.json')):
        try:
            result=json.loads(path.read_text());meta=json.loads((path.parent/'metadata.json').read_text())
        except (OSError,ValueError):continue
        documents=[]
        for d in result.get('documents',[]):
            status=d['status']
            if status not in ('link_only',):
                attempted+=1
                if status=='available':available+=1
                else:
                    failed+=1;key=d.get('error','Unknown').split(':',1)[0];errors[key]=errors.get(key,0)+1
            parsed=d.get('pow',{})
            rows=[{k:r.get(k) for k in ('itemCode','description','componentContext','componentContexts','costCategory','quantity','unit','printedUnitCostPesos','inclusiveUnitCostPesos','calculatedUnitCostPesos','amountPesos','directCostSharePct','manualReview','sourcePage','observedPages','extractionMethod','arithmeticStatus','verificationStatus','costBasis','amountBasis')} for r in parsed.get('rows',[])]
            people=[{k:p.get(k) for k in ('name','roleText','kind','sourcePage','extractionMethod','verificationStatus')} for p in d.get('signatories',{}).get('people',[]) if qualified_role(p.get('roleText',''),d['kind'])]
            controls=[{k:c.get(k) for k in ('sourcePage','basis','amountBasis','printedPesos','recoveredItemRows','recoveredPesos','differencePesos','reconciled')} for c in parsed.get('itemizedDirectCostControls',[])]
            categories=list(parsed.get('costCategoryBreakdown',[]))
            if d['kind']=='pow':
                for correction in reviewed.get(meta.get('code'),[]):
                    match=next((c for c in categories if category_key(c.get('label'))==category_key(correction.get('label'))),None)
                    if match:match.update(correction)
                    else:categories.append(correction)
            review_pages=[{'page':p.get('page'),'note':p.get('reviewNote')} for p in parsed.get('pages',[]) if p.get('status')=='needs_manual_review']
            categories.sort(key=lambda c:-float(c.get('amountPesos') or 0))
            summary_metadata=parsed.get('summaryMetadata',{}) if d['kind']=='pow' else {}
            declared=[f for f in summary_metadata.get('qualitativeFacts',[]) if f.get('kind')=='declared_count']
            has_named=any(f.get('kind')=='named_component' for f in summary_metadata.get('qualitativeFacts',[]))
            generated_scope_note=('The POW states '+', '.join(f.get('printedText','') for f in declared)+'; no named school/building/site breakdown was detected in the parsed pages.' if declared and not has_named else None)
            scope_note=(reviewed_config.get('projectScopeNotes',{}).get(meta.get('code')) or generated_scope_note) if d['kind']=='pow' else None
            documents.append({'kind':d['kind'],'status':status,'url':d.get('metadata',{}).get('url'),'sha256':d.get('sha256'),'pageCount':parsed.get('pageCount',d.get('signatories',{}).get('sourcePages')),'pages':parsed.get('pages',[]),'rows':rows,'costCategoryBreakdown':categories,'summaryMetadata':summary_metadata,'scopeNote':scope_note,'controls':controls,'reviewPages':review_pages,'people':people,'signatoryStatus':d.get('signatories',{}).get('status'),'errorType':d.get('error','').split(':',1)[0] or None})
        if not documents:empty+=1
        projects.append({'code':meta['code'],'name':meta['projectName'],'office':meta.get('office'),'region':meta.get('region'),'allocationPesos':round(float(meta['amount'])*1000),'preparedAt':result.get('preparedAtUtc'),'documents':documents,'documentLinks':[{'type':d.get('documentType'),'url':d.get('url')} for d in meta.get('documents',[])]})
    prepared=[p for p in projects if any(d['rows'] for d in p['documents'])]
    return {'generatedAtUtc':datetime.now(timezone.utc).isoformat(),'stage':'NEP FY2027 proposal documents','projects':projects,'summary':{'projectsWithParsedPow':len(prepared),'parsedPowRows':sum(len(d['rows']) for p in projects for d in p['documents'] if d['kind']=='pow'),'projectsWithSavedResults':len(projects),'projectsWithoutSelectedAttachments':empty,'availableDocuments':available,'failedDocuments':failed,'attemptedDocuments':attempted,'errorTypes':errors},'source':'https://api.dpwh.bettergov.ph','scope':'Static snapshot of locally cached documents. Not whole-program coverage. Raw PDFs and photos are excluded from this publication.'}
def atomic_write(path,text):
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temporary.write_text(text);temporary.replace(path)

def build():
    from build_report_heroes import hero,STYLE
    from uniform_report_menu import apply_page
    from report_table_presentation import apply_page as tables,publish_assets
    data=collect();s=data['summary'];data['powCategoryMerges']=CATEGORY_MERGES;data['powCategoryLabels']=CATEGORY_LABELS;data['hgabCoverage'],data['powPeers']=hgab_statistics()
    data['summaryPeerGroups']=summary_peer_groups(data['projects'])
    coverage=data['hgabCoverage']
    hero_stats=[
        ('No selected NEP counterpart',f"{coverage['noSelectedNepRows']:,}",f"{coverage['noSelectedNepPct']:.1f}% of project rows"),
        ('No listed DPWH documents',f"{coverage['missingListedDocumentsRows']:,}",f"{coverage['missingListedDocumentsRows']/coverage['projectRows']:.1%} of project rows"),
        ('DPWH transparency links',f"{coverage['linkedRows']:,}",f"{coverage['linkedPct']:.1f}% of project rows"),
        ('Double red flag · no selected NEP counterpart + no listed docs',f"{coverage['doubleRedFlagRows']:,}",f"{coverage['doubleRedFlagPct']:.1f}% of project rows"),
    ]
    lead=hero('DPWH POWs · cached proposal documents',str(s['parsedPowRows']),'bill rows reveal the cost drivers',str(s['projectsWithParsedPow']),'projects with recovered POW bill rows', hero_stats, 'The statistics summarize HGAB 3rd-reading rows and their DPWH Transparency coverage. Coverage gaps are review flags; they do not establish that documents do not exist elsewhere.')
    text=(ROOT/'project_documents/indepth.html').read_text().replace('<!--HERO_STYLE-->',STYLE).replace('<!--HERO-->',lead)
    version=hashlib.sha256((ROOT/'project_documents/indepth.js').read_bytes()).hexdigest()[:12]
    text=text.replace('src="dpwh-in-depth.js"',f'src="dpwh-in-depth.js?v={version}"')
    text=tables(apply_page(text,'dpwh.html'),publish_assets())
    for target in (OUT,STATIC):
        atomic_write(target/'dpwh-in-depth-data.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
        atomic_write(target/'dpwh-in-depth.js',(ROOT/'project_documents/indepth.js').read_text())
        atomic_write(target/'dpwh.html',text)
    return s
if __name__=='__main__':print(json.dumps(build(),indent=2))
