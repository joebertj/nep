#!/usr/bin/env python3
"""Build the Historical MPB regional and provincial rankings page only."""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static' / 'nep-preview'
OUT = ROOT / 'analysis_output'
SOURCE = OUT / 'mpb-barangay-index.json'
BASE_SOURCE = OUT / 'mpb-barangay-base-data.json'
PSGC = ROOT / 'data_sources' / 'bettergov-psgc-locations.jsonl'
PAGE = 'mpb-regional-province.html'
DATA = 'mpb-regional-province-data.json'

POVERTY_SOURCE = ODV / 'database' / 'poverty.json'


def average_ranks(values):
    ordered = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and ordered[j][1] == ordered[i][1]:
            j += 1
        rank = (i + 1 + j) / 2
        for k in range(i, j):
            ranks[ordered[k][0]] = rank
        i = j
    return ranks


def pearson(xs, ys):
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    numerator = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    return numerator / math.sqrt(dx * dy) if dx and dy else 0.0


def spearman(xs, ys):
    return pearson(average_ranks(xs), average_ranks(ys))


def permutation_spearman(xs, ys, seed):
    observed = spearman(xs, ys)
    ranked_x, ranked_y = average_ranks(xs), average_ranks(ys)
    rng = random.Random(seed)
    extreme, simulations = 0, 20000
    shuffled = ranked_y[:]
    for _ in range(simulations):
        rng.shuffle(shuffled)
        if abs(pearson(ranked_x, shuffled)) >= abs(observed) - 1e-12:
            extreme += 1
    return {'rho': observed, 'permutations': simulations, 'pValue': (extreme + 1) / (simulations + 1)}


def two_proportion_z(success_a, total_a, success_b, total_b):
    pooled = (success_a + success_b) / (total_a + total_b)
    se = math.sqrt(pooled * (1 - pooled) * (1 / total_a + 1 / total_b))
    z = ((success_a / total_a) - (success_b / total_b)) / se if se else 0.0
    return {'z': z, 'pValue': math.erfc(abs(z) / math.sqrt(2))}


def region_label(row):
    name = str(row.get('name') or '').upper()
    if name in ('NCR', 'NATIONAL CAPITAL REGION') or 'NATIONAL CAPITAL REGION' in name: return 'NCR'
    if name in ('CAR', 'CORDILLERA ADMINISTRATIVE REGION') or 'CORDILLERA ADMINISTRATIVE REGION' in name: return 'CAR'
    if name == 'NIR' or 'NEGROS ISLAND' in name: return 'NIR'
    if name in ('BARMM', 'AUTONOMOUS REGION IN MUSLIM MINDANAO') or 'BANGSAMORO' in name: return 'BARMM'
    if name == 'MIMAROPA' or 'MIMAROPA' in name: return 'MIMAROPA'
    if name == 'CARAGA' or 'CARAGA' in name: return 'REGION 13'
    import re
    numeric = re.search(r'\bREGION\s+(1[0-3]|[1-9])\b', name)
    if numeric: return f'REGION {int(numeric.group(1))}'
    match = re.search(r'REGION\s+(XIII|XII|XI|X|IX|VIII|VII|VI|V|IV-A|IV-B|III|II|I)', name)
    if not match: return ''
    roman = match.group(1)
    return {'IV-A':'REGION 4A','IV-B':'MIMAROPA','I':'REGION 1','II':'REGION 2','III':'REGION 3',
            'V':'REGION 5','VI':'REGION 6','VII':'REGION 7','VIII':'REGION 8','IX':'REGION 9',
            'X':'REGION 10','XI':'REGION 11','XII':'REGION 12','XIII':'REGION 13'}.get(roman, '')


