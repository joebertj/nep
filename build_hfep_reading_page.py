#!/usr/bin/env python3
"""Build only the HFEP page's House-reading comparison section."""
import json
from pathlib import Path
from hgab_revision_page_module import render_reading_revision_overlay

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'


def build():
    path = STATIC / 'hfep.html'
    page = path.read_text(encoding='utf-8')
    if not (STATIC / 'nep-agency-baselines.json').exists():
        page = render_reading_revision_overlay(page, 'hfep')
    path.write_text(page, encoding='utf-8')
    (OUT / path.name).write_text(page, encoding='utf-8')
    return {'page': path.name}


if __name__ == '__main__':
    print(json.dumps(build()))
