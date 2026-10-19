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
from build_report_heroes import STYLE
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
    csvbuffer=io.StringIO();writer=csv.writer(csvbuffer);writer.writerow(headers);writer.writerows(rows)
    # Each export is self-contained and works on file:// previews.
    encoded=esc(csvbuffer.getvalue())
    from format_report_currency import format_cell
    return f'<button class="export-btn" type="button" data-csv="{encoded}">Export CSV</button><div class="evidence-table"><table><thead><tr>'+''.join(f'<th>{esc(v)}</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{esc(format_cell(headers[i],v))}</td>' for i,v in enumerate(row))+'</tr>' for row in rows)+'</tbody></table></div>'

CSS='''<style id="investigation-evidence-style">.investigation-evidence{margin:24px 0;padding:24px;border:1px solid #c6dbd6;border-radius:14px;background:#fff;color:#18303b}.investigation-evidence h2{margin:0 0 12px}.investigation-evidence p{max-width:1100px}.evidence-table{width:100%;overflow-wrap:anywhere}.evidence-table table{width:100%;border-collapse:collapse;table-layout:fixed}.evidence-table th,.evidence-table td{position:static!important;text-align:left!important;white-space:normal!important;padding:12px;border-bottom:1px solid #d9e3e1;vertical-align:top}.evidence-table th{background:#eef5f3}.evidence-graphic{display:block;width:100%;height:auto;max-height:360px;margin:16px 0}.export-btn{background:#b65b09!important;color:#fff!important;border:1px solid #914600!important;border-radius:8px;padding:9px 14px;margin:10px 0;font-weight:700;cursor:pointer}.queue-controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.queue-controls button:not(.export-btn){padding:8px 12px}.queue-flag-button{border:0;background:transparent;font-size:1.05rem;letter-spacing:.03em;cursor:pointer}.queue-flag-button:focus-visible,.queue-controls button:focus-visible{outline:3px solid #087e78;outline-offset:2px}.flag-evidence-dialog{width:min(720px,calc(100% - 32px));max-height:80vh;overflow:auto;border:1px solid #9bb7af;border-radius:14px;padding:22px;color:#18303b}.flag-evidence-dialog::backdrop{background:#102f3e99}.flag-evidence-dialog form{display:flex;justify-content:flex-end}.flag-evidence-dialog li{margin:12px 0}.flag-evidence-dialog li p{margin:4px 0}.investigation-evidence .caution{padding:14px;background:#fff4dd;border-left:4px solid #ba7800}.finding{padding:24px;border-radius:14px;border:1px solid #d9e3e1;background:#fff;margin:18px 0}.finding h2{margin:0 0 8px}.finding .rank{color:#087e78;font-weight:800}.finding .lead{font-size:1.4rem;font-weight:750}.finding dt{font-weight:750;margin-top:12px}.finding dd{margin:4px 0}.finding a{color:#087e78;font-weight:700}.finding[hidden],tr[hidden]{display:none}.summary-controls{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}.summary-controls input,.summary-controls select{padding:10px;border:1px solid #b6c9c4;border-radius:8px;font:inherit}.summary-controls input{flex:1;min-width:200px}@media(max-width:650px){.evidence-table th,.evidence-table td{padding:7px;font-size:12px}.finding,.investigation-evidence{padding:16px}}</style>'''
JS='''<script id="investigation-evidence-script">document.addEventListener('click',e=>{const b=e.target.closest('[data-csv]');if(!b)return;const url=URL.createObjectURL(new Blob(['\ufeff'+b.dataset.csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=(document.title.toLowerCase().replace(/[^a-z0-9]+/g,'-')+'-evidence.csv');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)});</script>'''

def section(identifier,title,body):
    return f'<section id="{identifier}" class="investigation-evidence"><h2>{esc(title)}</h2>{body}</section>'

def inject(page,identifier,body):
    p=STATIC/page;t=p.read_text()
    pattern=rf'<section id="{re.escape(identifier)}".*?</section>'
    if re.search(pattern,t,re.S):t=re.sub(pattern,lambda m:body,t,flags=re.S)
    else:t=t.replace('</main>',body+'</main>',1)
    if 'id="investigation-evidence-style"' not in t:t=t.replace('</head>',CSS+'</head>',1)
    if 'id="investigation-evidence-script"' not in t:t=t.replace('</body>',JS+'</body>',1)
    p.write_text(t)

def integer_units(weights,total,ids):
    shares=[total*w/sum(weights) for w in weights];rounded=[math.floor(v) for v in shares]
    order=sorted(range(len(weights)),key=lambda i:(-(shares[i]-rounded[i]),ids[i]))
    for i in order[:total-sum(rounded)]:rounded[i]+=1
    if sum(rounded)!=total:raise ValueError('RCS scenario does not conserve units')
    return shares,rounded

def cumulative_graph(models):
    colors=['#355b92','#087e78','#b65b09'];n=len(models[0][1]);maximum=sum(models[0][1])
    lines=[]
    for (label,values),color in zip(models,colors):
        cumulative=[0];
        for value in values:cumulative.append(cumulative[-1]+value)
        points=' '.join(f'{60+830*i/n:.2f},{245-190*v/maximum:.2f}' for i,v in enumerate(cumulative))
        lines.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{points}"/><text x="65" y="{285+len(lines)*22}" fill="{color}" font-size="14">{esc(label)}</text>')
    return '<svg class="evidence-graphic" viewBox="0 0 950 355" role="img" aria-label="Cumulative RCS budget units across offices ordered from lower to higher rainfall"><path d="M60 45 V245 H890" fill="none" stroke="#536873"/><text x="10" y="55">199</text><text x="25" y="245">0</text><text x="60" y="265">1st office</text><text x="760" y="265">199th office</text><text x="60" y="25">Cumulative budget units · offices ordered by rainfall proxy</text>'+''.join(lines)+'</svg>'

