#!/usr/bin/env python3
"""Build local static review pages for HB 10858 reading-stage changes."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from analyze_fmr_nia_repeats import fields, matches
from chainage import compare_chainage
from enrich_congressional_representatives import RepresentativeLookup, enrich_rows

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
STATIC = ODV / "static" / "nep-preview"
OUT = ROOT / "analysis_output"


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def amount(row: dict | None) -> int:
    return int(float((row or {}).get("amountPesos") or 0))


def compare_rows(old: list[dict], new: list[dict], group: str) -> dict:
    def identity(row: dict) -> tuple[str, ...]:
        if group == "deped":
            return tuple(norm(row.get(k)) for k in ("region", "division", "schoolName"))
        return (norm(row.get("projectName")),)

    old_index: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for row in old:
        old_index[identity(row)].append(row)
    used: Counter[tuple[str, ...]] = Counter()
    rows = []
    for current in new:
        key = identity(current)
        match_i = used[key]
        previous = old_index[key][match_i] if match_i < len(old_index[key]) else None
        used[key] += 1
        if previous is None:
            status = "Only in 3rd reading"
        elif group == "deped":
            fields = ("juniorHighPersonnelServicesPesos", "juniorHighMooePesos", "juniorHighTotalPesos", "seniorHighMooePesos")
            status = "Allocation changed" if any(int(previous.get(k) or 0) != int(current.get(k) or 0) for k in fields) else "Same allocation"
        else:
            status = "Allocation changed" if amount(previous) != amount(current) else "Same allocation"
        if group == "deped":
            rows.append({
                "status": status, "name": current.get("schoolName", ""),
                "region": current.get("region", ""), "division": current.get("division", ""),
                "secondTotal": int((previous or {}).get("totalPesos") or 0),
                "thirdTotal": int(current.get("totalPesos") or 0),
                "delta": int(current.get("totalPesos") or 0) - int((previous or {}).get("totalPesos") or 0),
                "secondJhsPs": int((previous or {}).get("juniorHighPersonnelServicesPesos") or 0),
                "thirdJhsPs": int(current.get("juniorHighPersonnelServicesPesos") or 0),
                "secondJhsMooe": int((previous or {}).get("juniorHighMooePesos") or 0),
                "thirdJhsMooe": int(current.get("juniorHighMooePesos") or 0),
                "secondShsMooe": int((previous or {}).get("seniorHighMooePesos") or 0),
                "thirdShsMooe": int(current.get("seniorHighMooePesos") or 0),
                "sourcePage": current.get("sourcePage", ""),
            })
        else:
            rows.append({
                "status": status, "name": current.get("projectName", ""),
                "secondAmount": amount(previous), "thirdAmount": amount(current),
                "delta": amount(current) - amount(previous),
                "secondPage": (previous or {}).get("sourcePage", ""),
                "thirdPage": current.get("sourcePage", ""),
                "secondSource": (previous or {}).get("sourceVolume", ""),
                "thirdSource": current.get("sourceVolume", ""),
                "chainage": current.get("projectName", ""),
            })
    for key, records in old_index.items():
        for previous in records[used[key]:]:
            rows.append({
                "status": "Only in 2nd reading",
                "name": previous.get("schoolName", "") if group == "deped" else previous.get("projectName", ""),
                "region": previous.get("region", ""), "division": previous.get("division", ""),
                "secondTotal": int(previous.get("totalPesos") or 0) if group == "deped" else 0,
                "thirdTotal": 0, "delta": -int(previous.get("totalPesos") or 0) if group == "deped" else -amount(previous),
                "secondAmount": amount(previous), "thirdAmount": 0,
                "secondPage": previous.get("sourcePage", ""), "thirdPage": "",
                "sourcePage": previous.get("sourcePage", ""), "chainage": previous.get("projectName", ""),
            })
    counts = Counter(row["status"] for row in rows)
    old_total = sum(int(r.get("totalPesos") or 0) for r in old) if group == "deped" else sum(amount(r) for r in old)
    new_total = sum(int(r.get("totalPesos") or 0) for r in new) if group == "deped" else sum(amount(r) for r in new)
    return {
        "summary": {"secondRows": len(old), "thirdRows": len(new), "secondTotal": old_total,
                    "thirdTotal": new_total, "statusCounts": dict(counts)},
        "rows": rows,
    }


def load_edition(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


def hgab_insertions(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    out = []
    for r in rows:
        # The broad exact-title-miss queue included many rows with credible
        # fuzzy NEP counterparts. Keep only rows that survive both embedded
        # NEP-title detection and the office/region fuzzy title screen.
        if r["comparison"] != "No plausible NEP title counterpart; review candidate":
            continue
        out.append({
            "comparison": r["comparison"], "projectName": r["projectName"],
            "amountPesos": int(float(r["amountPesos"] or 0)), "region": r["region"],
            "office": r["office"], "closest_nep_title": r["closest_nep_title"],
            "title_similarity_pct": int(float(r["title_similarity_pct"] or 0)),
            "sourceVolume": r["sourceVolume"], "sourcePage": r["sourcePage"],
        })
    return out


def gaa25_nia() -> list[dict]:
    parquet = ODV / "data" / "parquet" / "budget_2025.parquet"
    path = str(parquet).replace("'", "''")
    sql = f"""SELECT description, amount, department_desc, agency_desc FROM read_parquet('{path}')
      WHERE agency_desc ILIKE '%National Irrigation%'
      AND regexp_matches(upper(coalesce(description,'')), 'IRRIGATION| SIP | CIS ')"""
    result = subprocess.run(["duckdb", "-json", "-c", sql], cwd=ODV, check=True, text=True, capture_output=True)
    return json.loads(result.stdout or "[]")


def write_dpwh_comparison_page() -> None:
    data_path = STATIC / "dpwh-data.json"
    data = json.loads(data_path.read_text(encoding="utf-8"))
    data["hbInsertions2nd"] = hgab_insertions(OUT / "hb_nep_comparison.csv")
    data["hbInsertions"] = hgab_insertions(OUT / "hb_nep_comparison_3rd.csv")
    lookup = RepresentativeLookup()
    for rows in (data["hbInsertions"], data["hbInsertions2nd"]):
        enrich_rows(rows, lookup, "projectName")
    third_summary = json.loads((OUT / "hb_nep_comparison_3rd_summary.json").read_text(encoding="utf-8"))
    with (OUT / "hb_nep_comparison.csv").open(newline="", encoding="utf-8") as source:
        old_counts = Counter(r["comparison"] for r in csv.DictReader(source))
    summary = {"counts": dict(old_counts), "billSource": [{"file": "HB 10858 · 2nd reading"}]}
    data["hbInsertions3rdSummary"] = third_summary
    data["hbInsertions2ndSummary"] = summary
    write_json(data_path, data)

    # Refresh the insertion section on the DPWH home page as well as the
    # dedicated page below. This section deliberately shows only HGAB rows
    # without a plausible NEP title counterpart; ambiguous rows remain in the
    # separate review export and are not counted as clear additions.
    dpwh_path = STATIC / "dpwh.html"
    dpwh_html = dpwh_path.read_text(encoding="utf-8")
    third_total = sum(int(row.get("amountPesos") or 0) for row in data["hbInsertions"])
    insertion_intro = (
        f'The 3rd-reading title screen leaves <strong>{len(data["hbInsertions"]):,} HGAB lines</strong> '
        f'without a plausible FY2027 NEP title counterpart, carrying '
        f'<strong>₱{third_total / 1_000_000_000:,.2f}B</strong>. '
        f'The full comparison also has {third_summary["counts"].get("Multiple or already paired NEP counterparts; review scope", 0):,} '
        f'ambiguous or already-paired rows. These are review leads, not confirmed additions.'
    )
    dpwh_html = re.sub(
        r'(<section id="hgab-insertion".*?<h2>).*?(</h2>\s*<p class="sub">).*?(</p>)',
        lambda m: m.group(1) + "FY2027 3rd-reading HGAB lines without a plausible NEP title match" + m.group(2) + insertion_intro + m.group(3),
        dpwh_html, count=1, flags=re.S,
    )
    dpwh_html = dpwh_html.replace("All potential insertions", "All lines without a plausible NEP title match")
    dpwh_html = dpwh_html.replace("No close title counterpart", "No plausible NEP title counterpart")
    dpwh_html = dpwh_html.replace("Possible title counterpart", "Plausible NEP title counterpart")
    dpwh_html = dpwh_html.replace("No close title counterpart; review candidate", "No plausible NEP title counterpart; review candidate")
    dpwh_html = dpwh_html.replace("Possible title counterpart; review scope", "Plausible NEP title counterpart; review scope")
    dpwh_html = dpwh_html.replace("<th>HB project line</th>", "<th>3rd-reading HGAB line</th>")
    dpwh_html = dpwh_html.replace(
        '<option value="all">All lines without a plausible NEP title match</option><option value="novel">No plausible NEP title counterpart</option><option value="near">Plausible NEP title counterpart</option>',
        '<option value="all">All lines without a plausible NEP title match</option>',
    )
    dpwh_html = dpwh_html.replace(
        '<strong>HB candidates by title screen</strong><span>Candidate count and allocation for the current filters.</span>',
        '<strong>DPWH line items by NEP title-screen result</strong><span>Counts across all 3rd-reading DPWH records; the table below lists only lines without a plausible NEP title counterpart.</span>',
    ).replace('aria-label="HB candidates by title screen"', 'aria-label="DPWH line items by NEP title-screen result"')
    old_screen_groups = "const insertionGroups=[['Plausible NEP title counterpart; review scope','Plausible NEP title counterpart · review scope',true],['No plausible NEP title counterpart; review candidate','No plausible NEP title counterpart',false]].map(([key,label,candidate])=>{const group=rows.filter(r=>r.comparison===key);return{label,value:group.reduce((t,r)=>t+Number(r.amountPesos||0),0),count:group.length,candidate}});renderDonut('insertionGraph',insertionGroups,v=>peso(v));"
    new_screen_groups = "const screenCounts=(D.hbInsertions3rdSummary||{}).counts||{},insertionGroups=[['Exact normalized title found in NEP','Exact title match'],['Plausible NEP title counterpart; review scope','Plausible title match'],['No plausible NEP title counterpart; review candidate','No plausible title match'],['Multiple or already paired NEP counterparts; review scope','Ambiguous / already paired']].map(([key,label])=>({label,count:Number(screenCounts[key]||0),value:Number(screenCounts[key]||0)}));renderDonut('insertionGraph',insertionGroups,v=>fmt(v));"
    dpwh_html = dpwh_html.replace(old_screen_groups, new_screen_groups)
    dpwh_html = dpwh_html.replace("dpwh_hgab_insertion_candidates.csv", "dpwh_hgab_nep_review_records.csv")
    dpwh_html = dpwh_html.replace("The extractor is heuristic and requires checking against the original bill page;", "The corrected native-text parser reconciles the printed program totals; still check each project against the original bill page;")
    dpwh_path.write_text(dpwh_html, encoding="utf-8")

    comparison = json.loads((OUT / "dpwh_hgab_2nd_vs_3rd.json").read_text(encoding="utf-8"))
    thin_rows = []
    for row in comparison["rows"]:
        old, new = row.get("second"), row.get("third")
        old_chain = compare_chainage(str((old or {}).get("projectName") or ""), "").get("prior_chainage", "")
        new_chain = compare_chainage("", str((new or {}).get("projectName") or "")).get("current_chainage", "")
        thin_rows.append({
            **{k: v for k, v in row.items() if k not in {"second", "third"}},
            "second_chainage": old_chain, "third_chainage": new_chain,
            "second": ({k: old.get(k) for k in ("projectName", "amountPesos", "office", "region", "sourcePage")} if old else None),
            "third": ({k: new.get(k) for k in ("projectName", "amountPesos", "office", "region", "sourcePage")} if new else None),
        })
    write_json(STATIC / "dpwh-hgab-comparison.json", {"summary": comparison["summary"], "rows": thin_rows})

    hgab_page = STATIC / "dpwh-hgab.html"
    html = hgab_page.read_text(encoding="utf-8")
    third_candidates = data["hbInsertions"]
    third_total = sum(int(row.get("amountPesos") or 0) for row in third_candidates)
    old_candidates = data["hbInsertions2nd"]
    old_total = sum(int(row.get("amountPesos") or 0) for row in old_candidates)
    html = html.replace(
        "<title>DPWH · HGAB insertions (FY2027)</title>",
        "<title>DPWH · NEP to HGAB review (FY2027)</title>",
    )
    html = re.sub(
        r'<meta name="description" content="[^"]*">',
        '<meta name="description" content="FY2027 DPWH NEP to HGAB review queue. Unmatched title records are unresolved until checked against project scope and bill pages; they are not confirmed insertions.">',
        html, count=1,
    )
    html = html.replace("(HB 10858, second reading)", "(HB 10858, third reading)")
    html = html.replace(
        "without an exact normalized project-title match in the FY2027 NEP extract. These are insertion candidates",
        "that remain unmatched after exact-title, embedded-source-title, and fuzzy title screening against the FY2027 NEP",
    )
    html = html.replace(
        "<h1>DPWH: additions in HGAB after the NEP</h1>",
        "<h1>DPWH: NEP to HGAB review</h1>",
    )
    html = re.sub(
        r'(<h1>DPWH: NEP to HGAB review</h1>)<p>.*?</p>',
        r'\1<p>Only records with no exact or plausible fuzzy project-title counterpart in the FY2027 NEP remain in this shortlist. They are title-screen candidates for additions and still need project-scope verification.</p>',
        html, count=1, flags=re.S,
    )
    html = re.sub(
        r'<section class="impact-teaser" aria-label="(?:Key finding|NEP to HGAB review status|NEP to HGAB unmatched shortlist)">.*?</section>',
        f'''<section class="impact-teaser" aria-label="NEP to HGAB unmatched shortlist"><div><span class="impact-teaser-kicker">DPWH · FY2027 NEP to 3rd-reading HGAB</span><div class="impact-teaser-headline">{len(third_candidates):,}</div><div class="impact-teaser-title">HGAB line items without a plausible NEP title counterpart</div><p class="impact-teaser-copy">Exact titles and fuzzy title counterparts scoring at least 83% are removed from this shortlist.</p></div><div class="impact-teaser-side"><div class="impact-teaser-stat"><strong>₱{third_total/1e9:,.2f}B</strong><span>allocation across the unmatched shortlist</span></div><p class="impact-teaser-foot">The 83% title screen is a triage rule. Confirm project location, chainage, scope, and the cited bill page before treating a line as a true addition.</p></div></section>''',
        html, count=1, flags=re.S,
    )
    html = html.replace(
        "<h2>Potential insertions in FY2027 HGAB relative to NEP</h2>",
        "<h2>FY2027 HGAB line items unmatched to NEP</h2>",
    )
    html = html.replace(
        "<h2>FY2027 HGAB records needing NEP scope review</h2>",
        "<h2>FY2027 HGAB line items unmatched to NEP</h2>",
    )
    html = html.replace("All potential insertions", "All unmatched line items")
    html = html.replace("All unresolved records", "All unmatched line items")
    html = html.replace("No close title counterpart; review candidate", "No plausible NEP title counterpart; review candidate")
    html = html.replace("Possible title counterpart; review scope", "Plausible NEP title counterpart; review scope")
    html = html.replace("No close title counterpart", "No plausible NEP title counterpart")
    html = html.replace("Possible title counterpart", "Plausible NEP title counterpart")
    html = html.replace('<option value="all">All unresolved records</option><option value="novel">No close title counterpart</option><option value="near">Possible title counterpart</option>', '<option value="all">All unmatched line items</option><option value="novel">No plausible NEP title counterpart</option>')
    html = html.replace('<option value="near">Plausible NEP title counterpart</option>', '')
    html = html.replace("HB candidates by title screen", "Unmatched HGAB line items after NEP title screening")
    html = html.replace("Unresolved records by title-screen result", "Unmatched HGAB line items after NEP title screening")
    html = html.replace("Candidate count and allocation for the current filters.", "Count and extracted allocation for the unmatched line items.")
    html = html.replace("Unresolved-record count and extracted allocations for the current filters.", "Count and extracted allocation for the unmatched line items.")
    html = html.replace("<th>HB project line</th>", "<th>Extracted HGAB record</th>")
    html = html.replace("<th class=\"num\">HB allocation</th>", "<th class=\"num\">Extracted amount</th>")
    html = re.sub(
        r'(<h2>FY2027 HGAB line items unmatched to NEP</h2>\s*<p class="sub">).*?(</p>)',
        lambda m: m.group(1) + f'After removing exact-title matches and fuzzy title counterparts scoring at least 83%, <strong>{len(third_candidates):,} HGAB line items</strong> remain, carrying <strong>₱{third_total/1e9:,.2f}B</strong>. This shortlist is screened for project-title similarity; verify project scope and cited bill page before counting confirmed additions.' + m.group(2),
        html, count=1, flags=re.S,
    )
    archive = f'''<details class="card section" id="second-reading-archive"><summary><strong>Previous edition · HGAB 2nd Reading</strong></summary><p class="sub">The 2nd-reading edition has {len(old_candidates):,} unmatched records after the same 83% title screen, carrying ₱{old_total/1e9:,.2f}B in extracted allocations. These are candidates for review, not confirmed additions.</p><button class="export-btn" id="secondReadingCsv" type="button">Export 2nd-reading unmatched records to CSV</button><p class="sub"><a href="dpwh-hgab-comparison.html">Open DPWH 2nd vs 3rd Reading comparison</a></p></details>'''
    html = re.sub(r'<details class="card section" id="second-reading-archive">.*?</details>', '', html, count=1, flags=re.S)
    section_start = html.index('<section id="hgab-insertion"')
    source_context = html.index('<p class="sub">Source: local HB 10858 Volume I-C', section_start)
    section_end = html.index('</section>', source_context)
    html = html[:section_end] + archive + html[section_end:]
    second_csv_handler = "document.getElementById('secondReadingCsv').onclick=()=>downloadCsv('dpwh_hgab_2nd_reading_review_records.csv',D.hbInsertions2nd);"
    html = html.replace(second_csv_handler, "")
    html = html.replace("document.getElementById('insertionCsv').onclick=", second_csv_handler + "document.getElementById('insertionCsv').onclick=", 1)
    html = html.replace("dpwh_hgab_insertion_candidates.csv", "dpwh_hgab_nep_review_records.csv")
    html = html.replace("Export filtered rows to CSV", "Export filtered review records to CSV")
    html = html.replace(
        "The extractor is heuristic and requires checking against the original bill page;",
        "The corrected native-text parser reconciles the printed program totals; still check each project against the original bill page;",
    )
    html = html.replace('<a href="dpwh-hgab.html">DPWH · HGAB insertions</a>', '<a href="dpwh-hgab.html">NEP → HGAB (3rd)</a><a href="dpwh-hgab-comparison.html">DPWH 2nd vs 3rd</a><a href="nia-irrigation.html">NIA irrigation</a><a href="deped.html">DepEd</a>', 1)
    hgab_page.write_text(html, encoding="utf-8")

    page = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DPWH HGAB · 2nd vs 3rd Reading</title><script src="/static/js/chart.js"></script><style>
:root{--ink:#172b3a;--muted:#637381;--paper:#f4f6f5;--card:#fff;--line:#dce3e1;--teal:#087e78;--amber:#a65b08}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:#102f3e;color:#fff;padding:30px max(22px,calc((100vw - 1250px)/2))}h1{margin:8px 0;font-size:clamp(30px,4vw,46px)}header p{max-width:900px;color:#d1dfde}.nav{display:flex;gap:15px;flex-wrap:wrap}.nav a{color:#a7ddd1}.wrap{max-width:1250px;margin:auto;padding:24px}.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:16px}.metric,.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}.label{color:var(--muted);font-size:13px}.value{font-size:25px;font-weight:750}.charts{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;margin-bottom:16px}.chart{min-height:270px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.toolbar input,.toolbar select,button{font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:7px;background:#fff}.export{background:#087e78;color:#fff;border-color:#087e78}table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px}th,td{padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere;text-align:left}th{background:#eff4f2;position:sticky;top:0}.num{font-variant-numeric:tabular-nums;text-align:right}.tablewrap{max-height:68vh;overflow:auto}.note{color:var(--muted);font-size:13px}.pagination{display:flex;justify-content:space-between;align-items:center;margin:12px 0}.pagination button{cursor:pointer}.danger{color:#8c4c06}@media(max-width:800px){.charts{grid-template-columns:1fr}.wrap{padding:14px}table{font-size:11px}}
</style></head><body><header><div>FY2027 · HB 10858 · DPWH project schedule</div><h1>2nd Reading vs 3rd Reading</h1><p>Compare candidate DPWH line items across the two bill editions. Exact titles are paired first. Fuzzy title matches require chainage compatibility and no opposing direction; review all candidates against the PDF before treating them as the same project or a deletion/insertion.</p><nav class="nav"><a href="dpwh.html">NEP patterns</a><a href="dpwh-hgab.html">NEP → HGAB (3rd reading)</a><a href="nia-irrigation.html">NIA irrigation</a><a href="deped.html">DepEd school allocations</a><a href="fmr.html">FMR</a><a href="nia.html">NIA projects</a><a href="hfep.html">HFEP</a></nav></header><main class="wrap">__READING_TEASER__<section class="metrics" id="metrics"></section><section class="charts"><article class="card chart"><h2>2nd vs 3rd allocations</h2><canvas id="scatter"></canvas></article><article class="card chart"><h2>Line changes after filters</h2><canvas id="statusChart"></canvas></article></section><article class="card"><h2>Line item changes</h2><p class="note">The corrected parser matches the printed 2nd and 3rd reading schedules. Disjoint station ranges are kept separate; package, phase, and segment changes remain review signals. “New in 3rd reading” is an extraction status; verify each cited page before interpreting it as an insertion.</p><div class="toolbar"><input id="search" type="search" placeholder="Filter title, office, or chainage"><select id="status"><option value="all">All statuses</option></select><button class="export" id="csv">Export filtered CSV</button></div><div class="tablewrap"><table><thead><tr><th>Status</th><th>2nd reading line</th><th>3rd reading line</th><th>2nd chainage</th><th>3rd chainage</th><th class="num">2nd amount</th><th class="num">3rd amount</th><th class="num">Change</th><th>Range check</th><th>Office / source</th></tr></thead><tbody id="body"></tbody></table></div><div class="pagination"><button id="prev">Previous</button><span id="range"></span><button id="next">Next</button></div></article></main><script>
fetch('dpwh-hgab-comparison.json').then(r=>r.json()).then(D=>{const rows=D.rows,s=D.summary;const peso=n=>'₱'+Number(n||0).toLocaleString('en-PH');const fmt=n=>Number(n||0).toLocaleString('en-PH');document.getElementById('metrics').innerHTML=[['2nd reading lines',fmt(s.secondCandidateCount)],['3rd reading lines',fmt(s.thirdCandidateCount)],['2nd reading allocations',peso(s.secondAllocationPesos)],['3rd reading allocations',peso(s.thirdAllocationPesos)]].map(x=>`<article class="metric"><div class="label">${x[0]}</div><div class="value">${x[1]}</div></article>`).join('');const statusSelect=document.getElementById('status');const statuses=[...new Set(rows.map(r=>r.status))];statusSelect.innerHTML+='<option value="changed">Changed rows only</option>'+statuses.map(x=>`<option>${x}</option>`).join('');const search=document.getElementById('search'),sel=statusSelect,body=document.getElementById('body'),range=document.getElementById('range');let page=0,size=40,a,b;function filtered(){const q=search.value.toLowerCase(),st=sel.value;return rows.filter(r=>(!st||st==='all'||(st==='changed'?r.status!=='Retained · same amount':r.status===st))&&[r.status,r.second?.projectName,r.third?.projectName,r.second?.office,r.third?.office,r.chainage_overlap].some(v=>String(v||'').toLowerCase().includes(q)))}function update(){const list=filtered();page=Math.min(page,Math.max(0,Math.ceil(list.length/size)-1));const start=page*size;body.innerHTML=list.slice(start,start+size).map(r=>`<tr><td>${r.status}<br>${r.score_pct?`${r.score_pct}% title`:''}</td><td>${r.second?.projectName||'—'}</td><td>${r.third?.projectName||'—'}</td><td>${r.second_chainage||'—'}</td><td>${r.third_chainage||'—'}</td><td class="num">${r.second?peso(r.second.amountPesos):'—'}</td><td class="num">${r.third?peso(r.third.amountPesos):'—'}</td><td class="num">${peso(r.amount_delta_pesos)}</td><td>${r.chainage_status}${r.chainage_overlap?'<br>overlap '+r.chainage_overlap:''}<br>${r.tranche_status}</td><td>${r.third?.office||r.second?.office||''}<br>${r.third?.sourcePage?`3rd p.${r.third.sourcePage}`:''} ${r.second?.sourcePage?`· 2nd p.${r.second.sourcePage}`:''}</td></tr>`).join('');range.textContent=`${list.length?start+1:0}–${Math.min(start+size,list.length)} of ${list.length}`;if(a)a.destroy();if(b)b.destroy();const stats={};for(const x of list)stats[x.status]=(stats[x.status]||0)+1;a=new Chart(document.getElementById('statusChart'),{type:'bar',data:{labels:Object.keys(stats),datasets:[{label:'Line items',data:Object.values(stats),backgroundColor:'#087e78'}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y'}});const points=list.filter(x=>x.second&&x.third).map(x=>({x:Number(x.second.amountPesos),y:Number(x.third.amountPesos)}));b=new Chart(document.getElementById('scatter'),{type:'scatter',data:{datasets:[{label:'Matched lines',data:points,backgroundColor:'#355b92'}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{type:'linear',title:{display:true,text:'2nd reading allocation (₱)'}},y:{type:'linear',title:{display:true,text:'3rd reading allocation (₱)'}}}}})}search.oninput=()=>{page=0;update()};sel.onchange=()=>{page=0;update()};document.getElementById('prev').onclick=()=>{page=Math.max(0,page-1);update()};document.getElementById('next').onclick=()=>{page++;update()};document.getElementById('csv').onclick=()=>{const list=filtered(),cols=['status','score_pct','second_title','third_title','second_amount_pesos','third_amount_pesos','delta_pesos','chainage_status','chainage_overlap','tranche_status','second_page','third_page'];const csv=[cols,...list.map(r=>[r.status,r.score_pct,r.second?.projectName||'',r.third?.projectName||'',r.second?.amountPesos||'',r.third?.amountPesos||'',r.amount_delta_pesos,r.chainage_status,r.chainage_overlap,r.tranche_status,r.second?.sourcePage||'',r.third?.sourcePage||''])].map(a=>a.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));a.download='dpwh_hgab_2nd_vs_3rd.csv';a.click();URL.revokeObjectURL(a.href)};update()}).catch(e=>{console.error(e);document.getElementById('metrics').textContent='Could not load the comparison data.'});
</script></body></html>'''
    new_rows = [row for row in comparison["rows"] if row["status"] == "New in 3rd reading"]
    removed_rows = [row for row in comparison["rows"] if row["status"] == "Only in 2nd reading"]
    new_total = sum(int((row.get("third") or {}).get("amountPesos") or 0) for row in new_rows)
    teaser = (f'<section class="card" style="margin:20px auto;padding:18px 22px;max-width:1250px;border-left:7px solid #f2ad4e">'
        f'<div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#087e78;font-weight:750">Corrected 2nd vs 3rd reading comparison</div>'
        f'<div style="font-size:52px;line-height:1.1;font-weight:820">{len(new_rows):,}</div>'
        f'<strong>line items listed in 3rd reading without a selected 2nd-reading counterpart</strong>'
        f'<p>Those lines total ₱{new_total/1_000_000:,.0f}M. {len(removed_rows):,} 2nd-reading lines have no selected 3rd-reading counterpart. These are extraction and title-screen results for document review.</p></section>')
    page = page.replace("__READING_TEASER__", teaser)
    (STATIC / "dpwh-hgab-comparison.html").write_text(page, encoding="utf-8")


def main() -> None:
    second = load_edition(ROOT / "hgab_2nd_editions.json")
    third = load_edition(ROOT / "hgab_3rd_editions.json")
    summaries = {}
    for group in ("fmr", "nia_named", "hfep", "nia_irrigation", "deped"):
        summaries[group] = compare_rows(second[group], third[group], "deped" if group == "deped" else group)
    write_json(OUT / "hgab_reading_revision_summary.json", {k: v["summary"] for k, v in summaries.items()})
    write_json(STATIC / "hgab-revision-data.json", summaries)

    # Historical GAA screen for the newly found NIA irrigation appendix.
    nia_now = [fields(row, 2027, "nia") for row in third["nia_irrigation"]]
    previous = [fields(row, 2025, "nia") for row in gaa25_nia()]
    matched = matches(nia_now, previous)
    best = {}
    for row in matched:
        key = row["line_id"]
        if key not in best or row["rank"] < best[key]["rank"]:
            best[key] = row
    repeats = [row for row in best.values() if row["similarity"] >= 0.62]
    write_json(STATIC / "nia-irrigation-data.json", {
        "revision": summaries["nia_irrigation"], "projects": second["nia_irrigation"] + third["nia_irrigation"],
        "repeatCandidates": repeats,
    })
    write_json(STATIC / "deped-data.json", summaries["deped"])

    write_dpwh_comparison_page()
    update_existing_pages(summaries)
    write_nia_page()
    write_deped_page()
    print("Built 3rd-reading comparison data and pages under ODV static/nep-preview")


def update_existing_pages(summaries: dict) -> None:
    # Put a live 3rd-reading summary before each retained 2nd-reading report.
    mapping = {"fmr.html": "fmr", "nia.html": "nia_named", "hfep.html": "hfep"}
    for filename, key in mapping.items():
        path = STATIC / filename
        html = path.read_text(encoding="utf-8")
        if 'id="edition-current"' in html:
            continue
        label = {"fmr": "FMR", "nia_named": "NIA named projects", "hfep": "HFEP"}[key]
        card = f'''<section id="edition-current" class="card section"><h2>{label}: 3rd Reading vs 2nd Reading</h2><p class="sub">3rd-reading allocations lead this page. The retained analysis below uses the 2nd-reading schedule and is marked as historical.</p><div class="grid metrics" id="editionMetrics"></div><figure class="comparison-graphic"><figcaption><strong>Schedule allocations by reading</strong><span>Totals and line counts from extracted schedules.</span></figcaption><div class="odv-chart"><canvas id="editionChart"></canvas></div></figure><div class="toolbar"><input id="editionSearch" type="search" placeholder="Filter title, status, or page"><select id="editionFilter"><option value="all">All rows</option><option>Allocation changed</option><option>Only in 3rd reading</option><option>Only in 2nd reading</option></select><button class="export-btn" id="editionCsv">Export filtered CSV</button></div><div class="tablewrap"><table><thead><tr><th>Status</th><th>Project / facility</th><th class="num">2nd reading</th><th class="num">3rd reading</th><th class="num">Change</th><th>Source pages</th></tr></thead><tbody id="editionBody"></tbody></table></div><p class="sub">FMR and HFEP NEP amounts are program envelopes; their named HGAB lines can itemize those envelopes and are not automatically new money. NIA titles indicate potential identity matches only; inspect phase, location, and scope.</p></section><h2 class="edition-archive-heading">Previous analysis · HGAB 2nd Reading</h2>'''
        html = html.replace('<main class="wrap">', '<main class="wrap">\n' + card, 1)
        html = html.replace('</body>', f'''<script>
fetch('hgab-revision-data.json').then(r=>r.json()).then(D=>{{const A=D.{key},s=A.summary,rows=A.rows;const fmt=n=>Number(n||0).toLocaleString('en-PH'),peso=n=>'₱'+fmt(n);document.getElementById('editionMetrics').innerHTML=[['2nd reading lines',fmt(s.secondRows)],['3rd reading lines',fmt(s.thirdRows)],['2nd schedule total',peso(s.secondTotal)],['3rd schedule total',peso(s.thirdTotal)]].map(x=>`<article class="card"><div class="metric-label">${{x[0]}}</div><div class="metric-value">${{x[1]}}</div></article>`).join('');const chart=new Chart(document.getElementById('editionChart'),{{type:'bar',data:{{labels:['2nd Reading','3rd Reading'],datasets:[{{label:'Schedule total (₱)',data:[s.secondTotal,s.thirdTotal],backgroundColor:['#355b92','#087e78']}}]}},options:{{responsive:true,maintainAspectRatio:false,scales:{{y:{{beginAtZero:true}}}}}}}});const body=document.getElementById('editionBody'),search=document.getElementById('editionSearch'),filter=document.getElementById('editionFilter');function draw(){{const q=search.value.toLowerCase(),f=filter.value,list=rows.filter(x=>(f==='all'||x.status===f)&&[x.status,x.name,x.secondPage,x.thirdPage].some(v=>String(v||'').toLowerCase().includes(q)));body.innerHTML=list.slice(0,400).map(x=>`<tr><td>${{x.status}}</td><td>${{x.name}}</td><td class="num">${{peso(x.secondAmount)}}</td><td class="num">${{peso(x.thirdAmount)}}</td><td class="num">${{peso(x.delta)}}</td><td>2nd p.${{x.secondPage||'—'}} · 3rd p.${{x.thirdPage||'—'}}</td></tr>`).join('')||'<tr><td colspan="6">No rows for this filter.</td></tr>'}}search.oninput=draw;filter.onchange=draw;document.getElementById('editionCsv').onclick=()=>{{const cols=['status','name','secondAmount','thirdAmount','delta','secondPage','thirdPage'];const list=rows.filter(x=>(filter.value==='all'||x.status===filter.value)&&[x.status,x.name,x.secondPage,x.thirdPage].some(v=>String(v||'').toLowerCase().includes(search.value.toLowerCase())));const csv=[cols,...list.map(x=>cols.map(k=>x[k]??''))].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\\r\\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+csv],{{type:'text/csv'}}));a.download='{key}_2nd_vs_3rd.csv';a.click();URL.revokeObjectURL(a.href)}};draw()}}).catch(e=>console.error(e));
</script></body>''', 1)
        html = html.replace('<a href="dpwh-hgab.html">DPWH · HGAB insertions</a>', '<a href="dpwh-hgab.html">NEP → HGAB (3rd)</a><a href="dpwh-hgab-comparison.html">DPWH 2nd vs 3rd</a><a href="nia-irrigation.html">NIA irrigation</a><a href="deped.html">DepEd</a>', 1)
        html = html.replace('FY 2027 · HB 10858 (HGAB)', 'FY 2027 · HB 10858 (3rd Reading)', 1)
        html = html.replace('Repeat screen: FY2027 HGAB against available FY2025 GAA.', 'Historical 2nd-reading repeat screen: FY2027 HGAB against available FY2025 GAA.', 1)
        if '/static/js/chart.js' not in html:
            html = html.replace('</head>', '<script src="/static/js/chart.js"></script></head>', 1)
        path.write_text(html, encoding="utf-8")


def common_page(title: str, h1: str, intro: str, data_file: str, nav: str, content: str, js: str) -> str:
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{intro}"><title>{title}</title><script src="/static/js/chart.js"></script><style>
:root{{--ink:#172b3a;--muted:#637381;--paper:#f4f6f5;--card:#fff;--line:#dce3e1;--teal:#087e78;--blue:#355b92}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}header{{background:#102f3e;color:#fff;padding:30px max(22px,calc((100vw - 1200px)/2))}}h1{{font-size:clamp(30px,4vw,46px);margin:8px 0}}header p{{color:#d1dfde;max-width:900px}}nav{{display:flex;flex-wrap:wrap;gap:15px}}nav a{{color:#a7ddd1}}main{{max-width:1200px;margin:auto;padding:22px}}.card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}}.metric-label{{font-size:13px;color:var(--muted)}}.metric-value{{font-size:24px;font-weight:750}}.charts{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.chart{{height:340px}}.toolbar{{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}}input,select,button{{font:inherit;padding:9px;border:1px solid var(--line);border-radius:6px}}button{{background:var(--teal);color:#fff;cursor:pointer}}table{{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px}}th,td{{padding:7px 6px;text-align:left;border-bottom:1px solid var(--line);overflow-wrap:anywhere;vertical-align:top}}th{{background:#eff4f2}}.num{{text-align:right;font-variant-numeric:tabular-nums}}.tablewrap{{max-height:70vh;overflow:auto}}.note{{font-size:13px;color:var(--muted)}}@media(max-width:800px){{.charts{{grid-template-columns:1fr}}main{{padding:12px}}}}
</style></head><body><header><div>FY 2027 · HB 10858 · 2nd and 3rd Reading schedules</div><h1>{h1}</h1><p>{intro}</p><nav>{nav}</nav></header><main>{content}</main><script>
fetch('{data_file}').then(r=>r.json()).then(D=>{{{js}}}).catch(e=>{{console.error(e);document.querySelector('main').insertAdjacentHTML('afterbegin','<p class="card">Could not load local comparison data.</p>')}});
</script></body></html>'''


def write_nia_page() -> None:
    nav = '<a href="dpwh.html">DPWH NEP patterns</a><a href="dpwh-hgab.html">NEP → HGAB</a><a href="dpwh-hgab-comparison.html">DPWH 2nd vs 3rd</a><a href="deped.html">DepEd</a><a href="fmr.html">FMR</a><a href="nia.html">NIA named projects</a><a href="hfep.html">HFEP</a>'
    content = '''<section class="card"><div class="metrics" id="metrics"></div><p class="note">This is a separate 423-row NIA irrigation-program appendix, apart from the 32-item named-project schedule in the main NIA report. It is a candidate extraction; verify title and amount on the cited page. Potential GAA matches are review leads, not confirmed repeats.</p></section><section class="charts"><article class="card chart"><h2>2nd vs 3rd reading allocations</h2><canvas id="scatter"></canvas></article><article class="card chart"><h2>3rd-reading candidate matches by confidence</h2><canvas id="repeatChart"></canvas></article></section><section class="card"><h2>Potential year-on-year matches · 3rd HGAB vs 2025 GAA</h2><div class="toolbar"><input id="repeatSearch" placeholder="Filter project or prior title"><button id="repeatCsv">Export CSV</button></div><div class="tablewrap"><table><thead><tr><th>NIA project line</th><th class="num">3rd HGAB</th><th>FY2025 GAA candidate</th><th class="num">2025 GAA</th><th>Match</th><th>Chainage</th><th>Tranche</th><th>Source pages</th></tr></thead><tbody id="repeatBody"></tbody></table></div></section><section class="card"><h2>Full irrigation-program line list</h2><div class="toolbar"><input id="allSearch" placeholder="Filter NIA project, station, or page"><select id="allEdition"><option value="3rd">3rd Reading</option><option value="2nd">2nd Reading</option></select><button id="allCsv">Export filtered lines</button></div><div class="tablewrap"><table><thead><tr><th>Project / work</th><th>Station / chainage</th><th class="num">Amount</th><th>Edition / page</th><th>2nd to 3rd change</th></tr></thead><tbody id="allBody"></tbody></table></div></section>'''
    js = r'''const peso=n=>'₱'+Number(n||0).toLocaleString('en-PH'),fmt=n=>Number(n||0).toLocaleString('en-PH'),rev=D.revision,rows=rev.rows,projects=D.projects,repeats=D.repeatCandidates;document.getElementById('metrics').innerHTML=[['3rd-reading line items',fmt(rev.summary.thirdRows)],['3rd-reading allocation',peso(rev.summary.thirdTotal)],['2nd-reading allocation',peso(rev.summary.secondTotal)],['Potential 2025 GAA title matches',fmt(repeats.length)]].map(x=>`<article><div class="metric-label">${x[0]}</div><div class="metric-value">${x[1]}</div></article>`).join('');const matched=rows.filter(x=>x.secondAmount&&x.thirdAmount);new Chart(document.getElementById('scatter'),{type:'scatter',data:{datasets:[{label:'Matched project titles',data:matched.map(x=>({x:x.secondAmount,y:x.thirdAmount})),backgroundColor:'#087e78'}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{title:{display:true,text:'2nd Reading (₱)'}},y:{title:{display:true,text:'3rd Reading (₱)'}}}}});new Chart(document.getElementById('repeatChart'),{type:'doughnut',data:{labels:['≥80% title similarity','62–79% title similarity'],datasets:[{data:[repeats.filter(x=>x.similarity>=.8).length,repeats.filter(x=>x.similarity<.8).length],backgroundColor:['#087e78','#e3a23b']}]},options:{responsive:true,maintainAspectRatio:false}});const repBody=document.getElementById('repeatBody'),repSearch=document.getElementById('repeatSearch');function drawRepeats(){const q=repSearch.value.toLowerCase(),list=repeats.filter(x=>(x.name+' '+x.prior_name).toLowerCase().includes(q)).slice(0,500);repBody.innerHTML=list.map(x=>`<tr><td>${x.name}</td><td class="num">${peso(x.amount)}</td><td>${x.prior_name}</td><td class="num">${peso(x.prior_amount)}</td><td>${Math.round(x.similarity*100)}%</td><td>${x.chainage_status||'not stated'}${x.chainage_overlap?'<br>'+x.chainage_overlap:''}</td><td>${x.tranche_status||'not stated'} ${x.tranche_detail||''}</td><td>${x.source}<br>${x.prior_source}</td></tr>`).join('')||'<tr><td colspan="8">No title candidates at the current filter.</td></tr>'}repSearch.oninput=drawRepeats;document.getElementById('repeatCsv').onclick=()=>exportRows(repeats.filter(x=>(x.name+' '+x.prior_name).toLowerCase().includes(repSearch.value.toLowerCase())),['name','amount','prior_name','prior_amount','similarity','chainage_status','chainage_overlap','tranche_status','tranche_detail','source','prior_source'],'nia_irrigation_2027_vs_2025_gaa.csv');const allSearch=document.getElementById('allSearch'),edition=document.getElementById('allEdition'),allBody=document.getElementById('allBody');function drawAll(){const q=allSearch.value.toLowerCase(),list=projects.filter(x=>(x.edition===edition.value)&&x.projectName.toLowerCase().includes(q));allBody.innerHTML=list.slice(0,500).map(x=>{const match=rows.find(r=>r.name===x.projectName);return `<tr><td>${x.projectName}</td><td>${(x.projectName.match(/(?:sta\.?|km)\s*\d[^)]*/gi)||[]).join('; ')||'—'}</td><td class="num">${peso(x.amountPesos)}</td><td>${x.edition} · p.${x.sourcePage}</td><td>${match?.status||'—'} · ${peso(match?.delta||0)}</td></tr>`}).join('')}allSearch.oninput=drawAll;edition.onchange=drawAll;document.getElementById('allCsv').onclick=()=>exportRows(projects.filter(x=>x.edition===edition.value&&x.projectName.toLowerCase().includes(allSearch.value.toLowerCase())),['edition','projectName','amountPesos','sourcePage','sourceText'],'nia_irrigation_schedule_'+edition.value+'.csv');function exportRows(rows,cols,name){const csv=[cols,...rows.map(r=>cols.map(k=>r[k]??''))].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));a.download=name;a.click();URL.revokeObjectURL(a.href)}drawRepeats();drawAll();'''
    page = common_page("NIA Irrigation Program · 2nd vs 3rd Reading", "NIA FY2027 Irrigation Program", "Review the detailed NIA irrigation works schedule, compare 2nd and 3rd readings, and inspect title matches against 2025 GAA. Amounts and titles require source-page verification.", "nia-irrigation-data.json", nav, content, js)
    (STATIC / "nia-irrigation.html").write_text(page, encoding="utf-8")


def write_deped_page() -> None:
    nav = '<a href="dpwh.html">DPWH NEP patterns</a><a href="dpwh-hgab.html">NEP → HGAB</a><a href="dpwh-hgab-comparison.html">DPWH 2nd vs 3rd</a><a href="nia-irrigation.html">NIA irrigation</a><a href="fmr.html">FMR</a><a href="nia.html">NIA</a><a href="hfep.html">HFEP</a>'
    content = '''<section class="card"><div class="metrics" id="metrics"></div><p class="note">This schedule allocates school operating budgets (junior-high personnel services, junior-high MOOE, junior-high total, and senior-high MOOE). It is not a school construction-project list. Compare bill-stage changes by school and verify table rows in Volume I-B before interpreting a change.</p></section><section class="charts"><article class="card chart"><h2>Allocation by region · 2nd vs 3rd</h2><canvas id="regionChart"></canvas></article><article class="card chart"><h2>Largest school allocation changes</h2><canvas id="changeChart"></canvas></article></section><section class="card"><h2>School-level allocation changes</h2><div class="toolbar"><input id="search" placeholder="Filter school, division, or region"><select id="region"><option value="all">All regions</option></select><select id="status"><option value="all">All change status</option></select><button id="csv">Export filtered CSV</button></div><div class="tablewrap"><table><thead><tr><th>Status</th><th>Region</th><th>School division / SDO</th><th>Secondary school</th><th class="num">2nd total</th><th class="num">3rd total</th><th class="num">Change</th><th>Page</th></tr></thead><tbody id="body"></tbody></table></div><p class="note">Showing up to 500 filtered schools at a time; CSV exports all filtered rows.</p></section>'''
    js = r'''const rows=D.rows,s=D.summary,peso=n=>'₱'+Number(n||0).toLocaleString('en-PH'),fmt=n=>Number(n||0).toLocaleString('en-PH');document.getElementById('metrics').innerHTML=[['Schools / allocation rows',fmt(s.thirdRows)],['2nd reading total',peso(s.secondTotal)],['3rd reading total',peso(s.thirdTotal)],['Net change',peso(s.thirdTotal-s.secondTotal)]].map(x=>`<article><div class="metric-label">${x[0]}</div><div class="metric-value">${x[1]}</div></article>`).join('');const regions=[...new Set(rows.map(r=>r.region).filter(Boolean))].sort(),regionSelect=document.getElementById('region'),statusSelect=document.getElementById('status');regionSelect.innerHTML+='<option value="__blank">Unclassified / missing</option>'+regions.map(r=>`<option>${r}</option>`).join('');statusSelect.innerHTML+=Object.keys(s.statusCounts).map(x=>`<option>${x}</option>`).join('');const byRegion={};for(const x of rows){const key=x.region||'Unclassified';byRegion[key]??={second:0,third:0};byRegion[key].second+=x.secondTotal;byRegion[key].third+=x.thirdTotal}new Chart(document.getElementById('regionChart'),{type:'bar',data:{labels:Object.keys(byRegion),datasets:[{label:'2nd Reading',data:Object.values(byRegion).map(x=>x.second),backgroundColor:'#355b92'},{label:'3rd Reading',data:Object.values(byRegion).map(x=>x.third),backgroundColor:'#087e78'}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y'}});const largest=[...rows].sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta)).slice(0,15);new Chart(document.getElementById('changeChart'),{type:'bar',data:{labels:largest.map(x=>x.name),datasets:[{label:'3rd minus 2nd (₱)',data:largest.map(x=>x.delta),backgroundColor:largest.map(x=>x.delta<0?'#bc604a':'#087e78')}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y'}});const search=document.getElementById('search'),body=document.getElementById('body');function filtered(){let q=search.value.toLowerCase(),reg=regionSelect.value,st=statusSelect.value;return rows.filter(x=>(reg==='all'||(reg==='__blank'&&!x.region)||x.region===reg)&&(st==='all'||x.status===st)&&[x.name,x.region,x.division,x.status].some(v=>String(v||'').toLowerCase().includes(q)))}function draw(){const list=filtered();body.innerHTML=list.slice(0,500).map(x=>`<tr><td>${x.status}</td><td>${x.region||'—'}</td><td>${x.division||'—'}</td><td>${x.name}</td><td class="num">${peso(x.secondTotal)}</td><td class="num">${peso(x.thirdTotal)}</td><td class="num">${peso(x.delta)}</td><td>p.${x.sourcePage||'—'}</td></tr>`).join('')}for(const el of [search,regionSelect,statusSelect])el.addEventListener(el===search?'input':'change',draw);document.getElementById('csv').onclick=()=>{const cols=['status','region','division','name','secondTotal','thirdTotal','delta','secondJhsPs','thirdJhsPs','secondJhsMooe','thirdJhsMooe','secondShsMooe','thirdShsMooe','sourcePage'],data=filtered(),csv=[cols,...data.map(x=>cols.map(k=>x[k]??''))].map(a=>a.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));a.download='deped_school_allocation_2nd_vs_3rd.csv';a.click();URL.revokeObjectURL(a.href)};draw();'''
    page = common_page("DepEd school allocations · 2nd vs 3rd Reading", "DepEd secondary-school allocations", "Compare the HGAB 2nd and 3rd reading school operating allocations by region, school division, and school. This schedule covers operating budgets, not construction projects.", "deped-data.json", nav, content, js)
    (STATIC / "deped.html").write_text(page, encoding="utf-8")


if __name__ == "__main__":
    main()
