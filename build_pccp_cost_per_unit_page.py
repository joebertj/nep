#!/usr/bin/env python3
"""Build only the DPWH Atlas cost-per-unit page and its price data."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def build():
    from build_dpwh_indepth import publish_pccp_price_reference
    from report_table_presentation import apply_page as apply_tables, publish_assets
    from uniform_report_menu import apply_page as apply_menu

    publish_pccp_price_reference()
    script = ROOT / 'project_documents/cost-per-unit.js'
    cost_js = script.read_text(encoding='utf-8')
    indepth_js = (ROOT / 'project_documents/indepth.js').read_text(encoding='utf-8')
    loader = (ROOT / 'project_documents/dpwh-data-loader.js').read_text(encoding='utf-8')
    data = (OUT / 'dpwh-in-depth-data.json').read_bytes()
    loader_version = hashlib.sha256((loader + '\n' + hashlib.sha256(data).hexdigest()).encode()).hexdigest()[:12]
    page = (ROOT / 'project_documents/pccp-cost-per-unit.html').read_text(encoding='utf-8')
    page = page.replace('src="cost-per-unit.js"',
                        f'src="cost-per-unit.js?v={hashlib.sha256(cost_js.encode()).hexdigest()[:12]}"')
    page = re.sub(r'src="dpwh-in-depth\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-in-depth.js?v={hashlib.sha256(indepth_js.encode()).hexdigest()[:12]}"', page, count=1)
    page = re.sub(r'src="dpwh-data-loader\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-data-loader.js?v={loader_version}"', page, count=1)
    page = apply_tables(apply_menu(page, 'pccp-cost-per-unit.html'), publish_assets())
    for target in (OUT, STATIC):
        target.mkdir(parents=True, exist_ok=True)
        (target / 'cost-per-unit.js').write_text(cost_js, encoding='utf-8')
        (target / 'pccp-cost-per-unit.html').write_text(page, encoding='utf-8')
    return {'page': 'pccp-cost-per-unit.html'}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
