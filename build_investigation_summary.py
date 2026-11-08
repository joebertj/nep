#!/usr/bin/env python3
"""Build investigative talking points and supporting analyses from workspace data."""
import csv
import hashlib
import html
import io
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path
from report_hero_module import STYLE
from hgab_matching import UNMATCHED, is_fap
from build_repeat_stage_survival import build as build_survival
from build_rcs_stage_trace import build as build_rcs_trace
from build_congress_benchmark import build as build_benchmark, render as render_benchmark

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
SOURCES=[]

def read(name):
    p=STATIC/name;SOURCES.append({'file':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    return json.loads(p.read_text())

def esc(v):return html.escape(str(v),quote=True)
def peso(v):return '₱'+f'{v/1e9:,.3f}B' if v>=1e9 else '₱'+f'{v/1e6:,.3f}M'

def table(headers,rows):
    csvbuffer=io.StringIO();writer=csv.writer(csvbuffer,lineterminator='\n');writer.writerow(headers);writer.writerows(rows)
    # Each export is self-contained and works on file:// previews.
    encoded=esc(csvbuffer.getvalue())
    from report_currency_module import format_cell
    return f'<button class="export-btn" type="button" data-csv="{encoded}">Export CSV</button><div class="evidence-table"><table><thead><tr>'+''.join(f'<th>{esc(v)}</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{esc(format_cell(headers[i],v))}</td>' for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>'

CSS='''<style id="investigation-evidence-style">.investigation-evidence{margin:24px 0;padding:24px;border:1px solid #c6dbd6;border-radius:14px;background:#fff;color:#18303b}.investigation-evidence h2{margin:0 0 12px}.investigation-evidence p{max-width:1100px}.evidence-table{width:100%;overflow-wrap:anywhere}.evidence-table table{width:100%;border-collapse:collapse;table-layout:fixed}.evidence-table th,.evidence-table td{position:static!important;text-align:left!important;white-space:normal!important;padding:12px;border-bottom:1px solid #d9e3e1;vertical-align:top}.evidence-table th{background:#eef5f3}.evidence-graphic{display:block;width:100%;height:auto;max-height:360px;margin:16px 0}.export-btn{background:#b65b09!important;color:#fff!important;border:1px solid #914600!important;border-radius:8px;padding:9px 14px;margin:10px 0;font-weight:700;cursor:pointer}.queue-controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.queue-controls button:not(.export-btn){padding:8px 12px}.queue-flag-button{border:0;background:transparent;font-size:1.05rem;letter-spacing:.03em;cursor:pointer}.queue-flag-button:focus-visible,.queue-controls button:focus-visible{outline:3px solid #087e78;outline-offset:2px}.flag-evidence-dialog{width:min(720px,calc(100% - 32px));max-height:80vh;overflow:auto;border:1px solid #9bb7af;border-radius:14px;padding:22px;color:#18303b}.flag-evidence-dialog::backdrop{background:#102f3e99}.flag-evidence-dialog form{display:flex;justify-content:flex-end}.flag-evidence-dialog li{margin:12px 0}.flag-evidence-dialog li p{margin:4px 0}.investigation-evidence .caution{padding:14px;background:#fff4dd;border-left:4px solid #ba7800}.finding{padding:24px;border-radius:14px;border:1px solid #d9e3e1;background:#fff;margin:18px 0}.finding h2{margin:0 0 8px}.finding .rank{color:#087e78;font-weight:800}.finding .lead{font-size:1.4rem;font-weight:750}.finding dt{font-weight:750;margin-top:12px}.finding dd{margin:4px 0}.finding a{color:#087e78;font-weight:700}.finding[hidden],tr[hidden]{display:none}.summary-controls{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.summary-controls input,.summary-controls select{padding:10px;border:1px solid #b6c9c4;border-radius:8px;font:inherit}.summary-controls input{flex:1;min-width:200px}@media(max-width:650px){.evidence-table th,.evidence-table td{padding:7px;font-size:12px}.finding,.investigation-evidence{padding:16px}}</style>'''
SUMMARY_CARD_CSS='''<style id="summary-priority-cards-style">.summary-lead-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:18px 0}.summary-priority-card{display:flex;flex-direction:column;min-height:190px;padding:20px;border:1px solid #c6dbd6;border-top:5px solid #087e78;border-radius:14px;background:#fff;color:#18303b;text-decoration:none;box-shadow:0 3px 12px #18303b0b;transition:transform .15s ease,box-shadow .15s ease}.summary-priority-card:hover{transform:translateY(-2px);box-shadow:0 8px 20px #18303b18}.summary-priority-card:focus-visible{outline:3px solid #087e78;outline-offset:3px}.summary-priority-card .summary-card-rank{font-size:.78rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:#087e78}.summary-priority-card h3{margin:8px 0;font-size:1.16rem;line-height:1.3}.summary-priority-card .summary-card-lead{margin:0 0 12px;font-size:1.02rem;font-weight:700}.summary-priority-card .summary-card-exposure{margin:auto 0 0;padding-top:12px;border-top:1px solid #d9e3e1;font-size:.9rem;color:#405762}.summary-priority-card .summary-card-exposure strong{color:#18303b}@media(max-width:720px){.summary-lead-grid{grid-template-columns:1fr}.summary-priority-card{min-height:0}}</style>'''
JS='''<script id="investigation-evidence-script">document.addEventListener('click',e=>{const b=e.target.closest('[data-csv]');if(!b)return;const url=URL.createObjectURL(new Blob(['\ufeff'+b.dataset.csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=(document.title.toLowerCase().replace(/[^a-z0-9]+/g,'-')+'-evidence.csv');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});</script>'''

def section(identifier,title,body):
    return f'<section id="{identifier}" class="investigation-evidence"><h2>{esc(title)}</h2>{body}</section>'

def remove_section(page, identifier):
    """Remove one complete section, including nested section elements."""
    start_match=re.search(rf'<section\b(?=[^>]*\bid=["\']{re.escape(identifier)}["\'])[^>]*>',page,re.I)
    if not start_match:
        return page
    token=re.compile(r'</?section\b[^>]*>',re.I)
    depth=0
    for match in token.finditer(page,start_match.start()):
        if match.group(0).lower().startswith('</'):
            depth-=1
            if depth==0:
                return page[:start_match.start()]+page[match.end():]
        else:
            depth+=1
    return page

def remove_line_item_queue(page):
    page=remove_section(page,'summary-top-line-items')
    return re.sub(r'<p\b[^>]*class=["\'][^"\']*summary-queue-jump[^"\']*["\'][^>]*>.*?</p>', '', page, flags=re.I|re.S)

def refresh_undocumented_hgab_card(page):
    """Refresh the restored summary card from the consolidated all-HGAB table."""
    coverage_path=STATIC/'hgab-document-coverage.json'
    stats_path=STATIC/'dpwh-in-depth-data.json'
    coverage=json.loads(coverage_path.read_text(encoding='utf-8'))
    stats=json.loads(stats_path.read_text(encoding='utf-8'))['senateSupportingDocumentCoverageAllHgab']
    rows=coverage.get('projects',[])
    expected=int(stats['denominatorProjectRows'])
    if len(rows)!=expected or len(rows)!=int(coverage.get('denominatorProjectRows',-1)):
        raise ValueError(f'All-HGAB document coverage mismatch: {len(rows)} project rows, expected {expected}')
    missing=[row for row in rows if not row.get('proposalDocumentsMatched') and not row.get('senateHgabDocumentsMatched')]
    missing_count=len(missing)
    missing_pesos=sum(int(row.get('amountPesos') or 0) for row in missing)
    expected_missing=int(stats['rowsWithoutProposalOrSenateMatch'])
    if missing_count!=expected_missing:
        raise ValueError(f'All-HGAB unmatched count mismatch: table has {missing_count}, summary stats have {expected_missing}')
    total_pesos=sum(int(row.get('amountPesos') or 0) for row in rows)
    matched_count=expected-missing_count
    matched_pct=100*matched_count/expected if expected else 0
    display_amount=(f'₱{missing_pesos/1e9:,.2f}B' if missing_pesos>=1_000_000_000
                    else f'₱{missing_pesos/1e6:,.2f}M')
    card_copy=(f'Across all {expected:,} HGAB rows, {matched_count:,} ({matched_pct:.2f}%) have a Proposal or Senate HGAB document match. '
               f'{missing_count:,} rows worth {display_amount} currently have no matched document from either source. '
               'The reported Senate/GAB removals (295 items; ₱8.836B) remain aggregate-only and cannot be assigned to individual rows from the available data.')
    card_pattern=r'<article class="priority-card">(?:(?!</article>).)*?<h3>Undocumented HGAB</h3>.*?</article>'
    match=re.search(card_pattern,page,re.S)
    if not match:
        raise ValueError('Restored summary is missing the Undocumented HGAB priority card')
    card=match[0]
    card=re.sub(r'(<strong class="priority-metric">).*?(</strong>)',
                lambda m:m[1]+f'{missing_count:,} remain · {display_amount}'+m[2],card,count=1,flags=re.S)
    card=re.sub(r'<p>.*?</p>',lambda _m:'<p>'+html.escape(card_copy)+'</p>',card,count=1,flags=re.S)
    page=page[:match.start()]+card+page[match.end():]
    page=re.sub(r'(<div><span>Undocumented HGAB projects</span><strong>).*?(</strong></div>)',
                lambda m:m[1]+f'{missing_count:,} · {display_amount}'+m[2],page,count=1,flags=re.S)
    page=re.sub(r'<p>Of the ₱183\.926806B no-document inventory,.*?</p>',
                lambda _m:'<p>'+html.escape(card_copy)+'</p>',page,count=1,flags=re.S)
    return page,{'rows':missing_count,'allocationPesos':missing_pesos,'matchedRows':matched_count,
                 'denominatorRows':expected,'matchedPct':round(matched_pct,2),'totalAllocationPesos':total_pesos}

def refresh_connectivity_card(page):
    """Keep the summary's FMR lead aligned with connectivity's current classes."""
    data=json.loads((STATIC/'connectivity-data.json').read_text(encoding='utf-8'))
    rows=data.get('projects',[])
    classes=Counter(row.get('connectivityClass') for row in rows)
    flag='Flag FMR · only road or mapped cropland ≤500 m'
    double='Double Flag FMR · road and mapped cropland >500 m'
    review='Review · other distance combinations'
    baseline='Baseline FMR · road and mapped cropland ≤500 m'
    flagged_count=classes[flag]+classes[double]
    flagged_pesos=sum(int(row.get('amountPesos') or 0) for row in rows if row.get('connectivityClass') in {flag,double})
    review_rows=[row for row in rows if row.get('connectivityClass')==review]
    baseline_rows=[row for row in rows if row.get('connectivityClass')==baseline]
    coordinate_rows=sum(bool(row.get('coordinateQualityFlag')) for row in rows)
    amount=lambda value:f'₱{value/1e9:,.3f}B' if value>=1e9 else f'₱{value/1e6:,.3f}M'
    pattern=r'<article class="priority-card">(?:(?!</article>).)*?<h3>FMR road and cropland proximity</h3>.*?</article>'
    match=re.search(pattern,page,re.S)
    if not match:
        raise ValueError('Restored summary is missing the FMR connectivity priority card')
    card=match[0]
    card=re.sub(r'(<strong class="priority-metric">).*?(</strong>)',
                lambda m:m[1]+f'{amount(flagged_pesos)} · {flagged_count:,} Flag / Double Flag projects'+m[2],card,count=1,flags=re.S)
    secondary=(f'<div class="priority-secondary"><span><strong>{len(review_rows):,}</strong> Review · {amount(sum(int(r.get("amountPesos") or 0) for r in review_rows))}</span>'
               f'<span><strong>{len(baseline_rows):,}</strong> Baseline · {amount(sum(int(r.get("amountPesos") or 0) for r in baseline_rows))}</span>'
               f'<span><strong>{coordinate_rows:,}</strong> Coordinate review</span><span><strong>{len(rows):,}</strong> FMRs screened</span></div>')
    card=re.sub(r'<div class="priority-secondary">.*?</div>',lambda _m:secondary,card,count=1,flags=re.S)
    description=('Printed route endpoints are compared with DPWH classified roads and ESA WorldCover 2021 mapped cropland using a shared 500 m cutoff. '
                 'Rows with endpoint gaps over 20 km remain in coordinate review. Proximity does not prove road access or farm use.')
    card=re.sub(r'<p>.*?</p>',lambda _m:'<p>'+html.escape(description)+'</p>',card,count=1,flags=re.S)
    return page[:match.start()]+card+page[match.end():],{'flagOrDoubleRows':flagged_count,'flagOrDoublePesos':flagged_pesos,
        'baselineRows':len(baseline_rows),'reviewRows':len(review_rows),'coordinateReviewRows':coordinate_rows,'totalRows':len(rows)}

def integer_units(weights,total,ids):
    shares=[total*w/sum(weights) for w in weights];rounded=[math.floor(v) for v in shares]
    order=sorted(range(len(weights)),key=lambda i:(-(shares[i]-rounded[i]),ids[i]))
    for i in order[:total-sum(rounded)]:rounded[i]+=1
    if sum(rounded)!=total:raise ValueError('RCS scenario does not conserve units')
    return shares,rounded

def main():
    # Consume the latest data products. A summary build owns summary.html and
    # must not invoke other page builders as a side effect.
    length_data=json.loads((ROOT/'analysis_output/cost_per_km.json').read_text())
    dpwh_indepth_data=json.loads((ROOT/'analysis_output/dpwh-in-depth-data.json').read_text())
    mpb=json.loads((ROOT/'analysis_output/mpb_analysis.json').read_text())['summary']
    dpwh=read('dpwh-data.json');rcs=read('rcs-data.json');congress=read('congress-data.json')
    innovations=read('budget-innovations-data.json');reading=read('dpwh-hgab-comparison.json');revision=read('hgab-revision-data.json')
    survival=build_survival()
    trace=build_rcs_trace()['summary']
    clear_pairs=survival['summary']['pairStatuses'].get('Clear retained link',0)
    clear_proposals=survival['summary']['uniqueStatuses'].get('Clear retained link',0)
    districts=rcs['districts'];n=len(districts);pool=rcs['summary']['wholeUnits'];unit=4200000
    if n!=199 or pool!=199 or any(r['currentPesos']!=unit for r in districts):raise ValueError('Uniform RCS talking point no longer applies')
    mean=[r['averageAnnualMm'] for r in districts];ids=[r['office'] for r in districts]
    fractions,whole=integer_units(mean,pool,ids)
    rain_by_name={r['province']:r for r in rcs['rainfall']['provinces']}
    # Median sensitivity uses only observed province series. The one regional
    # fallback keeps its mean and is explicitly counted as a sensitivity limit.
    median=[rain_by_name.get(r['rainfallArea'],{}).get('medianAnnualMm',r['averageAnnualMm']) for r in districts]
    median_fractions,median_whole=integer_units(median,pool,ids)
    current=[r['currentUnits'] for r in districts];province=[r['recommendedUnits'] for r in districts]
    shifts=lambda values:sum(abs(a-b) for a,b in zip(current,values))/2
    rcs_stats={'offices':n,'poolPesos':n*unit,'allocationCV':0,'rainfallProxyCV':statistics.pstdev(mean)/statistics.mean(mean),
               'minimumRainMm':min(mean),'maximumRainMm':max(mean),'wettestToDriestRatio':max(mean)/min(mean),
               'officeMeanUnitsMoved':shifts(whole),'provinceMeanUnitsMoved':shifts(province),'officeMedianUnitsMoved':shifts(median_whole),
               'meanMedianDifferentOfficeUnits':sum(a!=b for a,b in zip(whole,median_whole)),
               'regionalFallbackOffices':sum(r['rainfallArea'] not in rain_by_name for r in districts),
               'correlation':'Undefined: allocation variance is zero; no correlation p-value reported.'}
    # RCS evidence sections are rendered by build_rcs_pow_review.py.

    repeat=dpwh['priorityRepeats'];unique={}
    for row in repeat:
        key=row['source_code']
        if key in unique and unique[key]['amount_2027']!=row['amount_2027']:raise ValueError('Conflicting current repeat amount')
        unique[key]=row
    strata=Counter(r['chainage_status'] for r in repeat)
    repeat_stats={'comparisonPairs':len(repeat),'uniqueCurrentProposals':len(unique),'uniqueCurrentPesos':sum(r['amount_2027'] for r in unique.values()),'chainageStatuses':dict(strata),'overlapUniqueProposals':len({r['source_code'] for r in repeat if r['chainage_status']=='overlap'}),'trancheStatuses':dict(Counter(r['tranche_status'] for r in repeat))}
    test=dpwh['fiveMillionStats']['results'][0];N=test['district_offices'];a=test['overlap_offices'];road=test['road_offices'];flood=test['flood_offices'];b=road-a;c=flood-a;d=N-a-b-c
    p=sum(math.comb(road,k)*math.comb(N-road,flood-k)/math.comb(N,flood) for k in range(a,min(road,flood)+1) if 0<=flood-k<=N-road)
    odds=a*d/(b*c);se=math.sqrt(sum(1/v for v in [a,b,c,d]));ci=[math.exp(math.log(odds)-1.96*se),math.exp(math.log(odds)+1.96*se)]
    price_stats={'N':N,'roadOffices':road,'floodOffices':flood,'overlap':a,'expectedOverlap':road*flood/N,'hypergeometricP':p,'oddsRatio':odds,'wald95CI':ci,'regionalPermutationP':test['region_controlled_simulated_p_value'],'regionalPermutationRepetitions':test['simulation_repetitions'],'postSelectionAdjusted':False}
    # Repeat-analysis sections are owned by repeats.html. Do not inject them
    # into dpwh.html: this builder runs during document refreshes and used to
    # append sections after the consolidated HGAB coverage table.
    from analyze_within_stage_repeats import build as build_within_stage, render as render_within_stage
    # Keep the within-stage comparison on repeats.html only.
    # Keep HGAB survival analysis on repeats.html only.

    csvpath=ROOT/'analysis_output/hb_nep_comparison_3rd.csv';SOURCES.append({'file':csvpath.name,'sha256':hashlib.sha256(csvpath.read_bytes()).hexdigest()})
    with csvpath.open() as f:comparison=list(csv.DictReader(f))
    oo2_impact=json.loads((ROOT/'analysis_output/dpwh_oo2_hgab_impact.json').read_text())
    oo2_matched_ids={r['hgabCandidate']['id'] for r in oo2_impact['records']
                     if r.get('status')=='High-confidence candidate' and r.get('hgabCandidate')}
    domestic=[r for r in comparison if r['comparison']==UNMATCHED and not is_fap(r)
              and r.get('hgab_id') not in oo2_matched_ids]
    # DPWH HGAB page owner renders its insertion evidence section.

    s=congress['summary'];coverage=s['strictAssignedPesos']/s['sourceTotalPesos']
    # Congress page owner renders attribution coverage from congress-data.json.
    # Congress page owner renders attribution coverage from congress-data.json.
    try:
        benchmark=build_benchmark()
    except ValueError as exc:
        cached_benchmark=STATIC/'congress-benchmark.json'
        if not cached_benchmark.is_file():
            raise
        print(f'Congress benchmark refresh skipped ({exc}); retaining the last reconciled benchmark.')
        benchmark=json.loads(cached_benchmark.read_text())

    inspire=next(r for r in innovations['candidates'] if r['id']=='inspire')
    # Budget innovations page owner renders the INSPIRE history section.

    findings=[
        {'rank':1,'id':'rcs','title':'RCS: identical budget packages across unequal rainfall proxies','lead':f'199 offices × ₱4.2M = {peso(n*unit)}','basis':'Direct allocation observation; rainfall need remains a proxy','page':'rcs.html#rcs-statistical-evidence','question':'What policy or engineering design justifies one identical budget unit per office?','evidence':f'All district-office RCS lines have the same amount. Province/regional rainfall proxies differ by {max(mean)/min(mean):.2f}×. Alternative formulas move different numbers of budget units.','alternative':'Standard package costs or a minimum coverage policy may justify equal allocations. Rainfall alone does not measure demand.','next':'Obtain siting, design capacity, water demand, catchment area and existing RCS inventory.','caution':'DEO is not LEG; province rainfall is not a district observation. Returning FY2026 program.'},
        {'rank':2,'id':'prices','title':'Exact ₱5M road and flood allocations cluster in the same offices','lead':f'{a} overlapping offices vs {road*flood/N:.1f} expected under independence','basis':'Exploratory statistical association','page':'repeats.html#dpwh-investigation-evidence','question':'Does standard design, office workload or coordinated allocation explain the co-occurrence?','evidence':f'Office odds ratio {odds:.2f}; unadjusted exact p={p:.3g}. Region-controlled result is also unusual under its stated null.','alternative':'Common specifications, office workload and project mix can create clustering.','next':'Pre-specify work-type and workload controls; inspect quantities and comparable prior-year prices.','caution':'Threshold/category selection was post hoc. Association does not establish procurement splitting or intent.'},
        {'rank':3,'id':'repeats','title':'Recurring project titles: inspect overlapping work before alleging duplication','lead':f'{clear_pairs} of {len(repeat)} NEP comparison pairs clearly retained in HGAB','basis':'Scope-screened comparison candidates','page':'repeats.html#repeat-hgab-survival','question':'Are new appropriations paying for already-funded components or legitimate continuation?','evidence':f'{clear_proposals} of {len(unique)} distinct NEP repeat-screen proposals have clear HGAB links. {repeat_stats["overlapUniqueProposals"]} proposals have explicit overlapping historical chainage. {peso(repeat_stats["uniqueCurrentPesos"])} is the unique NEP proposal allocation, not alleged loss.','alternative':'Multi-year implementation, rehabilitation and distinct components can share names and segments.','next':'Prioritize explicitly overlapping retained proposals and high amounts; compare contracts, quantities, tranche scopes and completion.','caution':'The 737 headline counts NEP–old GAA comparison pairs. Potential retention and missing counterparts remain separate.'},
        {'rank':2,'id':'insertions','title':'HGAB-only candidates after OO2 adjustment','lead':f'{len(domestic):,} domestic records remain after excluding {len(oo2_matched_ids):,} high-confidence OO2 matches','basis':'OO2-adjusted source and matcher reconciliation; review remains provisional','page':'dpwh-OO2-hgab.html#hgab-investigation-evidence','question':'Which remaining HGAB-only candidates have no NEP counterpart after the OO2 amendments are accounted for?','evidence':f'The pre-OO2 screen had {len(domestic)+len(oo2_matched_ids):,} domestic candidates. Excluding {len(oo2_matched_ids):,} unique HGAB lines with high-confidence OO2 amendment matches leaves {len(domestic):,}, carrying {peso(sum(int(r["amountPesos"]) for r in domestic))}. Nine amendment rows remain under review and are not excluded from this count.','alternative':'OO2 title changes may refer to changed scope, and the workbook’s row totals do not reconcile; review candidates need source-level adjudication.','next':'Review the nine uncertain amendment-to-HGAB links against the source pages, scope and line amounts.','caution':'An OO2 match is a candidate correspondence, not proof of identical scope or formal NEP incorporation; HGAB-only remains a review classification, not a confirmed insertion.'},
        {'rank':5,'id':'inspire','title':'INSPIRE: a large returning named appropriation needs a whole-project ledger','lead':f'{peso(inspire["fy2027Pesos"])} proposed in FY2027','basis':'Direct appropriation history; scope unresolved','page':'budget-innovations.html#innovation-investigation-evidence','question':'What is the total approved cost and which unfinished components explain the new appropriation?','evidence':'Named GAA lines exist in FY2023 and FY2025; FY2027 is not a first appearance.','alternative':'A legitimate phased project can require multiple appropriations.','next':'Obtain total project cost, phases, progress, obligations, disbursements and procurement records.','caution':'Appropriations are not actual spending; stage/year sums do not prove duplication.'}]
    findings.append({'rank':3,'id':'mpb','title':'Multi-purpose buildings: a large share needs NEP counterpart review',
        'lead':f'{mpb["insertionCandidates"]:,} potential insertion candidates · {peso(mpb["insertionPesos"])}',
        'basis':'Parser- and matching-dependent program screen','page':'mpb.html#mpb-insertions',
        'question':'Which MPB lines are genuinely new, and what documented facility needs and designs support them?',
        'evidence':f'The HGAB MPB PAP contains {mpb["hgabLines"]:,} lines carrying {peso(mpb["hgabPesos"])}. {mpb["ambiguousLines"]:,} counterpart cases remain separate from insertion candidates. The historical screen has {mpb["repeatPairs"]} comparison pairs covering {mpb["repeatProposals"]} distinct NEP proposals.',
        'alternative':'Renaming, combined occurrences and legitimate phased construction can explain unmatched or recurring titles. Similar amounts can reflect standard designs.',
        'next':'Audit original NEP/HGAB pages; obtain building purpose, floor area, design, quantities, contract scope and completion records.',
        'caution':'MPB overlaps the full DPWH insertion/repeat findings; do not add their amounts. Equal allocations are not equal construction unit prices.'})
    length_groups={r['category']:r for r in length_data['summary']}
    length_lead=' · '.join(f'{name}: {length_groups[name]["missingPct"]:.2f}%' for name in ('Roads','Bridges','FMR'))
    findings.append({'rank':7,'id':'length-coverage','title':'Length and chainage gaps limit budget scrutiny',
        'lead':length_lead+' without usable extracted length',
        'basis':'Extracted metadata coverage; original-document completeness unverified',
        'page':'cost-matching.html#cost-coverage',
        'question':'Can the funded segment and engineering length be established for every allocation?',
        'evidence':' · '.join(f'{name}: {length_groups[name]["withLength"]:,}/{length_groups[name]["lineItems"]:,} lines have derivable stated lengths' for name in ('Roads','Bridges','FMR'))+'. Official programs have separate denominators on the supporting page.',
        'alternative':'Lengths may be recorded in engineering schedules or continuation text not recovered by this extraction; incomplete metadata need not reflect deliberate omission.',
        'next':'Inspect original source pages and obtain funded-segment boundaries, complete chainage, project quantities and bridge spans; reconcile extraction gaps before alleging disclosure failures.',
        'caution':'Missing includes absent and unusable extracted evidence, not proof the original documents lack length. Coordinate distances do not establish construction length; mixed scopes are separate.'})
    findings.append({'rank':8,'id':'cost-per-km','title':'Allocation per stated meter: inspect scope before comparing rates',
        'lead':f'{sum(r["highRateCandidate"] for r in length_data["projects"] if r["category"]=="Roads"):,} road and {sum(r["highRateCandidate"] for r in length_data["projects"] if r["category"]=="Bridges")} bridge high-rate candidates · FMR peers insufficient',
        'basis':'Descriptive allocation/segment-length proxy; comparable engineering costs unavailable',
        'page':'cost-per-km.html#length-density-groups',
        'question':'Do apparently high rates reflect short printed segments, structures, broader funded scope, or unusually costly comparable work?',
        'evidence':'Whole HGAB line-item allocation is divided by its derivable stated segment meters. Roads, bridges and FMR are displayed separately, with official work-program filters. Mixed road/bridge lines receive no single-work rate. Data-derived length groups and within-program slope-change screens are provided; no fixed 100-meter boundary is imposed.',
        'alternative':'Terrain, width, structures, approaches, rehabilitation scope and components outside the stated segment can explain large differences. Tiny printed ranges or parser errors can produce extreme ratios.',
        'next':'Verify station endpoints on original pages, then compare quantities, width, funded extent, designs and bill-of-quantity costs within the same work type. Investigate unusually short denominators before interpreting extreme ratios.',
        'caution':'These are appropriations per stated segment meter, not verified construction unit costs. Bridge chainage is not necessarily bridge span. No cross-category average, overpricing estimate or corruption probability is established.'})
    lane_summary=length_data.get('laneCost',{}).get('summary',[])
    lane_counts={k:sum(r[k] for r in lane_summary) for k in ['titleLaneRateRecords','inventoryProxyRateRecords','existingAssetLaneRateRecords']}
    findings[-1]['evidence']+=f' Lane evidence now supports {lane_counts["titleLaneRateRecords"]:,} title-stated lane rates, {lane_counts["inventoryProxyRateRecords"]:,} stated-length inventory lane estimates, and {lane_counts["existingAssetLaneRateRecords"]:,} existing-bridge asset lane estimates. These bases are shown separately and are not pooled into the per-meter flags.'
    findings[-1]['caution']+=' Inventory lanes are existing asset characteristics, not verified funded quantities; widening needs additional funded lanes. Overpasses, flyovers and viaducts use bridge peers.'
    context=length_data['laneCost']['assetContext']
    findings[-1]['evidence']+=f' Recorded-condition screening identifies {sum(r["rehabGoodFairCandidates"] for r in context["byCategory"].values())} rehabilitation lines on fully matched Good/Fair assessed road segments and {sum(r["recentSurfacingCandidates"] for r in context["byCategory"].values())} pavement-work lines within the disclosed five-budget-year surfacing window. These are review leads; later deterioration and different work scope may justify the allocations.'
    short_audit=json.loads((ROOT/'analysis_output/short_segment_audit.json').read_text())
    if short_audit.get('comparisonCsvSha256')!=hashlib.sha256(csvpath.read_bytes()).hexdigest():
        raise ValueError('Rerun audit_short_segments.py: native comparison changed')
    verified_short=[r for r in short_audit['sourceChecks'] if r['fullTitlePresentInVisiblePDFText'] and r['lengthMeters']<5 and r['id'] in {p['id'] for p in length_data['projects'] if p['category']=='Roads'}]
    if verified_short:
        findings.append({'rank':9,'id':'short-printed-ranges','title':'Very short printed road ranges need engineering clarification',
            'lead':f'{len(verified_short)} checked road ranges imply less than 5 meters',
            'basis':'Original PDF text agreement; funded engineering extent unresolved',
            'page':'cost-matching.html#short-segment-evidence',
            'question':'Do the printed station endpoints correctly describe the funded segment, or do notation and scope need correction?',
            'evidence':'Original-page visible text agrees with sampled road titles whose station differences calculate to '+', '.join(f'{r["lengthMeters"]:g} meters' for r in verified_short)+'. Across all 3,175 known road lengths, only 204 (6.43%) are below 100 meters; high-rate sorting concentrates short denominators at the top.',
            'alternative':'A source-document typo, station convention, short component within a larger project, or broader funded scope can explain these values. A very short printed range does not establish the physical length actually funded.',
            'next':'Request corrected or certified station endpoints, funded-segment plans, engineering quantities and allocation scope; verify notation before interpreting extreme allocation-per-meter rates.',
            'caution':'This is a printed-range/denominator issue, not evidence that most road projects are short or overpriced. Sampled title agreement rules out a title-transcription mismatch for those examples, not source errors or engineering ambiguity. Bridge lengths require separate interpretation.'})
    hgab_scope=dpwh_indepth_data['hgabCoverage']
    findings.extend([
        {'rank':10,'id':'hgab-no-nep-counterpart','title':'HGAB 3rd projects without a selected NEP counterpart',
         'lead':f'{hgab_scope["noSelectedNepRows"]:,} / {hgab_scope["projectRows"]:,} project rows · {hgab_scope["noSelectedNepPct"]:.1f}%',
         'basis':'One-to-one stage matching screen; unmatched rows require source review',
         'page':'dpwh.html#hgab-coverage',
         'question':'Which HGAB 3rd projects are genuinely absent from NEP after title, scope and occurrence review?',
         'evidence':'The current one-to-one comparison selected no NEP counterpart for these project rows. The comparison uses title and scope signals; unresolved and unmatched cases are not proof of new projects.',
         'alternative':'Renaming, title wrapping, scope changes, occurrence aggregation and parser errors can prevent counterpart selection.',
         'next':'Review NEP and HGAB source pages side by side, then reconcile project scope, office, location and amount.',
         'caution':'No selected counterpart means a review candidate, not a confirmed insertion.'},
        {'rank':11,'id':'hgab-no-listed-documents','title':'HGAB-only projects without a matched Senate supporting document',
         'lead':f'{dpwh_indepth_data.get("senateSupportingDocumentCoverage",{}).get("projectRowsWithoutMatchedDocument",0):,} / {dpwh_indepth_data.get("senateSupportingDocumentCoverage",{}).get("denominatorProjectRows",0):,} HGAB-only rows · {100-dpwh_indepth_data.get("senateSupportingDocumentCoverage",{}).get("projectsWithAtLeastOneMatchedDocumentPct",0):.2f}%',
         'basis':'Senate HGAB all-document scan; unique House-row title/code linkage',
         'page':'dpwh.html#senate-supporting-document-coverage',
         'question':'Which unmatched rows have files that need clearer title or file-code linkage?',
         'evidence':'The expanded scan checks BP 202, POW, Development Council documents, geotagged-photo files, Certificates of Implementability and other PDFs for HGAB-only House rows.',
         'alternative':'Image-only, damaged or ambiguously coded files can remain unmatched even when a document exists.',
         'next':'Review per-project file counts and source documents, then resolve ambiguous or unreadable file associations.',
         'caution':'A title/code match signals file presence, not verified contents; no match is not proof of absence.'},
        {'rank':12,'id':'hgab-missing-document-types','title':'Proposal attachment lists missing a POW, photos or development-council document',
         'lead':f'{hgab_scope["missingAnyTypeRows"]:,} / {hgab_scope["inspectedRows"]:,} inspected attachment lists · {hgab_scope["missingAnyTypePct"]:.1f}%',
         'basis':'DPWH Transparency Proposal attachment metadata; HGAB 3rd title matches',
         'page':'dpwh-transparency.html#proposal-attachment-type-gaps',
         'question':'Which attachment types are absent from inspected Proposal lists, and should DPWH add them?',
         'evidence':'Counts cover only HGAB projects with a directly matched Proposal record and locally inspected attachment metadata. They are Proposal-only statistics; Senate-provided HGAB files are counted separately.',
         'alternative':'The local snapshot may be incomplete, and an attachment may be indexed under another type or record.',
         'next':'Review each matched Proposal record and request missing categories from the implementing office.',
         'caution':'Uninspected projects are unknown, not counted as missing; the missing-type groups can overlap.'}
    ])
    # Put the largest disclosed allocation scopes first. These cohorts overlap,
    # so their exposures are comparison aids and must never be summed as a loss.
    hgab_only_docs=json.loads((ROOT/'analysis_output/senate-hgab-only-document-stats.json').read_text())
    hgab_rows=hgab_only_docs.get('projects',[])
    exposure_by_id={
        'rcs':(n*unit,'199 equal RCS office allocations'),
        'prices':(price_stats['overlap']*2*5_000_000,'Minimum: one exact ₱5M road and one flood entry in each overlapping office'),
        'repeats':(repeat_stats['uniqueCurrentPesos'],'Unique current NEP proposal allocations in the repeat screen'),
        'insertions':(sum(int(r['amountPesos']) for r in domestic),'OO2-adjusted domestic HGAB-only candidate allocations'),
        'inspire':(int(inspire['fy2027Pesos']),'FY2027 proposed allocation'),
        'mpb':(int(mpb['insertionPesos']),'MPB insertion-candidate allocations'),
        'length-coverage':(sum(int(r.get('unusableLengthAllocationPesos',0)) for r in length_data['summary']),'Allocations with absent or unusable extracted length'),
        'cost-per-km':(sum(int(r['amountPesos']) for r in length_data['projects'] if r.get('highRateCandidate')),'Allocation of high-rate screen candidates'),
        'short-printed-ranges':(sum(int(r['amountPesos']) for r in length_data['projects'] if r['id'] in {x['id'] for x in verified_short}),'Allocation for source-checked short-range candidates'),
        'hgab-no-nep-counterpart':(sum(int(r.get('amountPesos',0)) for r in hgab_rows),'All HGAB-only row allocations; 6,105-row cohort'),
        'hgab-no-listed-documents':(sum(int(r.get('amountPesos',0)) for r in hgab_rows if not r.get('hasAtLeastOneTitleMatchedDocument')),'Allocations for HGAB-only rows without a matched supporting file'),
    }
    for finding in findings:
        exposure=exposure_by_id.get(finding['id'])
        finding['costExposurePesos']=exposure[0] if exposure else None
        finding['costExposureBasis']=exposure[1] if exposure else 'No comparable allocation total in the current Proposal attachment-list extract'
    findings.sort(key=lambda r:(r['costExposurePesos'] is None,-(r['costExposurePesos'] or 0),r['id']))
    findings=findings[:8]
    if len(findings) != 8:
        raise RuntimeError(f'Summary must contain exactly eight investigation cards; found {len(findings)}')
    exposures=[r['costExposurePesos'] for r in findings]
    ranked_exposures=[v for v in exposures if v is not None]
    if ranked_exposures != sorted(ranked_exposures, reverse=True):
        raise RuntimeError('Summary cards are not sorted by descending allocation exposure')
    for rank,finding in enumerate(findings,1):finding['rank']=rank
    coverage_rows=[[k,v['summary']['thirdRows'],int(v['summary']['thirdTotal']),sum(count for status,count in v['summary']['statusCounts'].items() if status!='Same allocation')] for k,v in revision.items()]
    from summary_evidence_links import enrich_findings
    enrich_findings(findings)
    document={'title':'Investigative talking points','rankingMethod':'Editorial triage by evidence strength, allocation scale and verifiable next question; not corruption likelihood or a statistical risk score. Amounts overlap; do not add them.','findings':findings,'statistics':{'rcs':rcs_stats,'repeats':repeat_stats,'fiveMillion':price_stats,'strictCoverage':s},'sources':SOURCES,'scope':'FY2027 NEP/HGAB 3rd reading; historical GAA comparisons where locally available. No GAB/GAA 2027 outcome inferred.'}
    document['budgetStages']=['NEP','HGAB (House)','GAB (Senate)','Bicam (House/Senate reconciliation)','GAA (enacted)']
    document['statistics']['repeatRetention']=survival['summary']
    document['statistics']['mpb']=mpb
    document['statistics']['lengthCoverage']=length_data['summary']
    document['statistics']['highRateScreen']=length_data['highRateScreen']
    document['statistics']['laneCostCoverage']=lane_summary
    document['statistics']['assetConditionContext']=context
    document['statistics']['shortSegments']=short_audit['categories']
    document['statistics']['rcsStageTrace']=trace
    document['districtComparisonPolicy']={'scope':'All district rows are available for reader selection in the all-district ranking. No selected-district section or person-specific defaults.','data':'congress-benchmark.json'}
    document['allDistrictComparison']=benchmark['summary']
    findings[0]['evidence']+=f' All {trace["unchangedInHGAB"]} DEO lines are retained unchanged in HGAB; no differentiated needs weighting is visible in the amounts.'
    document['localDatasetInventory']=[{'file':'database/poverty.json','use':'Potential socio-economic context; no year/definition recorded in the inspected rows, so not used as a needs control.'},
                                       {'file':'static/data/flood_summary.json','coverage':'2016–2024 projects','use':'Historical project reference; not a current flood-exposure or FY2027 needs denominator.'}]
    for item in document['localDatasetInventory']:
        item['sha256']=hashlib.sha256((ROOT.parent/'open-data-visualization'/item['file']).read_bytes()).hexdigest()
    from standardize_nep_hgab_pages import agency_summary_coverage
    document['agencyComparisonCoverage']=agency_summary_coverage()
    (STATIC/'summary-data.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'analysis_output/investigation_summary.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    from uniform_report_menu import NAV as nav, apply_page as apply_report_menu
    cards=''.join(f'<article class="finding" id="lead-{r["id"]}" data-basis="{esc(r["basis"])}"><span class="rank">Allocation exposure order {r["rank"]} · {esc(r["basis"])}</span><h2>{esc(r["title"])}</h2><p class="lead">{esc(r["lead"])}</p><p class="cost-exposure">Allocation exposure in this review scope: {peso(r["costExposurePesos"]) if r.get("costExposurePesos") is not None else "Not available for comparison"} · {esc(r["costExposureBasis"])}</p><dl>'+''.join(f'<dt>{label}</dt><dd>{esc(r[key])}</dd>' for label,key in [('Talking point','question'),('Observed evidence','evidence'),('Plausible explanation','alternative'),('What investigators need next','next'),('Parsing/location caution','caution')])+f'</dl><p><a href="{esc(r["page"])}">Supporting analysis and source tables →</a></p></article>' for r in findings)
    ranked='<div class="summary-lead-grid" role="list" aria-label="Eight investigative leads ranked by allocation exposure">'+''.join(
        f'<a class="summary-priority-card" role="listitem" href="#lead-{esc(r["id"])}"><span class="summary-card-rank">Priority {r["rank"]} · {esc(r["basis"])}</span><h3>{esc(r["title"])}</h3><p class="summary-card-lead">{esc(r["lead"])}</p><p class="summary-card-exposure"><strong>Allocation exposure: {peso(r["costExposurePesos"]) if r.get("costExposurePesos") is not None else "Not available"}</strong><br>{esc(r["costExposureBasis"])}</p></a>'
        for r in findings)+'</div>'
    neutral=table(['Schedule','HGAB 3rd lines','HGAB 3rd pesos','Changed between 2nd and 3rd'],coverage_rows)
    neutral+='<p>These extracted FMR, NIA, HFEP and DepEd schedules have no allocation changes between the two readings. Stability is not itself a red flag. No year-on-year repetition or NEP insertion claim follows from unchanged bill-stage totals. NIA named projects and the irrigation appendix are separate schedule slices; do not add their totals without reconciling hierarchy.</p>'
    quality='<p>NEP → HGAB → GAB/GAA are different stages; prior-year GAA is enacted, current proposals are not. Match allocation records at the same hierarchy before comparing money.</p><ul><li>Printed-total reconciliation catches amount/hierarchy errors but cannot certify title identity or location.</li><li>Preserve source pages and occurrence counts. One comparison row may group multiple allocations; headers are not projects.</li><li>Require barangay → town/city → province context. DEO numbers do not identify legislative districts.</li><li>Keep directional names, tranches, province splits and construction chainage distinct. The confirmed multi-place Butuan/RTR line stays outside strict LEG totals.</li><li>Strict congressional rankings cover only '+f'{coverage:.1%}'+' of extracted allocation value. Names indicate geography, not authorship or sponsorship.</li></ul><p><a href="congress.html#congress-investigation-evidence">Inspect congressional coverage limits →</a></p>'
    quality=quality.replace('NEP → HGAB → GAB/GAA','NEP → HGAB (House) → GAB (Senate) → Bicam → GAA')
    flow='<p><strong>NEP → HGAB (House version) → GAB (Senate version) → Bicam (House/Senate reconciliation) → GAA (enacted).</strong></p><p>NEP and final GAA provide the published bookends. The investigative focus is how allocations change through House and Senate deliberations and bicameral reconciliation. A genuinely new HGAB line deserves scrutiny: who proposed it, what documented need supports it, and whether it remains in the Senate and reconciled versions. A lawful amendment can add projects; an unmatched parser row is not yet a demonstrated amendment.</p><p>These pages currently trace NEP and House readings. No survival claim is made for Senate GAB, Bicam or FY2027 GAA until those versions are available and reconciled. Retained NEP repeat candidates and new HGAB insertion candidates answer different questions.</p>'
    flow+='<p><a href="congress.html#congress-all-representatives">Compare estimated allocations across all congressional districts →</a></p>'
    datasets=table(['Investigative question','Dataset or documents needed','Current workspace limitation'],[['RCS needs','Geocoded RCS sites, storage/catchment design, population served, water access and dry-season demand','Rainfall is province-level; it cannot locate demand or actual sites'],['Repeated work','Contract IDs, bill of quantities, as-built chainage, completion and disbursements','Budget titles and stated chainage do not establish paid work'],['Price clustering','Work quantities, standard estimates, procurement thresholds, prior-year comparable contracts','Exact peso values alone are not unit prices'],['Insertions','Audited native NEP/HGAB occurrence links and original PDF pages','A balanced total does not certify every unmatched row'],['LEG rankings','Dated barangay/municipality LEG boundaries and funded-segment geometry','PH location DB contains undated and conflicting claims'],['INSPIRE','Approved total project cost, phase ledger, obligations and releases','Appropriations are not disbursements']])
    datasets+='<p>Workspace search found a province poverty file, but its rows do not identify year or indicator definition; it is not used as a needs control. The local flood project summary covers 2016–2024 projects, not present-day hazard exposure. Neither provides the missing RCS site/catchment, water-access or demand denominator. Additional datasets must be dated, sourced and matched to the correct geographic level before correlation.</p>'
    hero=f'<section class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">FY2027 budget · investigative triage</span><div class="repeat-hero-total"><strong>{len(findings)}</strong><span>leads worth a closer look</span></div><p>Cards are sorted by disclosed allocation exposure within each review scope. Scopes overlap and must not be added; exposures are not losses or a corruption score.</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><span>Uniform RCS packages</span><strong>199 offices</strong></div><div><span>Repeat candidates</span><strong>686 proposals</strong></div></div><p>Evidence guides an investigation. None of these findings establishes corruption.</p></div></section>'
    filters='<div class="summary-controls"><input id="lead-search" type="search" placeholder="Search talking points" aria-label="Search talking points"><select id="lead-basis" aria-label="Filter evidence class"><option value="">All evidence classes</option>'+''.join(f'<option>{esc(r["basis"])}</option>' for r in findings)+'</select></div>'
    filterjs="""<script>const search=document.getElementById('lead-search'),basis=document.getElementById('lead-basis');function filter(){document.querySelectorAll('.finding').forEach(card=>card.hidden=!(card.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!basis.value||card.dataset.basis===basis.value)))}search.addEventListener('input',filter);basis.addEventListener('change',filter);</script>"""
    hero=hero.replace('686 proposals',f'{len(unique):,} proposals')
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Budget Summary · Investigative Talking Points</title><style>*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,sans-serif;background:#f3f6f5;color:#18303b}header{background:#123944;color:white;padding:30px clamp(16px,2vw,32px)}header h1{font-size:clamp(28px,4vw,48px);margin:0}main{width:100%;padding:24px clamp(16px,2vw,32px)}a{color:#087e78}header a{color:white}header p{max-width:1100px}</style>'+STYLE+CSS+SUMMARY_CARD_CSS+'</head><body><header><h1>Budget Summary · Investigative Talking Points</h1><p>NEP patterns and NEP → HGAB screens, with parsing uncertainty and location limits alongside every claim. Priorities are editorial triage, not a corruption score. Figures overlap and must not be added together.</p>'+nav+'</header><main>'+hero+section('summary-stages','Follow the changes between budget stages',flow)+section('ranked-leads','Where to start',ranked)+filters+cards+section('summary-quality','Parsing and location gotchas',quality)+section('summary-neutral','Other schedules · no reading-stage change found',neutral)+section('summary-data-needs','Evidence needed to strengthen the claims',datasets)+'</main>'+JS+filterjs+'</body></html>'
    # Normalize only the newly generated summary page. Other report builders
    # retain their own content while using the shared menu transformer when they
    # write their pages; never copy one page's navigation onto every page.
    restored_summary=ROOT/'project_documents/summary_priority_leads.html'
    if restored_summary.is_file():
        page=restored_summary.read_text(encoding='utf-8')
    else:
        page=apply_report_menu(page,'summary.html')
    (STATIC/'summary.html').write_text(page)
    (ROOT/'analysis_output/summary.html').write_text(page)
    (ROOT/'analysis_output/summary.html').write_text((STATIC/'summary.html').read_text())
    # This formerly ran only inside the site-wide finalizer. Keep the summary
    # comparison current without touching any other report page.
    # summary_priority_leads.html is the recovered, version-controlled page
    # from open-data-visualization commit 72f9346cc. Keep the historical hero,
    # exposure-ranked cards and page structure authoritative after builders run.
    final_summary=(restored_summary.read_text(encoding='utf-8') if restored_summary.is_file()
                   else (STATIC/'summary.html').read_text())
    # The checked-in historical summary is restored after the first render; it
    # must receive the shared menu again so its chrome stays aligned with every
    # other page. Keep this write inside the Summary builder.
    final_summary=apply_report_menu(final_summary,'summary.html')
    if restored_summary.is_file():
        final_summary,document_gap_stats=refresh_undocumented_hgab_card(final_summary)
        final_summary,connectivity_card_stats=refresh_connectivity_card(final_summary)
        final_summary=remove_line_item_queue(final_summary)
        (STATIC/'summary.html').write_text(final_summary,encoding='utf-8')
    else:
        document_gap_stats=None
        connectivity_card_stats=None
    final_data=json.loads((STATIC/'summary-data.json').read_text())
    card_count=len(re.findall(r'<article class="priority-card"',final_summary)) if restored_summary.is_file() else len(re.findall(r'<article class="finding"',final_summary))
    if card_count != 8 or len(final_data.get('findings',[])) != 8:
        raise RuntimeError(
            'Summary output drifted during finalization: '
            f'{card_count} restored HTML cards, {len(final_data.get("findings",[]))} JSON findings; expected eight of each'
        )
    from report_table_presentation import apply_page_table_module
    final_summary,_=apply_page_table_module('summary.html',final_summary)
    (STATIC/'summary.html').write_text(final_summary,encoding='utf-8')
    (ROOT/'analysis_output/summary.html').write_text(final_summary)
    print(json.dumps({'findings':len(findings),'rcs':rcs_stats,'repeats':repeat_stats,'fiveMillion':price_stats,'domesticInsertionCandidates':len(domestic),'allHgabDocumentGap':document_gap_stats,'fmrConnectivity':connectivity_card_stats},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
