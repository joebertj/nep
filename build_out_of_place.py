#!/usr/bin/env python3
"""Build an interactive map of coordinate-bearing HGAB DPWH DEO/LEG projects."""
import hashlib
import csv
import html
import json
import math
import re
import subprocess
import sys
import shutil
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
TAILWIND_VERSION = hashlib.sha256((ROOT.parent / 'open-data-visualization/static/css/tailwind.css').read_bytes()).hexdigest()[:12]
SOURCE = ROOT / 'hb10858_3rd_dpwh_projects.json'
OUT_DATA = ROOT / 'analysis_output/out_of_place_projects.json'
OUT_BOUNDARIES = ROOT / 'analysis_output/out-of-place-boundaries.json'
OUT_JS = ROOT / 'analysis_output/out-of-place.js'
STATIC_DATA = STATIC / 'out-of-place-data.json'
STATIC_JS = STATIC / 'out-of-place.js'
STATIC_BOUNDARIES = STATIC / 'out-of-place-boundaries.json'
SHARE_DIR = STATIC / 'out-of-place-share'
PORTRAIT_CACHE = ROOT / '.cache/out_of_place_portraits'
OUT_HTML = ROOT / 'analysis_output/out-of-place.html'
STATIC_HTML = STATIC / 'out-of-place.html'

sys.path.insert(0, str(ROOT))
from analyze_mpb_proximity import coordinates, utm51_to_wgs84
from build_mpb_report import _leg_profile_index, _representative_cards

DEO_LEG = re.compile(r'\b(?:DEO|LEG)\b', re.I)