def build_data():
    index = json.loads(SOURCE.read_text(encoding='utf-8'))
    poverty_source = json.loads(POVERTY_SOURCE.read_text(encoding='utf-8'))
    poverty = {}
    for row in poverty_source:
        key = region_label({'name': row.get('region')})
        if key and row.get('poverty') is not None:
            poverty[key] = float(row['poverty'])
    # The 2023 poverty source predates NIR. Derive a transparent NIR proxy from
    # the two province estimates now assigned to NIR in the current PSGC.
    province_poverty = {
        str(province.get('province') or '').strip().casefold(): float(province['poverty'])
        for row in poverty_source for province in row.get('provinces', [])
        if province.get('poverty') is not None
    }
    nir_province_rates = [province_poverty.get('negros occidental'), province_poverty.get('negros oriental')]
    if all(value is not None for value in nir_province_rates):
        poverty['NIR'] = sum(nir_province_rates) / len(nir_province_rates)
    periods = index.get('periods', [])
    psgc = {row['code']: row for row in (json.loads(line) for line in PSGC.read_text(encoding='utf-8').splitlines() if line.strip())}
    province_regions, locality_by_code = {}, {}
    official_by_region, official_by_locality, official_by_province, official_by_type = (defaultdict(int) for _ in range(4))
    for row in psgc.values():
        if row.get('level') == 'region':
            continue
        parent = psgc.get(row.get('parent_code'), {})
        region = region_label(parent) if parent.get('level') == 'region' else ''
        if row.get('level') == 'province' and region:
            province_regions[row.get('name', '').casefold()] = region
        if row.get('level') in ('city', 'municipality', 'sub_municipality'):
            if not region and parent.get('level') == 'province':
                region = province_regions.get(parent.get('name', '').casefold(), '')
            if row.get('level') == 'sub_municipality':
                locality = psgc.get(row.get('parent_code'), {})
                if locality.get('level') == 'city':
                    region = region or (region_label(psgc.get(locality.get('parent_code'), {})) if psgc.get(locality.get('parent_code'), {}).get('level') == 'region' else '')
                    locality_by_code[row['code']] = {'name': locality.get('name') or '', 'type': 'City', 'region': region, 'rollupCode': locality.get('code')}
                continue
            locality_by_code[row['code']] = {'name': row.get('name') or '', 'type': 'City' if row.get('level') == 'city' else 'Municipality', 'region': region, 'rollupCode': row['code']}
    # Resolve municipal/locality region assignments after province names are indexed.
    for code, locality in locality_by_code.items():
        row = psgc[code]
        parent = psgc.get(row.get('parent_code'), {})
        if not locality['region'] and parent.get('level') == 'province':
            locality['region'] = province_regions.get(parent.get('name', '').casefold(), '')
        if not locality['region']:
            ancestor = parent
            while ancestor:
                if ancestor.get('level') == 'region':
                    locality['region'] = region_label(ancestor)
                    break
                ancestor = psgc.get(ancestor.get('parent_code'))
    for row in psgc.values():
        if row.get('level') != 'barangay':
            continue
        raw_locality_code = row.get('parent_code') or ''
        locality = locality_by_code.get(raw_locality_code, {})
        locality_code = locality.get('rollupCode') or raw_locality_code
        locality = locality_by_code.get(locality_code, locality)
        region = locality.get('region') or ''
        province = psgc.get(psgc.get(locality_code, {}).get('parent_code'), {})
        if not province or province.get('level') == 'region':
            province_name = locality.get('name') or ''
        else:
            province_name = province.get('name') or ''
        if region: official_by_region[region] += 1
        if locality_code: official_by_locality[locality_code] += 1
        if province_name: official_by_province[province_name.casefold()] += 1
    for code, locality in locality_by_code.items():
        official_by_type[locality.get('type') or 'Unclassified'] += official_by_locality.get(code, 0)
    base = json.loads(BASE_SOURCE.read_text(encoding='utf-8'))
    base_by_id = {row.get('id'): row for row in base.get('barangays', [])}
    regions = defaultdict(lambda: {'region': '', 'officialBarangays': 0, 'barangayPlaces': 0, 'historicalProjectTitleMatches': 0, 'projectRows': 0, 'allocationPesos': 0})
    provinces = defaultdict(lambda: {'region': '', 'province': '', 'officialBarangays': 0, 'barangayPlaces': 0, 'historicalProjectTitleMatches': 0, 'projectRows': 0, 'allocationPesos': 0})
    localities = defaultdict(lambda: {'region': '', 'province': '', 'locality': '', 'localityType': '', 'officialBarangays': 0, 'barangayPlaces': 0, 'historicalProjectTitleMatches': 0, 'projectRows': 0, 'allocationPesos': 0})
    locality_types = defaultdict(lambda: {'localityType': '', 'officialBarangays': 0, 'coveredBarangays': 0, 'projectRows': 0, 'allocationPesos': 0, 'historicalProjectTitleMatches': 0})
    coverage_periods = [{'year': int(p['year']), 'stage': str(p.get('stage') or ''), 'officialBarangays': 0, 'coveredBarangays': 0, 'projectRows': 0, 'allocationPesos': 0, 'multiplicity': {'1': 0, '2–3': 0, '4–5': 0, '6+': 0}} for p in periods]
    all_multiplicity = {'1': 0, '2–3': 0, '4–5': 0, '6+': 0}
    top_barangays = []
    for item in index.get('barangayRows', []):
        place_id, barangay, municipality, province, region, _shard, yearly = item
        code = str(place_id).removeprefix('psgc:')
        psgc_row = psgc.get(code, {})
        locality_code = psgc_row.get('parent_code') or ''
        locality = locality_by_code.get(locality_code, {})
        # The index can contain a stale or unspecified region label. PSGC hierarchy
        # is the authoritative location fallback for barangay rollups.
        resolved_region = locality.get('region') or province_regions.get(str(province).casefold()) or (region_label({'name': region}) if region and region != 'Unspecified region' else '')
        if not province:
            parent = psgc.get(locality_code, {})
            parent_row = psgc.get(parent.get('parent_code'), {})
            province = parent_row.get('name') if parent_row.get('level') == 'province' else (locality.get('name') or '')
        if not resolved_region or not province:
            continue
        region_row = regions[resolved_region]
        region_row['region'] = resolved_region
        region_row['officialBarangays'] = official_by_region.get(resolved_region, 0)
        # Source rows occasionally vary only by capitalization for the same
        # PSGC province. Merge those rows before joining PSA poverty estimates.
        province_key = (resolved_region, str(province).strip().casefold())
        province_row = provinces[province_key]
        province_row['region'], province_row['province'] = resolved_region, province
        province_row['officialBarangays'] = official_by_province.get(str(province).casefold(), 0)
        locality_key = locality_code or f'{resolved_region}|{province}|{municipality}'
        locality_row = localities[locality_key]
        locality_row.update({'region': resolved_region, 'province': province, 'locality': municipality or locality.get('name') or '', 'localityType': locality.get('type') or 'Locality', 'officialBarangays': official_by_locality.get(locality_code, 0)})
        region_has_data = False
        province_has_data = False
        for stat in yearly:
            year_index, amount, count = int(stat[0]), int(stat[1]), int(stat[2])
            if year_index >= len(periods):
                continue
            period = periods[year_index]
            key = (int(period['year']), str(period.get('stage') or ''))
            for target in (region_row, province_row, locality_row):
                target.setdefault('_periods', defaultdict(lambda: {'projectRows': 0, 'allocationPesos': 0}))
                target['_periods'][key]['projectRows'] += count
                target['_periods'][key]['allocationPesos'] += amount
                if count:
                    target['_periods'][key]['coveredBarangays'] = target['_periods'][key].get('coveredBarangays', 0) + 1
            coverage_periods[year_index]['officialBarangays'] = index.get('summary', {}).get('officialBarangays', 0)
            coverage_periods[year_index]['projectRows'] += count
            coverage_periods[year_index]['allocationPesos'] += amount
            if count or amount:
                region_has_data = province_has_data = True
                coverage_periods[year_index]['coveredBarangays'] += 1
                band = '1' if count == 1 else '2–3' if count <= 3 else '4–5' if count <= 5 else '6+'
                coverage_periods[year_index]['multiplicity'][band] += 1
        if region_has_data:
            region_row['barangayPlaces'] += 1
        if province_has_data:
            province_row['barangayPlaces'] += 1
        if region_has_data:
            locality_row['barangayPlaces'] += 1
        base_place = base_by_id.get(place_id, {})
        building_count = len(base_place.get('buildings', []))
        all_count = sum(int(stat[2]) for stat in yearly)
        for target in (region_row, province_row, locality_row):
            target['historicalProjectTitleMatches'] += building_count
        type_row = locality_types[locality.get('type') or 'Unclassified']
        type_row['localityType'] = locality.get('type') or 'Unclassified'
        type_row['officialBarangays'] = official_by_type[type_row['localityType']]
        if region_has_data: type_row['coveredBarangays'] += 1
        type_row['historicalProjectTitleMatches'] += building_count
        type_row['projectRows'] += all_count
        type_row['allocationPesos'] += sum(int(stat[1]) for stat in yearly)
        if building_count:
            band = '1' if building_count == 1 else '2–3' if building_count <= 3 else '4–5' if building_count <= 5 else '6+'
            all_multiplicity[band] += 1
            top_barangays.append({'barangay': barangay, 'municipality': municipality, 'province': province, 'region': resolved_region, 'historicalProjectTitleMatches': building_count, 'projectRows': all_count, 'allocationPesos': sum(int(stat[1]) for stat in yearly)})

    def finalize(rows):
        result = []
        for row in rows:
            periods_by_key = row.pop('_periods', {})
            row['periods'] = [
            {'year': year, 'stage': stage, **values}
                for (year, stage), values in sorted(periods_by_key.items())
            ]
            row['projectRows'] = sum(p['projectRows'] for p in row['periods'])
            row['allocationPesos'] = sum(p['allocationPesos'] for p in row['periods'])
            result.append(row)
        return result

    official_n = int(index.get('summary', {}).get('officialBarangays', 0))
    covered_n = int(index.get('summary', {}).get('barangaysWithMpb', 0))
    title_match_counts = [len(row.get('buildings', [])) for row in base_by_id.values()]
    lam = sum(title_match_counts) / max(1, official_n)
    observed_bins = [sum(value == k for value in title_match_counts) for k in range(4)] + [sum(value >= 4 for value in title_match_counts)]
    poisson_probabilities = [math.exp(-lam) * lam ** k / math.factorial(k) for k in range(4)]
    poisson_probabilities.append(max(0.0, 1 - sum(poisson_probabilities)))
    expected_bins = [official_n * probability for probability in poisson_probabilities]
    chi_square = sum((observed - expected) ** 2 / expected for observed, expected in zip(observed_bins, expected_bins) if expected)
    concentration_test = {'name': 'Poisson goodness-of-fit chi-square', 'null': 'historical project-title matches are distributed at a common rate across official barangays',
                         'bins': ['0', '1', '2', '3', '4+'], 'observed': observed_bins, 'expected': expected_bins,
                         'chiSquare': chi_square, 'degreesOfFreedom': 3, 'pValueLabel': '< 0.001', 'meanMatchesPerBarangay': lam,
                         'matchesPerCoveredBarangay': sum(title_match_counts) / max(1, covered_n), 'totalTitleMatches': sum(title_match_counts),
                         'coveredBarangays': covered_n, 'officialBarangays': official_n}

    type_by_name = {row['localityType']: row for row in locality_types.values()}
    city = type_by_name.get('City', {'coveredBarangays': 0, 'officialBarangays': 0})
    municipality = type_by_name.get('Municipality', {'coveredBarangays': 0, 'officialBarangays': 0})
    settlement_test = {'name': 'Two-proportion z test', 'null': 'City and municipality barangay coverage rates are equal',
                       'cityRate': city['coveredBarangays'] / max(1, city['officialBarangays']),
                       'municipalityRate': municipality['coveredBarangays'] / max(1, municipality['officialBarangays']),
                       'cityCovered': city['coveredBarangays'], 'cityTotal': city['officialBarangays'],
                       'municipalityCovered': municipality['coveredBarangays'], 'municipalityTotal': municipality['officialBarangays'],
                       **two_proportion_z(city['coveredBarangays'], city['officialBarangays'], municipality['coveredBarangays'], municipality['officialBarangays'])}

    # NIR's derived proxy overlaps the published Region VI/VII poverty estimates.
    # Exclude all three from inferential correlations so each test uses comparable
    # geographic boundaries; the charts still display all 18 current regions.
    test_regions = [row for row in regions.values() if row['region'] not in ('REGION 6', 'REGION 7', 'NIR') and row['region'] in poverty]
    poverty_x = [poverty[row['region']] for row in test_regions]
    coverage_y = [100 * row['barangayPlaces'] / max(1, row['officialBarangays']) for row in test_regions]
    allocation_y = [sum(values['allocationPesos'] for values in row.get('_periods', {}).values()) / max(1, row['officialBarangays']) for row in test_regions]
    poverty_coverage_test = permutation_spearman(poverty_x, coverage_y, 20261109)
    poverty_allocation_test = permutation_spearman(poverty_x, allocation_y, 20261110)
    poverty_tests = {'method': 'Two-sided permutation test of Spearman rank correlation; 20,000 permutations with fixed seed',
                     'excludedForBoundaryOverlap': ['REGION 6', 'REGION 7', 'NIR'], 'n': len(test_regions),
                     'coverage': poverty_coverage_test, 'allocationPerBarangay': poverty_allocation_test}

    summary = dict(index.get('summary', {}))
    summary['historicalProjectTitleMatches'] = summary.pop('buildingIdentities', summary.get('historicalProjectTitleMatches', 0))

    return {
        'generatedAtUtc': index.get('generatedAtUtc'),
        'source': 'MPB barangay index generated from the BetterGov MPB map line export',
        'scope': 'Only FY2015–FY2027 MPB rows assigned to official barangay PSGC places are included. FY2015–FY2026 rows are enacted GAA; FY2027 is the House Bill 10858 3rd-reading proposal.',
        'caveat': 'Regional and provincial amounts sum allocations attached to barangay-assigned rows. They are budget allocations, not expenditures or verified construction costs. Broader-area and unplaced rows are excluded. City-versus-municipality is an administrative proxy, not a barangay urban/rural classification. The poverty comparison uses PSA 2023 poverty incidence among families and is descriptive; it does not establish a budget-prioritization rule.',
        'periods': [{'year': int(p['year']), 'stage': str(p.get('stage') or '')} for p in periods],
        'regions': finalize(regions.values()),
        'provinces': [
            {**row, 'povertyIncidence2023AmongFamiliesPct': province_poverty.get(str(row.get('province') or '').strip().casefold())}
            for row in finalize(provinces.values())
        ],
        'provincePovertyIncidence2023AmongFamiliesPct': province_poverty,
        'poorestProvince2023AmongFamilies': max(
            ({'province': name.title(), 'povertyPct': rate} for name, rate in province_poverty.items()),
            key=lambda row: row['povertyPct'],
            default=None,
        ),
        'provincePovertySourceUrl': 'https://psa.gov.ph/sites/default/files/phdsd/2023%20FY%20Official%20Poverty%20Statistics%20Publication_15August2024.pdf',
        'lguPoverty2023SourceUrl': 'https://psa.gov.ph/statistics/poverty/node/1684082420',
        'lguPoverty2023WorkbookUrl': 'https://psa.gov.ph/sites/default/files/phdsd/2_2023%20SAE_with%20PSGC_noHUC_06Feb2026.xlsx',
        'localities': finalize(localities.values()),
        'localityTypes': list(locality_types.values()),
        'coveragePeriods': coverage_periods,
        'allYearsMultiplicity': all_multiplicity,
        'topBarangays': sorted(top_barangays, key=lambda x: (-x['historicalProjectTitleMatches'], -x['allocationPesos'], x['barangay']))[:100],
        'topBarangaysByAllocation': sorted(top_barangays, key=lambda x: (-x['allocationPesos'], -x['historicalProjectTitleMatches'], x['barangay']))[:100],
        'povertyIncidence2023AmongFamiliesPct': poverty,
        'povertySource': 'ODV database/poverty.json · PSA 2023 poverty incidence among families',
        'povertyNirMethod': 'NIR proxy: simple, unweighted mean of Negros Occidental (22.1%) and Negros Oriental (25.1%) provincial poverty-incidence estimates. The PSA 2023 regional rates for Regions VI and VII predate NIR and include those provinces; comparisons involving these three points overlap geographically.',
        'statisticalTests': {'titleMatchConcentration': concentration_test,
                             'cityMunicipalityCoverage': settlement_test, 'povertyAssociations': poverty_tests},
        'summary': summary,
    }


