#!/usr/bin/env python3
"""Build only the DPWH Transparency report page from its source template."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def build():
    from report_table_presentation import apply_page as apply_tables, publish_assets
    from uniform_report_menu import apply_page as apply_menu

    data = json.loads((OUT / 'dpwh-in-depth-data.json').read_text(encoding='utf-8'))
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    data_version = hashlib.sha256(serialized.encode()).hexdigest()[:12]
    indepth = (ROOT / 'project_documents/indepth.js').read_text(encoding='utf-8')
    loader = (ROOT / 'project_documents/dpwh-data-loader.js').read_text(encoding='utf-8')
    loader_version = hashlib.sha256((loader + '\n' + hashlib.sha256(serialized.encode()).hexdigest()).encode()).hexdigest()[:12]
    page = (ROOT / 'project_documents/transparency.html').read_text(encoding='utf-8')
    page = re.sub(r'src="dpwh-in-depth\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-in-depth.js?v={hashlib.sha256(indepth.encode()).hexdigest()[:12]}"', page, count=1)
    page = re.sub(r'src="dpwh-data-loader\.js(?:\?v=[^"]*)?"',
                  f'src="dpwh-data-loader.js?v={loader_version}"', page, count=1)
    page = apply_tables(apply_menu(page, 'dpwh-transparency.html'), publish_assets())
    for target in (OUT, STATIC):
        target.mkdir(parents=True, exist_ok=True)
        (target / 'dpwh-transparency.html').write_text(page, encoding='utf-8')
    return {'page': 'dpwh-transparency.html', 'dataVersion': data_version}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
