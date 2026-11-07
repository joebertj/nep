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
    page_path.write_text(page, encoding='utf-8')
    (OUT / page_path.name).write_text(page, encoding='utf-8')
    return {'page': page_path.name, 'unmatchedRows': len(data.get('hbInsertions', []))}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
