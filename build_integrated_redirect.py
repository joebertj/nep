#!/usr/bin/env python3
"""Build only the legacy integrated.html redirect page."""
import json

from build_integrated_district_reports import STATIC, build as build_data, make_pages

PAGE = 'integrated.html'


def build_page(data=None):
    data = data or build_data()
    make_pages(data, only_page=PAGE)
    page = STATIC / PAGE
    if not page.exists():
        raise RuntimeError(f'{PAGE} was not rendered')
    return {'page': PAGE, 'output': str(page)}


if __name__ == '__main__':
    print(json.dumps(build_page(), ensure_ascii=False, indent=2))
