#!/usr/bin/env python3
"""Reconcile a pinned third-party snapshot without running its source code.
Reviewed extraction takes priority; project-identity matching stays separate.
"""
import argparse,csv,hashlib,json,re
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'data_sources/csiiiv';OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
SITE='https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/'
REPO='https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS'
class Snapshot:
    def __init__(self):
        self.manifest=json.loads((BASE/'manifest.json').read_text())
        self.files={r['repositoryPath']:r for r in self.manifest['files']}
        self.used={}
    def load(self,name):
        record=self.files[name];p=ROOT/record['localPath'];raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Changed snapshot bytes: '+name)
        self.used[name]={'repositoryPath':name,'sourceUrl':record['sourceUrl'],'sha256':record['sha256'],'localPath':record['localPath']}
        return json.loads(raw)
def local(name):return json.loads((STATIC/name).read_text())
def build():
    snap=Snapshot();manifest=snap.manifest
    nia=snap.load('analysis-nia/data/nep_nia_dataset.json')
    nh=snap.load('analysis-nia/data/hgab_nia_tree.json')
    na=snap.load('analysis-nia/data/hgab_nia_audit.json')
    np=nia['projects'];hp=[r for r in nh['nodes'] if r['kind']=='project']
    if len(np)!=nia['meta']['row_count'] or sum(r['amount_php'] for r in np)!=nia['meta']['grand_total']:raise ValueError('NEP NIA ledger does not reconcile')
    if len(hp)!=na['summary']['projects'] or sum(r['printed_amount_php'] for r in hp)!=na['summary']['project_ledger_total_php']:raise ValueError('House NIA ledger does not reconcile')
    if not na['passed'] or not nia['meta']['all_controls_reconciled']:raise ValueError('NIA source audit not passed')
    for control in nia['sub_programs']:
        rows=[r for r in np if r['sub_program']==control['sub_program']]
        if len(rows)!=control['project_count'] or sum(r['amount_php'] for r in rows)!=control['control_amount']:raise ValueError('NEP NIA subprogram discrepancy')
    house_controls={r['label']:r['printed_amount_php'] for r in nh['nodes'] if r['kind']=='subprogram_control'}
    mapped_labels={'Extension/Expansion':'Extension/Expansion of Existing Irrigation System Sub-Program'}
    nia_control_comparison=[]
    for r in nia['sub_programs']:
        label=mapped_labels.get(r['sub_program'],r['sub_program']+' Sub-Program')
        house=house_controls[label]
        nia_control_comparison.append({'program':r['sub_program'],'nepPesos':r['control_amount'],'referenceHousePesos':house,'adjustmentPesos':house-r['control_amount']})
    ni=local('nia-irrigation-data.json')['revision']['summary']
    nia_data={'nepRows':len(np),'nepPesos':sum(r['amount_php'] for r in np),'referenceHouseRows':len(hp),'referenceHousePesos':sum(r['printed_amount_php'] for r in hp),'localHouseRows':ni['thirdRows'],'localHousePesos':ni['thirdTotal'],'controls':nia['sub_programs'],'controlComparison':nia_control_comparison,'readingComparison':na.get('reading_comparison'),
        'status':'Reviewed extraction adopted; local House count/total now agrees.' if ni['thirdRows']==len(hp) and ni['thirdTotal']==sum(r['printed_amount_php'] for r in hp) else 'Older local extraction has incomplete annex coverage.'}
    hfep={}
    for stage,name in [('nep','nep_hfep_data_list.json'),('house','hgab_hfep_data_list.json')]:
        d=snap.load('analysis-hfep/data/'+name);items=d['items'];verification=d['document']['verification']['summary']
        ledger=sum(r['amounts_php']['total'] for r in items)
        if len(items)!=verification['facilities'] or ledger!=verification['facility_ledger_total_php']:raise ValueError('HFEP ledger discrepancy')
        hfep[stage]={'facilities':len(items),'ledgerPesos':ledger,'columnPesos':{k:sum(r['amounts_php'].get(k,0) for r in items) for k in ['infrastructure','medical_equipment','motor_vehicle']},'verification':verification,'sourceMetadata':d['document']['metadata'],'categories':{r['label']:r['amounts_php']['total'] for r in d['controls'] if r['kind']=='category_control'}}
    hfep['localCapitalControls']=local('nep-agency-baselines.json')['hfepStageComparison']
    source=snap.load('analysis/data/source_comparison_2027.json')
    reading=snap.load('analysis/data/house_reading_changes_2027.json')
    local_reading=local('dpwh-hgab-comparison.json')['summary']
    verification=snap.load('analysis/data/source_verification_overview.json')
    from hgab_matching import UNMATCHED,is_fap,normalize
    own=list(csv.DictReader((OUT/'hb_nep_comparison_3rd.csv').open()))
    fap=[]
    for row in own:
        if row['comparison']!=UNMATCHED or not is_fap(row):continue
        found=[r for r in source['projects'] if r.get('house') and normalize(r['house']['title'])==normalize(row['projectName'])]
        fap.append({'projectName':row['projectName'],'localAmountPesos':int(row['amountPesos']),'localPage':row['sourcePage'],'referenceStatuses':[r['status'] for r in found],'referenceNepTitles':[(r.get('nep') or {}).get('title') for r in found]})
    updates=[]
    for stage in ['nep','hgab']:
        updated=snap.load(f'other-analysis/data/{stage}_fmr_coordinates_normalized.json')
        old=json.loads((ROOT/f'data_sources/fmr_analyst/{stage}_fmr_coordinates_normalized.json').read_text())
        prior={r['project_id']:r for r in old['projects']};current={r['project_id']:r for r in updated['projects']}
        delta=[]
        for ident,row in current.items():
            before=prior.get(ident)
            fields=[k for k in ['title','amount_php','coordinates','status','review_flags','normalization_rules'] if before is None or row.get(k)!=before.get(k)]
            if fields:delta.append({'sourceId':ident,'projectName':row['title'],'changedFields':fields,'oldCoordinates':before.get('coordinates') if before else None,'newCoordinates':row.get('coordinates'),'oldFlags':before.get('review_flags') if before else None,'newFlags':row.get('review_flags')})
        updates.append({'stage':stage,'oldRecords':len(prior),'referenceRecords':len(current),'changedRecords':len(delta),'removedIds':sorted(set(prior)-set(current)),'details':delta})
    chainage=snap.load('analysis/data/chainage_units_2027.json')
    chains={stage:{'rows':sum(r['source']==stage for r in chainage['units']),'withLength':sum(r['source']==stage and r.get('length_m') is not None for r in chainage['units'])} for stage in ['nep','hb2','hb3']}
    pending=next((r.get('review_summary',{}).get('needs_source_check') for r in verification['sources'] if r['key']=='nep'),None)
    equal_readings=all(local_reading[k]==reading['summary'][stage][field] for k,stage,field in [('secondCandidateCount','second','allocations'),('thirdCandidateCount','third','allocations'),('secondAllocationPesos','second','operations_including_projects'),('thirdAllocationPesos','third','operations_including_projects')])
    gap=hfep['nep']['verification']['grand_total_php']-hfep['nep']['ledgerPesos']
    fap_unmatched=sum(r['referenceStatuses']==['house_unmatched'] for r in fap)
    coordinate_changed=sum('coordinates' in d['changedFields'] for r in updates for d in r['details'])
    findings=[
        {'id':'nia-scope','priority':'Reviewed source adoption and annex coverage','pages':['nia-irrigation.html','nia.html','summary.html'],'finding':f"The external NIA House annex contains {len(hp)} project rows / PHP {nia_data['referenceHousePesos']:,}; the local detailed schedule contains {ni['thirdRows']} / PHP {ni['thirdTotal']:,}. The external NEP detailed annex is now available ({len(np)} rows). The reviewed extraction takes priority over older local automated parsing. Newly recovered rows are parser corrections, not budget insertions."},
        {'id':'hfep-baseline','priority':'Detailed baseline now available','pages':['hfep.html'],'finding':f"The external HFEP NEP ledger contains {hfep['nep']['facilities']} facilities, PHP {hfep['nep']['ledgerPesos']:,}. Printed control minus the facility ledger is PHP {gap:,}. Preserve that discrepancy; do not manufacture a balancing row or treat unmatched facility names as certified insertions."},
        {'id':'dpwh-readings','priority':'House reading control cross-check','pages':['dpwh-hgab-comparison.html'],'finding':f"External House controls contain {reading['summary']['second']['allocations']:,} second-reading and {reading['summary']['third']['allocations']:,} third-reading allocations; net operations change PHP {reading['summary']['allocation_delta_php']:,}. Local count and allocation controls agree: {equal_readings}. Repeated-key comparison groups are not the same grain as their member allocations."},
        {'id':'dpwh-matching','priority':'Methods and stages differ','pages':['dpwh-hgab.html','congress.html','summary.html'],'finding':f"The external retained NEP/House comparison uses the SECOND reading and reports {source['summary']['match_counts'].get('house_unmatched')} unmatched House candidates and {source['summary']['match_counts'].get('nep_unmatched')} unmatched NEP candidates. Our principal analysis uses the THIRD reading. Chainage/re-scoping fallbacks consume some external pairs; differing stations and altered geography still require independent review. The earlier 5,837/2,139 figures are not a current target."},
        {'id':'source-certification','priority':'Shared source limitation','pages':['dpwh.html','dpwh-hgab.html','repeats.html','congress.html'],'finding':f"The external source verification manifest records comparison_ready={verification['comparison_ready']}. Balanced arithmetic does not certify every OCR title, amount, source scope or project identity. Its NEP review queue includes {pending:,} pending checks; these are not confirmed extraction errors."},
        {'id':'fap-crosscheck','priority':'Agreement on unresolved cases','pages':['dpwh-hgab.html'],'finding':f"Of our {len(fap)} unmatched FAP lines, {fap_unmatched} also remain house_unmatched in the downloaded comparison. External narrative and matching JSON can differ; retained row statuses must be checked before assuming every FAP loan has a counterpart. Keep unresolved cases separate and provisional."},
        {'id':'fmr-coordinate-changes','priority':'Review before changing cost denominators','pages':['fmr.html','cost-per-km.html','cost-matching.html'],'finding':f"Compared with our imported FMR ledger, {sum(r['changedRecords'] for r in updates)} records have changed data/review fields, including {coordinate_changed} with changed coordinate arrays. Numeric repairs, review flags and new provenance must be reconciled before changing distance-based rates or geographic attribution. The update report lists every changed source row."},
        {'id':'chainage-coverage','priority':'Different screening populations','pages':['cost-matching.html','cost-per-km.html'],'finding':'The external chainage table includes flood control, local/FAP scopes and three source stages. Its length counts cannot be compared directly with our selected domestic roads/bridges/FMR denominator. Chainage-derived funded extent and endpoint distance remain distinct.'}]
    control_leads=[]
    for r in sorted(nia_control_comparison,key=lambda r:r['adjustmentPesos'])[:1]:
        control_leads.append({'page':'nia-irrigation.html','title':'Largest NIA sub-program control reduction','note':f"{r['program']}: NEP PHP {r['nepPesos']:,} versus House PHP {r['referenceHousePesos']:,}; change PHP {r['adjustmentPesos']:,}. These are external printed-annex controls, not project identities or proof of a transfer."})
    for label in ['2. LGU Hospitals','3. DOH Hospitals']:
        a=hfep['nep']['categories'][label];b=hfep['house']['categories'][label]
        control_leads.append({'page':'hfep.html','title':label,'note':f"{label}: NEP PHP {a:,} versus House PHP {b:,}; change PHP {b-a:,}. Opposing movements do not establish a direct transfer or service consequences."})
    result={'source':{'repository':REPO,'website':SITE+'#overview','commit':manifest['commit'],'retrievedAtUtc':manifest['retrievedAtUtc']},'refreshPolicy':'Documented human-reviewed source corrections take priority over older local automated extraction. The adoption step retains raw values, review flags, source hashes and bounded reading equivalence. No downloaded code executes. Extraction adoption does not certify cross-stage project identity or geographic attribution.','findings':findings,'additionalResearchLeads':control_leads,'nia':nia_data,'hfep':hfep,'dpwh':{'referenceSecondReading':source['summary'],'referenceReadings':reading['summary'],'localReadings':local_reading,'localDomesticUnmatched':sum(r['comparison']==UNMATCHED and not is_fap(r) for r in own),'fapCrosscheck':fap},'sourceVerification':verification,'fmrCoordinateUpdates':updates,'chainageCoverage':chains,'inputs':list(snap.used.values()),'snapshotChanges':manifest.get('changes',[])}
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n';(OUT/'external_reference_review.json').write_text(text);(STATIC/'external-reference-review.json').write_text(text)
    md=['# External analyst source review','',f"Source: [{REPO}]({REPO}) · [workbench]({SITE}#overview)",f"Pinned revision: `{manifest['commit']}` · fetched {manifest['retrievedAtUtc']}",'','## Findings','']
    for f in findings:md.extend([f"### {f['priority']}",'',f['finding'],'','Affected pages: '+', '.join(f['pages']),''])
    md.extend(['## Additional source-derived research leads',''])
    for lead in control_leads:md.extend([lead['note'],''])
    md.extend(['## Refresh workflow','','Run `python3 update_csiiiv_reference.py --refresh-pages` to fetch the current selected files, verify hashes, rebuild this review and update the attributed panels. Use `--offline --refresh-pages` to reuse the retained snapshot. Reviewed NIA/HFEP/FMR source extractions are adopted with provenance; affected calculations are rebuilt. Cross-stage identity claims remain separate. Changes are recorded in the manifest and adoption JSON.','','Downloaded source code is retained for reading, never executed. Snapshots are private and ignored by Git; the manifest, downloader and findings are retained. Existing identical files are referenced rather than duplicated.','','## Coordinate updates',''])
    for r in updates:md.append(f"- {r['stage']}: {r['changedRecords']} changed records, {len(r['removedIds'])} removed IDs; {r['referenceRecords']} total. Full before/after values in JSON.")
    (OUT/'external_reference_review.md').write_text('\n'.join(md)+'\n')
    return result