def main():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    mpb_audit_path = ROOT / 'analysis_output/mpb_proximity.json'
    mpb_audit_ids = set()
    if mpb_audit_path.exists():
        mpb_audit_ids = {str(item.get('projectId')) for item in json.loads(mpb_audit_path.read_text()).get('coordinateAudit', []) if item.get('projectId')}
    boundary_source = ROOT / 'data_sources/arcgis_dpwh/archive/selected/city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
    boundary_rows = [json.loads(line) for line in boundary_source.read_text(encoding='utf-8').splitlines()]
    province_names = sorted({row.get('attributes', {}).get('PROV_DBM') for row in boundary_rows if row.get('attributes', {}).get('PROV_DBM')}, key=len, reverse=True)

    def norm(value):
        import unicodedata
        value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
        return re.sub(r'[^a-z0-9]+', ' ', value).strip()

    def named_province(text):
        value = norm(text)
        for name in province_names:
            if norm(name) in value:
                return name
        if 'metro manila' in value:
            return 'Metropolitan Manila'
        return None

    def convert_rings(rings, thin_tolerance=None):
        converted = []
        for ring in rings or []:
            points = [utm51_to_wgs84(point[0], point[1]) for point in ring if len(point) >= 2]
            if thin_tolerance and len(points) > 4:
                kept = [points[0]]
                for point in points[1:-1]:
                    previous = kept[-1]
                    cos_lat = max(0.2, __import__('math').cos(__import__('math').radians(point[1])))
                    if __import__('math').hypot((point[0] - previous[0]) * cos_lat, point[1] - previous[1]) >= thin_tolerance:
                        kept.append(point)
                if len(kept) < 3:
                    kept = [points[0], points[len(points)//3], points[2*len(points)//3]]
                if points[-1] != kept[0]:
                    kept.append(kept[0])
                points = kept
            converted.append(points)
        return converted

    projects = []
    office_change_path = ROOT / 'analysis_output/dpwh_deo_office_changes.json'
    office_changes = json.loads(office_change_path.read_text(encoding='utf-8')) if office_change_path.exists() else {'records': []}
    office_change_by_id = {item['hgabProjectId']: item for item in office_changes.get('records', []) if item.get('hgabProjectId')}
    for row in source['data']['data']:
        title = str(row.get('projectName') or '')
        office = str(row.get('office') or '')
        combined = ' '.join((title, office, str(row.get('sourceText') or '')))
        explicit_deo_leg = DEO_LEG.search(combined)
        mpb_coordinate_audit = str(row.get('id')) in mpb_audit_ids
        office_change = office_change_by_id.get(str(row.get('id')))
        if not (explicit_deo_leg or mpb_coordinate_audit or office_change):
            continue
        point = coordinates(title)
        if point.get('latitude') is None or point.get('longitude') is None:
            continue
        project_province = named_province(' '.join((title, office)))
        projects.append({
            'id': row['id'],
            'projectName': title,
            'office': office,
            'amountPesos': int(row.get('amountPesos') or 0),
            'sourceVolume': row.get('sourceVolume'),
            'sourcePage': row.get('sourcePage'),
            'coordinateRaw': point['raw'],
            'latitude': point['latitude'],
            'longitude': point['longitude'],
            'coordinateStatus': point['status'],
            'coordinateOrientation': point['orientation'],
            'province': project_province,
        })
        if str(row['id']) in office_change_by_id:
            projects[-1]['officeAssignmentChange'] = office_change_by_id[str(row['id'])]
    projects.sort(key=lambda row: (row.get('sourcePage') or 0, row['id']))
    comparison_path = ROOT / 'analysis_output/hb_nep_comparison_3rd.csv'
    comparison_by_id = {}
    repeated_amount_groups = {}
    if comparison_path.exists():
        with comparison_path.open(encoding='utf-8-sig', newline='') as source_csv:
            comparison_rows = list(csv.DictReader(source_csv))
        for compare in comparison_rows:
            project_id = compare.get('hgab_id')
            if project_id:
                comparison_by_id[project_id] = compare
            try:
                amount_key = (str(compare.get('pap3') or compare.get('pap2') or 'Unclassified').strip(), int(float(compare.get('amountPesos') or 0)))
            except (TypeError, ValueError):
                continue
            group = repeated_amount_groups.setdefault(amount_key, {'ids': set(), 'offices': set()})
            if project_id:
                group['ids'].add(project_id)
            if compare.get('office'):
                group['offices'].add(compare['office'])
        for project in projects:
            compare = comparison_by_id.get(project['id'])
            flags = []
            if compare:
                status = compare.get('comparison', '')
                nep_title = compare.get('closest_nep_title', '')
                try:
                    nep_amount = int(float(compare.get('closest_nep_amount_pesos') or 0))
                    delta = int(float(compare.get('amount_delta_pesos') or 0))
                except (TypeError, ValueError):
                    nep_amount, delta = 0, 0
                project['nepComparison'] = {'status': status, 'title': nep_title, 'amountPesos': nep_amount, 'allocationDeltaPesos': delta}
                if 'No plausible NEP title counterpart' in status:
                    flags.append({'label': 'Potential NEP insertion', 'detail': 'Current comparison found no plausible NEP title counterpart. Confirm against the source schedules.'})
                elif 'Plausible NEP title counterpart' in status:
                    flags.append({'label': 'NEP counterpart needs scope review', 'detail': f'Possible counterpart: {nep_title}. Title similarity does not confirm identical scope.'})
                if delta:
                    direction = 'increase' if delta > 0 else 'decrease'
                    flags.append({'label': f'Allocation {direction}: {abs(delta):,} pesos', 'detail': f'Compared with the current NEP counterpart amount of ₱{nep_amount:,}.'})
            office_change = project.get('officeAssignmentChange')
            if office_change:
                flags.append({'label': 'Implementing office changed between NEP and HGAB', 'detail': f"NEP: {office_change['nepOffice']} → HGAB 3rd: {office_change['hgabOffice']}. CSIIIV comparison status: {office_change['status']}."})
            pap = str(compare.get('pap3') or compare.get('pap2') or 'Unclassified').strip() if compare else 'Unclassified'
            group = repeated_amount_groups.get((pap, project['amountPesos']), {'ids': set(), 'offices': set()})
            if len(group['ids']) >= 3 and len(group['offices']) >= 3:
                flags.append({'label': f'Repeated allocation amount · {len(group["ids"])} projects', 'detail': f'₱{project["amountPesos"]:,} also appears in {pap} across {len(group["offices"])} offices in HGAB 3rd. These are project allocations, not comparable unit prices.'})
            project['analysisFlags'] = flags
    attribution_path = ROOT / 'analysis_output/congress_geographic_attribution_db_3rd.json'
    attribution = json.loads(attribution_path.read_text(encoding='utf-8'))
    attribution_by_id = {row.get('id'): row for row in attribution.get('projects', [])}
    profile_source, profile_index = _leg_profile_index()
    for project in projects:
        geo = attribution_by_id.get(project['id'], {})
        project['geographicAttributionStatus'] = geo.get('status', 'unresolved')
        project['districts'] = geo.get('districts') or []
        project['representativeCards'] = _representative_cards(geo, profile_index, profile_source)
        project['geographicEvidence'] = geo.get('geographicEvidence') or []
    SHARE_DIR.mkdir(parents=True, exist_ok=True)
    PORTRAIT_CACHE.mkdir(parents=True, exist_ok=True)
    for row in projects:
        suffix = hashlib.sha256(row['id'].encode()).hexdigest()[:8]
        words = re.sub(r'[^a-z0-9]+', '-', row['projectName'].lower()).strip('-')[:52].strip('-')
        row['shareSlug'] = f'{words or "deo-leg-project"}-{suffix}'
    portrait_files = {}
    def is_portrait_image(path):
        if not path.is_file() or path.stat().st_size < 4:
            return False
        signature = path.read_bytes()[:8]
        return signature.startswith(b'\x89PNG\r\n\x1a\n') or signature.startswith(b'\xff\xd8\xff')
    for row in projects:
        first_cached_photo = None
        for card in row.get('representativeCards', []):
            photo_url = card.get('photoUrl')
            if not photo_url:
                continue
            photo_digest = hashlib.sha256(photo_url.encode()).hexdigest()[:16]
            cached_photo = PORTRAIT_CACHE / f'{photo_digest}.image'
            if not is_portrait_image(cached_photo):
                try:
                    request = urllib.request.Request(photo_url, headers={'User-Agent': 'BetterGov share-card builder'})
                    with urllib.request.urlopen(request, timeout=20) as response:
                        photo_data = response.read()
                    if not photo_data.startswith((b'\x89PNG\r\n\x1a\n', b'\xff\xd8\xff')):
                        raise ValueError('portrait response is not a PNG or JPEG image')
                    cached_photo.write_bytes(photo_data)
                except Exception as error:
                    print(f'Could not cache representative portrait for {row["id"]}: {error}', file=sys.stderr)
                    continue
            signature = cached_photo.read_bytes()[:8]
            public_ext = '.png' if signature.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg'
            public_name = f'representative-{photo_digest}{public_ext}'
            public_photo = SHARE_DIR / public_name
            if not is_portrait_image(public_photo) or public_photo.read_bytes() != cached_photo.read_bytes():
                shutil.copyfile(cached_photo, public_photo)
            card['cachedPhotoUrl'] = f'out-of-place-share/{public_name}'
            if first_cached_photo is None:
                first_cached_photo = str(cached_photo)
        if first_cached_photo:
            portrait_files[row['id']] = first_cached_photo
    payload = {
        'title': 'Coordinate-bearing DEO/LEG projects in the HGAB 3rd-reading DPWH schedule',
        'count': len(projects),
        'method': 'Includes project rows whose title, office, or source text contains DEO/LEG text, or is listed in the MPB coordinate audit, and whose title contains exactly one unambiguous decimal coordinate pair within the Philippines. Coordinates are plotted as printed; the point itself does not establish the intended administrative district or prove an error.',
        'source': {
            'file': 'hb10858_3rd_dpwh_projects.json',
            'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'stage': 'HGAB 3rd reading',
        },
        'reviewFlagBasis': {'file': str(comparison_path.relative_to(ROOT)), 'sha256': hashlib.sha256(comparison_path.read_bytes()).hexdigest() if comparison_path.exists() else None, 'note': 'Counterpart and repeated-amount flags are review signals; exact repeated allocations are not construction unit prices.'},
        'projects': projects,
    }
    relevant_provinces = {project['province'] for project in projects if project.get('province')}
    national_features, focused_features = [], []
    for boundary in boundary_rows:
        attrs = boundary.get('attributes', {})
        province = attrs.get('PROV_DBM')
        rings = boundary.get('geometry', {}).get('rings') or []
        if not rings:
            continue
        geo_rings = convert_rings(rings)
        bboxes = []
        for geo_ring in geo_rings:
            if geo_ring:
                bboxes.append((min(p[0] for p in geo_ring), max(p[0] for p in geo_ring),
                               min(p[1] for p in geo_ring), max(p[1] for p in geo_ring)))
        nearby_ids = []
        for project in projects:
            lat, lon = project['latitude'], project['longitude']
            cos_lat = max(0.2, math.cos(math.radians(lat)))
            distance = min((math.hypot(max(min_lon-lon, 0, lon-max_lon)*cos_lat,
                                       max(min_lat-lat, 0, lat-max_lat))
                            for min_lon, max_lon, min_lat, max_lat in bboxes), default=float('inf'))
            if distance <= 0.55:
                nearby_ids.append(project['id'])
        if province in relevant_provinces or nearby_ids:
            focused_features.append({
                'key': str(attrs.get('OBJECTID') or f'{province}-{attrs.get("MUNICIPAL")}'),
                'province': province,
                'city': attrs.get('MUNICIPAL') if str(attrs.get('CENTERS') or '').strip().lower() == 'city' else None,
                'municipality': attrs.get('MUN_DBM') or attrs.get('MUNICIPAL'),
                'nearbyProjectIds': nearby_ids,
                'rings': geo_rings,
            })
        national_features.append({'rings': convert_rings(rings, thin_tolerance=0.025)})
    boundary_data = {
        'source': 'DPWH ArcGIS City-Municipal Boundaries; archived locally in EPSG:32651, converted to WGS84 for map display.',
        'sourceFile': str(boundary_source.relative_to(ROOT)),
        'sourceSha256': hashlib.sha256(boundary_source.read_bytes()).hexdigest(),
        'national': national_features,
        'provinceFeatures': focused_features,
    }
    STATIC_BOUNDARIES.write_text(json.dumps(boundary_data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    OUT_BOUNDARIES.write_text(json.dumps(boundary_data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    STATIC_JS.write_text(JS, encoding='utf-8')
    OUT_JS.write_text(JS, encoding='utf-8')
    cache_payload = Path('/private/tmp/out-of-place-map-cache-payload.json')
    cache_payload.write_text(json.dumps({**payload, 'portraitFiles': portrait_files}, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    swift_cache = Path('/private/tmp/odv-swift-module-cache')
    swift_cache.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        'swift', '-module-cache-path', str(swift_cache),
        str(ROOT / 'build_out_of_place_share_cards.swift'),
        str(cache_payload), str(STATIC_BOUNDARIES), str(SHARE_DIR),
    ], check=True, capture_output=True, text=True)
    og_share_card = STATIC / 'out-of-place-share-card.png'
    subprocess.run([
        'swift', '-module-cache-path', str(swift_cache),
        str(ROOT / 'build_out_of_place_og_card.swift'),
        str(cache_payload), str(STATIC_BOUNDARIES), str(og_share_card),
    ], check=True, capture_output=True, text=True)
    og_image_url = 'https://research.bettergov.ph/static/nep-preview/out-of-place-share-card.png?v=' + hashlib.sha256(og_share_card.read_bytes()).hexdigest()[:12]
    image_base = 'https://research.bettergov.ph/static/nep-preview/out-of-place-share/'
    page_base = image_base
    for row in projects:
        slug = row['shareSlug']
        image_path = SHARE_DIR / f'{slug}.png'
        version = hashlib.sha256(image_path.read_bytes()).hexdigest()[:12]
        row['shareImage'] = f'{image_base}{slug}.png?v={version}'
        row['sharePage'] = f'{page_base}{slug}.html?v={version}'
        row['interactivePage'] = f'../out-of-place.html?project={row["id"]}'
        title = html.escape(row['projectName'], quote=True)
        rep = (row.get('representativeCards') or [{}])[0]
        rep_text = (f'Geographic representative: {rep.get("name") or rep.get("officialName")} · {rep.get("district")}. ' if rep.get('name') or rep.get('officialName') else 'No geographic representative resolved. ')
        description = html.escape(f'{row["office"]} · {rep_text}Printed coordinate {row["coordinateRaw"]}. Geographic coverage is not sponsorship.', quote=True)
        page_url = html.escape(row['sharePage'], quote=True)
        image_url = html.escape(row['shareImage'], quote=True)
        interactive = html.escape(row['interactivePage'], quote=True)
        reps_html = ''.join(f'<article class="face"><img src="{html.escape(Path(str(card.get("cachedPhotoUrl") or card.get("photoUrl") or "")).name, quote=True)}" alt="Official photo of {html.escape(str(card.get("name") or card.get("officialName") or "representative"), quote=True)}" loading="lazy"><div><strong>{html.escape(str(card.get("name") or card.get("officialName") or "Representative"))}</strong><span>{html.escape(str(card.get("district") or "Geographic district"))}</span><a href="{html.escape(str(card.get("profileUrl") or "#"), quote=True)}">Official profile ↗</a></div></article>' for card in row.get('representativeCards', []) if card.get('photoUrl'))
        reps_html = reps_html or '<p>No geographic representative was resolved for this coordinate.</p>'
        share_html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Out of place? · {title}</title><meta name="description" content="{description}"><meta property="og:type" content="website"><meta property="og:url" content="{page_url}"><meta property="og:title" content="Out of place? · {title}"><meta property="og:description" content="{description}"><meta property="og:image" content="{image_url}"><meta property="og:image:secure_url" content="{image_url}"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="Map showing the printed project coordinate among DEO/LEG coordinate-bearing projects"><meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Out of place? · {title}"><meta name="twitter:description" content="{description}"><meta name="twitter:image" content="{image_url}"><link id="bettergov-tailwind-style" rel="stylesheet" href="../../css/tailwind.css?v={TAILWIND_VERSION}"><style>body{{margin:0;padding:28px;background:#FAFAFA;color:#212121;font:16px/1.5 system-ui,sans-serif}}main{{max-width:1200px;margin:auto}}img.map{{display:block;width:100%;height:auto;border-radius:14px}}a{{display:inline-block;margin-top:10px;padding:10px 15px;border-radius:8px;background:#0038A8;color:white;text-decoration:none;font-weight:700}}p{{color:#616161}}.face{{display:flex;gap:14px;align-items:center;margin:16px 0;padding:14px;border:1px solid #E0E0E0;border-radius:12px;background:white;max-width:480px}}.face img{{width:84px;height:100px;object-fit:cover;border-radius:8px;background:#EEEEEE}}.face span{{display:block;color:#616161}}.face a{{color:#0038A8;background:none;padding:4px 0}}</style></head><body><main><h1>Out of place? · {title}</h1><img class="map" src="{slug}.png" width="1200" height="630" alt="Cached project coordinate map"><h2>Geographic representative</h2>{reps_html}<a href="{interactive}">Open interactive map and project card ↗</a><p>{description} Proposed allocation. Coordinate signals are review leads, not findings.</p></main></body></html>'''
        (SHARE_DIR / f'{slug}.html').write_text(share_html, encoding='utf-8')
    final_data = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    STATIC_DATA.write_text(final_data, encoding='utf-8')
    OUT_DATA.write_text(final_data, encoding='utf-8')
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
    base = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Out of place? · Coordinate review</title>
<meta name="description" content="Review HGAB 3rd-reading DPWH projects with DEO or LEG text and printed coordinates on a map, one project at a time, including MPB coordinate-audit candidates.">
<meta property="og:type" content="website"><meta property="og:url" content="https://research.bettergov.ph/static/nep-preview/out-of-place.html"><meta property="og:title" content="Out of place? · DPWH coordinate review"><meta property="og:description" content="Explore HGAB 3rd-reading DPWH projects whose printed coordinates fall outside a project-named locality. Compare the intended place with the coordinate landing area and nearby municipalities. Location signals are review leads, not findings."><meta property="og:image" content="__OG_IMAGE_URL__"><meta property="og:image:secure_url" content="__OG_IMAGE_URL__"><meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630"><meta property="og:image:alt" content="Philippines map of HGAB 3rd DPWH coordinate review projects alongside intended locations">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="Out of place? · DPWH coordinate review"><meta name="twitter:description" content="Compare printed DPWH project coordinates with named localities. Location signals are review leads, not findings."><meta name="twitter:image" content="__OG_IMAGE_URL__">
<style>

:root{color-scheme:light;--ink:#212121;--muted:#616161;--line:#E0E0E0;--teal:#0038A8;--gold:#FCD116;--paper:#FAFAFA}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:26px clamp(16px,4vw,52px) 22px;background:#00246a;color:white}header .eyebrow{margin:0 0 8px;color:#FCD116;font-size:12px;font-weight:750;letter-spacing:.08em;text-transform:uppercase}header h1{margin:0;font-size:clamp(28px,4vw,44px);line-height:1.1}header p{max-width:900px;margin:12px 0 0;color:#f5f5f5}
nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}nav a{padding:6px 10px;border:1px solid #ffffff55;border-radius:8px;color:#FCD116;text-decoration:none;font-size:13px}nav a:hover{background:#ffffff12;color:white}
main{box-sizing:border-box;width:100%;max-width:none;margin:0;padding:26px clamp(16px,2vw,32px) 56px}.notice{padding:12px 15px;border-left:4px solid var(--gold);background:#fff9e9;color:#4e4939}.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:16px 0}.toolbar button,.toolbar a,.toolbar select,.toolbar input{font:inherit}.toolbar button,.toolbar select,.toolbar input,.toolbar a{min-height:40px;padding:8px 12px;border:1px solid #BDBDBD;border-radius:8px;background:white;color:var(--ink)}.toolbar button{cursor:pointer}.toolbar button.primary{background:var(--teal);border-color:var(--teal);color:white;font-weight:700}.toolbar .count{margin-left:auto;color:var(--muted);font-size:14px}.workspace{display:grid;grid-template-columns:minmax(0,1.9fr) minmax(320px,.8fr);gap:16px;align-items:start}.panel{border:1px solid var(--line);border-radius:12px;background:#fff;box-shadow:0 3px 14px #19343d0b}.map-panel{padding:12px}.map-heading{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:2px 6px 10px}.map-heading h2{margin:0;font-size:18px}.map-heading span{color:var(--muted);font-size:13px}.map-heading button{padding:6px 9px;border:1px solid #BDBDBD;border-radius:7px;background:#fff;color:var(--ink);cursor:pointer}.map-scale-note{margin:8px 4px 0;color:var(--muted);font-size:12px;line-height:1.45}.map-wrap{overflow:hidden;border:1px solid #E0E0E0;border-radius:9px;background:#FAFAFA}.map-wrap svg{display:block;width:100%;height:auto;min-height:300px}.map-window-title{fill:#0038A8;font:700 15px/1.2 system-ui,sans-serif}.map-feature{fill:#EEEEEE;stroke:#BDBDBD;stroke-width:.055;vector-effect:non-scaling-stroke}.map-feature.nearby-feature{fill:#F5F5F5;stroke:#BDBDBD;stroke-width:.07}.map-feature.intended-area{fill:#DBEAFE;stroke:#0038A8;stroke-width:.12}.map-feature.coordinate-area{fill:#FCD116;stroke:#CE1126;stroke-width:.15}.map-feature.coordinate-area.intended-area{fill:#FCD116;stroke:#0038A8;stroke-width:.22;stroke-dasharray:2 1}.point{cursor:pointer;stroke:white;stroke-width:2;vector-effect:non-scaling-stroke}.point circle{fill:#0038A8}.point text{fill:white;font-size:10px;font-weight:800;text-anchor:middle;dominant-baseline:central;pointer-events:none}.point.selected circle{fill:#CE1126;stroke:#fff;stroke-width:3}.point:hover circle{fill:#CE1126}.map-legend{display:flex;flex-wrap:wrap;gap:7px 15px;padding:9px 7px 1px;color:var(--muted);font-size:13px}.map-legend span{display:inline-flex;align-items:center;gap:6px}.map-legend i{display:inline-block;width:13px;height:13px;border:1px solid #9E9E9E;border-radius:3px;background:#F5F5F5}.map-legend .legend-intended{background:#DBEAFE;border-color:#0038A8}.map-legend .legend-coordinate{background:#FCD116;border-color:#CE1126}.card{padding:18px}.card .map-focus{margin:0 0 8px;padding:6px 9px;border:1px solid #BDBDBD;border-radius:7px;background:#FAFAFA;color:var(--ink);font:inherit;font-size:13px;cursor:pointer}.card .map-focus:hover{background:#EAF0FF}.card-kicker{color:var(--teal);font-size:12px;font-weight:800;letter-spacing:.07em;text-transform:uppercase}.review-flags{display:flex;flex-wrap:wrap;gap:7px;margin:12px 0}.review-flag{display:flex;flex-direction:column;align-items:flex-start;gap:3px;padding:7px 10px;border:1px solid #CE1126;border-radius:8px;background:#FDE8EB;color:#A10E20;font-size:13px;font-weight:700;line-height:1.35}.review-flag::before{content:"⚑";font-size:14px}.review-flag small{font-size:12px;font-weight:500;line-height:1.4}.review-flag.clear{border-color:#BFDBFE;background:#EFF6FF;color:#0038A8}.review-flag.clear::before{content:"✓"}.card h2{margin:8px 0 12px;font-size:22px;line-height:1.25}.card .office{padding:10px 12px;border-radius:8px;background:#EAF0FF;font-weight:700}.representative-section{margin:18px 0;padding:14px;border:1px solid #E0E0E0;border-radius:10px;background:#F5F5F5}.representative-section h3{margin:0 0 10px;font-size:16px}.mpb-member-associations{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}.mpb-member-association{display:flex;gap:12px;align-items:center;padding:12px;border:1px solid #d4dfdc;border-radius:10px;background:#fff}.mpb-member-association>div{display:grid;gap:3px}.mpb-member-portrait{display:block;width:82px;height:110px;object-fit:cover;object-position:top;border-radius:7px;border:1px solid #d4dfdc;background:#edf3f1}.mpb-member-association a:not(.mpb-member-portrait-link){color:#0038A8;font-size:13px;font-weight:700}.representative-caveat{margin:10px 0 0;color:var(--muted);font-size:13px}@media(max-width:650px){.mpb-member-associations{grid-template-columns:1fr}}.facts{display:grid;grid-template-columns:1fr;gap:9px;margin:16px 0}.facts div{padding-bottom:8px;border-bottom:1px solid #EEEEEE}.facts dt{color:var(--muted);font-size:12px}.facts dd{margin:2px 0 0;font-weight:650;overflow-wrap:anywhere}.share{display:flex;gap:9px;flex-wrap:wrap;margin-top:16px}.share a,.share button{display:inline-flex;align-items:center;gap:7px;padding:9px 12px;border:0;border-radius:8px;background:#1877f2;color:white;text-decoration:none;font:inherit;font-weight:750;cursor:pointer}.share button.primary{background:var(--teal);color:white}.share [hidden]{display:none}.share a.copy{background:#EEEEEE;color:var(--ink);border:1px solid var(--line)}.list-panel{margin-top:16px;padding:14px}.list-panel h2{margin:0 0 10px;font-size:18px}.project-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px;max-height:390px;overflow:auto}.project-list button{padding:9px 11px;border:1px solid #E0E0E0;border-radius:8px;background:white;color:var(--ink);text-align:left;cursor:pointer}.project-list button[aria-current=true]{border-color:var(--teal);background:#EAF0FF}.project-list small{display:block;color:var(--muted)}.source{margin-top:18px;padding:14px 16px;border:1px solid var(--line);border-radius:10px;background:#fff;color:var(--muted);font-size:13px}.source a{color:#0038A8}.status{min-height:20px;color:var(--muted);font-size:13px}
@media(max-width:850px){.workspace{grid-template-columns:1fr}.map-wrap svg{min-height:300px}.card{order:0}}@media(max-width:520px){header{padding-top:20px}.toolbar .count{width:100%;margin-left:0}.map-wrap svg{min-height:250px}.card h2{font-size:19px}}

</style></head><body class="out-of-place-theme"><header><div class="eyebrow">BetterGov · DPWH coordinate review</div><h1>Out of place?</h1><p>Projects whose printed coordinates fall outside a project-named municipality or city. The source includes DEO/LEG references and full District Engineering Office names. Select a point to compare the intended locality with the landing area and adjacent places.</p><nav aria-label="Budget report pages"><a href="mpb.html">MPB map</a><a href="dpwh.html">DPWH POWs</a><a href="dpwh-hgab.html">NEP → HGAB (3rd)</a><a href="congress.html">District allocations</a></nav></header>
<main><aside id="report-evidence-notice" class="notice" role="note"><strong>Evidence limits.</strong> Coordinates are taken from HGAB 3rd project titles and plotted against cached DPWH/NAMRIA-derived municipal and city boundaries. A plotted coordinate or geographic representative association is a review lead, not proof of an incorrect location, project sponsorship, payment, or wrongdoing. Verify the printed coordinates, named place, boundary source and cited schedule page before drawing conclusions.</aside><div class="toolbar"><button id="previous" type="button">← Previous</button><button id="next" class="primary" type="button">Next project →</button><label for="search">Find a project</label><input id="search" type="search" placeholder="Project, office, province…"><span id="count" class="count"></span></div>
<div class="workspace"><section class="panel map-panel"><div class="map-heading"><h2>Project location map</h2><span id="map-view-label">Selected project · intended, landing and adjacent areas</span><button id="reset-map" type="button">Philippines overview</button></div><div id="map" class="map-wrap" aria-label="Single map showing the intended project area, printed coordinate landing area, and adjacent localities"></div><p class="map-scale-note">The map shows the intended project locality, coordinate landing locality and adjacent places together. It uses one geographic scale, so widely separated areas may appear small.</p><div class="map-legend"><span><i class="legend-intended"></i>Project-named intended area</span><span><i class="legend-coordinate"></i>Coordinate landing area</span><span><i></i>Adjacent localities</span></div></section><article id="project-card" class="panel card" aria-live="polite"></article></div>
<section class="panel list-panel"><h2>Projects outside intended localities</h2><div id="project-list" class="project-list"></div></section>
<aside class="source"><strong>Method and source</strong><p id="method"></p><p>Source: HGAB 3rd-reading DPWH project schedule, PDF page shown on each card. This is an appropriation listing, not verified spending. <a href="out-of-place-data.json">Open parsed project data ↗</a></p><p id="status" class="status" aria-live="polite"></p></aside></main>
<script>window.OUT_OF_PLACE_DATA = __DATA__;</script><script src="out-of-place.js?v=__JS_VERSION__"></script></body></html>'''
    page_html = base.replace('__DATA__', serialized).replace('__JS_VERSION__', hashlib.sha256(JS.encode('utf-8')).hexdigest()[:12]).replace('__OG_IMAGE_URL__', html.escape(og_image_url, quote=True))
    # Use the same shared BetterGov research theme and presentation assets as
    # the original ODV report pages (the Tailwind config has no custom palette).
    from report_table_presentation import publish_assets, apply_page as apply_shared_report_theme
    page_html = apply_shared_report_theme(page_html, publish_assets())
    from uniform_report_menu import apply_page as apply_generic_report_menu
    page_html = apply_generic_report_menu(page_html, 'out-of-place.html')
    page_brand_style = '''<style id="out-of-place-bettergov-brand-style">
body.out-of-place-theme{--ink:#212121!important;--muted:#616161!important;--line:#E0E0E0!important;--teal:#0038A8!important;--gold:#FCD116!important;--paper:#FAFAFA!important;--research-ink:#212121!important;--research-muted:#616161!important;--research-teal:#0038A8!important;--research-line:#E0E0E0!important;--research-ground:#FAFAFA!important;background:#FAFAFA!important;color:#212121!important}
body.out-of-place-theme>main{box-sizing:border-box!important;width:100%!important;max-width:none!important;margin:0!important;padding:26px clamp(16px,2vw,32px) 56px!important}
body.out-of-place-theme>header{background:linear-gradient(115deg,#00246A 0%,#0038A8 100%)!important;border-bottom-color:#FCD116!important}
body.out-of-place-theme>header .eyebrow{color:#FCD116!important}body.out-of-place-theme>header p{color:#F5F5F5!important}
body.out-of-place-theme>header .report-nav a,body.out-of-place-theme>header .report-nav a:visited{color:#FCD116!important}body.out-of-place-theme>header .report-nav a:hover{color:#fff!important;border-color:#FCD116!important}
body.out-of-place-theme #report-evidence-notice{border-left-color:#0038A8!important;background:#EAF0FF!important;color:#212121!important}
body.out-of-place-theme .toolbar{background:#F5F5F5!important;border-color:#E0E0E0!important}
body.out-of-place-theme :is(button,a,input,select):focus-visible{outline-color:#FCD116!important}
body.out-of-place-theme .map-feature{fill:#EEEEEE!important;stroke:#BDBDBD!important}body.out-of-place-theme .map-feature.nearby-feature{fill:#F5F5F5!important;stroke:#9E9E9E!important}
body.out-of-place-theme .map-feature.intended-area{fill:#DBEAFE!important;stroke:#0038A8!important}body.out-of-place-theme .map-feature.coordinate-area{fill:#FCD116!important;stroke:#CE1126!important}
body.out-of-place-theme .map-feature.coordinate-area.intended-area{fill:#FCD116!important;stroke:#0038A8!important}
body.out-of-place-theme .map-wrap{background:#FAFAFA!important;border-color:#E0E0E0!important}body.out-of-place-theme .map-scale-note{color:#616161!important}
body.out-of-place-theme .map-legend i{background:#F5F5F5!important;border-color:#9E9E9E!important}body.out-of-place-theme .map-legend .legend-intended{background:#DBEAFE!important;border-color:#0038A8!important}body.out-of-place-theme .map-legend .legend-coordinate{background:#FCD116!important;border-color:#CE1126!important}
body.out-of-place-theme .review-flag{background:#FDE8EB!important;border-color:#CE1126!important;color:#A10E20!important}body.out-of-place-theme .review-flag.clear{background:#EFF6FF!important;border-color:#BFDBFE!important;color:#0038A8!important}
body.out-of-place-theme .card-kicker,body.out-of-place-theme .source a,body.out-of-place-theme .representative-facecard .face-profile{color:#0038A8!important}
body.out-of-place-theme .office{background:#EAF0FF!important}body.out-of-place-theme .representative-section{background:#F5F5F5!important;border-color:#E0E0E0!important}
body.out-of-place-theme .mpb-member-association{background:#fff!important}body.out-of-place-theme .mpb-member-portrait{background:#EEEEEE!important}
body.out-of-place-theme .map-point circle,body.out-of-place-theme .point circle{fill:#0038A8!important}body.out-of-place-theme .point.selected circle{fill:#CE1126!important}body.out-of-place-theme .point:hover circle{fill:#FCD116!important}
</style>'''
    page_html = page_html.replace('</head>', page_brand_style + '</head>', 1)
    STATIC_HTML.write_text(page_html, encoding='utf-8')
    OUT_HTML.write_text(page_html, encoding='utf-8')
    print(json.dumps({'projectCount': len(projects), 'cachedSharePages': len(projects), 'cachedMapImages': len(projects), 'html': str(STATIC_HTML), 'data': str(STATIC_DATA)}, indent=2))


JS = r'''(() => {
  const data = window.OUT_OF_PLACE_DATA;
  const allProjects = data.projects || [];
  let projects = [];
  const mapNode = document.getElementById('map');
  const card = document.getElementById('project-card');
  const listNode = document.getElementById('project-list');
  const countNode = document.getElementById('count');
  const status = document.getElementById('status');
  const search = document.getElementById('search');
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const norm = value => String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim();
  function pointInRings(lon,lat,rings){let inside=false;for(const ring of rings||[]){let hit=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>lat)!==(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)hit=!hit;}if(hit)inside=!inside;}return inside;}
  const money = value => '₱' + Number(value || 0).toLocaleString('en-PH');
  const params = new URLSearchParams(location.search);
  let selected = 0;
  let boundaries = {national:[],provinceFeatures:[]};
  document.getElementById('method').textContent = data.method;
  function shareUrl(project) { return project.sharePage || new URL('?project=' + encodeURIComponent(project.id), location.href).href; }
  let focused = true;
  function mapPoint(lon, lat, bounds, rect={x:0,y:0,w:1200,h:680}) {
    const pad=42,centerLat=(bounds.minLat+bounds.maxLat)/2,cos=Math.max(.2,Math.cos(centerLat*Math.PI/180));
    const rx=Math.max(.002,(bounds.maxLon-bounds.minLon)*cos),ry=Math.max(.002,bounds.maxLat-bounds.minLat),scale=Math.min((rect.w-2*pad)/rx,(rect.h-2*pad)/ry);
    const usedW=rx*scale,usedH=ry*scale,left=rect.x+(rect.w-usedW)/2,bottom=rect.y+(rect.h-usedH)/2;
    return {x:left+((lon-bounds.minLon)*cos)*scale,y:rect.y+rect.h-bottom-(lat-bounds.minLat)*scale};
  }
  let boundaryBoxCache = new WeakMap();
  function featureBounds(feature) {
    if (boundaryBoxCache.has(feature)) return boundaryBoxCache.get(feature);
    const box={minLon:Infinity,maxLon:-Infinity,minLat:Infinity,maxLat:-Infinity};
    for(const ring of feature.rings||[]) for(const [lon,lat] of ring){box.minLon=Math.min(box.minLon,lon);box.maxLon=Math.max(box.maxLon,lon);box.minLat=Math.min(box.minLat,lat);box.maxLat=Math.max(box.maxLat,lat);}
    boundaryBoxCache.set(feature,box);return box;
  }
  function featureGap(a,b) { return {x:Math.max(0,a.minLon-b.maxLon,b.minLon-a.maxLon),y:Math.max(0,a.minLat-b.maxLat,b.minLat-a.maxLat)}; }
  function neighborsOf(anchor, pool) {
    if(!anchor)return [];
    const anchorBounds=featureBounds(anchor),limit=.035;
    let neighbors=pool.filter(f=>f!==anchor).filter(f=>{const gap=featureGap(anchorBounds,featureBounds(f));return gap.x<=limit&&gap.y<=limit;});
    if(!neighbors.length) neighbors=pool.filter(f=>f!==anchor).map(f=>({f,g:featureGap(anchorBounds,featureBounds(f))})).sort((a,b)=>Math.hypot(a.g.x,a.g.y)-Math.hypot(b.g.x,b.g.y)).slice(0,1).map(x=>x.f);
    return neighbors;
  }
  function localityFeatures(project) {
    const all=boundaries.provinceFeatures||[];
    const containing=all.find(f=>pointInRings(project.longitude,project.latitude,f.rings));
    const candidates=containing?all.filter(f=>norm(f.province)===norm(containing.province)):all.filter(f=>norm(f.province)===norm(project.province)||(f.nearbyProjectIds||[]).includes(project.id));
    const pool=candidates.length?candidates:all;
    const anchor=containing||pool.slice().sort((a,b)=>{
      const pointBox={minLon:project.longitude,maxLon:project.longitude,minLat:project.latitude,maxLat:project.latitude};
      const ga=featureGap(pointBox,featureBounds(a)),gb=featureGap(pointBox,featureBounds(b));
      return Math.hypot(ga.x*Math.cos(project.latitude*Math.PI/180),ga.y)-Math.hypot(gb.x*Math.cos(project.latitude*Math.PI/180),gb.y);
    })[0];
    return {features:anchor?[anchor,...neighborsOf(anchor,pool)]:[],containing,anchor};
  }
  function intendedLocalityFeatures(project) {
    const all=boundaries.provinceFeatures||[];
    const named=all.filter(f=>isNamedIntendedLocality(project,f)).sort((a,b)=>(Number(norm(b.province)===norm(project.province))-Number(norm(a.province)===norm(project.province)))||((b.city||b.municipality||'').length-(a.city||a.municipality||'').length));
    if(named.length){
      const anchor=named[0],pool=all.filter(f=>norm(f.province)===norm(anchor.province));
      return {features:[anchor,...neighborsOf(anchor,pool)],anchor,target:anchor,resolved:true};
    }
    const province=all.filter(f=>norm(f.province)===norm(project.province));
    return {features:province,anchor:null,target:null,resolved:false};
  }
  function isNamedIntendedLocality(project, feature) {
    const place=feature.city||feature.municipality;
    if(!place)return false;
    const base=norm(String(place).replace(/\s*\(capital\)\s*$/i,''));
    const aliases=new Set([base]);
    if(base.startsWith('city of ')){const name=base.slice(8);aliases.add(name);aliases.add(`${name} city`);}
    if(base.endsWith(' city')){const name=base.slice(0,-5);aliases.add(name);aliases.add(`city of ${name}`);}
    const title=` ${norm(project.projectName)} `;
    return [...aliases].filter(Boolean).some(name=>title.includes(` ${name} `));
  }
  function isOutsideResolvedIntendedLocality(project) {
    const intended=intendedLocalityFeatures(project).target;
    return Boolean(intended && !pointInRings(project.longitude,project.latitude,intended.rings));
  }
  function hasInsertionFlag(project) { return (project.analysisFlags||[]).some(flag=>/potential nep insertion/i.test(flag.label||'')); }
  function nearestBoundary(project, features) {
    const radius=6371008.8, lat0=project.latitude*Math.PI/180, cosLat=Math.cos(lat0);
    let best=null;
    for(const feature of features||[]) {
      let distance=Infinity;
      for(const ring of feature.rings||[]) for(let i=0;i<ring.length;i++) {
        const a=ring[i],b=ring[(i+1)%ring.length];
        const ax=(a[0]-project.longitude)*Math.PI/180*radius*cosLat, ay=(a[1]-project.latitude)*Math.PI/180*radius;
        const bx=(b[0]-project.longitude)*Math.PI/180*radius*cosLat, by=(b[1]-project.latitude)*Math.PI/180*radius;
        const dx=bx-ax,dy=by-ay,den=dx*dx+dy*dy;
        const t=den?Math.max(0,Math.min(1,-(ax*dx+ay*dy)/den)):0;
        distance=Math.min(distance,Math.hypot(ax+t*dx,ay+t*dy));
      }
      if(Number.isFinite(distance)&&(!best||distance<best.meters)) best={feature,meters:distance,inside:pointInRings(project.longitude,project.latitude,feature.rings)};
    }
    return best;
  }
  function formatBoundaryDistance(project, intended) {
    const candidates=intended?.target?[intended.target]:[];
    const nearest=nearestBoundary(project,candidates);
    if(!nearest)return 'Not available: intended locality not resolved from project title';
    const place=nearest.feature.city||nearest.feature.municipality||'mapped locality';
    const distance=nearest.meters<1000?`${Math.max(10,Math.round(nearest.meters/10)*10).toLocaleString('en-PH')} m`:`${(nearest.meters/1000).toFixed(2)} km`;
    return `About ${distance} from the mapped boundary of ${place}`;
  }
  function locationReviewFlags(project, local) {
    const flags=[];
    const landed=local?.containing;
    if(!landed) flags.push('Coordinate is outside the currently mapped municipality/city boundaries');
    else {
      const intended=(local.features||[]).find(feature=>isNamedIntendedLocality(project,feature));
      const landedPlace=landed.city||landed.municipality||'mapped locality';
      if(intended&&intended.key!==landed.key) flags.push(`Coordinate falls in ${landedPlace}, outside the project-named locality ${intended.city||intended.municipality}`);
      if(project.province&&norm(landed.province)!==norm(project.province)) flags.push(`Coordinate falls in ${landed.province}, outside the province named in the project`);
    }
    return flags;
  }
  function renderMap() {
    const project=projects[selected];
    if(!focused||!project){
      drawComparisonMap([{title:'Philippines overview',kind:'overview',features:boundaries.national||[]}],null);
      document.getElementById('map-view-label').textContent=project?'Philippines overview · select a project point to focus the map':'No projects outside a resolved intended locality';
      return;
    }
    const intended=intendedLocalityFeatures(project),landing=localityFeatures(project);
    const intendedTarget=intended.target;
    const landingTarget=landing.containing||null;
    const intendedName=intendedTarget?(intendedTarget.city||intendedTarget.municipality):null;
    const landingName=landing.containing?(landing.containing.city||landing.containing.municipality):null;
    document.getElementById('map-view-label').textContent=`Project ${selected+1} of ${projects.length} · intended, landing and adjacent areas`;
    const combinedFeatures=[...new Map([...(intended.features||[]),...(landing.features||[])].map(feature=>[feature.key,feature])).values()];
    const intendedTitle=intendedName?`intended · ${intendedName}, ${intendedTarget.province}`:`intended area · ${project.province||'province not resolved'}`;
    const landingTitle=landingName?`landing · ${landingName}, ${landingTarget.province}`:'landing · outside mapped municipalities/cities';
    drawComparisonMap([{title:`${intendedTitle} · ${landingTitle} · adjacent localities`,kind:'combined',features:combinedFeatures,target:intendedTarget,landingKey:landingTarget?.key,project}],project);
  }
  function drawComparisonMap(views,selectedProject) {
    const width=1200,height=680,gap=0,outer=12;
    views=views.slice(0,1); // Always render one map canvas with all intended, landing and adjacent areas.
    const viewWidth=width-outer*2;
    let contents='';
    for(let index=0;index<views.length;index++){
      const view=views[index],rect={x:outer+index*(viewWidth+gap),y:outer,w:viewWidth,h:height-outer*2};
      contents+=`<rect x="${rect.x}" y="${rect.y}" width="${rect.w}" height="${rect.h}" rx="12" fill="#fff" stroke="#E0E0E0"/>`;
      contents+=`<text x="${rect.x+16}" y="${rect.y+25}" class="map-window-title">${esc(view.title)}</text>`;
      const mapRect={x:rect.x+8,y:rect.y+38,w:rect.w-16,h:rect.h-46},features=view.features||[];
      const bounds={minLon:Infinity,maxLon:-Infinity,minLat:Infinity,maxLat:-Infinity};
      for(const f of features)for(const ring of f.rings||[])for(const [lon,lat] of ring){bounds.minLon=Math.min(bounds.minLon,lon);bounds.maxLon=Math.max(bounds.maxLon,lon);bounds.minLat=Math.min(bounds.minLat,lat);bounds.maxLat=Math.max(bounds.maxLat,lat);}
      const plottedProject=view.project||null;
      if(plottedProject){bounds.minLon=Math.min(bounds.minLon,plottedProject.longitude);bounds.maxLon=Math.max(bounds.maxLon,plottedProject.longitude);bounds.minLat=Math.min(bounds.minLat,plottedProject.latitude);bounds.maxLat=Math.max(bounds.maxLat,plottedProject.latitude);}
      if(!Number.isFinite(bounds.minLon)){bounds.minLon=116;bounds.maxLon=127.5;bounds.minLat=4;bounds.maxLat=21.5;}
      if(view.kind==='overview'){bounds.minLon=116;bounds.maxLon=127.5;bounds.minLat=4;bounds.maxLat=21.5;}
      if(plottedProject&&features.length){const padx=Math.max(.02,(bounds.maxLon-bounds.minLon)*.12),pady=Math.max(.02,(bounds.maxLat-bounds.minLat)*.12);bounds.minLon-=padx;bounds.maxLon+=padx;bounds.minLat-=pady;bounds.maxLat+=pady;}
      contents+=features.map(feature=>{
        const path=(feature.rings||[]).map(ring=>'M'+ring.map(([lon,lat],i)=>{const q=mapPoint(lon,lat,bounds,mapRect);return (i?'L':'')+q.x.toFixed(1)+','+q.y.toFixed(1);}).join(' ')+'Z').join(' ');
        const intended=(view.kind==='intended'||view.kind==='combined')&&view.target&&feature.key===view.target.key;
        const landing=view.landingKey&&feature.key===view.landingKey;
        const adjacent=(view.kind==='landing'||view.kind==='combined')&&feature.key!==view.landingKey&&feature.key!==view.target?.key;
        const cls=['map-feature',intended?'intended-area':'',landing?'coordinate-area':'',adjacent?'nearby-feature':''].filter(Boolean).join(' ');
        return `<path class="${cls}" fill-rule="evenodd" d="${path}"/>`;
      }).join('');
      if(plottedProject){const q=mapPoint(plottedProject.longitude,plottedProject.latitude,bounds,mapRect);contents+=`<g class="point selected" role="img" aria-label="Printed project coordinate"><title>Printed project coordinate</title><circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="12"/><text x="${q.x.toFixed(1)}" y="${q.y.toFixed(1)}">●</text></g>`;}
      if(view.kind==='overview'){
        contents+=projects.map((item,projectIndex)=>{const q=mapPoint(item.longitude,item.latitude,bounds,mapRect);return `<g class="point" data-index="${projectIndex}" role="button" tabindex="0" aria-label="Project ${projectIndex+1}: ${esc(item.projectName)}"><title>${projectIndex+1}. ${esc(item.projectName)}</title><circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="8"/><text x="${q.x.toFixed(1)}" y="${q.y.toFixed(1)}">${projectIndex+1}</text></g>`;}).join('');
      }
    }
    mapNode.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Map showing the intended project area, printed coordinate landing area and adjacent localities"><rect width="${width}" height="${height}" fill="#FAFAFA"/>${contents}</svg>`;
    mapNode.querySelectorAll('[data-index]').forEach(el=>{el.addEventListener('click',()=>select(Number(el.dataset.index)));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(Number(el.dataset.index));}});});
  }
  function renderCard() {
    const p=projects[selected]; if(!p){card.innerHTML='<p>No project has a coordinate outside a resolved project-named municipality or city.</p>';return;}
    const url=shareUrl(p); const fb='https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(url);
    const local=localityFeatures(p); const intended=intendedLocalityFeatures(p); const reviewFlags=[...(p.analysisFlags||[]),...locationReviewFlags(p,local).map(label=>({label}))];
    const flagsHtml=reviewFlags.length?`<section class="review-flags" aria-label="Project review flags">${reviewFlags.map(flag=>`<div class="review-flag"><strong>${esc(flag.label||flag)}</strong>${flag.detail?`<small>${esc(flag.detail)}</small>`:''}</div>`).join('')}</section>`:'<div class="review-flags"><div class="review-flag clear"><strong>No review flags identified by these screens</strong><small>This is not a certification that the project has no issues.</small></div></div>';
    const reps=p.representativeCards||[];
    const facecards=reps.filter(r=>r.cachedPhotoUrl||r.photoUrl).map(r=>{
      const cachedSrc=r.cachedPhotoUrl||'';
      const remoteSrc=r.photoUrl||'';
      const src=cachedSrc||remoteSrc;
      const fallback=remoteSrc&&remoteSrc!==src?` data-fallback="${esc(remoteSrc)}" onerror="if(this.dataset.fallback){this.onerror=null;this.src=this.dataset.fallback}"`:'';
      return `<div class="mpb-member-association"><a class="mpb-member-portrait-link" href="${esc(r.profileUrl||'#')}" target="_blank" rel="noopener" aria-label="Open official House profile for ${esc(r.name||r.officialName||'representative')}"><img class="mpb-member-portrait" src="${esc(src)}"${fallback} alt="Portrait of ${esc(r.name||r.officialName||'representative')}" loading="lazy"></a><div><strong>${esc(r.name||r.officialName||'Representative')}</strong><span>${esc(r.district||'')}</span>${r.profileUrl?`<a href="${esc(r.profileUrl)}" target="_blank" rel="noopener">House profile ↗</a>`:''}</div></div>`;
    }).join('');
    const facecardHtml=`<section class="representative-section"><h3>Geographic representative</h3>${facecards?`<div class="mpb-member-associations">${facecards}</div>`:'<p>No geographic representative was resolved for this project coordinate.</p>'}<p class="representative-caveat">This is a geographic district association based on the cited location evidence, not evidence of sponsorship.</p></section>`;
    card.innerHTML=`<div class="card-kicker">Project ${selected+1} of ${projects.length} · ${esc(p.coordinateStatus)}</div><button class="map-focus" type="button" id="zoom-to-locality">Focus map ↗</button><h2>${esc(p.projectName)}</h2><div class="office">Listed office: ${esc(p.office || 'Not stated')}</div>${flagsHtml}<dl class="facts"><div><dt>Allocation in HGAB 3rd</dt><dd>${money(p.amountPesos)}</dd></div><div><dt>Named province</dt><dd>${esc(p.province || 'Not resolved from project/office text')}</dd></div><div><dt>Distance to intended locality boundary</dt><dd>${esc(formatBoundaryDistance(p,intended))}</dd></div><div><dt>Source</dt><dd>${esc(p.sourceVolume || 'HGAB 3rd DPWH schedule')}, PDF page ${esc(p.sourcePage)}</dd></div><div><dt>Project ID</dt><dd>${esc(p.id)}</dd></div></dl>${facecardHtml}<p>The map distinguishes the project-named intended area, the coordinate landing area, and neighboring or nearest localities. Distance is measured from the printed coordinate to the intended locality boundary; a plotted point is a review lead, not a finding.</p><div class="share"><button class="primary" type="button" id="native-share">Share project</button><a href="${fb}" target="_blank" rel="noopener" aria-label="Share this project on Facebook"><strong>f</strong> Share on Facebook</a><a class="copy" href="${url}" id="copy-link">Copy project link</a></div>`;
    document.getElementById('zoom-to-locality').addEventListener('click',()=>{focused=true;renderMap();});
    const nativeShare=document.getElementById('native-share');
    if (!navigator.share) nativeShare.hidden=true;
    nativeShare.addEventListener('click', async () => { try { await navigator.share({title:`Out of place? · ${p.projectName}`,text:`${p.office || 'DPWH project'} · HGAB 3rd project coordinate review. A location signal is a review lead, not a finding.`,url}); } catch (error) { if (error?.name !== 'AbortError') status.textContent='Sharing could not be opened. Use Facebook or copy the project link.'; } });
    document.getElementById('copy-link').addEventListener('click', async e => { e.preventDefault(); try { if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(url); else { const input=document.createElement('textarea'); input.value=url; input.style.position='fixed'; input.style.opacity='0'; document.body.append(input); input.select(); const copied=document.execCommand('copy'); input.remove(); if (!copied) throw new Error('Clipboard unavailable'); } status.textContent='Project link copied.'; } catch { status.textContent='Could not copy the link. Open the project share page to copy its address.'; window.open(url,'_blank','noopener'); } });
  }
  card.addEventListener('click', event => {
    if (event.target.closest('a,button,input,select')) return;
    focused=true;
    renderMap();
  });
  function renderList() {
    const term=search.value.trim().toLowerCase();
    const filtered=projects.map((p,i)=>({p,i})).filter(({p})=>!term||`${p.projectName} ${p.office} ${p.id}`.toLowerCase().includes(term));
    countNode.textContent=`${filtered.length} of ${projects.length} projects`;
    listNode.innerHTML=filtered.map(({p,i})=>`<button type="button" data-index="${i}" aria-current="${i===selected}"><strong>${i+1}. ${esc(p.projectName)}</strong><small>${esc(p.office)} · ${esc(p.coordinateRaw)}</small></button>`).join('');
    listNode.querySelectorAll('[data-index]').forEach(node=>node.addEventListener('click',()=>select(Number(node.dataset.index))));
  }
  function select(index) { if(!projects.length)return; selected=(index+projects.length)%projects.length; focused=true; history.replaceState(null,'','?project='+encodeURIComponent(projects[selected].id)); renderMap(); renderCard(); renderList(); }
  document.getElementById('previous').addEventListener('click',()=>select(selected-1));
  document.getElementById('next').addEventListener('click',()=>select(selected+1));
  document.getElementById('reset-map').addEventListener('click',()=>{focused=false;renderMap();});
  search.addEventListener('input',renderList);
  countNode.textContent='Checking project coordinates against mapped intended localities…';
  fetch('out-of-place-boundaries.json').then(r=>r.ok?r.json():Promise.reject()).then(x=>{boundaries=x;projects=allProjects.filter(p=>isOutsideResolvedIntendedLocality(p)||p.officeAssignmentChange);projects.sort((a,b)=>{const insertionOrder=Number(hasInsertionFlag(b))-Number(hasInsertionFlag(a));if(insertionOrder)return insertionOrder;if(hasInsertionFlag(a))return Number(b.amountPesos||0)-Number(a.amountPesos||0);return Number(a.sourcePage||0)-Number(b.sourcePage||0);});document.getElementById('method').textContent='Shows projects whose printed coordinate falls outside a project-named municipality or city, plus projects with an identified NEP-to-HGAB implementing-office change. Office-change projects appear here only when their printed coordinate can be plotted; the full office-change review list is on the DPWH NEP → HGAB page.';selected=Math.max(0,projects.findIndex(p=>p.id===params.get('project')));if(!projects.length)status.textContent='No projects qualify for the map review.';renderCard();renderList();renderMap();}).catch(()=>{status.textContent='Mapped boundaries could not load, so outside projects cannot be verified and are not shown.';boundaries={national:[],provinceFeatures:[]};projects=[];selected=0;renderCard();renderList();renderMap();});
})();'''

if __name__ == '__main__':
    main()
