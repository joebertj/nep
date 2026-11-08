#!/usr/bin/env python3
"""Rebuild the retained archive page from its local source copy."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "analysis_output/archive.html"
OUTPUT = ROOT.parent / "open-data-visualization/static/nep-preview/archive.html"


def build():
    html = SOURCE.read_text(encoding="utf-8")
    html = re.sub(
        r'<p>These focused reports remain available; Out of Place is also linked in the main menu\.</p>',
        '<p>These focused reports remain available.</p>', html)
    html = re.sub(
        r'<li><a href="out-of-place\.html"><strong>Out of Place</strong></a> · Projects with coordinates outside their intended location</li>',
        '', html)
    if "Out of Place" in html and re.search(
            r'<section[^>]*id="additional-reports".*?Out of Place', html, re.S):
        raise RuntimeError("Out of Place still appears in the archive's Additional reports section")

    from report_table_presentation import apply_page_table_module
    html, contract = apply_page_table_module("archive.html", html)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(html, encoding="utf-8")
    SOURCE.write_text(html, encoding="utf-8")
    return {"page": OUTPUT.name, "outOfPlaceArchived": False, **contract}


if __name__ == "__main__":
    import json
    print(json.dumps(build(), ensure_ascii=False))
