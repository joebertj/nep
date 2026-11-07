#!/usr/bin/env python3
"""Match FY2027 FMR source geometry to nearby mapped unpaved OSM roads."""
from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import osmium

from build_connectivity_report import point_segment_distance, utm51

ROOT = Path(__file__).resolve().parent
PBF = ROOT / 'data_sources/connectivity_online/philippines-261104.osm.pbf'
FMR = ROOT / 'analysis_output/fmr_corrected_dataset.json'
OUT = ROOT / 'analysis_output/connectivity-unpaved-road-indicator.json'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
RAW_CACHE = ROOT / 'data_sources/connectivity_online/osm-unpaved-roads-raw.json'
CELL = 1000.0
BUFFER = 100.0
CONNECTED = 30.0

UNPAVED_SURFACES = {
    'unpaved', 'gravel', 'fine_gravel', 'pebblestone', 'dirt', 'earth', 'ground',
    'compacted', 'grass', 'sand', 'mud', 'rock', 'stone', 'woodchips', 'gravel_turf',
}
PAVED_SURFACES = {'asphalt', 'concrete', 'concrete:lanes', 'concrete:plates', 'paving_stones', 'sett', 'metal', 'wood'}


def is_unpaved(tags: dict[str, str]) -> bool:
    highway = tags.get('highway', '')
    surface = tags.get('surface', '').lower()
    tracktype = tags.get('tracktype', '').lower()
    if surface in PAVED_SURFACES:
        return False
    return surface in UNPAVED_SURFACES or tracktype in {'grade2', 'grade3', 'grade4', 'grade5'} or highway == 'track'


def extract_roads():
    if RAW_CACHE.exists():
        cached = json.loads(RAW_CACHE.read_text())
        if cached.get('sourceFile') == PBF.name:
            return cached
    roads: dict[int, dict] = {}
    node_ids: set[int] = set()

    class Select(osmium.SimpleHandler):
        def way(self, way):
            tags = dict(way.tags)
            if not tags.get('highway') or not is_unpaved(tags):
                return
            refs = [node.ref for node in way.nodes]
            if len(refs) < 2:
                return
            roads[way.id] = {'id': way.id, 'tags': tags, 'nodes': refs}
            node_ids.update(refs)

    Select().apply_file(str(PBF), filters=[osmium.filter.KeyFilter('highway', 'surface', 'tracktype')])
    print(f'Selected {len(roads):,} candidate unpaved road ways; recovering locations for {len(node_ids):,} nodes.', flush=True)
    locations: dict[int, tuple[float, float]] = {}

    class Locations(osmium.SimpleHandler):
        def node(self, node):
            if node.id in node_ids and node.location.valid():
                locations[node.id] = (node.location.lon, node.location.lat)

    Locations().apply_file(str(PBF), filters=[osmium.filter.IdFilter(node_ids)])
    elements = []
    for road in roads.values():
        coords = [locations[node_id] for node_id in road['nodes'] if node_id in locations]
        if len(coords) >= 2:
            elements.append({'id': road['id'], 'tags': road['tags'], 'coordinates': coords})
    try:
        with osmium.io.Reader(str(PBF)) as reader:
            timestamp = reader.header().get('osmosis_replication_timestamp')
    except Exception:
        timestamp = None
    payload = {'source': 'Offline OpenStreetMap Philippines PBF', 'sourceFile': PBF.name,
               'osmTimestamp': timestamp, 'license': '© OpenStreetMap contributors, ODbL 1.0',
               'candidateWays': len(roads), 'waysWithGeometry': len(elements), 'elements': elements}
    RAW_CACHE.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    return payload


def segment_distance(a, b, c, d):
    def orient(p, q, r):
        return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    intersects = (o1 * o2 <= 0 and o3 * o4 <= 0
                  and max(min(a[0], b[0]), min(c[0], d[0])) <= min(max(a[0], b[0]), max(c[0], d[0]))
                  and max(min(a[1], b[1]), min(c[1], d[1])) <= min(max(a[1], b[1]), max(c[1], d[1])))
    if intersects:
        return 0.0
    return min(point_segment_distance(c, a, b), point_segment_distance(d, a, b),
               point_segment_distance(a, c, d), point_segment_distance(b, c, d))


