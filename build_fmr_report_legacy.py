#!/usr/bin/env python3
"""Build a standalone FMR-focused HTML review page from DuckDB CSV outputs."""

import csv
import json
from pathlib import Path
from report_styles import fit_tables

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "analysis_output" / "hb_agencies"
DEST = ROOT / "analysis_output" / "fmr.html"


def rows(name: str) -> list[dict]:
    path = DATA / name
    if not path.exists():
        raise SystemExit(f"Missing {path}; run analyze_hb_agencies.py hb10858_agency_projects.parquet first.")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def integer(row: dict, key: str) -> int:
    try:
        return int(float(row.get(key) or 0))
    except ValueError:
        return 0


def json_for_script(value) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


prices = rows("fmr_amount_frequency.csv")
provinces = rows("fmr_province_allocations.csv")
locations = rows("fmr_location_repeated_allocations.csv")
projects = rows("hb_project_candidates.csv")
projects = [r for r in projects if r.get("program") == "Farm-to-Market Roads"]
flags = rows("fmr_flagged_rows.csv")
chainage = rows("fmr_chainage_unit_cost.csv")
summary = rows("hb_agency_totals.csv")
summary = next((r for r in summary if r["program"] == "Farm-to-Market Roads"), {})
top_price = next((r for r in prices if integer(r, "amountPesos") == 15_000_000), {})
candidate_count = integer(summary, "projects")
amount_review = integer(summary, "amount_cell_review_rows")
hierarchy_review = integer(summary, "hierarchy_review_rows")
included_count = candidate_count - amount_review

embedded = {
    "prices": prices,
    "provinces": provinces,
    "locations": locations,
    "projects": projects,
    "flags": flags,
    "chainage": chainage,
    "candidateCount": candidate_count,
    "amountReview": amount_review,
    "hierarchyReview": hierarchy_review,
    "includedCount": included_count,
    "at15m": integer(top_price, "project_candidates"),
    "at15mShare": float(top_price.get("share_of_unflagged_pct") or 0),
    "at15mLocations": integer(top_price, "distinct_location_hints"),
}
data = json_for_script(embedded)

html = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="A focused review of Farm-to-Market Road allocations in HB 10858, FY 2027.">
<title>Budget review · FMR (HB 10858 HGAB FY2027)</title>
<style>
:root{--ink:#172b3a;--muted:#637381;--paper:#f3f6f5;--card:#fff;--line:#dce4e1;--teal:#087e78;--teal-dark:#075c58;--teal-light:#dff3ee;--amber:#9a5a09;--amber-light:#fff3dd;--blue:#315e83;--shadow:0 12px 32px #17323c0b}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:#102f3e;color:#f4f7f6;padding:42px max(24px,calc((100vw - 1160px)/2)) 38px}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:11px;color:#a7ddd1;font-weight:750}h1{font-size:clamp(32px,5vw,54px);letter-spacing:-.04em;line-height:1.02;margin:14px 0 14px;max-width:850px}header p{color:#d4e1df;max-width:760px;font-size:16px;margin:0}.wrap{max-width:1160px;margin:auto;padding:24px}.section{margin:0 0 18px}.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px;box-shadow:var(--shadow)}h2{font-size:22px;letter-spacing:-.025em;margin:0 0 4px}.sub{color:var(--muted);font-size:13px;margin:0 0 17px}.lead{background:linear-gradient(135deg,#e5f5f1,#fff 72%);border-color:#c7e9e0}.lead-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;align-items:center}.big{font-size:clamp(54px,8vw,82px);font-weight:800;letter-spacing:-.06em;line-height:1;color:var(--teal-dark)}.big-label{font-size:19px;font-weight:700;margin-top:8px}.big-note{color:var(--muted);font-size:13px;margin-top:8px}.callout{background:var(--teal-light);border-left:4px solid var(--teal);border-radius:9px;padding:13px 15px;margin-top:16px}.warning{background:var(--amber-light);border:1px solid #f1d8ad;color:#65440f;border-radius:11px;padding:14px 16px;margin:0 0 18px}.warning strong{color:#4e350e}.metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}.metric{padding:15px 16px;background:#ffffffd9;border:1px solid var(--line);border-radius:12px}.metric-label{font-size:12px;color:var(--muted)}.metric-value{font-weight:760;font-size:25px;line-height:1.2;margin-top:4px;font-variant-numeric:tabular-nums}.metric-note{font-size:11px;color:var(--muted);margin-top:4px}.columns{display:grid;grid-template-columns:1.05fr .95fr;gap:18px}.bars{display:grid;gap:11px}.barrow{display:grid;grid-template-columns:minmax(88px,1.2fr) 3fr 64px;gap:10px;align-items:center;font-size:13px}.barname{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.track{height:11px;border-radius:9px;background:#edf1ef;overflow:hidden}.bar{height:100%;background:var(--teal);border-radius:9px;min-width:2px}.barvalue{text-align:right;font-variant-numeric:tabular-nums;color:var(--muted);white-space:nowrap}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px}table{border-collapse:collapse;width:100%;background:#fff;font-size:12px}th,td{text-align:left;padding:9px 11px;border-bottom:1px solid #e9eeec;vertical-align:top}th{position:sticky;top:0;background:#f7faf8;color:#51626b;font-size:11px;z-index:1}td.num,th.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}td.title{min-width:310px;max-width:560px}.toolbar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin:14px 0}.toolbar input,.toolbar select{border:1px solid var(--line);border-radius:9px;padding:10px 12px;font:inherit;background:white;color:var(--ink)}.toolbar input{min-width:min(340px,100%);flex:1}.toolbar button,.pager button{border:1px solid var(--line);background:#fff;border-radius:8px;padding:7px 11px;font:inherit;cursor:pointer;color:var(--ink)}.toolbar button:hover,.pager button:hover{border-color:var(--teal);color:var(--teal)}.pager{display:flex;justify-content:flex-end;align-items:center;gap:10px;color:var(--muted);font-size:12px;margin-top:10px}.tag{display:inline-block;background:var(--amber-light);color:var(--amber);border-radius:99px;padding:2px 7px;font-size:10px;font-weight:700}.muted{color:var(--muted)}.source{font-size:12px;color:var(--muted)}a{color:var(--blue)}footer{padding:8px 2px 32px;color:var(--muted);font-size:12px}.empty{text-align:center;padding:20px;color:var(--muted)}
@media(max-width:760px){.wrap{padding:15px}.lead-grid,.columns{grid-template-columns:1fr}.card{padding:17px}.metrics{grid-template-columns:1fr 1fr}header{padding:30px 20px}.barrow{grid-template-columns:90px 1fr 55px}}@media(max-width:440px){.metrics{grid-template-columns:1fr 1fr}.metric-value{font-size:21px}}.report-nav{display:flex;gap:16px;flex-wrap:wrap;margin-top:16px;font-size:13px}.report-nav a{color:#a7ddd1}
</style>
</head>
<body>
<header><div class="eyebrow">FY 2027 · HB 10858 (HGAB) · Department of Agriculture</div><h1>FMR: Farm-to-Market Roads and the ₱15 million pattern</h1><p>A focused look at listed FMR allocations, repeated amounts, and location clusters. This page is a screening aid built from PDF text extraction, not a verified list of additions or a finding of improper spending.</p><p class="source-context">FY2027 source: HGAB. Repeat screen: FY2027 HGAB against available FY2025 GAA. FY2026 GAA line items are not in the local data.</p><nav class="report-nav" aria-label="Budget report pages"><a href="dpwh.html">DPWH</a><a href="fmr.html">FMR</a><a href="nia.html">NIA</a><a href="hfep.html">HFEP</a></nav></header>
<main class="wrap">
<section class="card lead section">
  <div class="lead-grid"><div><div class="eyebrow" style="color:var(--teal-dark)">Opening pattern · same printed allocation</div><div class="big">₱15M</div><div class="big-label">appears in 364 FMR candidates</div><div class="big-note">48.2% of the 755 candidates without low-amount extraction flags; spread across 249 distinct title-based location hints.</div></div>
  <div><h2>What the pattern says</h2><p>Many FMR entries have the same listed amount across different place names. That makes ₱15 million a useful first review group. A few schedule entries provide STA chainage, which gives a direct length by subtraction. Only two usable start/end chainage pairs were found in this pass, so length-adjusted comparisons are still a small review sample.</p><div class="callout"><strong>Keep the hierarchy in view</strong>Some nearby lines are PAP labels or summaries rather than project-level allocations. Check each row and amount against its cited PDF page before counting it as an individual project or an HB addition.</div></div></div>
  <div class="repeat-summary-slot"></div>
</section>
<!-- GENERATED YEAR-ON-YEAR REPEAT REVIEW -->
<div class="warning"><strong>Candidate data, not confirmed project rows.</strong> Amounts are extracted from an aligned PDF table. The title hierarchy can mix PAPs, subtotals, and projects. Forty low amount cells are held out of the frequency denominator; four large allocations remain included but are marked for hierarchy review. Candidate sums should not be presented as final program totals.</div>
<section class="grid columns section">
 <article class="card"><h2>Most common printed amounts</h2><p class="sub">Counts among rows without low-amount flags. Bar length shows the share of that subset.</p><div class="bars" id="priceBars"></div></article>
 <article class="card"><h2>Allocation concentration by province hint</h2><p class="sub">Place suffix inferred from project title; displayed for triage, not a verified geography join.</p><div class="bars" id="provinceBars"></div></article>
</section>
<section class="card section"><h2>Same place hint, repeated amount</h2><p class="sub">Rows sharing the same final city/province text and amount. These clusters help prioritize checking project scope and the source table.</p><div class="table-wrap"><table><thead><tr><th>Title-derived location hint</th><th class="num">Amount</th><th class="num">Candidate count</th><th>Project title examples</th></tr></thead><tbody id="locationBody"></tbody></table></div></section>
<section class="card section"><h2>Length check from printed STA chainage</h2><p class="sub">For rows with two explicit station values, the listed length is the absolute difference in metres. Allocation per kilometre is amount divided by that stated length. This is more useful for size comparison than straight-line endpoint distance, but the PDF row and scope still need verification.</p><div class="table-wrap"><table><thead><tr><th>Project title candidate</th><th class="num">Allocation</th><th class="num">Start STA (m)</th><th class="num">End STA (m)</th><th class="num">Length (m)</th><th class="num">Amount per km</th><th>PDF page</th></tr></thead><tbody id="chainageBody"></tbody></table></div><div class="callout"><strong>Small sample: <span id="chainageCount"></span> candidates with paired STA values.</strong> Treat these as a way to validate the length-based workflow, not as a representative cost benchmark for all FMR projects.</div></section>
<section class="card section"><h2>Province allocation table</h2><p class="sub">Candidate counts and amount summaries using the final two comma-separated title components as location hints. Provinces with fewer than five parsed candidates are omitted here.</p><div class="table-wrap"><table><thead><tr><th>Province hint</th><th class="num">Candidates</th><th class="num">Candidate total*</th><th class="num">Median amount</th><th class="num">At ₱15M</th><th class="num">Share at ₱15M</th></tr></thead><tbody id="provinceBody"></tbody></table></div><p class="source">*The total is a sum of extracted candidates, not an audited program total.</p></section>
<section class="card section"><h2>Project candidate review list</h2><p class="sub">Search titles, place names, source context, or PDF pages. The source context helps distinguish a project line from neighboring hierarchy labels and summary rows.</p><div class="toolbar"><input id="projectSearch" type="search" placeholder="Search project title, place, context, or page"><select id="projectSort"><option value="amount_desc">Largest amount</option><option value="amount_asc">Smallest amount</option><option value="page">PDF page</option><option value="title">Project title</option></select></div><div class="table-wrap"><table><thead><tr><th>Project title candidate</th><th class="num">Amount</th><th>PDF page</th><th>Review</th><th>Nearby source context</th></tr></thead><tbody id="projectBody"></tbody></table></div><div class="pager" id="projectPager"></div></section>
<section class="card section"><h2>Amount and coordinate review</h2><div class="columns"><div><h3>Amount review rows</h3><p class="sub">The extractor marks amounts below ₱1 million for cell-level checking. Larger allocations are retained, with a hierarchy note when above ₱60 million; these may still be valid project amounts.</p><div class="table-wrap"><table><thead><tr><th class="num">Amount</th><th>Project title candidate</th><th>Page</th></tr></thead><tbody id="flagBody"></tbody></table></div></div><div><h3>Straight-line endpoints</h3><p class="sub">The PDF includes endpoint coordinates for many rows. Parsed coordinates yield a straight-line distance, which is not the road's built length. Twenty-three unflagged endpoint pairs fall outside the rough 0.1–10 km review band. Verify coordinates and project scope before using any cost-per-kilometer comparison.</p><p class="sub">The companion CSV <code>fmr_unit_cost_candidates.csv</code> is a review queue only. The explicit STA pairs above provide the stronger size measure where present.</p></div></div></section>
<footer><p><strong>Source:</strong> HB 10858, FY 2027, Volume I-B, Department of Agriculture Farm-to-Market Roads schedule. Extraction uses Ghostscript text and PDF coordinates. Candidate rows retain volume/page and nearby text context.</p><p>Analysis generated with DuckDB. Rebuild with <code>python3 analyze_hb_agencies.py hb10858_agency_projects.parquet</code> followed by <code>python3 build_fmr_report.py</code>. This page embeds its data and needs no server or external JavaScript.</p></footer>
</main>
<script>
const D=__DATA__;
const peso=n=>new Intl.NumberFormat('en-PH',{style:'currency',currency:'PHP',maximumFractionDigits:0}).format(Number(n)||0);
const num=n=>new Intl.NumberFormat('en-PH',{maximumFractionDigits:0}).format(Number(n)||0);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
document.getElementById('mCandidates').textContent=num(D.candidateCount);
document.getElementById('mAmountReview').textContent=num(D.amountReview);
document.getElementById('mHierarchyReview').textContent=num(D.hierarchyReview);
function bars(target,items,label,value,formatter){const max=Math.max(1,...items.map(x=>Number(x[value])||0));document.getElementById(target).innerHTML=items.map(x=>`<div class="barrow"><div class="barname" title="${esc(x[label])}">${esc(x[label])}</div><div class="track"><div class="bar" style="width:${Math.max(1,100*(Number(x[value])||0)/max)}%"></div></div><div class="barvalue">${formatter?formatter(x[value]):num(x[value])}</div></div>`).join('')||'<div class="empty">No rows available</div>'}
bars('priceBars',D.prices.slice(0,8).map(x=>({...x,label:peso(x.amountPesos),value:Number(x.project_candidates)})),'label','value',v=>`${num(v)} rows`);
bars('provinceBars',D.provinces.slice(0,9).map(x=>({...x,label:x.province_hint,value:Number(x.project_candidates)})),'label','value',v=>`${num(v)} rows`);
document.getElementById('locationBody').innerHTML=D.locations.slice(0,30).map(r=>`<tr><td>${esc(r.location_hint)}</td><td class="num">${peso(r.amountPesos)}</td><td class="num">${num(r.project_candidates)}</td><td class="title">${esc(r.project_examples)}</td></tr>`).join('')||'<tr><td colspan="4" class="empty">No repeated location groups</td></tr>';
document.getElementById('provinceBody').innerHTML=D.provinces.slice(0,35).map(r=>`<tr><td>${esc(r.province_hint)}</td><td class="num">${num(r.project_candidates)}</td><td class="num">${peso(r.candidate_total_pesos)}</td><td class="num">${peso(r.median_candidate_pesos)}</td><td class="num">${num(r.candidates_at_15m)}</td><td class="num">${Number(r.pct_at_15m).toFixed(1)}%</td></tr>`).join('');
document.getElementById('flagBody').innerHTML=D.flags.slice(0,50).map(r=>`<tr><td class="num">${peso(r.amountPesos)}</td><td class="title">${esc(r.projectName)}</td><td>${esc(r.sourcePage)}</td></tr>`).join('')||'<tr><td colspan="3" class="empty">No amount review rows</td></tr>';
document.getElementById('chainageCount').textContent=num(D.chainage.length);
document.getElementById('chainageBody').innerHTML=D.chainage.map(r=>`<tr><td class="title">${esc(r.projectName)}</td><td class="num">${peso(r.amountPesos)}</td><td class="num">${num(r.chainageStartMeters)}</td><td class="num">${num(r.chainageEndMeters)}</td><td class="num">${num(r.chainageDistanceMeters)}</td><td class="num">${peso(r.pesosPerChainageKm)}</td><td>${esc(r.sourcePage)}</td></tr>`).join('')||'<tr><td colspan="7" class="empty">No paired stationing rows found</td></tr>';
const search=document.getElementById('projectSearch'),sort=document.getElementById('projectSort'),tbody=document.getElementById('projectBody'),pager=document.getElementById('projectPager');let page=0;const pageSize=25;
function drawProjects(){const q=search.value.trim().toLowerCase();let list=D.projects.filter(r=>`${r.projectName} ${r.sourcePage} ${r.sourceContext} ${r.screeningFlags} ${r.reviewNotes}`.toLowerCase().includes(q));list.sort((a,b)=>sort.value==='amount_asc'?Number(a.amountPesos)-Number(b.amountPesos):sort.value==='page'?Number(a.sourcePage)-Number(b.sourcePage):sort.value==='title'?a.projectName.localeCompare(b.projectName):Number(b.amountPesos)-Number(a.amountPesos));const pages=Math.max(1,Math.ceil(list.length/pageSize));page=Math.min(page,pages-1);const slice=list.slice(page*pageSize,(page+1)*pageSize);tbody.innerHTML=slice.map(r=>{const flagged=String(r.screeningFlags||'[]')!=='[]';const hierarchy=String(r.reviewNotes||'[]')!=='[]';const tags=[flagged?'Amount check':'',hierarchy?'Hierarchy check':''].filter(Boolean).map(t=>`<span class="tag">${esc(t)}</span>`).join(' ');return `<tr><td class="title">${esc(r.projectName)}</td><td class="num">${peso(r.amountPesos)}</td><td>${esc(r.sourcePage)}</td><td>${tags||'<span class="muted">Review source row</span>'}</td><td class="title muted">${esc(r.sourceContext)}</td></tr>`}).join('')||'<tr><td colspan="5" class="empty">No matching candidates</td></tr>';pager.innerHTML=`<button ${page===0?'disabled':''} data-step="-1">Previous</button><span>${list.length?num(page*pageSize+1):0}–${num(Math.min((page+1)*pageSize,list.length))} of ${num(list.length)}</span><button ${page>=pages-1?'disabled':''} data-step="1">Next</button>`;pager.querySelectorAll('button').forEach(b=>b.onclick=()=>{page+=Number(b.dataset.step);drawProjects()})}
search.oninput=()=>{page=0;drawProjects()};sort.onchange=()=>{page=0;drawProjects()};drawProjects();
</script>
</body></html>'''.replace("__DATA__", data)

DEST.write_text(fit_tables(html), encoding="utf-8")
print(f"Wrote standalone FMR report: {DEST}")
