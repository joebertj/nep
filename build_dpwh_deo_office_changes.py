#!/usr/bin/env python3
"""Build the CSIIIV-sourced DPWH office-change review and annotate OOP map rows."""
import html
import json
import math
import re
import hashlib
import shutil
import subprocess
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / 'data_sources/csiiiv/snapshots/34ef5d8cbbacda92f6503ffd9a428569f157f64d/analysis/data/source_comparison_2027.json'
HGAB = ROOT / 'hb10858_3rd_dpwh_projects.json'
DATA = ROOT / 'analysis_output/dpwh_deo_office_changes.json'
PAGE = ROOT.parent / 'open-data-visualization/static/nep-preview/dpwh-hgab.html'
MAP_DATA = ROOT.parent / 'open-data-visualization/static/nep-preview/dpwh-deo-office-change-maps.json'
MAP_JS_SOURCE = ROOT / 'report_assets/dpwh_deo_office_changes.js'
MAP_JS = ROOT.parent / 'open-data-visualization/static/nep-preview/dpwh-deo-office-changes.js'
ENGINEERING_DISTRICTS = ROOT / 'data_sources/arcgis_dpwh/archive/selected/engineering_districts/layers/Engineering_District_FeatureServer_0-ac70a8f7/features.jsonl'
SHARE_DIR = ROOT.parent / 'open-data-visualization/static/nep-preview/dpwh-office-change-share'
PORTRAIT_CACHE = ROOT / '.cache/out_of_place_portraits'
LEG_PROFILE_SOURCE = ROOT / 'data_sources/csiiiv/legislative_profiles_ff0f748.json'
MARKER = '<!-- dpwh-deo-office-changes -->'

import sys
sys.path.insert(0, str(ROOT))
from analyze_mpb_proximity import utm51_to_wgs84


def norm(value):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '', value)