def apply_pages(data=None):
    if not (BASE/'manifest.json').exists():return
    data=data or build()
    from build_investigation_summary import esc,section,table,inject
    def comparison_graph(labels,values):
        maximum=max(values+[1]);svg='<figure><figcaption>Separate source ledgers · billions of pesos · not additive</figcaption><svg class="evidence-graphic" viewBox="0 0 1050 300" role="img" aria-label="Source ledger allocation comparison">'
        for i,(label,value) in enumerate(zip(labels,values)):
            x=100+i*290;height=200*value/maximum
            svg+=f'<rect x="{x}" y="{230-height}" width="130" height="{height}" fill="{["#087e78","#b65b09","#79848b"][i]}"/><text x="{x}" y="{220-height}">{value/1e9:,.3f}B</text><text x="{x}" y="265">{esc(label)}</text>'
        return svg+'</svg></figure>'
    source=data['source'];credits=f'<p>Comparative source: <a href="{SITE}#overview">csiiiv FY2027 budget analysis</a> · <a href="{REPO}/tree/{source["commit"]}">GitHub snapshot {source["commit"][:12]}</a>. Downloaded {esc(source["retrievedAtUtc"])}. Primary budget PDFs remain authoritative. <a href="external-reference-review.json" download>Reconciliation, source hashes and update details (JSON)</a>.</p>'
    targets=sorted({p for f in data['findings'] for p in f['pages']})
    for page in targets:
        relevant=[f for f in data['findings'] if page in f['pages']]
        body=credits+'<ul>'+''.join('<li>'+esc(f['finding'])+'</li>' for f in relevant)+'</ul>'
        leads=[r for r in data.get('additionalResearchLeads',[]) if r['page']==page]
        if leads:body+='<h3>Source-derived research leads</h3>'+''.join('<p>'+esc(r['note'])+'</p>' for r in leads)
        if page in ['nia-irrigation.html','nia.html']:
            n=data['nia'];body+=comparison_graph(['External NEP','External House','Adopted House'],[n['nepPesos'],n['referenceHousePesos'],n['localHousePesos']]);body+=table(['NIA scope','Project rows','Allocation pesos'],[['External NEP detailed annex',n['nepRows'],n['nepPesos']],['External House annex',n['referenceHouseRows'],n['referenceHousePesos']],['Adopted HGAB detailed schedule',n['localHouseRows'],n['localHousePesos']]])
            body+='<p>The preferred House source is the retained second-reading copy. Its audit reports text equivalence across the NIA annex readings; this does not independently authenticate the bill. Annex totals and named major NIA projects are different scopes and must not be added without checking their budget hierarchy.</p>'
        if page=='hfep.html':
            h=data['hfep'];body+=comparison_graph(['NEP facility ledger','House facility ledger','NEP printed control'],[h['nep']['ledgerPesos'],h['house']['ledgerPesos'],h['nep']['verification']['grand_total_php']]);body+=table(['HFEP annex ledger','Facilities','Allocation pesos'],[['External NEP facilities',h['nep']['facilities'],h['nep']['ledgerPesos']],['External House facilities',h['house']['facilities'],h['house']['ledgerPesos']],['NEP printed control', '—',h['nep']['verification']['grand_total_php']]])
            body+='<p>The reviewed detailed NEP annex is adopted as the preferred facility baseline. Programme-level controls remain separate from facility-ledger totals. Printed control minus the NEP facility ledger is ₱'+f"{h['nep']['verification']['grand_total_php']-h['nep']['ledgerPesos']:,}"+'. This difference is retained explicitly. No facility insertion count is imported from title similarity.</p>'
        inject(page,'external-reference-review',section('external-reference-review','Independent source cross-check · current snapshot',body))
        if page=='dpwh-hgab.html':
            path=STATIC/page;text=path.read_text().replace(':not(#supporting-methodology){display:none!important}',':not(#supporting-methodology):not(#external-reference-review){display:none!important}');path.write_text(text)
    # Correct missing-baseline claims without claiming locally verified identities.
    p=STATIC/'nia-irrigation.html';text=p.read_text()
    text=text.replace('comparable detailed NEP baseline missing','detailed external NEP annex available; counterpart reconciliation pending')
    text=text.replace('Not established · comparable detailed NEP baseline missing','Detailed external NEP annex available · counterpart not yet reconciled locally')
    text=text.replace('A comparable detailed NEP baseline is not established.','A detailed external NEP annex is now available; local row-level counterpart reconciliation remains incomplete.')
    text=text.replace('NEP columns remain unestablished until a comparable baseline is verified.','A detailed external NEP annex is available; NEP counterparts remain unestablished until local row-level reconciliation.')
    from build_report_heroes import hero,peso
    n=data['nia']
    if n['localHouseRows']==n['referenceHouseRows'] and n['localHousePesos']==n['referenceHousePesos']:
        delta=n['localHousePesos']-n['nepPesos']
        card=hero('NIA irrigation · NEP → HGAB 3rd reading',peso(abs(delta)), 'net annex allocation '+('increase' if delta>=0 else 'decrease'),peso(n['localHousePesos']),'HGAB detailed irrigation annex', [('NEP projects',f"{n['nepRows']:,}",peso(n['nepPesos'])),('HGAB projects',f"{n['localHouseRows']:,}", 'Reviewed source extraction adopted')], 'Six sub-program controls define the comparable annex scope. Additional recovered rows correct extraction coverage; project-level insertions require separate identity matching.')
    else:
        card=hero('NIA irrigation · coverage under review',f"{n['nepRows']:,}",'detailed NEP annex rows available',peso(n['localHousePesos']),'local HGAB extracted schedule', [('External House rows',f"{n['referenceHouseRows']:,}",peso(n['referenceHousePesos'])),('Local HGAB rows',f"{n['localHouseRows']:,}", 'Scope reconciliation pending')], 'Reviewed source extraction takes priority over conflicting older automated parsing.')
    text=re.sub(r'(<section id="report-hero">).*?(</section>)',lambda m:m[1]+card+m[2],text,count=1,flags=re.S)
    p.write_text(text)
    p=STATIC/'hfep.html';text=p.read_text().replace('Facility-level NEP comparisons need a detailed NEP annex.','A detailed external NEP annex is available; local facility counterpart reconciliation remains pending.').replace('Facility insertions/removals remain unestablished without that detailed baseline.','A detailed external NEP annex is now available; facility insertions/removals remain unestablished until row-level identity and scope are reconciled locally.');p.write_text(text)
    # The prior summary uses a workbook-only scope statement; add the newer availability.
    p=STATIC/'summary.html';text=p.read_text().replace('Detailed NEP works baseline missing','External detailed NEP annex available; local scope reconciliation pending');p.write_text(text)
    for page in targets:
        p=STATIC/page;mirror=OUT/page
        if mirror.exists():mirror.write_text(p.read_text())
    return {'updatedPages':targets,'sourceCommit':source['commit']}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--refresh-pages',action='store_true');args=parser.parse_args();d=build()
    if args.refresh_pages:apply_pages(d)
    print(json.dumps({'source':d['source'],'findings':len(d['findings']),'nia':{k:v for k,v in d['nia'].items() if k!='controls'},'fmrChanges':[{k:v for k,v in r.items() if k!='details'} for r in d['fmrCoordinateUpdates']]},indent=2))
