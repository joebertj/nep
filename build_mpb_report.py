#!/usr/bin/env python3
"""Build a standalone MPB report from existing audited stage comparisons."""
import csv
import hashlib
import json
import re
import subprocess
import unicodedata
from urllib.parse import quote
from collections import Counter, defaultdict
from pathlib import Path
from report_hero_module import STYLE
from hgab_matching import UNMATCHED, is_fap
from uniform_report_menu import apply_share_build_meta

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
TAILWIND_VERSION = hashlib.sha256((ROOT.parent / 'open-data-visualization/static/css/tailwind.css').read_bytes()).hexdigest()[:12]
CATEGORY = 'BIP - Multi-Purpose Buildings/ Facilities to support Social Services'
LEG_PROFILE_SOURCE = ROOT / 'data_sources/csiiiv/legislative_profiles_ff0f748.json'
CSIIIV_CITY_SEAT_ALIASES = {
    'bacolod': 'BACOLOD CITY', 'baguio': 'BAGUIO CITY', 'butuan': 'BUTUAN CITY',
    'cagayan de oro': 'CAGAYAN DE ORO CITY', 'calamba': 'CITY OF CALAMBA',
    'cotabato': 'NORTH COTABATO', 'general santos': 'GENERAL SANTOS CITY',
    'iligan': 'ILIGAN CITY', 'las pinas': 'CITY OF LAS PIÑAS',
    'malabon': 'MALABON CITY', 'mandaluyong': 'CITY OF MANDALUYONG',
    'mandaue': 'MANDAUE CITY', 'manila': 'MANILA CITY',
    'muntinlupa': 'CITY OF MUNTINLUPA', 'navotas': 'NAVOTAS CITY',
    'paranaque': 'CITY OF PARAÑAQUE', 'pasay': 'PASAY CITY', 'pasig': 'PASIG CITY',
    'san jose del monte': 'CITY OF SAN JOSE DEL MONTE', 'san juan': 'SAN JUAN CITY',
    'taguig': 'TAGUIG CITY', 'valenzuela': 'VALENZUELA CITY',
}


