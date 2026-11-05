"""Build the FY2027 FMR-to-road screen and attach shared place inventories."""
from __future__ import annotations

import json
import math
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
FMR = ROOT / 'analysis_output' / 'fmr_corrected_dataset.json'
ROAD = ROOT / 'data_sources/arcgis_dpwh/archive/selected/road_classification/layers/Road_Classification_FeatureServer_1-b0aa1cb4/features.jsonl'
OUT = ROOT / 'analysis_output' / 'connectivity-fmr-road.json'
SOURCE_DATA = ROOT / 'analysis_output' / 'connectivity-data.json'
SOURCE_ROAD_PROJECTS = ROOT / 'analysis_output' / 'connectivity-road-projects.json'
PAGE = STATIC / 'connectivity.html'
DATA = STATIC / 'connectivity-data.json'
SCRIPT = STATIC / 'connectivity.js'
CELL = 1000.0

JS = r'''(()=>{
  const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x),
    esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  if(location.protocol==='file:'){
    const message='Connectivity data is stored in separate JSON files. Open this page through the local web server (HTTP), not directly as a file.';
    document.getElementById('rows').innerHTML='<tr><td colspan="7">'+message+'</td></tr>';
    document.getElementById('road-project-count').textContent=message;
    return;
  }
  fetch('connectivity-data.json').then(r=>{if(!r.ok)throw Error('connectivity-data.json returned HTTP '+r.status);return r.json()}).then(d=>{
    const rows=d.projects||[],q=document.getElementById('q'),sel=document.getElementById('result'),size=document.getElementById('size'),body=document.getElementById('rows'),pageLabel=document.getElementById('page');
    Object.keys(d.summary||{}).forEach(x=>sel.add(new Option(`${x} (${d.summary[x]})`,x)));
    document.getElementById('road-stats').innerHTML=Object.entries(d.summary||{}).map(([k,v])=>`<div class="stat"><strong>${n(v)}</strong>${esc(k)}</div>`).join('')+`<div class="stat"><strong>${n(rows.length)}</strong>FMR projects · ${n(d.roadFeatures)} DPWH road sections</div>`;
    const order=['Near road · ≤100 m','Review · 100–500 m','Distant · 500 m–1 km','No nearby DPWH classified road · >1 km'],colors=['#25834b','#d2a700','#d66b1f','#b4232e'],max=Math.max(1,...order.map(k=>Number(d.summary?.[k]||0)));
    document.getElementById('road-distance-chart').innerHTML=order.map((label,i)=>{const value=Number(d.summary?.[label]||0);return `<div class="road-chart-row"><span>${esc(label.replace(/^.*· /,''))}</span><div class="road-chart-track"><i style="width:${value/max*100}%;background:${colors[i]}"></i></div><strong>${n(value)}</strong></div>`}).join('');
    let page=0;function draw(){const term=q.value.trim().toLowerCase(),items=rows.filter(x=>(!sel.value||x.result===sel.value)&&(!term||`${x.title} ${x.region} ${x.roadName}`.toLowerCase().includes(term))).sort((a,b)=>Number(b.amountPesos||0)-Number(a.amountPesos||0)),per=Number(size.value),pages=Math.max(1,Math.ceil(items.length/per));page=Math.min(page,pages-1);body.innerHTML=items.slice(page*per,(page+1)*per).map(x=>`<tr><td><button type="button" class="connectivity-map-open" data-connectivity-map="${esc(x.id)}" aria-label="Map FMR and road connection for ${esc(x.title)}">Map</button> ${esc(x.title)}<small>Printed source p. ${esc(x.sourcePage)} · ${esc(x.coordinateBasis)}</small></td><td>${esc(x.region)}</td><td>${esc(x.roadName)}<small>${esc(x.roadClass)} · ${esc(x.roadSection)}</small></td><td class="num">${n(x.startDistanceMeters)}</td><td class="num">${x.endDistanceMeters==null?'—':n(x.endDistanceMeters)}</td><td class="${x.flagTags?.length?'red-flag':''}">${esc(x.result)}${x.flagTags?.length?'<small>Flag tag: nearest endpoint over 1 km from the DPWH classified road network</small>':''}</td><td class="num">${peso(x.amountPesos)}</td></tr>`).join('')||'<tr><td colspan="7">No matching records.</td></tr>';pageLabel.textContent=`${items.length?page*per+1:0}–${Math.min((page+1)*per,items.length)} of ${items.length} · Page ${page+1} of ${pages}`;document.getElementById('prev').disabled=page===0;document.getElementById('next').disabled=page>=pages-1}
    q.addEventListener('input',()=>{page=0;draw()});sel.addEventListener('change',()=>{page=0;draw()});size.addEventListener('change',()=>{page=0;draw()});document.getElementById('prev').onclick=()=>{page--;draw()};document.getElementById('next').onclick=()=>{page++;draw()};draw();
  }).catch(e=>{document.getElementById('rows').innerHTML='<tr><td colspan="8">Connectivity data unavailable: '+esc(e.message||e)+'</td></tr>';});

  // This larger title-screen asset loads independently; it cannot delay the
  // endpoint-distance table above.
  fetch('connectivity-road-projects.json').then(r=>{if(!r.ok)throw Error('connectivity-road-projects.json returned HTTP '+r.status);return r.json()}).then(roadData=>{
    const roadRows=roadData.rows||[],rq=document.getElementById('roadq'),rb=document.getElementById('road-project-rows'),rp=document.getElementById('road-page'),rs=document.getElementById('road-size');
    document.getElementById('road-project-count').textContent=`${n(roadRows.length)} GAA/HGAB road titles pass the rural/remote or national-road title screen. Place status uses DPWH City-Municipal Boundaries; municipality is a provisional remote-area proxy. ${Object.entries(roadData.placeStatusCounts||{}).map(([k,v])=>`${n(v)} ${k}`).join(' · ')}`;
    let roadPage=0;function drawRoad(){const term=rq.value.trim().toLowerCase(),items=roadRows.filter(x=>!term||`${x.title} ${x.source}`.toLowerCase().includes(term)),per=Number(rs.value),pages=Math.max(1,Math.ceil(items.length/per));roadPage=Math.min(roadPage,pages-1);rb.innerHTML=items.slice(roadPage*per,(roadPage+1)*per).map(x=>`<tr><td>FY${x.year}<br>${esc(x.stage)}</td><td>${esc(x.title)}</td><td class="num">${peso(x.amountPesos)}</td><td>${esc(x.source)}</td><td>${esc(x.placeStatus)}${x.matchedPlaces?.length?`<small>${esc(x.matchedPlaces.join(', '))}</small>`:''}</td></tr>`).join('')||'<tr><td colspan="5">No matching projects.</td></tr>';rp.textContent=`${items.length?roadPage*per+1:0}–${Math.min((roadPage+1)*per,items.length)} of ${items.length} · Page ${roadPage+1} of ${pages}`;document.getElementById('road-prev').disabled=roadPage===0;document.getElementById('road-next').disabled=roadPage>=pages-1}
    rq.addEventListener('input',()=>{roadPage=0;drawRoad()});rs.addEventListener('change',()=>{roadPage=0;drawRoad()});document.getElementById('road-prev').onclick=()=>{roadPage--;drawRoad()};document.getElementById('road-next').onclick=()=>{roadPage++;drawRoad()};drawRoad();
  }).catch(e=>{document.getElementById('road-project-count').textContent='Road-place candidate data unavailable: '+String(e.message||e);});
})();'''


