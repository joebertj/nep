#!/usr/bin/env python3
"""Build only the Historical district totals ranking page."""
import hashlib
import json
import re

from build_integrated_district_reports import ROOT, STATIC, build as build_data

PAGE = 'integrated-district-totals.html'
TEMPLATE = ROOT / 'report_assets' / PAGE


def build_page(data=None):
    # Data generation writes only the two JSON datasets; this entry point owns
    # the HTML for the district totals page.
    data = data or build_data()
    html = TEMPLATE.read_text(encoding='utf-8')
    for filename in ('integrated-district-data.json', 'integrated-project-data.json'):
        version = hashlib.sha256((STATIC / filename).read_bytes()).hexdigest()[:12]
        html = re.sub(
            rf"fetch\('{re.escape(filename)}(?:\?v=[^']*)?'\)",
            f"fetch('{filename}?v={version}')",
            html,
        )
    from uniform_report_menu import apply_page
    html = apply_page(html, PAGE)
    from report_table_presentation import apply_page_table_module
    html, contract = apply_page_table_module(PAGE, html)
    for destination in (STATIC / PAGE, ROOT / 'analysis_output' / PAGE):
        destination.write_text(html, encoding='utf-8')
    return {
        'page': PAGE,
        'districts': len(data.get('districts', [])),
        'periods': len(data.get('periods', [])),
        'tableContract': contract,
    }


if __name__ == '__main__':
    print(json.dumps(build_page(), ensure_ascii=False, indent=2))
