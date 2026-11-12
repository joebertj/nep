#!/usr/bin/env python3
"""Build MPB comparisons with public school/health/evacuation facilities."""
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static' / 'nep-preview'
OUT = ROOT / 'analysis_output'
PAGE = 'education-health.html'
DATA = 'education-health-data.json'
LINES = ROOT / 'data_sources' / 'bettergov-mpb-years-lines.csv'
PSGC = ROOT / 'data_sources' / 'bettergov-psgc-locations.jsonl'
FACILITIES = OUT / 'connectivity-public-services-data.json'
FACILITIES_RAW = ROOT / 'data_sources' / 'connectivity_online' / 'osm-public-services-raw.json'


def normalize_place(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().casefold()
    value = re.sub(r'\([^)]*\)', ' ', value)
    value = re.sub(r'\b(city of|municipality of|municipality|city|capital)\b', ' ', value)
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def explicitly_public(tags):
    ownership = (tags.get('ownership') or '').casefold()
    operator_type = (tags.get('operator:type') or '').casefold()
    public_types = {
        'public', 'government', 'public/government', 'municipal',
        'local_government', 'government_local', 'barangay_government',
        'barangay_governement', 'autonomous_regional_government',
        'state', 'national',
    }
    operator = tags.get('operator') or ''
    public_operator = re.search(
        r'\b(?:deped|department of education|department of health|'
        r'(?:city|municipal|provincial|barangay|local) government|'
        r'government of|local government unit|lgu)\b',
        operator,
        re.I,
    )
    return ownership in {'public', 'government'} or operator_type in public_types or bool(public_operator)


def join_facility_candidates(places, geography_rows):
    mapped = json.loads(FACILITIES.read_text())['rows']
    raw = json.loads(FACILITIES_RAW.read_text())['elements']
    tags_by_id = {f"osm:{x['type']}:{x['id']}": x.get('tags', {}) for x in raw}

    place_admin = {}
    municipality_province = {}
    municipality_province_family = {}
    for place in places.values():
        if place.get('level') not in ('municipality', 'city', 'sub_municipality'):
            continue
        ancestors = []
        current = place
        while current:
            ancestors.append(current)
            current = places.get(current.get('parent_code'))
        province = next((x for x in ancestors if x.get('level') == 'province'), {})
        region = next((x for x in ancestors if x.get('level') == 'region'), {})
        key = (normalize_place(place.get('name')), normalize_place(region.get('name')))
        place_admin.setdefault(key, []).append((place, province, region))
        province_key = (normalize_place(place.get('name')), normalize_place(province.get('name')))
        if province_key[1]:
            municipality_province.setdefault(province_key, []).append((place, province, region))
            for family in ('negros','mindoro','maguindanao','agusan','misamis','ilocos','camarines'):
                if family in province_key[1].split():
                    municipality_province_family.setdefault((province_key[0], family), []).append((place, province, region))

    categories = {
        'schools': lambda row, tags: row['type'] == 'School / education facility' and explicitly_public(tags),
        'health': lambda row, tags: row['type'] == 'Health / medical facility' and explicitly_public(tags),
        'evacuation': lambda row, tags: (
            tags.get('emergency', '').casefold() in {'evacuation_center', 'evacuation_centre'}
            or tags.get('disaster_help_point:shelter', '').casefold() == 'yes'
            or (
                tags.get('social_facility', '').casefold() == 'shelter'
                and 'displaced' in (tags.get('social_facility:for', '').casefold().split(';'))
            )
        ),
    }
    counters = {key: defaultdict(int) for key in categories}
    inventories = {}
    unmatched = {key: 0 for key in categories}
    join_audit = []

    for category, qualifies in categories.items():
        candidates = [
            row for row in mapped
            if qualifies(row, tags_by_id.get(row['id'], {}))
        ]
        joined = 0
        recovered_by_province = 0
        recovered_by_family = 0
        joined_municipalities = set()
        for row in candidates:
            join_method = 'municipality-region'
            key = (normalize_place(row.get('municipality')), normalize_place(row.get('region')))
            matches = place_admin.get(key, [])
            province_key = normalize_place(row.get('province'))
            if province_key:
                province_matches = [
                    match for match in matches
                    if normalize_place(match[1].get('name')) == province_key
                ]
                if len(province_matches) == 1:
                    matches = province_matches
            if len(matches) != 1 and province_key:
                fallback = municipality_province.get((normalize_place(row.get('municipality')), province_key), [])
                if len(fallback) == 1:
                    matches = fallback
                    recovered_by_province += 1
                    join_method = 'unique-municipality-province'
            if len(matches) != 1 and province_key:
                family_matches = municipality_province_family.get((normalize_place(row.get('municipality')), province_key), [])
                if len(family_matches) == 1:
                    matches = family_matches
                    recovered_by_family += 1
                    join_method = 'unique-municipality-province-family'
            if len(matches) != 1:
                unmatched[category] += 1
                join_audit.append({'id':row['id'],'category':category,'municipalityPsgc':None,'method':'unresolved'})
                continue
            place, province, region = matches[0]
            joined += 1
            join_audit.append({'id':row['id'],'category':category,'municipalityPsgc':place['code'],'method':join_method})
            joined_municipalities.add(place['code'])
            current = place
            while current:
                if current.get('level') in {'municipality', 'city', 'province', 'region'}:
                    counters[category][current['code']] += 1
                current = places.get(current.get('parent_code'))

        inventories[category] = {
            'source': 'OpenStreetMap public-services country extract, downloaded 2026-11-04',
            'sourceUrl': 'https://www.openstreetmap.org/copyright',
            'candidateRows': len(candidates),
            'joinedRows': joined,
            'unmatchedRows': unmatched[category],
            'matchedMunicipalities': len(joined_municipalities),
            'recoveredByUniqueMunicipalityProvince': recovered_by_province,
            'recoveredByUniqueMunicipalityProvinceFamily': recovered_by_family,
            'joinBasis': 'Mapped source point or feature center matched to exactly one PSGC municipality/city using municipality name and region, or a unique municipality-and-province match when region labels differ, or unique municipality within a published province family (e.g. Negros, Mindoro); ambiguous matches remain excluded; counts roll up to province and region.',
            'status': 'Partial OSM candidates only. Counts require explicit public/government tags for schools and health facilities; evacuation candidates require explicit shelter or evacuation tags. This is not a complete or official facility inventory.',
        }

    official_path = OUT / 'education-health-official-sites.json'
    official = json.loads(official_path.read_text())
    records = official['records']
    qc_code = '1381300000'
    previous_qc = counters['evacuation'].get(qc_code, 0)
    delta = len(records) - previous_qc
    current = places[qc_code]
    while current:
        if current['level'] in {'municipality', 'city', 'province', 'region'}:
            counters['evacuation'][current['code']] += delta
        current = places.get(current.get('parent_code'))
    qc_barangays = {p['code'] for p in places.values() if p.get('parent_code') == qc_code and p['level'] == 'barangay'}
    official_barangays = defaultdict(int)
    for record in records:
        if record.get('barangayPsgc'):
            official_barangays[record['barangayPsgc']] += 1
    inv = inventories['evacuation']
    inv['joinedRows'] += delta
    if previous_qc == 0:
        inv['matchedMunicipalities'] += 1
    inv['candidateRows'] += delta
    inv['source'] = 'OpenStreetMap outside Quezon City; Quezon City government evacuation directory within the city'
    inv['status'] = 'Quezon City uses 493 distinct designated sites from the official city directory, replacing its OSM candidates. Elsewhere counts remain partial OSM candidates. Temporary sites are included; these counts do not measure dedicated evacuation buildings.'
    inv['officialRefinement'] = {**official['audit'], 'replacedOsmCandidates': previous_qc, 'netChange': delta, 'sourceUrl': records[0]['sourceUrl']}
    (STATIC / 'education-health-official-sites.json').write_text(official_path.read_text())

    philhealth_path = OUT / 'education-health-philhealth.json'
    philhealth = json.loads(philhealth_path.read_text())
    ph_counts = {'hospitals': defaultdict(int), 'yakap': defaultdict(int)}
    ph_beds = defaultdict(int)
    for category in ('hospitals', 'yakap'):
        unique = {}
        for record in philhealth[category]['records']:
            if record['ownership'] != 'government' or not record.get('municipalityCode'):
                continue
            key = (normalize_place(record['name']), record['municipalityCode'], normalize_place(record.get('street'))) 
            unique.setdefault(key, record)
        for record in unique.values():
            current = places[record['municipalityCode']]
            while current:
                if current['level'] in {'municipality', 'city', 'province', 'region'}:
                    ph_counts[category][current['code']] += 1
                    if category == 'hospitals' and record.get('beds') is not None:
                        ph_beds[current['code']] += record['beds']
                current = places.get(current.get('parent_code'))

    for row in geography_rows:
        counts = {category: counters[category].get(row['code'], 0) for category in categories}
        if row['level'] in {'municipality', 'city', 'province', 'region'}:
            row['facilityCounts'] = counts
            row['philhealthHealthCounts'] = {'hospitals': ph_counts['hospitals'].get(row['code'], 0), 'yakap': ph_counts['yakap'].get(row['code'], 0)}
            row['philhealthGovernmentHospitalBeds'] = ph_beds.get(row['code'], 0)
        else:
            row['facilityCounts'] = {category: None for category in categories}
            row['philhealthHealthCounts'] = {'hospitals': None, 'yakap': None}
            row['philhealthGovernmentHospitalBeds'] = None
            if row['code'] in official_barangays:
                row['facilityCounts']['evacuation'] = official_barangays[row['code']]
        cur=places.get(row['code'],{}); ancestors=[]
        while cur:
            ancestors.append(cur);cur=places.get(cur.get('parent_code'))
        row['regionCode']=next((x['code'] for x in ancestors if x.get('level')=='region'),'')
        row['provinceCode']=next((x['code'] for x in ancestors if x.get('level')=='province'),'')
        row['municipalityCode']=next((x['code'] for x in ancestors if x.get('level') in {'municipality','city','sub_municipality'}),'')
        row['facilitySource'] = {'evacuation': 'Quezon City government directory' if row['code'] == qc_code or row['code'] in official_barangays else 'OSM candidates or regional mixed-source total'}
    deped_path = OUT / 'education-health-deped-schools.json'
    deped = json.loads(deped_path.read_text())
    deped_counts = defaultdict(int)
    deped_enrollment = defaultdict(int)
    deped_enrollment_schools = defaultdict(int)
    for record in deped['records']:
        for code in (record.get('regionCode'), record.get('provinceCode'), record.get('municipalityCode'), record.get('barangayCode')):
            if code:
                deped_counts[code] += 1
                if record.get('enrollment') is not None:
                    deped_enrollment[code] += record['enrollment']
                    deped_enrollment_schools[code] += 1
    for row in geography_rows:
        row['depedPublicSchoolCount'] = deped_counts.get(row['code'], 0)
        row['depedPublicEnrollment'] = deped_enrollment.get(row['code'], 0)
        row['depedEnrollmentSchoolCount'] = deped_enrollment_schools.get(row['code'], 0)
    audit_payload = json.dumps({'method':'Unique matches only. Province-family matches use broad published labels such as Negros; unresolved records are excluded. Quezon City official evacuation records replace OSM counts within the city.', 'osmJoins':join_audit, 'officialLedger':'education-health-official-sites.json'},ensure_ascii=False)
    for root in (OUT,STATIC):
        (root/'education-health-facility-crosswalk.json').write_text(audit_payload+'\n')
    inventories['depedSchools'] = {
        'source': deped['source'], 'sourceUrl': deped['sourceUrl'], 'sourceRows': deped['publicSchoolRows'],
        'reportedEnrollmentRows': deped['reportedEnrollmentRows'], 'publicEnrollmentTotal': deped['publicEnrollmentTotal'],
        'municipalityMatched': deped['municipalityMatched'], 'barangayMatched': deped['barangayMatched'],
        'municipalityUnmatched': deped['unmatched'].get('municipality', 0),
        'barangayUnmatched': deped['unmatched'].get('barangay', 0), 'joinMethods': deped['joinMethods'],
        'status': 'DepEd SY 2025-26 public-school IDs and reported enrollment, distributed by NASH Reviewer. Counts include uniquely joined school IDs only; unmatched IDs are excluded, so counts are a joined-record lower bound.'
    }
    inventories['philhealthHospitals'] = philhealth['hospitals']
    inventories['philhealthYakap'] = philhealth['yakap']
    return inventories


def build_data():
    places = {r['code']: r for r in (json.loads(x) for x in PSGC.read_text().splitlines() if x.strip())}
    children = defaultdict(list)
    for r in places.values():
        if r.get('parent_code'):
            children[r['parent_code']].append(r['code'])
    records = []
    with LINES.open(encoding='utf-8-sig', newline='') as f:
        for row in csv.DictReader(f):
            if row.get('fiscal_year') != '2027' or int(float(row.get('house_bill_php') or 0)) <= 0:
                continue
            code = (row.get('place_psgc') or '').strip()
            place = places.get(code)
            if not place:
                continue
            # A title-only screen: no PAP, scope or description fields enter this classification.
            title = (row.get('title_as_published') or row.get('title') or '').casefold()
            labels = []
            for label, words in (
                ('school', r'\b(?:school|classroom|education|educational|college|university)\b'),
                ('health', r'\b(?:health|hospital|clinic|medical|infirmary|birthing|rhu|health center|health centre)\b'),
                ('evacuation', r'\b(?:evacuation|evac)\b'),
            ):
                if re.search(words, title):
                    labels.append(label)
            records.append({'code': code, 'title': title, 'labels': labels, 'amount': int(float(row['house_bill_php'])), 'id': row.get('line_id','')})

    # Group direct row counts and distinct barangays across PSGC hierarchy.
    levels = {'barangay': 'barangay', 'municipality': 'municipality', 'city': 'city', 'sub_municipality': 'municipality'}
    grouped = defaultdict(lambda: {'rows': 0, 'amount': 0, 'barangays': set(), 'heuristicAny': set(), 'heuristics': defaultdict(lambda: {'rows': 0, 'amount': 0, 'barangays': set()})})
    for rec in records:
        code = rec['code']; current = places.get(code, {}); ancestors = []
        while current:
            if current.get('level') in levels:
                ancestors.append(current)
            current = places.get(current.get('parent_code'))
        # Region and province are included as distinct reporting levels.
        current = places.get(code, {})
        while current:
            if current.get('level') in ('province', 'region'):
                ancestors.append(current)
            current = places.get(current.get('parent_code'))
        barangay = code if places.get(code, {}).get('level') == 'barangay' else ''
        for p in ancestors:
            key = (p.get('level'), p['code'])
            g = grouped[key]; g['rows'] += 1; g['amount'] += rec['amount']
            if barangay: g['barangays'].add(barangay)
            for label in rec['labels']:
                h = g['heuristics'][label]; h['rows'] += 1; h['amount'] += rec['amount']
                if barangay: h['barangays'].add(barangay)
            if rec['labels']:
                g['heuristicAny'].add(rec['id'])
    official_barangays = defaultdict(int)
    for p in places.values():
        if p.get('level') != 'barangay':
            continue
        cur = p
        while cur:
            if cur.get('level') in ('region', 'province', 'city', 'municipality', 'sub_municipality'):
                official_barangays[cur['code']] += 1
            cur = places.get(cur.get('parent_code'))
    rows = []
    for (level, code), g in grouped.items():
        p = places[code]
        parent = places.get(p.get('parent_code'), {})
        region = p.get('name') if level == 'region' else ''
        province = p.get('name') if level == 'province' else ''
        cur = p
        while cur:
            if cur.get('level') == 'region': region = cur.get('name','')
            if cur.get('level') == 'province': province = cur.get('name','')
            cur = places.get(cur.get('parent_code'))
        rows.append({'level': level, 'code': code, 'name': p.get('name',''), 'region': region, 'province': province,
                     'mpbRows': g['rows'], 'mpbPesos': g['amount'], 'barangaysWithMPB': len(g['barangays']), 'officialBarangays': official_barangays.get(code, 0), 'heuristicAny': len(g['heuristicAny']),
                     'heuristics': {k: {'rows': v['rows'], 'pesos': v['amount'], 'barangays': len(v['barangays'])} for k,v in g['heuristics'].items()}})
    order = {'region': 0, 'province': 1, 'city': 2, 'municipality': 3, 'barangay': 4, 'sub_municipality': 5}
    rows.sort(key=lambda r: (order.get(r['level'],9), r['region'], r['province'], r['name']))
    facility_inventories = join_facility_candidates(places, rows)
    return {'fiscalYear': 2027, 'stage': 'House Bill', 'mpbProjectRows': len(records), 'geographyRows': rows,
            'facilityInventories': facility_inventories,
            'facilitySourceNote': 'Public schools now include a separate DepEd SY 2025-26 enrollment-panel count, joined to PSGC at municipality and barangay where uniquely resolved; unresolved IDs are excluded. OSM school and health counts remain a separate partial map cross-check. Evacuation counts use the Quezon City government directory there and OSM elsewhere.',
            'method': 'MPB row counts use FY2027 House Bill line records assigned to PSGC places. MPB density is shown as project rows per 100 official barangays where coverage exists. Facility candidate counts per 100 barangays use municipality/city PSGC joins and official barangay denominators; they are incomplete map counts, not confirmed inventory coverage. Heuristic labels inspect title text only; they are not confirmed building uses.'}


def build_page(data):
    (OUT / DATA).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    (STATIC / DATA).parent.mkdir(parents=True, exist_ok=True)
    (STATIC / DATA).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MPB vs Schools, Health and Evacuation Facilities</title><style>
:root{--ink:#142b3b;--muted:#566b79;--line:#d8e1e7;--blue:#0038a8;--gold:#f5c542;--bg:#f5f8fa}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}main{width:100%;max-width:none;margin:0;padding:26px clamp(16px,2vw,32px) 56px}.eyebrow{font-weight:750;letter-spacing:.1em;color:var(--blue);font-size:.78rem}h1{font-size:clamp(2rem,4vw,3.3rem);line-height:1.08;margin:.35rem 0 1rem}h2{margin:.1rem 0 .6rem;font-size:1.5rem}h3{margin:0 0 .5rem}.lede{max-width:800px;color:var(--muted)}.section{margin:24px 0;padding:24px;background:white;border:1px solid var(--line);border-radius:15px;box-shadow:0 3px 12px #17334a0a}.kicker{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--blue);font-weight:750}.notice{border-left:4px solid var(--gold);padding:12px 15px;background:#fff9e7;border-radius:5px;color:#394b57}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}.controls select,.controls input{font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:white}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f4f7f9;position:sticky;top:0}.num{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:9px}.small{font-size:.88rem;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.status{padding:14px;background:#f6f8fa;border:1px solid var(--line);border-radius:10px}.status strong{display:block;margin-bottom:4px}.pill{display:inline-block;border-radius:20px;padding:3px 9px;background:#eaf0ff;color:#173c82;font-size:.78rem;font-weight:700}.footer{font-size:.86rem;color:var(--muted);margin-top:20px}.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:14px;margin-top:16px}.chart-panel{min-width:0;padding:16px;border:1px solid var(--line);border-radius:12px;background:#fbfcfd}.chart-panel h3{font-size:1.05rem}.chart-note{margin:0 0 12px;color:var(--muted);font-size:.84rem}.bar-chart{display:grid;gap:8px}.bar-row{display:grid;grid-template-columns:minmax(100px,155px) minmax(50px,1fr) minmax(72px,auto);align-items:center;gap:9px;font-size:.82rem}.bar-label{overflow-wrap:anywhere;line-height:1.25}.bar-track{height:13px;overflow:hidden;border-radius:99px;background:#e9eef2}.bar-fill{height:100%;border-radius:inherit;background:#0038a8}.bar-fill.school{background:#0038a8}.bar-fill.health{background:#008b74}.bar-fill.evacuation{background:#d47a00}.bar-value{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:650}.chart-empty{color:var(--muted);font-size:.88rem}@media(max-width:560px){.bar-row{grid-template-columns:minmax(88px,120px) minmax(35px,1fr) minmax(65px,auto);gap:6px;font-size:.76rem}.chart-panel{padding:12px}} @media(max-width:700px){main{padding:20px 12px}.section{padding:16px}table{font-size:.84rem}}
 .density-legend{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0;font-size:.82rem;color:var(--muted)}.density-legend span{display:inline-flex;align-items:center;gap:6px}.density-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;background:#0038a8}.density-legend i.facility{background:#008b74}.density-row,.density-header{display:grid;grid-template-columns:minmax(135px,220px) minmax(100px,1fr) minmax(100px,1fr);gap:12px;align-items:center}.density-row{padding:4px 0;font-size:.8rem}.density-header{margin:10px 0 3px;font-weight:700;font-size:.75rem;color:var(--muted)}.density-place{line-height:1.2}.density-bar{position:relative;height:18px;border-radius:99px;background:#e9eef2;overflow:hidden}.density-bar i{display:block;height:100%;border-radius:inherit;background:#0038a8}.density-bar.facility i{background:#008b74}.density-bar b{position:absolute;right:6px;top:0;font-size:.7rem;line-height:18px;color:#142b3b;font-variant-numeric:tabular-nums}@media(max-width:560px){.density-row,.density-header{grid-template-columns:minmax(82px,1fr) minmax(78px,1fr) minmax(78px,1fr);gap:6px;font-size:.68rem}.density-bar{height:20px}.density-bar b{font-size:.62rem;line-height:20px}}[hidden]{display:none!important}.controls button{font:inherit;padding:10px 15px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink);cursor:pointer}.controls button[aria-pressed="true"]{background:#0038a8;color:white;border-color:#0038a8}.controls button:focus-visible{outline:3px solid #f5c542;outline-offset:2px}.view-switch{position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:5}.heuristic-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.85rem;margin:16px 0}.heuristic-legend span:before{content:"";display:inline-block;width:12px;height:12px;background:var(--series);margin-right:6px;border-radius:3px}.heuristic-chart-row{display:grid;grid-template-columns:minmax(130px,1fr) minmax(180px,3fr);gap:18px;padding:14px 0;border-bottom:1px solid var(--line);font-size:.86rem}.heuristic-chart-row small{display:block;color:var(--muted);font-size:.72rem}.heuristic-series{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}.heuristic-bar-row{display:grid;grid-template-rows:auto 14px auto;gap:4px;align-items:center;font-size:.76rem}.heuristic-bar-row b{text-align:left}.heuristic-track{height:14px;background:#edf1f5;border-radius:5px;overflow:hidden}.heuristic-track i{display:block;height:100%;border-radius:5px}.heuristic-bar-row b{text-align:right;font-variant-numeric:tabular-nums}@media(max-width:760px){.heuristic-series{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.heuristic-chart-row{grid-template-columns:1fr;gap:8px}.view-switch button{padding:8px 10px;font-size:.85rem}}.education-health-hero{padding:clamp(22px,3vw,36px);background:linear-gradient(120deg,#00246a,#0038a8);border-left:8px solid #fcd116;border-radius:14px;margin-bottom:24px;color:white}.bettergov-research main .education-health-hero h2{color:white!important}.education-health-hero .eyebrow{color:#fcd116}.education-health-hero p,.education-health-hero .small{color:#f4f6f8}.section{box-shadow:none}.view-switch{border-bottom:1px solid var(--line)}main>.controls[aria-label="Geography level"]{padding:14px;background:white;border:1px solid var(--line);border-radius:11px}.geo-filters{align-items:end;position:relative}.geo-filters label{display:grid;gap:4px}.geo-filters input{min-height:40px}.geo-filters #geo-search-results{position:absolute;top:100%;left:40%;z-index:30;display:grid;max-height:320px;overflow:auto;background:white;border:1px solid var(--line);border-radius:8px;box-shadow:0 8px 24px #142b3b24}.geo-filters #geo-search-results button{padding:9px 12px;text-align:left;background:white;border:0;border-bottom:1px solid var(--line);font:inherit;cursor:pointer}.geo-filters #geo-search-results button:hover,.geo-filters #geo-search-results button:focus{background:#eaf0ff}@media(max-width:700px){.geo-filters #geo-search-results{left:0;right:0}}</style></head><body><header><h1>MPB, schools, health and evacuation facilities</h1><p>Compare FY2027 House Bill MPB project lines with mapped public-service facilities, and explore project titles at each geographic level.</p></header><main><section class="page-hero education-health-hero"><div class="eyebrow">Historical · MPB and public services</div><h2>How do MPB project lines compare with mapped facilities?</h2><p>Select a geography and a view below to explore record density and the uses mentioned in MPB titles.</p><p class="small">MPB allocations: FY2027 House Bill. Facility map snapshot: 4 November 2026.</p></section><div class="notice"><b>Coverage:</b> school and health counts use an OpenStreetMap snapshot downloaded 4 November 2026. Schools and health facilities are included only when public or government status is explicitly tagged. Evacuation counts use the official Quezon City directory within that city and explicitly tagged OSM candidates elsewhere. This combines sources with different coverage; it is not a complete national inventory.</div>
<div class="controls geo-filters" aria-label="Filter all sections by geography"><label>Region <select id="geo-region"><option value="">All regions</option></select></label><label>Province <select id="geo-province" disabled><option value="">All provinces</option></select></label><label>Municipality / city <select id="geo-municipality" disabled><option value="">All municipalities / cities</option></select></label><label>Barangay <select id="geo-barangay" disabled><option value="">All barangays</option></select></label><label>Quick place search <input id="geo-quick-search" type="search" placeholder="Search Bataan barangay or municipality" autocomplete="off"></label><div id="geo-search-results" role="listbox" aria-label="Matching places"></div><button type="button" id="geo-clear">Clear place</button></div><nav class="controls view-switch" aria-label="Comparison view"><button type="button" data-view="regional-charts" aria-pressed="true">Overview</button><button type="button" data-view="schools" aria-pressed="false">01 · Schools</button><button type="button" data-view="health" aria-pressed="false">02 · Health</button><button type="button" data-view="evacuation" aria-pressed="false">03 · Evacuation</button><button type="button" data-view="heuristics" aria-pressed="false">04 · MPB title analysis</button></nav><section class="section" id="data-coverage"><div class="kicker">What is counted</div><h2>Current data and coverage</h2><p>FY2027 MPB denominator: 5,805 House Bill project rows with PSGC places. Facility counts are dated source records joined to places; they are not counts of MPB-funded buildings.</p><div class="grid"><div class="status"><strong>48,129 DepEd public schools</strong><p>SY 2025–26 · 47,372 uniquely joined to municipalities and 46,686 to barangays. The panel reports 22,078,460 learners across 48,126 public schools; only joined records appear in place-level totals. Unmatched IDs are excluded from place counts.</p></div><div class="status"><strong>44,060 OSM school candidates joined</strong><p>OpenStreetMap snapshot · 4 Nov 2026 · used as an independent map cross-check, not added to DepEd counts.</p></div><div class="status"><strong>2,612 health candidates</strong><p>OpenStreetMap snapshot · 4 Nov 2026 · 2,682 candidates screened; 70 lack a unique PSGC place.</p></div><div class="status"><strong>781 PhilHealth government hospitals / infirmaries matched</strong><p>September 30, 2026 list · 824 government entries total · 60,744 beds in joined facilities; 43 government rows remain unmatched.</p></div><div class="status"><strong>2,722 PhilHealth YAKAP providers matched</strong><p>September 30, 2026 list · 2,917 government entries total · 195 government rows remain unmatched. YAKAP and hospital listings overlap.</p></div><div class="status"><strong>756 evacuation sites / candidates</strong><p>493 Quezon City government directory sites plus 265 OSM candidates elsewhere · 2 directory sites lack a barangay match.</p></div></div><p class="small">For school and health records, matching recovered 5,476 and 445 additional municipality joins respectively through unique municipality/province matches or unique matches within a broad province label. Ambiguous records remain unmatched. National school coverage is a joined-record lower bound, and health coverage remains a partial OSM count. The DOH National Health Facility Registry is the stronger next source; its official pages identify the registry and recent reports, but a facility-level download was not available in this research pass. <a href="https://nash.com.ph/blog/download-cleaned-deped-school-data" target="_blank" rel="noopener">DepEd dataset documentation</a> · <a href="https://sites.google.com/doh.gov.ph/hfsrbdata/home" target="_blank" rel="noopener">DOH HFSRB data repository mandate</a> · <a href="https://sites.google.com/view/doh-hfdb/2026-q3-updates/dc-2026-0525" target="_blank" rel="noopener">DOH NHFR annual-report circular</a>.</p></section><section class="section" id="regional-charts"><div class="kicker">Regional overview</div><h2>Project-line and mapped-facility density by place</h2><p class="small">Each bar uses the same denominator: rows or mapped candidates per 100 official barangays. Use the geography buttons above to change the whole page. Choose a facility type to compare its rate with MPB project-line density. The chart shows up to 20 places ranked by MPB rate. Learner totals show enrolled students at schools that joined to the selected places; three public-school rows have no reported enrollment. This compares record counts, not equivalent assets: one MPB line is not necessarily one building, and OpenStreetMap facility counts are incomplete candidates.</p><div class="chart-panel"><label for="density-facility"><strong>Compare MPB with</strong></label> <select id="density-facility" aria-label="Facility type to compare with MPB"><option value="depedSchools">DepEd public schools (SY 2025–26)</option><option value="depedEnrollment">DepEd enrolled learners (SY 2025–26)</option><option value="philhealthHospitals">PhilHealth government hospitals / infirmaries</option><option value="philhealthBeds">PhilHealth government hospital beds</option><option value="philhealthYakap">PhilHealth government YAKAP providers</option><option value="schools">OSM public-tagged school candidates</option><option value="health">Public-tagged health candidates</option><option value="evacuation">Evacuation candidates</option></select><p class="chart-note" id="density-summary"></p><div class="density-legend"><span><i></i>FY2027 MPB project rows</span><span><i class="facility"></i><span id="density-facility-legend">Public-tagged school candidates</span></span></div><div class="density-header" aria-hidden="true"><span>Place</span><span>MPB rows / 100 barangays</span><span id="density-facility-header">School candidates / 100 barangays</span></div><div class="bar-chart" id="density-region-chart" role="list" aria-label="MPB and mapped facility candidates per 100 barangays by region"></div></div></section>
<section class="section" id="schools"><div class="kicker">01 · Schools</div><h2>MPB density vs public-school counts</h2><p>The main school series counts DepEd SY 2025–26 public-school IDs joined to PSGC. OSM public-tagged school candidates are shown separately as a cross-check; the two sources overlap and are not added together. OSM counts are available at municipality and above, while DepEd joins also reach barangay level.</p><div class="grid" id="school-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">DepEd public schools (SY 2025–26)</th><th class="num">Reported learners (SY 2025–26)</th><th class="num">OSM public-tagged school candidates</th><th class="num">OSM candidates / 100 barangays*</th></tr></thead><tbody id="school-rows"></tbody></table></div></section>
<section class="section" id="health"><div class="kicker">02 · Health</div><h2>MPB density vs health facilities</h2><p>Compare the partial OSM map count with separate PhilHealth government hospital/infirmary and YAKAP provider lists (both updated September 30, 2026). Hospital beds are listed in the PhilHealth hospital source. These are different accreditation lists and can overlap; do not add their counts. PhilHealth lists include municipality but not barangay, so those measures are unavailable at barangay level. YAKAP includes RHUs, health centers and hospitals; it is not an all-facility census. <a href="https://www.philhealth.gov.ph/partners/providers/facilities/accredited/HOSP_093026.pdf" target="_blank" rel="noopener">hospital / infirmary list</a> · <a href="https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf" target="_blank" rel="noopener">YAKAP list</a>.</p><div class="grid" id="health-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped public-tagged facilities</th><th class="num">PhilHealth government hospitals / infirmaries</th><th class="num">Beds in matched government hospitals</th><th class="num">PhilHealth government YAKAP providers</th><th class="num">OSM candidates / 100 barangays*</th></tr></thead><tbody id="health-rows"></tbody></table></div></section>
<section class="section" id="evacuation"><div class="kicker">03 · Evacuation centers</div><h2>MPB density vs mapped evacuation candidates</h2><p>Quezon City uses 493 distinct evacuation sites in the city government directory, replacing its OSM candidates. Other locations use explicitly tagged OSM candidates. The directory includes 422 temporary, 69 semi-permanent and 2 permanent sites. Three repeated listings were excluded; two sites labeled Quirino 3-B remain included in city totals but have no resolved barangay assignment.</p><div class="grid" id="evacuation-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped evacuation candidates</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="evacuation-rows"></tbody></table></div></section>
<section class="section" id="heuristics" hidden><div class="kicker">04 · Title-only heuristics</div><h2>Title-only heuristic: MPB vs schools, health and evacuation</h2><p>These counts flag MPB titles containing relevant words. A keyword does not prove the building’s use. One project can appear in more than one category.</p><div class="controls"><input id="geo-search" type="search" placeholder="Filter place, region or province" aria-label="Filter title analysis by place"><label>Chart measure <select id="heuristic-metric"><option value="count">Project rows</option><option value="rate">Rows per 100 barangays</option></select></label></div><p id="heuristic-summary" class="small" aria-live="polite"></p><div class="heuristic-legend"><span style="--series:#0038a8">School title hits</span><span style="--series:#008b74">Health title hits</span><span style="--series:#d47a00">Evacuation title hits</span><span style="--series:#697a8b">Other MPB rows</span></div><div id="heuristic-chart" role="list" aria-label="MPB title categories by place"></div><p class="small">Bars share one scale starting at zero. Categories can overlap; each is drawn separately. Chart shows up to 20 places ranked by total MPB rows or rate; the table includes all filtered places.</p><div class="table-wrap"><table><thead><tr><th>Place</th><th>Region</th><th>Province</th><th class="num">School title hits</th><th class="num">Health title hits</th><th class="num">Evacuation title hits</th><th class="num">Other MPB rows</th></tr></thead><tbody id="heuristic-rows"></tbody></table></div><p class="small">Keyword rules use title text only: school/classroom/education/college/university; health/hospital/clinic/medical/infirmary/birthing/RHU; evacuation/evac. Other means no hit in these title-only word groups.</p></section>
<section class="section" id="additional-sources"><h2>Facility records incorporated</h2><p><strong>Quezon City evacuation sites:</strong> extracted 496 rows; retained 493 distinct barangay/name/address listings after removing three repeated entries. 491 match a PSGC barangay; two Quirino 3-B listings remain assigned only at city level. Types: 422 temporary, 69 semi-permanent, 2 permanent. Same-named sites at different addresses remain separate. The directory replaces OSM counts in Quezon City.</p><p><a href="education-health-official-sites.json" download>Download extracted city records and count audit</a> · <a href="education-health-facility-crosswalk.json" download>Download facility-to-PSGC crosswalk</a></p><h3>Additional sources checked</h3><p><strong>DOH National Health Facility Registry:</strong> DOH confirmed through an FOI response that a 2025 NHFR-derived Excel and shapefile can be released on request; the 2025 coordinate layer may be incomplete and have coordinate gaps. We have not received those files, so they are not in these counts. <a href="https://www.foi.gov.ph/agencies/doh/digitized-map-of-hospitals-and-health-facilities/">DOH FOI response and data notes</a>.</p><p><strong>DepEd Region VIII public-school list:</strong> downloaded the SY 2025–2026 PDF, but it is regional and text extraction/OCR returned no records. It did not change school counts.</p></section><p class="footer">*Denominator: official barangay count for the reporting geography; MPB rate is project rows per 100 barangays, not buildings or expenditure. OSM facilities join at municipality/city PSGC and roll up to provinces and regions. Quezon City official evacuation sites also join to barangays where names resolve. The OSM source layer contains mapped candidates only, and blank or untagged locations are not evidence that a facility is absent. <a href="connectivity-public-services-data.json">Download the mapped public-service source layer</a> · <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors · ODbL</a>.</p></main><script>
const pageViews=['regional-charts','schools','health','evacuation','heuristics'];function selectView(view){pageViews.forEach(id=>document.getElementById(id).hidden=id!==view);document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)))}document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{selectView(b.dataset.view);history.replaceState(null,'','#'+b.dataset.view)}));selectView(pageViews.includes(location.hash.slice(1))?location.hash.slice(1):'regional-charts');window.addEventListener('hashchange',()=>selectView(pageViews.includes(location.hash.slice(1))?location.hash.slice(1):'regional-charts'));fetch('education-health-data.json').then(r=>r.json()).then(d=>{let geoLevel='region',selected={region:'',province:'',municipality:'',barangay:''};const geoSelects={region:document.getElementById('geo-region'),province:document.getElementById('geo-province'),municipality:document.getElementById('geo-municipality'),barangay:document.getElementById('geo-barangay')};const inLevel=x=>{if(selected.region&&x.regionCode!==selected.region)return false;if(selected.province&&x.provinceCode!==selected.province)return false;if(selected.municipality&&x.municipalityCode!==selected.municipality)return false;if(selected.barangay&&x.code!==selected.barangay)return false;return geoLevel==='municipality'?['municipality','city'].includes(x.level):x.level===geoLevel};const fmt=n=>Number(n||0).toLocaleString('en-PH');const levels={municipality:'Municipality / city',city:'City',province:'Province',region:'Region'};const facilities=d.facilityInventories;const tableIds={schools:'school-rows',health:'health-rows',evacuation:'evacuation-rows'};function renderFacilityTables(){for(const [key,id] of Object.entries(tableIds)){const facility=facilities[key];document.getElementById(key==='schools'?'school-status':key==='health'?'health-status':'evacuation-status').innerHTML=key==='health'?`<div class="status"><strong>${fmt(facility.joinedRows)} OSM public-tagged health candidates joined</strong><p class="small">Partial mapped cross-check; 70 of 2,682 candidates could not be uniquely matched.</p></div><div class="status"><strong>${fmt(facilities.philhealthHospitals.summary.governmentUniqueJoined)} government hospitals / infirmaries joined</strong><p class="small">${fmt(facilities.philhealthHospitals.summary.governmentRows)} government entries; ${fmt(facilities.philhealthHospitals.summary.governmentUnmatchedRows)} unresolved rows; ${fmt(facilities.philhealthHospitals.summary.governmentBedsJoined)} beds in matched facilities.</p></div><div class="status"><strong>${fmt(facilities.philhealthYakap.summary.governmentUniqueJoined)} government YAKAP providers joined</strong><p class="small">${fmt(facilities.philhealthYakap.summary.governmentRows)} government entries; ${fmt(facilities.philhealthYakap.summary.governmentUnmatchedRows)} unresolved rows; rows matched to unique PSGC municipalities.</p></div>`:`<div class="status"><strong>${fmt(facility.joinedRows)} facility records joined</strong><span class="pill">${key==='evacuation'?'City directory + OSM':'OSM · partial'}</span><p class="small">${facility.status}</p><p class="small">${fmt((facility.recoveredByUniqueMunicipalityProvince||0)+(facility.recoveredByUniqueMunicipalityProvinceFamily||0))} records recovered using unique municipality/province matches. ${fmt(facility.unmatchedRows)} candidate points could not be matched to a unique PSGC municipality.</p></div>`;const list=d.geographyRows.filter(inLevel);document.getElementById(id).innerHTML=list.map(x=>{const count=x.facilityCounts[key];return `<tr><td>${levels[x.level]||x.level}</td><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(x.mpbRows)}</td><td class="num">${fmt(x.mpbRows*100/Math.max(1,x.officialBarangays))}</td><td class="num">${key==='schools'?(x.depedPublicSchoolCount?fmt(x.depedPublicSchoolCount):'No joined ID'):count==null?'Unavailable':fmt(count)}</td>${key==='schools'?`<td class="num">${count==null?'Unavailable':fmt(count)}</td><td class="num">${count==null?'Unavailable':fmt(count*100/Math.max(1,x.officialBarangays))}</td>`:key==='health'?`<td class="num">${x.philhealthHealthCounts?.hospitals==null?'Unavailable':x.philhealthHealthCounts.hospitals?fmt(x.philhealthHealthCounts.hospitals):'No matched record'}</td><td class="num">${x.philhealthGovernmentHospitalBeds==null?'Unavailable':x.philhealthGovernmentHospitalBeds?fmt(x.philhealthGovernmentHospitalBeds):'No matched record'}</td><td class="num">${x.philhealthHealthCounts?.yakap==null?'Unavailable':x.philhealthHealthCounts.yakap?fmt(x.philhealthHealthCounts.yakap):'No matched record'}</td><td class="num">${count==null?'Unavailable':fmt(count*100/Math.max(1,x.officialBarangays))}</td>`:`<td class="num">${count==null?'Unavailable':fmt(count*100/Math.max(1,x.officialBarangays))}</td>`}</tr>`}).join('')||`<tr><td colspan="${key==='schools'?10:key==='health'?11:8}">No MPB PSGC matches at this level.</td></tr>`}}renderFacilityTables();const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const densitySelect=document.getElementById('density-facility'),densityLabels={philhealthHospitals:'PhilHealth government hospitals / infirmaries',philhealthBeds:'Beds in PhilHealth government hospitals',philhealthYakap:'PhilHealth government YAKAP providers',depedSchools:'DepEd public schools (SY 2025–26)',depedEnrollment:'Reported DepEd learners (SY 2025–26)',schools:'OSM public-tagged school candidates',health:'OSM public-tagged health candidates',evacuation:'Evacuation candidates'};function renderDensity(){const regions=d.geographyRows.filter(inLevel).filter(x=>['region','province','municipality','city','barangay'].includes(x.level));const key=densitySelect.value,label=densityLabels[key],rows=regions.map(x=>({name:x.name,facilityAvailable:key==='depedSchools'?Number(x.depedPublicSchoolCount)>0:key==='depedEnrollment'?Number(x.depedEnrollmentSchoolCount)>0:key.startsWith('philhealth')?x.level!=='barangay'&&Number(key==='philhealthHospitals'?x.philhealthHealthCounts?.hospitals:key==='philhealthYakap'?x.philhealthHealthCounts?.yakap:x.philhealthGovernmentHospitalBeds)>0:x.facilityCounts?.[key]!=null,mpb:Number(x.mpbRows||0)*100/Math.max(1,Number(x.officialBarangays||0)),facility:Number(key==='depedSchools'?x.depedPublicSchoolCount:key==='depedEnrollment'?x.depedPublicEnrollment:key==='philhealthHospitals'?x.philhealthHealthCounts?.hospitals||0:key==='philhealthYakap'?x.philhealthHealthCounts?.yakap||0:key==='philhealthBeds'?x.philhealthGovernmentHospitalBeds||0:x.facilityCounts?.[key]||0)*100/Math.max(1,Number(x.officialBarangays||0))})).sort((a,b)=>b.mpb-a.mpb).slice(0,20);const max=Math.max(1,...rows.flatMap(x=>[x.mpb,x.facility]));document.getElementById('density-facility-legend').textContent=label;document.getElementById('density-facility-header').textContent=label.replace('Public-tagged ','').replace('candidates','candidates')+' / 100 barangays';document.getElementById('density-region-chart').innerHTML=rows.map(x=>`<div class="density-row" role="listitem" title="${esc(x.name)} · MPB ${x.mpb.toFixed(1)} rows/100 barangays · ${esc(label)} ${x.facilityAvailable?x.facility.toFixed(1):'unavailable'}/100 barangays"><span class="density-place">${esc(x.name)}</span><span class="density-bar"><i style="width:${Math.max(0,Math.min(100,x.mpb/max*100))}%"></i><b>${x.mpb.toFixed(1)}</b></span><span class="density-bar facility"><i style="width:${Math.max(0,Math.min(100,x.facility/max*100))}%"></i><b>${x.facilityAvailable?x.facility.toFixed(1):'N/A'}</b></span></div>`).join('');const totalBarangays=regions.reduce((a,x)=>a+Number(x.officialBarangays||0),0),mpbTotal=regions.reduce((a,x)=>a+Number(x.mpbRows||0),0),facilityTotal=regions.reduce((a,x)=>a+Number(key==='depedSchools'?x.depedPublicSchoolCount:key==='depedEnrollment'?x.depedPublicEnrollment:key==='philhealthHospitals'?x.philhealthHealthCounts?.hospitals||0:key==='philhealthYakap'?x.philhealthHealthCounts?.yakap||0:key==='philhealthBeds'?x.philhealthGovernmentHospitalBeds||0:x.facilityCounts?.[key]||0),0);document.getElementById('density-summary').textContent=geoLevel==='barangay'?(key==='depedSchools'||key==='depedEnrollment')?'DepEd 2025–26 school IDs shown are those joined to this barangay; zero matches are not proof that no school exists. OSM school and health counts are unavailable at barangay level.':key.startsWith('philhealth')?'PhilHealth lists do not publish barangay fields; those counts are unavailable at barangay level. OSM school and health counts are also unavailable there.':'Barangay school and health counts are unavailable. Evacuation counts are available only for matched Quezon City directory barangays; unlisted barangays are unavailable, not zero.':`Across selected places: ${ (mpbTotal*100/Math.max(1,totalBarangays)).toFixed(1) } MPB project rows and ${(facilityTotal*100/Math.max(1,totalBarangays)).toFixed(1)} ${label.toLowerCase()} per 100 official barangays.`}densitySelect.addEventListener('change',renderDensity);renderDensity();const rows=d.geographyRows;function draw(){const level=geoLevel,q=document.getElementById('geo-search').value.trim().toLowerCase();const list=rows.filter(x=>(x.level===level||(level==='municipality'&&x.level==='city'))&&(!q||[x.name,x.region,x.province].join(' ').toLowerCase().includes(q)));const rate=document.getElementById('heuristic-metric').value==='rate',value=(x,n)=>rate?n*100/Math.max(1,x.officialBarangays):n,series=[['school','School','#0038a8'],['health','Health','#008b74'],['evacuation','Evacuation','#d47a00'],['other','Other','#697a8b']],count=(x,key)=>key==='other'?Math.max(0,x.mpbRows-x.heuristicAny):(x.heuristics?.[key]?.rows||0),top=[...list].sort((a,b)=>value(b,b.mpbRows)-value(a,a.mpbRows)||a.name.localeCompare(b.name)).slice(0,20),max=Math.max(1,...top.flatMap(x=>series.map(([key])=>value(x,count(x,key)))));document.getElementById('heuristic-summary').textContent=`${fmt(list.length)} places match · showing ${fmt(top.length)} in the chart · ${rate?'rows per 100 official barangays':'project rows'}.`;document.getElementById('heuristic-chart').innerHTML=top.map(x=>`<div class="heuristic-chart-row" role="listitem"><div><strong>${esc(x.name)}</strong><small>${esc([x.province,x.region].filter(Boolean).join(' · '))}</small></div><div class="heuristic-series">${series.map(([key,label,color])=>{const n=value(x,count(x,key));return `<div class="heuristic-bar-row"><span>${label}</span><div class="heuristic-track"><i style="width:${n/max*100}%;background:${color}"></i></div><b>${rate?n.toFixed(1):fmt(n)}</b></div>`}).join('')}</div></div>`).join('')||'<p>No locations match.</p>';document.getElementById('heuristic-rows').innerHTML=list.map(x=>{const h=x.heuristics||{},school=h.school?.rows||0,health=h.health?.rows||0,evac=h.evacuation?.rows||0;return `<tr><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(school)}</td><td class="num">${fmt(health)}</td><td class="num">${fmt(evac)}</td><td class="num">${fmt(Math.max(0,x.mpbRows-x.heuristicAny))}</td></tr>`}).join('')||'<tr><td colspan="7">No locations match.</td></tr>'}function fillGeo(level,parentCode=''){const sel=geoSelects[level],levels={region:['region'],province:['province'],municipality:['municipality','city'],barangay:['barangay']},parent={province:'regionCode',municipality:'provinceCode',barangay:'municipalityCode'}[level];const options=d.geographyRows.filter(x=>levels[level].includes(x.level)&&(!parentCode||x[parent]===parentCode)).sort((a,b)=>a.name.localeCompare(b.name));sel.innerHTML=`<option value="">All ${level==='municipality'?'municipalities / cities':level+'s'}</option>`+options.map(x=>`<option value="${x.code}">${esc(x.name)}</option>`).join('');sel.disabled=level!=='region'&&!parentCode}fillGeo('region');function updateGeo(level){const order=['region','province','municipality','barangay'],i=order.indexOf(level);selected[level]=geoSelects[level].value;geoLevel=selected.barangay?'barangay':selected.municipality?'municipality':selected.province?'province':selected.region?'region':'region';for(let j=i+1;j<order.length;j++){selected[order[j]]='';fillGeo(order[j],selected[order[j-1]])}renderFacilityTables();renderDensity();draw()}for(const level of ['region','province','municipality','barangay'])geoSelects[level].addEventListener('change',()=>updateGeo(level));const quickSearch=document.getElementById('geo-quick-search'),suggestions=document.getElementById('geo-search-results');function selectPlace(x){const region=x.regionCode||'',province=x.provinceCode||'',municipality=x.municipalityCode||'',isBarangay=x.level==='barangay';selected={region,province,municipality,barangay:isBarangay?x.code:''};geoLevel=isBarangay?'barangay':x.level==='city'||x.level==='municipality'?'municipality':x.level;geoSelects.region.value=region;fillGeo('province',region);geoSelects.province.value=province;fillGeo('municipality',province);geoSelects.municipality.value=municipality;fillGeo('barangay',municipality);geoSelects.barangay.value=isBarangay?x.code:'';geoSelects.barangay.disabled=!municipality;quickSearch.value=[x.name,x.level==='barangay'?x.province:'',x.level==='barangay'?x.region:''].filter(Boolean).join(', ');suggestions.innerHTML='';renderFacilityTables();renderDensity();draw()}quickSearch.addEventListener('input',()=>{const q=quickSearch.value.trim().toLowerCase();if(q.length<2){suggestions.innerHTML='';return}const hits=d.geographyRows.filter(x=>['region','province','municipality','city','barangay'].includes(x.level)&&[x.name,x.region,x.province].join(' ').toLowerCase().includes(q)).sort((a,b)=>({region:0,province:1,municipality:2,city:2,barangay:3}[a.level] - {region:0,province:1,municipality:2,city:2,barangay:3}[b.level]) || a.name.localeCompare(b.name)).slice(0,15);suggestions.innerHTML=hits.map((x,i)=>`<button type="button" role="option" data-hit="${i}">${esc(x.name)} · ${esc(x.level)}${x.province?' · '+esc(x.province):''}${x.level==='barangay'?' · '+esc(x.region):''}</button>`).join('');suggestions.querySelectorAll('button').forEach((button,i)=>button.addEventListener('click',()=>selectPlace(hits[i])))});document.getElementById('geo-clear').addEventListener('click',()=>{selected={region:'',province:'',municipality:'',barangay:''};geoLevel='region';quickSearch.value='';suggestions.innerHTML='';for(const k of ['region','province','municipality','barangay']){geoSelects[k].value='';if(k!=='region')fillGeo(k,'')}renderFacilityTables();renderDensity();draw()});document.getElementById('heuristic-metric').addEventListener('change',draw);document.getElementById('geo-search').addEventListener('input',draw);draw()}).catch(e=>{document.querySelector('main').insertAdjacentHTML('beforeend',`<p class="notice">MPB data could not be loaded: ${e.message}</p>`)})
</script></body></html>'''
    from uniform_report_menu import apply_page as apply_menu
    from report_table_presentation import apply_page_table_module
    html = apply_menu(html, PAGE)
    html, _ = apply_page_table_module(PAGE, html)
    for dest in (OUT / PAGE, STATIC / PAGE):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding='utf-8')
    return {'page': PAGE, 'mpbProjectRows': data['mpbProjectRows'], 'geographyRows': len(data['geographyRows'])}


if __name__ == '__main__':
    data = build_data()
    print(json.dumps(build_page(data), indent=2))
