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
        full_summary = bool(categories) and category_total > 0 and 98 <= share_total <= 102
        docs_by_project[doc['hgabId']].append({
            'code': doc.get('code') or '',
            'status': doc.get('status') or '',
            'pageCount': doc.get('pageCount'),
            'summaryPages': sorted({int(c['sourcePage']) for c in categories if c.get('sourcePage') is not None}),
            'categoryCount': len(categories),
            'shareTotalPct': round(share_total, 3),
            'categoryEstimatePesos': round(category_total) if full_summary else None,
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
            totals = sorted({d['categoryEstimatePesos'] for d in versions if d['categoryEstimatePesos'] is not None})
            selected['duplicateParseCount'] = len(versions)
            selected['conflictingEstimatePesos'] = totals if len(totals) > 1 else []
            if len(totals) > 1:
                selected['categoryEstimatePesos'] = None
            candidates.append(selected)
        candidates.sort(key=lambda d: d['code'])
        full = [d for d in candidates if d['categoryEstimatePesos'] is not None]
        if any(d.get('conflictingEstimatePesos') for d in candidates):
            status = 'conflicting_parse_results_review'
            estimate = None
            variance = None
            pct = None
        elif len(candidates) > 1:
            status = 'multiple_pow_files_review'
            estimate = None
            variance = None
            pct = None
        elif full:
            status = 'comparable_printed_category_estimate'
            estimate = full[0]['categoryEstimatePesos']
            variance = estimate - allocation
            pct = round(100 * variance / allocation, 2) if allocation else None
        elif candidates[0].get('itemizedDirectCostSubtotalPesos'):
            status = 'itemized_subtotal_only'
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

    projects.sort(key=lambda p: (p['status'] != 'comparable_printed_category_estimate', -abs(p.get('differencePesos') or 0), p['title'].casefold()))
    eligible = [p for p in projects if p['status'] == 'comparable_printed_category_estimate']
    allocation_total = sum(p['allocationPesos'] for p in eligible)
    estimate_total = sum(p['powEstimatePesos'] for p in eligible)
    within = sum(abs(p['differencePct'] or 0) <= 5 for p in eligible)
    below = sum((p['differencePct'] or 0) < -5 for p in eligible)
    above = sum((p['differencePct'] or 0) > 5 for p in eligible)
    return {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'scope': 'FY2027 House 3rd-reading DPWH project allocations matched to Senate-provided HGAB POWs.',
        'method': 'Exact normalized POW title matches only. A POW estimate is the sum of the printed project-wide category summary where recovered category shares total 98–102%. Repeated copies with the same HGAB file code are deduplicated. Projects with multiple distinct matched POW codes are shown as review cases and excluded from aggregate totals.',
        'limitations': [
            'POW printed category totals are estimates, not actual expenditures, contract prices, or proof of completed work.',
            'Only project-wide printed category summaries with a 98–102% share total are compared as a full estimate. Itemized direct-cost subtotals are shown as partial evidence and are not substituted for the POW estimate.',
            'Allocation and POW estimate can cover different scope, phases, or cost bases. A difference is a review signal, not an overrun, saving, or finding of wrongdoing.',
            'Multiple distinct matched POW codes and conflicting parses of one code are not summed or arbitrarily selected; they are excluded from aggregate comparison pending review.',
            'No exact-title match or no recovered summary does not prove that a POW is absent.'
        ],
        'summary': {
            'matchedProjectsWithPowRecords': len(projects),
            'projectsWithComparableEstimate': len(eligible),
            'projectsWithMultiplePowFiles': sum(p['status'] == 'multiple_pow_files_review' for p in projects),
            'projectsWithConflictingParseResults': sum(p['status'] == 'conflicting_parse_results_review' for p in projects),
            'projectsWithItemizedSubtotalOnly': sum(p['status'] == 'itemized_subtotal_only' for p in projects),
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
<title>Expectation vs Reality · HGAB allocation and POW estimates</title>
<style>
:root{--navy:#00246a;--blue:#0648a8;--gold:#fcd116;--ink:#18232d;--muted:#586877;--line:#d9e1e8;--paper:#f3f6f8;--green:#16867b;--red:#b83c32;--black:#111}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,sans-serif}header{background:#fff;border-bottom:1px solid var(--line);padding:22px clamp(16px,4vw,54px)}.brand{max-width:1300px;margin:auto;display:flex;align-items:center;gap:18px}.brand img{width:190px;max-width:40vw}.brand .eyebrow{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}h1{font-size:clamp(28px,4vw,42px);line-height:1.1;margin:5px 0;color:var(--navy)}.brand p{margin:4px 0;color:var(--muted)}main{max-width:1500px;margin:auto;padding:22px clamp(12px,3vw,36px)}section,.notice{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin:16px 0}.notice{border-left:5px solid var(--gold)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.metric{background:#f7fafb;border:1px solid var(--line);border-radius:9px;padding:13px}.metric strong{display:block;font-size:clamp(21px,3vw,30px);color:var(--navy);font-variant-numeric:tabular-nums}.metric span{color:var(--muted);font-size:13px}.bars{display:grid;gap:12px;margin:16px 0}.bar-row{display:grid;grid-template-columns:minmax(180px,1fr) 3fr minmax(150px,auto);gap:12px;align-items:center}.track{height:22px;background:#e9eff2;border-radius:5px;overflow:hidden}.fill{height:100%;background:var(--green)}.fill.estimate{background:var(--blue)}.bar-value{text-align:right;font-variant-numeric:tabular-nums}.scatter{width:100%;overflow-x:auto}.scatter svg{display:block;width:100%;min-width:600px;height:auto}.axis{stroke:#607985;stroke-width:1}.grid{stroke:#dfe7ea;stroke-width:1}.identity{stroke:#111;stroke-width:2;stroke-dasharray:7 5}.point{fill:#087e78;fill-opacity:.4;stroke:#fff;stroke-width:.5}.details{margin:12px 0;padding:12px 14px;border:1px solid var(--line);border-radius:8px;background:#fafcfd}.details summary{font-weight:700;cursor:pointer}.details ul{padding-left:22px}.controls{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.controls input,.controls select,.controls button{font:inherit;padding:8px 10px;border:1px solid #aab8c5;border-radius:7px;background:#fff}.controls input{min-width:230px;flex:1}button{cursor:pointer}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:8px}table{border-collapse:collapse;width:100%;min-width:1100px;font-size:13px}th,td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid var(--line);overflow-wrap:anywhere}th{background:#edf2f7;position:sticky;top:0;z-index:1}td.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}.sub{display:block;color:var(--muted);font-size:12px}.pill{display:inline-block;padding:2px 7px;border-radius:999px;background:#eef3fa}.gap-negative{color:#9e312c}.gap-positive{color:#126c53}.pager{display:flex;justify-content:flex-end;align-items:center;gap:10px;padding:12px}.pager button{padding:7px 12px;border:1px solid #aab8c5;border-radius:6px;background:white}footer{max-width:1500px;margin:auto;padding:20px clamp(12px,3vw,36px);color:var(--muted)}footer a{color:var(--blue)}@media(max-width:650px){.bar-row{grid-template-columns:1fr auto}.track{grid-column:1/-1;grid-row:2}.bar-value{grid-column:2;grid-row:1}.brand{align-items:flex-start;flex-direction:column}}
</style></head><body><header><div class="brand"><a href="https://bettergov.ph/" aria-label="BetterGov"><img src="https://assets.bettergov.ph/logos/webp/horizontal-black.webp" alt="BetterGov"></a><div><div class="eyebrow">FY2027 · Budget research · Senate HGAB</div><h1>Expectation vs Reality</h1><p>House project allocations compared with printed category estimates recovered from matched POWs.</p></div></div></header><main>
<div class="notice"><strong>How to read this comparison.</strong> A POW is a project estimate, not actual expenditure. Allocation and POW estimates may cover different scope, phases, or cost bases. Differences are review leads, not proof of overrun or savings.</div>
<section><h2>Matched project totals</h2><p>Aggregate comparison includes only unique HGAB project rows with one exact-title-matched POW file and a readable project-wide printed category summary.</p><div id="metrics" class="cards"></div><div id="bars" class="bars"></div><details class="details"><summary>How this comparison is calculated</summary><ul id="methods"></ul></details></section>
<section><h2>Project-level differences</h2><p>Sorted by largest absolute gap between the HGAB allocation and the POW printed category estimate. Multiple distinct POW files for one project are shown as review cases and excluded from totals.</p><div id="distribution" class="cards"></div><div id="scatter" class="scatter" role="img" aria-label="Project allocations compared with matched POW estimates"></div><div class="controls"><label for="q">Search</label><input id="q" type="search" placeholder="Project, office, House row, or HGAB file code"><label for="status">Estimate status</label><select id="status"><option value="">All statuses</option><option value="comparable_printed_category_estimate">Comparable printed estimate</option><option value="multiple_pow_files_review">Multiple POW files · review</option><option value="conflicting_parse_results_review">Conflicting parse results</option><option value="itemized_subtotal_only">Itemized subtotal only</option><option value="no_recovered_total_estimate">No recovered total estimate</option></select><label for="sort">Sort</label><select id="sort"><option value="difference">Largest absolute difference</option><option value="allocation">Largest allocation</option><option value="estimate">Largest POW estimate</option><option value="title">Project title</option><option value="office">Office</option></select></div><div class="table-wrap"><table><thead><tr><th>HGAB project / office</th><th>HGAB allocation</th><th>POW category estimate</th><th>Difference · estimate − allocation</th><th>Difference %</th><th>POW file / basis</th></tr></thead><tbody id="rows"></tbody></table></div><div class="pager"><button id="previous">Previous</button><span id="page"></span><button id="next">Next</button></div></section>
</main><footer><p>Sources: FY2027 HGAB 3rd-reading project ledger and Senate-provided HGAB POWs. Source PDF links are not published. <a href="dpwh.html">Return to Senate HGAB document coverage →</a></p><p>Generated data are preliminary machine extraction. Verify source pages and project scope before interpretation.</p></footer>
<script>
(async()=>{const D=await fetch('expectation-vs-reality-data.json?v=__VERSION__').then(r=>{if(!r.ok)throw Error('Comparison data failed to load');return r.json()}),S=D.summary||{},P=D.projects||[],fmt=n=>Number(n||0).toLocaleString('en-PH'),peso=n=>'₱'+fmt(Math.round(Number(n||0))),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),eligible=P.filter(p=>p.status==='comparable_printed_category_estimate'),metric=(v,l)=>`<div class="metric"><strong>${esc(v)}</strong><span>${esc(l)}</span></div>`;
document.getElementById('metrics').innerHTML=[metric(fmt(S.projectsWithComparableEstimate),'projects with one comparable printed estimate'),metric(peso(S.allocationPesos),'HGAB allocation for these projects'),metric(peso(S.powEstimatePesos),'summed POW category estimates'),metric((S.differencePesos<0?'−':'')+peso(Math.abs(S.differencePesos||0))+' · '+(S.differencePct||0)+'%','POW estimate minus allocation')].join('');
const max=Math.max(1,S.allocationPesos||0,S.powEstimatePesos||0);document.getElementById('bars').innerHTML=[['HGAB allocation',S.allocationPesos,'allocation'],['POW printed category estimate',S.powEstimatePesos,'estimate']].map(([l,v,k])=>`<div class="bar-row"><strong>${esc(l)}</strong><div class="track"><div class="fill ${k}" style="width:${100*Number(v||0)/max}%"></div></div><div class="bar-value">${peso(v)}</div></div>`).join('');document.getElementById('methods').innerHTML=(D.limitations||[]).map(x=>`<li>${esc(x)}</li>`).join('');
for(const [id,val,label] of [['under',S.estimateBelowAllocationMoreThan5Pct,'POW estimate more than 5% below allocation'],['near',S.within5Pct,'within ±5%'],['over',S.estimateAboveAllocationMoreThan5Pct,'POW estimate more than 5% above allocation'],['multiple',S.projectsWithMultiplePowFiles,'multiple distinct POW files · excluded from totals'],['conflicts',S.projectsWithConflictingParseResults,'conflicting parse results · excluded from totals']])document.getElementById('distribution').insertAdjacentHTML('beforeend',metric(fmt(val),label));
const W=960,H=520,L=150,R=30,T=28,B=62,maxAxis=Math.max(1,...eligible.flatMap(p=>[p.allocationPesos,p.powEstimatePesos])),x=v=>L+(Number(v||0)/maxAxis)*(W-L-R),y=v=>H-B-(Number(v||0)/maxAxis)*(H-T-B),ticks=5,svg=[`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Scatter plot of POW estimate against HGAB allocation; dashed line indicates equality">`];for(let i=0;i<=ticks;i++){const v=maxAxis*i/ticks,px=x(v),py=y(v);svg.push(`<line class="grid" x1="${L}" y1="${py}" x2="${W-R}" y2="${py}"/><line class="grid" x1="${px}" y1="${T}" x2="${px}" y2="${H-B}"/><text x="${L-10}" y="${py+4}" text-anchor="end" font-size="11">${esc(peso(v))}</text><text x="${px}" y="${H-B+20}" text-anchor="middle" font-size="11">${esc(peso(v))}</text>`)}svg.push(`<line class="identity" x1="${x(0)}" y1="${y(0)}" x2="${x(maxAxis)}" y2="${y(maxAxis)}"/><line class="axis" x1="${L}" y1="${T}" x2="${L}" y2="${H-B}"/><line class="axis" x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}"/><text x="${(L+W-R)/2}" y="${H-12}" text-anchor="middle" font-size="13">POW printed category estimate</text><text x="26" y="${(T+H-B)/2}" text-anchor="middle" font-size="13" transform="rotate(-90 26 ${(T+H-B)/2})">HGAB proposed allocation</text>`);for(const p of eligible)svg.push(`<circle class="point" cx="${x(p.powEstimatePesos)}" cy="${y(p.allocationPesos)}" r="3"><title>${esc(p.title)} · allocation ${esc(peso(p.allocationPesos))} · POW estimate ${esc(peso(p.powEstimatePesos))}</title></circle>`);svg.push('</svg>');document.getElementById('scatter').innerHTML=svg.join('');
let page=0,perPage=25;const q=document.getElementById('q'),status=document.getElementById('status'),sort=document.getElementById('sort'),body=document.getElementById('rows'),draw=()=>{const needle=q.value.trim().toLocaleLowerCase();let rows=P.filter(p=>(!status.value||p.status===status.value)&&(!needle||[p.title,p.office,p.region,p.hgabId,...p.powFiles.map(f=>f.code)].join(' ').toLocaleLowerCase().includes(needle)));rows.sort((a,b)=>{if(sort.value==='title')return a.title.localeCompare(b.title);if(sort.value==='office')return a.office.localeCompare(b.office)||a.title.localeCompare(b.title);if(sort.value==='allocation')return b.allocationPesos-a.allocationPesos;if(sort.value==='estimate')return (b.powEstimatePesos||0)-(a.powEstimatePesos||0);return Math.abs(b.differencePesos||0)-Math.abs(a.differencePesos||0)||a.title.localeCompare(b.title)});const pages=Math.max(1,Math.ceil(rows.length/perPage));page=Math.max(0,Math.min(page,pages-1));body.innerHTML=rows.slice(page*perPage,(page+1)*perPage).map(p=>{const estimate=p.powEstimatePesos==null?'—':peso(p.powEstimatePesos),difference=p.differencePesos==null?'—':peso(Math.abs(p.differencePesos))+(p.differencePesos<0?' below':' above'),pct=p.differencePct==null?'—':(p.differencePct>0?'+':'')+p.differencePct+'%',files=p.powFiles.map(f=>`<details><summary>${esc(f.code)}</summary><p>${fmt(f.categoryCount)} printed categories · share total ${fmt(f.shareTotalPct)}% · pages ${esc(f.summaryPages.join(', ')||'not recorded')}${f.conflictingEstimatePesos?.length?` · conflicting parsed estimates ${f.conflictingEstimatePesos.map(peso).join(' / ')}`:''}${f.duplicateParseCount>1?` · ${fmt(f.duplicateParseCount)} parser records for this file code`:''}${f.itemizedDirectCostSubtotalPesos?` · itemized subtotal ${peso(f.itemizedDirectCostSubtotalPesos)}`:''}</p><ul>${f.summaryCategories.map(c=>`<li>${esc(c.label)} · ${fmt(c.sharePct)}% · ${peso(c.amountPesos)} · p. ${fmt(c.sourcePage)}</li>`).join('')}</ul></details>`).join('');return `<tr><td><strong>${esc(p.title)}</strong><span class="sub">${esc(p.hgabId)} · ${esc(p.office)} · ${esc(p.region)}</span><span class="sub">${esc(p.pap)}</span></td><td class="num">${peso(p.allocationPesos)}</td><td class="num">${estimate}<span class="sub">${esc(p.status.replaceAll('_',' '))}</span></td><td class="num ${p.differencePesos==null?'':p.differencePesos<0?'gap-negative':'gap-positive'}">${difference}</td><td class="num">${pct}</td><td>${files||'No matched POW file code available'}</td></tr>`}).join('')||'<tr><td colspan="6">No project rows match this filter.</td></tr>';document.getElementById('page').textContent=`Page ${page+1} of ${pages} · ${fmt(rows.length)} project rows`;document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=page+1>=pages};for(const el of [q,status,sort])el.addEventListener(el===q?'input':'change',()=>{page=0;draw()});document.getElementById('previous').onclick=()=>{page--;draw()};document.getElementById('next').onclick=()=>{page++;draw()};draw();})().catch(e=>{document.querySelector('main').insertAdjacentHTML('afterbegin',`<div class="notice">${String(e.message||e)}</div>`)})
</script></body></html>'''
    html = html.replace('__VERSION__', version)
    import uniform_report_menu
    html = uniform_report_menu.apply_page(html, 'expectation-vs-reality.html')
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
