#!/usr/bin/env python3
"""Assemble the available project-level DPWH GAA stated-length rate series."""
import json
import math
import statistics
from pathlib import Path

from analyze_priority_repeats import query
from build_cost_per_km import OUT, STATIC, ROOT, category, lengths
from compare_meter_rates_2026 import build as build_2026_comparison


HISTORICAL_FAMILIES = ROOT / 'data_sources/gaa-dpwh-project-families-2016-2018.json'
GAA_2019 = ROOT / 'data_sources/gaa_2019_dpwh_technical/lines.json'
PARQUET = ROOT.parent / 'open-data-visualization/data/parquet'


def _add(rows, year, title, amount_pesos, source, pap=''):
    title = str(title or '').strip()
    amount = float(amount_pesos or 0)
    if not title or amount <= 0:
        return
    kind = category({'projectName': title, 'pap3': pap})
    if not kind:
        return
    km, status, method, _ = lengths(title)
    if km is None or km <= 0:
        return
    rows.append({
        'year': int(year), 'category': kind, 'project': title,
        'amountPesos': round(amount), 'lengthMeters': round(km * 1000, 3),
        'ratePesosPerMeter': amount / (km * 1000), 'lengthMethod': method,
        'lengthStatus': status, 'source': source,
    })


def build(current=None):
    current = current or json.loads((OUT / 'cost_per_km.json').read_text(encoding='utf-8'))
    records = []
    source_notes = []

    # FY2016–FY2018: BetterGov's locally retained DPWH project-family extract.
    family_data = json.loads(HISTORICAL_FAMILIES.read_text(encoding='utf-8'))
    family_rows = family_data.get('records', [])
    before = len(records)
    for row in family_rows:
        if row.get('category') not in {'Road', 'Bridge'}:
            continue
        _add(records, row.get('year'), row.get('name'), row.get('amountPesos'),
             row.get('source') or f'FY{row.get("year")} GAA project-family extract')
    source_notes.append({
        'years': [2016, 2017, 2018], 'source': family_data.get('title'),
        'sourceUrl': family_data.get('sourceUrl'), 'sourceRows': len(family_rows),
        'rateRows': len(records) - before,
        'limit': 'Retained classified DPWH project-family extract; not a fresh reparse of the complete GAA workbook.',
    })

    # FY2019: only rows identified as project-title candidates in the local
    # DBM technical schedule are considered; program/control lines are excluded.
    y19 = json.loads(GAA_2019.read_text(encoding='utf-8'))
    y19_rows = [r for r in y19.get('rows', []) if r.get('rowType') == 'project_title_candidate']
    before = len(records)
    for row in y19_rows:
        _add(records, 2019, row.get('title'), row.get('amountPesos'),
             f'FY2019 DBM technical DPWH GAA · UACS {row.get("uacs", "")}, pp. {row.get("sourcePages", [])}')
    source_notes.append({
        'years': [2019], 'source': y19.get('title'), 'sourceUrl': y19.get('sourceUrl'),
        'sourceRows': len(y19_rows), 'rateRows': len(records) - before,
        'limit': 'Technical GAA PDF text extraction; only project-title candidates with recoverable lengths are included.',
    })

    # FY2020–FY2025: budget parquet descriptions are hierarchy-expanded text;
    # requiring a recoverable stated length limits this to project-like rows.
    for year in range(2020, 2026):
        path = PARQUET / f'budget_{year}.parquet'
        if not path.exists():
            continue
        rows = query(
            "SELECT id, description, amount, agency_desc FROM read_parquet('" + str(path) + "') "
            "WHERE department_desc ILIKE '%Department of Public Works and Highways%' "
            "AND amount > 0 AND regexp_matches(upper(coalesce(description,'')), 'ROAD|HIGHWAY|BRIDGE')"
        )
        before = len(records)
        for row in rows:
            # Integrated GAA budget parquet amounts are in thousands of pesos.
            _add(records, year, row.get('description'), float(row.get('amount') or 0) * 1000,
                 f'FY{year} GAA parquet · row {row.get("id")}', row.get('agency_desc') or '')
        source_notes.append({
            'years': [year], 'source': f'ODV budget_{year}.parquet',
            'sourceRows': len(rows), 'rateRows': len(records) - before,
            'limit': 'Hierarchy-expanded DPWH GAA descriptions; amounts converted from thousands of pesos. Only rows with a recoverable title-stated length enter the rate series.',
        })

    # FY2026: use the existing parsed DPWH leaf-node comparison. FY2027 is the
    # HGAB proposal comparator, clearly separated from enacted GAA years.
    comp_2026 = build_2026_comparison(current)
    for row in comp_2026.get('gaaProjects', []):
        if row.get('rate') is None or not row.get('lengthMeters'):
            continue
        records.append({
            'year': 2026, 'category': row['category'], 'project': row['projectName'],
            'amountPesos': row['amountPesos'], 'lengthMeters': row['lengthMeters'],
            'ratePesosPerMeter': row['rate'], 'lengthMethod': row.get('lengthMethod'),
            'lengthStatus': row.get('lengthStatus'), 'source': f'FY2026 parsed DPWH GAA · Excel row {row.get("sourceExcelRow")}',
        })
    source_notes.append({
        'years': [2026], 'source': 'Parsed DPWH FY2026 GAA leaf-node schedule',
        'rateRows': sum(r['year'] == 2026 for r in records),
        'limit': 'Parsed DPWH leaf-node comparison source; its eligible scope is narrower than a complete DPWH GAA hierarchy.',
    })
    for row in current.get('projects', []):
        if row.get('category') == 'FMR' or not row.get('allocationPerStatedMeter') or not row.get('lengthMeters'):
            continue
        records.append({
            'year': 2027, 'stage': 'HGAB 3rd reading · proposed', 'category': row['category'],
            'project': row['projectName'], 'amountPesos': row.get('amountPesos'),
            'lengthMeters': row['lengthMeters'], 'ratePesosPerMeter': row['allocationPerStatedMeter'],
            'lengthMethod': row.get('lengthMethod'), 'lengthStatus': row.get('lengthStatus'),
            'source': row.get('sourceLabel'),
        })

    annual = []
    for year in range(2016, 2028):
        for kind in ['Roads', 'Bridges', 'Mixed roads / bridges']:
            sample = [r for r in records if r['year'] == year and r['category'] == kind
                      and float(r['lengthMeters']) >= 10 and float(r['ratePesosPerMeter']) > 0]
            rates = sorted(float(r['ratePesosPerMeter']) for r in sample)
            def quantile(q):
                if not rates:
                    return None
                if len(rates) == 1:
                    return rates[0]
                pos = (len(rates) - 1) * q
                lo, hi = math.floor(pos), math.ceil(pos)
                return rates[lo] + (rates[hi] - rates[lo]) * (pos - lo)
            annual.append({
                'year': year, 'stage': 'HGAB 3rd reading · proposed' if year == 2027 else 'Enacted GAA',
                'category': kind, 'usableRecords': len(rates),
                'medianPesosPerMeter': statistics.median(rates) if rates else None,
                'p25PesosPerMeter': quantile(.25), 'p75PesosPerMeter': quantile(.75),
                'minLengthMeters': 10,
            })

    result = {
        'title': 'Available project-level DPWH GAA stated-length rate series',
        'years': list(range(2016, 2027)), 'comparatorYear': 2027,
        'records': records, 'annual': annual, 'sourceNotes': source_notes,
        'method': 'Allocation divided by title-stated segment length using the same length parser as the current cost-per-meter screen. Only rates with at least 10 stated meters are summarized. Annual medians and quartiles are descriptive, unadjusted distributions; rows are not matched contracts or constant-scope price observations.',
        'limits': [
            'The available annual project-level series begins in FY2016. FY2015 local technical-GAA records are PAP-grouped rather than uniquely identified project records, so they are excluded; earlier annual project-level DPWH GAA sources are not present in this workspace.',
            'Historical source grain and completeness vary by year. FY2016–FY2018 use the retained DPWH project-family extract; FY2019 uses DBM technical-GAA text candidates; FY2020–FY2025 use hierarchy-expanded GAA budget descriptions; FY2026 uses parsed DPWH leaf nodes.',
            'The FY2020–FY2025 sources identify project-like rows through a recoverable stated length in the DPWH road/bridge description. This is not a complete project denominator and annual source coverage is not directly comparable.',
            'FY2027 HGAB is a proposed budget-stage comparator, not an enacted GAA year. Different project mix, scope, dimensions, quality, location and funded quantities remain uncontrolled.',
            'Rates are whole line-item allocations divided by title-stated segment length, not verified construction unit costs. FMR is excluded from this series.',
        ],
        'sources': source_notes + [{'years': [2026], 'source': comp_2026.get('sources')},
                                   {'years': [2027], 'source': current.get('sources')}],
    }
    text = json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n'
    (OUT / 'meter-rates-all-years.json').write_text(text, encoding='utf-8')
    (STATIC / 'meter-rates-all-years.json').write_text(text, encoding='utf-8')
    return result


if __name__ == '__main__':
    data = build()
    print(json.dumps({'records': len(data['records']), 'annual': [r for r in data['annual'] if r['usableRecords']]}, ensure_ascii=False, indent=2))