def _key(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def _leg_profile_index():
    payload = json.loads(LEG_PROFILE_SOURCE.read_text())
    index = {}
    for seat in payload['districts']:
        index[(_key(seat['jurisdiction']), _key(seat['districtLabel']))] = seat
    return payload['source'], index


def _representative_cards(attribution, profile_index, source):
    districts = attribution.get('districts') or []
    representatives = attribution.get('representatives') or []
    cards = []
    for i, district in enumerate(districts):
        parts = district.split(' · ')
        if len(parts) != 2:
            cards.append({'district': district, 'name': representatives[i] if len(representatives) == len(districts) else None,
                          'resolutionStatus': 'district_label_unresolved'})
            continue
        jurisdiction = CSIIIV_CITY_SEAT_ALIASES.get(_key(parts[0]), parts[0])
        designation = re.sub(r'\s+district$', '', parts[1], flags=re.I)
        seat = profile_index.get((_key(jurisdiction), _key(designation)))
        local_name = representatives[i] if len(representatives) == len(districts) else None
        if not seat:
            cards.append({'district': district, 'name': local_name, 'resolutionStatus': 'no_exact_csiiiv_seat_match'})
            continue
        candidates = []
        for candidate in seat.get('candidates', []):
            candidate_photo = candidate.get('photoFile')
            candidates.append({'name': candidate.get('name'), 'profileUrl': candidate.get('detailUrl'),
                'photoUrl': 'https://raw.githubusercontent.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/' +
                    quote(source['commit']) + '/DEO2LEG/legislative_profiles/photos/' + quote(candidate_photo) if candidate_photo else None})
        photo_file = seat.get('photoFile')
        cards.append({'district': district, 'name': local_name or seat.get('representative'),
            'officialName': seat.get('representative'), 'resolutionStatus': seat.get('resolutionStatus'),
            'profileUrl': seat.get('detailUrl'),
            'photoUrl': 'https://raw.githubusercontent.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/' +
                quote(source['commit']) + '/DEO2LEG/legislative_profiles/photos/' + quote(photo_file) if photo_file else None,
            'candidates': candidates})
    return cards


def _coordinate_resolve_leg_districts(rows, attribution):
    """Resolve unresolved seats only when coordinates fit both named admin and LEG polygons."""
    from analyze_mpb_proximity import place as parse_place, coordinates as parse_coordinates, utm51_to_wgs84, point_in_rings
    municipal_path = ROOT / 'data_sources/arcgis_dpwh/archive/selected/city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
    leg_path = ROOT / 'data_sources/arcgis_dpwh/archive/selected/congressional_districts/layers/Congressional_District_FeatureServer_0-277792f6/features.jsonl'
    if not municipal_path.exists() or not leg_path.exists():
        return
    pending = []
    for row in rows:
        project_id = row.get('hgab_id')
        current = attribution.get(project_id) or {}
        place = parse_place(row.get('projectName', ''))
        point = parse_coordinates(row.get('projectName', ''))
        if current.get('districts') or not place.get('key') or len(place['key']) != 3 or point.get('status') != 'Usable printed point':
            continue
        province, municipality, _barangay = place['key']
        pending.append((row, current, province, municipality, point))
    if not pending:
        return

    def read_shapes(path, kind):
        shapes = []
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                feature = json.loads(line)
                attrs = feature.get('attributes', {})
                if kind == 'municipality':
                    name = attrs.get('MUN_DBM') or attrs.get('MUNICIPAL')
                    province = attrs.get('PROV_DBM') or attrs.get('PROVINCE')
                else:
                    name = attrs.get('CONG_DIST')
                    province = attrs.get('PROVINCE')
                raw_rings = feature.get('geometry', {}).get('rings', [])
                rings = [[utm51_to_wgs84(*vertex[:2]) for vertex in ring] for ring in raw_rings if len(ring) >= 4]
                if name and province and rings:
                    shapes.append((attrs, _key(name), _key(province), rings))
        return shapes

    municipality_shapes = read_shapes(municipal_path, 'municipality')
    leg_shapes = read_shapes(leg_path, 'leg')
    ordinal_districts = {
        'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th',
        'fifth': '5th', 'sixth': '6th', 'seventh': '7th', 'eighth': '8th',
        'ninth': '9th', 'tenth': '10th', 'lone': 'Lone',
    }
    for row, current, province, municipality, point in pending:
        point_in = {'latitude': point['latitude'], 'longitude': point['longitude']}
        named_places = [shape for shape in municipality_shapes
                        if shape[1] == municipality and shape[2] == province
                        and point_in_rings(point_in, shape[3])]
        if len(named_places) != 1:
            continue
        district_shapes = [shape for shape in leg_shapes
                           if shape[2] == province and point_in_rings(point_in, shape[3])]
        district_names = {shape[1] for shape in district_shapes}
        if len(district_names) != 1:
            continue
        raw_district = str(district_shapes[0][0].get('CONG_DIST') or '')
        parsed = re.fullmatch(r'\s*(.*?)\s*\(\s*([A-Za-z]+)\s+District\s*\)\s*', raw_district, re.I)
        if not parsed:
            continue
        district_number = ordinal_districts.get(parsed.group(2).lower())
        if not district_number:
            continue
        jurisdiction = parsed.group(1).strip()
        resolved = dict(current)
        resolved['districts'] = [f'{jurisdiction} · {district_number} District']
        resolved['representatives'] = []
        resolved['status'] = 'resolved from printed coordinate inside matching municipality and unique legislative district boundaries'
        resolved['geographicEvidence'] = list(current.get('geographicEvidence') or []) + [{
            'basis': 'Printed coordinate falls inside the title-matched municipality polygon and exactly one congressional district polygon',
            'district': raw_district,
            'municipality': municipality,
            'province': province,
            'coordinateRaw': point.get('raw'),
            'boundarySource': 'Archived DPWH ArcGIS municipality and congressional district layers; effective dates unverified',
        }]
        attribution[row['hgab_id']] = resolved


def _render_metric_rows(metrics):
    """Accessible bars; every count keeps its denominator and unit visible."""
    rows = []
    for label, count, denominator, note in metrics:
        percent = (100 * count / denominator) if denominator else 0
        rows.append(f'<div class="mpb-flag-row"><div class="mpb-flag-label"><strong>{label}</strong>'
                    f'<span>{note}</span></div><div class="mpb-flag-track" role="img" aria-label="{count:,} of {denominator:,}, {percent:.1f} percent">'
                    f'<span style="width:{min(100, percent):.1f}%"></span></div>'
                    f'<div class="mpb-flag-value"><strong>{count:,}</strong><span>of {denominator:,} · {percent:.1f}%</span></div></div>')
    return ''.join(rows)


def _render_mpb_flag_chart(summary):
    hgab = int(summary['hgabLines'])
    metrics = [
        ('Potential insertion candidates', int(summary['insertionCandidates']), hgab,
         'No plausible NEP counterpart identified by the current match; review the source pages.'),
        ('Ambiguous NEP counterpart', int(summary['ambiguousLines']), hgab,
         'A possible or competing counterpart needs scope review.'),
        ('Allocation adjustment records', int(summary['adjustedLines']), hgab,
         'Selected one-to-one matches show a change; these can overlap the ambiguous review.'),
        ('Historical repeat comparison', int(summary['historicalRepeatProjects']), hgab,
         'At least one historical GAA comparison is linked to this project; one project can have comparisons in multiple years.'),
    ]
    return ('<section id="mpb-review-flags" class="card"><h2>MPB review flags · overview</h2>'
            '<p>These are different review queues, not a single corruption score. Bars show each count against its stated denominator; categories can overlap and should not be added together. A flag is a prompt for human review, not a finding.</p>'
            f'<div class="mpb-flag-group"><h3>Bill-stage comparison</h3>{_render_metric_rows(metrics)}</div></section>')


def _publish_mpb_historical_page(periods=None):
    """Publish classified historical DPWH allocations for four project types."""
    source = STATIC / 'integrated-project-data.json'
    integrated = json.loads(source.read_text(encoding='utf-8'))
    category_map = {'Flood control': 'Flood Control', 'Multi-purpose building': 'MPB', 'Road': 'Roads', 'Bridge': 'Bridges'}
    grouped = defaultdict(lambda: {'projectCount': 0, 'allocationPesos': 0})
    for row in integrated.get('projects', []):
        if row.get('stage') != 'GAA' or row.get('category') not in category_map: continue
        try: year, amount = int(row.get('year') or 0), int(float(row.get('amountPesos') or 0))
        except (TypeError, ValueError): continue
        if not year: continue
        key = (year, category_map[row['category']])
        grouped[key]['projectCount'] += 1
        grouped[key]['allocationPesos'] += amount
    import re
    site_signal_rules = [
        ('Subdivision named', re.compile(r'\bsubdivision\b', re.I)),
        ('HOA named', re.compile(r'\bHOA\b|homeowners?\s*(?:association|assoc)', re.I)),
        ('Village named · weak location cue', re.compile(r'\bvillage\b', re.I)),
        ('Explicit private-land wording', re.compile(r'\bprivate(?:ly)?\b|private\s+(?:land|lot|property)', re.I)),
        ('Land/lot transaction wording', re.compile(r'\b(?:land|lot)\s+(?:acquisition|purchase|donation|donated|leased|owned)\b', re.I)),
    ]
    site_rows = []
    for row in integrated.get('projects', []):
        if row.get('category') != 'Multi-purpose building': continue
        year, stage, title = int(row.get('year') or 0), str(row.get('stage') or ''), str(row.get('name') or '')
        if not (stage == 'GAA' and 2015 <= year <= 2026 or year == 2027 and stage == 'HGAB 3rd'): continue
        signals = [label for label, pattern in site_signal_rules if pattern.search(title)]
        if signals:
            site_rows.append({'year': year, 'stage': stage, 'title': title, 'signals': signals,
                              'amountPesos': int(float(row.get('amountPesos') or 0)), 'source': str(row.get('source') or '')})
    site_rows.sort(key=lambda x: (-x['amountPesos'], x['year'], x['title']))
    site_payload = {'scope': 'FY2015–FY2026 enacted GAA and FY2027 HGAB 3rd reading; title cues only.', 'rows': site_rows,
                    'method': 'MPB title screen. Village is a weak location cue and does not establish ownership.'}
    site_serialized = json.dumps(site_payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (STATIC / 'mpb-site-indicators-data.json', OUT / 'mpb-site-indicators-data.json'):
        path.write_text(site_serialized, encoding='utf-8')
    categories = ['Flood Control', 'MPB', 'Roads', 'Bridges']
    years = sorted({year for year, _ in grouped})
    payload = {'source': 'integrated-project-data.json', 'method': 'GAA-stage classified DPWH project rows grouped by fiscal year and source category.', 'years': years, 'categories': categories,
        'rows': [{'year': year, 'projectType': category, **grouped.get((year, category), {'projectCount': 0, 'allocationPesos': 0})} for year in years for category in categories]}
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    version = hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:12]
    for path in (STATIC / 'historical-allocations-data.json', OUT / 'historical-allocations-data.json'): path.write_text(serialized, encoding='utf-8')
    page = f'''<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Historical allocations · BetterGov</title>
<style>body{{margin:0;background:#eef3f4;color:#18303b;font:16px/1.5 system-ui,sans-serif}}header{{background:#142e3b;color:white;padding:24px 2vw}}h1{{margin:0;font-size:30px}}main{{padding:24px 2vw;max-width:none}}section.card{{background:white;border:1px solid #ccdcd8;border-radius:14px;padding:24px;margin:24px 0}}h2{{margin-top:0}}a{{color:#087e78}}.controls{{display:flex;align-items:center;gap:10px;margin:16px 0}}select{{font:inherit;padding:8px;border:1px solid #aebdca;border-radius:8px;background:white}}.chart{{display:grid;gap:8px;margin:16px 0 22px}}.bar-row{{display:grid;grid-template-columns:70px minmax(80px,1fr) minmax(130px,auto);align-items:center;gap:10px}}.track{{height:13px;background:#e7edf2;border-radius:20px;overflow:hidden}}.fill{{height:100%;background:linear-gradient(90deg,#0038a8,#168c86)}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere}}th{{background:#edf4f2}}.num{{text-align:right;white-space:nowrap}}.note{{color:#526773}}@media(max-width:650px){{th,td{{font-size:12px;padding:6px}}section.card{{padding:14px}}.bar-row{{grid-template-columns:52px minmax(50px,1fr) minmax(95px,auto);font-size:12px}}}}</style></head><body><header><h1>Historical DPWH allocations</h1><p>Classified GAA allocations for Flood Control, MPB, Roads and Bridges</p></header><main>
<section class=\"card\"><h2>Annual allocation by project type</h2><p>Counts and listed allocations use the integrated DPWH GAA project dataset. Categories follow that dataset's classification; this is not a complete account of every DPWH budget line. Allocations are not spending.</p><div class=\"controls\"><label for=\"type\">Project type</label><select id=\"type\"><option>Flood Control</option><option>MPB</option><option>Roads</option><option>Bridges</option></select></div><div id=\"chart\" class=\"chart\" aria-label=\"Annual allocation chart\"></div><div class=\"table-wrap\"><table><thead><tr><th>Fiscal year</th><th>Project type</th><th class=\"num\">Classified project rows</th><th class=\"num\">Listed allocation</th></tr></thead><tbody id=\"rows\"><tr><td colspan=\"4\">Loading historical allocations…</td></tr></tbody></table></div><p><a href=\"contractors.html?type=MPB\">Browse MPB contractors →</a></p><p class=\"note\">Source: integrated-project-data.json · GAA-stage DPWH rows · <a href=\"historical-allocations-data.json\" download>Download grouped data</a>.</p></section>
</main><script>fetch('historical-allocations-data.json?v={version}').then(r=>{{if(!r.ok)throw Error(r.status);return r.json()}}).then(d=>{{const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x),type=document.getElementById('type'),rows=document.getElementById('rows'),chart=document.getElementById('chart');function draw(){{const items=d.rows.filter(x=>x.projectType===type.value),max=Math.max(1,...items.map(x=>Number(x.allocationPesos||0)));rows.innerHTML=items.map(x=>'<tr><td>FY'+Number(x.year)+'</td><td>'+x.projectType+'</td><td class=\"num\">'+n(x.projectCount)+'</td><td class=\"num\">'+peso(x.allocationPesos)+'</td></tr>').join('')||'<tr><td colspan=\"4\">No rows for this category.</td></tr>';chart.innerHTML=items.map(x=>'<div class=\"bar-row\"><strong>FY'+Number(x.year)+'</strong><span class=\"track\"><span class=\"fill\" style=\"display:block;width:'+Math.max(0,Math.min(100,100*Number(x.allocationPesos||0)/max))+'%\"></span></span><span class=\"num\">'+peso(x.allocationPesos)+'</span></div>').join('')||'<p class=\"note\">No allocation values available.</p>'}}type.addEventListener('change',draw);draw()}}).catch(e=>{{document.getElementById('rows').innerHTML='<tr><td colspan=\"4\">Historical allocation data unavailable: '+String(e.message)+'</td></tr>'}});</script></body></html>'''
    site_section = '''<section class="card" id="mpb-site-indicators"><h2>MPB sites with subdivision, village or private-land cues</h2><p class="note">FY2015–FY2026 enacted GAA and FY2027 HGAB 3rd-reading MPB titles. “Village” is a weaker location cue; no title signal proves private ownership or restricted access. Verify title, donation, authorization and public purpose against source documents.</p><p id="mpb-site-summary" aria-live="polite">Loading…</p><div class="controls"><label for="mpb-site-year">Year</label><select id="mpb-site-year"><option value="all">All years</option></select><label for="mpb-site-search">Project</label><input id="mpb-site-search" type="search" placeholder="Search title or source" style="font:inherit;padding:8px;min-width:220px"></div><div class="table-wrap"><table data-report-table-exempt="true"><thead><tr><th>Year / stage</th><th>Project title</th><th>Title cue</th><th class="num">Allocation</th><th>Source</th></tr></thead><tbody id="mpb-site-rows"></tbody></table></div><div class="controls"><button id="mpb-site-prev" type="button">Previous</button><span id="mpb-site-page"></span><button id="mpb-site-next" type="button">Next</button></div><p class="note">Separate screening data: <a href="mpb-site-indicators-data.json" download>download JSON</a>.</p></section>'''
    page = page.replace('</main>', site_section + '</main>', 1)
    site_script = '''<script>fetch('mpb-site-indicators-data.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{const rows=d.rows,year=document.getElementById('mpb-site-year'),search=document.getElementById('mpb-site-search'),body=document.getElementById('mpb-site-rows'),summary=document.getElementById('mpb-site-summary'),pageLabel=document.getElementById('mpb-site-page'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));[...new Set(rows.map(x=>x.year))].sort((a,b)=>a-b).forEach(y=>year.add(new Option(`FY${y}`,y)));const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x);let page=0;function draw(){const q=search.value.trim().toLowerCase(),filtered=rows.filter(x=>(year.value==='all'||String(x.year)===year.value)&&(!q||`${x.title} ${x.source} ${x.signals.join(' ')}`.toLowerCase().includes(q))),size=25,pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages-1);const shown=filtered.slice(page*size,(page+1)*size),total=filtered.reduce((a,x)=>a+Number(x.amountPesos||0),0),village=filtered.filter(x=>x.signals.some(y=>y.startsWith('Village')));summary.textContent=`${n(filtered.length)} project lines · ${peso(total)} listed allocation; ${n(village.length)} have the weaker village cue (${peso(village.reduce((a,x)=>a+Number(x.amountPesos||0),0))}). Title screens are not ownership findings.`;body.innerHTML=shown.map(x=>`<tr><td>FY${x.year}<br>${esc(x.stage)}</td><td>${esc(x.title)}</td><td>${x.signals.map(esc).join('<br>')}</td><td class="num">${peso(x.amountPesos)}</td><td>${esc(x.source||'Source detail unavailable')}</td></tr>`).join('')||'<tr><td colspan="5">No title-screen matches.</td></tr>';pageLabel.textContent=`${filtered.length?page*size+1:0}–${Math.min((page+1)*size,filtered.length)} of ${filtered.length} · Page ${page+1} of ${pages}`;document.getElementById('mpb-site-prev').disabled=page===0;document.getElementById('mpb-site-next').disabled=page>=pages-1}year.addEventListener('change',()=>{page=0;draw()});search.addEventListener('input',()=>{page=0;draw()});document.getElementById('mpb-site-prev').onclick=()=>{page--;draw()};document.getElementById('mpb-site-next').onclick=()=>{page++;draw()};draw()}).catch(e=>{document.getElementById('mpb-site-summary').textContent='MPB title-screen data unavailable: '+e.message});</script>'''
    page = page.replace('</body>', site_script + '</body>', 1)
    from review_report_language import NOTICE
    from build_investigation_summary import CSS as EVIDENCE_CSS
    page = page.replace('<main>', '<main>' + NOTICE, 1).replace('</head>', EVIDENCE_CSS + '</head>', 1)
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    page = apply_uniform_menu_page(page, 'mpb-historical.html')
    from report_table_presentation import publish_assets, apply_page as apply_report_styles
    page = apply_report_styles(page, publish_assets())
    for path in (STATIC / 'mpb-historical.html', OUT / 'mpb-historical.html'): path.write_text(page, encoding='utf-8')

def _render_location_checks(proximity):
    location = proximity.get('summary', {})
    boundary_denominator = int(location.get('coordinateAuditQualifiedMatched', 0))
    printed_points = int(location.get('hgabLinesWithUsablePoint', 0))
    coordinate_pairs = len(proximity.get('current', []))
    close_pairs = sum(float(row.get('distanceMeters') or 0) < 50 for row in proximity.get('current', []))
    metrics = [
        ('Outside-boundary review queue', int(location.get('coordinateAuditOutside', 0)), boundary_denominator,
         'Printed coordinate needs checking against the named city or municipality boundary.'),
        ('No qualified boundary match', int(location.get('coordinateAuditUnmatched', 0)), printed_points,
         'A printed point exists, but its locality could not be matched to a qualified boundary.'),
        ('Same-barangay pairs under 50 m apart', close_pairs, coordinate_pairs,
         'A close pair may share a site or describe separate nearby work; check project scope.'),
    ]
    return ('<section id="mpb-location-checks" class="card"><h2>Location checks</h2>'
            '<p>Boundary checks appear first. Each bar uses its own stated denominator; location flags are review leads and do not show that a project is misplaced or duplicated.</p>'
            f'<div class="mpb-flag-group">{_render_metric_rows(metrics)}</div>'
            f'<nav class="mpb-location-jumps" aria-label="MPB location review links"><a href="#mpb-map-canvas">Open the locations map and project card ↗</a>'
            f'<a href="#mpb-outside-boundary-queue">Review all {int(location.get("coordinateAuditOutside", 0)):,} outside-boundary entries ↓</a></nav></section>')


def _map_share_payload(proximity, boundary_path):
    """Prepare one stable share-image record for every selectable locality map."""
    boundary_data = json.loads(boundary_path.read_text())
    boundaries = {feature['municipalityGroup']: feature for feature in boundary_data.get('features', [])}
    grouped = defaultdict(list)
    for row in proximity.get('current', []):
        name = row.get('municipalityGroup')
        if not name:
            parts = str(row.get('barangay') or '').split(' · ')
            name = ' · '.join(parts[1:]) if len(parts) >= 3 else 'Municipality unresolved'
        grouped[name].append(row)

    def inside(lon, lat, rings):
        result = False
        for ring in rings:
            for i, point in enumerate(ring):
                previous = ring[i - 1]
                xi, yi = point; xj, yj = previous
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    result = not result
        return result

    cards, share_pages = [], {}
    for name, rows in sorted(grouped.items()):
        digest = hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]
        slug = re.sub(r'[^a-z0-9]+', '-', unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()).strip('-')[:48].strip('-')
        slug = f'{slug or "locality"}-{digest}'
        points_by_key = {}
        pair_cards = []
        for row in rows:
            point_keys = []
            for side, source_key, title_key, coord_key in (
                ('left', 'sourceLabel', 'projectName', 'leftCoordinates'),
                ('right', 'otherSource', 'otherProject', 'rightCoordinates')):
                source = str(row.get(source_key) or '')
                title = str(row.get(title_key) or '')
                coord = row.get(coord_key) or {}
                try:
                    lat, lon = float(coord['latitude']), float(coord['longitude'])
                except (KeyError, TypeError, ValueError):
                    point_keys.append(None); continue
                key = source + '\n' + title
                if key not in points_by_key:
                    rings = (boundaries.get(name) or {}).get('rings') or []
                    points_by_key[key] = {'id': key, 'name': title,
                        'lon': lon, 'lat': lat, 'inside': inside(lon, lat, rings) if rings else True}
                point_keys.append(key)
            if all(point_keys):
                pair_cards.append({'left': point_keys[0], 'right': point_keys[1],
                                   'distance': float(row.get('distanceMeters') or 0)})
        boundary = boundaries.get(name) or {}
        cards.append({'slug': slug, 'groupName': name, 'title': name.title().replace(' · ', ' · '),
                      'points': list(points_by_key.values()), 'pairs': pair_cards,
                      'rings': boundary.get('rings') or []})
        share_pages[name] = f'mpb-map-share/{slug}.html'
    return cards, share_pages