def build_page():
    data = build_data()
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    version = hashlib.sha256(serialized.encode()).hexdigest()[:12]
    for destination in (STATIC / DATA, OUT / DATA):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized, encoding='utf-8')

    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Historical MPB distribution · BetterGov</title>
<style>main{{width:100%;max-width:none;padding:clamp(16px,2vw,32px);box-sizing:border-box}}.mpb-ranking-hero{{padding:clamp(22px,3vw,34px);border-left:8px solid #FCD116;border-radius:14px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff}}.bettergov-research main .mpb-ranking-hero h2{{color:#fff!important}}.mpb-ranking-hero p{{color:#f4f6f8}}.metric{{display:inline-block;margin:8px 18px 0 0}}.metric strong{{display:block;color:#FCD116;font-size:1.35rem}}.test-result{{margin:12px 0 18px;padding:12px 16px;border-left:4px solid #FCD116;background:#f5f8fb;color:#263746}}.test-result strong{{color:#00246A}}.ranking-section{{margin:24px 0;padding:20px;border:1px solid #d3dce4;border-radius:12px;background:#fff}}.ranking-controls{{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin:14px 0}}.ranking-controls label{{display:grid;gap:5px;font-weight:650}}.ranking-controls select{{min-width:190px;padding:8px;font:inherit}}.rank-chart{{display:grid;gap:7px;margin:16px 0 22px}}.rank-bar{{display:grid;grid-template-columns:minmax(130px,240px) minmax(100px,1fr) minmax(110px,auto);align-items:center;gap:10px}}.rank-track{{height:14px;background:#e8edf3;border-radius:12px;overflow:hidden}}.rank-fill{{display:block;height:100%;background:#0038A8}}.rank-total{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}.muted{{color:#5d6874}}.answer{{padding:12px 16px;background:#f1f6fb;border-left:4px solid #0038A8}}table{{width:100%;border-collapse:collapse}}th,td{{padding:9px;text-align:left;border-bottom:1px solid #d9e0e7}}th{{background:#e7effa}}td.num,th.num{{text-align:right;font-variant-numeric:tabular-nums}}.scatter{{width:100%;min-height:340px}}@media(max-width:650px){{.rank-bar{{grid-template-columns:minmax(95px,130px) minmax(50px,1fr) minmax(90px,auto);font-size:12px;gap:6px}}.ranking-section{{padding:12px}}}}</style></head><body><header><span class="eyebrow">Historical · MPB allocations</span><h1>Where do multi-purpose buildings go?</h1><p>Barangay coverage, city and municipality patterns, and regional poverty context.</p></header><main>
<section class="mpb-ranking-hero"><h2>MPB coverage and distribution</h2><p>Mapped MPB records from FY2015–FY2027, with FY2027 identified separately as a House Bill proposal.</p><div><span class="metric"><strong id="coverage-total">—</strong>barangays with at least one mapped MPB</span><span class="metric"><strong id="coverage-share">—</strong>of official barangays in the index</span><span class="metric"><strong id="facility-total">—</strong>historical project-title matches</span><span class="metric"><strong id="row-link-ratio">—</strong>mapped MPB row links per official barangay</span><span class="metric"><strong id="matches-covered-ratio">—</strong>title matches per covered barangay</span></div></section>
<section class="ranking-section"><h2>1 · How broad is MPB coverage, and do some barangays have multiple MPB records?</h2><p class="answer" id="coverage-answer">Loading mapped barangay coverage…</p><p class="muted"><strong>Historical project-title match:</strong> a normalized MPB project title paired with an official barangay, matched across fiscal years when the same title/barangay pair recurs. Coordinates are removed during title normalization. Identical or generic titles duplicated within one year are kept as separate unresolved records. These are title-based record groups, not verified counts of distinct or completed physical buildings. The distribution below shows the groups per barangay.</p><div id="coverage-test" class="test-result"></div><div id="coverage-chart" class="rank-chart" aria-label="Annual MPB coverage of barangays"></div><div class="table-wrap"><table><thead><tr><th>Fiscal year</th><th>Stage</th><th class="num">Covered barangays</th><th class="num">Official barangays</th><th class="num">Coverage</th><th class="num">Mapped project rows</th><th class="num">Listed allocation</th></tr></thead><tbody id="coverage-rows"></tbody></table></div><h3>Historical project-title matches per barangay · all years</h3><div id="multiplicity-chart" class="rank-chart"></div><div id="concentration-test" class="test-result"></div><h3>Top barangays by historical title matches</h3><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Barangay</th><th>Municipality / city</th><th>Province</th><th>Region</th><th class="num">Historical title matches</th><th class="num">Listed allocation</th></tr></thead><tbody id="top-barangays"></tbody></table></div><h3>Top barangays by listed allocation · all years</h3><div id="top-allocation-chart" class="rank-chart"></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Barangay</th><th>Municipality / city</th><th>Province</th><th>Region</th><th class="num">Historical title matches</th><th class="num">Listed allocation</th></tr></thead><tbody id="top-allocation-barangays"></tbody></table></div></section>
<section class="ranking-section"><h2>2 · Are MPBs concentrated in rural areas or in cities?</h2><p class="answer">The current mapped source can compare cities and municipalities, but it does not carry PSA barangay-level urban/rural classifications. City versus municipality below is only an administrative proxy: municipalities can include urban barangays, and cities can include rural barangays.</p><div id="settlement-test" class="test-result"></div><h3>Barangay coverage rate</h3><div id="settlement-coverage-chart" class="rank-chart"></div><h3>Allocation per official barangay</h3><div id="settlement-chart" class="rank-chart"></div><div class="table-wrap"><table><thead><tr><th>Administrative type</th><th class="num">Official barangays</th><th class="num">With mapped MPB</th><th class="num">Coverage</th><th class="num">Historical title matches</th><th class="num">Mapped allocation</th><th class="num">Allocation per official barangay</th></tr></thead><tbody id="settlement-rows"></tbody></table></div><h3>City and municipality rankings</h3><div class="ranking-controls"><label>Type<select id="locality-type"><option>City</option><option>Municipality</option></select></label><label>Region<select id="locality-region"></select></label><label>Period<select id="locality-period"></select></label></div><div id="locality-chart" class="rank-chart"></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Locality</th><th>Province</th><th>Region</th><th class="num">Barangay coverage</th><th class="num">Project rows</th><th class="num">Listed allocation</th><th class="num">Allocation per official barangay</th></tr></thead><tbody id="locality-rows"></tbody></table></div></section>
<section class="ranking-section"><h2>Local poverty context for MPB distribution</h2><p class="answer">PSA’s 2023 city- and municipality-level estimates add finer geographic context to the mapped MPB distribution. The small-area estimates cover 1,611 localities and include uncertainty measures; Siayan, Zamboanga del Norte had the highest poverty incidence among population at 67.8%, and eight localities exceeded 60%. These locality estimates are not joined to individual MPB allocations here, so they do not show whether funding reached higher-poverty localities.</p><p>Use the <a href="https://psa.gov.ph/statistics/poverty/node/1684082420" target="_blank" rel="noopener">PSA release</a> or <a href="https://psa.gov.ph/sites/default/files/phdsd/2_2023%20SAE_with%20PSGC_noHUC_06Feb2026.xlsx" target="_blank" rel="noopener">download its 2023 city/municipality workbook</a> to inspect local estimates, standard errors, coefficients of variation, and confidence intervals. The downloadable workbook is the authoritative locality-level source; this page does not infer a poverty value for cities or municipalities from regional or provincial averages.</p><h2>3 · Does MPB distribution favor poorer regions?</h2><p class="answer" id="poverty-answer">Comparing PSA 2023 poverty-incidence estimates with mapped MPB coverage and allocation per official barangay. These are descriptive regional comparisons, not proof of a funding rule.</p><div id="poverty-test" class="test-result"></div><h3>Poverty incidence and barangay coverage</h3><div id="poverty-coverage-chart"></div><h3>Poverty incidence and MPB allocation per official barangay</h3><div id="poverty-allocation-chart"></div><div class="table-wrap"><table><thead><tr><th>Region</th><th class="num">2023 poverty incidence among families</th><th class="num">Barangay coverage</th><th class="num">Coverage rate</th><th class="num">MPB allocation per official barangay</th><th class="num">Total mapped allocation</th></tr></thead><tbody id="poverty-rows"></tbody></table></div><p class="muted">† NIR is shown using the simple, unweighted mean of the PSA provincial estimates for Negros Occidental and Negros Oriental (23.6%); it is not an official regional estimate. The 2023 Region VI and VII poverty estimates predate NIR and include those provinces, so comparisons among Region VI, Region VII and NIR overlap geographically. These poverty rates are not a budget-need formula, and the correlations do not establish prioritization or causation.</p></section>
<section class="ranking-section"><h2>Regional ranking</h2><p class="muted">Choose a fiscal year or all available years. Select a region to see the provincial allocation ranking.</p><div class="ranking-controls"><label>Period<select id="region-period"></select></label></div><div id="region-chart" class="rank-chart"></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Region</th><th class="num">Barangays with MPB</th><th class="num">Project rows</th><th class="num">Listed allocation</th></tr></thead><tbody id="region-rows"></tbody></table></div><h3>Provincial ranking</h3><p class="muted">The highest 2023 provincial poverty incidence among families in the linked PSA data is <strong id="poorest-province-note">loading…</strong>. For matched provinces, this table pairs the PSA rate with mapped MPB allocation rows using the official province name. City-level rows have no provincial estimate; blank cells do not mean zero poverty. Rates and allocation totals describe different measures and do not establish funding need or causation.</p><div class="ranking-controls"><label>Region<select id="province-region"></select></label><label>Period<select id="province-period"></select></label></div><div id="province-chart" class="rank-chart"></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Province / city</th><th class="num">2023 poverty incidence among families</th><th class="num">Barangays with MPB</th><th class="num">Project rows</th><th class="num">Listed allocation</th></tr></thead><tbody id="province-rows"></tbody></table></div></section>
<section class="ranking-section"><h2>Sources and limits</h2><p id="scope"></p><p id="caveat" class="muted"></p><p>MPB records and allocations: <a href="https://budget.bettergov.ph/hgab/2027/multi-purpose/map" target="_blank" rel="noreferrer">BetterGov MPB map line export</a>. Regional and provincial 2023 poverty incidence among families: PSA <a href="https://psa.gov.ph/sites/default/files/phdsd/2023%20FY%20Official%20Poverty%20Statistics%20Publication_15August2024.pdf" target="_blank" rel="noreferrer">2023 Full Year Official Poverty Statistics</a>. City- and municipality-level 2023 estimates: PSA <a href="https://psa.gov.ph/statistics/poverty/node/1684082420">SAE release and workbook</a>. Geographic denominators use official barangay PSGC records. Allocations are not expenditures or verified construction costs.</p></section>
</main><script>
fetch('{DATA}?v={version}').then(r=>{{if(!r.ok)throw Error(r.status);return r.json()}}).then(d=>{{
const $=id=>document.getElementById(id), n=x=>Number(x||0).toLocaleString('en-PH'), peso=x=>'₱'+n(x), pct=x=>Number(x||0).toFixed(1)+'%', all='all';
const cov=d.summary.barangaysWithMpb||0,total=d.summary.officialBarangays||0;
$('coverage-total').textContent=n(cov);$('coverage-share').textContent=pct(cov*100/Math.max(1,total));$('facility-total').textContent=n(d.summary.historicalProjectTitleMatches);$('scope').textContent=d.scope;$('caveat').textContent=d.caveat;
const tests=d.statisticalTests, idTest=tests.titleMatchConcentration, rowLinks=Number(d.summary.mappedProjectRows||0), rowPerBarangay=rowLinks/Math.max(1,total), matchesPerCovered=Number(d.summary.historicalProjectTitleMatches||0)/Math.max(1,cov), pText=p=>p<0.001?'p < 0.001':'p = '+Number(p).toFixed(3);
$('row-link-ratio').textContent=rowPerBarangay.toFixed(2)+' : 1';$('matches-covered-ratio').textContent=matchesPerCovered.toFixed(2);
$('coverage-answer').textContent=n(cov)+' of '+n(total)+' official barangays ('+pct(cov*100/Math.max(1,total))+') have at least one historical project-title match. That does not mean one MPB maps to one barangay: '+n(rowLinks)+' mapped project-row links equal '+rowPerBarangay.toFixed(2)+' per official barangay, while '+n(d.summary.historicalProjectTitleMatches)+' historical project-title matches equal '+matchesPerCovered.toFixed(2)+' per covered barangay. These are row/title counts, not verified physical buildings.';
$('coverage-test').innerHTML='<strong>Coverage measure:</strong> '+n(cov)+' / '+n(total)+' barangays have at least one historical project-title match ('+pct(cov*100/Math.max(1,total))+'). This is a barangay coverage rate; it is not the share of MPBs assigned one-to-one to barangays.';
$('concentration-test').innerHTML='<strong>Concentration test · '+idTest.name+':</strong> χ²('+idTest.degreesOfFreedom+') = '+Number(idTest.chiSquare).toLocaleString('en-PH',{{maximumFractionDigits:1}})+', '+idTest.pValueLabel+'. Historical project-title match counts differ strongly from the equal-rate Poisson benchmark. This is evidence of uneven matched-record counts, not a test of how many physical buildings were completed.';
const periodLabel=p=>p.year===2027?'FY2027 · HGAB 3rd':'FY'+p.year+' · GAA', periodOptions='<option value="all">All available years</option>'+d.periods.map(p=>'<option value="'+p.year+'|'+p.stage+'">'+periodLabel(p)+'</option>').join('');
for(const id of ['region-period','province-period','locality-period'])$(id).innerHTML=periodOptions;
const coverage=d.coveragePeriods, maxCoverage=Math.max(1,...coverage.map(x=>x.coveredBarangays));
$('coverage-chart').innerHTML=coverage.map(x=>'<div class="rank-bar"><strong>'+periodLabel(x)+'</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*x.coveredBarangays/maxCoverage+'%"></i></span><span class="rank-total">'+pct(x.coveredBarangays*100/Math.max(1,x.officialBarangays))+'</span></div>').join('');
$('coverage-rows').innerHTML=coverage.map(x=>'<tr><td>FY'+x.year+'</td><td>'+x.stage+'</td><td class="num">'+n(x.coveredBarangays)+'</td><td class="num">'+n(x.officialBarangays)+'</td><td class="num">'+pct(x.coveredBarangays*100/Math.max(1,x.officialBarangays))+'</td><td class="num">'+n(x.projectRows)+'</td><td class="num">'+peso(x.allocationPesos)+'</td></tr>').join('');
const bands=['1','2–3','4–5','6+'], bandValues=bands.map(k=>({{label:k+' title matches',value:d.allYearsMultiplicity[k]||0}})), bandMax=Math.max(1,...bandValues.map(x=>x.value));$('multiplicity-chart').innerHTML=bandValues.map(x=>'<div class="rank-bar"><strong>'+x.label+'</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*x.value/bandMax+'%"></i></span><span class="rank-total">'+n(x.value)+' barangays</span></div>').join('');
$('top-barangays').innerHTML=d.topBarangays.slice(0,20).map((x,i)=>'<tr><td>'+(i+1)+'</td><td>'+x.barangay+'</td><td>'+x.municipality+'</td><td>'+x.province+'</td><td>'+x.region+'</td><td class="num">'+n(x.historicalProjectTitleMatches)+'</td><td class="num">'+peso(x.allocationPesos)+'</td></tr>').join('');
const topAllocation=d.topBarangaysByAllocation.slice(0,20),maxTopAllocation=Math.max(1,...topAllocation.map(x=>x.allocationPesos));$('top-allocation-chart').innerHTML=topAllocation.map((x,i)=>'<div class="rank-bar"><strong>'+(i+1)+'. '+x.barangay+' · '+x.province+'</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*x.allocationPesos/maxTopAllocation+'%"></i></span><span class="rank-total">'+peso(x.allocationPesos)+'</span></div>').join('');$('top-allocation-barangays').innerHTML=topAllocation.map((x,i)=>'<tr><td>'+(i+1)+'</td><td>'+x.barangay+'</td><td>'+x.municipality+'</td><td>'+x.province+'</td><td>'+x.region+'</td><td class="num">'+n(x.historicalProjectTitleMatches)+'</td><td class="num">'+peso(x.allocationPesos)+'</td></tr>').join('');
const types=d.localityTypes, maxType=Math.max(1,...types.map(x=>x.allocationPesos/Math.max(1,x.officialBarangays)));
$('settlement-coverage-chart').innerHTML=types.map(x=>'<div class="rank-bar"><strong>'+x.localityType+'s</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*x.coveredBarangays/Math.max(1,x.officialBarangays)+'%"></i></span><span class="rank-total">'+pct(x.coveredBarangays*100/Math.max(1,x.officialBarangays))+' · '+n(x.coveredBarangays)+' / '+n(x.officialBarangays)+'</span></div>').join('');
$('settlement-test').innerHTML='<strong>Coverage difference · '+tests.cityMunicipalityCoverage.name+':</strong> city '+pct(tests.cityMunicipalityCoverage.cityRate*100)+' ('+n(tests.cityMunicipalityCoverage.cityCovered)+' / '+n(tests.cityMunicipalityCoverage.cityTotal)+') vs municipality '+pct(tests.cityMunicipalityCoverage.municipalityRate*100)+' ('+n(tests.cityMunicipalityCoverage.municipalityCovered)+' / '+n(tests.cityMunicipalityCoverage.municipalityTotal)+'). Difference '+((tests.cityMunicipalityCoverage.cityRate-tests.cityMunicipalityCoverage.municipalityRate)*100).toFixed(2)+' percentage points; z = '+Number(tests.cityMunicipalityCoverage.z).toFixed(2)+', '+pText(tests.cityMunicipalityCoverage.pValue)+'. This tests coverage-rate difference only; administrative type is not rural/urban classification.';
$('settlement-chart').innerHTML=types.map(x=>'<div class="rank-bar"><strong>'+x.localityType+'s</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*(x.allocationPesos/Math.max(1,x.officialBarangays))/maxType+'%"></i></span><span class="rank-total">'+peso(x.allocationPesos/Math.max(1,x.officialBarangays))+' / barangay</span></div>').join('');
$('settlement-rows').innerHTML=types.map(x=>'<tr><td>'+x.localityType+'</td><td class="num">'+n(x.officialBarangays)+'</td><td class="num">'+n(x.coveredBarangays)+'</td><td class="num">'+pct(x.coveredBarangays*100/Math.max(1,x.officialBarangays))+'</td><td class="num">'+n(x.historicalProjectTitleMatches)+'</td><td class="num">'+peso(x.allocationPesos)+'</td><td class="num">'+peso(x.allocationPesos/Math.max(1,x.officialBarangays))+'</td></tr>').join('');
const regions=d.regions.map(x=>({{...x,povertyPct:d.povertyIncidence2023AmongFamiliesPct[x.region],coverageRate:100*x.barangayPlaces/Math.max(1,x.officialBarangays),allocationPerOfficialBarangay:x.allocationPesos/Math.max(1,x.officialBarangays)}})).filter(x=>x.povertyPct!=null);
function corr(xs,ys){{const mx=xs.reduce((a,b)=>a+b,0)/xs.length,my=ys.reduce((a,b)=>a+b,0)/ys.length;let num=0,dx=0,dy=0;xs.forEach((x,i)=>{{num+=(x-mx)*(ys[i]-my);dx+=(x-mx)**2;dy+=(ys[i]-my)**2}});return dx&&dy?num/Math.sqrt(dx*dy):0}}
function ranks(xs){{return xs.map(v=>1+xs.filter(x=>x<v).length+(xs.filter(x=>x===v).length-1)/2)}}
function pearsonText(a,b){{const r=corr(a,b);return(r>=0?'+':'')+r.toFixed(2)}}
function scatter(id,rows,yKey,yLabel,statLabel){{const w=960,h=390,p={{l:112,r:30,t:24,b:68}},xmin=Math.min(...rows.map(x=>x.povertyPct)),xmax=Math.max(...rows.map(x=>x.povertyPct)),ymin=Math.min(0,...rows.map(x=>x[yKey])),ymax=Math.max(...rows.map(x=>x[yKey])),dx=Math.max(1,xmax-xmin),dy=Math.max(1,ymax-ymin),X=x=>p.l+(x-xmin)*(w-p.l-p.r)/dx,Y=y=>h-p.b-(y-ymin)*(h-p.t-p.b)/dy;const comparable=rows.filter(x=>!['REGION 6','REGION 7','NIR'].includes(x.region)),xs=comparable.map(x=>x.povertyPct),ys=comparable.map(x=>x[yKey]),rho=pearsonText(ranks(xs),ranks(ys)),r=pearsonText(xs,ys),axisValue=v=>yKey==='allocationPerOfficialBarangay'?'₱'+(v/1000000).toLocaleString('en-PH',{{maximumFractionDigits:0}})+'M':Number(v).toLocaleString('en-PH',{{maximumFractionDigits:0}});$(id).innerHTML='<p class="muted">Comparable regions only · Pearson r '+r+' · Spearman ρ '+rho+' · n='+comparable.length+' (NIR†, Regions VI/VII omitted from correlations)</p><svg class="scatter" viewBox="0 0 '+w+' '+h+'" role="img" aria-label="'+statLabel+' by regional poverty incidence"><line x1="'+p.l+'" y1="'+Y(ymin)+'" x2="'+(w-p.r)+'" y2="'+Y(ymin)+'" stroke="#526773"/><line x1="'+p.l+'" y1="'+p.t+'" x2="'+p.l+'" y2="'+Y(ymin)+'" stroke="#526773"/><text x="'+(w/2)+'" y="'+(h-15)+'" text-anchor="middle">2023 poverty incidence among families (%)</text><text transform="translate(18 '+(h/2)+') rotate(-90)" text-anchor="middle">'+yLabel+'</text>'+[0,.25,.5,.75,1].map(q=>'<line x1="'+p.l+'" y1="'+(p.t+q*(h-p.t-p.b))+'" x2="'+(w-p.r)+'" y2="'+(p.t+q*(h-p.t-p.b))+'" stroke="#e1e7ed"/><text x="'+(p.l-8)+'" y="'+(p.t+q*(h-p.t-p.b)+4)+'" text-anchor="end" font-size="11">'+axisValue(ymax-q*(ymax-ymin))+'</text>').join('')+rows.map(x=>'<circle cx="'+X(x.povertyPct)+'" cy="'+Y(x[yKey])+'" r="6" fill="#0038A8"><title>'+(x.region==='NIR'?'NIR (derived proxy)':x.region)+': poverty '+x.povertyPct+'%; '+statLabel.toLowerCase()+' '+(yKey==='coverageRate'?pct(x[yKey]):peso(x[yKey]))+'</title></circle><text x="'+(X(x.povertyPct)+8)+'" y="'+(Y(x[yKey])-7)+'" font-size="12">'+(x.region==='NIR'?'NIR†':x.region)+'</text>').join('')+'</svg>'}}
scatter('poverty-coverage-chart',regions,'coverageRate','Barangays covered (%)','Poverty incidence vs. barangay coverage');scatter('poverty-allocation-chart',regions,'allocationPerOfficialBarangay','Allocation per official barangay (₱)','Poverty incidence vs. allocation per official barangay');
$('poverty-test').innerHTML='<strong>Association tests:</strong> '+tests.povertyAssociations.method+'. On '+tests.povertyAssociations.n+' regions with comparable boundaries, poverty vs coverage: Spearman ρ = '+Number(tests.povertyAssociations.coverage.rho).toFixed(2)+', '+pText(tests.povertyAssociations.coverage.pValue)+'; poverty vs allocation per official barangay: Spearman ρ = '+Number(tests.povertyAssociations.allocationPerBarangay.rho).toFixed(2)+', '+pText(tests.povertyAssociations.allocationPerBarangay.pValue)+'. Region VI, Region VII and derived NIR are omitted from these tests because their 2023 poverty geographies overlap. Associations do not establish a prioritization rule.';
const povertyRows=regions.sort((a,b)=>a.povertyPct-b.povertyPct);$('poverty-rows').innerHTML=povertyRows.map(x=>'<tr><td>'+(x.region==='NIR'?'NIR†':x.region)+'</td><td class="num">'+pct(x.povertyPct)+'</td><td class="num">'+n(x.barangayPlaces)+' / '+n(x.officialBarangays)+'</td><td class="num">'+pct(x.coverageRate)+'</td><td class="num">'+peso(x.allocationPerOfficialBarangay)+'</td><td class="num">'+peso(x.allocationPesos)+'</td></tr>').join('');
if(d.poorestProvince2023AmongFamilies)$('poorest-province-note').textContent=d.poorestProvince2023AmongFamilies.province+' ('+pct(d.poorestProvince2023AmongFamilies.povertyPct)+')';
const regionNames=[...new Set(d.regions.map(x=>x.region))].sort((a,b)=>a.localeCompare(b));$('province-region').innerHTML=regionNames.map(x=>'<option>'+x+'</option>').join('');$('locality-region').innerHTML='<option value="all">All regions</option>'+regionNames.map(x=>'<option>'+x+'</option>').join('');
function values(row,period){{const xs=period===all?row.periods:row.periods.filter(p=>p.year+'|'+p.stage===period);return{{projectRows:xs.reduce((a,p)=>a+Number(p.projectRows||0),0),allocationPesos:xs.reduce((a,p)=>a+Number(p.allocationPesos||0),0),barangayPlaces:period===all?Number(row.barangayPlaces||0):xs.reduce((a,p)=>a+(Number(p.coveredBarangays)||0),0)}}}}
function render(rows,period,tbody,chart,labelKey,placeCount){{const xs=rows.map(x=>({{...x,...values(x,period)}})).filter(x=>x.projectRows||x.allocationPesos).sort((a,b)=>b.allocationPesos-a.allocationPesos||b.projectRows-a.projectRows||a[labelKey].localeCompare(b[labelKey]));const mx=Math.max(1,...xs.map(x=>x.allocationPesos));$(chart).innerHTML=xs.slice(0,15).map((x,i)=>'<div class="rank-bar"><strong>'+(i+1)+'. '+x[labelKey]+'</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*x.allocationPesos/mx+'%"></i></span><span class="rank-total">'+peso(x.allocationPesos)+'</span></div>').join('')||'<p class="muted">No mapped rows in this period.</p>';$(tbody).innerHTML=xs.map((x,i)=>'<tr><td>'+(i+1)+'</td><td>'+x[labelKey]+'</td>'+(labelKey==='province'?'<td class="num">'+(x.povertyIncidence2023AmongFamiliesPct==null?'—':pct(x.povertyIncidence2023AmongFamiliesPct))+'</td>':'')+'<td class="num">'+n(x[placeCount]||x.barangayPlaces)+'</td><td class="num">'+n(x.projectRows)+'</td><td class="num">'+peso(x.allocationPesos)+'</td></tr>').join('')||'<tr><td colspan="5">No mapped rows.</td></tr>'}}
function drawRanks(){{render(d.regions,$('region-period').value,'region-rows','region-chart','region','barangayPlaces');render(d.provinces.filter(x=>x.region===$('province-region').value),$('province-period').value,'province-rows','province-chart','province','barangayPlaces')}}
function drawLocalities(){{const type=$('locality-type').value,region=$('locality-region').value,period=$('locality-period').value;let rows=d.localities.filter(x=>x.localityType===type&&(region==='all'||x.region===region)).map(x=>({{...x,...values(x,period)}})).sort((a,b)=>(b.allocationPesos/Math.max(1,b.officialBarangays))-(a.allocationPesos/Math.max(1,a.officialBarangays)));const mx=Math.max(1,...rows.slice(0,15).map(x=>x.allocationPesos/Math.max(1,x.officialBarangays)));$('locality-chart').innerHTML=rows.slice(0,15).map((x,i)=>'<div class="rank-bar"><strong>'+(i+1)+'. '+x.locality+'</strong><span class="rank-track"><i class="rank-fill" style="width:'+100*(x.allocationPesos/Math.max(1,x.officialBarangays))/mx+'%"></i></span><span class="rank-total">'+peso(x.allocationPesos/Math.max(1,x.officialBarangays))+' / barangay</span></div>').join('');$('locality-rows').innerHTML=rows.map((x,i)=>'<tr><td>'+(i+1)+'</td><td>'+x.locality+'</td><td>'+x.province+'</td><td>'+x.region+'</td><td class="num">'+n(x.barangayPlaces)+' / '+n(x.officialBarangays)+'</td><td class="num">'+n(x.projectRows)+'</td><td class="num">'+peso(x.allocationPesos)+'</td><td class="num">'+peso(x.allocationPesos/Math.max(1,x.officialBarangays))+'</td></tr>').join('')||'<tr><td colspan="8">No localities match this selection.</td></tr>'}}
for(const id of ['region-period','province-period'])$(id).addEventListener('change',drawRanks);$('province-region').addEventListener('change',drawRanks);for(const id of ['locality-type','locality-region','locality-period'])$(id).addEventListener('change',drawLocalities);drawRanks();drawLocalities()
}}).catch(e=>{{for(const id of ['coverage-rows','settlement-rows','poverty-rows','region-rows','province-rows','locality-rows'])document.getElementById(id).innerHTML='<tr><td colspan="8">MPB data unavailable: '+String(e.message)+'</td></tr>'}});
</script></body></html>'''
    from uniform_report_menu import apply_page as apply_menu
    html = apply_menu(html, PAGE)
    from report_table_presentation import apply_page_table_module
    html, contract = apply_page_table_module(PAGE, html)
    for destination in (STATIC / PAGE, OUT / PAGE):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html, encoding='utf-8')
    return {'page': PAGE, 'data': DATA, 'regions': len(data['regions']), 'provinces': len(data['provinces']), 'tableContract': contract}


if __name__ == '__main__':
    print(json.dumps(build_page(), ensure_ascii=False, indent=2))