def add_to_grid(grid, bounds, value):
    x0, y0, x1, y1 = bounds
    gx0, gx1 = int(x0 // CELL), int(x1 // CELL)
    gy0, gy1 = int(y0 // CELL), int(y1 // CELL)
    if (gx1-gx0+1) * (gy1-gy0+1) > 5000:
        return
    for gx in range(gx0, gx1+1):
        for gy in range(gy0, gy1+1):
            grid[gx, gy].append(value)


def build():
    fmr = json.loads(FMR.read_text())
    road_data = extract_roads()
    route_grid = defaultdict(list)
    route_legs = defaultdict(list)
    skipped = set()
    for row in fmr.get('projects', []):
        project_id = str(row.get('project_id') or '')
        parts = row.get('coordinates') or []
        for part in parts:
            points = [utm51(float(lon), float(lat)) for lon, lat in part]
            for a, b in zip(points, points[1:]):
                if math.dist(a, b) > 20000:
                    skipped.add(project_id)
                    continue
                leg = (project_id, a, b)
                route_legs[project_id].append(leg)
                add_to_grid(route_grid, (min(a[0], b[0])-BUFFER, min(a[1], b[1])-BUFFER,
                                         max(a[0], b[0])+BUFFER, max(a[1], b[1])+BUFFER), leg)

    nearest = {}
    for road in road_data['elements']:
        points = [utm51(lon, lat) for lon, lat in road['coordinates']]
        for c, d in zip(points, points[1:]):
            gx0, gx1 = int((min(c[0], d[0])-BUFFER)//CELL), int((max(c[0], d[0])+BUFFER)//CELL)
            gy0, gy1 = int((min(c[1], d[1])-BUFFER)//CELL), int((max(c[1], d[1])+BUFFER)//CELL)
            candidates = set()
            for gx in range(gx0, gx1+1):
                for gy in range(gy0, gy1+1):
                    candidates.update(route_grid.get((gx, gy), ()))
            for project_id, a, b in candidates:
                distance = segment_distance(a, b, c, d)
                if distance > BUFFER:
                    continue
                if project_id not in nearest or distance < nearest[project_id]['distanceMeters']:
                    tags = road['tags']
                    nearest[project_id] = {
                        'distanceMeters': round(distance, 1),
                        'name': tags.get('name') or tags.get('ref') or 'Unnamed mapped road',
                        'highway': tags.get('highway'), 'surface': tags.get('surface'),
                        'tracktype': tags.get('tracktype'),
                        'osmUrl': f"https://www.openstreetmap.org/way/{road['id']}",
                    }

    rows = []
    for project in fmr.get('projects', []):
        project_id = str(project.get('project_id') or '')
        evidence = nearest.get(project_id)
        if project_id in skipped:
            status = 'Not assessed · source coordinate gap >20 km'
        elif not route_legs.get(project_id):
            status = 'Not assessed · no source route geometry'
        elif evidence and evidence['distanceMeters'] <= CONNECTED:
            status = 'Likely connected · mapped road within 30 m'
        elif evidence:
            status = 'Nearby · mapped road within 100 m'
        else:
            status = 'No mapped unpaved road within 100 m'
        rows.append({'id': project_id, 'status': status, **(evidence or {})})

    result = {'source': road_data['source'], 'osmTimestamp': road_data.get('osmTimestamp'),
              'license': road_data['license'], 'method': 'Offline OpenStreetMap ways tagged highway=track, surface as unpaved, or tracktype grade2–grade5. Compared to the printed FMR source route geometry in UTM zone 51N. Within 30 m is a likely connection; 31–100 m is nearby only. This is a map-data indicator, not proof of a drivable or passable connection.',
              'searchRadiusMeters': BUFFER, 'likelyConnectionMeters': CONNECTED,
              'candidateWays': road_data['candidateWays'], 'waysWithGeometry': road_data['waysWithGeometry'],
              'rows': rows}
    encoded = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    OUT.write_text(encoded)
    (STATIC / 'connectivity-unpaved-road-indicator.json').write_text(encoded)
    print(json.dumps({'projects': len(rows), 'likelyConnected': sum(r['status'].startswith('Likely connected') for r in rows),
                      'nearby': sum(r['status'].startswith('Nearby') for r in rows),
                      'noMappedRoad': sum(r['status'].startswith('No mapped') for r in rows),
                      'candidateWays': road_data['candidateWays'], 'waysWithGeometry': road_data['waysWithGeometry']}, ensure_ascii=False))


if __name__ == '__main__':
    build()
