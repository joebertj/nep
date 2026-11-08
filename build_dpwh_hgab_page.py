#!/usr/bin/env python3
"""Apply reading-stage context and write only dpwh-hgab.html."""
import json
from pathlib import Path
from dpwh_hgab_revision_module import render_revision_context

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'


def build():
    page_path = STATIC / 'dpwh-hgab.html'
    data = json.loads((STATIC / 'dpwh-data.json').read_text(encoding='utf-8'))
    page = render_revision_context(page_path.read_text(encoding='utf-8'), data)
    # Compose this page's DPWH↔HGAB evidence modules in dependency order.
    # Each module returns HTML and may refresh its own data exports; only this
    # builder publishes dpwh-hgab.html.
    from build_dpwh_fap_review import refresh as render_fap_review
    from build_dpwh_subtractions import refresh as render_subtractions
    from build_dpwh_allocation_adjustments import refresh as render_allocation_adjustments
    from build_dpwh_hgab_headlines import refresh as render_headlines
    page = render_fap_review(page)
    page = render_subtractions(page)
    page = render_allocation_adjustments(page)
    page = render_headlines(page)
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module(page_path.name,page)
    page_path.write_text(page, encoding='utf-8')
    (OUT / page_path.name).write_text(page, encoding='utf-8')
    return {'page': page_path.name, 'unmatchedRows': len(data.get('hbInsertions', []))}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