def simplified_ring(ring, tolerance=450):
    points = [(float(p[0]), float(p[1])) for p in ring if len(p) >= 2]
    if len(points) < 4:
        return points
    closed = math.dist(points[0], points[-1]) < 1
    if closed:
        points = points[:-1]
    kept = [points[0]]
    for point in points[1:]:
        if math.dist(point, kept[-1]) >= tolerance:
            kept.append(point)
    if len(kept) < 3:
        kept = points[::max(1, len(points)//3)][:3]
    if closed and kept[-1] != kept[0]:
        kept.append(kept[0])
    return kept


def build_office_geography(records):
    feature_by_name = {}
    bangsamoro_rings = []
    for line in ENGINEERING_DISTRICTS.read_text(encoding='utf-8').splitlines():
        feature = json.loads(line)
        attrs = feature.get('attributes', {})
        name = attrs.get('DEO')
        if not name:
            continue
        rings = []
        for raw_ring in feature.get('geometry', {}).get('rings', []):
            sparse = simplified_ring(raw_ring)
            if len(sparse) >= 4:
                converted = [utm51_to_wgs84(x, y) for x, y in sparse]
                rings.append(converted)
                if 'bangsamoro autonomous region' in str(attrs.get('REGION', '')).lower():
                    bangsamoro_rings.append(converted)
        feature_by_name[norm(name)] = {
            'name': name,
            'province': attrs.get('PROVINCE'),
            'region': attrs.get('REGION'),
            'congressionalDistrict': attrs.get('CONG_DIST'),
            'rings': rings,
            'source': 'DPWH Engineering District FeatureServer · archived snapshot, data edited August 2024',
        }
    aliases = {
        norm('Siguijor District Engineering Office'): norm('Siquijor District Engineering Office'),
        norm('Las Pi ñ as Muntinlupa District Engineering Office'): norm('Las PiMas-Muntinlupa District Engineering Office'),
    }
    needed = {office for row in records for office in (row['nepOffice'], row['hgabOffice']) if office}
    offices = {}
    for office in sorted(needed):
        if norm(office) == norm('Central Office'):
            offices[office] = {'name': office, 'kind': 'central'}
            continue
        if norm(office) == norm('BARMM'):
            offices[office] = {
                'name': 'BARMM · all mapped DEO areas',
                'kind': 'aggregate',
                'province': 'Bangsamoro Autonomous Region in Muslim Mindanao',
                'rings': bangsamoro_rings,
                'source': 'DPWH Engineering District FeatureServer · aggregate of all mapped BARMM DEO areas',
            }
            continue
        key = aliases.get(norm(office), norm(office))
        match = feature_by_name.get(key)
        if match:
            offices[office] = {'kind': 'deo', **match}
        else:
            offices[office] = {
                'name': office,
                'kind': 'unresolved',
                'note': 'No single matching engineering-district boundary was available in the DPWH boundary snapshot.',
            }
    return offices


def representatives_for_office(office, geometry, profile_index, profile_source):
    """Resolve only a single seat explicitly named by the archived DEO boundary crosswalk."""
    if geometry.get('kind') not in ('deo', 'aggregate') or not geometry.get('congressionalDistrict'):
        return []
    raw = str(geometry['congressionalDistrict']).strip()
    match = re.fullmatch(r'(.+?)\s*\(([^()]*)\)', raw)
    if not match:
        return []
    jurisdiction, label = match.groups()
    jurisdiction_aliases = {'mtprovince': 'mountain province', 'manilacity': 'manila',
                            'butuancity': 'agusan del norte'}
    jurisdiction = jurisdiction_aliases.get(norm(jurisdiction), jurisdiction)
    normalized_label = norm(label)
    ordinal = {'lone': 'lone', 'first': '1st', 'second': '2nd', 'third': '3rd',
               'fourth': '4th', 'fifth': '5th', 'sixth': '6th', 'seventh': '7th',
               'eighth': '8th', 'ninth': '9th', 'tenth': '10th', 'eleventh': '11th',
               'twelfth': '12th'}
    seat_numbers = re.findall(r'(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|lone)', normalized_label)
    if not seat_numbers:
        return []
    numbers = list(dict.fromkeys(ordinal[value] for value in seat_numbers))
    cards = []
    for number in numbers:
        seat = profile_index.get((norm(jurisdiction), norm(number)))
        if not seat or not seat.get('representative'):
            continue
        photo_file = seat.get('photoFile')
        photo_url = ('https://raw.githubusercontent.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/' +
                     profile_source['commit'] + '/DEO2LEG/legislative_profiles/photos/' + photo_file) if photo_file else None
        cards.append({'district': f"{jurisdiction} · {number} district", 'name': seat.get('representative'),
                      'officialName': seat.get('representative'), 'profileUrl': seat.get('detailUrl'),
                      'photoUrl': photo_url, 'resolutionStatus': seat.get('resolutionStatus')})
    return cards


def cache_representative_photos(projects):
    """Reuse OOP's local portrait cache and publish referenced portraits beside share pages."""
    import urllib.request
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    PORTRAIT_CACHE.mkdir(parents=True, exist_ok=True)
    oop_share = ROOT.parent / 'open-data-visualization/static/nep-preview/out-of-place-share'
    for row in projects:
        for card in row.get('nepRepresentatives', []) + row.get('hgabRepresentatives', []):
            photo_url = card.get('photoUrl')
            if not photo_url:
                continue
            digest = hashlib.sha256(photo_url.encode()).hexdigest()[:16]
            cached = PORTRAIT_CACHE / f'{digest}.image'
            if not cached.is_file() or cached.stat().st_size < 4:
                oop_cached = next(iter(oop_share.glob(f'representative-{digest}.*')), None) if oop_share.exists() else None
                if oop_cached and oop_cached.is_file() and oop_cached.stat().st_size > 4:
                    shutil.copyfile(oop_cached, cached)
            if not cached.is_file() or cached.stat().st_size < 4:
                try:
                    request = urllib.request.Request(photo_url, headers={'User-Agent': 'BetterGov share-card builder'})
                    with urllib.request.urlopen(request, timeout=15) as response:
                        data = response.read()
                    if not data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
                        continue
                    cached.write_bytes(data)
                except Exception as error:
                    print(f"Could not cache representative portrait for {card['name']}: {error}")
                    continue
            data = cached.read_bytes()
            ext = '.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg'
            name = f'representative-{digest}{ext}'
            public = SHARE_DIR / name
            if not public.is_file() or public.read_bytes() != data:
                shutil.copyfile(cached, public)
            card['cachedPhotoUrl'] = f'dpwh-office-change-share/{name}'


def main():
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    projects = json.loads(HGAB.read_text(encoding='utf-8'))['data']['data']
    selected = []
    for pair in snapshot['projects']:
        house, nep = pair.get('house'), pair.get('nep')
        if not house or not nep or house.get('office_canonical') == nep.get('office_canonical'):
            continue
        if pair['status'] in ('exact_candidate', 'chainage_candidate'):
            selected.append(pair)
        elif pair['status'] == 'scope_amendment_candidate' and 'San Manuel' in house.get('title', ''):
            selected.append(pair)  # one Isabela scope-adjusted office change
    records = []
    for pair in selected:
        house, nep = pair['house'], pair['nep']
        matches = [row for row in projects if int(row.get('amountPesos') or 0) == int(house.get('amount_php') or 0)
                   and norm(row.get('projectName')) == norm(house.get('title'))]
        hgab_id = matches[0]['id'] if len(matches) == 1 else None
        records.append({
            'hgabProjectId': hgab_id,
            'title': house.get('title', ''),
            'nepOffice': nep.get('office', ''),
            'hgabOffice': house.get('office', ''),
            'nepPage': nep.get('pdf_page'),
            'hgabPage': house.get('pdf_page'),
            'nepAmountPesos': nep.get('amount_php'),
            'hgabAmountPesos': house.get('amount_php'),
            'status': pair.get('status'),
            'confidence': pair.get('confidence'),
            'coordinatePairPrinted': bool(hgab_id and re.search(r'\d{1,2}\.\d+\s*,\s*\d{2,3}\.\d+', house.get('title', ''))),
        })
    records.sort(key=lambda row: (row['hgabPage'] or 0, row['title']))
    mapped = [row for row in records if row['hgabProjectId'] and row['coordinatePairPrinted']]
    mapped_ids = {row['hgabProjectId'] for row in mapped}
    for row in records:
        row['mapUrl'] = f"out-of-place.html?project={row['hgabProjectId']}" if row['hgabProjectId'] in mapped_ids else None
    unmapped = [row for row in records if row['hgabProjectId'] not in mapped_ids]
    offices = build_office_geography(unmapped)
    profiles = json.loads(LEG_PROFILE_SOURCE.read_text(encoding='utf-8'))
    profile_source, profile_index = profiles['source'], {}
    for seat in profiles['districts']:
        profile_index[(norm(seat['jurisdiction']), norm(seat['districtLabel']))] = seat
    map_projects = []
    for index, row in enumerate(unmapped):
        item = {key: row[key] for key in ('title', 'nepOffice', 'hgabOffice', 'nepPage', 'hgabPage', 'nepAmountPesos', 'hgabAmountPesos')}
        item['nepRepresentatives'] = representatives_for_office(row['nepOffice'], offices.get(row['nepOffice'], {}), profile_index, profile_source)
        item['hgabRepresentatives'] = representatives_for_office(row['hgabOffice'], offices.get(row['hgabOffice'], {}), profile_index, profile_source)
        item['shareSlug'] = f"{re.sub(r'[^a-z0-9]+', '-', row['title'].lower()).strip('-')[:48].strip('-') or 'office-change'}-{hashlib.sha256((row['title'] + str(index)).encode()).hexdigest()[:10]}"
        map_projects.append(item)
    cache_representative_photos(map_projects)
    map_payload = {
        'source': 'DPWH Engineering District FeatureServer · archived DPWH office boundaries (edited August 2024)',
        'projectCount': len(map_projects),
        'offices': offices,
        'projects': map_projects,
    }
    MAP_DATA.write_text(json.dumps(map_payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    share_input = ROOT / 'analysis_output/dpwh_office_change_share_payload.json'
    share_input.write_text(json.dumps(map_payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    swift_cache = Path('/private/tmp/odv-swift-module-cache')
    swift_cache.mkdir(parents=True, exist_ok=True)
    subprocess.run(['swift', '-module-cache-path', str(swift_cache), str(ROOT / 'build_dpwh_office_change_share_cards.swift'), str(share_input), str(SHARE_DIR)], check=True)
    public_base = 'https://research.bettergov.ph/static/nep-preview/dpwh-office-change-share/'
    for project in map_projects:
        slug = project['shareSlug']
        image = SHARE_DIR / f'{slug}.png'
        version = hashlib.sha256(image.read_bytes()).hexdigest()[:12]
        project['sharePage'] = f'{public_base}{slug}.html?v={version}'
        project['shareImage'] = f'{public_base}{slug}.png?v={version}'
        image_name = f'{slug}.png'
        title = html.escape(project['title'], quote=True)
        allocation_delta = int(project['hgabAmountPesos'] or 0)-int(project['nepAmountPesos'] or 0)
        allocation_delta_text = ('−₱' if allocation_delta < 0 else '+₱') + f'{abs(allocation_delta):,}'
        description = html.escape(f"NEP {project['nepOffice']} → HGAB 3rd {project['hgabOffice']} · allocation change {allocation_delta_text}. Geographic representatives are associated with mapped DEO boundaries, not project sponsorship.", quote=True)
        reps = []
        for side, label in (('nepRepresentatives', 'From · NEP office'), ('hgabRepresentatives', 'To · HGAB 3rd office')):
            for rep in project[side]:
                image_src = Path(rep.get('cachedPhotoUrl') or '').name
                photo = f'<img src="{html.escape(image_src, quote=True)}" alt="Photo of {html.escape(rep["name"], quote=True)}">' if image_src else ''
                reps.append(f'<div class="rep">{photo}<span><strong>{html.escape(rep["name"])}</strong><small>{label} · {html.escape(rep["district"])}</small><a href="{html.escape(rep.get("profileUrl") or "#", quote=True)}">House profile ↗</a></span></div>')
        reps_html = ''.join(reps) or '<p>No single geographic representative was resolved for these office boundaries.</p>'
        page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Office change · {title}</title><meta name="description" content="{description}"><meta property="og:type" content="website"><meta property="og:url" content="{html.escape(project['sharePage'], quote=True)}"><meta property="og:title" content="Office change · {title}"><meta property="og:description" content="{description}"><meta property="og:image" content="{html.escape(project['shareImage'], quote=True)}"><meta property="og:image:secure_url" content="{html.escape(project['shareImage'], quote=True)}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{html.escape(project['shareImage'], quote=True)}"><link rel="stylesheet" href="../../css/tailwind.css"><style>body{{margin:0;padding:24px;background:#FAFAFA;color:#212121;font:16px/1.5 system-ui,sans-serif}}main{{max-width:1200px;margin:auto}}img.map{{display:block;width:100%;height:auto;border-radius:14px}}.rep{{display:inline-flex;gap:12px;align-items:center;vertical-align:top;margin:8px;padding:12px;border:1px solid #ddd;border-radius:10px;background:white}}.rep img{{width:64px;height:76px;object-fit:cover;border-radius:7px}}.rep small,.rep a{{display:block}}.rep a{{color:#0038A8}}</style></head><body><main><h1>Office change · {title}</h1><img class="map" src="{image_name}" width="1200" height="630" alt="Office change share card"><h2>Geographic representatives associated with mapped DEO boundaries</h2>{reps_html}<p>{description} These geographic associations indicate mapped boundary coverage, not project sponsorship.</p><a href="../dpwh-hgab.html#deo-office-changes">Open the DPWH office changes explorer ↗</a></main></body></html>'''
        (SHARE_DIR / f'{slug}.html').write_text(page, encoding='utf-8')
    map_payload['projects'] = map_projects
    MAP_DATA.write_text(json.dumps(map_payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    map_js = MAP_JS_SOURCE.read_text(encoding='utf-8')
    MAP_JS.write_text(map_js, encoding='utf-8')
    payload = {
        'source': 'CSIIIV retained source comparison snapshot',
        'snapshotCommit': '34ef5d8cbbacda92f6503ffd9a428569f157f64d',
        'snapshotPath': str(SNAPSHOT.relative_to(ROOT)),
        'scope': 'Exact and chainage candidates with canonical office changes, plus the San Manuel, Isabela scope-adjusted candidate. Two Camiguin operations-center title/scope candidates are excluded pending manual identity review.',
        'count': len(records), 'mappableCount': len(mapped), 'records': records,
    }
    payload['officeMapAsset'] = str(MAP_DATA.relative_to(ROOT.parent / 'open-data-visualization'))
    payload['officeMapProjectCount'] = len(map_projects)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    rows_html = ''.join(
        '<tr><td>' + html.escape(row['title']) + '</td><td><strong>NEP:</strong> ' + html.escape(row['nepOffice']) + ' <span aria-label="changed to">→</span> <strong>HGAB 3rd:</strong> ' + html.escape(row['hgabOffice']) + '</td>'
        + f"<td>{html.escape(str(row['nepPage'] or '—'))} → {html.escape(str(row['hgabPage'] or '—'))}</td>"
        + f"<td>₱{int(row['nepAmountPesos'] or 0):,} → ₱{int(row['hgabAmountPesos'] or 0):,}</td>"
        + '</tr>' for row in unmapped
    )
    section = f'''{MARKER}<section class="card deo-office-changes-section" id="deo-office-changes"><h2>Office changes · {len(unmapped)}</h2>
<p class="sub">Compare the NEP and HGAB 3rd implementing-office areas for the {len(unmapped)} candidate line items without project coordinates. The maps show DPWH engineering-district boundaries; Central Office is shown with the DPWH seal. The listed office change is a comparison signal, not proof that the project moved geographically. The Isabela record is scope-adjusted; two Camiguin operations-center candidates are excluded pending identity review.</p>
<p class="sub">Source comparison: <a href="https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/tree/34ef5d8cbbacda92f6503ffd9a428569f157f64d">CSIIIV snapshot 34ef5d8cbbac</a>. Engineering-district boundaries: DPWH layer snapshot, data edited August 2024. The {len(mapped)} records with printed project coordinates remain on <a href="out-of-place.html">Out of Place</a>.</p>
<div class="deo-change-explorer" id="deo-change-explorer" data-source="dpwh-deo-office-change-maps.json"><div class="deo-change-toolbar"><input type="search" id="deo-change-search" placeholder="Search project or office"><button type="button" id="deo-change-previous">Previous</button><span id="deo-change-count" aria-live="polite">Loading office maps…</span><button type="button" id="deo-change-next">Next</button></div>
<div class="deo-change-workspace"><section class="deo-change-map-panel"><h3>NEP office → HGAB 3rd office</h3><div class="deo-change-map-pair" id="deo-change-map-pair"><p>Loading engineering-district boundaries…</p></div><p class="deo-change-map-note">Each shape is shown in its own fitted map panel. The arrow indicates the office assignment listed in the two source schedules; it is not a project-location arrow.</p></section><article class="deo-change-card" id="deo-change-card" aria-live="polite"></article></div>
<section class="deo-change-list-panel"><h3>Office-change projects</h3><div class="deo-change-list" id="deo-change-list"></div></section></div>
<details class="deo-change-table"><summary>Show the 61 office-change records as a table</summary><div class="tablewrap"><table><thead><tr><th>Project line item</th><th>Office change · NEP → HGAB 3rd</th><th>NEP → HGAB PDF page</th><th>NEP → HGAB allocation</th></tr></thead><tbody>{rows_html}</tbody></table></div></details></section>'''
    page = PAGE.read_text(encoding='utf-8')
    if MARKER in page:
        start = page.index(MARKER)
        # The section contains several nested <section> elements. Remove the
        # complete generated block up to the next first-party report section;
        # stopping at the first </section> leaves the table/list behind and
        # duplicates them on every rebuild.
        end = page.find('<section class="card section">', start)
        if end < 0:
            end = page.find('</main>', start)
        if end >= 0:
            page = page[:start] + page[end:]
    css = '''<style id="deo-office-changes-style">
.deo-office-changes-section{scroll-margin-top:20px}.deo-change-explorer{margin-top:18px}.deo-change-toolbar{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin:12px 0}.deo-change-toolbar input,.deo-change-toolbar button{font:inherit;min-height:40px;padding:8px 11px;border:1px solid #BDBDBD;border-radius:8px;background:#fff;color:#212121}.deo-change-toolbar input{min-width:min(360px,100%);flex:1}.deo-change-toolbar button{cursor:pointer}.deo-change-toolbar button:disabled{opacity:.45;cursor:default}.deo-change-toolbar span{color:#616161;font-size:13px}.deo-change-workspace{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(320px,.85fr);gap:14px;align-items:stretch}.deo-change-map-panel,.deo-change-card,.deo-change-list-panel{border:1px solid #E0E0E0;border-radius:11px;background:#fff;padding:15px}.deo-change-map-panel h3,.deo-change-list-panel h3{margin:0 0 12px;font-size:17px}.deo-change-map-pair{display:grid;grid-template-columns:minmax(0,1fr) 30px minmax(0,1fr);gap:7px;align-items:center}.deo-change-mapbox{min-width:0;min-height:260px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:7px;padding:8px;border:1px solid #E0E0E0;border-radius:9px;background:#FAFAFA;text-align:center}.deo-change-mapbox svg{display:block;width:100%;height:auto;max-height:260px}.deo-change-mapbox strong{font-size:13px;line-height:1.35;overflow-wrap:anywhere}.deo-change-mapbox>span{color:#616161;font-size:12px}.deo-boundary{stroke-width:2;vector-effect:non-scaling-stroke;stroke-linejoin:round}.deo-boundary.from{fill:#DBEAFE;stroke:#0038A8}.deo-boundary.to{fill:#FDE68A;stroke:#CE1126}.deo-change-arrow{color:#0038A8;font-size:26px;font-weight:800;text-align:center}.deo-change-central img{width:92px;height:92px;object-fit:contain}.deo-change-central strong{font-size:16px;color:#0038A8}.deo-change-central span{font-weight:700}.deo-change-unresolved{color:#616161}.deo-change-unresolved strong{color:#212121}.deo-change-map-note,.deo-change-source{color:#616161;font-size:12px;line-height:1.5}.deo-change-card{display:flex;flex-direction:column;gap:10px}.deo-change-kicker{color:#0038A8;font-size:12px;font-weight:800;letter-spacing:.04em;text-transform:uppercase}.deo-change-card h3{margin:0;font-size:19px;line-height:1.35}.deo-change-offices{display:grid;gap:8px}.deo-change-offices div,.deo-change-cost div{padding:9px 10px;border:1px solid #E0E0E0;border-radius:8px;background:#FAFAFA}.deo-change-offices small,.deo-change-cost small{display:block;color:#616161;font-size:11px}.deo-change-offices strong{display:block;margin-top:3px;font-size:13px;line-height:1.35;overflow-wrap:anywhere}.deo-change-cost{display:grid;grid-template-columns:1fr 1fr;gap:7px}.deo-change-cost strong{display:block;margin-top:4px;font-size:15px;font-variant-numeric:tabular-nums}.deo-change-cost .deo-change-delta{grid-column:1/-1;background:#EAF0FF;border-color:#BFDBFE}.deo-change-cost .deo-change-delta strong{font-size:20px;color:#0038A8}.deo-change-list-panel{margin-top:14px}.deo-change-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px;max-height:360px;overflow-y:auto;overflow-x:hidden}.deo-change-list button{min-width:0;padding:9px 10px;border:1px solid #E0E0E0;border-radius:8px;background:#fff;text-align:left;cursor:pointer}.deo-change-list button[aria-current=true]{border-color:#0038A8;background:#EAF0FF}.deo-change-list button strong,.deo-change-list button small{display:block;line-height:1.4;overflow-wrap:anywhere}.deo-change-list button strong{font-size:12px}.deo-change-list button small{margin-top:4px;color:#616161;font-size:11px}.deo-change-table{margin-top:12px}.deo-change-table summary{cursor:pointer;font-weight:650}.deo-change-table .tablewrap{max-width:100%;overflow-x:visible!important}.deo-change-table table{min-width:0;width:100%;table-layout:auto}.deo-change-table th:first-child,.deo-change-table td:first-child{width:30%;overflow-wrap:anywhere}.deo-change-table th:nth-child(2),.deo-change-table td:nth-child(2){width:45%;overflow-wrap:anywhere}.deo-change-table th:nth-child(n+3),.deo-change-table td:nth-child(n+3){overflow-wrap:anywhere}
@media(max-width:900px){.deo-change-workspace{grid-template-columns:1fr}.deo-change-map-pair{grid-template-columns:1fr}.deo-change-arrow{transform:rotate(90deg)}.deo-change-mapbox{min-height:220px}.deo-change-mapbox svg{max-height:220px}}
@media(max-width:540px){.deo-change-toolbar span{order:-1;width:100%}.deo-change-mapbox{min-height:200px}}
</style>'''
    css = css.replace('</style>', '.deo-change-representatives{display:grid;gap:7px}.deo-change-representatives h4{margin:0;font-size:13px}.deo-change-rep{display:flex;align-items:center;gap:9px;min-width:0;padding:8px;border:1px solid #E0E0E0;border-radius:8px;background:#FAFAFA}.deo-change-rep img{width:46px;height:54px;border-radius:6px;object-fit:cover;background:#eee}.deo-change-rep strong,.deo-change-rep small,.deo-change-rep a{display:block;overflow-wrap:anywhere}.deo-change-rep strong{font-size:12px}.deo-change-rep small,.deo-change-rep a{font-size:11px;color:#616161}.deo-change-rep a{color:#0038A8}.deo-change-share{display:flex;flex-wrap:wrap;gap:7px;margin-top:auto}.deo-change-share a,.deo-change-share button{font:inherit;font-size:12px;padding:8px 10px;border:1px solid #BDBDBD;border-radius:7px;background:white;color:#212121;text-decoration:none;cursor:pointer}.deo-change-share .fb{background:#1877F2;border-color:#1877F2;color:white;font-weight:700}</style>')
    page = re.sub(r'<style id="deo-office-changes-style">.*?</style>', '', page, flags=re.S)
    page = page.replace('</head>', css + '</head>', 1)
    hero_start = page.find('<section id="report-hero"')
    hero_end = page.find('</section>', hero_start) + len('</section>') if hero_start >= 0 else -1
    if hero_end > len('</section>'):
        page = page[:hero_end] + '\n' + section + page[hero_end:]
    else:
        page = page.replace('</main>', section + '</main>')
    jump = '<a href="#deo-office-changes">Office changes · 61</a>'
    page = page.replace(jump, '')
    PAGE.write_text(page, encoding='utf-8')
    page = PAGE.read_text(encoding='utf-8')
    page = re.sub(r'<script id="deo-office-changes-script"[^>]*></script>', '', page)
    version = hashlib.sha256(MAP_JS.read_bytes()).hexdigest()[:12]
    page = page.replace('</body>', f'<script id="deo-office-changes-script" src="dpwh-deo-office-changes.js?v={version}" defer></script></body>', 1)
    PAGE.write_text(page, encoding='utf-8')
    print(f'Wrote {len(records)} office-change candidates ({len(mapped)} coordinate-mappable; {len(unmapped)} listed on DPWH page).')


if __name__ == '__main__':
    main()
