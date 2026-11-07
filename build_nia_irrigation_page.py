#!/usr/bin/env python3
"""Build only the NIA irrigation HTML page from prepared shared data."""
from pathlib import Path
from standardize_nep_hgab_pages import render_page

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'


def build():
    page, summary = render_page('nia-irrigation.html')
    (STATIC / 'nia-irrigation.html').write_text(page, encoding='utf-8')
    (OUT / 'nia-irrigation.html').write_text(page, encoding='utf-8')
    return summary


if __name__ == '__main__':
    import json
    print(json.dumps(build(), ensure_ascii=False))
