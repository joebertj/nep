#!/usr/bin/env python3
"""Compare FY2027 HGAB FMR and NIA candidates with available prior GAAs.

Reads only local workspace data. Requires the DuckDB command-line client for
the parquet sources in open-data-visualization/data/parquet.
"""

import csv
import html
import io
import json
import re
import subprocess
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote
from chainage import compare_chainage, compare_tranche, has_directional_conflict

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
OUT = ROOT / "analysis_output"
MARKER = "<!-- GENERATED YEAR-ON-YEAR REPEAT REVIEW -->"
END_MARKER = "<!-- END GENERATED YEAR-ON-YEAR REPEAT REVIEW -->"


def duckdb_rows(sql: str) -> list[dict]:
    result = subprocess.run(
        ["duckdb", "-json", "-c", sql], cwd=ODV, text=True,
        capture_output=True, check=True,
    )
    return json.loads(result.stdout or "[]")


def load_json_rows(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))["data"]
    return data.get("data", []) if isinstance(data, dict) else data


def normalize(value: str) -> str:
    text = (value or "").upper().replace("&", " AND ")
    text = re.sub(r"\b(PHASE|PH)\s*(I{1,3}|IV|V|[0-9]+)\b", r" PHASE \1 ", text)
    text = re.sub(r"\b(BRGY|BARANGAY)\b", " BARANGAY ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def fields(row: dict, year: int, kind: str) -> dict:
    if year == 2027:
        name = row.get("projectName", row.get("name", ""))
        amount = row.get("amountPesos")
        if amount is None:
            amount = float(row.get("amount") or 0) * 1000
        source = f"HB 10858 Vol I-B p. {row.get('sourcePage', '')}".strip()
    elif year == 2026:
        name = row.get("name") or row.get("revised_name") or row.get("description") or ""
        amount = row.get("amount") or 0
        source = f"{row.get('source_sheet', '')} row {row.get('source_row', '')}".strip()
    else:
        name = row.get("description", "")
        amount = (row.get("amount") or 0) * 1000  # GAA parquet stores thousands of pesos.
        source = f"GAA-2025 · {row.get('department_desc', '')} · {row.get('agency_desc', '')}"
    line_id = str(row.get("code") or row.get("id") or f"{source} · {name} · {amount}") if year == 2027 else ""
    return {"year": year, "kind": kind, "name": str(name).replace("\n", " ").strip(),
            "amount": round(float(amount or 0)), "source": source, "line_id": line_id}


def similarity(left: str, right: str) -> float:
    stop = {"PROJECT", "IRRIGATION", "SYSTEM", "CONSTRUCTION", "CONCRETING",
            "ROAD", "FARM", "MARKET", "REHABILITATION", "PHASE", "BRGY",
            "BARANGAY", "EXTENSION", "IMPROVEMENT", "PROPOSED", "REPAIR",
            "CANAL", "WORKS", "AND", "OF", "THE", "IN", "AT", "FOR"}
    a = " ".join(w for w in normalize(left).split() if w not in stop)
    b = " ".join(w for w in normalize(right).split() if w not in stop)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    wa, wb = set(a.split()), set(b.split())
    jac = len(wa & wb) / len(wa | wb) if wa | wb else 0
    # Sequence similarity rewards preserved ordering; token overlap tolerates
    # punctuation and inserted location qualifiers.
    return max(seq, jac * 0.94)


def matches(targets: list[dict], previous: list[dict]) -> list[dict]:
    result = []
    stop = {"PROJECT", "IRRIGATION", "SYSTEM", "CONSTRUCTION", "CONCRETING",
            "ROAD", "FARM", "MARKET", "REHABILITATION", "PHASE", "BRGY",
            "BARANGAY", "EXTENSION", "IMPROVEMENT", "PROPOSED", "REPAIR",
            "CANAL", "WORKS", "AND", "OF", "THE", "IN", "AT", "FOR"}
    previous_tokens = [set(normalize(old["name"]).split()) - stop for old in previous]
    for current in targets:
        current_tokens = set(normalize(current["name"]).split()) - stop
        rough = []
        for old, tokens in zip(previous, previous_tokens):
            # Opposite explicit regional directions are a strong location
            # conflict across FMR and NIA title comparisons.
            if has_directional_conflict(current["name"], old["name"]):
                continue
            chainage = compare_chainage(current["name"], old["name"])
            # Exclude disjoint extents when both lines state ranges. A single
            # station or missing range remains a review lead with its status shown.
            if chainage["has_current_range"] and chainage["has_prior_range"] and not chainage["overlaps"]:
                continue
            tranche = compare_tranche(current["name"], old["name"])
            union = current_tokens | tokens
            score = len(current_tokens & tokens) / len(union) if union else 0
            rough.append((score, old, chainage, tranche))
        # Token overlap cheaply narrows the search; SequenceMatcher is then
        # applied only to plausible title candidates.
        shortlist = sorted(rough, key=lambda x: x[0], reverse=True)[:30]
        ranked = sorted(((similarity(current["name"], old["name"]), old, chainage, tranche)
                         for _, old, chainage, tranche in shortlist), key=lambda x: x[0], reverse=True)
        for rank, (score, old, chainage, tranche) in enumerate(ranked[:3], 1):
            result.append({**current, "prior_year": old["year"], "prior_name": old["name"],
                           "prior_amount": old["amount"], "prior_source": old["source"],
                           "similarity": round(score, 3), "rank": rank,
                           "amount_difference": current["amount"] - old["amount"], **chainage, **tranche})
    return result


def esc(value) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def peso(value) -> str:
    return "₱" + f"{int(value or 0):,}"


REPORT_TABLE_CSV_HELPER = r'''<style>
.comparison-graphic{margin:14px 0 18px;padding:14px 16px;border:1px solid #dce4e1;border-radius:10px;background:#f8fbf9}.comparison-graphic figcaption{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:12px}.comparison-graphic figcaption span{font-size:12px;color:#637381}.compare-row{display:grid;grid-template-columns:minmax(190px,260px) 1fr;gap:12px;align-items:center;margin:7px 0;font-size:12px}.compare-track{height:13px;background:#e5eeeb;border-radius:9px;overflow:hidden}.compare-track i{display:block;height:100%;background:#087e78;border-radius:9px}.compare-track.candidate i{background:#dda64d}.export-btn{border:1px solid #cbd8d3;border-radius:8px;padding:8px 11px;background:#fff;color:#172b3a;cursor:pointer;font:inherit;font-size:12px;font-weight:650}.export-btn:hover{background:#eef7f4}@media(max-width:650px){.compare-row{grid-template-columns:1fr;gap:5px}}
</style><script>
window.downloadReportTable=function(id,filename){
 const table=document.getElementById(id);if(!table)return;
 const rows=[...table.querySelectorAll('thead tr,tbody tr')].map(tr=>[...tr.children].map(td=>td.innerText.trim()));
 const csv=rows.map(row=>row.map(value=>'"'+String(value).replace(/"/g,'""')+'"').join(',')).join('\r\n');
 const link=document.createElement('a');link.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));link.download=filename;link.click();URL.revokeObjectURL(link.href);
};
window.downloadNiaCandidatesCsv=function(){
 const rows=D.projects.map(r=>[r.projectName,r.amountPesos,r.sourcePage,r.sourceContext,r.rowType,r.reviewNotes]);
 const values=[['Project title candidate','Amount (pesos)','PDF page','Nearby source context','Row type','Review notes'],...rows];
 const csv=values.map(row=>row.map(v=>'"'+String(Array.isArray(v)?v.join('; '):(v??'')).replace(/"/g,'""')+'"').join(',')).join('\r\n');
 const link=document.createElement('a');link.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));link.download='nia_hgab_project_candidates.csv';link.click();URL.revokeObjectURL(link.href);
};
</script>'''


def render_section(kind: str, comparisons: list[dict]) -> str:
    # Show one best FY2025 GAA candidate per 2027 HGAB row. FY2026 committee
    # amendment schedules are HGAB-stage data, not enacted GAA, so they are
    # deliberately excluded from this comparison.
    best = {}
    for row in comparisons:
        threshold = 0.90
        if row["similarity"] < threshold:
            continue
        key = (row.get("line_id") or row["name"], row["prior_year"])
        if key not in best or row["similarity"] > best[key]["similarity"]:
            best[key] = row
    by_year = {}
    for year in (2025,):
        year_rows = [r for r in best.values() if r["prior_year"] == year]
        by_year[year] = sorted(year_rows, key=lambda r: (-r["similarity"], r["name"]))
    eligible = {2025: by_year[2025]}
    ordered = eligible[2025][:200]
    unique_targets = {}
    prior_total = 0
    for row in eligible[2025]:
        target_id = row.get("line_id") or row["name"]
        unique_targets.setdefault(target_id, row["amount"])
        prior_total += row["prior_amount"]
    comparison_count = len(eligible[2025])
    fy2027_total = sum(unique_targets.values())
    insertion_summary = json.loads((OUT / "hgab_non_dpwh_insertion_summary.json").read_text(encoding="utf-8"))
    if kind == "fmr":
        insertion = insertion_summary["FMR"]
        insertion_label = "HGAB FMR titles not separately named in NEP"
        insertion_value = f"{insertion['hgabCandidateCount']:,} lines"
        insertion_note = (
            f"₱{insertion['hgabCandidateAmountPesos'] / 1_000_000_000:,.2f}B candidate amount within "
            f"₱{insertion['nepRegionalCapitalEnvelopePesos'] / 1_000_000_000:,.2f}B regional NEP envelope; "
            "itemization is not automatically additional spending"
        )
    else:
        insertion = insertion_summary["NIA"]
        with (OUT / "hgab_non_dpwh_insertion_candidates.csv").open(encoding="utf-8", newline="") as stream:
            insertion_rows = [
                row for row in csv.DictReader(stream)
                if row["family"] == "NIA irrigation" and row["comparison"].startswith("Potential insertion")
            ]
        insertion_count = len(insertion_rows)
        insertion_amount = sum(int(row["hb_amount_pesos"] or 0) for row in insertion_rows)
        insertion_label = "Potential NEP-to-HGAB named project insertions"
        insertion_value = f"{insertion_count:,} · ₱{insertion_amount / 1_000_000_000:,.2f}B"
        insertion_note = (
            f"{insertion['comparisonCounts'].get('Named in NEP; compare amount and scope', 0)} of "
            f"{insertion['hgabCandidateCount']} HGAB candidates have exact NEP title matches; "
            "no close named NEP counterpart for the remaining lines"
        )
    summary_html = f'''<div class="repeat-summary metrics"><div class="metric"><div class="mlabel">Potential HGAB-to-GAA repeat matches</div><div class="mvalue">{comparison_count:,}</div><div class="mnote">FY2027 HGAB lines with a high title match in FY2025 GAA</div></div><div class="metric"><div class="mlabel">FY2027 HGAB allocation on matched lines</div><div class="mvalue">₱{fy2027_total / 1_000_000_000:,.2f}B</div><div class="mnote">Screened allocation, not confirmed duplicate cost</div></div><div class="metric"><div class="mlabel">Matched FY2025 GAA allocations</div><div class="mvalue">₱{prior_total / 1_000_000_000:,.2f}B</div><div class="mnote">FY2025 enacted GAA comparison</div></div><div class="metric"><div class="mlabel">{esc(insertion_label)}</div><div class="mvalue">{esc(insertion_value)}</div><div class="mnote">{esc(insertion_note)}</div></div><div class="metric"><div class="mlabel">FY2026 GAA source</div><div class="mvalue">Unavailable</div><div class="mnote">Not present locally for this agency schedule</div></div></div>'''
    rows = "".join(
        "<tr><td>{}</td><td class='num'>{}</td><td>{}</td><td>{}</td>"
        "<td>{}</td><td>{}</td><td>{}</td><td class='num'>{}</td><td class='num'>{}</td>"
        "<td class='num'>{}%</td><td>{}</td></tr>".format(
            esc(r["name"]), peso(r["amount"]), r["year"], esc(r["prior_name"]),
            esc(r["current_chainage"]), esc(r["prior_chainage"]),
            esc((f"Overlap: {r['chainage_overlap']}" if r["chainage_status"] == "overlap" else r["chainage_status"])
                + (f" · Tranche split (50/50): {r['tranche_detail']}"
                   if r["tranche_status"] in {"different tranche", "different marker type"}
                   else f" · Tranche info: {r['tranche_detail']}" if r["tranche_status"] == "one side stated" else "")),
            peso(r["prior_amount"]), ("+" if r["amount_difference"] > 0 else "") + peso(r["amount_difference"]),
            round(r["similarity"] * 100), esc(r["prior_source"]))
        for r in ordered
    )
    title = "FMR" if kind == "fmr" else "NIA irrigation"
    csv_columns = ["kind", "year", "line_id", "name", "amount", "prior_year", "prior_name",
                   "prior_amount", "similarity", "rank", "amount_difference", "source", "prior_source",
                   "current_chainage", "prior_chainage", "chainage_overlap", "chainage_status",
                   "tranche_status", "tranche_detail", "tranche_conflict"]
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=csv_columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(comparisons)
    csv_href = "data:text/csv;charset=utf-8," + quote(csv_buffer.getvalue(), safe="")
    explain = ("FY2027 DA FMR candidates from HGAB against available FY2025 enacted GAA lines."
               if kind == "fmr" else
               "FY2027 named NIA project candidates from HGAB against available FY2025 enacted GAA NIA lines.")
    insertion_context = (
        f'''<div class="callout"><strong>NEP-to-HGAB line-item screen:</strong> the FY2027 NEP lists regional FMR capital envelopes totaling ₱{insertion_summary["FMR"]["nepRegionalCapitalEnvelopePesos"] / 1_000_000_000:,.2f}B. HB 10858 names {insertion_summary["FMR"]["hgabCandidateCount"]:,} local FMR candidate lines totaling ₱{insertion_summary["FMR"]["hgabCandidateAmountPesos"] / 1_000_000_000:,.2f}B. These titles are not separately itemized in the NEP, but may be allocated under that envelope; this screen does not count them as additional money.</div>'''
        if kind == "fmr" else
        ""
    )
    insertion_table = ""
    if kind == "fmr":
        with (OUT / "hgab_non_dpwh_insertion_candidates.csv").open(encoding="utf-8", newline="") as stream:
            fmr_insertion_rows = [row for row in csv.DictReader(stream) if row["family"] == "FMR"]
        insertion_data = json.dumps([
            {"name": row["hb_project"], "amount": int(row["hb_amount_pesos"] or 0),
             "page": row["source_page"], "context": row["source_context"]}
            for row in fmr_insertion_rows
        ], ensure_ascii=False).replace("</", "<\\/")
        envelope = insertion_summary["FMR"]["nepRegionalCapitalEnvelopePesos"]
        hb_total = insertion_summary["FMR"]["hgabCandidateAmountPesos"]
        ratio = min(100, hb_total * 100 / max(1, envelope))
        insertion_chart = f'''<figure class="comparison-graphic"><figcaption><strong>HB FMR itemization against the NEP regional envelope</strong><span>Candidate lines may be funded within this envelope.</span></figcaption><div class="compare-row"><span>NEP envelope · ₱{envelope / 1e9:,.2f}B</span><div class="compare-track"><i style="width:100%"></i></div></div><div class="compare-row"><span>HB candidate lines · ₱{hb_total / 1e9:,.2f}B</span><div class="compare-track candidate"><i style="width:{ratio:.1f}%"></i></div></div></figure>'''
        insertion_table = f'''<div class="card section"><h2>HGAB FMR line items under the NEP envelope</h2><p class="sub">The NEP provides regional FMR allocations rather than project-title lines. These {len(fmr_insertion_rows):,} HGAB rows are itemization candidates for review against those envelopes; they are not counted as added spending. Search the extracted line items and verify the source page.</p>{insertion_chart}<div class="toolbar"><input id="fmrNepSearch" type="search" placeholder="Search FMR project, page, or context"><button class="export-btn" type="button" onclick="downloadFmrCsv()">Export all {len(fmr_insertion_rows):,} rows to CSV</button></div><div class="tablewrap"><table id="fmrNepTable"><thead><tr><th>HGAB FMR line</th><th class="num">HB allocation</th><th>HB page</th><th>Nearby schedule context</th></tr></thead><tbody id="fmrNepBody"></tbody></table></div><div class="pager" id="fmrNepPager"></div><script>const FMR_NEP={insertion_data};function downloadFmrCsv(){{const headers=['HGAB FMR line','HB allocation (pesos)','HB page','Nearby schedule context'];const rows=FMR_NEP.map(r=>[r.name,r.amount,r.page,r.context]);const csv=[headers,...rows].map(row=>row.map(v=>'\"'+String(v??'').replace(/\"/g,'\"\"')+'\"').join(',')).join('\\r\\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+csv],{{type:'text/csv;charset=utf-8'}}));a.download='fmr_nep_to_hgab.csv';a.click();URL.revokeObjectURL(a.href)}}(()=>{{const body=document.getElementById('fmrNepBody'),pager=document.getElementById('fmrNepPager'),search=document.getElementById('fmrNepSearch');let page=0;const size=30,esc=s=>String(s??'').replace(/[&<>\"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}}[c])),peso=n=>'₱'+new Intl.NumberFormat('en-PH').format(Number(n)||0),num=n=>new Intl.NumberFormat('en-PH').format(n);function draw(){{const q=search.value.toLowerCase();const list=FMR_NEP.filter(r=>`${{r.name}} ${{r.page}} ${{r.context}}`.toLowerCase().includes(q));const pages=Math.max(1,Math.ceil(list.length/size));page=Math.min(page,pages-1);const start=page*size;body.innerHTML=list.slice(start,start+size).map(r=>`<tr><td>${{esc(r.name)}}</td><td class="num">${{peso(r.amount)}}</td><td>${{esc(r.page)}}</td><td>${{esc(r.context)}}</td></tr>`).join('')||'<tr><td colspan="4">No matching lines</td></tr>';pager.innerHTML=`<button ${{page===0?'disabled':''}} data-step="-1">Previous</button><span>${{list.length?num(start+1):0}}–${{num(Math.min(start+size,list.length))}} of ${{num(list.length)}}</span><button ${{page>=pages-1?'disabled':''}} data-step="1">Next</button>`;pager.querySelectorAll('button').forEach(b=>b.onclick=()=>{{page+=Number(b.dataset.step);draw()}})}}search.oninput=()=>{{page=0;draw()}};draw()}})();</script></div>'''
    if kind == "nia":
        nia_match_count = insertion["comparisonCounts"].get("Named in NEP; compare amount and scope", 0)
        nia_unmatched = insertion["comparisonCounts"].get("Potential insertion; no close named NEP counterpart", 0)
        insertion_chart = f'''<figure class="comparison-graphic"><figcaption><strong>Named NEP matches and unmatched HGAB candidates</strong><span>Count of 32 NIA candidate lines by title screen.</span></figcaption><div class="compare-row"><span>Named in NEP · {nia_match_count}</span><div class="compare-track"><i style="width:{nia_match_count * 100 / max(1, insertion["hgabCandidateCount"]):.1f}%"></i></div></div><div class="compare-row"><span>No close named counterpart · {nia_unmatched}</span><div class="compare-track candidate"><i style="width:{nia_unmatched * 100 / max(1, insertion["hgabCandidateCount"]):.1f}%"></i></div></div></figure>'''
        insertion_table = f'''<div class="card section"><h2>Potential NEP-to-HGAB project insertions</h2><p class="sub">These HGAB titles have no close named counterpart in the FY2027 NEP NIA schedule after matching project identity. They are review leads, not confirmed additions.</p>{insertion_chart}<div class="toolbar"><button class="export-btn" type="button" onclick="downloadReportTable('niaInsertionTable','nia_nep_to_hgab_candidates.csv')">Export table to CSV</button></div><div class="tablewrap"><table id="niaInsertionTable"><thead><tr><th>HGAB project</th><th class="num">Amount</th><th>PDF page</th><th>Review basis</th></tr></thead><tbody>__NIA_INSERTION_ROWS__</tbody></table></div></div>'''.replace(
            "__NIA_INSERTION_ROWS__",
            "".join(
                f"<tr><td>{esc(row['hb_project'])}</td><td class='num'>{peso(int(row['hb_amount_pesos'] or 0))}</td><td>{esc(row['source_page'])}</td><td>{esc(row['comparison'])}</td></tr>"
                for row in insertion_rows
            ) or '<tr><td colspan="4">No unmatched named NIA candidates.</td></tr>'
        )
    return f'''{MARKER}<!--SUMMARY_START-->{summary_html}<!--SUMMARY_END-->
{insertion_context}{insertion_table}
<section class="card section" style="margin:0 0 18px">
<h2>Potential {title} repeats: FY2027 HGAB vs FY2025 GAA</h2>
<p class="sub">{explain} The workspace has FY2026 HGAB amendment schedules, but not FY2026 enrolled-copy GAA line items for DA/FMR or NIA; the HGAB schedules are excluded here. The table keeps high name matches (90%). Across categories, explicit opposing directions (East/West, North/South, Norte/Sur, Oriental/Occidental) are excluded. Different package, phase, stage, lot, or segment labels are treated as a 50/50 signal: they may mark legitimate yearly segmentation or a repeated scope, so those candidates stay visible for review. Check whether stated chainage overlaps. Lower ranked candidates are in the CSV. Similarity is a screening aid, not proof of the same project: verify location, scope, phase, and amounts against the source. Amounts and differences are in pesos.</p>
<figure class="comparison-graphic"><figcaption><strong>Matched allocation totals</strong><span>FY2027 HGAB lines and their FY2025 GAA matches shown above.</span></figcaption><div class="compare-row"><span>FY2027 · ₱{fy2027_total / 1e9:,.2f}B</span><div class="compare-track"><i style="width:{100 * fy2027_total / max(1, fy2027_total, prior_total):.1f}%"></i></div></div><div class="compare-row"><span>FY2025 GAA · ₱{prior_total / 1e9:,.2f}B</span><div class="compare-track candidate"><i style="width:{100 * prior_total / max(1, fy2027_total, prior_total):.1f}%"></i></div></div></figure>
<div class="toolbar"><button class="export-btn" type="button" onclick="downloadReportTable('{kind}RepeatTable','{kind}_visible_repeat_matches.csv')">Export table to CSV</button></div><div style="border:1px solid #dce4e1;border-radius:10px"><table id="{kind}RepeatTable" style="border-collapse:collapse;width:100%;font-size:12px;table-layout:fixed"><thead><tr><th>FY2027 line item</th><th>FY2027 amount</th><th>Compared with</th><th>Closest prior-year line</th><th>FY2027 chainage</th><th>Prior chainage</th><th>Chainage / tranche check</th><th>Prior amount</th><th>Difference</th><th>Name match</th><th>Prior source</th></tr></thead><tbody>{rows or '<tr><td colspan="11">No candidates met the display threshold.</td></tr>'}</tbody></table></div>
<p class="sub" style="margin-top:12px">Full top-three match candidates: <a href="{csv_href}" download="{kind}_year_on_year_candidates.csv">download the review CSV</a>. Coverage: FY2025 uses the local enacted GAA budget file; FMR is limited to DA and NIA irrigation to the NIA agency. FY2026 GAA line-item sources for these schedules are not present in the current workspace.</p>
</section>{END_MARKER}{REPORT_TABLE_CSV_HELPER}'''


def replace_section(path: Path, section: str, stale: str | None = None) -> None:
    page = path.read_text(encoding="utf-8")
    # Remove the old NIA notice that said the local files lacked prior-year
    # names; the broader route/data search below replaces that conclusion.
    summary_match = re.search(r'<!--SUMMARY_START-->(.*?)<!--SUMMARY_END-->', section, re.S)
    summary_html = summary_match.group(1) if summary_match else ""
    section = section.replace(summary_match.group(0), "", 1) if summary_match else section
    page = re.sub(
        r'<div class="callout" style="background:#fff8e9;border-left-color:var\(--amber\)"><strong>FY2026 year-on-year repeat check</strong><p>.*?</p></div>',
        "", page, count=1,
    )
    # Clear older generated layouts as well as the current marked section.
    # Prior versions could leave a duplicate below the repeat table.
    title_pattern = r"Potential (?:FMR|NIA irrigation) repeats:"
    page = re.sub(
        re.escape(MARKER) + r".*?<h2>" + title_pattern + r".*?</section>(?:" + re.escape(END_MARKER) + r")?",
        "", page, flags=re.S,
    )
    page = re.sub(
        r'<section class="card section" style="margin:0 0 18px">(?:(?!</section>).)*?<h2>' + title_pattern + r".*?</section>",
        "", page, flags=re.S,
    )
    page = re.sub(
        r'<div class="card section"><h2>(?:HGAB FMR line items under the NEP envelope|Potential NEP-to-HGAB project insertions)</h2>.*?</div></div>',
        "", page, flags=re.S,
    )
    page = re.sub(r'<div class="callout"><strong>NEP-to-HGAB line-item screen:</strong>.*?</div>', "", page, flags=re.S)
    page = page.replace(REPORT_TABLE_CSV_HELPER, "")
    page = page.replace(END_MARKER, "").replace(MARKER, "")
    if summary_html:
        marked_summary = f'<!--REPEAT_SUMMARY_START-->{summary_html}<!--REPEAT_SUMMARY_END-->'
        if '<div class="repeat-summary-slot"></div>' in page:
            page = page.replace('<div class="repeat-summary-slot"></div>', marked_summary, 1)
        else:
            page = re.sub(r'<!--REPEAT_SUMMARY_START-->.*?<!--REPEAT_SUMMARY_END-->', marked_summary, page, count=1, flags=re.S)
        lead_count = re.search(r'<div class="mvalue">([\d,]+)</div>', summary_html)
        if lead_count:
            page = page.replace('id="repeatCount"></div>', f'id="repeatCount">{lead_count.group(1)}</div>', 1)
    page = page.replace(
        '<select id="sort"><option value="amount_desc">Largest amount</option><option value="amount_asc">Smallest amount</option><option value="page">PDF page</option><option value="title">Project name</option></select></div><div class="tablewrap"><table><thead><tr><th>Project title candidate</th>',
        '<select id="sort"><option value="amount_desc">Largest amount</option><option value="amount_asc">Smallest amount</option><option value="page">PDF page</option><option value="title">Project name</option></select><button class="export-btn" type="button" onclick="downloadNiaCandidatesCsv()">Export all project rows to CSV</button></div><div class="tablewrap"><table id="niaProjectTable"><thead><tr><th>Project title candidate</th>',
        1,
    )
    lead = re.search(r'<section class="card lead section"[^>]*>.*?</section>', page, flags=re.S)
    if lead:
        page = page[:lead.end()] + "\n" + section + page[lead.end():]
    else:
        page = page.replace('<main class="wrap">', '<main class="wrap">\n' + section, 1)
    path.write_text(page, encoding="utf-8")


def write_csv(path: Path, data: list[dict]) -> None:
    columns = ["kind", "year", "line_id", "name", "amount", "prior_year", "prior_name",
               "prior_amount", "similarity", "rank", "amount_difference", "source", "prior_source",
               "current_chainage", "prior_chainage", "chainage_overlap", "chainage_status",
               "tranche_status", "tranche_detail", "tranche_conflict"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)


def main() -> None:
    fmr27 = [fields(r, 2027, "fmr") for r in load_json_rows(ROOT / "hb10858_agency_projects.json")
             if r.get("program") == "Farm-to-Market Roads"]
    nia27 = [fields(r, 2027, "nia") for r in load_json_rows(ROOT / "hb10858_nia_projects.json")]
    p25 = "'" + str(ODV / "data/parquet/budget_2025.parquet") + "'"
    fmr25 = duckdb_rows(f"""select * from read_parquet({p25}) where department_desc ilike '%Agriculture%'
      and regexp_matches(upper(coalesce(description,'')), 'FARM.?TO.?MARKET| FMR ')""")
    nia25 = duckdb_rows(f"""select * from read_parquet({p25}) where agency_desc ilike '%National Irrigation%'
      and regexp_matches(upper(coalesce(description,'')), 'IRRIGATION| SIP | CIS ')""")
    previous = {
        "fmr": [fields(r, 2025, "fmr") for r in fmr25],
        "nia": [fields(r, 2025, "nia") for r in nia25],
    }
    targets = {"fmr": fmr27, "nia": nia27}
    all_matches = []
    for kind in ("fmr", "nia"):
        data = matches(targets[kind], previous[kind])
        all_matches.extend(data)
        replace_section(OUT / ("fmr.html" if kind == "fmr" else "nia.html"), render_section(kind, data))
        print(f"{kind.upper()}: FY2027 HGAB={len(targets[kind])}, FY2025 GAA prior={len(previous[kind])}; FY2026 GAA source unavailable locally")
    write_csv(OUT / "fmr_nia_year_on_year_candidates.csv", all_matches)
    print(f"Wrote {OUT / 'fmr_nia_year_on_year_candidates.csv'} and updated FMR/NIA reports")


if __name__ == "__main__":
    main()
