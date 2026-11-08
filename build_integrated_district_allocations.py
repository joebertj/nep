#!/usr/bin/env python3
"""Own the Historical · District allocations report page."""
import json

from build_integrated_district_reports import ROOT, STATIC, build as build_data, make_pages

PAGE = 'integrated-district-allocations.html'


def build_page(data=None):
    """Build only this page; data generation does not write report HTML."""
    data = data or build_data()
    make_pages(data, only_page=PAGE)
    page_path = STATIC / PAGE
    if not page_path.exists():
        raise RuntimeError(f'{PAGE} was not rendered by its page module')
    (ROOT / 'analysis_output' / PAGE).write_text(page_path.read_text(encoding='utf-8'), encoding='utf-8')
    return {
        'page': PAGE,
        'districts': len(data.get('districts', [])),
        'periods': len(data.get('periods', [])),
        'output': str(page_path),
    }


def main():
    print(json.dumps(build_page(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
