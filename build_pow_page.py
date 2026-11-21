#!/usr/bin/env python3
"""Build the POW forensics page with separate Proposal and Senate HGAB evidence."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / "open-data-visualization/static/nep-preview"
TEMPLATE = ROOT / "report_assets/pow_page_template.html"
INDEPTH = STATIC / "dpwh-in-depth-data.json"
DATA_OUT = STATIC / "pow-hgab-parsed-documents.json"
PRINTED_DATES_OUT = STATIC / "pow-printed-dates.json"
STATS_OUT = STATIC / "senate-hgab-pow-stats.json"
JS_SOURCE = ROOT / "report_assets/pow_hgab_documents.js"
REUSE_JS_SOURCE = ROOT / "report_assets/pow_document_reuse.js"

SECTION = '''<section class="card" id="senate-hgab-parsed-pows"><h2>2. Senate-provided HGAB POW files · parsed results</h2><p>One row per parsed Senate HGAB POW file. The title link records the parser’s current match status; it does not verify the extracted bill rows or the project scope. Proposal PDF metadata and image-forensics above remain a separate corpus.</p><div id="hgab-pow-summary" class="scope" aria-live="polite"><p class="muted">Loading Senate HGAB POW results…</p></div><div class="controls"><input id="hgab-pow-query" type="search" placeholder="Search HGAB file code or matched project title"><select id="hgab-pow-match"><option value="">All title-match statuses</option></select><span id="hgab-pow-count" class="muted" aria-live="polite"></span></div><div class="controls"><button id="hgab-pow-export" type="button">Download all HGAB POW records as JSON</button><button id="hgab-pow-prev" type="button">Previous</button><span id="hgab-pow-page" class="muted" aria-live="polite"></span><button id="hgab-pow-next" type="button">Next</button></div><div class="tablewrap"><table id="hgab-pow-table"><thead><tr><th>HGAB file code</th><th>Matched HGAB project title</th><th>Title match</th><th>Parser status</th><th>Bill rows</th><th>Category-summary rows</th><th>PDF pages</th><th>Printed date(s) · page</th><th>Proposal counterpart</th></tr></thead><tbody><tr><td colspan="9">Loading Senate HGAB POW records…</td></tr></tbody></table></div><p class="muted">Files with no accepted title match remain listed by HGAB file code and are not assigned to project rows. Direct Senate file links and storage paths are not published.</p></section>'''


def compact_document(record):
    return {
        "code": record.get("code"),
        "status": record.get("status"),
        "pageCount": record.get("pageCount"),
        "matchStatus": record.get("matchStatus"),
        "hgabId": record.get("hgabId"),
        "hgabTitle": record.get("hgabTitle"),
        "candidateHgabIds": record.get("candidateHgabIds") or [],
        "cohortStatus": record.get("cohortStatus"),
        "proposalCode": record.get("proposalCode"),
        "rowCount": len(record.get("rows") or []),
        "categorySummaryRowCount": len(record.get("costCategoryBreakdown") or []),
    }


def build():
    index = json.loads(INDEPTH.read_text(encoding="utf-8"))
    records = []
    for shard in index.get("arrayShards", {}).get("hgabPowResults", []):
        shard_path = STATIC / shard["path"]
        records.extend(compact_document(record) for record in json.loads(shard_path.read_text(encoding="utf-8")))
    records.sort(key=lambda record: record.get("code") or "")
    statuses = Counter(record.get("status") or "unknown" for record in records)
    matches = Counter(record.get("matchStatus") or "unknown" for record in records)
    matched_projects = {record["hgabId"] for record in records if record.get("hgabId")}
    stats = {
        "generatedAtUtc": index.get("generatedAtUtc"),
        "source": "Current published DPWH in-depth data and parsed Senate HGAB POW result shards",
        "parsedDocuments": len(records),
        "documentsWithBillRows": sum(record["rowCount"] > 0 for record in records),
        "billRows": sum(record["rowCount"] for record in records),
        "printedCategories": sum(record["categorySummaryRowCount"] for record in records),
        "parserStatuses": dict(statuses),
        "titleMatchStatuses": dict(matches),
        "filesWithAcceptedHgabTitleMatch": sum(bool(record.get("hgabId")) for record in records),
        "uniqueMatchedHgabProjectRows": len(matched_projects),
        "rowsWithProposalCounterpart": sum(bool(record.get("proposalCode")) for record in records),
        "scopeNote": "Counts summarize parsed file records. A parsed file can have no matched HGAB project row; accepted title matches are unverified and do not establish document contents.",
    }

    existing_stats = json.loads(STATS_OUT.read_text(encoding="utf-8")) if STATS_OUT.exists() else {}
    # Preserve the separate title-scan audit fields and its original timestamp.
    existing_stats.update({key: value for key, value in stats.items()
                           if key not in {"generatedAtUtc", "source", "scopeNote"}})
    existing_stats["parserDataUpdatedAtUtc"] = index.get("generatedAtUtc")
    existing_stats["parserSource"] = stats["source"]
    STATS_OUT.write_text(json.dumps(existing_stats, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    payload = {"summary": stats, "documents": records}
    DATA_OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    scan_path = ROOT / "analysis_output/senate_supporting_documents_hgab_only_scan.json"
    scan = json.loads(scan_path.read_text(encoding="utf-8")) if scan_path.is_file() else {"documents": []}
    dates_by_code = {}
    for source in scan.get("documents", []):
        if source.get("documentType") != "POW":
            continue
        code = str(source.get("projectCode") or "").upper()
        if not code:
            continue
        entry = dates_by_code.setdefault(code, {"files": set(), "dates": {}})
        entry["files"].add(Path(str(source.get("file") or "")).name)
        for date in source.get("printedDates") or []:
            label = str(date.get("printedDate") or "").strip()
            if not label:
                continue
            item = entry["dates"].setdefault(label, {"isoDate": date.get("isoDate"), "pages": set()})
            if date.get("sourcePage") is not None:
                item["pages"].add(int(date["sourcePage"]))
    printed_dates = {"source": "34,317-PDF supporting-document reparse; printed dates extracted from PDF text/OCR", "byCode": {
        code: {"files": sorted(entry["files"]), "dates": [
            {"printedDate": label, "isoDate": value["isoDate"], "sourcePages": sorted(value["pages"])}
            for label, value in sorted(entry["dates"].items(), key=lambda pair: (pair[1]["isoDate"] or "", pair[0]))
        ]} for code, entry in dates_by_code.items()
    }}
    PRINTED_DATES_OUT.write_text(json.dumps(printed_dates, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ROOT / "analysis_output/pow-hgab-parsed-documents.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (ROOT / "analysis_output/senate-hgab-pow-stats.json").write_text(
        json.dumps(existing_stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    page = TEMPLATE.read_text(encoding="utf-8")
    if 'id="senate-hgab-parsed-pows"' not in page:
        insertion_point = '<section class="card"><h2>4. What this investigation can establish</h2>'
        if insertion_point not in page:
            raise RuntimeError("POW page template is missing the expected insertion point")
        page = page.replace(insertion_point, SECTION + "\n" + insertion_point, 1)
    allocation_section = '''<section class="card" id="allocation-vs-pow-tec" aria-labelledby="allocation-vs-pow-tec-heading"><h2 id="allocation-vs-pow-tec-heading">3. HGAB allocation vs POW total estimated cost</h2><p>This aggregate comparison uses the recovered I. TOTAL ESTIMATED COST · As Submitted from matched POWs, compared with the House 3rd-reading allocation. It is a cross-reference to the project-level expectation-vs-reality analysis; it does not compare allocation with the A+B+C category summary alone.</p><div id="allocation-vs-pow-tec-metrics" class="scope" aria-live="polite"><p class="muted">Loading aggregate comparison…</p></div><p id="allocation-vs-pow-tec-note" class="muted">The POW total is an estimate. Differences can reflect scope, phase, or cost basis and do not establish spending or overrun.</p><p><a href="expectation-vs-reality.html">Open the project-level expectation vs reality comparison ↗</a></p></section>'''
    if 'id="allocation-vs-pow-tec"' not in page:
        insertion_point = '<section class="card"><h2>4. What this investigation can establish</h2>'
        if insertion_point not in page:
            raise RuntimeError("POW page template is missing the aggregate comparison insertion point")
        page = page.replace(insertion_point, allocation_section + "\n" + insertion_point, 1)
    page = page.replace(
        "This is the local DPWH forensic snapshot; it does not count Senate HGAB files or establish that each POW was fully parsed.",
        "This Proposal-only forensic snapshot does not count Senate HGAB PDFs; their parsed records are listed separately above.")
    script = JS_SOURCE.read_text(encoding="utf-8")
    dates_version = __import__("hashlib").sha256(PRINTED_DATES_OUT.read_bytes()).hexdigest()[:12]
    script = script.replace("__PRINTED_DATES_VERSION__", dates_version)
    (STATIC / "pow-hgab-parsed-documents.js").write_text(script, encoding="utf-8")
    version = __import__("hashlib").sha256(script.encode("utf-8")).hexdigest()[:12]
    reuse_script = REUSE_JS_SOURCE.read_text(encoding="utf-8")
    (STATIC / "pow-document-reuse.js").write_text(reuse_script, encoding="utf-8")
    reuse_version = __import__("hashlib").sha256(reuse_script.encode("utf-8")).hexdigest()[:12]
    allocation_script = (ROOT / "report_assets/pow_allocation_comparison.js").read_text(encoding="utf-8")
    (STATIC / "pow_allocation_comparison.js").write_text(allocation_script, encoding="utf-8")
    allocation_version = __import__("hashlib").sha256(allocation_script.encode("utf-8")).hexdigest()[:12]
    page = page.replace("</body>", f'''<script>
window.__showPowComparisonUnavailable=()=>{{
 const summary=document.getElementById('hgab-pow-summary'),table=document.querySelector('#hgab-pow-table tbody'),metrics=document.getElementById('token-pow-metrics'),tokenTable=document.querySelector('#token-pow-table tbody');
 if(summary)summary.innerHTML='<p class="caution">POW comparison data could not be initialized. Reload the page to retry.</p>';
 if(table)table.innerHTML='<tr><td colspan="9">POW comparison data is unavailable.</td></tr>';
 if(metrics)metrics.innerHTML='<p class="caution">5/5 comparison data could not be initialized. Reload the page to retry.</p>';
 if(tokenTable)tokenTable.innerHTML='<tr><td colspan="4">5/5 comparison data is unavailable.</td></tr>';
}};
setTimeout(()=>{{
 const pending=['hgab-pow-summary','#hgab-pow-table tbody','token-pow-metrics','#token-pow-table tbody'].some(selector=>{{const node=selector.startsWith('#')?document.querySelector(selector):document.getElementById(selector);return /Loading|Comparing/i.test(node?.textContent||'')}});
 if(pending)window.__showPowComparisonUnavailable();
}},40000);
</script><script src="pow-hgab-parsed-documents.js?v={version}" defer onerror="window.__showPowComparisonUnavailable()"></script><script src="pow_allocation_comparison.js?v={allocation_version}" defer></script></body>''', 1)

    from report_table_presentation import apply_page_table_module
    page, table_contract = apply_page_table_module("pow.html", page)
    from uniform_report_menu import apply_page as apply_uniform_menu
    page = apply_uniform_menu(page, "pow.html")
    (STATIC / "pow.html").write_text(page, encoding="utf-8")
    (ROOT / "analysis_output/pow.html").write_text(page, encoding="utf-8")
    return {"page": "pow.html", **stats, "tableContract": table_contract}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
