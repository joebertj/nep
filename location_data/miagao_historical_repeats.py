"""Qualify and normalize annual DPWH titles for the Miagao repeat catalog."""
import re

from location_data.historical_repeat_titles import location_title, normalized_scope
from location_data.location_text import geographic_title

MIAGAO = re.compile(r'\bmiag[\s‐‑–-]?ao\b', re.I)
CODE = '0603030000'


def title_key(title):
    base, _ = geographic_title(location_title(title))
    return normalized_scope(MIAGAO.sub('miagao', base))


def in_miagao(title, places):
    return any(places.lineage(code).get('municipality') == CODE
               for code in places.resolve(location_title(title)))


def annual_rows(historical, places):
    for year, rows in historical.items():
        for row in rows:
            title = row['name']
            if row['amount'] > 0 and MIAGAO.search(title) and in_miagao(title, places):
                yield year, row
