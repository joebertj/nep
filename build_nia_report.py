#!/usr/bin/env python3
"""Build a standalone NIA project schedule review page."""

import csv
import json
from pathlib import Path
from report_styles import fit_tables

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "hb10858_nia_projects.json"
DATA = ROOT / "analysis_output" / "hb_agencies"
DEST = ROOT / "analysis_output" / "nia.html"


def read_csv(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        raise SystemExit(f"Missing {path}; run analyze_hb_agencies.py with the NIA Parquet first.")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


payload = json.loads(SOURCE.read_text(encoding="utf-8"))
projects = payload["data"]["data"]
metadata = payload.get("metadata", {})
prices = read_csv("nia_amount_frequency.csv")
candidate_sum = sum(int(row["amountPesos"]) for row in projects)
printed_total = int(metadata.get("printedProjectSubtotalPesos", 10_655_321_000))
data = json.dumps({
    "projects": projects,
    "prices": prices,
    "count": len(projects),
    "candidateSum": candidate_sum,
    "printedTotal": printed_total,
    "gap": printed_total - candidate_sum,
}, ensure_ascii=False).replace("</", "<\\/")

html = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="NIA named irrigation project allocations in HB 10858, FY 2027.">
<title>Budget review · NIA (HB 10858 HGAB FY2027)</title>
<style>
:root{--ink:#172b3a;--muted:#637381;--paper:#f3f6f5;--card:#fff;--line:#dce4e1;--teal:#087e78;--teal-dark:#075c58;--mint:#dff3ee;--amber:#9a5a09;--amber-bg:#fff3dd;--blue:#315e83;--shadow:0 12px 32px #17323c0b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--blue)}header{background:#102f3e;color:#f4f7f6;padding:40px max(24px,calc((100vw - 1120px)/2)) 36px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:11px;color:#a7ddd1;font-weight:750}h1{font-size:clamp(32px,5vw,52px);letter-spacing:-.04em;line-height:1.03;margin:13px 0;max-width:900px}header p{color:#d4e1df;max-width:800px;margin:0;font-size:16px}.report-nav{display:flex;gap:16px;flex-wrap:wrap;margin-top:16px;font-size:13px}.report-nav a{color:#a7ddd1}.wrap{max-width:1120px;padding:24px;margin:auto}.section{margin:0 0 18px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:var(--shadow)}h2{font-size:22px;letter-spacing:-.025em;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin:0 0 17px}.lead{background:linear-gradient(135deg,#e5f5f1,#fff 72%);border-color:#c7e9e0}.leadgrid{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:center}.big{font-size:clamp(54px,9vw,88px);font-weight:820;letter-spacing:-.065em;line-height:1;color:var(--teal-dark)}.biglabel{font-size:19px;font-weight:740;margin-top:8px}.callout{background:var(--mint);border-left:4px solid var(--teal);border-radius:9px;padding:13px 15px;margin-top:14px}.warning{background:var(--amber-bg);border:1px solid #f1d8ad;color:#65440f;border-radius:11px;padding:14px 16px;margin:0 0 18px}.warning strong{color:#4e350e}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:20px}.metric{padding:14px 15px;background:#ffffffd9;border:1px solid var(--line);border-radius:12px}.mlabel{font-size:12px;color:var(--muted)}.mvalue{font-size:24px;line-height:1.2;font-weight:760;margin-top:4px;font-variant-numeric:tabular-nums}.mnote{font-size:11px;color:var(--muted);margin-top:4px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}.bars{display:grid;gap:10px}.barrow{display:grid;grid-template-columns:minmax(100px,1.3fr) 3fr 80px;gap:10px;align-items:center;font-size:13px}.barname{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.track{height:11px;background:#edf1ef;border-radius:9px;overflow:hidden}.bar{height:100%;background:var(--teal);border-radius:9px;min-width:2px}.barvalue{text-align:right;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;background:white;font-size:12px}th,td{padding:9px 11px;border-bottom:1px solid #e9eeec;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#f7faf8;color:#51626b;font-size:11px;z-index:1}td.num,th.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}td.title{min-width:330px;max-width:620px}.toolbar{display:flex;gap:9px;margin:13px 0;flex-wrap:wrap}.toolbar input,.toolbar select{border:1px solid var(--line);border-radius:9px;padding:10px 12px;font:inherit;background:white;color:var(--ink)}.toolbar input{min-width:min(340px,100%);flex:1}.pager{display:flex;justify-content:flex-end;align-items:center;gap:10px;color:var(--muted);font-size:12px;margin-top:10px}.pager button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 11px;cursor:pointer}.muted{color:var(--muted)}footer{padding:8px 2px 32px;color:var(--muted);font-size:12px}.empty{text-align:center;padding:18px;color:var(--muted)}
@media(max-width:740px){.wrap{padding:15px}.leadgrid,.grid2{grid-template-columns:1fr}.card{padding:17px}.metrics{grid-template-columns:1fr 1fr}header{padding:30px 20px}.barrow{grid-template-columns:90px 1fr 55px}}@media(max-width:460px){.metrics{grid-template-columns:1fr 1fr}.mvalue{font-size:20px}}
</style></head><body>
<header><div class="eyebrow">FY 2027 · HB 10858 (HGAB) · National Irrigation Administration</div><h1>NIA: named irrigation project allocations</h1><p>A schedule-level review of the named NIA projects, repeated printed amounts, and the subtotal reconciliation. Similar amounts are a screening clue; projects may differ in type, scale, stage, and scope.</p><p class="source-context">FY2027 source: HGAB. Repeat screen: FY2027 HGAB against available FY2025 GAA. FY2026 GAA line items are not in the local data.</p><nav class="report-nav" aria-label="Budget report pages"><a href="dpwh.html">DPWH</a><a href="fmr.html">FMR</a><a href="nia.html">NIA</a><a href="hfep.html">HFEP</a></nav></header>
<main class="wrap">
<section class="card lead section"><div class="leadgrid"><div><div class="eyebrow" style="color:var(--teal-dark)">Potential HGAB-to-GAA repeats</div><div class="big" id="repeatCount"></div><div class="biglabel">potential repeat matches</div><div class="bigsub"><span id="count"></span> named project candidates in the FY2027 HGAB schedule</div></div><div><h2>What this schedule supports</h2><p>These name-based candidates compare FY2027 HGAB lines with FY2025 enacted GAA lines. Similar names can describe different scopes or locations, so confirm project type, location, stage, and source line before treating them as repeats. FY2026 GAA line items are not available locally for this screen.</p><div class="callout"><strong>Use matching amounts as a sorting tool.</strong> Project titles alone do not establish that allocations fund the same scope.</div></div></div><div class="repeat-summary-slot"></div></section>
<!-- GENERATED YEAR-ON-YEAR REPEAT REVIEW -->
<section class="grid2 section"><article class="card"><h2>Most repeated printed amounts</h2><p class="sub">Counts of named project candidates at each exact amount. Identical amounts do not establish equal project size or unit cost.</p><div class="bars" id="amountBars"></div></article><article class="card"><h2>How to read the list</h2><p class="sub">Each row preserves the source page and nearby schedule text to help review its place in the hierarchy.</p><ul><li>Rows on pages 570 and 572 contain the extracted project titles; page 571 is a mirrored schedule layout.</li><li>Amounts are in pesos in the data files and report.</li><li>Project titles alone do not provide a reliable length, capacity, or cost-per-unit measure.</li></ul></article></section>
<details class="section"><summary>Schedule subtotal reconciliation</summary><p>The 32 named project candidate amounts sum to <strong id="candidateSum"></strong>; the printed <em>Total, Project(s)</em> subtotal on PDF page 572 is <strong id="printedTotal"></strong>. Difference: <strong id="gap"></strong>. The schedule also contains program and PAP summaries; these are not additional project rows. An exact sum is a completeness check, not independent verification of every title-to-amount pairing or project-level classification.</p></details>
<section class="card section"><h2>NIA project candidate review</h2><p class="sub">Search project names, amount, PDF page, or nearby source context. Use the source PDF to verify project scope and hierarchy.</p><div class="toolbar"><input id="search" type="search" placeholder="Search project, amount, context, or page"><select id="sort"><option value="amount_desc">Largest amount</option><option value="amount_asc">Smallest amount</option><option value="page">PDF page</option><option value="title">Project name</option></select></div><div class="tablewrap"><table><thead><tr><th>Project title candidate</th><th class="num">Amount</th><th>PDF page</th><th>Nearby source context</th><th>Review note</th></tr></thead><tbody id="body"></tbody></table></div><div class="pager" id="pager"></div></section>
<footer><p><strong>Source:</strong> HB 10858, FY 2027, Volume I-B, NIA project schedule, PDF pages 570–572. Candidate records retain source volume, page, and nearby text.</p><p>Generated from the NIA JSON and DuckDB amount-frequency output. Rebuild with <code>python3 extract_hb_nia_projects.py</code>, <code>python3 convert_hb_json_to_parquet.py hb10858_nia_projects.json</code>, <code>python3 analyze_hb_agencies.py hb10858_nia_projects.parquet</code>, then <code>python3 build_nia_report.py</code>. This standalone page embeds its data and needs no server or external JavaScript.</p></footer>
</main><script>
const D=__DATA__;
const peso=n=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP',maximumFractionDigits:0}).format(Number(n)||0);
const num=n=>new Intl.NumberFormat('en-PH',{maximumFractionDigits:0}).format(Number(n)||0);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.getElementById('count').textContent=num(D.count);
document.getElementById('candidateSum').textContent=peso(D.candidateSum);
document.getElementById('printedTotal').textContent=peso(D.printedTotal);
document.getElementById('gap').textContent=peso(D.candidateSum-D.printedTotal);
const max=Math.max(1,...D.prices.map(x=>Number(x.project_candidates)||0));
document.getElementById('amountBars').innerHTML=D.prices.slice(0,10).map(x=>{const n=Number(x.project_candidates)||0;return `<div class="barrow"><div class="barname">${peso(x.amountPesos)}</div><div class="track"><div class="bar" style="width:${100*n/max}%"></div></div><div class="barvalue">${num(n)} projects</div></div>`}).join('')||'<div class="empty">No amount frequency data</div>';
const search=document.getElementById('search'),sort=document.getElementById('sort'),body=document.getElementById('body'),pager=document.getElementById('pager');let page=0;const size=15;
function draw(){const q=search.value.trim().toLowerCase();let rows=D.projects.filter(r=>`${r.projectName} ${r.amountPesos} ${r.sourcePage} ${r.sourceContext} ${r.reviewNotes}`.toLowerCase().includes(q));rows.sort((a,b)=>sort.value==='amount_asc'?Number(a.amountPesos)-Number(b.amountPesos):sort.value==='page'?Number(a.sourcePage)-Number(b.sourcePage):sort.value==='title'?a.projectName.localeCompare(b.projectName):Number(b.amountPesos)-Number(a.amountPesos));const pages=Math.max(1,Math.ceil(rows.length/size));page=Math.min(page,pages-1);const start=page*size;body.innerHTML=rows.slice(start,start+size).map(r=>`<tr><td class="title">${esc(r.projectName)}</td><td class="num">${peso(r.amountPesos)}</td><td>${esc(r.sourcePage)}</td><td class="title muted">${esc(r.sourceContext)}</td><td>${esc((r.reviewNotes||[]).join('; '))}</td></tr>`).join('')||'<tr><td colspan="5" class="empty">No matching project candidates</td></tr>';pager.innerHTML=`<button ${page===0?'disabled':''} data-step="-1">Previous</button><span>${rows.length?num(start+1):0}–${num(Math.min(start+size,rows.length))} of ${num(rows.length)}</span><button ${page>=pages-1?'disabled':''} data-step="1">Next</button>`;pager.querySelectorAll('button').forEach(b=>b.onclick=()=>{page+=Number(b.dataset.step);draw()})}
search.oninput=()=>{page=0;draw()};sort.onchange=()=>{page=0;draw()};draw();
</script></body></html>'''.replace("__DATA__", data)

DEST.parent.mkdir(parents=True, exist_ok=True)
DEST.write_text(fit_tables(html), encoding="utf-8")
print(f"Wrote standalone NIA report: {DEST}")
