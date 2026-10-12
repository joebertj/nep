#!/usr/bin/env python3
"""Validate the imported FMR ledger and bounded 2nd/3rd annex equivalence."""
import csv,hashlib,json,re,subprocess
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from hgab_matching import normalize
from chainage import has_directional_conflict,compare_tranche,compare_chainage
from location_data.project_location_scope import qualified,location_conflict
ROOT=Path(__file__).resolve().parent
RAW=ROOT/'data_sources/fmr_analyst';OUT=ROOT/'analysis_output';STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
PDFS=[ROOT/'HB 10858 FOR 2ND READING/2 - HB 10858 VOL IB.pdf',ROOT/'HB 10858 FOR 3RD READING/2- HB 10858 FOR 3RD READING VOL I-B.pdf']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def clean(text):return re.sub(r'\s+',' ','\n'.join(l for l in text.splitlines() if '.indd' not in l)).strip()
def validate():
    evidence=OUT/'fmr_annex_equivalence.json';hashes=[digest(p) for p in PDFS]
    old=json.loads(evidence.read_text()) if evidence.exists() else {}
    if old.get('pdfSha256')!=hashes:
        text=[]
        for i,p in enumerate(PDFS):
            dest=Path('/private/tmp')/f'fmr-verified-annex-{i}.txt'
            subprocess.run(['gs','-q','-dBATCH','-dNOPAUSE','-sDEVICE=txtwrite','-dFirstPage=667','-dLastPage=726',f'-sOutputFile={dest}',str(p)],check=True,capture_output=True)
            text.append(clean(dest.read_text()))
        old={'pdfSha256':hashes,'sourcePdfs':[str(p.relative_to(ROOT)) for p in PDFS],'pdfPages':[667,726],'annexContentEqual':text[0]==text[1],'normalizedTextSha256':[hashlib.sha256(t.encode()).hexdigest() for t in text],'normalization':'Exclude InDesign .indd production-footer lines; collapse whitespace. No project, coordinate or amount lines removed.','limits':'Bounded text comparison of the FMR annex only, not authentication of the entire bill or independent reconstruction of every ledger cell.'}
        evidence.write_text(json.dumps(old,indent=2)+'\n')
    if not old['annexContentEqual']:raise ValueError('2nd/3rd FMR annex text differs; cannot transfer ledger')
    ledgers={}
    for stage in ['hgab','nep']:
        payload=json.loads((RAW/f'{stage}_fmr_coordinates_normalized.json').read_text());audit=json.loads((RAW/f'{stage}_fmr_audit.json').read_text());projects=payload['projects']
        if not audit['passed']:raise ValueError('Imported audit did not pass')
        if stage=='hgab' and audit['metadata']['source_sha256']!=hashes[0]:raise ValueError('House source PDF hash differs')
        if len({p['project_id'] for p in projects})!=len(projects):raise ValueError('Duplicate FMR source IDs')
        if len(projects)!=audit['summary']['projects'] or sum(p['amount_php'] for p in projects)!=audit['summary']['project_ledger_total_php']:raise ValueError('FMR ledger total/count mismatch')
        csvrows=list(csv.DictReader((RAW/f'{stage}_fmr_projects_normalized.csv').open()))
        if {(r['project_id'],r['title'],int(r['amount_php'])) for r in csvrows}!={(p['project_id'],p['title'],p['amount_php']) for p in projects}:raise ValueError('CSV/JSON identity disagreement')
        totals=Counter()
        for p in projects:totals[p['region']]+=p['amount_php']
        for check in audit['rollup_checks']:
            if check['label'] in totals and totals[check['label']]!=check['printed_amount_php']:raise ValueError('Region control differs')
        ledgers[stage]=projects
    return ledgers,old

def coordinate_key(p):
    if p['status']!='normalized' or p['review_flags']:return None
    return json.dumps([[[round(v,6) for v in point] for point in segment] for segment in p['coordinates'] if segment and all(point is not None for point in segment)],separators=(',',':'))
