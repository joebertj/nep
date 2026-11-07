#!/usr/bin/env python3
"""Build district-level historical project allocation datasets and report pages.

Uses the shared DPWH project-title classifier and conservative legislative
district location rules. Allocations use current district geography;
historical Congress identities provide context without sponsorship claims.
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
            reason = 'DBM FY2015 DPWH capital-outlay account rows are available, but no classified project extract is loaded into this district series.'
        elif year == 2019:
            reason = 'DBM has a named DPWH technical GAA schedule, but it has not been loaded into this district series.'
        else:
            reason = 'No compatible, reconciled project-level extract is loaded for this report.'
        result.append({'year': year, 'available': False, 'status': status or 'not_loaded', 'reason': reason})
    return result


def slug(value: str) -> str:
    return '-'.join(re.findall(r'[a-z0-9]+', str(value or '').casefold()))


def roster_and_geography():
    raw = reps.roster_rows()
    seats_by_key = {}
    for row in raw:
        province = str(row.get('province') or '').strip()
        district = reps.district_key(row.get('district'))
        name = classifier.clean_name(str(row.get('representative') or ''))
        label = classifier.DISTRICT_LABELS.get(district)
        if not province or not name or not label or reps.norm(name) == 'special election':
            continue
        seats_by_key[(reps.norm(province), label)] = {
            'district': row.get('displayDistrict') or f'{province} · {label}', 'province': province,
            'districtLabel': label, 'representative': name,
            'memberStatus': row.get('memberStatus', 'active'),
            'lastRepresentative': row.get('lastRepresentative'),
            'representativeProfileUrl': row.get('profileUrl'),
            'districtId': 'leg:' + slug(province) + ':' + slug(label.replace(' District', '')),
        }
    seats = sorted(seats_by_key.values(), key=lambda row: (reps.norm(row['province']), row['districtLabel']))
    return seats, GeographicAttribution(ODV / 'static/data', seats)


def representative_periods(seats):
    """Verify current portraits, then attach researched Congress-specific rosters."""
    portrait_data = json.loads((STATIC / 'congress-district-roster.json').read_text(encoding='utf-8'))
    portrait_by_id = {row.get('districtId'): row for row in portrait_data.get('districts', [])}
    portrait_id_aliases = {
        'leg:antipolo:2nd': 'leg:antipolo-city:2nd',
        'leg:bi-an:lone': 'leg:binan-city:lone',
        'leg:las-pi-as:lone': 'leg:las-pinas-city:lone',
        'leg:mandaue:lone': 'leg:mandaue-city:lone',
        'leg:para-aque:1st': 'leg:paranaque-city:1st',
        'leg:para-aque:2nd': 'leg:paranaque-city:2nd',
        'leg:taguig-pateros:2nd': 'leg:taguig-city:2nd',
        'leg:taguig-pateros:1st': 'leg:taguig-city-pateros:lone',
    }
    photo_overrides = json.loads((STATIC / 'congress-photo-overrides.json').read_text())
    sourced_portraits = {row['districtId']: row for row in photo_overrides}
    sourced_profile_pages = {row['districtId']: row['sourceUrl'] for row in photo_overrides}

    verification_path = STATIC / 'congress-portrait-verification.json'
    verification = json.loads(verification_path.read_text()).get('images', {}) if verification_path.exists() else {}
    audit = {}
    for seat in seats:
        current_name = seat.get('representative') or ''
        city_prefix, district_number = seat['districtId'].rsplit(':', 1)
        city_id = city_prefix + '-city:' + district_number
        portrait = (portrait_by_id.get(seat['districtId'])
                    or portrait_by_id.get(portrait_id_aliases.get(seat['districtId']))
                    or portrait_by_id.get(city_id) or {})
        if portrait.get('status') == 'resolved' and portrait.get('photoUrl'):
            photo = portrait['photoUrl']
            photo_source = portrait.get('portraitSourceUrl') or portrait.get('profileUrl') or 'https://www.congress.gov.ph/house-members'
            photo_congress = 20  # Current roster portrait feed is explicitly the 20th Congress.
        else:
            override = sourced_portraits.get(seat['districtId'], {})
            photo = override.get('photoUrl')
            photo_source = override.get('sourceUrl') or sourced_profile_pages.get(seat['districtId'])
            photo_congress = override.get('photoCongress')
        source_name = portrait.get('sourceName') or portrait.get('name') or current_name
        overlap = set(reps.norm(source_name).split()) & set(reps.norm(current_name).split())
        identity_status = ('name_tokens_and_district_match' if len(overlap) >= 2 else 'same_district_profile_alias')
        if photo and not overlap and seat['districtId'] not in sourced_portraits:
            photo = None
            identity_status = 'unresolved_name_mismatch'
        transport = verification.get(photo, {})
        seat['representativePhotoIdentityStatus'] = identity_status
        seat['representativePhotoSourceName'] = source_name
        seat['representativeProfileUrl'] = seat.get('representativeProfileUrl') or portrait.get('profileUrl') or 'https://www.congress.gov.ph/house-members'
        seat['representativePhotoOriginalUrl'] = photo
        seat['representativePhotoCongress'] = photo_congress
        seat['representativePhotoUrl'] = transport.get('localUrl') if transport.get('status') == 'verified_image' else photo
        seat['representativePhotoVerifiedAtUtc'] = transport.get('checkedAtUtc')
        seat['representativePhotoSourceUrl'] = photo_source
        seat['representativePhotoStatus'] = transport.get('status', 'unverified_url') if photo else 'no direct portrait image URL located'
        if seat.get('memberStatus') != 'active':
            seat['representativePhotoUrl'] = None
            seat['representativePhotoStatus'] = 'no active member listed; former member portrait withheld'
            seat['representativePhotoSourceUrl'] = seat['representativeProfileUrl']
            seat['representativePhotoIdentityStatus'] = 'inactive_no_current_member'
        seat['representativePhotoName'] = current_name if seat['representativePhotoUrl'] else None
        seat['representativesByPeriod'] = {}
        seat['representativeStatusByPeriod'] = {}
        seat['representativePhotoCongressByPeriod'] = {}
        seat['representativeCongressByPeriod'] = {}
        seat['representativePhotosByPeriod'] = {}
        seat['representativePhotoSourcesByPeriod'] = {}

    from historical_congress_context import attach
    return attach(seats)


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
            # Full roster/photo histories live once on the district record.
            'year': year, 'stage': stage, **{k: v for k, v in seat.items() if not k.endswith('ByPeriod')},
            'representative': seat['representativesByPeriod'].get(f'{year}|{stage}'),
            'representativePhotoUrl': seat['representativePhotosByPeriod'].get(f'{year}|{stage}'),
            'representativePhotoSourceUrl': (seat['representativePhotoSourcesByPeriod'].get(f'{year}|{stage}') or {}).get('sourceUrl'),
            'representativePhotoName': seat['representativePortraitSubjectsByPeriod'].get(f'{year}|{stage}'),
            'rosterCongress': seat['representativeCongressByPeriod'].get(f'{year}|{stage}'),
            'photoCongress': (seat['representativePhotoSourcesByPeriod'].get(f'{year}|{stage}') or {}).get('photoCongress'),
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
            'classifier': 'Shared title classifier for multi-purpose buildings, flood control, bridges, and roads.',
            'attribution': 'Current legislative-district roster and strict qualified-location rules. Unique assignments only; shared and unresolved titles remain excluded from district totals.',
            'timeLimit': 'Project locations are assigned to current legislative district boundaries. Historical names and portraits follow the corresponding Congress roster where the seat can be reconciled with the current district. Election-year fiscal snapshots use the incoming Congress as cohort context; this does not identify who enacted or sponsored a budget. Portrait creation Congress is recorded separately from the member roster Congress.',
            'representativeCoverage': representative_audit,
            'representativeRosterCheckedDate': '2026-11-04',
            'representativeSource': 'House of Representatives, House Members · 20th Congress (https://www.congress.gov.ph/house-members), with current seat corrections for Antipolo 2nd, Cavite 4th, and the Taguig City/Taguig City-Pateros seats. Historical identities use the sourced 16th–19th Congress district rosters and attributed Commons portraits in congress-historical-rosters.json. Portraits may come from another term only when the individual identity matches; photo Congress and roster Congress remain separate.',
            'sources': 'FY2015 DBM DPWH account-level GAA CSV with capital-outlay PAP candidates; FY2016–FY2018 title-classified DPWH current-new-appropriation rows from the BetterGov GAA Explorer baseline; FY2019 UACS-coded named project rows from the DBM Technical GAA DPWH schedule; FY2020–FY2025 integrated annual GAA data; FY2026 DPWH Details Enrolled Copy; FY2027 House GAB 3rd-reading DPWH schedule. FY2015–FY2019 use separate historical source layers; FY2027 is a proposal, not enacted GAA.',
        },
    }
    data['buildVersion'] = hashlib.sha256(json.dumps(data['annual'], ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]
    summary_data = {key: value for key, value in data.items() if key != 'projects'}
    project_data = {key: value for key, value in data.items() if key != 'annual'}
    OUT.write_text(json.dumps(summary_data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    PROJECT_OUT.write_text(json.dumps(project_data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return data


HISTORY_HERO_CSS = '#all-years-total{font-size:clamp(26px,3vw,42px);color:#0038A8;font-variant-numeric:tabular-nums}.portrait-unavailable{display:inline-flex;align-items:center;justify-content:center;min-width:36px;min-height:36px;font-size:10px;background:#eef2f8;border-radius:6px;padding:4px}.history-hero{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(300px,.9fr);gap:24px;align-items:center;margin:18px 0 24px;padding:clamp(22px,3vw,34px);border-left:7px solid #FCD116;border-radius:16px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff;box-shadow:0 12px 30px #00246A22}.history-hero h2{margin:0 0 8px;color:#fff!important;font-size:clamp(24px,3vw,36px)!important;line-height:1.1!important}.history-hero p{margin:0;color:#f3f6ff}.history-hero-kicker{display:block;margin-bottom:8px;color:#FCD116;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.history-hero-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.history-hero-stats>div{display:flex;min-height:100px;flex-direction:column;justify-content:center;gap:7px;padding:14px;border:1px solid #ffffff35;border-radius:11px;background:#ffffff12}.history-hero-stats strong{color:#FCD116;font-size:clamp(24px,3vw,36px);line-height:1;font-variant-numeric:tabular-nums}.history-hero-stats span{color:#f3f6ff;font-size:12px;line-height:1.3}@media(max-width:760px){.history-hero{grid-template-columns:1fr}.history-hero-stats>div{min-height:75px}}'

def page_shell(title, teaser, page, content, data_url='integrated-district-data.json'):
    from uniform_report_menu import NAV, CSS
    readability_js = hashlib.sha256((STATIC/'report-table-readability.js').read_bytes()).hexdigest()[:12]
    readability_css = hashlib.sha256((STATIC/'report-table-readability.css').read_bytes()).hexdigest()[:12]
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · BetterGov</title><meta name="description" content="District allocations for classified DPWH projects across enacted GAA years and HGAB 3rd reading."><link rel="stylesheet" href="research-theme.css?v=20261029"><link rel="stylesheet" href="report-table-readability.css?v={readability_css}"><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f3f6f5;color:#18303b;font:15px/1.5 system-ui,sans-serif}}header.uniform-report-header{{background:#102f3e;color:white;padding:24px clamp(16px,2vw,32px)}}main{{width:100%;padding:24px clamp(16px,2vw,32px) 60px}}.intro,.panel,.stat{{background:#fff;border:1px solid #c6dbd6;border-radius:14px;padding:18px;margin:0 0 16px}}.intro{{border-left:5px solid #087e78}}.filters{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}input,select,button{{font:inherit;padding:9px 11px;border:1px solid #b6c9c4;border-radius:8px;background:#fff;color:#18303b}}input{{flex:1;min-width:200px}}button{{cursor:pointer}}button:disabled{{opacity:.45;cursor:default}}.stats{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}}.stat{{margin:0;padding:14px}}.stat strong{{display:block;font-size:clamp(20px,2vw,28px);color:#087e78}}.stat span,.muted{{color:#526773;font-size:13px}}.chart{{width:100%;overflow:auto}}svg{{display:block;width:100%;height:auto;min-width:650px}}.table-wrap{{width:100%;overflow-x:auto}}table{{border-collapse:collapse;width:100%;table-layout:fixed}}th,td{{padding:9px 10px;text-align:left;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere}}th{{background:#eaf2f0}}td.amount{{text-align:right;font-variant-numeric:tabular-nums}}.district-cell{{font-weight:700}}.representative{{display:flex;align-items:center;gap:8px}}.representative img{{width:36px;height:36px;border-radius:50%;object-fit:cover;border:2px solid #FCD116}}.chart-face{{width:26px;height:26px;object-fit:cover;border-radius:50%;stroke:#FCD116}}.representative-card{{display:flex;align-items:center;gap:10px;margin:10px 0 14px;padding:10px 12px;border:1px solid #E0E0E0;border-radius:10px;background:#fff}}.representative-card img{{width:48px;height:48px;object-fit:cover;border-radius:50%;border:3px solid #FCD116}}.badge{{display:inline-block;padding:2px 7px;border-radius:99px;background:#edf4f2;color:#28545a;font-size:11px}}.pagination{{display:flex;justify-content:space-between;align-items:center;margin:12px 0}}.caution{{padding:12px;background:#fff4dd;border-left:4px solid #b65b09}}@media(max-width:760px){{main{{padding:16px 12px}}.stats{{grid-template-columns:repeat(2,minmax(0,1fr))}}th,td{{font-size:12px;padding:6px}}}}
</style></head><body class="bettergov-research"><header class="uniform-report-header"><div class="report-header-heading"><a class="report-header-brand" href="https://bettergov.ph/" aria-label="BetterGov home"><img src="https://assets.bettergov.ph/logos/webp/horizontal-black.webp" alt="BetterGov"></a><div class="eyebrow">BetterGov · Budget research</div><h1>{title}</h1><p>{teaser}</p></div>{NAV}</header><main>{content}</main><script src="report-table-readability.js?v={readability_js}"></script></body></html>'''
    return html.replace('</style></head>', HISTORY_HERO_CSS + '</style></head>', 1)


def make_pages(data):
    def data_loader(url):
        version = hashlib.sha256((STATIC / url).read_bytes()).hexdigest()[:12]
        return """<script>window.integratedDataPromise=fetch('__URL__?v=__VERSION__').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).catch(e=>{document.querySelector('main').insertAdjacentHTML('afterbegin','<p class="caution">Integrated district data could not be loaded. Serve this page through the local app or a web server.</p>');throw e});</script>""".replace('__URL__', url).replace('__VERSION__', version)
    data_js = data_loader('integrated-district-data.json')
    base = '''<aside id="report-evidence-notice" class="intro gaa-year-coverage report-disclaimer" role="note"><strong>Disclaimer.</strong> This page compares classified DPWH budget allocations across project categories and years by legislative district. Totals include uniquely assigned project rows; shared or unresolved locations are excluded. Historical allocations use today’s district boundaries. Annual names and portraits use the corresponding Congress roster where the historic seat can be reconciled. Election-year snapshots use the incoming Congress as cohort context, and do not establish budget enactment or sponsorship. Allocations are not payments.<p><strong>Older GAA coverage.</strong> FY2015 project-title candidates come from the DBM DPWH account-level GAA CSV and include capital-outlay PAP records; see <a href="gaa-2015-dpwh-technical.html">the FY2015 parsed lines</a>. FY2016–2018 project-family rows come from the GAA Explorer DPWH baseline; FY2019 project-title candidates come from the DBM technical DPWH GAA schedule and are classified from specific UACS lines. <a href="gaa-2019-dpwh-technical.html">Search all FY2019 DPWH technical GAA lines</a>. FY2000–2008 has partial or aggregate-only coverage; FY2001, FY2004 and FY2006 had no new enacted GAA; FY2009–2013 lacks DEO-level detail and is not reconciled to this district series; FY2014 has no reconciled named-project extract. Unavailable years are disabled and excluded from totals, averages and charts.</p></aside>'''
    history_hero = ('<section class="history-hero" aria-label="Historical data coverage"><div><span class="history-hero-kicker">DPWH · historical allocations</span><h2>Trace project allocations across years and districts</h2><p>Unavailable and unreconciled years stay out of comparisons. FY2027 is the HGAB 3rd-reading proposal, not enacted GAA.</p></div><div class="history-hero-stats"><div><strong>'+str(len(data['periods']))+'</strong><span>available budget year and stage snapshots</span></div><div><strong>'+str(len(data['categories']))+'</strong><span>shared project categories</span></div><div><strong>'+str(len(data['districts']))+'</strong><span>district records in this dataset</span></div></div></section>')
    base += history_hero
    allocations = base + '''<section class="panel" id="all-years-summary"><strong id="all-years-total">—</strong><p id="all-years-caption"></p><a href="integrated-district-totals.html">Open total ranking · all available years ↗</a></section><section class="panel"><h2>Compare annual district allocations</h2><p class="muted">This view compares each district’s yearly totals and ranks districts for the selected period. Annual names and portraits follow the corresponding Congress roster. A portrait from another term can illustrate the same person; its source term is recorded separately. Allocation geography uses current district boundaries. Changed or unresolved historic seats are flagged; Congress context does not imply sponsorship. Project rows below follow the selected district, year, category and title filter.</p><div class="filters"><label>District <select id="trend-district"></select></label><label>Year <select id="rank-year"></select></label><label>Project type <select id="rank-category"></select></label><label>Project title <input id="project-filter" type="search" placeholder="Filter project titles"></label><button id="rank-export" type="button">Export CSV</button></div><div id="allocation-chart" class="chart" aria-live="polite"></div><div class="stats"><div class="stat"><strong id="period-total">—</strong><span>Selected district · selected period</span></div><div class="stat"><strong id="period-lines">—</strong><span>Classified project records</span></div><div class="stat"><strong id="unresolved-total">—</strong><span id="unresolved-label">Unassigned allocation · selected period</span></div><div class="stat"><strong id="period-coverage">—</strong><span id="period-coverage-label">District-assigned share of classified amount</span></div></div></section><section class="panel" id="project-records"><h2>Project records · selected district and year</h2><p class="muted" id="project-results-status">Loading matching project rows…</p><div class="table-wrap"><table><thead><tr><th>Project</th><th>Legislative district</th><th>Category</th><th>Allocation</th><th>Year / stage</th><th>Source</th></tr></thead><tbody id="matching-project-rows"><tr><td colspan="6">Loading project rows…</td></tr></tbody></table></div><div class="pagination"><button id="matching-project-prev" type="button" disabled>Previous</button><span id="matching-project-page">Page 1</span><button id="matching-project-next" type="button" disabled>Next</button></div></section><section class="panel"><h2 id="ranking-title">District ranking · all available years</h2><div class="filters"><label>Rank by <select id="rank-metric"><option value="allocation">Allocation</option><option value="lines">Project lines</option></select></label></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Legislative district</th><th>Current district representative · context only</th><th>Classified lines</th><th>Allocation</th><th>Share of ranked total</th></tr></thead><tbody id="district-ranking"></tbody></table></div><p class="muted" id="ranking-status"></p><div class="pagination"><button id="ranking-prev" type="button" disabled>Previous</button><span id="ranking-page">Page 1</span><button id="ranking-next" type="button">Next</button></div></section><section class="panel"><h2 id="lowest-title">Lowest-allocation districts · all available years</h2><p class="muted">The ten smallest totals for the selected period and category, including districts with zero classified allocations.</p><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Legislative district</th><th>Current district representative · context only</th><th>Classified lines</th><th>Allocation</th><th>Share of assigned total</th></tr></thead><tbody id="lowest-ranking"></tbody></table></div><p class="muted" id="lowest-status"></p></section>''' + data_js + '<script src="integrated-district-view.js?v=' + hashlib.sha256((ROOT / 'report_assets/integrated_district_view.js').read_bytes()).hexdigest()[:12] + '"></script>'
    (STATIC / 'integrated-district-view.js').write_bytes((ROOT / 'report_assets/integrated_district_view.js').read_bytes())
    pages = {
        'integrated-district-allocations.html': page_shell('Historical · District allocations', 'How classified DPWH project allocations changed across years, district by district.', 'integrated-district-allocations.html', allocations),
        'integrated.html': page_shell('Historical · Project records', 'Project records are now part of Historical · District allocations.', 'integrated.html', '<section class="panel"><h2>Project records moved</h2><p>District allocations and project records are now combined on one page.</p><p><a href="integrated-district-allocations.html#project-records">Open district allocations and project records ↗</a></p></section><script>location.replace("integrated-district-allocations.html#project-records")</script>'),
    }
    # Reapply the shared menu/readability conventions after writing the HTML.
    from uniform_report_menu import apply_page
    for name, html in pages.items():
        (STATIC / name).write_text(apply_page(html, name), encoding='utf-8')
    totals_page = STATIC / 'integrated-district-totals.html'
    if totals_page.exists():
        text = totals_page.read_text()
        for filename in ('integrated-district-data.json', 'integrated-project-data.json'):
            version = hashlib.sha256((STATIC/filename).read_bytes()).hexdigest()[:12]
            text = re.sub(r"fetch\('"+re.escape(filename)+r"(?:\?v=[^']*)?'\)",
                          "fetch('"+filename+"?v="+version+"')",text)
        totals_page.write_text(text)


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