def main():
    if (ROOT/'data_sources/csiiiv/source_policy.json').exists():
        from adopt_csiiiv_reference import adopt
        adopt()
        from build_corrected_fmr_page import generate as refresh_reviewed_fmr
        refresh_reviewed_fmr()
    from build_cost_per_km import build as build_cost_per_km
    length_data=build_cost_per_km()
    dpwh_indepth_data=json.loads((ROOT/'analysis_output/dpwh-in-depth-data.json').read_text())
    from build_line_item_review_queue import build as build_review_queue, render as render_review_queue
    review_queue=build_review_queue(dpwh_indepth_data)
    from build_mpb_report import build as build_mpb
    mpb=build_mpb()['summary']
    dpwh=read('dpwh-data.json');rcs=read('rcs-data.json');congress=read('congress-data.json')
    innovations=read('budget-innovations-data.json');reading=read('dpwh-hgab-comparison.json');revision=read('hgab-revision-data.json')
    survival=build_survival()
    rcs_trace=build_rcs_trace()
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
    rows=[['Equal allocation (observed)',0,0,n],
          ['Province mean, then split among DEOs (existing scenario)',int(shifts(province)),sum(v==0 for v in province),sum(v==1 for v in province)],
          ['Each DEO weighted by province mean (alternative)',int(shifts(whole)),sum(v==0 for v in whole),sum(v==1 for v in whole)],
          ['Each DEO weighted by province median (sensitivity)',int(shifts(median_whole)),sum(v==0 for v in median_whole),sum(v==1 for v in median_whole)]]
    order=sorted(range(n),key=lambda i:(mean[i],ids[i]))
    graph=cumulative_graph([('Observed equal units',[current[i] for i in order]),('Province-first scenario',[province[i] for i in order]),('Per-office rainfall scenario',[whole[i] for i in order])])
    body=f'<p>All {n} district-office lines receive one ₱4.2M budget unit, while their rainfall proxies span {min(mean):,.0f}–{max(mean):,.0f} mm/year ({max(mean)/min(mean):.2f}×). Allocation coefficient of variation is 0%; rainfall-proxy variation is {rcs_stats["rainfallProxyCV"]:.1%}. This establishes uniformity despite variable rainfall; it does not establish that planners ignored every factor.</p>'+graph+table(['Formula','Budget units moved from current allocation','Offices assigned zero units','Offices retaining one unit'],rows)
    body+='<p>Units moved = half the sum of absolute changes; all scenarios conserve 199 budget units. Largest-remainder rounding uses office name to break ties. A budget unit is not a verified count of installed collectors. Province means are shared proxies, not 199 independent rainfall observations.</p><p class="caution">Hypothesis for investigators: the flat amount is a standard package rather than a needs-based allocation. Alternatives include a minimum-coverage policy or common construction specification. Pearson correlation is undefined because every allocation is identical; a p-value against an invented random-allocation process would be misleading. Neither rainfall formula is a recommended final budget, and a model assigning zero units is not evidence an office needs none.</p>'
    body+=f'<p>Mean versus median weighting changes whole-unit recommendations for {rcs_stats["meanMedianDifferentOfficeUnits"]} offices. {rcs_stats["regionalFallbackOffices"]} office uses a regional rainfall fallback. Establish the actual site/catchment area, design capacity, water demand, storage, access and existing assets before making a needs claim.</p>'
    body+='<p class="caution">The direct per-office rainfall formula rounds to one whole budget unit for every office, even though fractional shares differ. Equal whole units therefore do not, by themselves, refute rainfall weighting at this budget-unit resolution. The existing province-first scenario moves 44 units because provinces receive a share before it is divided among offices. That structural choice must be justified before claiming it is a better allocation.</p>'
    inject('rcs.html','rcs-statistical-evidence',section('rcs-statistical-evidence','Uniform allocations · formula sensitivity',body))
    trace=rcs_trace['summary']
    body='<p><strong>The observed budget pattern is identical distribution: 199 DEO lines at ₱4.2M each. No differentiated needs weighting is visible in those line amounts.</strong> Whether planners considered need outside the schedule requires policy/design records; equal figures alone cannot establish what they thought.</p>'
    body+='<svg class="evidence-graphic" viewBox="0 0 900 110" role="img" aria-label="199 NEP RCS office lines remain unchanged in HGAB"><rect x="10" y="15" width="330" height="70" rx="10" fill="#355b92"/><text x="30" y="58" fill="white" font-size="22">NEP: 199 × ₱4.2M</text><path d="M355 50 H510" stroke="#18303b" stroke-width="4"/><path d="M495 40 L515 50 L495 60" fill="none" stroke="#18303b" stroke-width="4"/><rect x="530" y="15" width="350" height="70" rx="10" fill="#087e78"/><text x="550" y="58" fill="white" font-size="22">HGAB: 199 × ₱4.2M</text></svg>'
    body+=table(['Stage check','DEO RCS lines'],[['Retained unchanged in HGAB',trace['unchangedInHGAB']],['No selected HGAB counterpart',trace['withoutSelectedCounterpart']],['Allocation decreases in HGAB',trace['allocationDecreases']]])
    body+='<p><a class="export-btn" href="rcs-stage-trace.csv" download>Export all 199 RCS stage/scenario lines CSV</a> · <a href="rcs-stage-trace.json">Source and LEG reference evidence JSON</a></p><p class="caution">No DEO RCS line was lost in the current HGAB trace. A named LEG cannot be declared a recipient or loser without the installation locations, applicable boundaries and evidence of the funded service area.</p>'
    inject('rcs.html','rcs-stage-evidence',section('rcs-stage-evidence','Even distribution · did any RCS allocation disappear in HGAB?',body))
    path=STATIC/'rcs.html';page=path.read_text()
    page=page.replace('<h1>What would RCS allocation look like if rainfall were the only input?</h1>','<h1>199 offices. One identical RCS allocation.</h1>')
    page=re.sub(r'(<h1>199 offices\. One identical RCS allocation\.</h1>)<p>.*?</p>',lambda m:m[1]+'<p>Each DEO receives ₱4.2M in NEP, and all 199 allocations remain unchanged in HGAB 3rd reading. No differentiated needs weighting is visible in those amounts. The stage trace appears first; rainfall data and alternative allocation formulas follow.</p>',page,count=1,flags=re.S)
    block=re.search(r'<section id="rcs-stage-evidence".*?</section>',page,re.S)
    if block:
        text=block.group(0);page=page[:block.start()]+page[block.end():]
        hero_end=re.search(r'<section[^>]*id="report-hero".*?</section>',page,re.S)
        if hero_end:page=page[:hero_end.end()]+text+page[hero_end.end():]
        else:page=re.sub(r'(<main\b[^>]*>)',lambda m:m[0]+text,page,count=1)
    path.write_text(page)

    repeat=dpwh['priorityRepeats'];unique={}
    for row in repeat:
        key=row['source_code']
        if key in unique and unique[key]['amount_2027']!=row['amount_2027']:raise ValueError('Conflicting current repeat amount')
        unique[key]=row
    strata=Counter(r['chainage_status'] for r in repeat)
    repeat_stats={'comparisonPairs':len(repeat),'uniqueCurrentProposals':len(unique),'uniqueCurrentPesos':sum(r['amount_2027'] for r in unique.values()),'chainageStatuses':dict(strata),'overlapUniqueProposals':len({r['source_code'] for r in repeat if r['chainage_status']=='overlap'}),'trancheStatuses':dict(Counter(r['tranche_status'] for r in repeat))}
    bar='';position=0;colors=['#087e78','#355b92','#b65b09','#777']
    for (status,count),color in zip(strata.items(),colors):
        width=900*count/len(repeat);bar+=f'<rect x="{position:.2f}" y="10" width="{width:.2f}" height="35" fill="{color}"><title>{esc(status)}: {count} comparison pairs</title></rect>';position+=width
    graph='<svg class="evidence-graphic" viewBox="0 0 900 55" role="img" aria-label="Repeat comparison pairs grouped by chainage evidence">'+bar+'</svg>'
    body=f'<p>{len(repeat):,} comparison pairs represent {len(unique):,} distinct FY2027 proposals carrying {peso(repeat_stats["uniqueCurrentPesos"])}. The current allocation is counted once per proposal; it is not a loss estimate and is not summed across prior years.</p>'+graph+table(['Chainage evidence','Comparison pairs'],sorted(strata.items(),key=lambda r:-r[1]))
    body+=f'<p>{repeat_stats["overlapUniqueProposals"]} distinct proposals have at least one explicitly overlapping stated segment. Overlap is a strong reason to inspect work descriptions, but widening, rehabilitation, bridge approaches or different components can legitimately use the same chainage. {repeat_stats["trancheStatuses"].get("one side stated",0)} pairs state a tranche on only one side.</p><p class="caution">Name similarity is a screening result. Missing chainage does not imply overlapping work. Different barangays, municipalities, provinces, directions and packages must remain distinct. Retrieve contracts, quantities, completion reports and maps before alleging duplicate funding.</p>'
    test=dpwh['fiveMillionStats']['results'][0];N=test['district_offices'];a=test['overlap_offices'];road=test['road_offices'];flood=test['flood_offices'];b=road-a;c=flood-a;d=N-a-b-c
    p=sum(math.comb(road,k)*math.comb(N-road,flood-k)/math.comb(N,flood) for k in range(a,min(road,flood)+1) if 0<=flood-k<=N-road)
    odds=a*d/(b*c);se=math.sqrt(sum(1/v for v in [a,b,c,d]));ci=[math.exp(math.log(odds)-1.96*se),math.exp(math.log(odds)+1.96*se)]
    price_stats={'N':N,'roadOffices':road,'floodOffices':flood,'overlap':a,'expectedOverlap':road*flood/N,'hypergeometricP':p,'oddsRatio':odds,'wald95CI':ci,'regionalPermutationP':test['region_controlled_simulated_p_value'],'regionalPermutationRepetitions':test['simulation_repetitions'],'postSelectionAdjusted':False}
    body+='<h3>Exact ₱5M road/flood co-occurrence · exploratory office test</h3>'+table(['Statistic','Result'],[['Offices with both exact ₱5M road and flood entries',a],['Expected overlap under independent office assignment',f'{road*flood/N:.2f}'],['One-sided hypergeometric p-value (recomputed)',f'{p:.6g}'],['Odds ratio; approximate 95% interval',f'{odds:.2f}; {ci[0]:.2f}–{ci[1]:.2f}'],['Region-controlled permutation p-value (existing analysis)',f'{test["region_controlled_simulated_p_value"]:.6g}']])
    body+='<p>Null model: fix how many of the 199 offices have each type of ₱5M entry, then assign flood-office membership independently of road-office membership. The exact test rejects this simple independence model. The existing region-controlled test preserves regional membership counts.</p><p class="caution">The ₱5M threshold and project categories were selected after observing patterns. P-values and the Wald interval are exploratory, unadjusted for that selection or multiple comparisons. Office workload, project mix and common standard designs can explain co-occurrence. Next test: a pre-specified model controlling project count, work type, region and prior-year price distributions; request engineering quantities to assess price plausibility.</p>'
    inject('dpwh.html','dpwh-investigation-evidence',section('dpwh-investigation-evidence','Repeat denominators and allocation clustering',body))
    from analyze_within_stage_repeats import build as build_within_stage, render as render_within_stage
    inject('dpwh.html','within-stage-repeats',section('within-stage-repeats','Similar line items within NEP and within HGAB 3rd reading',render_within_stage(build_within_stage())))
    rows=[[r['status'],r['comparisonPairs'],r['uniqueNEPProposals'],r['nepPesos'],r['selectedHgabPesos'] if r['selectedHgabPesos'] is not None else 'No selected allocation'] for r in survival['groups']]
    rectangles=[];legend=[]
    for i,(group,color) in enumerate(zip(survival['groups'],['#087e78','#b65b09','#777','#355b92'])):
        legend.append(f'<text x="380" y="{80+i*35}" fill="{color}" font-size="14">{esc(group["status"])}</text>')
    for j,key in enumerate(['comparisonPairs','uniqueNEPProposals']):
        y=280
        for group,color in zip(survival['groups'],['#087e78','#b65b09','#777','#355b92']):
            height=230*group[key]/len(repeat);y-=height
            rectangles.append(f'<rect x="{90+j*150}" y="{y:.2f}" width="85" height="{height:.2f}" fill="{color}"><title>{esc(group["status"])}: {group[key]}</title></rect>')
    retention_graph='<svg class="evidence-graphic" viewBox="0 0 850 340" role="img" aria-label="Stacked vertical bars show HGAB retention classes for 737 comparison pairs and 686 distinct proposals"><path d="M60 40 V280 H350" fill="none" stroke="#536873"/><text x="15" y="55">737</text><text x="90" y="305">Comparison pairs</text><text x="240" y="325">Distinct proposals</text>'+''.join(rectangles+legend)+'</svg>'
    body=f'<p>The 737 headline is a NEP-level comparison with old enacted GAA. Tracing the same proposal codes into HGAB 3rd reading gives <strong>{clear_pairs} clearly retained comparison pairs, representing {clear_proposals} distinct proposals</strong>. Potential links remain separate.</p>'+retention_graph+table(['HGAB retention class','Original GAA comparison pairs','Distinct NEP proposals','Original NEP allocation pesos','Selected HGAB allocation pesos'],rows)
    body+='<p>A proposal matched to two historical years counts twice in the pair column but once in the proposal column. Clear retention means a selected, scope-compatible normalized-title link in our current parser, not a certified work-scope audit. A potential retained link is a provisional selected counterpart. Missing links do not establish that HGAB removed the project.</p><p><a class="export-btn" href="repeat-nep-hgab-proposals.csv" download>Export all 686 proposal traces CSV</a> · <a href="repeat-nep-hgab-survival.json">Full pair and proposal evidence JSON</a></p><p class="caution">For retained proposals, investigate whether old appropriations and HGAB fund the same component. For unmatched proposals, check renaming, segmentation, parser fragments and original pages before claiming removal. Amount changes on retained lines are allocation adjustments, not automatically insertion or removal.</p>'
    inject('dpwh.html','repeat-hgab-survival',section('repeat-hgab-survival','Of the NEP repeat candidates, how many survived into HGAB?',body))

    csvpath=ROOT/'analysis_output/hb_nep_comparison_3rd.csv';SOURCES.append({'file':csvpath.name,'sha256':hashlib.sha256(csvpath.read_bytes()).hexdigest()})
    with csvpath.open() as f:comparison=list(csv.DictReader(f))
    domestic=[r for r in comparison if r['comparison']==UNMATCHED and not is_fap(r)]
    fap=[r for r in comparison if r['comparison']==UNMATCHED and is_fap(r)]
    status_counts=Counter(r['comparison'] for r in comparison)
    body='<p>These four statuses partition native HGAB rows; they are not four certified outcomes. Schedule totals can reconcile while individual titles, offices or occurrence links remain wrong.</p>'+table(['NEP counterpart screen','Native HGAB allocation records'],status_counts.items())
    body+=f'<p>{len(domestic):,} domestic candidate lines carry {peso(sum(int(r["amountPesos"]) for r in domestic))}. The {len(fap)} unpaired FAP lines carrying {peso(sum(int(r["amountPesos"]) for r in fap))} remain a separate review. Neither bucket is proof of insertion; new wording, combined occurrences or parser fragments can hide existing NEP projects.</p><p class="caution">Investigators should manually audit a stratified sample by program, office class and amount band, oversampling high-value candidates, and review original NEP/HGAB pages. Report adjudicated false-positive rates with uncertainty before extrapolating. The supplied analyst export has 5,797 comparison rows, not 5,837 certified added projects; grouped rows and non-project headers use different count units.</p>'
    inject('dpwh-hgab.html','hgab-investigation-evidence',section('hgab-investigation-evidence','Insertion candidates · what the matching can establish',body))

    s=congress['summary'];coverage=s['strictAssignedPesos']/s['sourceTotalPesos']
    body=f'<p>Strict attribution covers {s["uniquelyAssignedLines"]:,}/{s["sourceLineItems"]:,} source lines ({s["uniquelyAssignedLines"]/s["sourceLineItems"]:.1%}) and {coverage:.1%} of extracted allocation value. The remaining money is excluded from strict LEG rankings, not missing from the budget.</p>'+table(['Attribution outcome','HGAB lines','Allocation pesos'],[['Strict single LEG',s['uniquelyAssignedLines'],s['strictAssignedPesos']],['Shared or unresolved',s['strictExcludedLines'],s['strictExcludedAmountPesos']]])
    body+='<p class="caution">District totals are evidence-supported lower coverage totals, not complete receipts or amounts sponsored by representatives. Offices are not legislative seats. Homonymous places require parent and geographic level; multi-place routes cannot be allocated to one LEG without segment evidence. The ₱1.2B Butuan/RTR project is a confirmed multi-place exclusion, not a Butuan-only allocation.</p><p>Before comparing districts, measure each district’s unresolved coverage using project locations and dated boundaries. Province splits, current versus historical names, shared DEOs and school names can all change eligibility for attribution. No concentration test is reliable while missing attribution differs by district.</p>'
    inject('congress.html','congress-investigation-evidence',section('congress-investigation-evidence','Ranking coverage and location exclusions',body))
    additions_path=ROOT/'analysis_output/congress_leg_insertions.json'
    additions=json.loads(additions_path.read_text())
    audit_path=ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json'
    audit=json.loads(audit_path.read_text())['projects']
    comparison_by_id={r['hgab_id']:r for r in comparison}
    # Remove the retired selected-district section when updating existing HTML.
    path=STATIC/'congress.html'
    page=re.sub(r'<section\b[^>]*id="selected-district-scrutiny"[^>]*>.*?</section>', '', path.read_text(), flags=re.S)
    path.write_text(page)
    benchmark=build_benchmark()
    benchmark_body,benchmark_script=render_benchmark(benchmark)
    inject('congress.html','congress-all-representatives',section('congress-all-representatives','All districts · estimated allocations, roles and reference comparisons',benchmark_body))
    from build_house_party_list_roster import build as build_party_list, render as render_party_list
    inject('congress.html','congress-party-list-roster',section('congress-party-list-roster','Party-list representatives · organizations and verified roles',render_party_list(build_party_list())))
    path=STATIC/'congress.html';page=path.read_text()
    page=re.sub(r'<script id="congress-benchmark-script">.*?</script>','',page,flags=re.S)
    page=page.replace('</body>',benchmark_script+'</body>',1);path.write_text(page)

    inspire=next(r for r in innovations['candidates'] if r['id']=='inspire')
    historical=[r for r in inspire['historical'] if r['n']]
    body='<p>INSPIRE is a returning named project, not a keyword appearing for the first time. Separate history of wording from history of funded scope.</p>'+table(['Stage/year','Observed allocation pesos'],[[f'GAA {r["year"]}',int(r['pesos'])] for r in historical]+[['NEP 2027',inspire['fy2027Pesos']]])
    body+='<p class="caution">Past enacted allocations plus a new proposal do not establish duplicate spending, actual release or disbursement. Ask for approved total project cost, component scope, procurement phases, progress, obligations and remaining balance. A newly seen phrase can also name a long-negotiated foreign-assisted project; keyword novelty is not an insertion finding.</p>'
    inject('budget-innovations.html','innovation-investigation-evidence',section('innovation-investigation-evidence','Returning labels · INSPIRE funding history',body))

    findings=[
        {'rank':1,'id':'rcs','title':'RCS: identical budget packages across unequal rainfall proxies','lead':f'199 offices × ₱4.2M = {peso(n*unit)}','basis':'Direct allocation observation; rainfall need remains a proxy','page':'rcs.html#rcs-statistical-evidence','question':'What policy or engineering design justifies one identical budget unit per office?','evidence':f'All district-office RCS lines have the same amount. Province/regional rainfall proxies differ by {max(mean)/min(mean):.2f}×. Alternative formulas move different numbers of budget units.','alternative':'Standard package costs or a minimum coverage policy may justify equal allocations. Rainfall alone does not measure demand.','next':'Obtain siting, design capacity, water demand, catchment area and existing RCS inventory.','caution':'DEO is not LEG; province rainfall is not a district observation. Returning FY2026 program.'},
        {'rank':2,'id':'prices','title':'Exact ₱5M road and flood allocations cluster in the same offices','lead':f'{a} overlapping offices vs {road*flood/N:.1f} expected under independence','basis':'Exploratory statistical association','page':'repeats.html#dpwh-investigation-evidence','question':'Does standard design, office workload or coordinated allocation explain the co-occurrence?','evidence':f'Office odds ratio {odds:.2f}; unadjusted exact p={p:.3g}. Region-controlled result is also unusual under its stated null.','alternative':'Common specifications, office workload and project mix can create clustering.','next':'Pre-specify work-type and workload controls; inspect quantities and comparable prior-year prices.','caution':'Threshold/category selection was post hoc. Association does not establish procurement splitting or intent.'},
        {'rank':3,'id':'repeats','title':'Recurring project titles: inspect overlapping work before alleging duplication','lead':f'{clear_pairs} of {len(repeat)} NEP comparison pairs clearly retained in HGAB','basis':'Scope-screened comparison candidates','page':'repeats.html#repeat-hgab-survival','question':'Are new appropriations paying for already-funded components or legitimate continuation?','evidence':f'{clear_proposals} of {len(unique)} distinct NEP repeat-screen proposals have clear HGAB links. {repeat_stats["overlapUniqueProposals"]} proposals have explicit overlapping historical chainage. {peso(repeat_stats["uniqueCurrentPesos"])} is the unique NEP proposal allocation, not alleged loss.','alternative':'Multi-year implementation, rehabilitation and distinct components can share names and segments.','next':'Prioritize explicitly overlapping retained proposals and high amounts; compare contracts, quantities, tranche scopes and completion.','caution':'The 737 headline counts NEP–old GAA comparison pairs. Potential retention and missing counterparts remain separate.'},
        {'rank':2,'id':'insertions','title':'Two NEP matching screens give different candidate counts','lead':f'{len(domestic):,} supplied-comparison rows vs {dpwh_indepth_data["hgabCoverage"]["noSelectedNepRows"]:,} / {dpwh_indepth_data["hgabCoverage"]["projectRows"]:,} native project rows','basis':'Source and matcher reconciliation; not a confirmed insertion count','page':'dpwh-hgab.html#hgab-investigation-evidence','question':'Which source rows explain the difference between the supplied comparison and the native one-to-one screen?','evidence':f'The supplied comparison marks {len(domestic):,} domestic rows without a plausible NEP title counterpart, carrying {peso(sum(int(r["amountPesos"]) for r in domestic))}. The native one-to-one screen selects no NEP counterpart for {dpwh_indepth_data["hgabCoverage"]["noSelectedNepRows"]:,} of {dpwh_indepth_data["hgabCoverage"]["projectRows"]:,} HGAB project rows. The {abs(len(domestic)-dpwh_indepth_data["hgabCoverage"]["noSelectedNepRows"]):,}-row difference is not a count of missing projects: the screens use different matching rules and row populations.','alternative':'Different project filters, grouped occurrences, parser boundaries, source versions and matching rules can change candidate counts.','next':'Reconcile project IDs and source pages, align project-level denominators, then adjudicate a sample against the original NEP and HGAB pages.','caution':'Neither count is a certified insertion total, and the counts are not independent confirmations of the same set of projects.'},
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
        {'rank':11,'id':'hgab-no-listed-documents','title':'HGAB 3rd projects with no listed DPWH Transparency documents',
         'lead':f'{hgab_scope["missingListedDocumentsRows"]:,} / {hgab_scope["projectRows"]:,} project rows · {100*hgab_scope["missingListedDocumentsRows"]/hgab_scope["projectRows"]:.1f}%',
         'basis':'DPWH Transparency FY2027 snapshot; local title reconciliation',
         'page':'dpwh.html#hgab-coverage',
         'question':'Are project documents available through another route, or should document links be added to the Transparency record?',
         'evidence':'Rows without a matched transparency entry listing one or more documents are counted, including titles that do not match the snapshot.',
         'alternative':'Documents may be available on another official page or not yet indexed in the captured snapshot.',
         'next':'Verify the project identifier and query the responsible DPWH office for POW, geotagged photos and RDC records.',
         'caution':'No listed document is a disclosure gap in this snapshot; it does not establish that no document exists.'},
        {'rank':12,'id':'hgab-missing-document-types','title':'Incomplete documentation: missing POW, geotagged photos or RDC',
         'lead':f'{hgab_scope["missingAnyTypeRows"]:,} / {hgab_scope["inspectedRows"]:,} inspected attachment lists · {hgab_scope["missingAnyTypePct"]:.1f}%',
         'basis':'Locally inspected attachment metadata; HGAB 3rd title matches',
         'page':'dpwh.html#hgab-coverage',
         'question':'Which listed attachment types are absent, and can DPWH provide the missing POW, photos or RDC?',
         'evidence':'Counts cover only title-matched HGAB projects whose attachment metadata is locally inspected. The supporting section breaks missing POW, photos and RDC out separately.',
         'alternative':'The local snapshot may be incomplete, and an attachment may be indexed under another type or record.',
         'next':'Review each project’s transparency entry and request missing categories from the implementing office.',
         'caution':'Uninspected projects are unknown, not counted as missing; the missing-type groups can overlap.'}
    ])
    priority={'rcs':1,'insertions':2,'mpb':3,'repeats':4,'prices':5,'inspire':6,'length-coverage':7,'cost-per-km':8,'short-printed-ranges':9,'hgab-no-nep-counterpart':10,'hgab-no-listed-documents':11,'hgab-missing-document-types':12}
    for finding in findings:finding['rank']=priority[finding['id']]
    findings.sort(key=lambda r:r['rank'])
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
    document['statistics']['lineItemReviewQueue']=review_queue['summary']
    document['lineItemReviewQueue']={'data':'line-item-review-queue.json','ranking':review_queue['ranking'],'scope':review_queue['scope'],'method':review_queue['method']}
    document['statistics']['rcsStageTrace']=trace
    document['districtComparisonPolicy']={'scope':'All district rows are available for reader selection in the all-district ranking. No selected-district section or person-specific defaults.','data':'congress-benchmark.json'}
    document['allDistrictComparison']=benchmark['summary']
    findings[0]['evidence']+=f' All {trace["unchangedInHGAB"]} DEO lines are retained unchanged in HGAB; no differentiated needs weighting is visible in the amounts.'
    document['localDatasetInventory']=[{'file':'database/poverty.json','use':'Potential socio-economic context; no year/definition recorded in the inspected rows, so not used as a needs control.'},
                                       {'file':'static/data/flood_summary.json','coverage':'2016–2024 projects','use':'Historical project reference; not a current flood-exposure or FY2027 needs denominator.'}]
    for item in document['localDatasetInventory']:
        item['sha256']=hashlib.sha256((ROOT.parent/'open-data-visualization'/item['file']).read_bytes()).hexdigest()
    (STATIC/'summary-data.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'analysis_output/investigation_summary.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    nav=re.search(r'<nav class="report-nav".*?</nav>',(STATIC/'rcs.html').read_text(),re.S).group(0)
    if 'href="congress.html"' not in nav:nav=nav.replace('</nav>','<a href="congress.html">Congressional District Allocations</a></nav>')
    if 'href="summary.html"' not in nav:nav=nav.replace('</nav>','<a href="summary.html">Summary · investigative leads</a></nav>')
    cards=''.join(f'<article class="finding" id="lead-{r["id"]}" data-basis="{esc(r["basis"])}"><span class="rank">Investigation priority {r["rank"]} · {esc(r["basis"])}</span><h2>{esc(r["title"])}</h2><p class="lead">{esc(r["lead"])}</p><dl>'+''.join(f'<dt>{label}</dt><dd>{esc(r[key])}</dd>' for label,key in [('Talking point','question'),('Observed evidence','evidence'),('Plausible explanation','alternative'),('What investigators need next','next'),('Parsing/location caution','caution')])+f'</dl><p><a href="{esc(r["page"])}">Supporting analysis and source tables →</a></p></article>' for r in findings)
    ranked=table(['Priority','Investigative lead','Evidence class','Question to verify'],[[r['rank'],r['title'],r['basis'],r['question']] for r in findings])
    neutral=table(['Schedule','HGAB 3rd lines','HGAB 3rd pesos','Changed between 2nd and 3rd'],coverage_rows)
    neutral+='<p>These extracted FMR, NIA, HFEP and DepEd schedules have no allocation changes between the two readings. Stability is not itself a red flag. No year-on-year repetition or NEP insertion claim follows from unchanged bill-stage totals. NIA named projects and the irrigation appendix are separate schedule slices; do not add their totals without reconciling hierarchy.</p>'
    quality='<p>NEP → HGAB → GAB/GAA are different stages; prior-year GAA is enacted, current proposals are not. Match allocation records at the same hierarchy before comparing money.</p><ul><li>Printed-total reconciliation catches amount/hierarchy errors but cannot certify title identity or location.</li><li>Preserve source pages and occurrence counts. One comparison row may group multiple allocations; headers are not projects.</li><li>Require barangay → town/city → province context. DEO numbers do not identify legislative districts.</li><li>Keep directional names, tranches, province splits and construction chainage distinct. The confirmed multi-place Butuan/RTR line stays outside strict LEG totals.</li><li>Strict congressional rankings cover only '+f'{coverage:.1%}'+' of extracted allocation value. Names indicate geography, not authorship or sponsorship.</li></ul><p><a href="congress.html#congress-investigation-evidence">Inspect congressional coverage limits →</a></p>'
    quality=quality.replace('NEP → HGAB → GAB/GAA','NEP → HGAB (House) → GAB (Senate) → Bicam → GAA')
    flow='<p><strong>NEP → HGAB (House version) → GAB (Senate version) → Bicam (House/Senate reconciliation) → GAA (enacted).</strong></p><p>NEP and final GAA provide the published bookends. The investigative focus is how allocations change through House and Senate deliberations and bicameral reconciliation. A genuinely new HGAB line deserves scrutiny: who proposed it, what documented need supports it, and whether it remains in the Senate and reconciled versions. A lawful amendment can add projects; an unmatched parser row is not yet a demonstrated amendment.</p><p>These pages currently trace NEP and House readings. No survival claim is made for Senate GAB, Bicam or FY2027 GAA until those versions are available and reconciled. Retained NEP repeat candidates and new HGAB insertion candidates answer different questions.</p>'
    flow+='<p><a href="congress.html#congress-all-representatives">Compare estimated allocations across all congressional districts →</a></p>'
    datasets=table(['Investigative question','Dataset or documents needed','Current workspace limitation'],[['RCS needs','Geocoded RCS sites, storage/catchment design, population served, water access and dry-season demand','Rainfall is province-level; it cannot locate demand or actual sites'],['Repeated work','Contract IDs, bill of quantities, as-built chainage, completion and disbursements','Budget titles and stated chainage do not establish paid work'],['Price clustering','Work quantities, standard estimates, procurement thresholds, prior-year comparable contracts','Exact peso values alone are not unit prices'],['Insertions','Audited native NEP/HGAB occurrence links and original PDF pages','A balanced total does not certify every unmatched row'],['LEG rankings','Dated barangay/municipality LEG boundaries and funded-segment geometry','PH location DB contains undated and conflicting claims'],['INSPIRE','Approved total project cost, phase ledger, obligations and releases','Appropriations are not disbursements']])
    datasets+='<p>Workspace search found a province poverty file, but its rows do not identify year or indicator definition; it is not used as a needs control. The local flood project summary covers 2016–2024 projects, not present-day hazard exposure. Neither provides the missing RCS site/catchment, water-access or demand denominator. Additional datasets must be dated, sourced and matched to the correct geographic level before correlation.</p>'
    hero=f'<section class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">FY2027 budget · investigative triage</span><div class="repeat-hero-total"><strong>{len(findings)}</strong><span>leads worth a closer look</span></div><p>Allocation patterns to question, explanations to check, and records to request.</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><span>Uniform RCS packages</span><strong>199 offices</strong></div><div><span>Repeat candidates</span><strong>686 proposals</strong></div></div><p>Evidence guides an investigation. None of these findings establishes corruption.</p></div></section>'
    filters='<div class="summary-controls"><input id="lead-search" type="search" placeholder="Search talking points" aria-label="Search talking points"><select id="lead-basis" aria-label="Filter evidence class"><option value="">All evidence classes</option>'+''.join(f'<option>{esc(r["basis"])}</option>' for r in findings)+'</select></div>'
    filterjs="""<script>const search=document.getElementById('lead-search'),basis=document.getElementById('lead-basis');function filter(){document.querySelectorAll('.finding').forEach(card=>card.hidden=!(card.textContent.toLowerCase().includes(search.value.toLowerCase())&&(!basis.value||card.dataset.basis===basis.value)))}search.addEventListener('input',filter);basis.addEventListener('change',filter);</script>"""
    hero=hero.replace('686 proposals',f'{len(unique):,} proposals')
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Budget Summary · Investigative Talking Points</title><style>*{box-sizing:border-box}body{margin:0;font:16px/1.5 system-ui,sans-serif;background:#f3f6f5;color:#18303b}header{background:#123944;color:white;padding:30px clamp(16px,2vw,32px)}header h1{font-size:clamp(28px,4vw,48px);margin:0}main{width:100%;padding:24px clamp(16px,2vw,32px)}a{color:#087e78}header a{color:white}header p{max-width:1100px}</style>'+STYLE+CSS+'</head><body><header><h1>Budget Summary · Investigative Talking Points</h1><p>NEP patterns and NEP → HGAB screens, with parsing uncertainty and location limits alongside every claim. Priorities are editorial triage, not a corruption score. Figures overlap and must not be added together.</p>'+nav+'</header><main>'+hero+'<p class="summary-queue-jump"><a href="#summary-top-line-items">Full line-item review queue ↓</a></p>'+section('summary-stages','Follow the changes between budget stages',flow)+section('ranked-leads','Where to start',ranked)+filters+cards+section('summary-quality','Parsing and location gotchas',quality)+section('summary-neutral','Other schedules · no reading-stage change found',neutral)+section('summary-data-needs','Evidence needed to strengthen the claims',datasets)+section('summary-top-line-items','Full line-item review queue',render_review_queue(review_queue,table,esc))+'</main>'+JS+filterjs+'</body></html>'
    (STATIC/'summary.html').write_text(page)
    (ROOT/'analysis_output/summary.html').write_text(page)
    # Fifteen links occupy three desktop rows; preserve equal menu height on
    # every page and enough rows for smaller screens.
    navstyle='<style id="summary-nav-layout">header .report-nav{display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr));grid-auto-rows:34px;align-content:start;gap:8px 10px!important;height:118px!important;min-height:118px!important;margin-top:16px!important}header .report-nav a{display:flex;align-items:center;justify-content:center;height:34px;padding:4px 7px;border:1px solid #ffffff55;border-radius:8px;text-align:center;text-decoration:none;font-size:12px;line-height:1.1;overflow-wrap:anywhere}@media(max-width:900px){header .report-nav{grid-template-columns:repeat(3,minmax(0,1fr));height:160px!important;min-height:160px!important}}@media(max-width:560px){header .report-nav{grid-template-columns:repeat(2,minmax(0,1fr));height:244px!important;min-height:244px!important}}</style>'
    for p in STATIC.glob('*.html'):
        t=p.read_text();t=re.sub(r'<nav class="report-nav".*?</nav>',lambda m:nav,t,flags=re.S)
        t=re.sub(r'<style id="summary-nav-layout">.*?</style>','',t,flags=re.S).replace('</head>',navstyle+'</head>',1);p.write_text(t)
    (ROOT/'analysis_output/summary.html').write_text((STATIC/'summary.html').read_text())
    from review_report_language import apply as apply_evidence_wording
    from location_data.build_inventory_location_review import build as build_inventory_location_review
    build_inventory_location_review()
    apply_evidence_wording()
    (ROOT/'analysis_output/summary.html').write_text((STATIC/'summary.html').read_text())
    print(json.dumps({'findings':len(findings),'rcs':rcs_stats,'repeats':repeat_stats,'fiveMillion':price_stats,'domesticInsertionCandidates':len(domestic)},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
