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
from hgab_matching import is_fap

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
        if is_fap(r) or r["comparison"] != "No plausible NEP title counterpart; review candidate":
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


def prepare_dpwh_comparison_data() -> None:
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

    # The DPWH home page is owned by build_dpwh_indepth.py. Keep the
    # insertion comparison data in dpwh-data.json for its dedicated analysis
    # consumers, but do not patch dpwh.html from this reading-stage builder.

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



def render_dpwh_comparison_page() -> str:
    comparison = json.loads((STATIC / "dpwh-hgab-comparison.json").read_text(encoding="utf-8"))
    page = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>DPWH HGAB · 2nd vs 3rd Reading</title><script src="/static/js/chart.js"></script><style>
:root{--ink:#172b3a;--muted:#637381;--paper:#f4f6f5;--card:#fff;--line:#dce3e1;--teal:#087e78;--amber:#a65b08}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}header{background:#102f3e;color:#fff;padding:30px clamp(16px,3vw,44px)}h1{margin:8px 0;font-size:clamp(30px,4vw,46px)}header p{max-width:900px;color:#d1dfde}.report-nav{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));grid-auto-rows:34px;align-content:start;gap:8px 10px;height:76px;min-height:76px;margin-top:16px}.report-nav a{box-sizing:border-box;display:flex;min-width:0;height:34px;align-items:center;justify-content:center;padding:4px 7px;border:1px solid #ffffff55;border-radius:8px;color:#a7ddd1;text-align:center;text-decoration:none;font-size:12px;line-height:1.1;overflow-wrap:anywhere}@media(max-width:900px){.report-nav{grid-template-columns:repeat(3,minmax(0,1fr));grid-auto-rows:34px;height:160px;min-height:160px}}@media(max-width:560px){.report-nav{grid-template-columns:repeat(2,minmax(0,1fr));grid-auto-rows:34px;height:202px;min-height:202px}}.wrap{width:100%;max-width:none;margin:0;padding:24px clamp(16px,3vw,44px)}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-bottom:22px}.metric,.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}.label{color:var(--muted);font-size:13px}.value{font-size:30px;line-height:1.15;font-weight:750;letter-spacing:-.03em;margin-top:7px}.charts{display:grid;grid-template-columns:1.5fr 1fr;gap:16px;margin-bottom:16px}.chart{min-width:0}.chart-canvas{position:relative;width:100%;height:280px;max-height:280px}.toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.toolbar input,.toolbar select,button{font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:7px;background:#fff}.export{background:#087e78;color:#fff;border-color:#087e78}table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:12px}th,td{padding:8px 6px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere;text-align:left}th{background:#eff4f2;position:sticky;top:0}.num{font-variant-numeric:tabular-nums;text-align:right}.tablewrap{max-height:68vh;overflow:auto}.note{color:var(--muted);font-size:13px}.pagination{display:flex;justify-content:space-between;align-items:center;margin:12px 0}.pagination button{cursor:pointer}.danger{color:#8c4c06}@media(max-width:800px){.charts{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.wrap{padding:14px}table{font-size:11px}}
</style></head><body><header><div>FY2027 · HB 10858 · DPWH project schedule</div><h1>2nd Reading vs 3rd Reading</h1><p>Compare candidate DPWH line items across the two bill editions. Exact titles are paired first. Fuzzy title matches require chainage compatibility and no opposing direction; review all candidates against the PDF before treating them as the same project or a deletion/insertion.</p><nav class="report-nav" aria-label="Budget report pages"><a href="dpwh.html">DPWH · NEP patterns</a><a href="dpwh-hgab.html">DPWH · NEP → HGAB (3rd)</a><a href="dpwh-hgab-comparison.html">DPWH · HGAB 2nd vs 3rd</a><a href="nia-irrigation.html">NIA irrigation</a><a href="deped.html">DepEd</a><a href="rcs.html">RCS · POW scope review</a><a href="fmr.html">FMR</a><a href="nia.html">NIA</a><a href="hfep.html">HFEP</a><a href="budget-innovations.html">Budget Innovations</a></nav></header><main class="wrap">__READING_TEASER__<section class="metrics" id="metrics"></section><section class="charts"><article class="card chart"><h2>2nd vs 3rd allocations</h2><div class="chart-canvas"><canvas id="scatter"></canvas></div></article><article class="card chart"><h2>Line changes after filters</h2><div class="chart-canvas"><canvas id="statusChart"></canvas></div></article></section><article class="card"><h2>Line item changes</h2><p class="note">The corrected parser matches the printed 2nd and 3rd reading schedules. Disjoint station ranges are kept separate; package, phase, and segment changes remain review signals. “New in 3rd reading” is an extraction status; verify each cited page before interpreting it as an insertion.</p><div class="toolbar"><input id="search" type="search" placeholder="Filter title, office, or chainage"><select id="status"><option value="all">All statuses</option></select><button class="export" id="csv">Export filtered CSV</button></div><div class="tablewrap"><table><thead><tr><th>Status</th><th>2nd reading line</th><th>3rd reading line</th><th>2nd chainage</th><th>3rd chainage</th><th class="num">2nd amount</th><th class="num">3rd amount</th><th class="num">Change</th><th>Range check</th><th>Office / source</th></tr></thead><tbody id="body"></tbody></table></div><div class="pagination"><button id="prev">Previous</button><span id="range"></span><button id="next">Next</button></div></article></main><script>
fetch('dpwh-hgab-comparison.json').then(r=>r.json()).then(D=>{const rows=D.rows,s=D.summary;const peso=n=>'₱'+Number(n||0).toLocaleString('en-PH');const fmt=n=>Number(n||0).toLocaleString('en-PH');document.getElementById('metrics').innerHTML=[['2nd reading lines',fmt(s.secondCandidateCount)],['3rd reading lines',fmt(s.thirdCandidateCount)],['2nd reading allocations',peso(s.secondAllocationPesos)],['3rd reading allocations',peso(s.thirdAllocationPesos)]].map(x=>`<article class="metric"><div class="label">${x[0]}</div><div class="value">${x[1]}</div></article>`).join('');const statusSelect=document.getElementById('status');const statuses=[...new Set(rows.map(r=>r.status))];statusSelect.innerHTML+='<option value="changed">Changed rows only</option>'+statuses.map(x=>`<option>${x}</option>`).join('');const search=document.getElementById('search'),sel=statusSelect,body=document.getElementById('body'),range=document.getElementById('range');let page=0,size=40,a,b;function filtered(){const q=search.value.toLowerCase(),st=sel.value;return rows.filter(r=>(!st||st==='all'||(st==='changed'?r.status!=='Retained · same amount':r.status===st))&&[r.status,r.second?.projectName,r.third?.projectName,r.second?.office,r.third?.office,r.chainage_overlap].some(v=>String(v||'').toLowerCase().includes(q)))}function update(){const list=filtered();page=Math.min(page,Math.max(0,Math.ceil(list.length/size)-1));const start=page*size;body.innerHTML=list.slice(start,start+size).map(r=>`<tr><td>${r.status}<br>${r.score_pct?`${r.score_pct}% title`:''}</td><td>${r.second?.projectName||'—'}</td><td>${r.third?.projectName||'—'}</td><td>${r.second_chainage||'—'}</td><td>${r.third_chainage||'—'}</td><td class="num">${r.second?peso(r.second.amountPesos):'—'}</td><td class="num">${r.third?peso(r.third.amountPesos):'—'}</td><td class="num">${peso(r.amount_delta_pesos)}</td><td>${r.chainage_status}${r.chainage_overlap?'<br>overlap '+r.chainage_overlap:''}<br>${r.tranche_status}</td><td>${r.third?.office||r.second?.office||''}<br>${r.third?.sourcePage?`3rd p.${r.third.sourcePage}`:''} ${r.second?.sourcePage?`· 2nd p.${r.second.sourcePage}`:''}</td></tr>`).join('');range.textContent=`${list.length?start+1:0}–${Math.min(start+size,list.length)} of ${list.length}`;if(a)a.destroy();if(b)b.destroy();const stats={};for(const x of list)stats[x.status]=(stats[x.status]||0)+1;a=new Chart(document.getElementById('statusChart'),{type:'bar',data:{labels:Object.keys(stats),datasets:[{label:'Line items',data:Object.values(stats),backgroundColor:'#087e78'}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:'y'}});const points=list.filter(x=>x.second&&x.third).map(x=>({x:Number(x.second.amountPesos),y:Number(x.third.amountPesos)}));b=new Chart(document.getElementById('scatter'),{type:'scatter',data:{datasets:[{label:'Matched lines',data:points,backgroundColor:'#355b92'}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{type:'linear',title:{display:true,text:'2nd reading allocation (₱)'}},y:{type:'linear',title:{display:true,text:'3rd reading allocation (₱)'}}}}})}search.oninput=()=>{page=0;update()};sel.onchange=()=>{page=0;update()};document.getElementById('prev').onclick=()=>{page=Math.max(0,page-1);update()};document.getElementById('next').onclick=()=>{page++;update()};document.getElementById('csv').onclick=()=>{const list=filtered(),cols=['status','score_pct','second_title','third_title','second_amount_pesos','third_amount_pesos','delta_pesos','chainage_status','chainage_overlap','tranche_status','second_page','third_page'];const csv=[cols,...list.map(r=>[r.status,r.score_pct,r.second?.projectName||'',r.third?.projectName||'',r.second?.amountPesos||'',r.third?.amountPesos||'',r.amount_delta_pesos,r.chainage_status,r.chainage_overlap,r.tranche_status,r.second?.sourcePage||'',r.third?.sourcePage||''])].map(a=>a.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv'}));a.download='dpwh_hgab_2nd_vs_3rd.csv';a.click();URL.revokeObjectURL(a.href)};update()}).catch(e=>{console.error(e);document.getElementById('metrics').textContent='Could not load the comparison data.'});
</script></body></html>'''
    new_rows = [row for row in comparison["rows"] if row["status"] == "New in 3rd reading"]
    removed_rows = [row for row in comparison["rows"] if row["status"] == "Only in 2nd reading"]
    new_total = sum(int((row.get("third") or {}).get("amountPesos") or 0) for row in new_rows)
    teaser = (f'<section class="card" style="margin:20px 0;padding:18px 22px;width:100%;border-left:7px solid #f2ad4e">'
        f'<div style="font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#087e78;font-weight:750">Corrected 2nd vs 3rd reading comparison</div>'
        f'<div style="font-size:52px;line-height:1.1;font-weight:820">{len(new_rows):,}</div>'
        f'<strong>line items listed in 3rd reading without a selected 2nd-reading counterpart</strong>'
        f'<p>Those lines total ₱{new_total/1_000_000:,.0f}M. {len(removed_rows):,} 2nd-reading lines have no selected 3rd-reading counterpart. These are extraction and title-screen results for document review.</p></section>')
    page = page.replace("__READING_TEASER__", teaser)
    return page


def main() -> None:
    second = load_edition(ROOT / "hgab_2nd_editions.json")
    third = load_edition(ROOT / "hgab_3rd_editions.json")
    summaries = {}
    for group in ("fmr", "nia_named", "hfep", "nia_irrigation", "deped"):
        summaries[group] = compare_rows(second[group], third[group], "deped" if group == "deped" else group)
    write_json(OUT / "hgab_reading_revision_summary.json", {k: v["summary"] for k, v in summaries.items()})
    write_json(STATIC / "hgab-revision-data.json", summaries)
    prepare_dpwh_comparison_data()

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

    # HTML output is deliberately delegated to one-page builders. This script
    # only prepares shared schedule and comparison JSON inputs.
    print("Built HGAB reading-revision data; run the owning page builders to render HTML")


if __name__ == "__main__":
    main()
