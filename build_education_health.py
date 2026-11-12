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
:root{--ink:#142b3b;--muted:#566b79;--line:#d8e1e7;--blue:#0038a8;--gold:#f5c542;--bg:#f5f8fa}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1200px;margin:auto;padding:28px 20px 80px}.eyebrow{font-weight:750;letter-spacing:.1em;color:var(--blue);font-size:.78rem}h1{font-size:clamp(2rem,4vw,3.3rem);line-height:1.08;margin:.35rem 0 1rem}h2{margin:.1rem 0 .6rem;font-size:1.5rem}h3{margin:0 0 .5rem}.lede{max-width:800px;color:var(--muted)}.section{margin:24px 0;padding:24px;background:white;border:1px solid var(--line);border-radius:15px;box-shadow:0 3px 12px #17334a0a}.kicker{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--blue);font-weight:750}.notice{border-left:4px solid var(--gold);padding:12px 15px;background:#fff9e7;border-radius:5px;color:#394b57}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}.controls select,.controls input{font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:white}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f4f7f9;position:sticky;top:0}.num{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:9px}.small{font-size:.88rem;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.status{padding:14px;background:#f6f8fa;border:1px solid var(--line);border-radius:10px}.status strong{display:block;margin-bottom:4px}.pill{display:inline-block;border-radius:20px;padding:3px 9px;background:#eaf0ff;color:#173c82;font-size:.78rem;font-weight:700}.footer{font-size:.86rem;color:var(--muted);margin-top:20px}.chart-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:14px;margin-top:16px}.chart-panel{min-width:0;padding:16px;border:1px solid var(--line);border-radius:12px;background:#fbfcfd}.chart-panel h3{font-size:1.05rem}.chart-note{margin:0 0 12px;color:var(--muted);font-size:.84rem}.bar-chart{display:grid;gap:8px}.bar-row{display:grid;grid-template-columns:minmax(100px,155px) minmax(50px,1fr) minmax(72px,auto);align-items:center;gap:9px;font-size:.82rem}.bar-label{overflow-wrap:anywhere;line-height:1.25}.bar-track{height:13px;overflow:hidden;border-radius:99px;background:#e9eef2}.bar-fill{height:100%;border-radius:inherit;background:#0038a8}.bar-fill.school{background:#0038a8}.bar-fill.health{background:#008b74}.bar-fill.evacuation{background:#d47a00}.bar-value{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:650}.chart-empty{color:var(--muted);font-size:.88rem}@media(max-width:560px){.bar-row{grid-template-columns:minmax(88px,120px) minmax(35px,1fr) minmax(65px,auto);gap:6px;font-size:.76rem}.chart-panel{padding:12px}} @media(max-width:700px){main{padding:20px 12px}.section{padding:16px}table{font-size:.84rem}}
 </style></head><body><main><div class="eyebrow">MPB · PUBLIC SERVICE ACCESS</div><h1>MPB vs schools, health facilities and evacuation centers</h1><p class="lede">Compare FY2027 House Bill MPB allocations with mapped public-service facility candidates joined to PSGC administrative areas.</p><div class="notice"><b>Coverage:</b> facility counts use an OpenStreetMap snapshot downloaded 4 November 2026. Schools and health facilities are included only when public or government status is explicitly tagged. Evacuation candidates need an explicit evacuation or displaced-shelter tag. This map layer is incomplete and is not an official inventory.</div>
<section class="section" id="regional-charts"><div class="kicker">Regional overview</div><h2>FY2027 MPB rows and mapped facility candidates by region</h2><p class="small">These charts summarize regional records. The MPB chart counts House Bill project rows; facility charts show partial public-tagged OpenStreetMap candidates per 100 official barangays. Facility rates are not official inventory coverage, and missing mapped candidates do not establish facility absence.</p><div class="chart-grid"><figure class="chart-panel"><figcaption><h3>MPB project rows</h3><p class="chart-note">All FY2027 House Bill MPB rows joined to PSGC regions.</p></figcaption><div class="bar-chart" id="mpb-region-chart" role="list" aria-label="FY2027 MPB project rows by region"></div></figure><figure class="chart-panel"><figcaption><h3>Public-tagged school candidates</h3><p class="chart-note">Top 10 regions by mapped candidates per 100 official barangays.</p></figcaption><div class="bar-chart" id="school-region-chart" role="list" aria-label="Mapped public-tagged school candidates per 100 barangays by region"></div></figure><figure class="chart-panel"><figcaption><h3>Public-tagged health candidates</h3><p class="chart-note">Top 10 regions by mapped candidates per 100 official barangays.</p></figcaption><div class="bar-chart" id="health-region-chart" role="list" aria-label="Mapped public-tagged health candidates per 100 barangays by region"></div></figure><figure class="chart-panel"><figcaption><h3>Evacuation candidates</h3><p class="chart-note">Top 10 regions by mapped candidates per 100 official barangays.</p></figcaption><div class="bar-chart" id="evacuation-region-chart" role="list" aria-label="Mapped evacuation candidates per 100 barangays by region"></div></figure></div></section>
<section class="section" id="schools"><div class="kicker">01 · Schools</div><h2>MPB density vs mapped public-school candidates</h2><p>Counts include mapped school features with explicit public or government operator/ownership tags. Facility points join to municipality/city PSGC by unique municipality name and region; totals roll up to province and region. Barangay-level school counts are not inferred.</p><div class="grid" id="school-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped public-tagged schools</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="school-rows"></tbody></table></div></section>
<section class="section" id="health"><div class="kicker">02 · Health</div><h2>MPB density vs mapped public health candidates</h2><p>Counts include mapped hospitals, clinics and health posts with explicit public or government operator/ownership tags. Private and unclassified facilities are excluded; this OSM subset is incomplete and has not been checked against the DOH NHFR.</p><div class="grid" id="health-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped public-tagged facilities</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="health-rows"></tbody></table></div></section>
<section class="section" id="evacuation"><div class="kicker">03 · Evacuation centers</div><h2>MPB density vs mapped evacuation candidates</h2><p>Counts include features explicitly tagged as evacuation centers or shelters for displaced people. These mapped candidates are not a complete or currently validated LGU/OCD inventory.</p><div class="grid" id="evacuation-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Mapped evacuation candidates</th><th class="num">Candidates / 100 barangays*</th></tr></thead><tbody id="evacuation-rows"></tbody></table></div></section>
<section class="section" id="heuristics"><div class="kicker">04 · Title-only heuristics</div><h2>Title-only heuristic: MPB vs schools, health and evacuation</h2><p>These counts flag MPB titles containing relevant words. A keyword does not prove the building’s use. One project can appear in more than one category.</p><div class="controls"><label>Geography <select id="geo-level"><option value="region">Region</option><option value="province">Province</option><option value="municipality">Municipality / city</option><option value="barangay">Barangay</option></select></label><input id="geo-search" type="search" placeholder="Filter place"></div><div class="table-wrap"><table><thead><tr><th>Place</th><th>Region</th><th>Province</th><th class="num">School title hits</th><th class="num">Health title hits</th><th class="num">Evacuation title hits</th><th class="num">Other MPB rows</th></tr></thead><tbody id="heuristic-rows"></tbody></table></div><p class="small">Keyword rules use title text only: school/classroom/education/college/university; health/hospital/clinic/medical/infirmary/birthing/RHU; evacuation/evac. Other means no hit in these title-only word groups.</p></section>
<p class="footer">*Denominator: official barangay count for the reporting geography; MPB rate is project rows per 100 barangays, not buildings or expenditure. Facilities join at municipality/city PSGC and roll up to provinces and regions; barangay-level facility totals are not available. The OSM source layer contains mapped candidates only, and blank or untagged locations are not evidence that a facility is absent. <a href="connectivity-public-services-data.json">Download the mapped public-service source layer</a> · <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors · ODbL</a>.</p></main><script>
fetch('education-health-data.json').then(r=>r.json()).then(d=>{const fmt=n=>Number(n||0).toLocaleString('en-PH');const levels={municipality:'Municipality / city',city:'City',province:'Province',region:'Region'};const facilities=d.facilityInventories;const tableIds={schools:'school-rows',health:'health-rows',evacuation:'evacuation-rows'};for(const [key,id] of Object.entries(tableIds)){const facility=facilities[key];document.getElementById(key==='schools'?'school-status':key==='health'?'health-status':'evacuation-status').innerHTML=`<div class="status"><strong>${fmt(facility.joinedRows)} mapped candidates joined</strong><span class="pill">OSM · partial</span><p class="small">${facility.status}</p><p class="small">${fmt(facility.unmatchedRows)} candidate points could not be matched to a unique PSGC municipality.</p></div>`;const list=d.geographyRows.filter(x=>['municipality','city','province','region'].includes(x.level));document.getElementById(id).innerHTML=list.map(x=>{const count=x.facilityCounts[key]??0;return `<tr><td>${levels[x.level]||x.level}</td><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(x.mpbRows)}</td><td class="num">${fmt(x.mpbRows*100/Math.max(1,x.officialBarangays))}</td><td class="num">${fmt(count)}</td><td class="num">${fmt(count*100/Math.max(1,x.officialBarangays))}</td></tr>`}).join('')||'<tr><td colspan="8">No MPB PSGC matches at this level.</td></tr>'}const esc=s=>String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const regions=d.geographyRows.filter(x=>x.level==='region');function renderBars(id,items,maxValue,color,valueText){const el=document.getElementById(id);el.innerHTML=items.length?items.map(x=>`<div class="bar-row" role="listitem" title="${esc(x.name)}: ${esc(valueText(x))}"><span class="bar-label">${esc(x.name)}</span><span class="bar-track"><span class="bar-fill ${color}" style="display:block;width:${Math.max(0,Math.min(100,x.value/Math.max(1,maxValue)*100))}%"></span></span><span class="bar-value">${esc(valueText(x))}</span></div>`).join(''):'<p class="chart-empty">No regional records available.</p>'}const mpbBars=regions.map(x=>({name:x.name,value:x.mpbRows})).sort((a,b)=>b.value-a.value);renderBars('mpb-region-chart',mpbBars,mpbBars[0]?.value||1,'',x=>fmt(x.value)+' rows');for(const [key,id,color] of [['schools','school-region-chart','school'],['health','health-region-chart','health'],['evacuation','evacuation-region-chart','evacuation']]){const bars=regions.map(x=>{const count=x.facilityCounts?.[key]||0;return {name:x.name,count,value:count*100/Math.max(1,x.officialBarangays)}}).filter(x=>x.count>0).sort((a,b)=>b.value-a.value).slice(0,10);renderBars(id,bars,bars[0]?.value||1,color,x=>`${x.value.toFixed(1)} · ${fmt(x.count)}`)}const rows=d.geographyRows;function draw(){const level=document.getElementById('geo-level').value,q=document.getElementById('geo-search').value.trim().toLowerCase();const list=rows.filter(x=>x.level===level&&(!q||[x.name,x.region,x.province].join(' ').toLowerCase().includes(q)));document.getElementById('heuristic-rows').innerHTML=list.map(x=>{const h=x.heuristics||{},school=h.school?.rows||0,health=h.health?.rows||0,evac=h.evacuation?.rows||0;return `<tr><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(school)}</td><td class="num">${fmt(health)}</td><td class="num">${fmt(evac)}</td><td class="num">${fmt(Math.max(0,x.mpbRows-x.heuristicAny))}</td></tr>`}).join('')||'<tr><td colspan="7">No locations match.</td></tr>'}document.getElementById('geo-level').addEventListener('change',draw);document.getElementById('geo-search').addEventListener('input',draw);draw()}).catch(e=>{document.querySelector('main').insertAdjacentHTML('beforeend',`<p class="notice">MPB data could not be loaded: ${e.message}</p>`)})
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
