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

    for category, qualifies in categories.items():
        candidates = [
            row for row in mapped
            if qualifies(row, tags_by_id.get(row['id'], {}))
        ]
        joined = 0
        joined_municipalities = set()
        for row in candidates:
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
            if len(matches) != 1:
                unmatched[category] += 1
                continue
            place, province, region = matches[0]
            joined += 1
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
            'joinBasis': 'Mapped source point or feature center matched to exactly one PSGC municipality/city using municipality name and region; counts roll up to province and region.',
            'status': 'Partial OSM candidates only. Counts require explicit public/government tags for schools and health facilities; evacuation candidates require explicit shelter or evacuation tags. This is not a complete or official facility inventory.',
        }

    for row in geography_rows:
        counts = {category: counters[category].get(row['code'], 0) for category in categories}
        if row['level'] in {'municipality', 'city', 'province', 'region'}:
            row['facilityCounts'] = counts
        else:
            row['facilityCounts'] = {category: None for category in categories}
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
            'facilitySourceNote': 'Facility candidates are a partial OpenStreetMap snapshot, not authoritative school, health or evacuation-center inventories. Only facilities with explicit public/government tags are counted for schools and health. Candidate points are joined to PSGC municipalities/cities by unique municipality name and region, then rolled up to province and region; barangay-level facility counts are not inferred.',
            'method': 'MPB row counts use FY2027 House Bill line records assigned to PSGC places. MPB density is shown as project rows per 100 official barangays where coverage exists. Facility candidate counts per 100 barangays use municipality/city PSGC joins and official barangay denominators; they are incomplete map counts, not confirmed inventory coverage. Heuristic labels inspect title text only; they are not confirmed building uses.'}


def build_page(data):
    (OUT / DATA).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    (STATIC / DATA).parent.mkdir(parents=True, exist_ok=True)
    (STATIC / DATA).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MPB vs Schools, Health and Evacuation Facilities</title><style>
