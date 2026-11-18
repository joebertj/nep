#!/usr/bin/env python3
"""Build a project-level comparison of HGAB allocations and POW summary estimates."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'


def read(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def write(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(value, encoding='utf-8')
    tmp.replace(path)


def build_data():
    indepth = read('dpwh-in-depth-data.json')
    total_cost_data = read('hgab-pow-total-estimates.json')
    total_cost_by_code = total_cost_data.get('byCode') or {}
    mapping = read('hb_nep_comparison_3rd_mapping.json')
    hgab = {}
    for row in mapping.get('hgabWithoutSelectedCounterpart', []):
        if row.get('allocationKind') == 'project' and row.get('id'):
            hgab[row['id']] = row
    for pair in mapping.get('pairs', []):
        row = pair.get('hgab') or {}
        if pair.get('hgabId') and row.get('allocationKind') in (None, 'project'):
            hgab[pair['hgabId']] = row

    docs_by_project = defaultdict(list)
    for doc in indepth.get('hgabPowResults', []):
        if doc.get('matchStatus') != 'exact_title_match' or not doc.get('hgabId'):
            continue
        project = hgab.get(doc['hgabId'])
        if not project:
            continue
        categories = doc.get('costCategoryBreakdown') or []
        share_total = sum(float(c.get('sharePct') or 0) for c in categories)
        category_total = sum(float(c.get('amountPesos') or 0) for c in categories)
        itemized_subtotal = sum(float(r.get('amountPesos') or 0) for r in doc.get('rows') or [])
        code = str(doc.get('code') or '')
        total_cost = total_cost_by_code.get(code.casefold()) or {}
        source_total = (total_cost.get('sourcePdfResults') or [{}])[0]
        docs_by_project[doc['hgabId']].append({
            'code': code,
            'status': doc.get('status') or '',
            'pageCount': doc.get('pageCount'),
            'summaryPages': sorted({int(c['sourcePage']) for c in categories if c.get('sourcePage') is not None}),
            'categoryCount': len(categories),
            'shareTotalPct': round(share_total, 3),
            'totalEstimatedCostPesos': total_cost.get('totalEstimatedCostPesos'),
            'evaluatedTotalEstimatedCostPesos': total_cost.get('evaluatedTotalEstimatedCostPesos'),
            'totalEstimateStatus': total_cost.get('status') or 'no_total_estimate_record',
            'totalConstructionCostPesos': source_total.get('totalConstructionCostPesos'),
            'engineeringAdministrativeOverheadPesos': source_total.get('engineeringAdministrativeOverheadPesos'),
            'printedTotalEstimatedCostPesos': source_total.get('printedTotalEstimatedCostPesos'),
            'sourcePdfCount': total_cost.get('sourcePdfCount') or 0,
            'sourcePdfSha256': total_cost.get('sourcePdfSha256') or [],
            'conflictingTotalEstimatedCostPesos': total_cost.get('conflictingTotalEstimatedCostPesos') or [],
            'firstPageSummarySubtotalPesos': round(category_total, 2) if categories and category_total > 0 else None,
            'itemizedDirectCostSubtotalPesos': round(itemized_subtotal) if itemized_subtotal else None,
            'summaryCategories': [
                {'label': c.get('label'), 'sharePct': c.get('sharePct'), 'amountPesos': c.get('amountPesos'), 'sourcePage': c.get('sourcePage')}
                for c in categories
            ],
        })

    projects = []
    for hgab_id, docs in docs_by_project.items():
        source = hgab[hgab_id]
        allocation = int(round(float(source.get('amountPesos') or 0)))
        # Copies of the same file code are deduplicated, but conflicting parses are not silently selected.
        grouped_codes = defaultdict(list)
        for doc in docs:
            grouped_codes[doc['code']].append(doc)
        candidates = []
        for code, versions in grouped_codes.items():
            versions.sort(key=lambda d: (d['categoryCount'], d['pageCount'] or 0), reverse=True)
            selected = dict(versions[0])
            totals = sorted({round(float(d['totalEstimatedCostPesos']), 2) for d in versions if d['totalEstimatedCostPesos'] is not None})
            source_conflicts = sorted({float(value) for d in versions for value in d.get('conflictingTotalEstimatedCostPesos') or []})
            selected['duplicateParseCount'] = len(versions)
            selected['conflictingEstimatePesos'] = sorted(set(totals + source_conflicts)) if len(totals) > 1 or source_conflicts else []
            if selected['conflictingEstimatePesos']:
                selected['totalEstimatedCostPesos'] = None
            elif selected['totalEstimatedCostPesos'] is not None:
                estimate_value = float(selected['totalEstimatedCostPesos'])
                lower_bounds = [
                    ('A+B+C', selected.get('firstPageSummarySubtotalPesos')),
                    ('G (D+E+F)', selected.get('totalConstructionCostPesos')),
                ]
                failed_bounds = [label for label, amount in lower_bounds if amount is not None and estimate_value < float(amount) * 0.99]
                if failed_bounds:
                    selected['totalEstimateReviewIssue'] = 'I amount is materially below ' + ' and '.join(failed_bounds)
                    selected['totalEstimateStatus'] = 'i_total_below_supporting_subtotal_review'
                    selected['totalEstimatedCostPesos'] = None
            candidates.append(selected)
        candidates.sort(key=lambda d: d['code'])
        full = [d for d in candidates if d['totalEstimatedCostPesos'] is not None]
        if any(d.get('conflictingEstimatePesos') for d in candidates):
            status = 'conflicting_total_estimated_cost_review'
            estimate = None
            variance = None
            pct = None
        elif len(candidates) > 1:
            status = 'multiple_pow_files_review'
            estimate = None
            variance = None
            pct = None
        elif any(d.get('totalEstimateReviewIssue') for d in candidates):
            status = 'i_total_reconciliation_review'
            estimate = None
            variance = None
            pct = None
        elif full:
            status = 'comparable_total_estimated_cost'
            estimate = full[0]['totalEstimatedCostPesos']
            variance = estimate - allocation
            pct = round(100 * variance / allocation, 2) if allocation else None
        elif candidates[0].get('firstPageSummarySubtotalPesos') or candidates[0].get('itemizedDirectCostSubtotalPesos'):
            status = 'subtotal_evidence_only_no_total_estimated_cost'
            estimate = None
            variance = None
            pct = None
        else:
            status = 'no_recovered_total_estimate'
            estimate = None
            variance = None
            pct = None
        projects.append({
            'hgabId': hgab_id,
            'title': source.get('projectName') or '',
            'office': source.get('office') or '',
            'region': source.get('region') or '',
            'pap': source.get('pap3') or source.get('pap2') or source.get('pap1') or '',
            'allocationPesos': allocation,
            'powEstimatePesos': estimate,
            'differencePesos': variance,
            'differencePct': pct,
            'status': status,
            'powFiles': candidates,
        })

    projects.sort(key=lambda p: (p['status'] != 'comparable_total_estimated_cost', -abs(p.get('differencePesos') or 0), p['title'].casefold()))
    eligible = [p for p in projects if p['status'] == 'comparable_total_estimated_cost']
    allocation_total = sum(p['allocationPesos'] for p in eligible)
    estimate_total = sum(p['powEstimatePesos'] for p in eligible)
    within = sum(abs(p['differencePct'] or 0) <= 5 for p in eligible)
    below = sum((p['differencePct'] or 0) < -5 for p in eligible)
    above = sum((p['differencePct'] or 0) > 5 for p in eligible)
    return {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'scope': 'FY2027 House 3rd-reading DPWH project allocations matched to Senate-provided HGAB POWs.',
        'method': 'Exact normalized POW title matches only. The allocation comparison uses the visible As Submitted amount printed on the I. TOTAL ESTIMATED COST row of the first page. The A+B+C summary, G Total Construction Cost (D+E+F), and H Engineering and Administrative Overhead are supporting detail only; none is substituted for I. Repeated copies with the same HGAB file code are deduplicated. Projects with multiple distinct matched POW codes are shown as review cases and excluded from aggregate totals.',
        'limitations': [
            'POW printed category totals are estimates, not actual expenditures, contract prices, or proof of completed work.',
            'The comparison target is I. TOTAL ESTIMATED COST, which includes G Total Construction Cost (D+E+F) and H Engineering and Administrative Overhead (EAO). A 100% A+B+C summary or D+E+F bill subtotal alone is not the comparison amount.',
            'Visible values are read by OCR from rendered first pages. The allocation comparison uses I. TOTAL ESTIMATED COST · As Submitted; As Evaluated is reported separately when visible. If I is not recovered, no estimate is substituted from another cost line.',
            'OCR-read I values materially below the A+B+C summary or G construction cost are held for review and excluded from aggregate comparison.',
            'Allocation and POW estimate can cover different scope, phases, or cost bases. A difference is a review signal, not an overrun, saving, or finding of wrongdoing.',
            'Multiple distinct matched POW codes and conflicting parses of one code are not summed or arbitrarily selected; they are excluded from aggregate comparison pending review.',
            'No exact-title match or no recovered summary does not prove that a POW is absent.'
        ],
        'summary': {
            'matchedProjectsWithPowRecords': len(projects),
            'projectsWithComparableEstimate': len(eligible),
            'projectsWithMultiplePowFiles': sum(p['status'] == 'multiple_pow_files_review' for p in projects),
            'projectsWithConflictingParseResults': sum(p['status'] == 'conflicting_total_estimated_cost_review' for p in projects),
            'projectsWithIReconciliationIssues': sum(p['status'] == 'i_total_reconciliation_review' for p in projects),
            'projectsWithSubtotalEvidenceOnly': sum(p['status'] == 'subtotal_evidence_only_no_total_estimated_cost' for p in projects),
            'projectsWithSubtotalEvidenceAndNoTotal': sum(p['status'] == 'no_recovered_total_estimate' for p in projects),
            'projectsWithoutRecoveredEstimate': sum(p['status'] == 'no_recovered_total_estimate' for p in projects),
            'allocationPesos': allocation_total,
            'powEstimatePesos': estimate_total,
            'differencePesos': estimate_total - allocation_total,
            'differencePct': round(100 * (estimate_total - allocation_total) / allocation_total, 2) if allocation_total else None,
            'estimateBelowAllocationMoreThan5Pct': below,
            'estimateAboveAllocationMoreThan5Pct': above,
            'within5Pct': within,
        },
        'projects': projects,
    }


def render(data):
    summary = data['summary']
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    version = hashlib.sha256(payload.encode()).hexdigest()[:12]
    html = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>HGAB allocation vs TOTAL ESTIMATED COST · POW comparison</title>
<style>
:root{--navy:#00246a;--blue:#0648a8;--gold:#fcd116;--ink:#18232d;--muted:#586877;--line:#d9e1e8;--paper:#f3f6f8;--green:#16867b;--red:#b83c32;--black:#111}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,sans-serif}header{background:#fff;border-bottom:1px solid var(--line);padding:22px clamp(16px,4vw,54px)}.brand{max-width:none;margin:auto;display:flex;align-items:center;gap:18px}.brand img{width:190px;max-width:40vw}.brand .eyebrow{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}h1{font-size:clamp(28px,4vw,42px);line-height:1.1;margin:5px 0;color:var(--navy)}.brand p{margin:4px 0;color:var(--muted)}main{width:100%;max-width:none;margin:auto;padding:22px clamp(12px,3vw,36px)}section,.notice{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}.notice{border-left:5px solid var(--gold)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.metric{background:#f7fafb;border:1px solid var(--line);border-radius:9px;padding:13px}.metric strong{display:block;font-size:clamp(21px,3vw,30px);color:var(--navy);font-variant-numeric:tabular-nums}.metric span{color:var(--muted);font-size:13px}.bars{display:grid;gap:12px;margin:16px 0}.bar-row{display:grid;grid-template-columns:minmax(180px,1fr) 3fr minmax(150px,auto);gap:12px;align-items:center}.track{height:22px;background:#e9eff2;border-radius:5px;overflow:hidden}.fill{height:100%;background:var(--green)}.fill.estimate{background:var(--blue)}.bar-value{text-align:right;font-variant-numeric:tabular-nums}.scatter{width:100%;overflow-x:auto}.scatter svg{display:block;width:100%;min-width:600px;height:auto}.axis{stroke:#607985;stroke-width:1}.grid{stroke:#dfe7ea;stroke-width:1}.identity{stroke:#111;stroke-width:2;stroke-dasharray:7 5}.point{fill:#087e78;fill-opacity:.4;stroke:#fff;stroke-width:.5}.details{margin:12px 0;padding:12px 14px;border:1px solid var(--line);border-radius:8px;background:#fafcfd}.details summary{font-weight:700;cursor:pointer}.details ul{padding-left:22px}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.controls input,.controls select,.controls button{font:inherit;padding:8px 10px;border:1px solid #aab8c5;border-radius:7px;background:#fff}.controls input{min-width:230px;flex:1}button{cursor:pointer}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px}table{border-collapse:collapse;width:100%;min-width:1100px;font-size:13px}th,td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{background:#edf2f7;position:sticky;top:0;z-index:1}td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.sub{display:block;color:var(--muted);font-size:12px}.pill{display:inline-block;padding:2px 7px;border-radius:999px;background:#eef3fa}.gap-negative{color:#9e312c}.gap-positive{color:#126c53}.pager{display:flex;justify-content:flex-end;align-items:center;gap:10px;padding:12px}.pager button{padding:7px 12px;border:1px solid #aab8c5;border-radius:6px;background:white}footer{width:100%;max-width:none;margin:auto;padding:20px clamp(12px,3vw,36px);color:var(--muted)}footer a{color:var(--blue)}@media(max-width:650px){.bar-row{grid-template-columns:1fr auto}.track{grid-column:1/-1;grid-row:2}.bar-value{grid-column:2;grid-row:1}.brand{align-items:flex-start;flex-direction:column}}
</style></head><body><header><div class="brand"><a href="https://bettergov.ph/" aria-label="BetterGov"><img src="https://assets.bettergov.ph/logos/webp/horizontal-black.webp" alt="BetterGov"></a><div><div class="eyebrow">FY2027 · Budget research · Senate HGAB</div><h1>HGAB allocation vs TOTAL ESTIMATED COST</h1><p>Compare House project allocations with I. TOTAL ESTIMATED COST from the matched POW.</p></div></div></header><main>
<div class="notice"><strong>Correct comparison basis.</strong> Compare the proposed allocation with I. TOTAL ESTIMATED COST · As Submitted. The first-page A+B+C summary and the D+E+F bill components feed into that total; neither subtotal alone is the comparison amount. The comparison uses the visible As Submitted amount in I. TOTAL ESTIMATED COST; As Evaluated is shown separately when present. A POW estimate is not actual expenditure, and differences may reflect scope or phase.</div>
<section><h2>TOTAL ESTIMATED COST comparison</h2><p>Aggregate comparison includes only unique HGAB project rows with one exact-title-matched POW file and a recovered I. TOTAL ESTIMATED COST. First-page A+B+C and bill-page D+E+F values are retained as evidence, not substituted for I.</p><div id="metrics" class="cards"></div><div id="bars" class="bars"></div><details class="details"><summary>How this comparison is calculated</summary><ul id="methods"></ul></details></section>
<section><h2>Project-level comparison and review queue</h2><p>Rows are sorted by the absolute difference when I is available. Projects without a recovered I are retained for review with their available subtotals identified. Multiple distinct POW files for one project are shown as review cases and excluded from totals.</p><div id="distribution" class="cards"></div><div id="scatter" class="scatter" role="img" aria-label="Project allocations compared with recovered TOTAL ESTIMATED COST values"></div><div class="controls"><label for="q">Search</label><input id="q" type="search" placeholder="Project, office, House row, or HGAB file code"><label for="status">Estimate status</label><select id="status"><option value="">All statuses</option><option value="comparable_total_estimated_cost">Comparable TOTAL ESTIMATED COST</option><option value="multiple_pow_files_review">Multiple POW files · review</option><option value="i_total_reconciliation_review">I total below A+B+C / G · review</option><option value="conflicting_total_estimated_cost_review">Conflicting TOTAL ESTIMATED COST values</option><option value="subtotal_evidence_only_no_total_estimated_cost">Subtotal evidence only · I not recovered</option><option value="no_recovered_total_estimate">No recovered TOTAL ESTIMATED COST</option></select><label for="sort">Sort</label><select id="sort"><option value="difference">Largest absolute difference</option><option value="allocation">Largest allocation</option><option value="estimate">Largest POW estimate</option><option value="title">Project title</option><option value="office">Office</option></select></div><div class="table-wrap"><table><thead><tr><th>HGAB project / office</th><th>HGAB allocation</th><th>POW I. TOTAL ESTIMATED COST · As Submitted</th><th>Difference · I − allocation</th><th>Difference %</th><th>POW file / basis</th></tr></thead><tbody id="rows"></tbody></table></div><div class="pager"><button id="previous">Previous</button><span id="page"></span><button id="next">Next</button></div></section>
</main><footer><p>Sources: FY2027 HGAB 3rd-reading project ledger and indexed Senate-provided HGAB POW PDFs. This comparison uses I. TOTAL ESTIMATED COST; OCR extraction status and visible A+B+C, G, and H context are shown per POW. Source PDF links are not published. Values are OCRed from rendered page images. <a href="dpwh.html">Return to Senate HGAB document coverage →</a></p><p>Generated data are preliminary machine extraction. Verify source pages and project scope before interpretation.</p></footer>
<script>
(async()=>{const D=await fetch('expectation-vs-reality-data.json?v=__VERSION__').then(r=>{if(!r.ok)throw Error('Comparison data failed to load');return r.json()}),S=D.summary||{},P=D.projects||[],fmt=n=>Number(n||0).toLocaleString('en-PH'),peso=n=>'₱'+fmt(Math.round(Number(n||0))),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),eligible=P.filter(p=>p.status==='comparable_total_estimated_cost'),metric=(v,l)=>`<div class="metric"><strong>${esc(v)}</strong><span>${esc(l)}</span></div>`;
const comparableCount=Number(S.projectsWithComparableEstimate||0);document.getElementById('metrics').innerHTML=comparableCount?[metric(fmt(comparableCount),'projects with one recovered TOTAL ESTIMATED COST'),metric(peso(S.allocationPesos),'HGAB allocation for these projects'),metric(peso(S.powEstimatePesos),'summed POW TOTAL ESTIMATED COST'),metric((S.differencePesos<0?'−':'')+peso(Math.abs(S.differencePesos||0))+' · '+(S.differencePct||0)+'%','POW TOTAL ESTIMATED COST minus allocation')].join(''):[metric('0','projects with one recovered TOTAL ESTIMATED COST'),metric('—','HGAB allocation total unavailable'),metric('—','TOTAL ESTIMATED COST not recovered'),metric('—','difference unavailable')].join('');
const max=Math.max(1,S.allocationPesos||0,S.powEstimatePesos||0);document.getElementById('bars').innerHTML=comparableCount?[['HGAB allocation',S.allocationPesos,'allocation'],['POW TOTAL ESTIMATED COST',S.powEstimatePesos,'estimate']].map(([l,v,k])=>`<div class="bar-row"><strong>${esc(l)}</strong><div class="track"><div class="fill ${k}" style="width:${100*Number(v||0)/max}%"></div></div><div class="bar-value">${peso(v)}</div></div>`).join(''):'<p class="notice">No aggregate comparison is shown until I. TOTAL ESTIMATED COST is recovered from the matched POWs.</p>';document.getElementById('methods').innerHTML=(D.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('');
for(const [id,val,label] of [['under',S.estimateBelowAllocationMoreThan5Pct,'TOTAL ESTIMATED COST more than 5% below allocation'],['near',S.within5Pct,'within ±5%'],['over',S.estimateAboveAllocationMoreThan5Pct,'TOTAL ESTIMATED COST more than 5% above allocation'],['subtotal',S.projectsWithSubtotalEvidenceOnly,'Subtotal evidence only · I not recovered'],['reconcile',S.projectsWithIReconciliationIssues,'I below A+B+C or G · OCR reconciliation review'],['multiple',S.projectsWithMultiplePowFiles,'multiple distinct POW files · excluded from totals'],['conflicts',S.projectsWithConflictingParseResults,'conflicting parse results · excluded from totals']])document.getElementById('distribution').insertAdjacentHTML('beforeend',metric(fmt(val),label));
const W=960,H=520,L=150,R=30,T=28,B=62,maxAxis=Math.max(1,...eligible.flatMap(p=>[p.allocationPesos,p.powEstimatePesos])),x=v=>L+(Number(v||0)/maxAxis)*(W-L-R),y=v=>H-B-(Number(v||0)/maxAxis)*(H-T-B),ticks=5,svg=[`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Scatter plot of TOTAL ESTIMATED COST against HGAB allocation; dashed line indicates equality">`];for(let i=0;i<=ticks;i++){const v=maxAxis*i/ticks,px=x(v),py=y(v);svg.push(`<line class="grid" x1="${L}" y1="${py}" x2="${W-R}" y2="${py}"/><line class="grid" x1="${px}" y1="${T}" x2="${px}" y2="${H-B}"/><text x="${L-10}" y="${py+4}" text-anchor="end" font-size="11">${esc(peso(v))}</text><text x="${px}" y="${H-B+20}" text-anchor="middle" font-size="11">${esc(peso(v))}</text>`)}svg.push(`<line class="identity" x1="${x(0)}" y1="${y(0)}" x2="${x(maxAxis)}" y2="${y(maxAxis)}"/><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${H-B}"/><line class="axis" x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}"/><text x="${(L+W-R)/2}" y="${H-12}" text-anchor="middle" font-size="13">POW I. TOTAL ESTIMATED COST</text><text x="26" y="${(T+H-B)/2}" text-anchor="middle" font-size="13" transform="rotate(-90 26 ${(T+H-B)/2})">HGAB proposed allocation</text>`);for(const p of eligible)svg.push(`<circle class="point" cx="${x(p.powEstimatePesos)}" cy="${y(p.allocationPesos)}" r="3"><title>${esc(p.title)} · allocation ${esc(peso(p.allocationPesos))} · POW estimate ${esc(peso(p.powEstimatePesos))}</title></circle>`);svg.push('</svg>');document.getElementById('scatter').innerHTML=eligible.length?svg.join(''):'<p class="notice">No plotted comparisons: no matched POW currently has a recovered I. TOTAL ESTIMATED COST amount.</p>';
let page=0,perPage=25;const q=document.getElementById('q'),status=document.getElementById('status'),sort=document.getElementById('sort'),body=document.getElementById('rows'),draw=()=>{const needle=q.value.trim().toLocaleLowerCase();let rows=P.filter(p=>(!status.value||p.status===status.value)&&(!needle||[p.title,p.office,p.region,p.hgabId,...p.powFiles.map(f=>f.code)].join(' ').toLocaleLowerCase().includes(needle)));rows.sort((a,b)=>{if(sort.value==='title')return a.title.localeCompare(b.title);if(sort.value==='office')return a.office.localeCompare(b.office)||a.title.localeCompare(b.title);if(sort.value==='allocation')return b.allocationPesos-a.allocationPesos;if(sort.value==='estimate')return (b.powEstimatePesos||0)-(a.powEstimatePesos||0);return Math.abs(b.differencePesos||0)-Math.abs(a.differencePesos||0)||a.title.localeCompare(b.title)});const pages=Math.max(1,Math.ceil(rows.length/perPage));page=Math.max(0,Math.min(page,pages-1));body.innerHTML=rows.slice(page*perPage,(page+1)*perPage).map(p=>{const estimate=p.powEstimatePesos==null?'—':peso(p.powEstimatePesos),difference=p.differencePesos==null?'—':peso(Math.abs(p.differencePesos))+(p.differencePesos<0?' below':' above'),pct=p.differencePct==null?'—':(p.differencePct>0?'+':'')+p.differencePct+'%',files=p.powFiles.map(f=>`<details><summary>${esc(f.code)}</summary><p>${fmt(f.categoryCount)} A+B+C summary rows · category shares ${fmt(f.shareTotalPct)}% · first-page subtotal ${f.firstPageSummarySubtotalPesos==null?'not recovered':peso(f.firstPageSummarySubtotalPesos)} · G (D+E+F) ${f.totalConstructionCostPesos==null?'not recovered':peso(f.totalConstructionCostPesos)} · H EAO ${f.engineeringAdministrativeOverheadPesos==null?'not recovered':peso(f.engineeringAdministrativeOverheadPesos)} · I. TOTAL ESTIMATED COST · As Submitted ${f.totalEstimatedCostPesos==null?'not recovered':peso(f.totalEstimatedCostPesos)} · As Evaluated ${f.evaluatedTotalEstimatedCostPesos==null?'not printed/recovered':peso(f.evaluatedTotalEstimatedCostPesos)} · extraction ${esc(f.totalEstimateStatus)} · pages ${esc(f.summaryPages.join(', ')||'not recorded')}${f.totalEstimateReviewIssue?` · review: ${esc(f.totalEstimateReviewIssue)}`:''}${f.conflictingEstimatePesos?.length?` · conflicting parsed estimates ${f.conflictingEstimatePesos.map(peso).join(' / ')}`:''}${f.duplicateParseCount>1?` · ${fmt(f.duplicateParseCount)} parser records for this file code`:''}${f.itemizedDirectCostSubtotalPesos?` · itemized subtotal ${peso(f.itemizedDirectCostSubtotalPesos)}`:''}</p><ul>${f.summaryCategories.map(c=>`<li>${esc(c.label)} · ${fmt(c.sharePct)}% · ${peso(c.amountPesos)} · p. ${fmt(c.sourcePage)}</li>`).join('')}</ul></details>`).join('');return `<tr><td><strong>${esc(p.title)}</strong><span class="sub">${esc(p.hgabId)} · ${esc(p.office)} · ${esc(p.region)}</span><span class="sub">${esc(p.pap)}</span></td><td class="num">${peso(p.allocationPesos)}</td><td class="num">${estimate}<span class="sub">${esc(p.status.replaceAll('_',' '))}</span></td><td class="num ${p.differencePesos==null?'':p.differencePesos<0?'gap-negative':'gap-positive'}">${difference}</td><td class="num">${pct}</td><td>${files||'No matched POW file code available'}</td></tr>`}).join('')||'<tr><td colspan="6">No project rows match this filter.</td></tr>';document.getElementById('page').textContent=`Page ${page+1} of ${pages} · ${fmt(rows.length)} project rows`;document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=page+1>=pages};for(const el of [q,status,sort])el.addEventListener(el===q?'input':'change',()=>{page=0;draw()});document.getElementById('previous').onclick=()=>{page--;draw()};document.getElementById('next').onclick=()=>{page++;draw()};draw();})().catch(e=>{document.querySelector('main').insertAdjacentHTML('afterbegin',`<div class="notice">${String(e.message||e)}</div>`)})
</script></body></html>'''
    html = html.replace('__VERSION__', version)
    import uniform_report_menu
    html = uniform_report_menu.apply_page(html, 'expectation-vs-reality.html')
    from report_table_presentation import apply_page_table_module
    html,_=apply_page_table_module('expectation-vs-reality.html',html)
    return payload + '\n', html


def main():
    data = build_data()
    payload, html = render(data)
    for folder in (OUT, STATIC):
        write(folder / 'expectation-vs-reality-data.json', payload)
        write(folder / 'expectation-vs-reality.html', html)
    print(json.dumps(data['summary'], indent=2))


if __name__ == '__main__':
    main()
