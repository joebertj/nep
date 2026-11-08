#!/usr/bin/env python3
"""Build only the historical MPB allocation report and its data assets."""
import json

from mpb_historical_page_module import build_page as render_page
from build_mpb_report import OUT, STATIC


def build_page():
    render_page()
    page = (STATIC / 'mpb-historical.html').read_text(encoding='utf-8')
    from report_table_presentation import apply_page_table_module
    page, contract = apply_page_table_module('mpb-historical.html', page)
    for destination in (STATIC / 'mpb-historical.html', OUT / 'mpb-historical.html'):
        destination.write_text(page, encoding='utf-8')
    return {'page': 'mpb-historical.html', 'tableContract': contract}


if __name__ == '__main__':
    print(json.dumps(build_page(), ensure_ascii=False, indent=2))
