#!/usr/bin/env python3
"""Refresh archive.html's report links and shared navigation."""
from __future__ import annotations

from build_fmr_dataset import OUT, STATIC
from uniform_report_menu import apply_page

OLD = '<a href="fmr.html"><strong>FMR</strong></a> · Farm-to-market road analyses'
NEW = '<a href="fmr-archive.html"><strong>FMR archive</strong></a> · Farm-to-market road analyses'


def generate() -> dict:
    source = OUT / 'archive.html'
    page = source.read_text(encoding='utf-8')
    occurrences = page.count(OLD)
    if occurrences != 1 and NEW not in page:
        raise RuntimeError(f'Expected one FMR archive entry in archive.html; found {occurrences}.')
    page = page.replace(OLD, NEW)
    page = apply_page(page, 'archive.html')
    source.write_text(page, encoding='utf-8')
    (STATIC / 'archive.html').write_text(page, encoding='utf-8')
    return {'page': 'archive.html', 'fmrArchiveLinks': page.count('href="fmr-archive.html"')}


if __name__ == '__main__':
    import json
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
