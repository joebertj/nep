"""Per-page output contracts for builders that render report tables."""
import re
from report_currency_module import money_header


PAGE_TABLE_CONTRACTS = {
    'dpwh-hgab.html': {
        'builder': 'build_dpwh_hgab_headlines.py',
        'chainageViewer': True,
    },
    'dpwh-OO2-hgab.html': {
        'builder': 'build_dpwh_oo2_hgab.py',
        'chainageViewer': True,
    },
    'repeats.html': {
        'builder': 'build_repeats_page.py',
        'chainageViewer': True,
    },
}


def check_page_table_contract(page_name, html):
    """Raise when a page builder's output misses its declared table behavior."""
    contract = PAGE_TABLE_CONTRACTS.get(page_name, {})
    tables = re.findall(r'<table\b.*?</table>', html, flags=re.I | re.S)
    if not tables:
        raise RuntimeError(f'{page_name}: expected at least one rendered table')

    unformatted = []
    for table_number, table in enumerate(tables, 1):
        head = re.search(r'<thead\b.*?</thead>', table, flags=re.I | re.S)
        if not head:
            continue
        headers = [re.sub(r'<[^>]+>', '', cell).strip()
                   for cell in re.findall(r'<th\b[^>]*>(.*?)</th>', head[0], flags=re.I | re.S)]
        body = table[head.end():]
        for row in re.findall(r'<tr\b.*?</tr>', body, flags=re.I | re.S):
            cells = re.findall(r'<td\b[^>]*>(.*?)</td>', row, flags=re.I | re.S)
            for index, cell in enumerate(cells[:len(headers)]):
                value = re.sub(r'<[^>]+>', '', cell).strip().replace(',', '')
                if money_header(headers[index]) and re.fullmatch(r'-?\d+(?:\.\d+)?', value):
                    unformatted.append(f'table {table_number}, column {headers[index]!r}')
    if unformatted:
        raise RuntimeError(f'{page_name}: numeric currency cells are not formatted: {unformatted[:5]}')

    viewer_present = bool(re.search(r'<script\b[^>]*id="chainage-overlap-viewer"', html, re.I))
    if contract.get('chainageViewer') and not viewer_present:
        raise RuntimeError(f'{page_name}: required chainage overlap viewer script is missing')
    return {
        'page': page_name,
        'builder': contract.get('builder'),
        'tables': len(tables),
        'currencyCellsFormatted': True,
        'chainageViewer': viewer_present,
    }
