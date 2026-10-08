#!/usr/bin/env python3
"""Build a standalone HFEP review page from candidate extraction and DuckDB outputs."""

import csv
import json
from pathlib import Path
from report_styles import fit_tables

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "analysis_output" / "hb_agencies"
SOURCE = ROOT / "hb10858_hfep_projects.json"
DEST = ROOT / "analysis_output" / "hfep.html"


def rows(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        raise SystemExit(f"Missing {path}; run analyze_hb_agencies.py with the HFEP Parquet first.")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def number(row: dict, key: str) -> int:
    try:
        return int(float(row.get(key) or 0))
    except (ValueError, TypeError):
        return 0


payload = json.loads(SOURCE.read_text(encoding="utf-8"))
candidates = payload["data"]["data"]
metadata = payload.get("metadata", {})
prices = rows("hfep_amount_frequency.csv")
types = rows("hfep_type_amount_frequency.csv")
profiles = rows("hfep_component_profiles.csv")
components_review = rows("hfep_component_reconciliation.csv")

type_summary = {}
for row in types:
    name = row["facility_type"]
    item = type_summary.setdefault(name, {"facility_type": name, "facility_candidates": 0, "candidate_total_pesos": 0})
    count = number(row, "facility_candidates")
    item["facility_candidates"] += count
    item["candidate_total_pesos"] += count * number(row, "amountPesos")
type_summary = sorted(type_summary.values(), key=lambda x: -x["facility_candidates"])

at_500k = [r for r in candidates if number(r, "amountPesos") == 500_000]
at_500k_bhs = [r for r in at_500k if "barangay health station" in r["projectName"].lower() or " bhs" in r["projectName"].lower()]
profile_500k = next((r for r in profiles if number(r, "amountPesos") == 500_000), {})
candidate_sum = sum(number(r, "amountPesos") for r in candidates)
component_totals = {
    "infrastructure": sum(number(r, "amountInfrastructurePesos") for r in candidates),
    "medicalEquipment": sum(number(r, "amountMedicalEquipmentPesos") for r in candidates),
    "motorVehicle": sum(number(r, "amountMotorVehiclePesos") for r in candidates),
}
grand_total = number(metadata, "printedGrandTotalPesos")
gap = grand_total - candidate_sum
embedded = {
    "candidates": candidates,
    "prices": prices[:15],
    "types": type_summary,
    "componentTotals": component_totals,
    "candidateCount": len(candidates),
    "candidateSum": candidate_sum,
    "grandTotal": grand_total,
    "gap": gap,
    "gapPct": 100 * gap / grand_total if grand_total else 0,
    "at500k": len(at_500k),
    "at500kBhs": len(at_500k_bhs),
    "profile500k": profile_500k,
    "componentMismatches": len(components_review),
}
data = json.dumps(embedded, ensure_ascii=False).replace("</", "<\\/")

html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="A review of FY 2027 HFEP facility allocations and repeated component amounts in HB 10858.">
<title>Budget review · HFEP (HB 10858 HGAB FY2027)</title>
<style>
:root{--ink:#172b3a;--muted:#637381;--paper:#f3f6f5;--card:#fff;--line:#dce4e1;--teal:#087e78;--teal-dark:#075c58;--mint:#dff3ee;--amber:#9a5a09;--amber-bg:#fff3dd;--blue:#315e83;--shadow:0 12px 32px #17323c0b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--blue)}header{background:#102f3e;color:#f4f7f6;padding:40px max(24px,calc((100vw - 1120px)/2)) 36px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:11px;color:#a7ddd1;font-weight:750}h1{font-size:clamp(32px,5vw,52px);letter-spacing:-.04em;line-height:1.03;margin:13px 0;max-width:900px}header p{color:#d4e1df;max-width:800px;margin:0;font-size:16px}.nav{margin-top:20px;font-size:13px;color:#bdd0d0}.report-nav a{color:#a7ddd1}.wrap{max-width:1120px;padding:24px;margin:auto}.section{margin:0 0 18px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:var(--shadow)}h2{font-size:22px;letter-spacing:-.025em;margin:0 0 4px}h3{font-size:16px;margin:0 0 5px}.sub{color:var(--muted);font-size:13px;margin:0 0 17px}.lead{background:linear-gradient(135deg,#e5f5f1,#fff 72%);border-color:#c7e9e0}.leadgrid{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center}.big{font-size:clamp(58px,9vw,90px);font-weight:820;letter-spacing:-.065em;line-height:1;color:var(--teal-dark)}.biglabel{font-size:19px;font-weight:740;margin-top:8px}.bigsub{font-size:13px;color:var(--muted);margin-top:5px}.callout{background:var(--mint);border-left:4px solid var(--teal);border-radius:9px;padding:13px 15px;margin-top:14px}.warning{background:var(--amber-bg);border:1px solid #f1d8ad;color:#65440f;border-radius:11px;padding:14px 16px;margin-bottom:18px}.warning strong{color:#4e350e}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:20px}.metric{padding:14px 15px;background:#ffffffd9;border:1px solid var(--line);border-radius:12px}.mlabel{font-size:12px;color:var(--muted)}.mvalue{font-size:24px;line-height:1.2;font-weight:760;margin-top:4px;font-variant-numeric:tabular-nums}.mnote{font-size:11px;color:var(--muted);margin-top:4px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}.bars{display:grid;gap:10px}.barrow{display:grid;grid-template-columns:minmax(90px,1.1fr) 3fr 75px;gap:10px;align-items:center;font-size:13px}.barname{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.track{height:11px;background:#edf1ef;border-radius:9px;overflow:hidden}.bar{height:100%;background:var(--teal);border-radius:9px;min-width:2px}.barvalue{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;background:white;font-size:12px}th,td{padding:9px 11px;border-bottom:1px solid #e9eeec;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#f7faf8;color:#51626b;font-size:11px;z-index:1}td.num,th.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}td.title{min-width:280px;max-width:570px}.component{display:grid;gap:10px}.componentrow{display:grid;grid-template-columns:180px 1fr 115px;gap:12px;align-items:center;font-size:13px}.stack{display:flex;height:16px;background:#eef1ef;border-radius:9px;overflow:hidden}.seg-infra{background:#087e78}.seg-med{background:#5b88b5}.seg-vehicle{background:#dda64d}.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:11px;color:var(--muted);margin:10px 0 16px}.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.toolbar{display:flex;gap:9px;margin:13px 0;flex-wrap:wrap}.toolbar input,.toolbar select{border:1px solid var(--line);border-radius:9px;padding:10px 12px;font:inherit;background:white;color:var(--ink)}.toolbar input{min-width:min(340px,100%);flex:1}.pager{display:flex;justify-content:flex-end;align-items:center;gap:10px;color:var(--muted);font-size:12px;margin-top:10px}.pager button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.tag{display:inline-block;background:#e8f1f6;color:#315e83;border-radius:99px;padding:2px 7px;font-size:10px;font-weight:700}.muted{color:var(--muted)}.source{font-size:12px;color:var(--muted)}footer{padding:8px 2px 32px;color:var(--muted);font-size:12px}.empty{text-align:center;padding:18px;color:var(--muted)}
@media(max-width:740px){.wrap{padding:15px}.leadgrid,.grid2{grid-template-columns:1fr}.card{padding:17px}.metrics{grid-template-columns:1fr 1fr}.componentrow{grid-template-columns:120px 1fr 90px}header{padding:30px 20px}.barrow{grid-template-columns:90px 1fr 55px}}@media(max-width:460px){.metrics{grid-template-columns:1fr 1fr}.mvalue{font-size:20px}.componentrow{grid-template-columns:1fr 1fr}.componentrow .stack{grid-column:1/-1;grid-row:2}}
</style></head>
<body>
<header><div class="eyebrow">FY 2027 · HB 10858 (HGAB) · Department of Health</div><h1>HFEP: repeated facility allocations</h1><p>A first-pass review of the Health Facilities Enhancement Program schedule. The lead pattern is a repeated ₱500,000 medical equipment allocation, mainly among barangay health stations. This is a screening result; the schedule and facility scope need source-page review.</p><p class="source-context">FY2027 source: HGAB. This page screens repeated allocations within the current House bill stage.</p><nav class="report-nav" aria-label="Budget report pages"><a href="dpwh.html">DPWH</a><a href="fmr.html">FMR</a><a href="nia.html">NIA</a><a href="hfep.html">HFEP</a></nav></header>
<main class="wrap">
<section class="card lead section"><div class="leadgrid"><div><div class="eyebrow" style="color:var(--teal-dark)">Repeated medical equipment amount</div><div class="big">₱500K</div><div class="biglabel"><span id="500count"></span> facility candidates</div><div class="bigsub"><span id="500bhs"></span> are barangay health stations</div></div><div><h2>What repeats</h2><p>All candidates at ₱500,000 show that amount in the medical equipment column, with no infrastructure or motor vehicle amount. <span id="500bhsNarrative"></span> This may reflect a standardized equipment package; compare the listed items, facility size, and service scope before judging whether equal allocations make sense.</p><div class="callout"><strong>Useful next check:</strong> compare the ₱500,000 bundle with the HFEP equipment list and see whether all of these stations receive the same equipment, quantity, and specifications.</div></div></div></section>

<section class="grid2 section"><article class="card"><h2>Most repeated total amounts</h2><p class="sub">Counts across facility candidates. Different totals can reflect different combinations of construction, equipment, and vehicles.</p><div class="bars" id="priceBars"></div></article><article class="card"><h2>Allocation counts by facility type</h2><p class="sub">Type labels are heuristic title categories. Use the source table to validate ambiguous names.</p><div class="bars" id="typeBars"></div></article></section>
<section class="card section"><h2>HFEP component allocation mix</h2><p class="sub">Extracted candidate amounts grouped by printed column. This shows whether repeated totals come from the same component or different funding mixes.</p><div class="legend"><span><i class="dot" style="background:#087e78"></i>Infrastructure</span><span><i class="dot" style="background:#5b88b5"></i>Medical equipment</span><span><i class="dot" style="background:#dda64d"></i>Motor vehicle</span></div><div class="component" id="componentBars"></div><p class="source" id="componentNote"></p></section>
<section class="card section"><h2>Largest facility allocations</h2><p class="sub">High amounts are review priorities, not automatic outliers: hospitals and major facilities can have substantially different scope.</p><div class="tablewrap"><table><thead><tr><th>Facility candidate</th><th class="num">Total</th><th class="num">Infrastructure</th><th class="num">Medical equipment</th><th class="num">Vehicle</th><th>PDF page</th></tr></thead><tbody id="largeBody"></tbody></table></div></section>
<section class="card section"><h2>HFEP facility candidate review</h2><p class="sub">Search names, nearby schedule context, or PDF page. Every row remains a candidate pending source review.</p><div class="toolbar"><input id="search" type="search" placeholder="Search facility, amount, source context, or page"><select id="sort"><option value="amount_desc">Largest amount</option><option value="amount_asc">Smallest amount</option><option value="page">PDF page</option><option value="title">Facility name</option></select></div><div class="tablewrap"><table><thead><tr><th>Facility candidate</th><th class="num">Total</th><th class="num">Infrastructure</th><th class="num">Medical equipment</th><th class="num">Vehicle</th><th>Page</th><th>Nearby source context</th></tr></thead><tbody id="projectBody"></tbody></table></div><div class="pager" id="pager"></div></section>
<footer><p><strong>Source:</strong> HB 10858, FY 2027, Volume I-B, Department of Health HFEP schedule, PDF pages 876–892. Values are in pesos. Candidate rows retain source page and nearby extracted text.</p><p>Generated from Ghostscript PDF text extraction and DuckDB candidate analyses. Rebuild with <code>python3 extract_hb_hfep_projects.py</code>, <code>python3 convert_hb_json_to_parquet.py hb10858_hfep_projects.json</code>, <code>python3 analyze_hb_agencies.py hb10858_agency_projects.parquet hb10858_nia_projects.parquet hb10858_hfep_projects.parquet</code>, then <code>python3 build_hfep_report.py</code>. This page embeds data and works without a server or external JavaScript.</p></footer>
<details class="section"><summary>Candidate total and printed grand total check</summary><p><span id="reconciliationStatus"></span> <span id="reconciliationDetail"></span> Candidate amount sum: <strong id="candidateSum"></strong>. Printed schedule grand total: <strong id="grandTotal"></strong>. Difference: <strong id="gapNote"></strong>. Exact reconciliation is a completeness check, not proof that every title is joined to the correct amount or rule. Verify a sample of rows against the printed pages before citing candidate totals.</p></details>
</main>
<script>
const D=__DATA__;
const peso=n=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP',maximumFractionDigits:0}).format(Number(n)||0);
const cellPeso=n=>n===null||n===undefined||n===''?'—':peso(n);
const compact=n=>new Intl.NumberFormat('en-PH',{notation:'compact',maximumFractionDigits:2}).format(Number(n)||0);
const num=n=>new Intl.NumberFormat('en-PH',{maximumFractionDigits:0}).format(Number(n)||0);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.getElementById('500count').textContent=num(D.at500k);document.getElementById('500bhs').textContent=num(D.at500kBhs);document.getElementById('500bhsNarrative').textContent=`${num(D.at500kBhs)} of ${num(D.at500k)} are barangay health stations.`;
document.getElementById('candidateSum').textContent='₱'+compact(D.candidateSum);document.getElementById('grandTotal').textContent='₱'+compact(D.grandTotal);document.getElementById('gapNote').textContent=D.gap===0?'Matches the printed grand total':`${D.gap>0?'Short by':'Over by'} ${peso(Math.abs(D.gap))} (${Math.abs(D.gapPct).toFixed(2)}% of printed total)`;
document.getElementById('reconciliationStatus').textContent=D.gap===0?'Candidate rows reconcile to the printed grand total.':`Candidate rows ${D.gap>0?'fall short of':'exceed'} the printed grand total.`;
document.getElementById('reconciliationDetail').textContent=`${num(D.candidateCount)} rows sum to ${peso(D.candidateSum)}; the printed total is ${peso(D.grandTotal)}.`;
function bars(id,items,label,value,fmt){const max=Math.max(1,...items.map(x=>Number(x[value])||0));document.getElementById(id).innerHTML=items.map(x=>`<div class="barrow"><div class="barname" title="${esc(x[label])}">${esc(x[label])}</div><div class="track"><div class="bar" style="width:${Math.max(1,100*(Number(x[value])||0)/max)}%"></div></div><div class="barvalue">${fmt?fmt(x[value]):num(x[value])}</div></div>`).join('')||'<div class="empty">No data available</div>'}
bars('priceBars',D.prices.slice(0,9).map(x=>({...x,label:peso(x.amountPesos),value:Number(x.facility_candidates)})),'label','value',v=>`${num(v)} sites`);
bars('typeBars',D.types.slice(0,9).map(x=>({...x,label:x.facility_type,value:Number(x.facility_candidates)})),'label','value',v=>`${num(v)} sites`);
const totals={i:D.componentTotals.infrastructure,m:D.componentTotals.medicalEquipment,v:D.componentTotals.motorVehicle};const grand=totals.i+totals.m+totals.v;
const componentRows=[['Infrastructure',totals.i,'seg-infra'],['Medical equipment',totals.m,'seg-med'],['Motor vehicle',totals.v,'seg-vehicle']];
document.getElementById('componentBars').innerHTML=componentRows.map(([label,val,cls])=>`<div class="componentrow"><span>${label}</span><div class="stack"><div class="${cls}" style="width:${grand?100*val/grand:0}%"></div></div><strong style="text-align:right">${peso(val)}</strong></div>`).join('');
document.getElementById('componentNote').textContent=`Across candidate rows: ${peso(totals.i)} infrastructure, ${peso(totals.m)} medical equipment, and ${peso(totals.v)} motor vehicle; ${num(D.componentMismatches)} rows have a component sum that differs from the extracted Total.`;
const sorted=[...D.candidates].sort((a,b)=>Number(b.amountPesos)-Number(a.amountPesos));document.getElementById('largeBody').innerHTML=sorted.slice(0,20).map(r=>`<tr><td class="title">${esc(r.projectName)}</td><td class="num">${peso(r.amountPesos)}</td><td class="num">${cellPeso(r.amountInfrastructurePesos)}</td><td class="num">${cellPeso(r.amountMedicalEquipmentPesos)}</td><td class="num">${cellPeso(r.amountMotorVehiclePesos)}</td><td>${esc(r.sourcePage)}</td></tr>`).join('');
const search=document.getElementById('search'),sort=document.getElementById('sort'),tbody=document.getElementById('projectBody'),pager=document.getElementById('pager');let page=0;const pageSize=30;
function draw(){const q=search.value.trim().toLowerCase();let list=D.candidates.filter(r=>`${r.projectName} ${r.amountPesos} ${r.sourcePage} ${r.sourceContext}`.toLowerCase().includes(q));list.sort((a,b)=>sort.value==='amount_asc'?Number(a.amountPesos)-Number(b.amountPesos):sort.value==='page'?Number(a.sourcePage)-Number(b.sourcePage):sort.value==='title'?a.projectName.localeCompare(b.projectName):Number(b.amountPesos)-Number(a.amountPesos));const pages=Math.max(1,Math.ceil(list.length/pageSize));page=Math.min(page,pages-1);const start=page*pageSize;tbody.innerHTML=list.slice(start,start+pageSize).map(r=>`<tr><td class="title">${esc(r.projectName)}</td><td class="num">${peso(r.amountPesos)}</td><td class="num">${cellPeso(r.amountInfrastructurePesos)}</td><td class="num">${cellPeso(r.amountMedicalEquipmentPesos)}</td><td class="num">${cellPeso(r.amountMotorVehiclePesos)}</td><td>${esc(r.sourcePage)}</td><td class="title muted">${esc(r.sourceContext)}</td></tr>`).join('')||'<tr><td colspan="7" class="empty">No matching facility candidates</td></tr>';pager.innerHTML=`<button ${page===0?'disabled':''} data-step="-1">Previous</button><span>${list.length?num(start+1):0}–${num(Math.min(start+pageSize,list.length))} of ${num(list.length)}</span><button ${page>=pages-1?'disabled':''} data-step="1">Next</button>`;pager.querySelectorAll('button').forEach(b=>b.onclick=()=>{page+=Number(b.dataset.step);draw()})}
search.oninput=()=>{page=0;draw()};sort.onchange=()=>{page=0;draw()};draw();
</script></body></html>'''.replace("__DATA__", data)

DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(fit_tables(html), encoding="utf-8")
print(f"Wrote standalone HFEP report: {DEST}")