:root{--ink:#142b3b;--muted:#566b79;--line:#d8e1e7;--blue:#0038a8;--gold:#f5c542;--bg:#f5f8fa}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}main{width:100%;max-width:none;margin:0;padding:26px clamp(16px,2vw,32px) 56px}.eyebrow{font-weight:750;letter-spacing:.1em;color:var(--blue);font-size:.78rem}h1{font-size:clamp(2rem,4vw,3.3rem);line-height:1.08;margin:.35rem 0 1rem}h2{margin:.1rem 0 .6rem;font-size:1.5rem}h3{margin:0 0 .5rem}.lede{max-width:800px;color:var(--muted)}.section{margin:24px 0;padding:24px;background:white;border:1px solid var(--line);border-radius:15px;box-shadow:0 3px 12px #17334a0a}.kicker{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--blue);font-weight:750}.notice{border-left:4px solid var(--gold);padding:12px 15px;background:#fff9e7;border-radius:5px;color:#394b57}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}.controls select,.controls input{font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:white}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f4f7f9;position:sticky;top:0}.num{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:9px}.small{font-size:.88rem;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.status{padding:14px;background:#f6f8fa;border:1px solid var(--line);border-radius:10px}.status strong{display:block;margin-bottom:4px}.pill{display:inline-block;border-radius:20px;padding:3px 9px;background:#eaf0ff;color:#173c82;font-size:.78rem;font-weight:700}.footer{font-size:.86rem;color:var(--muted);margin-top:20px}.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:14px;margin-top:16px}.chart-panel{min-width:0;padding:16px;border:1px solid var(--line);border-radius:12px;background:#fbfcfd}.chart-panel h3{font-size:1.05rem}.chart-note{margin:0 0 12px;color:var(--muted);font-size:.84rem}.bar-chart{display:grid;gap:8px}.bar-row{display:grid;grid-template-columns:minmax(100px,155px) minmax(50px,1fr) minmax(72px,auto);align-items:center;gap:9px;font-size:.82rem}.bar-label{overflow-wrap:anywhere;line-height:1.25}.bar-track{height:13px;overflow:hidden;border-radius:99px;background:#e9eef2}.bar-fill{height:100%;border-radius:inherit;background:#0038a8}.bar-fill.school{background:#0038a8}.bar-fill.health{background:#008b74}.bar-fill.evacuation{background:#d47a00}.bar-value{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:650}.chart-empty{color:var(--muted);font-size:.88rem}@media(max-width:560px){.bar-row{grid-template-columns:minmax(88px,120px) minmax(35px,1fr) minmax(65px,auto);gap:6px;font-size:.76rem}.chart-panel{padding:12px}} @media(max-width:700px){main{padding:20px 12px}.section{padding:16px}table{font-size:.84rem}}
 .density-legend{display:flex;gap:16px;flex-wrap:wrap;margin:12px 0;font-size:.82rem;color:var(--muted)}.density-legend span{display:inline-flex;align-items:center;gap:6px}.density-legend i{display:inline-block;width:12px;height:12px;border-radius:3px;background:#0038a8}.density-legend i.facility{background:#008b74}.density-row,.density-header{display:grid;grid-template-columns:minmax(135px,220px) minmax(100px,1fr) minmax(100px,1fr);gap:12px;align-items:center}.density-row{padding:4px 0;font-size:.8rem}.density-header{margin:10px 0 3px;font-weight:700;font-size:.75rem;color:var(--muted)}.density-place{line-height:1.2}.density-bar{position:relative;height:18px;border-radius:99px;background:#e9eef2;overflow:hidden}.density-bar i{display:block;height:100%;border-radius:inherit;background:#0038a8}.density-bar.facility i{background:#008b74}.density-bar b{position:absolute;right:6px;top:0;font-size:.7rem;line-height:18px;color:#142b3b;font-variant-numeric:tabular-nums}@media(max-width:560px){.density-row,.density-header{grid-template-columns:minmax(82px,1fr) minmax(78px,1fr) minmax(78px,1fr);gap:6px;font-size:.68rem}.density-bar{height:20px}.density-bar b{font-size:.62rem;line-height:20px}}[hidden]{display:none!important}.controls button{font:inherit;padding:10px 15px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink);cursor:pointer}.controls button[aria-pressed="true"]{background:#0038a8;color:white;border-color:#0038a8}.controls button:focus-visible{outline:3px solid #f5c542;outline-offset:2px}.view-switch{position:sticky;top:0;background:var(--bg);padding:12px 0;z-index:5}.heuristic-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.85rem;margin:16px 0}.heuristic-legend span:before{content:"";display:inline-block;width:12px;height:12px;background:var(--series);margin-right:6px;border-radius:3px}.heuristic-chart-row{display:grid;grid-template-columns:minmax(130px,1fr) minmax(180px,3fr);gap:18px;padding:14px 0;border-bottom:1px solid var(--line);font-size:.86rem}.heuristic-chart-row small{display:block;color:var(--muted);font-size:.72rem}.heuristic-series{display:grid;gap:4px}.heuristic-bar-row{display:grid;grid-template-columns:78px 1fr 45px;gap:8px;align-items:center;font-size:.76rem}.heuristic-track{height:12px;background:#edf1f5;border-radius:5px;overflow:hidden}.heuristic-track i{display:block;height:100%;border-radius:5px}.heuristic-bar-row b{text-align:right;font-variant-numeric:tabular-nums}@media(max-width:560px){.heuristic-chart-row{grid-template-columns:1fr;gap:8px}.view-switch button{padding:8px 10px;font-size:.85rem}}.education-health-hero{padding:clamp(22px,3vw,36px);background:linear-gradient(120deg,#00246a,#0038a8);border-left:8px solid #fcd116;border-radius:14px;margin-bottom:24px;color:white}.bettergov-research main .education-health-hero h2{color:white!important}.education-health-hero .eyebrow{color:#fcd116}.education-health-hero p,.education-health-hero .small{color:#f4f6f8}.section{box-shadow:none}.view-switch{border-bottom:1px solid var(--line)}main>.controls[aria-label="Geography level"]{padding:14px;background:white;border:1px solid var(--line);border-radius:11px}</style></head><body><header><h1>MPB, schools, health and evacuation facilities</h1><p>Compare FY2027 House Bill MPB project lines with mapped public-service facilities, and explore project titles at each geographic level.</p></header><main><section class="page-hero education-health-hero"><div class="eyebrow">Historical · MPB and public services</div><h2>How do MPB project lines compare with mapped facilities?</h2><p>Select a geography and a view below to explore record density and the uses mentioned in MPB titles.</p><p class="small">MPB allocations: FY2027 House Bill. Facility map snapshot: 4 November 2026.</p></section><div class="notice"><b>Coverage:</b> facility counts use an OpenStreetMap snapshot downloaded 4 November 2026. Schools and health facilities are included only when public or government status is explicitly tagged. Evacuation candidates need an explicit evacuation or displaced-shelter tag. This map layer is incomplete and is not an official inventory.</div>
<div class="controls" role="group" aria-label="Geography level"><button type="button" data-level="region" aria-pressed="true">Region</button><button type="button" data-level="province" aria-pressed="false">Province</button><button type="button" data-level="municipality" aria-pressed="false">Municipality / city</button><button type="button" data-level="barangay" aria-pressed="false">Barangay</button></div><nav class="controls view-switch" aria-label="Comparison view"><button type="button" data-view="regional-charts" aria-pressed="true">Overview</button><button type="button" data-view="schools" aria-pressed="false">01 · Schools</button><button type="button" data-view="health" aria-pressed="false">02 · Health</button><button type="button" data-view="evacuation" aria-pressed="false">03 · Evacuation</button><button type="button" data-view="heuristics" aria-pressed="false">04 · MPB title analysis</button></nav><section class="section" id="regional-charts"><div class="kicker">Regional overview</div><h2>Project-line and mapped-facility density by place</h2><p class="small">Each bar uses the same denominator: rows or mapped candidates per 100 official barangays. Use the geography buttons above to change the whole page. Choose a facility type to compare its rate with MPB project-line density. The chart shows up to 20 places ranked by MPB rate. This compares record counts, not equivalent assets: one MPB line is not necessarily one building, and OpenStreetMap facility counts are incomplete candidates.</p><div class="chart-panel"><label for="density-facility"><strong>Compare MPB with</strong></label> <select id="density-facility" aria-label="Facility type to compare with MPB"><option value="schools">Public-tagged school candidates</option><option value="health">Public-tagged health candidates</option><option value="evacuation">Evacuation candidates</option></select><p class="chart-note" id="density-summary"></p><div class="density-legend"><span><i></i>FY2027 MPB project rows</span><span><i class="facility"></i><span id="density-facility-legend">Public-tagged school candidates</span></span></div><div class="density-header" aria-hidden="true"><span>Place</span><span>MPB rows / 100 barangays</span><span id="density-facility-header">School candidates / 100 barangays</span></div><div class="bar-chart" id="density-region-chart" role="list" aria-label="MPB and mapped facility candidates per 100 barangays by region"></div></div></section>
<section class="section" id="schools"><div class="kicker">01 · Schools</div><h2>MPB density vs mapped public-school candidates</h2><p>Counts include mapped school features with explicit public or government operator/ownership tags. Facility points join to municipality/city PSGC by unique municipality name and region; totals roll up to province and region. Barangay-level school counts are not inferred.</p><div class="grid" id="school-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped public-tagged schools</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="school-rows"></tbody></table></div></section>
<section class="section" id="health"><div class="kicker">02 · Health</div><h2>MPB density vs mapped public health candidates</h2><p>Counts include mapped hospitals, clinics and health posts with explicit public or government operator/ownership tags. Private and unclassified facilities are excluded; this OSM subset is incomplete and has not been checked against the DOH NHFR.</p><div class="grid" id="health-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped public-tagged facilities</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="health-rows"></tbody></table></div></section>
<section class="section" id="evacuation"><div class="kicker">03 · Evacuation centers</div><h2>MPB density vs mapped evacuation candidates</h2><p>Counts include features explicitly tagged as evacuation centers or shelters for displaced people. These mapped candidates are not a complete or currently validated LGU/OCD inventory.</p><div class="grid" id="evacuation-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped evacuation candidates</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="evacuation-rows"></tbody></table></div></section>
<section class="section" id="heuristics" hidden><div class="kicker">04 · Title-only heuristics</div><h2>Title-only heuristic: MPB vs schools, health and evacuation</h2><p>These counts flag MPB titles containing relevant words. A keyword does not prove the building’s use. One project can appear in more than one category.</p><div class="controls"><input id="geo-search" type="search" placeholder="Filter place, region or province" aria-label="Filter title analysis by place"><label>Chart measure <select id="heuristic-metric"><option value="count">Project rows</option><option value="rate">Rows per 100 barangays</option></select></label></div><p id="heuristic-summary" class="small" aria-live="polite"></p><div class="heuristic-legend"><span style="--series:#0038a8">School title hits</span><span style="--series:#008b74">Health title hits</span><span style="--series:#d47a00">Evacuation title hits</span><span style="--series:#697a8b">Other MPB rows</span></div><div id="heuristic-chart" role="list" aria-label="MPB title categories by place"></div><p class="small">Bars share one scale starting at zero. Categories can overlap; each is drawn separately. Chart shows up to 20 places ranked by total MPB rows or rate; the table includes all filtered places.</p><div class="table-wrap"><table><thead><tr><th>Place</th><th>Region</th><th>Province</th><th class="num">School title hits</th><th class="num">Health title hits</th><th class="num">Evacuation title hits</th><th class="num">Other MPB rows</th></tr></thead><tbody id="heuristic-rows"></tbody></table></div><p class="small">Keyword rules use title text only: school/classroom/education/college/university; health/hospital/clinic/medical/infirmary/birthing/RHU; evacuation/evac. Other means no hit in these title-only word groups.</p></section>
<section class="section" id="additional-sources"><h2>Additional data sources</h2><p class="small">Sources identified for improving this comparison; their records have not been added to the counts above.</p><ul><li><a href="https://region8.deped.gov.ph/2025/06/25/june-23-2025-rm-704-s-2025-masterlist-of-public-schools-with-approved-government-authority-to-operate-effective-s-y-2025-2026/">DepEd Region VIII public-school masterlist, SY 2025–2026</a> — a regional reference for checking school identities and public status.</li><li><a href="https://quezoncity.gov.ph/qcitizen-guides/quezon-city-evacuation-centers/">Quezon City evacuation centers for flood and fire</a> — lists barangay, location name, address and center type. Includes temporary sites such as schools and covered courts; these should be distinguished from dedicated evacuation buildings.</li><li><a href="https://nhfr.doh.gov.ph/">DOH National Health Facility Registry</a> — a candidate source for checking health-facility records; automated access returned HTTP 403 during this review.</li></ul></section><p class="footer">*Denominator: official barangay count for the reporting geography; MPB rate is project rows per 100 barangays, not buildings or expenditure. Facilities join at municipality/city PSGC and roll up to provinces and regions; barangay-level facility totals are not available. The OSM source layer contains mapped candidates only, and blank or untagged locations are not evidence that a facility is absent. <a href="connectivity-public-services-data.json">Download the mapped public-service source layer</a> · <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors · ODbL</a>.</p></main><script>
const pageViews=['regional-charts','schools','health','evacuation','heuristics'];function selectView(view){pageViews.forEach(id=>document.getElementById(id).hidden=id!==view);document.querySelectorAll('[data-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===view)))}document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{selectView(b.dataset.view);history.replaceState(null,'','#'+b.dataset.view)}));selectView(pageViews.includes(location.hash.slice(1))?location.hash.slice(1):'regional-charts');window.addEventListener('hashchange',()=>selectView(pageViews.includes(location.hash.slice(1))?location.hash.slice(1):'regional-charts'));fetch('education-health-data.json').then(r=>r.json()).then(d=>{let geoLevel='region';const inLevel=x=>x.level===geoLevel||(geoLevel==='municipality'&&x.level==='city');const fmt=n=>Number(n||0).toLocaleString('en-PH');const levels={municipality:'Municipality / city',city:'City',province:'Province',region:'Region'};const facilities=d.facilityInventories;const tableIds={schools:'school-rows',health:'health-rows',evacuation:'evacuation-rows'};function renderFacilityTables(){for(const [key,id] of Object.entries(tableIds)){const facility=facilities[key];document.getElementById(key==='schools'?'school-status':key==='health'?'health-status':'evacuation-status').innerHTML=`<div class="status"><strong>${fmt(facility.joinedRows)} mapped candidates joined</strong><span class="pill">OSM · partial</span><p class="small">${facility.status}</p><p class="small">${fmt(facility.unmatchedRows)} candidate points could not be matched to a unique PSGC municipality.</p></div>`;const list=d.geographyRows.filter(inLevel);document.getElementById(id).innerHTML=list.map(x=>{const count=x.facilityCounts[key];return `<tr><td>${levels[x.level]||x.level}</td><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(x.mpbRows)}</td><td class="num">${fmt(x.mpbRows*100/Math.max(1,x.officialBarangays))}</td><td class="num">${count==null?'Unavailable':fmt(count)}</td><td class="num">${count==null?'Unavailable':fmt(count*100/Math.max(1,x.officialBarangays))}</td></tr>`}).join('')||'<tr><td colspan="8">No MPB PSGC matches at this level.</td></tr>'}}renderFacilityTables();const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const densitySelect=document.getElementById('density-facility'),densityLabels={schools:'Public-tagged school candidates',health:'Public-tagged health candidates',evacuation:'Evacuation candidates'};function renderDensity(){const regions=d.geographyRows.filter(inLevel);const key=densitySelect.value,label=densityLabels[key],rows=regions.map(x=>({name:x.name,mpb:Number(x.mpbRows||0)*100/Math.max(1,Number(x.officialBarangays||0)),facility:Number(x.facilityCounts?.[key]||0)*100/Math.max(1,Number(x.officialBarangays||0))})).sort((a,b)=>b.mpb-a.mpb).slice(0,20);const max=Math.max(1,...rows.flatMap(x=>[x.mpb,x.facility]));document.getElementById('density-facility-legend').textContent=label;document.getElementById('density-facility-header').textContent=label.replace('Public-tagged ','').replace('candidates','candidates')+' / 100 barangays';document.getElementById('density-region-chart').innerHTML=rows.map(x=>`<div class="density-row" role="listitem" title="${esc(x.name)} · MPB ${x.mpb.toFixed(1)} rows/100 barangays · ${esc(label)} ${x.facility.toFixed(1)}/100 barangays"><span class="density-place">${esc(x.name)}</span><span class="density-bar"><i style="width:${Math.max(0,Math.min(100,x.mpb/max*100))}%"></i><b>${x.mpb.toFixed(1)}</b></span><span class="density-bar facility"><i style="width:${Math.max(0,Math.min(100,x.facility/max*100))}%"></i><b>${geoLevel==='barangay'?'N/A':x.facility.toFixed(1)}</b></span></div>`).join('');const totalBarangays=regions.reduce((a,x)=>a+Number(x.officialBarangays||0),0),mpbTotal=regions.reduce((a,x)=>a+Number(x.mpbRows||0),0),facilityTotal=regions.reduce((a,x)=>a+Number(x.facilityCounts?.[key]||0),0);document.getElementById('density-summary').textContent=geoLevel==='barangay'?'Barangay facility counts are unavailable in the source layer. The chart shows MPB rows only, up to 20 places ranked by MPB rate.':`Across selected places: ${ (mpbTotal*100/Math.max(1,totalBarangays)).toFixed(1) } MPB project rows and ${(facilityTotal*100/Math.max(1,totalBarangays)).toFixed(1)} ${label.toLowerCase()} per 100 official barangays.`}densitySelect.addEventListener('change',renderDensity);renderDensity();const rows=d.geographyRows;function draw(){const level=geoLevel,q=document.getElementById('geo-search').value.trim().toLowerCase();const list=rows.filter(x=>(x.level===level||(level==='municipality'&&x.level==='city'))&&(!q||[x.name,x.region,x.province].join(' ').toLowerCase().includes(q)));const rate=document.getElementById('heuristic-metric').value==='rate',value=(x,n)=>rate?n*100/Math.max(1,x.officialBarangays):n,series=[['school','School','#0038a8'],['health','Health','#008b74'],['evacuation','Evacuation','#d47a00'],['other','Other','#697a8b']],count=(x,key)=>key==='other'?Math.max(0,x.mpbRows-x.heuristicAny):(x.heuristics?.[key]?.rows||0),top=[...list].sort((a,b)=>value(b,b.mpbRows)-value(a,a.mpbRows)||a.name.localeCompare(b.name)).slice(0,20),max=Math.max(1,...top.flatMap(x=>series.map(([key])=>value(x,count(x,key)))));document.getElementById('heuristic-summary').textContent=`${fmt(list.length)} places match · showing ${fmt(top.length)} in the chart · ${rate?'rows per 100 official barangays':'project rows'}.`;document.getElementById('heuristic-chart').innerHTML=top.map(x=>`<div class="heuristic-chart-row" role="listitem"><div><strong>${esc(x.name)}</strong><small>${esc([x.province,x.region].filter(Boolean).join(' · '))}</small></div><div class="heuristic-series">${series.map(([key,label,color])=>{const n=value(x,count(x,key));return `<div class="heuristic-bar-row"><span>${label}</span><div class="heuristic-track"><i style="width:${n/max*100}%;background:${color}"></i></div><b>${rate?n.toFixed(1):fmt(n)}</b></div>`}).join('')}</div></div>`).join('')||'<p>No locations match.</p>';document.getElementById('heuristic-rows').innerHTML=list.map(x=>{const h=x.heuristics||{},school=h.school?.rows||0,health=h.health?.rows||0,evac=h.evacuation?.rows||0;return `<tr><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(school)}</td><td class="num">${fmt(health)}</td><td class="num">${fmt(evac)}</td><td class="num">${fmt(Math.max(0,x.mpbRows-x.heuristicAny))}</td></tr>`}).join('')||'<tr><td colspan="7">No locations match.</td></tr>'}document.querySelectorAll('[data-level]').forEach(button=>button.addEventListener('click',()=>{geoLevel=button.dataset.level;renderFacilityTables();renderDensity();document.querySelectorAll('[data-level]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));draw()}));document.getElementById('heuristic-metric').addEventListener('change',draw);document.getElementById('geo-search').addEventListener('input',draw);draw()}).catch(e=>{document.querySelector('main').insertAdjacentHTML('beforeend',`<p class="notice">MPB data could not be loaded: ${e.message}</p>`)})
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