def _write_map_share_pages(cards, share_pages):
    share_dir = STATIC / 'mpb-map-share'
    share_dir.mkdir(parents=True, exist_ok=True)
    image_base = 'https://research.bettergov.ph/static/nep-preview/mpb-map-share/'
    page_base = 'https://research.bettergov.ph/static/nep-preview/mpb-map-share/'
    versioned_pages = {}
    for card in cards:
        slug, title = card['slug'], card['title']
        image = share_dir / f'{slug}.png'
        version = hashlib.sha256(image.read_bytes()).hexdigest()[:12]
        image_url = image_base + image.name + '?v=' + version
        interactive = '../mpb.html?place=' + quote(next(name for name, path in share_pages.items() if path.endswith(slug + '.html')), safe='') + '#mpb-coordinate-proximity'
        page_url = page_base + slug + '.html?v=' + version
        versioned_pages[card['groupName']] = 'mpb-map-share/' + slug + '.html?v=' + version
        safe_title = title.replace('&', '&amp;').replace('<', '&lt;').replace('"', '&quot;')
        description = f'MPB project locations and same-site comparisons in {safe_title}. Listed coordinates and municipal boundary checks are review leads, not findings.'
        html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPB project locations · {safe_title}</title><meta name="description" content="{description}"><meta property="og:type" content="website"><meta property="og:url" content="{page_url}"><meta property="og:title" content="MPB project locations · {safe_title}"><meta property="og:description" content="{description}"><meta property="og:image" content="{image_url}"><meta property="og:image:secure_url" content="{image_url}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="Map of MPB project coordinates and the municipal boundary for {safe_title}"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="MPB project locations · {safe_title}"><meta name="twitter:description" content="{description}"><meta name="twitter:image" content="{image_url}"><link id="bettergov-tailwind-style" rel="stylesheet" href="../../css/tailwind.css?v={TAILWIND_VERSION}"><style>body{{margin:0;padding:28px;background:#eef3f4;color:#18303b;font:16px/1.5 system-ui,sans-serif}}main{{max-width:1200px;margin:auto}}.share-disclaimer{{display:block;margin:18px 0;padding:12px 16px;border-left:4px solid #FCD116;background:#fff;color:#18303b;border-radius:8px;font-size:14px;line-height:1.55}}img{{display:block;width:100%;height:auto;border-radius:14px}}a{{display:inline-block;margin-top:16px;padding:10px 15px;border-radius:8px;background:#087e78;color:white;text-decoration:none;font-weight:700}}</style><link rel="stylesheet" href="../report-disclaimer.css?v=20261029-disclaimer1"></head><body><main><h1>MPB project locations · {safe_title}</h1><img src="{image.name}" width="1200" height="630" alt="Map of listed project coordinates and municipality boundary"><a href="{interactive}">Open interactive map and project details ↗</a><p>Proposed allocations. Location signals are review leads, not findings.</p><aside class="share-disclaimer report-disclaimer" role="note"><p><strong>Scope.</strong> This card shows a municipality-level map and funding comparison for listed multi-purpose building projects. Printed points and nearby sites require source and scope verification.</p><strong>Disclaimer.</strong> These are preliminary, document-based observations, not allegations or findings that any person, office, contractor or other entity acted unlawfully. A flag, unmatched record, repeated amount or title, price or location outlier, or missing document is a prompt for review; it does not establish intent, responsibility, benefit, overpayment, duplicate scope or wrongdoing. Names and geographic or district associations indicate possible coverage only, not sponsorship, authorship, control, receipt or personal involvement. Source documents, data completeness, parsing, matching, categories, timing and boundaries may affect results. Verify cited primary records and seek relevant context before drawing or publishing conclusions. This site is updated as additional source documents are ingested and reviewed. Its records and calculations are preliminary and open to correction. Additional documents, stakeholder input, and independent review can surface missing information, errors, or context and improve accuracy over time; they may support more complete calculations but do not by themselves verify a record. Inviting people to examine the underlying sources and share corrections is part of the purpose of this work.</aside></main></body></html>'''
        from report_table_presentation import apply_bettergov_palette
        html = apply_bettergov_palette(html)
        (share_dir / f'{slug}.html').write_text(apply_share_build_meta(html))
    return versioned_pages