def utm51(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 to UTM zone 51N, matching the archived DPWH ArcGIS layers."""
    a, ecc_sq, k0 = 6378137.0, 0.00669437999014, 0.9996
    lat_r, lon_r = math.radians(lat), math.radians(lon)
    lon0 = math.radians(123.0)
    ecc_p = ecc_sq / (1 - ecc_sq)
    n = a / math.sqrt(1 - ecc_sq * math.sin(lat_r) ** 2)
    t = math.tan(lat_r) ** 2
    c = ecc_p * math.cos(lat_r) ** 2
    aa = math.cos(lat_r) * (lon_r - lon0)
    m = a * ((1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256) * lat_r
             - (3 * ecc_sq / 8 + 3 * ecc_sq**2 / 32 + 45 * ecc_sq**3 / 1024) * math.sin(2 * lat_r)
             + (15 * ecc_sq**2 / 256 + 45 * ecc_sq**3 / 1024) * math.sin(4 * lat_r)
             - (35 * ecc_sq**3 / 3072) * math.sin(6 * lat_r))
    x = k0 * n * (aa + (1 - t + c) * aa**3 / 6 + (5 - 18*t + t*t + 72*c - 58*ecc_p) * aa**5 / 120) + 500000
    y = k0 * (m + n * math.tan(lat_r) * (aa**2 / 2 + (5 - t + 9*c + 4*c*c) * aa**4 / 24
              + (61 - 58*t + t*t + 600*c - 330*ecc_p) * aa**6 / 720))
    return x, y


def point_segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    den = dx*dx + dy*dy
    t = 0 if den == 0 else max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / den))
    return math.hypot(p[0] - (a[0] + t*dx), p[1] - (a[1] + t*dy))


def cell(point):
    return int(point[0] // CELL), int(point[1] // CELL)


def nearest_road(point, grid, segments, bounds):
    """Expand the indexed cell search until no unsearched segment can be nearer."""
    cx, cy = cell(point)
    min_x, max_x, min_y, max_y = bounds
    max_radius = max(abs(cx - min_x), abs(cx - max_x), abs(cy - min_y), abs(cy - max_y))
    seen = set()
    best = (float('inf'), None)
    for radius in range(max_radius + 1):
        if radius == 0:
            cells = ((cx, cy),)
        else:
            cells = (
                [(x, cy - radius) for x in range(cx - radius, cx + radius + 1)]
                + [(x, cy + radius) for x in range(cx - radius, cx + radius + 1)]
                + [(cx - radius, y) for y in range(cy - radius + 1, cy + radius)]
                + [(cx + radius, y) for y in range(cy - radius + 1, cy + radius)]
            )
        candidates = set()
        for key in cells:
            candidates.update(grid.get(key, ()))
        for idx in candidates - seen:
            a, b, attrs = segments[idx]
            distance = point_segment_distance(point, a, b)
            if distance < best[0]:
                best = distance, attrs
        seen.update(candidates)
        left, right = (cx - radius) * CELL, (cx + radius + 1) * CELL
        bottom, top = (cy - radius) * CELL, (cy + radius + 1) * CELL
        unsearched_gap = min(point[0] - left, right - point[0], point[1] - bottom, top - point[1])
        if math.isfinite(best[0]) and unsearched_gap > best[0]:
            return best
        if radius >= max_radius:
            return best
    return best


def build():
    grid = defaultdict(list)
    segments = []
    roads = 0
    road_classes = Counter()
    with ROAD.open() as f:
        for line in f:
            feature = json.loads(line)
            attrs, paths = feature.get('attributes') or {}, (feature.get('geometry') or {}).get('paths') or []
            roads += 1
            road_classes[str(attrs.get('ROAD_SEC_CLASS') or 'Unclassified')] += 1
            for path in paths:
                pts = [(float(x), float(y)) for x, y, *_ in path]
                for a, b in zip(pts, pts[1:]):
                    idx = len(segments)
                    segments.append((a, b, attrs))
                    for gx in range(int(min(a[0],b[0])//CELL), int(max(a[0],b[0])//CELL)+1):
                        for gy in range(int(min(a[1],b[1])//CELL), int(max(a[1],b[1])//CELL)+1):
                            grid[gx,gy].append(idx)
    grid_x = [key[0] for key in grid]
    grid_y = [key[1] for key in grid]
    grid_bounds = (min(grid_x), max(grid_x), min(grid_y), max(grid_y))

    source = json.loads(FMR.read_text())
    integrated_path = STATIC / 'integrated-project-data.json'
    integrated = json.loads(integrated_path.read_text())
    import re
    remote_cue = re.compile(r'\b(?:sitio|barangay|brgy\.?|purok|farm.?to.?market|fmr|rural|mountain|upland|interior|access road)\b', re.I)
    explicit_city = re.compile(r'\bcity\b', re.I)
    national_road_cue = re.compile(r'\b(?:national road|national highway|national road network|national route|circumferential(?: road)?|bypass(?: road)?|coastal(?: road)?)\b', re.I)
    boundary_path = ROOT / 'data_sources/arcgis_dpwh/archive/selected/city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
    admin_places = []
    with boundary_path.open() as f:
        for line in f:
            a = (json.loads(line).get('attributes') or {})
            name = str(a.get('MUN_DBM') or a.get('MUNICIPAL') or '').strip()
            center = str(a.get('CENTERS') or '')
            if name and center in {'Municipality', 'City'}:
                admin_places.append((name, center, str(a.get('PROVINCE') or ''), str(a.get('REGION') or '')))
    def norm(s):
        return ' '.join(re.findall(r'[a-z0-9]+', str(s).lower()))
    def classify_place(title):
        title_n = f' {norm(title)} '
        # Require a whole place-name match; ambiguous same-name city/municipality
        # matches remain unresolved rather than being guessed as remote.
        hits = [(name, kind, province, region) for name, kind, province, region in admin_places
                if f' {norm(name)} ' in title_n]
        kinds = {h[1] for h in hits}
        if kinds == {'Municipality'}:
            return 'Municipality named · remote-area proxy', sorted({h[0] for h in hits})
        if 'City' in kinds and 'Municipality' not in kinds:
            return 'City named · exclude from remote screen', sorted({h[0] for h in hits})
        if len(kinds) > 1:
            return 'Ambiguous city/municipality name · review', sorted({h[0] for h in hits})
        return 'No municipality/city match in title · unresolved', []
    road_projects = []
    for row in integrated.get('projects', []):
        year, stage, title = int(row.get('year') or 0), str(row.get('stage') or ''), str(row.get('name') or '')
        if row.get('category') != 'Road' or not (stage == 'GAA' and 2015 <= year <= 2026 or year == 2027 and stage == 'HGAB 3rd'): continue
        if not remote_cue.search(title) and not national_road_cue.search(title): continue
        place_status, place_names = classify_place(title)
        if national_road_cue.search(title):
            place_status = 'National-road indicator · not remote'
        road_projects.append({'year':year,'stage':stage,'title':title,'amountPesos':int(float(row.get('amountPesos') or 0)),
                              'source':str(row.get('source') or ''),'districtId':str(row.get('districtId') or ''),
                              'placeStatus':place_status,'matchedPlaces':place_names})
    road_projects.sort(key=lambda x:(-x['year'],-x['amountPesos'],x['title']))
    gaa_road_rows = [r for r in integrated.get('projects', []) if r.get('category') == 'Road' and r.get('stage') == 'GAA']
    geometry_keys = {'geometry','coordinates','polyline','shape','startlongitude','start_longitude','latitude','longitude','startlatitude','start_latitude'}
    gaa_rows_with_location_fields = [r for r in gaa_road_rows if any(str(k).lower() in geometry_keys for k in r)]
    road_project_path = STATIC / 'connectivity-road-projects.json'
    place_summary = dict(Counter(r['placeStatus'] for r in road_projects))
    road_project_text = json.dumps({'scope':'Road-category projects with rural/remote wording; place status is matched against DPWH City-Municipal Boundaries (as of March 2022). A named municipality is a remote-area proxy only, not a claim that every road outside cities is remote. Projects without an unambiguous municipality match remain unresolved.','boundarySource':'DPWH City-Municipal Boundaries FeatureServer; source metadata cites NAMRIA rectified digitally by DPWH GIS staff (as of March 2022), with OpenStreetMap and PSA references.','placeStatusCounts':place_summary,'rows':road_projects},ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n'
    road_project_path.write_text(road_project_text)
    SOURCE_ROAD_PROJECTS.write_text(road_project_text)
    results = []
    for row in source['projects']:
        coords = row.get('coordinates') or []
        points = []
        for part in coords:
            for lon, lat in part:
                points.append(utm51(float(lon), float(lat)))
        if not points:
            continue
        ends = [points[0], points[-1]] if len(points) > 1 else [points[0]]
        nearest = []
        for p in ends:
            nearest.append(nearest_road(p, grid, segments, grid_bounds))
        best_idx = min(range(len(nearest)), key=lambda i: nearest[i][0])
        distance, attrs = nearest[best_idx]
        threshold = 'Near road · ≤100 m' if distance <= 100 else 'Review · 100–500 m' if distance <= 500 else 'Distant · 500 m–1 km' if distance <= 1000 else 'No nearby DPWH classified road · >1 km'
        results.append({
            'id': row['project_id'], 'title': row['title'], 'region': row['region'],
            'amountPesos': int(row['amount_php']), 'sourcePage': row['source']['printed_page'],
            'startDistanceMeters': round(nearest[0][0],1),
            'endDistanceMeters': round(nearest[-1][0],1) if len(nearest)>1 else None,
            'startLatitude': float(coords[0][0][1]), 'startLongitude': float(coords[0][0][0]),
            'endLatitude': float(coords[-1][-1][1]), 'endLongitude': float(coords[-1][-1][0]),
            'coordinateBasis': 'Printed start/end pair' if len(points) > 1 else 'Single coordinate; no route line',
            'closestEnd': 'Start' if best_idx == 0 else 'End', 'nearestDistanceMeters': round(distance,1),
            'result': threshold,
            'flagTags': ['DPWH National Road Network comparison · primary/secondary/tertiary classes included', 'HGAB 3rd-reading · DA FMR coordinate row', 'Nearest endpoint >1 km from DPWH classified road network'] if distance > 1000 else [],
            'roadName': (attrs or {}).get('ROAD_NAME') or 'Road name unavailable',
            'roadClass': (attrs or {}).get('ROAD_SEC_CLASS') or 'Class unavailable',
            'roadSection': (attrs or {}).get('SECTION_ID') or '',
        })
    results.sort(key=lambda x:(x['nearestDistanceMeters'], x['region'], x['title']))
    summary = Counter(r['result'] for r in results)
    coordinate_rows_with_route_pair = sum(
        sum(len(part) for part in (row.get('coordinates') or [])) >= 2
        for row in source['projects'])
    payload = {
        'scope': 'FY2027 House HGAB 3rd-reading DA FMR projects tested against DPWH National Road Network polylines, including the published primary, secondary and tertiary functional classes.',
        'method': 'Each printed HGAB FMR start/end coordinate was transformed from WGS84 to UTM zone 51N. The closest point from either endpoint to a DPWH National Road Network line segment was measured in metres. This classified network layer contains primary, secondary and tertiary functional classes. The separate FY2024/FY2025 DA FMR ArcGIS layers also carry route endpoints and are used in the venue-link review, not as farm polygons. Bands are ≤100 m, 100–500 m, 500 m–1 km and >1 km; proximity is not proof of a usable access connection.',
        'coordinateAudit': {'hgabFmrProjectRows': len(source['projects']), 'rowsWithRouteCoordinatePairs': coordinate_rows_with_route_pair, 'singleCoordinateRows': len(source['projects']) - coordinate_rows_with_route_pair, 'separateDaFmrArcgisLayers': {'fy2024Features': 1062, 'fy2025Features': 474}},
        'roadClasses': dict(road_classes),
        'gaaRoadAlignmentAudit': {'integratedGaaRoadRows': len(gaa_road_rows), 'rowsWithUsableGeometryOrCoordinateFields': len(gaa_rows_with_location_fields), 'note': 'This audit covers the integrated budget line-item table only. Coordinate-bearing FY2027 HGAB DA FMR project records and FY2024/FY2025 DA FMR ArcGIS records are separate datasets.'},
        'limits': ['This layer is the DPWH national-road network; its primary/secondary/tertiary labels are functional classes within that network, not a separate local-road inventory.', 'It does not cover every local, barangay, farm, or private road.', 'Coordinates are printed FMR endpoints and may be approximate; straight-line endpoint proximity does not prove an access connection.', 'Farm/cropland proximity is not included because no farm-boundary layer is currently available in the workspace.', 'Bridge analysis is deferred.', 'For question 2, DPWH National Road Network matches and routes explicitly named as national, circumferential, bypass or coastal are not treated as remote. A municipality match is a provisional remote-area proxy; routes with a city or unresolved endpoint stay out of the confirmed remote subset.', 'The visitor-venue join uses a 100 m buffer around straight-line segments reconstructed from available start/end coordinates. Route alignment, operating status, property ownership, and actual access remain unverified.'],
        'roadFeatures': roads, 'roadSegments': len(segments), 'roadProjectCandidates': len(road_projects), 'roadProjectPlaceStatusCounts': place_summary, 'summary': dict(summary), 'projects': results,
        'placeInventories': {'visitorVenues': 'connectivity-venues-data.json', 'privatePropertyIndicators': 'connectivity-property-indicators-data.json', 'unverifiedVenueNameCues': 'connectivity-venue-review-data.json'},
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    OUT.write_text(text)
    SOURCE_DATA.write_text(text)
    DATA.write_text(text)
    SCRIPT.write_text(JS)
    make_page(payload)
    print(json.dumps({'projects':len(results),'roadFeatures':roads,'roadSegments':len(segments),'summary':dict(summary)}))


def make_page(d):
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Road connectivity · BetterGov</title><link rel="stylesheet" href="research-theme.css"><link rel="stylesheet" href="report-table-readability.css"><style>body{margin:0;background:#eef3f4;color:#172b37;font:16px/1.5 system-ui,sans-serif}header{padding:28px 3vw;background:#00246A;color:white;border-bottom:4px solid #FCD116}header p{max-width:900px}main{padding:22px 3vw;max-width:none}.card{background:white;border:1px solid #d7e0e4;border-radius:14px;padding:22px;margin:20px 0}.stats{display:flex;flex-wrap:wrap;gap:12px}.stat{min-width:150px;flex:1;padding:14px;border:1px solid #d7e0e4;border-radius:10px}.stat strong{display:block;font-size:1.7rem}.note{color:#52636d}.filters{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0}.filters input,.filters select{padding:9px;border:1px solid #abb9c4;border-radius:7px;font:inherit}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{text-align:left;vertical-align:top;padding:9px;border-bottom:1px solid #d7e0e4;overflow-wrap:anywhere}th{background:#edf3f7}.num{text-align:right;white-space:nowrap}.table-wrap{overflow-x:auto}.controls{display:flex;align-items:center;gap:12px}.controls button{padding:8px 12px}.alert{padding:12px 14px;background:#fff5df;border-left:4px solid #c58100}.red-flag{color:#a31520;font-weight:750}.red-flag small{display:block;font-weight:500}@media(max-width:680px){.card{padding:14px}th,td{font-size:12px;padding:6px}}</style></head><body class="bettergov-research"><header><div class="eyebrow">BetterGov · Budget research</div><h1>Road connectivity</h1><p>Check whether FY2027 farm-to-market road endpoints meet the DPWH National Road Network. Distance bands at 100 m, 500 m and 1 km make proximity visible while keeping missing local-road data in view.</p></header><main><section class="card"><h2>1 · Do FY2027 FMR projects connect to an existing road?</h2><p>The screen measures each printed FMR start/end coordinate against DPWH National Road Network geometry and any GAA road-project alignment with usable data for determining distance or connection. Distances are grouped at 100 m, 500 m and 1 km. The local GAA project tables checked so far have no usable road alignment geometry, so the current bands use the DPWH network only. Proximity is a lead, not proof that vehicles can enter or that the segment is complete.</p><div class="stats" id="road-stats"></div><p class="alert"><strong>Coverage limit:</strong> the local ArcGIS layer represents the DPWH national-road network. It does not include every local, barangay, farm, or private road, so “no nearby national road” does not mean “no road connection.”</p><div class="filters"><label>Search <input id="q" type="search" placeholder="Project, province, road name"></label><label>Result <select id="result"><option value="">All results</option></select></label></div><div class="table-wrap"><table><thead><tr><th>FMR project</th><th>Region</th><th>Nearest national road</th><th class="num">Start (m)</th><th class="num">End (m)</th><th>Screen</th><th class="num">HGAB allocation</th><th>Map</th></tr></thead><tbody id="rows"></tbody></table></div><div class="controls"><button id="prev">Previous</button><span id="page"></span><button id="next">Next</button><label>Rows <select id="size"><option>10</option><option selected>25</option><option>50</option><option>100</option></select></label></div><p class="note">Sources: <a href="https://budget.bettergov.ph/hgab/2027/farm-to-market-roads">FY2027 HGAB FMR source page</a>; archived <a href="https://services1.arcgis.com/IwZZTMxZCmAmFYvF/arcgis/rest/services/National_Road_Network/FeatureServer/0">DPWH National Road Network ArcGIS layer</a>. <a href="connectivity-data.json" download>Download screening rows</a>.</p></section><section class="card"><h2>2 · Remote roads and current visitor venues</h2><p>Use a <strong>100 m buffer around the budgeted road alignment</strong>. Count current mapped resorts, hotels, guest houses, short-stay accommodation (including Airbnb-type venues), and event venues. Exclude residential rentals, government facilities, and public markets. A building footprint alone is not business evidence.</p><p class="alert"><strong>Distance and venue counts are pending usable alignments.</strong> The budgeted-road records have no project line geometry, so the 100 m/250 m venue test cannot be computed yet. The title candidates below include circumferential, bypass and coastal roads as national-road indicators and are checked against the DPWH City-Municipal Boundaries layer. A municipality match is only a provisional remote-area proxy. A project matched to the DPWH National Road Network is non-remote, including national-road corridors crossing city and municipality boundaries. Titles that explicitly identify a national road are tagged as such; without route alignment, other roads stay unresolved. City matches are excluded, and ambiguous/unmatched places stay unresolved.</p><p>For current public venue evidence, OpenStreetMap can supply tagged lodging and event-venue locations; its Philippines mapping convention includes hotels and event venues. DTI NegosyoKonek can help verify business identity and line of business, but the public portal is not a downloadable national geospatial inventory. These are leads, not a complete census. <a href="https://download.geofabrik.de/asia/philippines.html">Geofabrik Philippines OSM extract</a> · <a href="https://wiki.openstreetmap.org/wiki/PH%3AMap_Features">OSM Philippines mapping conventions</a> · <a href="https://negosyokonek.dti.gov.ph/">DTI NegosyoKonek</a>.</p><div class="filters"><label>Search remote-road title <input id="roadq" type="search" placeholder="Project or source"></label></div><div class="table-wrap"><table><thead><tr><th>Year / stage</th><th>Road project title</th><th class="num">Allocation</th><th>Source</th><th>Municipality/city screen</th></tr></thead><tbody id="road-project-rows"></tbody></table></div><div class="controls"><button id="road-prev">Previous</button><span id="road-page"></span><button id="road-next">Next</button><label>Rows <select id="road-size"><option>10</option><option selected>25</option><option>50</option><option>100</option></select></label></div><p class="note" id="road-project-count"></p><p><a href="connectivity-road-projects.json" download>Download remote-road title screen</a></p></section><section class="card"><h2>Method and limits</h2><ul><li>FMR records: 964 FY2027 HGAB 3rd-reading projects, 962 with usable coordinate endpoints in the corrected source ledger.</li><li>Question 1 groups the nearest FMR endpoint by distance: ≤100 m, 100–500 m, 500 m–1 km, and >1 km from the DPWH National Road Network. Question 2 uses a 100 m road-alignment buffer when alignments are available.</li><li>Coordinates are transformed to UTM zone 51N to compare metres with ArcGIS geometry. Distances are straight-line endpoint-to-line distances, not routed access distances.</li><li>GAA road alignments with usable location data are eligible as additional comparators. The reviewed GAA sources have no usable project geometry (0 of 37,754 integrated GAA road rows), so these distance bands use the DPWH network only.</li><li>Bridges are not included in this first version.</li><li>The provisional remote-area screen uses municipality/city names from the DPWH boundaries. A route matched to the DPWH National Road Network is non-remote, including national corridors crossing city and municipality boundaries. Circumferential, bypass and coastal roads are also treated as national-road indicators. The title table includes both rural/remote cues and these national-road indicators; project geometry is needed for route-level confirmation.</li></ul></section></main><script>Promise.allSettled([fetch('connectivity-data.json').then(r=>{if(!r.ok)throw Error('connectivity-data.json: HTTP '+r.status);return r.json()}),fetch('connectivity-road-projects.json').then(r=>{if(!r.ok)throw Error('connectivity-road-projects.json: HTTP '+r.status);return r.json()})]).then(([mainResult,roadResult])=>{if(mainResult.status!=='fulfilled')throw mainResult.reason;const d=mainResult.value,roadData=roadResult.status==='fulfilled'?roadResult.value:{rows:[],placeStatusCounts:{}};if(roadResult.status!=='fulfilled')document.getElementById('road-project-count').textContent='Road-place candidate data did not load: '+String(roadResult.reason.message||roadResult.reason);const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),rows=d.projects,q=document.getElementById('q'),sel=document.getElementById('result'),size=document.getElementById('size'),body=document.getElementById('rows'),pageLabel=document.getElementById('page');Object.keys(d.summary).forEach(x=>sel.add(new Option(`${x} (${d.summary[x]})`,x)));const stats=document.getElementById('road-stats');stats.innerHTML=Object.entries(d.summary).map(([k,v])=>`<div class="stat"><strong>${n(v)}</strong>${esc(k)}</div>`).join('')+`<div class="stat"><strong>${n(rows.length)}</strong>FMR projects · ${n(d.roadFeatures)} ArcGIS road features</div>`;let page=0;function draw(){const term=q.value.trim().toLowerCase(),items=rows.filter(x=>(!sel.value||x.result===sel.value)&&(!term||`${x.title} ${x.region} ${x.roadName}`.toLowerCase().includes(term))).sort((a,b)=>Number(b.amountPesos||0)-Number(a.amountPesos||0)),per=Number(size.value),pages=Math.max(1,Math.ceil(items.length/per));page=Math.min(page,pages-1);body.innerHTML=items.slice(page*per,(page+1)*per).map(x=>`<tr><td>${esc(x.title)}<small>Printed source p. ${esc(x.sourcePage)}</small></td><td>${esc(x.region)}</td><td>${esc(x.roadName)}<small>${esc(x.roadClass)} · ${esc(x.roadSection)}</small></td><td class="num">${n(x.startDistanceMeters)}</td><td class="num">${x.endDistanceMeters==null?'—':n(x.endDistanceMeters)}</td><td class="${x.flagTags.length?'red-flag':''}">${esc(x.result)}${x.flagTags.length?'<small>Flag tag: nearest endpoint over 1 km from the DPWH road network</small>':''}</td><td class="num">${peso(x.amountPesos)}</td></tr>`).join('')||'<tr><td colspan="7">No matching records.</td></tr>';pageLabel.textContent=`${items.length?page*per+1:0}–${Math.min((page+1)*per,items.length)} of ${items.length} · Page ${page+1} of ${pages}`;document.getElementById('prev').disabled=page===0;document.getElementById('next').disabled=page>=pages-1}q.addEventListener('input',()=>{page=0;draw()});sel.addEventListener('change',()=>{page=0;draw()});size.addEventListener('change',()=>{page=0;draw()});document.getElementById('prev').onclick=()=>{page--;draw()};document.getElementById('next').onclick=()=>{page++;draw()};draw();const roadRows=roadData.rows,rq=document.getElementById('roadq'),rb=document.getElementById('road-project-rows'),rp=document.getElementById('road-page'),rs=document.getElementById('road-size');document.getElementById('road-project-count').textContent=`${n(roadRows.length)} GAA/HGAB road titles pass the rural/remote or national-road title screen. Place status uses DPWH City-Municipal Boundaries; municipality is a provisional remote-area proxy. ${Object.entries(roadData.placeStatusCounts||{}).map(([k,v])=>`${n(v)} ${k}`).join(" · ")}`;let roadPage=0;function drawRoad(){const term=rq.value.trim().toLowerCase(),items=roadRows.filter(x=>!term||`${x.title} ${x.source}`.toLowerCase().includes(term)),per=Number(rs.value),pages=Math.max(1,Math.ceil(items.length/per));roadPage=Math.min(roadPage,pages-1);rb.innerHTML=items.slice(roadPage*per,(roadPage+1)*per).map(x=>`<tr><td>FY${x.year}<br>${esc(x.stage)}</td><td>${esc(x.title)}</td><td class=\"num\">${peso(x.amountPesos)}</td><td>${esc(x.source)}</td><td>${esc(x.placeStatus)}${x.matchedPlaces?.length?`<small>${esc(x.matchedPlaces.join(", "))}</small>`:""}</td></tr>`).join('')||'<tr><td colspan=\"5\">No matching projects.</td></tr>';rp.textContent=`${items.length?roadPage*per+1:0}–${Math.min((roadPage+1)*per,items.length)} of ${items.length} · Page ${roadPage+1} of ${pages}`;document.getElementById('road-prev').disabled=roadPage===0;document.getElementById('road-next').disabled=roadPage>=pages-1}rq.addEventListener('input',()=>{roadPage=0;drawRoad()});rs.addEventListener('change',()=>{roadPage=0;drawRoad()});document.getElementById('road-prev').onclick=()=>{roadPage--;drawRoad()};document.getElementById('road-next').onclick=()=>{roadPage++;drawRoad()};drawRoad()}).catch(e=>document.getElementById('rows').innerHTML='<tr><td colspan=\"7\">Connectivity data unavailable: '+String(e.message)+'</td></tr>');</script></body></html>'''
    import re
    html = re.sub(r'<script>Promise\.allSettled\(.*?</script>', '<script src="connectivity.js"></script>', html, count=1, flags=re.S)
    html = re.sub(
        r'(<h2>1 · Do FY2027 FMR projects connect to an existing road\?</h2>)<p>.*?</p>',
        r'\1<p>Each printed FY2027 HGAB FMR start/end coordinate is compared with the DPWH National Road Network, including its primary, secondary and tertiary functional classes. The table and chart show endpoint distance to that classified network. Farm proximity is not yet measured because a farm/cropland layer is not available locally; do not read these road-only results as Model, Flag or Double Flag classifications.</p>',
        html, count=1, flags=re.S)
    html = html.replace('<div class="stats" id="road-stats"></div>',
        '<div class="stats" id="road-stats"></div><h3>FMR endpoint distance to the DPWH classified road network</h3><div id="road-distance-chart" role="img" aria-label="Counts of FMR projects by distance to the nearest DPWH classified road"></div><p class="note">Road-only distance bands. Farm proximity is not included yet, so the requested combined categories cannot be counted from this chart.</p>', 1)
    html = html.replace('<th>Nearest national road</th>', '<th>Nearest DPWH classified road</th>', 1)
    html = html.replace('No nearby DPWH national road', 'No nearby DPWH classified road')
    html = html.replace('nearest endpoint over 1 km from the DPWH road network', 'nearest endpoint over 1 km from the DPWH classified road network')
    html = html.replace('https://services1.arcgis.com/IwZZTMxZCmAmFYvF/arcgis/rest/services/National_Road_Network/FeatureServer/0', 'https://services1.arcgis.com/IwZZTMxZCmAmFYvF/arcgis/rest/services/Road_Classification/FeatureServer/1')
    html = html.replace('DPWH National Road Network ArcGIS layer', 'DPWH Road Classification · National Road Network layer (Primary/Secondary/Tertiary)')
    html = html.replace('</style>', '#road-distance-chart{display:grid;gap:10px;max-width:900px;margin:12px 0 18px}.road-chart-row{display:grid;grid-template-columns:minmax(150px,220px) minmax(100px,1fr) 60px;align-items:center;gap:12px}.road-chart-track{height:20px;border-radius:5px;background:#edf1f4;overflow:hidden}.road-chart-track i{display:block;height:100%;border-radius:5px}.road-chart-row strong{text-align:right}@media(max-width:560px){.road-chart-row{grid-template-columns:115px minmax(60px,1fr) 42px;gap:8px;font-size:13px}}\n</style>', 1)
    html = re.sub(r'<h2>Method and limits</h2><ul>.*?</ul>',
        '<h2>Method and limits</h2><ul><li>FY2027 HGAB 3rd FMR schedule: 964 project rows, with printed start/end coordinate pairs for route distance screening.</li><li>The road comparator is DPWH’s National Road Network layer, including its Primary, Secondary and Tertiary functional classes. These are classes within the national network, not a separate local-road inventory.</li><li>Distances use straight-line endpoint-to-road measurements in UTM zone 51N. The 100 m, 500 m and 1 km bands are proximity screens, not proof of accessible connection.</li><li>Farm/cropland proximity remains unmeasured, so the Model / Flag / Double Flag categories are not assigned.</li><li>For venue review, coordinate-backed DA FMR records are compared with classified visitor venues using a 100 m straight-segment buffer. Route location, operating status and actual access need confirmation.</li><li>Municipality endpoints are a provisional remote-area proxy. City and unresolved routes are not included in the remote venue matches.</li></ul>', html, count=1, flags=re.S)
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    from connectivity_places_page import apply_page as apply_place_inventory
    PAGE.write_text(apply_place_inventory(apply_uniform_menu_page(html, PAGE.name)))


if __name__ == '__main__':
    build()
