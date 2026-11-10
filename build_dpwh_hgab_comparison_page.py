#!/usr/bin/env python3
"""Build only the DPWH 2nd-versus-3rd-reading HTML page."""
import json
from pathlib import Path
from build_hgab_revision_pages import render_dpwh_comparison_page
from report_hero_module import STYLE, hero, peso

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
OUT = ROOT / 'analysis_output'


def build():
    page = render_dpwh_comparison_page()
    summary = json.loads((STATIC / 'dpwh-hgab-comparison.json').read_text(encoding='utf-8'))['summary']
    net = int(summary['thirdAllocationPesos']) - int(summary['secondAllocationPesos'])
    lead = hero('DPWH · HB 10858 2nd vs 3rd Reading',
                str(summary['statusCounts'].get('New in 3rd reading', 0)),
                'line items appear only in the 3rd-reading extraction',
                peso(abs(net)) if net >= 0 else '−' + peso(abs(net)),
                'net increase across the extracted schedules', [
                    ('2nd-reading lines', f"{summary['secondCandidateCount']:,}", peso(summary['secondAllocationPesos'])),
                    ('3rd-reading lines', f"{summary['thirdCandidateCount']:,}", peso(summary['thirdAllocationPesos']))],
                'This is a document-stage comparison. A line appearing in one extraction does not by itself establish a policy insertion or deletion.')
    page = page.replace('__READING_TEASER__', '')
    page = page.replace('<main class="wrap">', '<main class="wrap"><section id="report-hero">' + lead + '</section>', 1)
    page = page.replace('</head>', STYLE + '</head>', 1)
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module('dpwh-hgab-comparison.html',page)
    from uniform_report_menu import apply_page as apply_uniform_menu
    page=apply_uniform_menu(page,'dpwh-hgab-comparison.html')
    (STATIC / 'dpwh-hgab-comparison.html').write_text(page, encoding='utf-8')
    (OUT / 'dpwh-hgab-comparison.html').write_text(page, encoding='utf-8')
    return {'page': 'dpwh-hgab-comparison.html'}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
