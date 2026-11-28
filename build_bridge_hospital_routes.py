"""Screen FY2027 House bridge lines and model hospital detours for matched spans."""
import gzip
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import osmium
from pyproj import Transformer

from build_amendment_access import ROOT, STATIC, OUT, ROAD_SPEEDS, km, route

LAYER = ROOT / 'data_sources/arcgis_dpwh/archive/layers/Detailed_Bridge_Inventory_Final_FeatureServer_1-72c1d1a7'
PBF = ROOT / 'data_sources/connectivity_online/philippines-261104.osm.pbf'
PDF = 'https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ic.pdf'
CELL = .075
UNPAVED = {'unpaved', 'gravel', 'ground', 'dirt', 'earth', 'compacted', 'fine_gravel', 'sand', 'mud'}


def tile(point):
    return tuple(math.floor(axis / CELL) for axis in point)


def adjacent(cell):
    return [(cell[0] + i, cell[1] + j) for i in (-1, 0, 1) for j in (-1, 0, 1)]


def normalized(name):
    return re.sub(r'\b(?:bridge|br|brg)\b|[^a-z0-9]', '', name.lower())


def inventory():
    tr = Transformer.from_crs(32651, 4326, always_xy=True)
    result = {}
    for file in sorted((LAYER / 'batches').glob('*.json.gz')):
        with gzip.open(file, 'rt') as stream:
            for feature in json.load(stream):
                a, g = feature['attributes'], feature.get('geometry')
                if g and a.get('BRIDGE_ID'):
                    lon, lat = tr.transform(g['x'], g['y'])
                    result[a['BRIDGE_ID']] = ((lat, lon), a['BR_NAME'] or '')
    return result


class Roads(osmium.SimpleHandler):
    def __init__(self, wanted):
        super().__init__()
        self.wanted = wanted
        self.edges = defaultdict(list)
        self.settlements = defaultdict(list)
        self.unpaved = set()

    def node(self, node):
        place = node.tags.get('place')
        name = node.tags.get('name')
        if place in {'village', 'hamlet', 'suburb', 'neighbourhood', 'quarter'} and name:
            point = (node.location.lat, node.location.lon)
            if tile(point) in self.wanted:
                self.settlements[tile(point)].append((name, point))

    def way(self, way):
        tags = way.tags
        road = tags.get('highway')
        if road not in ROAD_SPEEDS and road not in {'motorway', 'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link'}:
            return
        access = next((tags[k] for k in ('motorcar', 'motor_vehicle', 'vehicle', 'access') if k in tags), '')
        if access in {'no', 'private', 'agricultural', 'forestry'} or tags.get('area') == 'yes':
            return
        speed = ROAD_SPEEDS.get(road, 40)
        if tags.get('surface') in UNPAVED:
            speed = min(speed, 20)
        direction = tags.get('oneway:motor_vehicle', tags.get('oneway', 'yes' if road == 'motorway' or tags.get('junction') == 'roundabout' else 'no'))
        bridge = tags.get('bridge', 'no') not in {'no', 'movable', 'proposed', 'construction'}
        name = tags.get('bridge:name') or tags.get('name') or ''
        for a, b in zip(way.nodes, list(way.nodes)[1:]):
            if not a.location.valid() or not b.location.valid():
                continue
            u = a.lat, a.lon
            v = b.lat, b.lon
            cell = tile(u)
            if cell in self.wanted and a.ref != b.ref:
                if tags.get('surface') in UNPAVED:
                    self.unpaved.add(way.id)
                self.edges[cell].append((a.ref, b.ref, u, v, speed, direction, way.id, bridge, normalized(name)))