def build():
    from analyze_mpb_proximity import build as build_proximity,render as render_proximity
    proximity=build_proximity()
    inputs = ['hb_nep_comparison_3rd.csv', 'nep_dpwh_baseline.json',
              'dpwh_removals_3rd.json', 'repeat_nep_hgab_survival.json',
              'congress_geographic_attribution_db_3rd.json', 'dpwh-in-depth-data.json']
    with (OUT / inputs[0]).open() as f:
        rows = [r for r in csv.DictReader(f) if r['pap3'] == CATEGORY]
    attribution={r['id']:r for r in json.loads((OUT/inputs[4]).read_text())['projects']}
    # A printed point inside an administrative-district polygon can resolve a
    # title-only locality that the general DEO/LEG matcher does not recognize.
    ordinal_districts = {
        'first': '1st', 'second': '2nd', 'third': '3rd', 'fourth': '4th',
        'fifth': '5th', 'sixth': '6th', 'seventh': '7th', 'eighth': '8th',
        'ninth': '9th', 'tenth': '10th',
    }
    for match in proximity.get('coordinateAuditDistrictMatches', []):
        raw_district = str(match.get('congressionalDistrict') or '')
        parsed = re.fullmatch(r'\s*(.*?)\s*\(\s*([A-Za-z]+)\s+District\s*\)\s*', raw_district, re.I)
        if not parsed:
            continue
        district_number = ordinal_districts.get(parsed.group(2).lower())
        if not district_number:
            continue
        jurisdiction = re.sub(r'\s+City$', '', parsed.group(1), flags=re.I).strip()
        current = attribution.get(match.get('projectId'))
        if not current or current.get('districts'):
            continue
        resolved = dict(current)
        resolved['districts'] = [f'{jurisdiction} · {district_number} District']
        resolved['representatives'] = []
        resolved['status'] = 'resolved from printed coordinate inside named city-district boundary'
        resolved['geographicEvidence'] = list(current.get('geographicEvidence') or []) + [{
            'basis': 'Printed coordinate falls inside the named city-district polygon',
            'district': raw_district,
            'boundarySource': match.get('boundarySource'),
            'coordinateRaw': match.get('coordinateRaw'),
        }]
        attribution[match['projectId']] = resolved
    _coordinate_resolve_leg_districts(rows, attribution)
    transparency_snapshot=json.loads((OUT/inputs[5]).read_text())
    transparency_by_code={p.get('code'):p for p in transparency_snapshot.get('projects',[]) if p.get('code')}
    profile_source, profile_index = _leg_profile_index()
    survival = json.loads((OUT / inputs[3]).read_text())
    repeats = [r for r in survival['comparisonPairs'] if r['category'] == 'Multi-purpose building']
    base_data_path = OUT / 'mpb-barangay-data.json'
    barangay_periods = json.loads(base_data_path.read_text()).get('periods', []) if base_data_path.exists() else []
    historical_gaa_baseline = [p for p in barangay_periods if int(p.get('year') or 0) in (2015, 2016, 2017, 2018, 2019)]
    repeat_years = defaultdict(set)
    for repeat in repeats:
        repeat_years[repeat.get('source_code')].add(str(repeat.get('comparison_year')))
    close_pairs = defaultdict(list)
    for pair in proximity.get('current', []):
        if float(pair.get('distanceMeters') or 0) >= 50:
            continue
        left_id = pair.get('sourceLabel', '').split(' · ', 1)[0]
        right_id = pair.get('otherSource', '').split(' · ', 1)[0]
        close_pairs[left_id].append({'distanceMeters': pair.get('distanceMeters'), 'otherProject': pair.get('otherProject')})
        close_pairs[right_id].append({'distanceMeters': pair.get('distanceMeters'), 'otherProject': pair.get('projectName')})
    boundary_reviews = {r.get('projectId'): r for r in proximity.get('coordinateAudit', []) if r.get('projectId')}
    unresolved_boundary_reviews = {r.get('projectId'): r for r in proximity.get('coordinateAuditUnresolvedProjects', []) if r.get('projectId')}
    project_details = {}
    from analyze_mpb_proximity import place as parse_place, coordinates as parse_coordinates
    for row in rows:
        project_id = row['hgab_id']
        geo = attribution.get(project_id, {})
        location = parse_place(row['projectName'])
        point = parse_coordinates(row['projectName'])
        comparison = row.get('comparison', '')
        transparency_project=transparency_by_code.get(row.get('nep_api_id'))
        transparency_links=[{'type':d.get('type') or d.get('kind') or 'Document','url':d.get('url')}
                            for d in (transparency_project or {}).get('documentLinks',[])
                            if str(d.get('url') or '').startswith('https://')]
        insertion_status = ('Insertion candidate · no NEP counterpart' if comparison == UNMATCHED and not is_fap(row) else
                            'Exact normalized title found in NEP' if comparison == 'Exact normalized title found in NEP' else
                            'Counterpart review needed')
        review_flags = []
        if comparison == UNMATCHED and not is_fap(row):
            review_flags.append({'label': 'Potential insertion', 'detail': 'No plausible NEP counterpart identified by the current match.'})
        elif comparison not in (UNMATCHED, 'Exact normalized title found in NEP'):
            review_flags.append({'label': 'Ambiguous NEP counterpart', 'detail': 'A possible or competing counterpart needs scope review.'})
        delta = int(float(row.get('amount_delta_pesos') or 0))
        if row.get('paired_one_to_one') == 'True' and delta:
            review_flags.append({'label': 'Allocation changed between readings',
                                 'detail': f"{delta:+,} pesos from NEP to HGAB 3rd reading."})
        years = sorted(repeat_years.get(row.get('nep_api_id'), set()))
        if years:
            review_flags.append({'label': 'Historical repeat comparison', 'detail': 'Compared with GAA year(s): ' + ', '.join(years) + '.'})
        boundary = boundary_reviews.get(project_id)
        if boundary:
            distance = float(boundary.get('outsideBoundaryKm') or 0)
            review_flags.append({'label': 'Location boundary review',
                'detail': f"Printed coordinate is about {distance:,.1f} km from the named boundary."})
        unresolved_boundary = unresolved_boundary_reviews.get(project_id)
        if unresolved_boundary:
            if project_id == 'HB10858-3-0920-015927':
                # Manual map review by the project researcher places this printed
                # point at or very near the San Jose, Dinagat Islands boundary.
                # The barangay identity and which side of the generalized map
                # boundary it falls on remain unresolved.
                review_flags.append({'label': 'Location boundary review · point at boundary',
                    'detail': 'Manual map review places the printed coordinate at or very near the mapped San Jose, Dinagat Islands boundary. Available coordinate and polygon data do not establish which side it falls on; barangay identity remains unverified.'})
            else:
                review_flags.append({'label': 'Location boundary match unresolved',
                    'detail': 'A printed point could not be confidently matched to a named municipal boundary.'})
        for pair in close_pairs.get(project_id, []):
            review_flags.append({'label': 'Same-barangay pair under 50 m',
                'detail': f"{float(pair.get('distanceMeters') or 0):,.0f} m from {pair.get('otherProject', 'another listed project with the same barangay label')}."})
        project_details[project_id] = {
            'projectName': row['projectName'], 'office': row.get('office'), 'region': row.get('region'),
            'amountPesos': int(float(row['amountPesos'])), 'sourceVolume': row.get('sourceVolume'),
            'sourcePage': row.get('sourcePage'), 'insertionStatus': insertion_status,
            'transparencyLinks': transparency_links,
            'place': location.get('label'), 'placeEvidence': location.get('status'),
            'coordinate': point if point.get('status') == 'Usable printed point' else None,
            'reviewFlags': review_flags,
            'legAttributionStatus': geo.get('status', 'unresolved'),
            'representativeCards': _representative_cards(geo, profile_index, profile_source),
        }
    proximity['projectDetails'] = project_details
    proximity['representativeProfileSource'] = profile_source
    share_boundaries = STATIC / 'mpb-municipality-boundaries.json'
    share_cards, share_pages = _map_share_payload(proximity, share_boundaries)
    proximity['sharePages'] = share_pages
    proximity_json = json.dumps(proximity, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'mpb_proximity.json').write_text(proximity_json)
    (STATIC / 'mpb-proximity.json').write_text(proximity_json)
    share_card = STATIC / 'mpb-share-card.png'
    swift_cache = Path('/private/tmp/odv-swift-module-cache')
    swift_cache.mkdir(parents=True, exist_ok=True)
    subprocess.run(['swift', '-module-cache-path', str(swift_cache), str(ROOT / 'build_mpb_share_card.swift'),
                    str(OUT / 'mpb_proximity.json'), str(share_boundaries), str(share_card)],
                   check=True, capture_output=True, text=True)
    map_payload_path = Path('/private/tmp/mpb-local-map-share-cards.json')
    map_payload_path.write_text(json.dumps(share_cards, ensure_ascii=False))
    share_dir = STATIC / 'mpb-map-share'
    subprocess.run(['swift', '-module-cache-path', str(swift_cache), str(ROOT / 'build_mpb_local_share_cards.swift'),
                    str(map_payload_path), str(share_dir)], check=True, capture_output=True, text=True)
    share_pages = _write_map_share_pages(share_cards, share_pages)
    proximity['sharePages'] = share_pages
    proximity_json = json.dumps(proximity, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'mpb_proximity.json').write_text(proximity_json)
    (STATIC / 'mpb-proximity.json').write_text(proximity_json)
    share_image_url = 'https://research.bettergov.ph/static/nep-preview/mpb-share-card.png?v=' + hashlib.sha256(share_card.read_bytes()).hexdigest()[:12]
    for row in rows:
        for key in ['amountPesos', 'amount_delta_pesos', 'closest_nep_amount_pesos']:
            row[key] = int(float(row[key])) if row[key] else None
        row['representatives'] = '; '.join(attribution.get(row['hgab_id'], {}).get('representatives', []))
        row['legDistricts'] = '; '.join(attribution.get(row['hgab_id'], {}).get('districts', []))
        row['buildingType'] = ('Evacuation center' if 'evacuation' in row['projectName'].lower() else
                               'School / educational facility' if any(w in row['projectName'].lower() for w in ('school', 'classroom', 'college', 'university')) else
                               'Other / unspecified building')
    insertions = [r for r in rows if r['comparison'] == UNMATCHED and not is_fap(r)]
    ambiguous = [r for r in rows if r['comparison'] not in (UNMATCHED, 'Exact normalized title found in NEP')]
    adjustments = [r for r in rows if r['paired_one_to_one'] == 'True' and r['amount_delta_pesos'] not in (None, 0)]
    baseline = json.loads((OUT / inputs[1]).read_text())['data']['data']
    mpb_ids = {r['id'] for r in baseline if r['pap3'] == CATEGORY}
    removals = [r for r in json.loads((OUT / inputs[2]).read_text())['domestic']['rows'] if r['nepId'] in mpb_ids]
    prices = []
    groups = defaultdict(list)
    for row in rows:
        groups[(row['buildingType'], row['amountPesos'])].append(row)
    for (kind, amount), group in groups.items():
        prices.append({'buildingType': kind, 'amountPesos': amount, 'projects': len(group),
                       'totalPesos': amount * len(group), 'offices': len({r['office'] for r in group})})
    distribution = []
    offices = defaultdict(list)
    for row in rows:
        offices[(row['region'], row['office'])].append(row)
    for (region, office), group in offices.items():
        added = [r for r in group if r in insertions]
        distribution.append({'region': region, 'office': office, 'projects': len(group),
                             'amountPesos': sum(r['amountPesos'] for r in group),
                             'insertionCount': len(added), 'insertionPesos': sum(r['amountPesos'] for r in added)})
    summary = {'hgabLines': len(rows), 'hgabPesos': sum(r['amountPesos'] for r in rows),
               'insertionCandidates': len(insertions), 'insertionPesos': sum(r['amountPesos'] for r in insertions),
               'ambiguousLines': len(ambiguous), 'ambiguousPesos': sum(r['amountPesos'] for r in ambiguous),
               'repeatPairs': len(repeats), 'repeatProposals': len({r['source_code'] for r in repeats}),
               'historicalRepeatProjects': sum(1 for detail in project_details.values()
                                               if any(flag['label'] == 'Historical repeat comparison'
                                                      for flag in detail['reviewFlags'])),
               'removalCandidates': len(removals), 'removalPesos': sum(r['nepPesos'] for r in removals),
               'adjustedLines': len(adjustments)}
    data = {'category': CATEGORY, 'summary': summary,
            'insertions': insertions, 'ambiguous': ambiguous,
            'adjustments': adjustments, 'removals': removals, 'repeats': repeats, 'prices': prices,
            'distribution': distribution,'coordinateProximity':proximity,
            'sources': [{'file': name, 'sha256': hashlib.sha256((OUT / name).read_bytes()).hexdigest()} for name in inputs] +
                       ([{'file': str(base_data_path.name),
                          'sha256': hashlib.sha256(base_data_path.read_bytes()).hexdigest()}]
                        if base_data_path.exists() else []) +
                       [{'file': str(LEG_PROFILE_SOURCE.relative_to(ROOT)), 'sha256': hashlib.sha256(LEG_PROFILE_SOURCE.read_bytes()).hexdigest()}]}
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'mpb_analysis.json').write_text(serialized)
    (STATIC / 'mpb-data.json').write_text(serialized)
    _publish_mpb_historical_page(historical_gaa_baseline)
    html = PAGE.replace('__HERO_STYLE__', STYLE).replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
    proximity_section=render_proximity(proximity,keys=('current',))
    share_controls='''<div id="mpbMapActions" class="mpb-map-actions"><a id="mpbMapFacebook" aria-label="Share this map on Facebook" href="https://www.facebook.com/sharer/sharer.php?u=https%3A%2F%2Fresearch.bettergov.ph%2Fstatic%2Fnep-preview%2Fmpb.html%23mpb-coordinate-proximity" target="_blank" rel="noopener"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="#1877F2" d="M24 12.073C24 5.405 18.627 0 12 0S0 5.405 0 12.073c0 6.019 4.388 11.018 10.125 11.927v-8.437H7.078v-3.49h3.047V9.41c0-3.025 1.792-4.697 4.533-4.697 1.312 0 2.686.236 2.686.236v2.979h-1.513c-1.49 0-1.955.93-1.955 1.884v2.261h3.328l-.532 3.49h-2.796V24C19.612 23.091 24 18.092 24 12.073Z"/></svg><span>FB</span></a><a id="mpbMapDownload" href="#" download aria-label="Download locality map image"><span>PNG</span></a><button id="mpbMapNativeShare" type="button" aria-label="Share locality map image" hidden><span>Share</span></button><button id="mpbMapCopyLink" type="button" aria-label="Copy map share link"><svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="currentColor" d="M10.59 13.41a1.996 1.996 0 0 0 2.82 0l3-3a2 2 0 0 0-2.82-2.82l-1.72 1.72-1.41-1.41 1.72-1.72a4 4 0 1 1 5.66 5.66l-3 3a4 4 0 0 1-5.66 0l-.59-.59 1.41-1.41.59.57ZM13.41 10.59a1.996 1.996 0 0 0-2.82 0l-3 3a2 2 0 1 0 2.82 2.82l1.72-1.72 1.41 1.41-1.72 1.72a4 4 0 1 1-5.66-5.66l3-3a4 4 0 0 1 5.66 0l.59.59-1.41 1.41-.59-.57Z"/></svg><span>Copy</span></button><span id="mpbMapShareStatus" aria-live="polite"></span></div>'''
    proximity_section=proximity_section.replace('<div id="mpbMunicipalityPlot"></div>','<div id="mpb-map-canvas" class="mpb-map-canvas"><div id="mpbMunicipalityPlot"></div><div id="mpbMapProjectCard" class="mpb-map-project-card" hidden></div></div>',1)
    proximity_section=proximity_section.replace('<div class="mpb-map-canvas">','<p class="note">The selected project card appears beside the map. Select another point or project title to inspect its details.</p><div class="mpb-map-canvas">',1)
    proximity_section=proximity_section.replace('</div><div class="mpb-map-legend">','</div>'+share_controls+'<div class="mpb-map-legend">',1)
    flagged_overview=_render_mpb_flag_chart(summary)
    location_checks=_render_location_checks(proximity)
    html=html.replace('<div id="hero"></div>','<div id="hero"></div>'+flagged_overview+location_checks+proximity_section+'<p><a href="mpb-historical.html">Compare historical DPWH allocations by project type →</a></p><p><a href="out-of-place.html">Map all coordinate-bearing DEO/LEG project entries →</a></p><p><a href="repeats.html#hgab-historical-gaa">HGAB projects with historical GAA title matches →</a></p>')
    html=html.replace('</head>','<link rel="stylesheet" href="mpb-location-map.css?v=20261027-native-share-27"></head>')
    html=html.replace('<meta name="viewport" content="width=device-width,initial-scale=1">','<meta name="viewport" content="width=device-width,initial-scale=1"><meta property="og:type" content="website"><meta property="og:url" content="https://research.bettergov.ph/static/nep-preview/mpb.html"><meta property="og:title" content="DPWH multi-purpose building locations and funding"><meta property="og:description" content="Explore FY2027 multi-purpose building locations, same-site comparisons, project details, and geographic legislative district associations."><meta property="og:image" content="'+share_image_url+'"><meta property="og:image:secure_url" content="'+share_image_url+'"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="Map of listed FY2027 multi-purpose building project coordinates across Philippine municipal boundaries"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="DPWH multi-purpose building locations and funding"><meta name="twitter:description" content="Explore FY2027 multi-purpose building locations, same-site comparisons, and project details."><meta name="twitter:image" content="'+share_image_url+'">')
    map_version=hashlib.sha256((STATIC/'mpb-location-map.js').read_bytes()).hexdigest()[:12]
    html=html.replace('</body>',f'<script src="mpb-location-map.js?v={map_version}"></script></body>')
    from review_report_language import NOTICE
    from build_investigation_summary import CSS as EVIDENCE_CSS
    html=re.sub(r'(<main\b[^>]*>)',lambda m:m[0]+NOTICE,html,count=1)
    html=html.replace('</head>',EVIDENCE_CSS+'</head>',1)
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    html=apply_uniform_menu_page(html,'mpb.html')
    from report_table_presentation import publish_assets,apply_page as apply_report_styles
    html=apply_report_styles(html,publish_assets())
    from build_investigation_summary import JS as evidence_exports
    html=html.replace('</body>',evidence_exports+'</body>')
    (STATIC / 'mpb.html').write_text(html)
    (OUT / 'mpb.html').write_text(html)
    return data


PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPB · Multi-purpose building allocations · FY2027</title>
<style>body{margin:0;background:#eef3f4;color:#18303b;font:16px/1.5 system-ui,sans-serif}header{background:#142e3b;color:white;padding:24px 2vw}h1{margin:0;font-size:30px}main{padding:24px 2vw;max-width:none}section.card{background:white;border:1px solid #ccdcd8;border-radius:14px;padding:24px;margin:24px 0}h2{margin-top:0}a{color:#087e78}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.controls input,.controls select,.controls button{font:inherit;padding:8px;border:1px solid #a8bbb6;border-radius:8px}.export{background:#b65b09;color:white;font-weight:700}.controls input{flex:1;min-width:180px}table{width:100%;table-layout:fixed;border-collapse:collapse}th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;white-space:normal}th{background:#edf4f2}figure{margin:16px 0}svg{display:block;width:100%;height:auto;max-height:420px}.note{color:#526773}.caution{padding:14px;background:#fff4dd;border-left:4px solid #ba7800}@media(max-width:650px){th,td{font-size:12px;padding:6px}section.card{padding:14px}}</style>__HERO_STYLE__</head><body><header><h1>MPB · Multi-purpose building allocations</h1><p>FY2027 NEP → HGAB 3rd reading</p></header><main>
<div id="hero"></div>
<section class="card"><h2>What this page measures</h2><p>This page covers the BIP multi-purpose buildings/facilities PAP, including records named as evacuation centers. Category membership follows the parsed PAP, not a keyword search across every DPWH program. Titles, pages and amounts are retained from the current comparison.</p><p class="caution">Potential insertions have no plausible NEP counterpart identified by the current matching. They are review candidates, not certified new amendments. Ambiguous matches are separate. Budget amounts are appropriations, not expenditures or personal receipts; no finding establishes misconduct.</p><p><a href="mpb-data.json" download>Download complete analysis JSON</a> · <a href="dpwh-hgab.html">Full DPWH comparison and matching methodology</a></p></section>
<div id="sections"></div>
<section class="card"><h2>Supporting methodology and limitations</h2><ul><li>Insertion screening uses the same current native NEP/HGAB occurrence matching as the DPWH HGAB page. FAPs are excluded from domestic insertion candidates. A selected one-to-one counterpart is required for an allocation adjustment; approximate title similarity alone does not establish one.</li><li>Removal candidates are unpaired NEP records in this exact PAP. An absent selected link is not proof of deletion. Changes in wording, office, scope or aggregation can hide counterparts.</li><li>Repeat comparisons are FY2027 NEP versus available prior-year enacted GAA. The same NEP project can appear in multiple comparison years: comparison pairs and distinct proposals are different denominators. The loaded comparison set covers FY2016–FY2018 and FY2020–FY2026. FY2016–FY2018 is a separate title-classified DPWH project-family baseline; FY2019 named-project detail is unavailable. FY2000–2008 is partial/aggregate-only; FY2001/2004/2006 had no new GAA; FY2009–FY2015 is unavailable or unreconciled. Those years are excluded from repeat counts. HGAB retention follows selected links; a missing link is not a confirmed removal.</li><li>Directions, tranches and explicit chainage remain part of the inherited repeat screen. Repeated building names do not establish duplicate components or paid work. Barangay/town/province homonyms require qualified geographic evidence.</li><li>Building types are a simple title-based descriptive split. Other/unspecified includes mixed uses and titles without clear purpose. Equal allocation amounts are not equal unit costs: floor area, design, quantities and site conditions are unavailable.</li><li>Office totals are administrative allocations, not legislative district totals. Names in project tables come from existing strict PH location DB attribution; blank cells mean unresolved or shared coverage. No name determines screening eligibility.</li><li>Graphs reflect the current table filters. Ranked project and office graphs show up to 12 rows; table counts and CSV include all filtered rows. Repeat graphs count all filtered comparison pairs by retention status. No hypothesis test or corruption probability is inferred from these descriptive plots.</li></ul><p>Request original-page adjudication, approved designs, floor areas, bills of quantities, contracts, project completion and disbursement records before drawing conclusions. MPB findings overlap the full DPWH insertion and repeat findings; their amounts must not be added together.</p><h3>Sources and reproducibility</h3><p>Local FY2027 NEP DPWH baseline; HB 10858 3rd-reading Volume I-C; native comparison/removal records; historical GAA repeat screen; PH location DB strict attribution. <a href="mpb-data.json">Analysis JSON</a> records each input filename and SHA256. Source pages are listed per project. All monetary exports contain numeric pesos.</p></section>
</section><section class="card" id="mpb-land-site-review"><h2>Subdivision, village and private-land title indicators</h2><p class="note">Title-based screening cues only. A subdivision or HOA title is not proof of private ownership. “Village” is a weaker location cue: Philippine law uses “subdivision/village” together, but that label alone does not establish title, restricted access, or ineligibility for public funding. Confirm land title, public access, authorization, donation/easement and project purpose against source documents.</p><p id="mpb-land-site-summary" aria-live="polite"></p><div style="overflow-x:auto"><table><thead><tr><th>Project title</th><th>Title indicator</th><th>Listed location</th><th class="num">HGAB allocation</th><th>Source evidence</th></tr></thead><tbody id="mpb-land-site-rows"></tbody></table></div></section>
</main><script id="mpb-data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('mpb-data').textContent),S=D.summary;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+num(v),short=v=>'₱'+(v/1e9).toFixed(2)+'B';
document.getElementById('hero').innerHTML=`<section class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">MPB · NEP → HGAB 3rd reading</span><div class="repeat-hero-total"><strong>${num(S.insertionCandidates)}</strong><span>potential insertion candidates</span></div><p>${short(S.insertionPesos)} without a plausible NEP counterpart identified</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><span>HGAB MPB schedule</span><strong>${num(S.hgabLines)} lines · ${short(S.hgabPesos)}</strong></div><div><span>Ambiguous counterparts</span><strong>${num(S.ambiguousLines)} lines · ${short(S.ambiguousPesos)}</strong></div><div><span>Historical repeat screen</span><strong>${S.repeatPairs} pairs · ${S.repeatProposals} NEP projects</strong></div></div><p>Screening candidates require original-source and scope review.</p></div></section>`;
const projectColumns=[['Project','projectName'],['LEG · strict attribution','legDistricts'],['Representative · geographic coverage','representatives'],['Building type','buildingType'],['Closest NEP title · not necessarily a match','closest_nep_title'],['Matching basis','match_basis']];
const amountFrequency=new Map();for(const row of D.prices||[])amountFrequency.set(Number(row.amountPesos),(amountFrequency.get(Number(row.amountPesos))||0)+Number(row.projects||0));
const modeAmount=[...amountFrequency.entries()].sort((a,b)=>b[1]-a[1]||a[0]-b[0])[0]?.[0]||5000000;
D.modeRanking=Object.entries(D.coordinateProximity?.projectDetails||{}).map(([id,r])=>({...r,hgab_id:id,modeMultiple:Number(r.amountPesos||0)/modeAmount,modeAmount})).sort((a,b)=>b.modeMultiple-a.modeMultiple||a.projectName.localeCompare(b.projectName)).map((r,i,rows)=>({...r,modeRank:i&&Number(r.amountPesos)===Number(rows[i-1].amountPesos)?rows[i-1].modeRank:i+1}));
const configs=[
{id:'modeRanking',title:'MPB allocations · multiples of the most common amount',note:`The most common HGAB 3rd allocation is ${peso(modeAmount)} (${num(amountFrequency.get(modeAmount))} projects). Rank each listed allocation as a multiple of that amount. This is an allocation-size screen, not a construction-cost or value-for-money comparison. Open a project title for its office, NEP comparison, source page and applicable review signals.`,columns:[['Rank','modeRank'],['Project','projectName'],['HGAB allocation pesos','amountPesos'],['Multiple of common amount','modeMultiple']],metric:'modeMultiple',chart:'bars'},
{id:'insertions',title:'Potential insertions · no plausible NEP counterpart identified',note:'Domestic HGAB lines only. This bucket excludes ambiguous counterparts; verify original NEP and HGAB pages before confirming an insertion.',columns:[projectColumns[0],['HGAB allocation pesos','amountPesos'],...projectColumns.slice(1)],metric:'amountPesos',chart:'bars'},
{id:'ambiguous',title:'Ambiguous counterparts · kept outside insertion totals',note:'Potential, multiple or already-paired counterparts require scope/occurrence review. These are not certified insertions.',columns:[projectColumns[0],['HGAB allocation pesos','amountPesos'],...projectColumns.slice(1),['Counterpart status','comparison']],metric:'amountPesos',chart:'bars'},
{id:'adjustments',title:'Allocation adjustments · selected retained counterparts',note:'Positive and negative budget changes on selected one-to-one links; counterpart confidence remains visible. Potential title links still need scope review. These rows can overlap the ambiguous-counterpart review, but not insertion candidates. Open the HGAB project title for its office and source page.',columns:[['HGAB project','projectName'],['NEP project','closest_nep_title'],['HGAB allocation pesos','amountPesos'],['NEP allocation pesos','closest_nep_amount_pesos'],['Adjustment pesos','amount_delta_pesos'],['Counterpart confidence','comparison'],['NEP page','nep_source_page']],metric:'amount_delta_pesos',chart:'diverging'},
{id:'removals',title:'Potential removals · unpaired NEP lines',note:'Unpaired records are removal-review candidates. Absence of a selected counterpart does not certify deletion.',columns:[['NEP project','nepTitle'],['Office','office'],['NEP allocation pesos','nepPesos'],['Review basis','basis'],['NEP page','nepPage']],metric:'nepPesos',chart:'bars'},
{id:'repeats',title:'Historical repeat comparisons · did the NEP proposal survive into HGAB?',note:'One row per NEP–GAA comparison pair. Distinct NEP proposals are counted separately in the hero. Potential retention is not a clear retained link. Open the project title for the current HGAB allocation, office, representative association and source page.',columns:[['NEP project','project'],['NEP allocation pesos','amount_2027'],['GAA year','comparison_year'],['Prior GAA project','prior_project'],['Prior GAA allocation pesos','prior_amount'],['Prior source','prior_source'],['Chainage status','chainage_status'],['Tranche status','tranche_status'],['HGAB retention','retention']],metric:'amount_2027',chart:'retention'},
{id:'prices',title:'Allocation amounts by building type · repeated amounts need scope context',note:'Counts of identical appropriation amounts, grouped by descriptive building type. This is not a construction unit-price comparison.',columns:[['Building type','buildingType'],['Allocation per project pesos','amountPesos'],['Projects at this amount','projects'],['Combined allocation pesos','totalPesos'],['Offices','offices']],metric:'projects',chart:'vertical'},
{id:'distribution',title:'MPB allocations by implementing office',note:'Central Office is its own administrative bucket. An implementing office is not a congressional district.',columns:[['Region','region'],['Office','office'],['HGAB projects','projects'],['HGAB allocation pesos','amountPesos'],['Potential insertions','insertionCount'],['Potential insertion allocation pesos','insertionPesos']],metric:'amountPesos',chart:'vertical'}];
D.repeats=D.repeats.map(r=>({...r,retention:r.hgabRetention.status,hgabPage:r.hgabRetention.hgabPage,hgab_id:r.hgabRetention.hgabId}));
function graphic(rows,c,metric){
 if(!rows.length)return '<p>No matching records to plot.</p>';
 let points=rows.slice(0,12).map((r,i)=>({label:r.projectName||r.nepTitle||r.office||r.buildingType+' · '+peso(r.amountPesos),value:Number(r[metric]||0)}));
 if(c.chart==='retention'){const groups={};rows.forEach(r=>groups[r.retention]=(groups[r.retention]||0)+1);points=Object.entries(groups).map(([label,value])=>({label,value}));}
 const max=Math.max(1,...points.map(p=>Math.abs(p.value))),money=c.chart!=='retention'&&/pesos|amount/i.test(metric),fmt=v=>metric==='modeMultiple'?`${Number(v).toFixed(1)}×`:money?peso(v):num(v);let body='';
 if(c.chart==='bars')points.forEach((p,i)=>{let y=35+i*28;body+=`<text x="8" y="${y}" font-size="12">${i+1}<title>${esc(p.label)}</title></text><rect x="55" y="${y-12}" width="795" height="17" fill="#087e78" opacity=".12"></rect><rect x="55" y="${y-12}" width="${795*Math.abs(p.value)/max}" height="17" fill="#087e78"><title>${esc(p.label)}: ${fmt(p.value)}</title></rect><text x="860" y="${y}" font-size="11">${fmt(p.value)}</text>`});
 else points.forEach((p,i)=>{const step=880/points.length,x=65+i*step,w=Math.max(8,step*.65),div=c.chart==='diverging',base=div?155:255,h=(div?110:190)*Math.abs(p.value)/max,y=div?(p.value>=0?base-h:base):base-h;body+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${p.value<0?'#b65b09':'#087e78'}"><title>${esc(p.label)}: ${fmt(p.value)}</title></rect><text x="${x}" y="${y-5}" font-size="10">${fmt(p.value)}</text><text transform="translate(${x+5},280) rotate(30)" font-size="10">${i+1}<title>${esc(p.label)}</title></text>`;});
 const legend=`<ol class="chart-legend chart-legend-no-rank">${points.map(p=>`<li><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join('')}</ol>`;
 return `<svg viewBox="0 0 1030 420" role="img" aria-label="${esc(c.title)}"><title>${esc(c.title)}</title>${body}</svg>${legend}`;
}
for(const c of configs){
 const section=document.createElement('section');section.id='mpb-'+c.id;section.className='card mpb-project-review-'+c.id+(c.id==='modeRanking'?' mpb-mode-ranking':'');const choices=[...new Set(D[c.id].map(r=>r.buildingType||r.retention||r.region).filter(Boolean))].sort();
 const sortOptions=[...new Map([[c.metric,c.columns.find(([label,key])=>key===c.metric)?.[0]||c.metric],...c.columns.filter(([label,key])=>/pesos|projects|count/i.test(key)).map(([label,key])=>[key,label])]).entries()];
 section.innerHTML=`<h2>${esc(c.title)}</h2><p>${esc(c.note)}</p><div class="controls"><input type="search" aria-label="Search ${c.id}" placeholder="Filter projects, locations or source records"><select aria-label="Filter group"><option value="">All groups</option>${choices.map(v=>`<option>${esc(v)}</option>`).join('')}</select><select class="sort" aria-label="Sort metric">${sortOptions.map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('')}</select><select class="order" aria-label="Sort direction"><option value="desc">Largest first</option><option value="asc">Smallest first</option></select><button class="export" type="button">Export CSV</button></div><figure><figcaption></figcaption><div class="graph"></div></figure><p class="count"></p><table><thead><tr>${c.columns.map(([label])=>`<th>${esc(label)}</th>`).join('')}</tr></thead><tbody></tbody></table><div class="controls"><button class="prev">Previous</button><span class="page"></span><button class="next">Next</button></div>`;
 document.getElementById('sections').append(section);let filtered=[],page=0;
 const search=section.querySelector('input'),select=section.querySelector('select'),sort=section.querySelector('.sort'),order=section.querySelector('.order');
 function render(){const q=search.value.trim().toLowerCase(),group=select.value,metric=sort.value;filtered=D[c.id].filter(r=>(!group||[r.buildingType,r.retention,r.region].includes(group))&&(!q||JSON.stringify(r).toLowerCase().includes(q))).sort((a,b)=>(Number(b[metric]||0)-Number(a[metric]||0))*(order.value==='desc'?1:-1));const pages=Math.max(1,Math.ceil(filtered.length/25));page=Math.min(page,pages-1);section.querySelector('.graph').innerHTML=graphic(filtered,c,metric);section.querySelector('figcaption').textContent=c.chart==='retention'?'Comparison pairs by HGAB retention status · all filtered rows':'First '+Math.min(12,filtered.length)+' filtered rows · '+sort.selectedOptions[0].text+' · '+order.selectedOptions[0].text;section.querySelector('.count').textContent=num(filtered.length)+' filtered rows';section.querySelector('tbody').innerHTML=filtered.slice(page*25,(page+1)*25).map(r=>'<tr>'+c.columns.map(([label,key])=>{const value=key==='modeMultiple'?`${Number(r[key]).toFixed(1)}×`:/pesos|allocation|adjustment/i.test(label)&&r[key]!=null&&r[key]!==''?peso(r[key]):r[key]??'—';const projectId=r.hgab_id||r.hgabRetention?.hgabId;const projectTitle=projectId&&['projectName','project','nepTitle'].includes(key);return `<td>${projectTitle?`<span>${esc(value)}</span> <button type="button" class="mpb-open-project report-project-details-trigger" data-mpb-project-id="${esc(projectId)}">Details</button>`:esc(value)}</td>`}).join('')+'</tr>').join('')||`<tr><td colspan="${c.columns.length}">No matching records.</td></tr>`;section.querySelector('.page').textContent=`Page ${page+1} of ${pages}`;section.querySelector('.prev').disabled=page===0;section.querySelector('.next').disabled=page>=pages-1;}
 [search,select,sort,order].forEach(el=>el.addEventListener(el===search?'input':'change',()=>{page=0;render()}));section.querySelector('.prev').onclick=()=>{page--;render()};section.querySelector('.next').onclick=()=>{page++;render()};section.querySelector('.export').onclick=()=>{const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"',csv=[c.columns.map(([label])=>quote(label)).join(','),...filtered.map(r=>c.columns.map(([label,key])=>quote(r[key])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='mpb-'+c.id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};render();
}
const landTitleSignals=Object.entries(D.coordinateProximity?.projectDetails||{}).map(([code,row])=>{const title=String(row.projectName||''),signals=[];if(/\bsubdivision\b/i.test(title))signals.push('Subdivision named');if(/\bHOA\b|homeowners?\s*(?:association|assoc)/i.test(title))signals.push('HOA named');if(/\bvillage\b/i.test(title))signals.push('Village named · weak location cue');if(/\bprivate(?:ly)?\b|private\s+(?:land|lot|property)/i.test(title))signals.push('Private ownership wording');if(/\b(?:land|lot)\s+(?:acquisition|purchase|donation|donated|leased|owned)\b/i.test(title))signals.push('Land/lot transaction wording');return signals.length?{code,row,signals}:null}).filter(Boolean).sort((a,b)=>Number(b.row.amountPesos||0)-Number(a.row.amountPesos||0)||a.row.projectName.localeCompare(b.row.projectName));
const landRows=document.getElementById('mpb-land-site-rows');document.getElementById('mpb-land-site-summary').textContent=`${num(landTitleSignals.length)} FY2027 HGAB project titles match a subdivision, HOA, village, or explicit land/ownership phrase · ${peso(landTitleSignals.reduce((sum,x)=>sum+Number(x.row.amountPesos||0),0))} in listed allocations. Village is a weak cue; this is a review queue, not a finding about ownership.`;
landRows.innerHTML=landTitleSignals.map(({code,row,signals})=>{const links=(row.transparencyLinks||[]).filter(x=>x.url&&/^https:\/\//i.test(x.url)).map(x=>`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.type||'Project file')} ↗</a>`).join(' · '),source=`${esc(row.sourceVolume||'HB10858 3rd reading')} · p. ${esc(row.sourcePage||'not recorded')} · ${esc(code)}`;return `<tr><td>${esc(row.projectName)}<small>${esc(row.office||'Office not stated')}</small></td><td>${signals.map(esc).join('<br>')}</td><td>${esc(row.place||'No qualified place in record')}</td><td class="num">${peso(row.amountPesos)}</td><td><details><summary>View sources</summary><p>${source}</p>${links||'<p class="note">No linked project file is listed in the current transparency record.</p>'}</details></td></tr>`}).join('')||'<tr><td colspan="5">No subdivision, HOA, or explicit private-land wording was found in the current project titles.</td></tr>';
</script></body></html>'''

if __name__ == '__main__':
    print(json.dumps(build()['summary'], indent=2))