def region(v):return normalize(v).replace('region ','').replace('iva','iv a').replace('ivb','iv b')
def build():
    ledgers,evidence=validate();nep=ledgers['nep'];house=ledgers['hgab'];idx=defaultdict(list);used=set();matches=[]
    for i,p in enumerate(nep):idx[(normalize(p['title']),region(p['region']))].append(i)
    for p in house:
        exact=idx[(normalize(p['title']),region(p['region']))];free=[i for i in exact if i not in used];key=coordinate_key(p)
        selected=None;status='Potential insertion · no plausible NEP counterpart found';plausible=[]
        if free:
            selected=min(free,key=lambda i:(coordinate_key(nep[i])!=key,abs(nep[i]['amount_php']-p['amount_php']),i));used.add(selected)
            status='Exact title/region and normalized coordinate agreement' if key and coordinate_key(nep[selected])==key else 'Exact title/region · segment evidence needs review'
        elif exact:status='Ambiguous occurrence · NEP title already paired'
        else:
            q=qualified(p['title'])
            if q and q['province'] and q['municipality']:
                for i,n in enumerate(nep):
                    nq=qualified(n['title'])
                    if not nq or q['province']!=nq['province'] or q['municipality']!=nq['municipality']:continue
                    if location_conflict(p['title'],n['title']) or has_directional_conflict(p['title'],n['title']) or compare_tranche(p['title'],n['title'])['tranche_conflict']:continue
                    score=SequenceMatcher(None,normalize(p['title']),normalize(n['title']),autojunk=False).ratio()
                    # Fuzzy links are only a reason to withhold an insertion claim.
                    if score>=.90:plausible.append({'nepId':n['project_id'],'title':n['title'],'similarity':round(score,4)})
            if plausible:status='Plausible title counterpart · scope review'
        matches.append({'hgabId':p['project_id'],'projectName':p['title'],'region':p['region'],'amountPesos':p['amount_php'],'status':status,'nepId':nep[selected]['project_id'] if selected is not None else None,'nepTitle':nep[selected]['title'] if selected is not None else None,'nepPesos':nep[selected]['amount_php'] if selected is not None else None,'allocationAdjustmentPesos':p['amount_php']-nep[selected]['amount_php'] if selected is not None else None,'plausibleCounterparts':plausible,'coordinateStatus':p['status'],'coordinateReviewFlags':p['review_flags'],'sourcePage':p['source']['pdf_page'],'printedPage':p['source']['printed_page']})
    data={'scope':'DA locally-funded FMR annex only; NEP proposal and locally named HGAB 3rd reading. Not the full DA budget.','annexEquivalence':evidence,'summary':{'nepProjects':len(nep),'nepPesos':sum(p['amount_php'] for p in nep),'hgabProjects':len(house),'hgabPesos':sum(p['amount_php'] for p in house),'netAdjustmentPesos':sum(p['amount_php'] for p in house)-sum(p['amount_php'] for p in nep),'matchStatuses':dict(Counter(m['status'] for m in matches)),'unpairedNepProjects':len(nep)-len(used),'hgabCoordinateReview':sum(p['status']!='normalized' for p in house),'nepCoordinateReview':sum(p['status']!='normalized' for p in nep)},'projects':house,'nepProjects':nep,'stageMatches':matches,'unpairedNep':[p for i,p in enumerate(nep) if i not in used],
          'method':'One-to-one full normalized title plus printed-region join; normalized coordinate arrays (six decimal digits) strengthen segment evidence but never define road length. Free occurrences selected by coordinate agreement, then amount difference. Already-paired titles remain ambiguous. Fuzzy titles ≥90% with qualified town/province and no explicit location/direction/tranche conflict withhold an insertion claim; they do not establish retention. Missing counterparts are review candidates, not certified insertions/removals. Imported coordinate repairs and anomalies retain all original flags.',
          'limits':['Coordinates are endpoints, not measured road alignment length. Straight-line segment distances are diagnostics only and never supply cost-per-road-meter denominators.','The NEP standalone PDF is not available locally for independent cell extraction; imported source hash and audit provenance retained.','Regional equality and title agreement do not certify funded engineering scope. No attribution to authors or beneficiaries.','The annex text equivalence check excludes production-footer timestamps only and does not authenticate either full bill.'],
          'sources':[{'file':str(p.relative_to(ROOT)),'sha256':digest(p)} for p in sorted(RAW.glob('*')) if p.is_file()]}
    (OUT/'fmr_corrected_dataset.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');(STATIC/'fmr-data.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    # Canonical inputs for downstream cost coverage and reading-stage summaries.
    for stage,filename in [('2nd','hgab_2nd_editions.json'),('3rd','hgab_3rd_editions.json')]:
        path=ROOT/filename;payload=json.loads(path.read_text());rows=[]
        for p in house:
            rows.append({'id':f'FMR-{stage}-{p["project_id"]}','code':f'FMR-{stage}-{p["project_id"]}','fiscalYear':2027,'agency':'Department of Agriculture','program':'Farm-to-Market Roads','pap3':'FMR','office':'','region':p['region'],'projectName':p['title'],'amountPesos':p['amount_php'],'amount':p['amount_php']/1000,'sourceVolume':PDFS[stage=='3rd'].name,'sourcePage':p['source']['pdf_page'],'sourceContext':p['title']+'\n'+p['coordinates_raw'],'coordinateStatus':p['status'],'coordinateReviewFlags':p['review_flags'],'analystSourceId':p['project_id'],'printedPage':p['source']['printed_page']})
        payload['fmr']=rows;payload['fmrProvenance']=evidence;path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
        if stage=='3rd':
            p=ROOT/'hb10858_3rd_fmr_projects.json';old=json.loads(p.read_text());old['data']['data']=rows;old['metadata']={'source':'Corrected analyst FMR row ledger; bounded text equivalence with local 3rd-reading annex verified','candidateCount':len(rows),'totalPesos':data['summary']['hgabPesos'],'audit':'analysis_output/fmr_annex_equivalence.json'};p.write_text(json.dumps(old,ensure_ascii=False,indent=2)+'\n')
    # Refresh only FMR reading data, keeping all other agency analyses intact.
    from build_hgab_revision_pages import compare_rows
    second=json.loads((ROOT/'hgab_2nd_editions.json').read_text())['fmr'];third=json.loads((ROOT/'hgab_3rd_editions.json').read_text())['fmr'];revision=compare_rows(second,third,'fmr')
    path=STATIC/'hgab-revision-data.json';d=json.loads(path.read_text());d['fmr']=revision;path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    path=OUT/'hgab_reading_revision_summary.json';d=json.loads(path.read_text());d['fmr']=revision['summary'];path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    path=OUT/'hgab_non_dpwh_insertion_summary.json'
    if path.exists():
        d=json.loads(path.read_text());d['FMR']={'hgabCandidateCount':len(house),'hgabCandidateAmountPesos':data['summary']['hgabPesos'],
            'nepRegionalCapitalEnvelopePesos':data['summary']['nepPesos'],'nepProjectCount':len(nep),
            'nepRegionalCapitalEnvelopeByRegionPesos':dict(Counter({r:sum(p['amount_php'] for p in nep if p['region']==r) for r in {p['region'] for p in nep}})),
            'matchStatuses':data['summary']['matchStatuses'],'interpretation':'Detailed NEP FMR annex now available: use the corrected source-row comparison, not the earlier envelope-only itemization classification.'}
        path.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    csvpath=OUT/'hgab_non_dpwh_insertion_candidates.csv'
    if csvpath.exists():
        with csvpath.open() as f:
            reader=csv.DictReader(f);columns=reader.fieldnames;kept=[r for r in reader if r['family']!='FMR']
        for m in matches:
            kept.append({'family':'FMR','comparison':m['status'],'hb_project':m['projectName'],'hb_amount_pesos':m['amountPesos'],
                         'nep_project':m['nepTitle'] or '', 'nep_amount_pesos':m['nepPesos'] if m['nepPesos'] is not None else '',
                         'source_page':m['sourcePage'],'source_text':m['hgabId']})
        with csvpath.open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(kept)
    return data
if __name__=='__main__':print(json.dumps(build()['summary'],indent=2))
