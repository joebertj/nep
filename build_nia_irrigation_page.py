#!/usr/bin/env python3
"""Build only the NIA irrigation HTML page from prepared shared data."""
from pathlib import Path
from standardize_nep_hgab_pages import render_page

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'


def build():
    page, summary = render_page('nia-irrigation.html')
    from build_reviewed_annex_sections import apply_page as apply_reviewed_annex_section
    page = apply_reviewed_annex_section(page, 'nia-irrigation.html')
    from build_nep_stage_sections import apply_page as apply_nep_stage_section
    page = apply_nep_stage_section(page, 'nia-irrigation.html')
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module('nia-irrigation.html',page)
    (STATIC / 'nia-irrigation.html').write_text(page, encoding='utf-8')
    (OUT / 'nia-irrigation.html').write_text(page, encoding='utf-8')
    return summary


if __name__ == '__main__':
    import json
    print(json.dumps(build(), ensure_ascii=False))