def separation(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    fraction = ((point[0]-start[0])*dx + (point[1]-start[1])*dy) / max(1e-20, dx*dx+dy*dy)
    fraction = max(0, min(1, fraction))
    return km(point, (start[0] + fraction * dx, start[1] + fraction * dy))


def model(center, name, roads, hospitals):
    cells = adjacent(tile(center))
    edges = [edge for cell in cells for edge in roads.edges[cell]]
    target = normalized(name)
    candidates = {key for _, _, a, b, _, _, key, bridge, title in edges
                  if bridge and title and title == target and separation(center, a, b) <= .10}
    if len(candidates) != 1:
        return ('Ambiguous mapped spans' if candidates else 'No matching named mapped span'), None
    bridge_id = next(iter(candidates))
    coordinates = {}
    graph, closed = defaultdict(list), defaultdict(list)
    for a, b, u, v, speed, direction, way, _, _ in edges:
        coordinates[a], coordinates[b] = u, v
        duration = km(u, v) * 60 / speed
        if direction != '-1':
            graph[a].append((b, duration))
            if way != bridge_id:
                closed[a].append((b, duration))
        if direction not in {'yes', '1', 'true'}:
            graph[b].append((a, duration))
            if way != bridge_id:
                closed[b].append((a, duration))
    from scipy.spatial import cKDTree
    keys = list(coordinates)
    tree = cKDTree([coordinates[key] for key in keys])

    def snap(point):
        index = tree.query(point)[1]
        key = keys[index]
        return key if km(point, coordinates[key]) <= .25 else None

    nearby_hospitals = sorted((km(center, point), label, point) for label, point in hospitals if km(center, point) <= 6)
    nearby_hospitals = [(label, point, ref) for _, label, point in nearby_hospitals if (ref := snap(point)) is not None][:3]
    if not nearby_hospitals:
        return 'No mapped hospital within 6 km with a road tie-in', None
    span_segments = {(min(a, b), max(a, b)) for a, b, *_, way, is_bridge, _ in edges if way == bridge_id and is_bridge}
    towns = sorted((km(center, point), label, point) for cell in cells for label, point in roads.settlements[cell]
                   if km(center, point) <= 4)
    results = []
    visited = set()
    for _, label, point in towns[:30]:
        start = snap(point)
        if start is None or start in visited:
            continue
        visited.add(start)
        for hospital, destination, end in nearby_hospitals:
            baseline = route(graph, start, end)
            if not baseline or not any((min(a, b), max(a, b)) in span_segments for a, b in zip(baseline[1], baseline[1][1:])):
                continue
            detour = route(closed, start, end)

            def describe(result):
                if result is None:
                    return None
                time, path = result
                return {'minutes': round(time, 2), 'points': [[round(axis, 6) for axis in coordinates[n]] for n in path]}

            results.append({'name': label, 'point': point, 'hospitalName': hospital, 'hospital': destination,
                            'open': describe(baseline), 'closed': describe(detour)})
            break
        if len(results) == 6:
            break
    if not results:
        return 'No sampled hospital trip routed over span', None
    span = [[u, v] for _, _, u, v, _, _, way, _, _ in edges if way == bridge_id]
    return 'Hospital routes modeled', {'bridgeWay': bridge_id, 'span': span, 'origins': results}


def mapped_hospitals():
    facilities = json.loads((ROOT / 'data_sources/hospitals.json').read_bytes())['features']
    return {(f['properties']['name'], tuple(reversed(f['geometry']['coordinates']))) for f in facilities
                 if f['properties'].get('name') and (re.search(r'\bhospital\b|\bmedical (?:center|centre)\b', f['properties']['name'], re.I))
                 and not re.search(r'veterinary|animal|dental', f['properties']['name'], re.I)}


def main():
    ids = inventory()
    source = json.loads((ROOT / 'hb10858_3rd_dpwh_projects.json').read_bytes())['data']['data']
    rows = []
    centers = {}
    for record in source:
        title = record['projectName']
        code = re.search(r'\bB\d{5}[A-Z]{2}\b', title.upper())
        sector = record.get('pap3') or ''
        if not (code or re.search(r'\b(?:bridges?|br\.)\b', title, re.I) or
                re.search(r'^(?:construction|replacement|rehabilitation|retrofitting|widening).*\bbridges\b', sector, re.I)):
            continue
        key = code[0] if code else None
        page = record['sourcePage']
        rows.append({'title': title, 'id': record['id'], 'region': record['region'], 'bridgeId': key,
                     'url': PDF + '#page=' + str(page), 'amount': record['amountPesos']})
        if key in ids and re.search(r'\b(?:repair|rehabilitation|replacement|retrofitting|strengthening|widening)\b', title + ' ' + sector, re.I):
            centers[key] = ids[key]
    roads = Roads({cell for point, _ in centers.values() for cell in adjacent(tile(point))})
    print(f'Screening {len(rows)} House lines and {len(centers)} inventory bridges against the road extract.', flush=True)
    roads.apply_file(str(PBF), locations=True, idx='flex_mem')
    hospitals = mapped_hospitals()
    results = {}
    for key, (point, name) in centers.items():
        results[key] = model(point, name, roads, hospitals)
    for row in rows:
        title = row['title'].casefold()
        key = row['bridgeId']
        if 'bolinao' in title and ('santiago' in title or 'santiago' in title.replace('san tiago', 'santiago')) and 'bridge' in title:
            status, scenario = 'Hospital routes modeled', 'bolinao'
        elif key in results:
            status, data = results[key]
            scenario = key if data else None
        elif key in ids:
            status, scenario = 'Project scope needs review', None
        else:
            status, scenario = 'Needs verified span or proposed approaches', None
        row.update(status=status, scenario=scenario)
    payload = {'projects': rows, 'scenarios': {key: {'name': centers[key][1], **data}
                                                for key, (_, data) in results.items() if data}}
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (OUT, STATIC):
        (path / 'bridge-hospital-routes.json').write_text(content)
    print(len(rows), 'lines;', len(payload['scenarios']), 'additional bridge scenarios')


if __name__ == '__main__':
    main()
