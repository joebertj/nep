#!/usr/bin/env python3
"""Build MPB comparisons with public school/health/evacuation facilities."""
import csv
import json
import re
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
    return {'fiscalYear': 2027, 'stage': 'House Bill', 'mpbProjectRows': len(records), 'geographyRows': rows,
            'facilityInventories': {
                'schools': {'count': None, 'status': 'Official public-school point inventory not present in the project inputs; exclude records without verified public status.'},
                'health': {'count': None, 'status': 'DOH public-facility registry export not present in the project inputs; public ownership filter required.'},
                'evacuation': {'count': None, 'status': 'No complete, geocoded national public evacuation-center inventory present in the project inputs.'}},
            'method': 'MPB row counts use FY2027 House Bill line records assigned to PSGC places. MPB density is shown as project rows per 100 official barangays where coverage exists. Facility densities are withheld until verifiable public-only inventories can be joined. Heuristic labels inspect title text only; they are not confirmed building uses.'}


def build_page(data):
    (OUT / DATA).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    (STATIC / DATA).parent.mkdir(parents=True, exist_ok=True)
    (STATIC / DATA).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MPB vs Schools, Health and Evacuation Facilities</title><style>
:root{--ink:#142b3b;--muted:#566b79;--line:#d8e1e7;--blue:#0038a8;--gold:#f5c542;--bg:#f5f8fa}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}main{max-width:1200px;margin:auto;padding:28px 20px 80px}.eyebrow{font-weight:750;letter-spacing:.1em;color:var(--blue);font-size:.78rem}h1{font-size:clamp(2rem,4vw,3.3rem);line-height:1.08;margin:.35rem 0 1rem}h2{margin:.1rem 0 .6rem;font-size:1.5rem}h3{margin:0 0 .5rem}.lede{max-width:800px;color:var(--muted)}.section{margin:24px 0;padding:24px;background:white;border:1px solid var(--line);border-radius:15px;box-shadow:0 3px 12px #17334a0a}.kicker{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--blue);font-weight:750}.notice{border-left:4px solid var(--gold);padding:12px 15px;background:#fff9e7;border-radius:5px;color:#394b57}.controls{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}.controls select,.controls input{font:inherit;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:white}table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}th{background:#f4f7f9;position:sticky;top:0}.num{text-align:right;font-variant-numeric:tabular-nums}.table-wrap{overflow:auto;max-height:520px;border:1px solid var(--line);border-radius:9px}.small{font-size:.88rem;color:var(--muted)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.status{padding:14px;background:#f6f8fa;border:1px solid var(--line);border-radius:10px}.status strong{display:block;margin-bottom:4px}.pill{display:inline-block;border-radius:20px;padding:3px 9px;background:#eaf0ff;color:#173c82;font-size:.78rem;font-weight:700}.footer{font-size:.86rem;color:var(--muted);margin-top:20px} @media(max-width:700px){main{padding:20px 12px}.section{padding:16px}table{font-size:.84rem}}
</style></head><body><main><div class="eyebrow">MPB · PUBLIC SERVICE ACCESS</div><h1>MPB vs schools, health facilities and evacuation centers</h1><p class="lede">Compare FY2027 House Bill MPB allocations with public service locations as soon as an authoritative public-only facility inventory is available. This page separates mapped MPB evidence from facility data coverage and title-based purpose clues.</p><div class="notice"><b>Data coverage:</b> the project currently has no downloadable official public-only school, health-facility or national evacuation-center inventory. Facility counts and facility density are therefore not fabricated. MPB counts below use project locations matched to PSGC.</div>
<section class="section" id="schools"><div class="kicker">01 · Schools</div><h2>MPB density vs public-school density</h2><p>Granularity available for MPB: barangay, municipality/city, province and region. Public-school density is pending a verified public school inventory with coordinates or PSGC identifiers.</p><div class="grid" id="school-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Public schools</th><th class="num">Schools / 100 barangays*</th></tr></thead><tbody id="school-rows"></tbody></table></div></section>
<section class="section" id="health"><div class="kicker">02 · Health</div><h2>MPB density vs public health-facility density</h2><p>Target facility types: government hospitals, rural health units or urban health centers, and barangay health stations. Private facilities should be excluded using the DOH registry ownership classification.</p><div class="grid" id="health-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Public facilities</th><th class="num">Facilities / 100 barangays*</th></tr></thead><tbody id="health-rows"></tbody></table></div></section>
<section class="section" id="evacuation"><div class="kicker">03 · Evacuation centers</div><h2>MPB density vs public evacuation-center density</h2><p>Evacuation centers must be purpose-designated facilities or centers identified in LGU/DRRM inventories. Police and fire stations are not treated as evacuation centers.</p><div class="grid" id="evacuation-status"></div><div class="table-wrap"><table><thead><tr><th>Level</th><th>Place</th><th>Region</th><th>Province</th><th class="num">MPB rows</th><th class="num">MPB rows / 100 barangays*</th><th class="num">Public evacuation centers</th><th class="num">Centers / 100 barangays*</th></tr></thead><tbody id="evacuation-rows"></tbody></table></div></section>
<section class="section" id="heuristics"><div class="kicker">04 · Title-only heuristics</div><h2>Title-only heuristic: MPB vs schools, health and evacuation</h2><p>These counts flag MPB titles containing relevant words. A keyword does not prove the building’s use. One project can appear in more than one category.</p><div class="controls"><label>Geography <select id="geo-level"><option value="region">Region</option><option value="province">Province</option><option value="municipality">Municipality / city</option><option value="barangay">Barangay</option></select></label><input id="geo-search" type="search" placeholder="Filter place"></div><div class="table-wrap"><table><thead><tr><th>Place</th><th>Region</th><th>Province</th><th class="num">School title hits</th><th class="num">Health title hits</th><th class="num">Evacuation title hits</th><th class="num">Other MPB rows</th></tr></thead><tbody id="heuristic-rows"></tbody></table></div><p class="small">Keyword rules use title text only: school/classroom/education/college/university; health/hospital/clinic/medical/infirmary/birthing/RHU; evacuation/evac. Other means no hit in these title-only word groups.</p></section>
<p class="footer">*Denominator: official barangay count for the reporting geography; MPB rate is project rows per 100 barangays, not buildings or expenditure. MPB locations come from the current House Bill row inventory and are limited to records with a PSGC place assignment. Facility sources to connect: DepEd school geolocations; DOH National Health Facility Registry with government ownership filter; LGU/DRRM evacuation-center inventories. OSM venue points are not used as public facilities because public ownership is not consistently verified.</p></main><script>
fetch('education-health-data.json').then(r=>r.json()).then(d=>{const fmt=n=>Number(n||0).toLocaleString('en-PH');const levels={barangay:'Barangay',municipality:'Municipality / city',city:'City',province:'Province',region:'Region'};const facility=d.facilityInventories;for(const [key,label] of [['schools','Public school inventory'],['health','Public health inventory'],['evacuation','Evacuation-center inventory']])document.getElementById(key==='schools'?'school-status':key==='evacuation'?'evacuation-status':key+'-status').innerHTML=`<div class="status"><strong>${label}</strong><span class="pill">Not yet joined</span><p class="small">${facility[key].status}</p></div>`;const rows=d.geographyRows;const geographyCount=r=>r.level==='barangay'?1:null;const group=(container,level)=>{const data=rows.filter(x=>x.level===level);container.innerHTML=data.map(x=>`<tr><td>${levels[x.level]||x.level}</td><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(x.mpbRows)}</td><td class="num">${fmt(x.mpbRows*100/Math.max(1,x.officialBarangays))}</td><td class="num">Pending</td><td class="num">Pending</td></tr>`).join('')||'<tr><td colspan="8">No MPB PSGC matches at this level.</td></tr>'};for(const [id,level] of [['school-rows','barangay'],['health-rows','barangay'],['evacuation-rows','barangay']]){const el=document.getElementById(id);const list=rows.filter(x=>['barangay','municipality','city','province','region'].includes(x.level));el.innerHTML=list.map(x=>`<tr><td>${levels[x.level]||x.level}</td><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(x.mpbRows)}</td><td class="num">${fmt(x.mpbRows*100/Math.max(1,x.officialBarangays))}</td><td class="num">Pending</td><td class="num">Pending</td></tr>`).join('')};function draw(){const level=document.getElementById('geo-level').value,q=document.getElementById('geo-search').value.trim().toLowerCase();const list=rows.filter(x=>x.level===level&&(!q||[x.name,x.region,x.province].join(' ').toLowerCase().includes(q)));document.getElementById('heuristic-rows').innerHTML=list.map(x=>{const h=x.heuristics||{},school=h.school?.rows||0,health=h.health?.rows||0,evac=h.evacuation?.rows||0;return `<tr><td>${x.name}</td><td>${x.region||'—'}</td><td>${x.province||'—'}</td><td class="num">${fmt(school)}</td><td class="num">${fmt(health)}</td><td class="num">${fmt(evac)}</td><td class="num">${fmt(Math.max(0,x.mpbRows-x.heuristicAny))}</td></tr>`}).join('')||'<tr><td colspan="7">No locations match.</td></tr>'}document.getElementById('geo-level').addEventListener('change',draw);document.getElementById('geo-search').addEventListener('input',draw);draw()}).catch(e=>{document.querySelector('main').insertAdjacentHTML('beforeend',`<p class="notice">MPB data could not be loaded: ${e.message}</p>`)})
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
