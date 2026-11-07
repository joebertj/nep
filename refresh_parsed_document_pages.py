#!/usr/bin/env python3
"""Refresh each parsed-document report through its owning page builder.

This is an orchestrator only: it calls one-page builders in dependency order
and never writes report HTML itself.
"""
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "analysis_output"
STATIC = ROOT.parent / "open-data-visualization/static/nep-preview"
STATUS = OUT / "parsed-document-page-refresh-status.json"
LOCK = OUT / ".parsed-document-page-refresh.lock"


def now():
    return datetime.now(timezone.utc).isoformat()


def write_status(data):
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(STATUS)


def run_builder(script):
    result = subprocess.run(
        [sys.executable, str(ROOT / script)], cwd=ROOT,
        capture_output=True, text=True, check=True,
    )
    try:
        summary = json.loads(result.stdout)
    except (ValueError, TypeError):
        summary = {"output": result.stdout[-2000:]}
    return summary


def validate_page_outputs():
    expected_headers = ["HGAB code", "Project", "Office · region", "HGAB allocation",
                        "Proposal docs", "Senate HGAB docs",
                        "Signatories in related documents"]
    checks = {}
    for name in ("dpwh.html", "undocumented-hgab.html"):
        text = (STATIC / name).read_text()
        section_id = "all-hgab-document-coverage"
        section_start = text.find(f'id="{section_id}"')
        section_end = text.find("</section>", section_start)
        section = text[section_start:section_end] if section_start >= 0 and section_end >= 0 else ""
        import re
        head = re.search(r"<thead>(.*?)</thead>", section, re.S)
        headers = [re.sub(r"<[^>]+>", "", cell).strip()
                   for cell in re.findall(r"<th\b[^>]*>(.*?)</th>", head.group(1), re.S)] if head else []
        if headers != expected_headers:
            raise RuntimeError(f"{name} coverage columns changed: {headers!r}")
        checks[name] = {"coverageColumns": len(headers)}

    dpwh = (STATIC / "dpwh.html").read_text()
    import re
    main = re.search(r"<main\b[^>]*>(.*?)</main>", dpwh, re.S)
    final_sections = re.findall(r'<section\b[^>]*id="([^"]+)"[^>]*>', main.group(1), re.S) if main else []
    if not final_sections or final_sections[-1] != "all-hgab-document-coverage":
        raise RuntimeError(f"DPWH final section must be all-hgab-document-coverage; found {final_sections[-1:]!r}")
    checks["dpwh.html"]["finalSection"] = final_sections[-1]

    coverage_js = (STATIC / "hgab-document-coverage.js").read_text()
    if "<td>'+signatoryCell+'</td></tr>'" not in coverage_js or "colspan=\"7\"" not in coverage_js:
        raise RuntimeError("All-HGAB coverage row renderer must retain seven columns")

    summary = (STATIC / "summary.html").read_text()
    summary_data = json.loads((STATIC / "summary-data.json").read_text())
    cards = summary.count('<article class="finding"')
    agencies = len(summary_data.get("agencyComparisonCoverage", []))
    if cards != 8 or len(summary_data.get("findings", [])) != 8 or agencies != 5:
        raise RuntimeError(f"Summary contract changed: {cards} cards, {agencies} agency comparisons")
    checks["summary.html"] = {"cards": cards, "agencyComparisons": agencies}

    unit_page = (STATIC / "cost-per-unit.html").read_text()
    selector = re.search(r'<select\b[^>]*id="unit-page-size"[^>]*>(.*?)</select>', unit_page, re.S)
    if not selector or not re.search(r'<option\b[^>]*value="20"[^>]*selected', selector.group(1)):
        raise RuntimeError("Cost per unit Projects with this bill page size must remain 20")

    from audit_document_page_stats import audit as audit_document_stats
    audit = audit_document_stats()
    if audit['errors']:
        raise RuntimeError('Parsed-document statistics audit failed: ' + '; '.join(
            f"{item['code']}: {item['detail']}" for item in audit['errors']))
    checks['documentPageStatsAudit'] = {'status': audit['status'], 'checkedPages': len(audit['pages'])}

    # The published ODV copies receive site navigation, attribution and
    # cache-busting transforms, so byte equality with the analysis mirrors is
    # not a valid contract. Validate the actual published structures above.
    return checks


def refresh(source="unspecified"):
    OUT.mkdir(parents=True, exist_ok=True)
    with LOCK.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        status = {"status": "refreshing", "startedAtUtc": now(),
                  "pid": __import__("os").getpid(),
                  "source": source,
                  "builders": {}}
        write_status(status)
        try:
            for script in (
                "build_dpwh_indepth.py",
                "build_dpwh_transparency_page.py",
                "build_cost_per_unit_page.py",
                "build_pccp_cost_per_unit_page.py",
                "build_expectation_vs_reality.py",
                "build_development_council.py",
                "build_undocumented_hgab.py",
                "build_investigation_summary.py",
            ):
                status["activeBuilder"] = script
                status["heartbeatAtUtc"] = now()
                write_status(status)
                status["builders"][script] = run_builder(script)
            status["outputContracts"] = validate_page_outputs()
            status.update({"status": "complete", "completedAtUtc": now(),
                           "activeBuilder": None, "lastError": None})
            write_status(status)
            return status
        except Exception as exc:
            status.update({"status": "error", "completedAtUtc": now(),
                           "lastError": f"{type(exc).__name__}: {exc}"})
            write_status(status)
            raise


def main():
    source = sys.argv[1] if len(sys.argv) > 1 else "unspecified"
    print(json.dumps(refresh(source), ensure_ascii=False))


if __name__ == "__main__":
    main()
