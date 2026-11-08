#!/usr/bin/env python3
"""Build only the DepEd HTML page from prepared shared data."""
from pathlib import Path
from standardize_nep_hgab_pages import render_page

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'


def build():
    page, summary = render_page('deped.html')
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module('deped.html',page)
    (STATIC / 'deped.html').write_text(page, encoding='utf-8')
    (OUT / 'deped.html').write_text(page, encoding='utf-8')
    return summary


if __name__ == '__main__':
    import json
    print(json.dumps(build(), ensure_ascii=False))
