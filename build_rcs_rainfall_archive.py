#!/usr/bin/env python3
"""Build the archived rainfall-scenario page and its data through its owner."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / "open-data-visualization/static/nep-preview"
OUT = ROOT / "analysis_output"


def build():
    from build_rcs_analysis import build_data, page_html

    data = build_data()
    page = page_html()
    source_title = "<title>Rainwater Collector System · Rainfall allocation scenario</title>"
    if source_title not in page:
        raise RuntimeError("RCS source page title changed; update the archive page builder")
    page = page.replace(source_title, "<title>Archived rainfall scenario · Rainwater Collector System</title>", 1)
    source_fetch = "fetch('rcs-data.json')"
    if source_fetch not in page:
        raise RuntimeError("RCS source page data endpoint changed; update the archive page builder")
    page = page.replace(source_fetch, "fetch('rcs-rainfall-archive-data.json')", 1)

    from uniform_report_menu import apply_page as apply_menu
    page = apply_menu(page, "rcs-rainfall-archive.html")
    from report_table_presentation import apply_page_table_module
    page, table_contract = apply_page_table_module("rcs-rainfall-archive.html", page)

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (STATIC / "rcs-rainfall-archive.html").write_text(page, encoding="utf-8")
    (OUT / "rcs-rainfall-archive.html").write_text(page, encoding="utf-8")
    (STATIC / "rcs-rainfall-archive-data.json").write_text(payload, encoding="utf-8")
    (OUT / "rcs-rainfall-archive-data.json").write_text(payload, encoding="utf-8")
    return {"page": "rcs-rainfall-archive.html", "tableContract": table_contract,
            "generatedAtUtc": data.get("generatedAtUtc")}


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False))
