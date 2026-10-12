#!/usr/bin/env python3
"""Object/fund rows -> traceable agency/PAP baselines, retaining blank and zero distinctions."""
import hashlib,json,re
from collections import defaultdict,Counter
from pathlib import Path
from analyze_priority_repeats import query
from hgab_matching import normalize
from chainage import has_directional_conflict,compare_chainage,compare_tranche
from location_data.project_location_scope import location_conflict,qualified
from difflib import SequenceMatcher
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output';STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def build():
    path=ROOT/'nep_fy2027_all.parquet'
    rows=query(f"SELECT * FROM read_parquet('{path}') WHERE PREXC_LEVEL=7 AND (UACS_AGY_DSC='National Irrigation Administration' OR (UACS_DPT_DSC='Department of Health (DOH)' AND regexp_matches(DSC,'(?i)health facilities enhancement\\s+program')))")
    groups={}
    for r in rows:
        key=(r['agencyKey'],r['PREXC_FPAP_ID'],r.get('OPERUNIT'),r.get('UACS_REG_ID'))
        g=groups.setdefault(key,{'identityCodes':list(key),'agencyKey':r['agencyKey'],'agency':r['UACS_AGY_DSC'],'prexcId':r['PREXC_FPAP_ID'],'region':r.get('UACS_REG_DSC'),'office':r.get('UACS_OPER_DSC'),'title':r['DSC'],'scope':r['allocationNarrativeScope'],'components':[]})
        if normalize(g['title'])!=normalize(r['DSC']):raise ValueError('Same grouped identity has conflicting descriptions; review source rows')
        g['components'].append({k:r.get(k) for k in ['sourceRow','amountPesos','amountPresence','FUNDCD','UACS_FUNDSUBCAT_DSC','UACS_EXP_DSC','UACS_OBJ_DSC','budgetRowType']})
    for g in groups.values():
        funded=[r for r in g['components'] if r['amountPresence']!='blank']
        g['amountPesos']=sum(r['amountPesos'] for r in funded) if funded else None
        g['fundingEvidence']='blank amount; funding unestablished' if not funded else 'explicit zero' if g['amountPesos']==0 else 'positive appropriation' if g['amountPesos']>0 else 'negative appropriation'
        g['id']='NEP:'+json.dumps(g['identityCodes'],separators=(',',':'))
    records=list(groups.values())
    from audit_non_dpwh_stage_controls import build as audit_controls
    audit=audit_controls()
    checks={r['hgabId']:r for r in audit['niaChecks']}
    for agency in {r['agencyKey'] for r in rows}:
        rawtotal=sum(r.get('amountPesos') or 0 for r in rows if r['agencyKey']==agency)
        groupedtotal=sum(g['amountPesos'] or 0 for g in records if g['agencyKey']==agency)
        if rawtotal!=groupedtotal:raise ValueError('Grouping changed ledger money')
    nia=[g for g in records if g['agency']=='National Irrigation Administration'];hfep=[g for g in records if g['agencyKey']=='13:001']
    house=json.loads((ROOT/'hgab_3rd_editions.json').read_text());pairs=[]
    for h in house['nia_named']:
        title=h['projectName'];exact=[n for n in nia if normalize(n['title'])==normalize(title)]
        linked=exact[0] if len(exact)==1 else None
        plausible=[]
        if not linked:
            q=qualified(title)
            for n in nia:
                nq=qualified(n['title'])
                if not q or not nq or not q['province'] or not q['municipality'] or q['province']!=nq['province'] or q['municipality']!=nq['municipality']:continue
                if location_conflict(title,n['title']) or has_directional_conflict(title,n['title']) or compare_tranche(title,n['title'])['tranche_conflict']:continue
                if compare_chainage(title,n['title'])['chainage_status']=='disjoint':continue
                score=SequenceMatcher(None,normalize(title),normalize(n['title']),autojunk=False).ratio()
                if score>=.9:plausible.append({'nepId':n['id'],'title':n['title'],'similarity':round(score,4),'amountPesos':n['amountPesos']})
        status='Unresolved named counterpart; original-source review' if not linked else 'Title appears in NEP with blank funding; allocation not established' if linked['amountPesos'] is None else 'Allocation introduced against explicit NEP zero' if linked['amountPesos']==0 and h['amountPesos']>0 else 'Exact named counterpart · allocation changed' if linked['amountPesos']!=h['amountPesos'] else 'Exact named counterpart · same allocation'
        if plausible:status='Plausible geographic counterpart · scope review'
        pairs.append({'projectName':title,'hgabId':h['id'],'hgabPesos':h['amountPesos'],'sourceVolume':h['sourceVolume'],'sourcePage':h['sourcePage'],'status':status,'nepTitle':linked['title'] if linked else None,'nepId':linked['id'] if linked else None,'nepPesos':linked['amountPesos'] if linked else None,'adjustmentPesos':h['amountPesos']-linked['amountPesos'] if linked and linked['amountPesos'] is not None else None,'workbookRows':','.join(str(c['sourceRow']) for c in linked['components']) if linked else None,'plausibleCounterparts':plausible})
        check=checks[h['id']]
        pairs[-1]['visibleHgabRowVerified']=check['visibleRowVerified']
        if check['visibleRowVerified']:pairs[-1]['sourcePage']=check['evidence']['sourcePage']
    data={'summary':{'workbookComponentRows':len(rows),'groupedEntries':len(records),'niaComponentRows':sum(r['UACS_AGY_DSC']=='National Irrigation Administration' for r in rows),'niaEntries':len(nia),'niaAmountPesos':sum(g['amountPesos'] or 0 for g in nia),'niaFundedEntries':sum(g['amountPesos'] is not None and g['amountPesos']>0 for g in nia),'niaBlankEntries':sum(g['amountPesos'] is None for g in nia),'niaZeroEntries':sum(g['amountPesos']==0 for g in nia),'niaHgabNamedStatuses':dict(Counter(p['status'] for p in pairs)),'hfepOfficeSecretaryEnvelopePesos':sum(g['amountPesos'] or 0 for g in hfep),'hfepCapitalEnvelopePesos':sum(c['amountPesos'] or 0 for g in hfep for c in g['components'] if c['UACS_EXP_DSC']=='Capital Outlays')},'entries':records,'niaNamedComparisons':pairs,
          'scope':'NIA PREXC leaf entries and DOH HFEP programme entries from the NEP workbook. Object/fund components are aggregated by agency+PREXC+operating unit+region. Blank funding is not zero. PREXC leaf is not necessarily a construction site.',
          'method':'Source descriptions are retained. All NIA expenditure classes are included: GOCC project subsidies are classified as MOOE in the workbook, so a Capital-Outlays-only filter would miss them. Exact normalized whole-title NIA counterparts support descriptive allocation changes, with source rows preserved; not certified engineering scope. Fuzzy matches require qualified town/province and no explicit conflicts and do not establish changes. Repeated exact titles across grouped identities remain unresolved. Detailed NIA irrigation appendix rows and HFEP facility rows are not compared one-to-one with programme envelopes.',
          'limits':['Zero difference is possible and is not a parser failure. A nonzero difference can also reflect scope mismatch, incomplete HGAB extraction or a true budget change.','Grouped rows conserve workbook amounts but do not certify physical project identity. Positive components, explicit zero and blank catalogue entries remain separate.','Current HGAB named NIA rows are candidates, not a complete NIA agency ledger. HFEP facility extraction has not been reconciled to a printed programme control.','No claims of facility-level HFEP insertion or detailed NIA appendix insertion can be made from programme-level NEP entries.'],
          'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [path,ROOT/'hgab_3rd_editions.json']]}
    hfep_control=audit['hfepControl'];facility_total=sum(h['amountPesos'] for h in house['hfep'])
    if facility_total!=hfep_control['capitalOutlayPesos']:raise ValueError('HFEP facility extract fails printed CO reconciliation')
    data['hfepStageComparison']={'nepMooePesos':data['summary']['hfepOfficeSecretaryEnvelopePesos']-data['summary']['hfepCapitalEnvelopePesos'],
        'nepCapitalPesos':data['summary']['hfepCapitalEnvelopePesos'],'nepTotalPesos':data['summary']['hfepOfficeSecretaryEnvelopePesos'],
        'hgabMooePesos':hfep_control['mooePesos'],'hgabCapitalPesos':hfep_control['capitalOutlayPesos'],'hgabTotalPesos':hfep_control['totalPesos'],
        'capitalAdjustmentPesos':hfep_control['capitalOutlayPesos']-data['summary']['hfepCapitalEnvelopePesos'],
        'totalAdjustmentPesos':hfep_control['totalPesos']-data['summary']['hfepOfficeSecretaryEnvelopePesos'],
        'hgabFacilityRows':len(house['hfep']),'facilitySumMatchesPrintedCapitalControl':True,'source':hfep_control}
    data['limits'][2]='Current HGAB named NIA rows are not a complete NIA agency ledger. All 32 named row titles/amounts were checked against visible PDF text. The HFEP facility sum reconciles to the printed programme Capital Outlays control, not the programme total including MOOE.'
    data['sourceControlAudit']=audit
    text=json.dumps(data,ensure_ascii=False,indent=2)+'\n';(OUT/'nep_agency_baselines.json').write_text(text);(STATIC/'nep-agency-baselines.json').write_text(text)
    (STATIC/'nep-agency-stage-controls.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    return data

if __name__=='__main__':print(json.dumps(build()['summary'],indent=2))
