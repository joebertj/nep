#!/usr/bin/env python3
"""Build district-level historical project allocation datasets and report pages.

Uses the shared DPWH project-title classifier and conservative legislative
district location rules. Historical rows map to the current district roster;
they are not historical member-attribution claims.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ODV / 'analysis'))

from analyze_priority_repeats import classify, previous_rows  # noqa: E402
import build_congress_allocation_data as classifier  # noqa: E402
import enrich_nep_preview_representatives as reps  # noqa: E402
from strict_congress_geography import GeographicAttribution  # noqa: E402

OUT = STATIC / 'integrated-district-data.json'
PROJECT_OUT = STATIC / 'integrated-project-data.json'
PHOTO_OVERRIDES = STATIC / 'integrated-representative-photo-overrides.json'
GAA_MANIFEST = ROOT / 'data_sources' / 'gaa-explorer-manifest.json'


def unavailable_legacy_years(loaded_years):
    """Return explicit, non-computational placeholders for FY2000–2019."""
    manifest = json.loads(GAA_MANIFEST.read_text(encoding='utf-8'))
    statuses = {int(row['year']): row.get('status') for row in manifest.get('years', [])}
    result = []
    for year in range(2000, 2020):
        if year in loaded_years:
            continue
        status = statuses.get(year)
        if status == 'reenacted_no_new_gaa':
            reason = 'No new GAA was enacted for this fiscal year; it is not a zero-allocation observation.'
        elif year <= 2008:
            reason = 'The Explorer manifest marks this year as partial historical coverage; DPWH project-level detail is not complete.'
        elif year == 2014:
            reason = 'The available snapshot contains aggregate/control rows, not named DPWH project lines.'
        elif 2009 <= year <= 2013:
            reason = 'Named DPWH titles exist in the Explorer baseline, but this district series has no reconciled year extract; DEO names are also absent.'
        elif year == 2015:
            reason = 'Project-level DPWH rows appear in the Explorer baseline, but no reconciled year extract is loaded into this district series.'
        elif year == 2019:
            reason = 'The manifest marks published editions as differing; the inspected snapshot has no named DPWH project lines.'
        else:
            reason = 'No compatible, reconciled project-level extract is loaded for this report.'
        result.append({'year': year, 'available': False, 'status': status or 'not_loaded', 'reason': reason})
    return result


def slug(value: str) -> str:
    return '-'.join(re.findall(r'[a-z0-9]+', str(value or '').casefold()))


def roster_and_geography():
    raw = json.loads(reps.ROSTER_PATH.read_text(encoding='utf-8'))
    seats_by_key = {}
    for row in raw:
        province = str(row.get('province') or '').strip()
        district = reps.district_key(row.get('district'))
        name = classifier.clean_name(str(row.get('representative') or ''))
        label = classifier.DISTRICT_LABELS.get(district)
        if not province or not name or not label or reps.norm(name) == 'special election':
            continue
        seats_by_key[(reps.norm(province), label)] = {
            'district': f'{province} · {label}', 'province': province,
            'districtLabel': label, 'representative': name,
            'districtId': 'leg:' + slug(province) + ':' + slug(label.replace(' District', '')),
        }
    seats = sorted(seats_by_key.values(), key=lambda row: (reps.norm(row['province']), row['districtLabel']))
    return seats, GeographicAttribution(ODV / 'static/data', seats)


def representative_periods(seats):
    """Resolve budget-year representatives from explicit ODV term intervals.

    Budget-year rows use the House member serving when that budget was
    prepared: FY2020–FY2022 -> 18th Congress, FY2023–FY2025 -> 19th, and
    FY2026 onward -> 20th. Broad 2016–2025 defaults in the ODV config are
    deliberately ignored. Ambiguous and absent matches stay unresolved.
    """
    source = json.loads((ODV / 'static/data/congressmen_consolidated.json').read_text(encoding='utf-8'))
    aliases = {
        'antipolo city': 'antipolo', 'bacolod city': 'bacolod', 'baguio city': 'baguio',
        'butuan city': 'butuan', 'cagayan de oro city': 'cagayan de oro',
        'calamba city': 'calamba', 'caloocan city': 'caloocan',
        'valenzuela city': 'valenzuela', 'binan city': 'binan',
    }

    def seat_key(province, district):
        place = reps.norm(province)
        place = aliases.get(place, place)
        return place, reps.district_key(district)

    seats_by_key = {seat_key(row['province'], row['districtLabel']): row for row in seats}
    candidates = defaultdict(list)
    for person in source:
        if not person.get('province') or not person.get('district_number'):
            continue
        terms = person.get('terms') or []
        if isinstance(terms, str):
            try:
                terms = json.loads(terms)
            except json.JSONDecodeError:
                terms = []
        key = seat_key(person['province'], person['district_number'])
        if key not in seats_by_key:
            continue
        for term in terms:
            try:
                start, end = int(term['start']), int(term['end'])
            except (KeyError, TypeError, ValueError):
                continue
            # This range is the default inserted for people with no term data.
            if (start, end) == (2016, 2025):
                continue
            candidates[key].append((start, end, str(person.get('display_name') or '').strip()))

    audit = {}
    for seat in seats:
        key = seat_key(seat['province'], seat['districtLabel'])
        by_period = {}
        status_by_period = {}
        for year in range(2020, 2028):
            stage = 'HGAB 3rd' if year == 2027 else 'GAA'
            if year >= 2026:
                by_period[f'{year}|{stage}'] = seat['representative']
                status_by_period[f'{year}|{stage}'] = '20th Congress roster'
                continue
            anchor_year = year - 1
            matches = [(start, name) for start, end, name in candidates.get(key, [])
                       if start <= anchor_year < end and name]
            if matches:
                latest_start = max(start for start, _ in matches)
                names = {name for start, name in matches if start == latest_start}
                by_period[f'{year}|{stage}'] = next(iter(names)) if len(names) == 1 else None
                status_by_period[f'{year}|{stage}'] = 'explicit ODV term' if len(names) == 1 else 'ambiguous term records'
            else:
                by_period[f'{year}|{stage}'] = None
                status_by_period[f'{year}|{stage}'] = 'no explicit term record'
        seat['representativesByPeriod'] = by_period
        seat['representativeStatusByPeriod'] = status_by_period

    # Explicit, source-linked exceptions supplement ODV's incomplete term
    # intervals and provide portraits from the matching Congress.
    photo_overrides = json.loads(PHOTO_OVERRIDES.read_text(encoding='utf-8')) if PHOTO_OVERRIDES.exists() else []
    overrides_by_seat = defaultdict(list)
    for override in photo_overrides:
        overrides_by_seat[override.get('districtId')].append(override)
    for seat in seats:
        for override in overrides_by_seat.get(seat['districtId'], []):
            for period in override.get('periods', []):
                seat['representativesByPeriod'][period] = override['representative']
                seat['representativeStatusByPeriod'][period] = override.get('representativeStatus', 'sourced Congress roster override')

    # Current BetterGov roster portraits are usable for historic bars only
    # when the same named person held that seat in the budget year. Do not
    # carry a successor's face backwards across terms.
    portrait_data = json.loads((STATIC / 'congress-district-roster.json').read_text(encoding='utf-8'))
    portrait_by_id = {row.get('districtId'): row for row in portrait_data.get('districts', [])}
    surname_aliases = {
        'begtang': 'bulutbegtang', 'alfonso': 'vargasalfonso',
        'mercado': 'mercadorevilla', 'dizon': 'ouanodizon',
    }
    generational_suffixes = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}

    def name_tokens(value):
        return re.findall(r'[a-z]+', str(value or '').casefold())

    for seat in seats:
        # Prefer exact IDs so Cebu vs Cebu City and Quezon vs Quezon City
        # remain distinct. Only fall back to the City-qualified ID when this
        # exact legislative seat has no portrait-roster entry.
        city_prefix, district_number = seat['districtId'].rsplit(':', 1)
        city_id = city_prefix + '-city:' + district_number
        portrait = portrait_by_id.get(seat['districtId']) or portrait_by_id.get(city_id) or {}
        current_name = seat.get('representative') or ''
        roster_name = portrait.get('name') or ''
        # Roster display names use "Surname, Given" while district records
        # use "Given Surname". Require a surname match, including known
        # married-name variants, before using the portrait.
        surname = name_tokens(roster_name.split(',')[0])[0:]
        current_tokens = name_tokens(current_name)
        surname_key = ''.join(surname)
        expected = surname_aliases.get(surname_key, surname_key)
        person_tokens = [token for token in current_tokens if token not in generational_suffixes]
        surname_ok = bool(expected and any(''.join(person_tokens[i:]) == expected for i in range(len(person_tokens))))
        seat['representativePhotoUrl'] = (portrait.get('photoUrl')
            if portrait.get('status') == 'resolved' and portrait.get('photoUrl') and surname_ok else None)
        seat['representativePhotoName'] = current_name if seat['representativePhotoUrl'] else None
        seat['representativePhotosByPeriod'] = {
            key: (seat['representativePhotoUrl'] if seat['representativePhotoUrl'] and name == current_name else None)
            for key, name in seat['representativesByPeriod'].items()
        }
        for override in overrides_by_seat.get(seat['districtId'], []):
            for period in override.get('periods', []):
                seat['representativePhotosByPeriod'][period] = override.get('photoUrl')

        # A member who serves across adjacent Congresses is still the same
        # person. Reuse a sourced portrait for any other budget period in
        # which the exact same representative name is recorded; do not carry
        # a portrait across a change of representative.
        photo_by_name = {}
        for period, name in seat['representativesByPeriod'].items():
            photo = seat['representativePhotosByPeriod'].get(period)
            if name and photo:
                photo_by_name.setdefault(name, photo)
        for period, name in seat['representativesByPeriod'].items():
            if name and not seat['representativePhotosByPeriod'].get(period):
                seat['representativePhotosByPeriod'][period] = photo_by_name.get(name)

    for year in range(2020, 2028):
        stage = 'HGAB 3rd' if year == 2027 else 'GAA'
        values = [seat['representativesByPeriod'].get(f'{year}|{stage}') for seat in seats]
        statuses = [seat['representativeStatusByPeriod'].get(f'{year}|{stage}') for seat in seats]
        audit[f'{year}|{stage}'] = {
            'resolvedDistricts': sum(bool(value) for value in values),
            'unresolvedDistricts': sum(not value for value in values),
            'ambiguousDistricts': statuses.count('ambiguous term records'),
            'missingTermDistricts': statuses.count('no explicit term record'),
        }
    return audit


def current_hgab_rows():
    path = ROOT / 'hb10858_3rd_dpwh_projects.json'
    source = json.loads(path.read_text(encoding='utf-8'))
    rows = []
    for item in source['data']['data']:
        name = str(item.get('projectName') or '')
        category = classify(name)
        if not category:
            continue
        rows.append({
            'year': 2027, 'stage': 'HGAB 3rd', 'category': category, 'name': name,
            'amountPesos': int(round(float(item.get('amountPesos') or 0))),
            'source': f"HGAB 3rd · {item.get('sourceVolume') or 'DPWH schedule'} · PDF p. {item.get('sourcePage') or 'not stated'}",
            'sourcePage': str(item.get('sourcePage') or ''),
            'sourceId': str(item.get('id') or ''), 'historical': False,
        })
    return rows


def district_decision(row, geography, seats, historical: bool, coordinate_features=None, seat_indices=None):
    title = row['name']
    if historical:
        # Historical GAA rows do not inherit current bridge/inventory context.
        decision = geography._resolve_geographic({'projectName': title})
    else:
        decision = geography.resolve({'projectName': title})

    def seat_index(parent_names, district_label):
        return next((index for index, seat in enumerate(seats)
                     if slug(seat['province']) in parent_names
                     and seat['districtLabel'] == district_label), None)

    held = False
    caloocan = classifier._caloocan_barangay_district(title)
    if caloocan:
        label, number = caloocan
        idx = seat_index({'caloocan', 'caloocan-city'}, label)
        if idx is not None:
            decision['indices'] = [idx]
            decision['reasons'] = []
            decision['evidence'].append({'basis': 'Numbered Caloocan barangay statutory crosswalk', 'barangayNumber': number})

    manila_barangay = classifier._manila_barangay_district(title)
    manila_zone = classifier._manila_zone_district(title)
    manila_clues = [x for x in (manila_barangay, manila_zone) if x]
    if manila_clues:
        labels = {x[0] for x in manila_clues}
        idx = seat_index({'manila', 'manila-city'}, next(iter(labels))) if len(labels) == 1 else None
        if idx is not None:
            decision['indices'] = [idx]
            decision['reasons'] = []
            decision['evidence'].append({'basis': 'Manila statutory barangay / administrative-zone crosswalk'})
        else:
            decision['indices'] = []
            decision['reasons'] = ['Conflicting or unresolved Manila district evidence']

    antipolo = classifier._antipolo_barangay_district(title)
    if antipolo:
        label, barangays = antipolo
        idx = seat_index({'antipolo', 'antipolo-city'}, label)
        if idx is not None:
            decision['indices'] = [idx]
            decision['reasons'] = []
            decision['evidence'].append({'basis': 'RA 9232 Antipolo barangay crosswalk', 'barangays': barangays})

    indices = decision.get('indices') or []
    if len(indices) == 1:
        return indices[0], 'unique', ''
    if len(indices) > 1:
        return None, 'shared', 'Title describes locations in multiple legislative districts'

    # The same title-matched boundary-point fallback used by the current classifier.
    if not historical and row.get('sourceId'):
        return None, 'unresolved', '; '.join(decision.get('reasons') or ['No supported district attribution'])
    if classifier._title_point(title) and coordinate_features is not None:
        point = classifier._coordinate_district({'projectName': title}, coordinate_features, seat_indices or {})
        if point:
            return point['index'], 'unique', 'Unique named-locality printed-coordinate match to DPWH district boundary'
    return None, 'unresolved', '; '.join(decision.get('reasons') or ['No supported district attribution'])


def build():
    seats, geography = roster_and_geography()
    representative_audit = representative_periods(seats)
    historical = previous_rows()
    rows = []
    coverage = []
    prepared = []
    for year, source_rows in sorted(historical.items()):
        year_input = []
        for item in source_rows:
            name = str(item.get('name') or '')
            category = classify(name)
            if not category:
                continue
            year_input.append({
                'year': int(year), 'stage': 'GAA', 'category': category, 'name': name,
                'amountPesos': int(round(float(item.get('amount') or 0))),
                'source': str(item.get('source') or f'FY{year} GAA'),
                'sourceId': str(item.get('source') or ''), 'historical': True,
            })
        prepared.extend(year_input)
    prepared.extend(current_hgab_rows())
    coordinate_features = classifier._coordinate_district_features(
        [{'projectName': row['name']} for row in prepared]
    )
    seat_indices = {(classifier._place_key(seat['province']), seat['districtLabel']): index
                    for index, seat in enumerate(seats)}
    historical_prepared = [row for row in prepared if row['stage'] == 'GAA']
    hgab = [row for row in prepared if row['stage'] == 'HGAB 3rd']
    for year in sorted(historical):
        year_input = [row for row in historical_prepared if row['year'] == int(year)]
        for row in year_input:
            index, status, reason = district_decision(row, geography, seats, historical=True,
                                                      coordinate_features=coordinate_features,
                                                      seat_indices=seat_indices)
            row.update({'districtId': seats[index]['districtId'] if index is not None else None,
                        'district': seats[index]['district'] if index is not None else None,
                        'representative': seats[index]['representative'] if index is not None else None,
                        'attributionStatus': status, 'attributionNote': reason})
        assigned = [row for row in year_input if row['districtId']]
        rows.extend(assigned)
        coverage.append({
            'year': int(year), 'stage': 'GAA', 'sourceRowsClassified': len(year_input),
            'assignedRows': len(assigned), 'assignedPesos': sum(r['amountPesos'] for r in assigned),
            'unresolvedRows': len(year_input) - len(assigned),
            'unresolvedPesos': sum(r['amountPesos'] for r in year_input if not r['districtId']),
        })

    for row in hgab:
        index, status, reason = district_decision(row, geography, seats, historical=False,
                                                  coordinate_features=coordinate_features,
                                                  seat_indices=seat_indices)
        row.update({'districtId': seats[index]['districtId'] if index is not None else None,
                    'district': seats[index]['district'] if index is not None else None,
                    'representative': seats[index]['representative'] if index is not None else None,
                    'attributionStatus': status, 'attributionNote': reason})
    assigned_hgab = [row for row in hgab if row['districtId']]
    rows.extend(assigned_hgab)
    coverage.append({
        'year': 2027, 'stage': 'HGAB 3rd', 'sourceRowsClassified': len(hgab),
        'assignedRows': len(assigned_hgab), 'assignedPesos': sum(r['amountPesos'] for r in assigned_hgab),
        'unresolvedRows': len(hgab) - len(assigned_hgab),
        'unresolvedPesos': sum(r['amountPesos'] for r in hgab if not r['districtId']),
    })

    district_lookup = {seat['districtId']: seat for seat in seats}
    annual = defaultdict(lambda: {'lineItems': 0, 'totalPesos': 0, 'categories': defaultdict(lambda: {'lineItems': 0, 'totalPesos': 0})})
    for row in rows:
        key = (row['year'], row['stage'], row['districtId'])
        item = annual[key]
        item['lineItems'] += 1
        item['totalPesos'] += row['amountPesos']
        category = item['categories'][row['category']]
        category['lineItems'] += 1
        category['totalPesos'] += row['amountPesos']

    annual_rows = []
    for (year, stage, district_id), values in annual.items():
        seat = district_lookup[district_id]
        annual_rows.append({
            'year': year, 'stage': stage, **seat,
            'representative': seat['representativesByPeriod'].get(f'{year}|{stage}'),
            'representativePhotoUrl': seat['representativePhotosByPeriod'].get(f'{year}|{stage}'),
            'lineItems': values['lineItems'], 'totalPesos': values['totalPesos'],
            'categories': dict(values['categories']),
        })
    annual_rows.sort(key=lambda r: (r['year'], r['stage'], r['district']))
    data = {
        'title': 'Historical DPWH district project allocations',
        'periods': [{'year': r['year'], 'stage': r['stage']} for r in coverage],
        'yearAvailability': unavailable_legacy_years(set(historical)),
        'categories': ['Multi-purpose building', 'Flood control', 'Bridge', 'Road'],
        'districts': seats,
        'coverage': coverage,
        'annual': annual_rows,
        'projects': [{key: row[key] for key in ('year', 'stage', 'category', 'name', 'amountPesos', 'source', 'districtId')} for row in rows],
        'method': {
            'classifier': 'Shared title classifier from analyze_priority_repeats.py: Multi-purpose building, flood control, bridge and road.',
            'attribution': 'Current legislative-district roster and strict qualified-location rules. Unique assignments only; shared and unresolved titles remain excluded from district totals.',
            'timeLimit': 'Project locations are assigned to current legislative district boundaries. Representative labels are year-specific: explicit ODV term intervals for FY2020–FY2025 and the current 20th Congress roster for FY2026–FY2027. Ambiguous, missing, and default-only term records are left unresolved.',
            'representativeCoverage': representative_audit,
            'representativeSource': 'ODV static/data/congressmen_consolidated.json explicit term intervals; ODV static/data/20th_congress_representatives.json for FY2026–FY2027; source-linked, named exceptions are recorded in integrated-representative-photo-overrides.json. Broad default 2016–2025 terms are excluded.',
            'sources': 'FY2016–FY2018 title-classified DPWH current-new-appropriation rows from the BetterGov GAA Explorer baseline; FY2020–FY2025 ODV annual GAA data; FY2026 DPWH Details Enrolled Copy; FY2027 House GAB 3rd-reading DPWH schedule. FY2016–FY2018 use a separate source layer; FY2027 is a proposal, not enacted GAA.',
        },
    }
    summary_data = {key: value for key, value in data.items() if key != 'projects'}
    project_data = {key: value for key, value in data.items() if key != 'annual'}
    OUT.write_text(json.dumps(summary_data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    PROJECT_OUT.write_text(json.dumps(project_data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return data


HISTORY_HERO_CSS = '.history-hero{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(300px,.9fr);gap:24px;align-items:center;margin:18px 0 24px;padding:clamp(22px,3vw,34px);border-left:7px solid #FCD116;border-radius:16px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff;box-shadow:0 12px 30px #00246A22}.history-hero h2{margin:0 0 8px;color:#fff!important;font-size:clamp(24px,3vw,36px)!important;line-height:1.1!important}.history-hero p{margin:0;color:#f3f6ff}.history-hero-kicker{display:block;margin-bottom:8px;color:#FCD116;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.history-hero-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.history-hero-stats>div{display:flex;min-height:100px;flex-direction:column;justify-content:center;gap:7px;padding:14px;border:1px solid #ffffff35;border-radius:11px;background:#ffffff12}.history-hero-stats strong{color:#FCD116;font-size:clamp(24px,3vw,36px);line-height:1;font-variant-numeric:tabular-nums}.history-hero-stats span{color:#f3f6ff;font-size:12px;line-height:1.3}@media(max-width:760px){.history-hero{grid-template-columns:1fr}.history-hero-stats>div{min-height:75px}}'

def page_shell(title, teaser, page, content, data_url='integrated-district-data.json'):
    from uniform_report_menu import NAV, CSS
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · BetterGov</title><meta name="description" content="District allocations for classified DPWH projects across enacted GAA years and HGAB 3rd reading."><link rel="stylesheet" href="research-theme.css?v=20261029"><link rel="stylesheet" href="report-table-readability.css?v=20261029"><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6f5;color:#18303b;font:15px/1.5 system-ui,sans-serif}}header.uniform-report-header{{background:#102f3e;color:white;padding:24px clamp(16px,2vw,32px)}}main{{width:100%;padding:24px clamp(16px,2vw,32px) 60px}}.intro,.panel,.stat{{background:#fff;border:1px solid #c6dbd6;border-radius:14px;padding:18px;margin:0 0 16px}}.intro{{border-left:5px solid #087e78}}.filters{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}input,select,button{{font:inherit;padding:9px 11px;border:1px solid #b6c9c4;border-radius:8px;background:#fff;color:#18303b}}input{{flex:1;min-width:200px}}button{{cursor:pointer}}button:disabled{{opacity:.45;cursor:default}}.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}}.stat{{margin:0;padding:14px}}.stat strong{{display:block;font-size:clamp(20px,2vw,28px);color:#087e78}}.stat span,.muted{{color:#526773;font-size:13px}}.chart{{width:100%;overflow:auto}}svg{{display:block;width:100%;height:auto;min-width:650px}}.table-wrap{{width:100%;overflow-x:auto}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}th,td{{padding:9px 10px;text-align:left;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere}}th{{background:#eaf2f0}}td.amount{{text-align:right;font-variant-numeric:tabular-nums}}.district-cell{{font-weight:700}}.representative{{display:flex;align-items:center;gap:8px}}.representative img{{width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid #FCD116}}.chart-face{{width:26px;height:26px;object-fit:cover;border-radius:50%;stroke:#FCD116}}.representative-card{{display:flex;align-items:center;gap:10px;margin:10px 0 14px;padding:10px 12px;border:1px solid #E0E0E0;border-radius:10px;background:#fff}}.representative-card img{{width:48px;height:48px;object-fit:cover;border-radius:50%;border:3px solid #FCD116}}.badge{{display:inline-block;padding:2px 7px;border-radius:99px;background:#edf4f2;color:#28545a;font-size:11px}}.pagination{{display:flex;justify-content:space-between;align-items:center;margin:12px 0}}.caution{{padding:12px;background:#fff4dd;border-left:4px solid #b65b09}}@media(max-width:760px){{main{{padding:16px 12px}}.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}th,td{{font-size:12px;padding:6px}}}}
</style></head><body class="bettergov-research"><header class="uniform-report-header"><div class="report-header-heading"><a class="report-header-brand" href="https://bettergov.ph/" aria-label="BetterGov home"><img src="https://assets.bettergov.ph/logos/webp/horizontal-black.webp" alt="BetterGov"></a><div class="eyebrow">BetterGov · Budget research</div><h1>{title}</h1><p>{teaser}</p></div>{NAV}</header><main>{content}</main><script src="report-table-readability.js?v=20261029"></script></body></html>'''
    return html.replace('</style></head>', HISTORY_HERO_CSS + '</style></head>', 1)


def make_pages(data):
    def data_loader(url):
        version = hashlib.sha256((STATIC / url).read_bytes()).hexdigest()[:12]
        return """<script>window.integratedDataPromise=fetch('__URL__?v=__VERSION__').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).catch(e=>{document.querySelector('main').insertAdjacentHTML('afterbegin','<p class="caution">Integrated district data could not be loaded. Serve this page through the local app or a web server.</p>');throw e});</script>""".replace('__URL__', url).replace('__VERSION__', version)
    data_js = data_loader('integrated-district-data.json')
    detail_data_js = data_loader('integrated-project-data.json')
    base = '''<aside id="report-evidence-notice" class="intro gaa-year-coverage report-disclaimer" role="note"><strong>Disclaimer.</strong> This page compares classified DPWH budget allocations across project categories and years by legislative district. Totals include uniquely assigned project rows; shared or unresolved locations are excluded. Historical rows use today’s district boundaries and should not be read as historical representative attribution. Allocations are not payments.<p><strong>Older GAA coverage.</strong> FY2016–2018 project-family rows come from the GAA Explorer DPWH baseline. They are title-classified current new appropriations and form a separate historical source layer. FY2000–2008 has partial or aggregate-only coverage; FY2001, FY2004 and FY2006 had no new enacted GAA; FY2009–2013 lacks DEO-level detail and is not reconciled to this district series; FY2014–2015 has no reconciled named-project extract; FY2019 editions differ and named-project detail is absent. Unavailable years are disabled and excluded from totals, averages and charts.</p></aside>'''
    history_hero = ('<section class="history-hero" aria-label="Historical data coverage"><div><span class="history-hero-kicker">DPWH · historical allocations</span><h2>Trace project allocations across years and districts</h2><p>Unavailable and unreconciled years stay out of comparisons. FY2027 is the HGAB 3rd-reading proposal, not enacted GAA.</p></div><div class="history-hero-stats"><div><strong>'+str(len(data['periods']))+'</strong><span>available budget year and stage snapshots</span></div><div><strong>'+str(len(data['categories']))+'</strong><span>shared project categories</span></div><div><strong>'+str(len(data['districts']))+'</strong><span>district records in this dataset</span></div></div></section>')
    base += history_hero
    allocations = base + '''<section class="panel"><h2>Compare annual district allocations</h2><p class="muted">This view compares each district’s yearly totals and ranks districts for the selected period. The representative column uses year-specific roster data; unresolved historic entries are shown explicitly. For project titles and line-level allocations, open <a href="integrated.html">Historical · Project records</a>.</p><div class="filters"><label>District <select id="trend-district"></select></label><label>Year <select id="rank-year"></select></label><label>Project category <select id="rank-category"></select></label><button id="rank-export" type="button">Export CSV</button></div><div id="allocation-chart" class="chart" aria-live="polite"></div><div class="stats"><div class="stat"><strong id="period-total">—</strong><span>Selected district · selected period</span></div><div class="stat"><strong id="period-lines">—</strong><span>Classified project records</span></div><div class="stat"><strong id="unresolved-total">—</strong><span>Unassigned allocation · selected period</span></div><div class="stat"><strong id="period-coverage">—</strong><span>District-assigned share of classified amount</span></div></div></section><section class="panel"><h2>District ranking · selected year</h2><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Legislative district</th><th>Representative for budget year</th><th>Classified lines</th><th>Allocation</th><th>Share of assigned total</th></tr></thead><tbody id="district-ranking"></tbody></table></div><p class="muted" id="ranking-status"></p></section>''' + data_js + '''<script>
window.integratedDataPromise.then(D=>{const $=id=>document.getElementById(id),peso=n=>'₱'+Number(n||0).toLocaleString('en-PH',{maximumFractionDigits:0}),fmt=n=>Number(n||0).toLocaleString('en-PH'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const periods=D.periods,annual=D.annual,coverage=D.coverage,dist=$('trend-district'),yr=$('rank-year'),cat=$('rank-category');for(const x of D.districts){const o=document.createElement('option');o.value=x.districtId;o.textContent=x.district;dist.append(o)}for(const p of periods){const o=document.createElement('option');o.value=p.year+'|'+p.stage;o.textContent=p.stage==='GAA'?'FY'+p.year+' GAA':'FY'+p.year+' '+p.stage;yr.append(o)}for(const p of (D.yearAvailability||[])){const o=document.createElement('option');o.value='unavailable|'+p.year;o.textContent='FY'+p.year+' · Data unavailable';o.disabled=true;o.title=p.reason;yr.append(o)}[...yr.options].sort((a,b)=>Number((a.value.match(/\\d{4}/)||[0])[0])-Number((b.value.match(/\\d{4}/)||[0])[0])).forEach(o=>yr.append(o));for(const c of ['all',...D.categories]){const o=document.createElement('option');o.value=c;o.textContent=c==='all'?'All classified categories':c;cat.append(o)}dist.value=D.districts[0]?.districtId||'';yr.value=periods[periods.length-1]?.year+'|'+periods[periods.length-1]?.stage;
function currentPeriod(){return yr.value.split('|')}function selectedRows(){const [y,s]=currentPeriod();return annual.filter(x=>x.year===Number(y)&&x.stage===s&&(cat.value==='all'||x.categories[cat.value]))}function draw(){const [y,s]=currentPeriod(),selected=dist.value,catKey=cat.value;const series=periods.map(p=>{const x=annual.find(a=>a.year===p.year&&a.stage===p.stage&&a.districtId===selected);return {label:p.stage==='GAA'?'FY'+p.year:'FY'+p.year+' HGAB 3rd',value:catKey==='all'?(x?.totalPesos||0):(x?.categories?.[catKey]?.totalPesos||0),year:p.year,stage:p.stage,photo:x?.representativePhotoUrl}}),max=Math.max(...series.map(x=>x.value),1),W=1100,H=390,left=70,right=25,top=24,bottom=112,plotW=W-left-right,plotH=H-top-bottom,band=plotW/series.length,bw=Math.min(76,band*.58),base=H-bottom;const grid=[0,.25,.5,.75,1].map(t=>{const yy=base-plotH*t;return '<g><line x1="'+left+'" y1="'+yy+'" x2="'+(W-right)+'" y2="'+yy+'" stroke="#d9e3e1"/><text x="'+(left-9)+'" y="'+(yy+4)+'" text-anchor="end" font-size="10" fill="#526773">'+(max*t?('₱'+(max*t/1e9).toFixed(1)+'B'):'0')+'</text></g>'}).join('');$('allocation-chart').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Annual classified project allocations for selected district as vertical bars">'+grid+series.map((x,i)=>{const h=x.value/max*plotH,x0=left+i*band+(band-bw)/2,y0=base-h,cx=x0+bw/2;return '<g><title>'+esc(x.label)+' · '+peso(x.value)+'</title><rect x="'+x0+'" y="'+y0+'" width="'+bw+'" height="'+h+'" fill="#087e78" rx="5"/><text x="'+cx+'" y="'+Math.max(top+12,y0-8)+'" text-anchor="middle" font-size="11" fill="#18303b">'+(x.value?'₱'+(x.value/1e9).toFixed(1)+'B':'—')+'</text><text x="'+cx+'" y="'+(base+22)+'" text-anchor="middle" font-size="11" fill="#18303b">'+esc(x.label)+'</text>'+(x.photo?'<image class="chart-face" href="'+esc(x.photo)+'" x="'+(cx-13)+'" y="'+(base+37)+'" width="26" height="26" preserveAspectRatio="xMidYMid slice"><title>'+esc(annual.find(a=>a.year===x.year&&a.stage===x.stage&&a.districtId===selected)?.representative||'Representative')+'</title></image>':'')+'</g>'}).join('')+'</svg>';
const row=annual.find(a=>a.year===Number(y)&&a.stage===s&&a.districtId===selected),value=catKey==='all'?(row?.totalPesos||0):(row?.categories?.[catKey]?.totalPesos||0),lines=catKey==='all'?(row?.lineItems||0):(row?.categories?.[catKey]?.lineItems||0),c=coverage.find(a=>a.year===Number(y)&&a.stage===s);$('period-total').textContent=peso(value);$('period-lines').textContent=fmt(lines);$('unresolved-total').textContent=peso(c?.unresolvedPesos);$('period-coverage').textContent=(c&&c.assignedPesos+c.unresolvedPesos>0?(100*c.assignedPesos/(c.assignedPesos+c.unresolvedPesos)).toFixed(1)+'%':'—');
const rows=selectedRows().map((x)=>({...x,displayValue:catKey==='all'?x.totalPesos:x.categories[catKey].totalPesos,displayLines:catKey==='all'?x.lineItems:x.categories[catKey].lineItems})).filter(x=>x.displayValue>0).sort((a,b)=>b.displayValue-a.displayValue);const total=rows.reduce((n,x)=>n+x.displayValue,0);$('district-ranking').innerHTML=rows.map((x,i)=>'<tr><td>'+ (i+1)+'</td><td class="district-cell">'+esc(x.district)+'</td><td><span class="representative">'+(x.representativePhotoUrl?'<img src="'+esc(x.representativePhotoUrl)+'" alt="Portrait of '+esc(x.representative||'representative')+'" loading="lazy">':'')+'<span>'+esc(x.representative||'Not resolved')+'</span></span></td><td>'+fmt(x.displayLines)+'</td><td class="amount">'+peso(x.displayValue)+'</td><td class="amount">'+(total?100*x.displayValue/total:0).toFixed(2)+'%</td></tr>').join('');$('ranking-status').textContent=rows.length+' districts with classified allocations. Not assigned to any current district: '+peso(c?.unresolvedPesos)+'.'}
[dist,yr,cat].forEach(x=>x.addEventListener('change',draw));$('rank-export').onclick=()=>{const rows=[...$('district-ranking').querySelectorAll('tr')].map(tr=>[...tr.cells].map(td=>td.textContent));const csv=[['Rank','Legislative district','Representative','Classified lines','Allocation','Share'],...rows].map(r=>r.map(v=>'"'+v.replaceAll('"','""')+'"').join(',')).join('\\r\\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+csv],{type:'text/csv'}));a.download='integrated-district-allocations.csv';a.click()};draw()});</script>'''
    detail = base + '''<section class="panel"><h2>Projects by district and budget year</h2><p class="muted">This is the project-level view: filter and search classified project lines, inspect source entries, and export the matching records. For annual district rankings, open <a href="integrated-district-allocations.html">Historical · District allocations</a>.</p><div class="filters"><label>District <select id="project-district"></select></label><label>Budget year <select id="project-year"></select></label><label>Project category <select id="project-category"></select></label><input id="project-search" type="search" placeholder="Search project title"><button id="project-export" type="button">Export CSV</button></div><div id="project-representative" class="representative-card muted" aria-live="polite"></div><div id="project-chart" class="chart"></div><div class="stats"><div class="stat"><strong id="project-amount">—</strong><span>Allocation in selected district and year</span></div><div class="stat"><strong id="project-count">—</strong><span>Matching project lines</span></div><div class="stat"><strong id="project-year-amount">—</strong><span>Same district · all years</span></div><div class="stat"><strong id="unassigned-project-amount">—</strong><span>Unassigned this year</span></div></div><div class="table-wrap"><table><thead><tr><th>Project</th><th>Category</th><th>Allocation</th><th>Year / stage</th><th>Source</th></tr></thead><tbody id="project-rows"></tbody></table></div><div class="pagination"><button id="project-prev">Previous</button><span id="project-page">Page 1</span><button id="project-next">Next</button></div></section>''' + detail_data_js + '''<script>
window.integratedDataPromise.then(D=>{const $=id=>document.getElementById(id),peso=n=>'₱'+Number(n||0).toLocaleString('en-PH',{maximumFractionDigits:0}),fmt=n=>Number(n||0).toLocaleString('en-PH'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const ds=$('project-district'),ys=$('project-year'),cs=$('project-category'),pageSize=50;let page=0;for(const d of D.districts){const o=document.createElement('option');o.value=d.districtId;o.textContent=d.district;ds.append(o)}for(const p of D.periods){const o=document.createElement('option');o.value=p.year+'|'+p.stage;o.textContent=p.stage==='GAA'?'FY'+p.year+' GAA':'FY'+p.year+' '+p.stage;ys.append(o)}for(const p of (D.yearAvailability||[])){const o=document.createElement('option');o.value='unavailable|'+p.year;o.textContent='FY'+p.year+' · Data unavailable';o.disabled=true;o.title=p.reason;ys.append(o)}[...ys.options].sort((a,b)=>Number((a.value.match(/\\d{4}/)||[0])[0])-Number((b.value.match(/\\d{4}/)||[0])[0])).forEach(o=>ys.append(o));for(const c of ['all',...D.categories]){const o=document.createElement('option');o.value=c;o.textContent=c==='all'?'All classified categories':c;cs.append(o)}ds.value=D.districts[0]?.districtId||'';ys.value=D.periods[D.periods.length-1]?.year+'|'+D.periods[D.periods.length-1]?.stage;function rows(){const [y,s]=ys.value.split('|'),q=$('project-search').value.trim().toLowerCase();return D.projects.filter(p=>p.districtId===ds.value&&p.year===Number(y)&&p.stage===s&&(cs.value==='all'||p.category===cs.value)&&(!q||p.name.toLowerCase().includes(q)||p.source.toLowerCase().includes(q))).sort((a,b)=>b.amountPesos-a.amountPesos)}function draw(){const [y,s]=ys.value.split('|'),filtered=rows(),pages=Math.max(1,Math.ceil(filtered.length/pageSize));page=Math.min(page,pages-1);const shown=filtered.slice(page*pageSize,(page+1)*pageSize),total=filtered.reduce((n,p)=>n+p.amountPesos,0),allYear=D.projects.filter(p=>p.districtId===ds.value).reduce((n,p)=>n+p.amountPesos,0),cov=D.coverage.find(c=>c.year===Number(y)&&c.stage===s),seat=D.districts.find(d=>d.districtId===ds.value),rep=seat?.representativesByPeriod?.[y+'|'+s];$('project-representative').innerHTML=(seat?.representativePhotosByPeriod?.[y+'|'+s]?'<img src="'+esc(seat.representativePhotosByPeriod[y+'|'+s])+'" alt="Portrait of '+esc(rep)+'" loading="lazy">':'')+'<span><strong>'+(rep?'Representative for FY'+y+' '+s+': '+esc(rep):'Representative for FY'+y+' '+s+' not resolved')+'</strong></span>'; $('project-amount').textContent=peso(total);$('project-count').textContent=fmt(filtered.length);$('project-year-amount').textContent=peso(allYear);$('unassigned-project-amount').textContent=peso(cov?.unresolvedPesos);$('project-rows').innerHTML=shown.map(p=>'<tr><td>'+esc(p.name)+'</td><td>'+esc(p.category)+'</td><td class="amount">'+peso(p.amountPesos)+'</td><td>'+p.year+' '+esc(p.stage)+'</td><td>'+esc(p.source)+'</td></tr>').join('')||'<tr><td colspan="5">No classified projects match this district, year and search.</td></tr>';$('project-page').textContent='Page '+(page+1)+' of '+pages+' · '+fmt(filtered.length)+' projects';$('project-prev').disabled=page===0;$('project-next').disabled=page>=pages-1;const series=D.periods.map(p=>{const total=D.projects.filter(r=>r.districtId===ds.value&&r.year===p.year&&r.stage===p.stage&&(cs.value==='all'||r.category===cs.value)).reduce((n,r)=>n+r.amountPesos,0);const seatForPeriod=D.districts.find(d=>d.districtId===ds.value);return {label:p.stage==='GAA'?'FY'+p.year:'FY'+p.year+' HGAB',total,photo:seatForPeriod?.representativePhotosByPeriod?.[p.year+'|'+p.stage]}}),max=Math.max(1,...series.map(x=>x.total)),W=1000,H=320,bw=70,gap=(W-100)/series.length; $('project-chart').innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="District allocations by budget year">'+series.map((x,i)=>{const h=x.total/max*180,x0=55+i*gap,y0=205-h;return '<g><title>'+esc(x.label)+' · '+peso(x.total)+'</title><rect x="'+x0+'" y="'+y0+'" width="'+bw+'" height="'+h+'" fill="#087e78" rx="5"/><text x="'+(x0+bw/2)+'" y="'+(y0-7)+'" text-anchor="middle" font-size="11">'+(x.total?'₱'+(x.total/1e9).toFixed(1)+'B':'—')+'</text><text x="'+(x0+bw/2)+'" y="230" text-anchor="middle" font-size="11">'+esc(x.label)+'</text>'+(x.photo?'<image class="chart-face" href="'+esc(x.photo)+'" x="'+(x0+bw/2-13)+'" y="242" width="26" height="26" preserveAspectRatio="xMidYMid slice"><title>Representative for '+esc(x.label)+'</title></image>':'')+'</g>'}).join('')+'</svg>'}
[ds,ys,cs].forEach(x=>x.addEventListener('change',()=>{page=0;draw()}));$('project-search').addEventListener('input',()=>{page=0;draw()});$('project-prev').onclick=()=>{page=Math.max(0,page-1);draw()};$('project-next').onclick=()=>{page++;draw()};$('project-export').onclick=()=>{const data=rows(),cols=['year','stage','district','representative','category','name','amountPesos','source'],csv=[cols,...data.map(r=>{const seat=D.districts.find(d=>d.districtId===r.districtId)||{};return [r.year,r.stage,seat.district||'',seat.representative||'',r.category,r.name,r.amountPesos,r.source]})].map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\\r\\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+csv],{type:'text/csv'}));a.download='integrated-district-projects.csv';a.click()};draw()});</script>'''
    pages = {
        'integrated-district-allocations.html': page_shell('Historical · District allocations', 'How classified DPWH project allocations changed across years, district by district.', 'integrated-district-allocations.html', allocations),
        'integrated.html': page_shell('Historical · Project records', 'Explore classified DPWH project lines by legislative district and year.', 'integrated.html', detail),
    }
    # Reapply the shared menu/readability conventions after writing the HTML.
    from uniform_report_menu import apply_page
    for name, html in pages.items():
        (STATIC / name).write_text(apply_page(html, name), encoding='utf-8')


def main():
    data = build()
    make_pages(data)
    # The barangay MPB inventory consumes the integrated project snapshot above.
    from build_mpb_barangay import main as build_mpb_barangay_page
    build_mpb_barangay_page()
    print(json.dumps({'periods': data['periods'], 'districts': len(data['districts']),
                      'classifiedAssignedProjectRows': len(data['projects']),
                      'output': str(OUT)}, indent=2))


if __name__ == '__main__':
    main()
