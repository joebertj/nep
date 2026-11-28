#!/usr/bin/env python3
"""Build the Bolinao bridge access pilot from a local OpenStreetMap snapshot."""
import argparse
import gzip
import heapq
import json
import math
from collections import defaultdict
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data_sources/bolinao_access'
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
ROAD_SPEEDS = {
    'trunk': 45, 'primary': 45, 'secondary': 40, 'tertiary': 35,
    'unclassified': 25, 'residential': 25, 'living_street': 15, 'service': 15,
}
FERRY_ID = 169529525
BRIDGE_SITES = [(16.385190, 119.932902), (16.381039, 119.917088)]
ORIGINS = {
    'Binabalian': (3276455500, 4268), 'Dewey': (3276455506, 2136),
    'Goyoden': (12196488191, 2866), 'Lucero': (2043289331, 3256),
    'Pilar': (2043289328, 2487), 'Salud': (2043289330, 2613),
    'Victory': (2043289329, 1292),
}
NEP_URL = 'https://www.dbm.gov.ph/index.php/2027/national-expenditure-program-fy-2027'


def km(a, b):
    lat = math.radians((a[0] + b[0]) / 2)
    return 111.195 * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(lat))


def tags(element):
    return {tag.attrib['k']: tag.attrib['v'] for tag in element.findall('tag')}


def read_osm(paths):
    nodes, roads, shoreline = {}, {}, {}
    ferry = None
    for path in paths:
        root = ElementTree.parse(path).getroot()
        nodes.update({int(n.attrib['id']): (float(n.attrib['lat']), float(n.attrib['lon']))
                      for n in root.findall('node')})
        for way in root.findall('way'):
            way_id = int(way.attrib['id'])
            attrs = tags(way)
            refs = [int(n.attrib['ref']) for n in way.findall('nd')]
            highway = attrs.get('highway')
            access = next((attrs[k] for k in ('motorcar', 'motor_vehicle', 'vehicle', 'access') if k in attrs), '')
            if highway in ROAD_SPEEDS and access not in {'no', 'private', 'agricultural', 'forestry'} and attrs.get('area') != 'yes':
                direction = attrs.get('oneway:motor_vehicle', attrs.get('oneway', 'yes' if attrs.get('junction') == 'roundabout' else 'no'))
                speed = ROAD_SPEEDS[highway]
                if attrs.get('surface') in {'unpaved', 'gravel', 'ground', 'dirt', 'earth'}:
                    speed = min(speed, 20)
                roads[way_id] = [refs, speed, direction]
            if attrs.get('natural') == 'coastline':
                shoreline[way_id] = refs
            if way_id == FERRY_ID:
                hours, minutes = map(int, attrs['duration'].split(':'))
                ferry = [refs, hours * 60 + minutes]
    if ferry is None:
        raise ValueError('The OSM snapshot must include the Santiago Island ferry.')
    used = {ref for way, _, _ in roads.values() for ref in way}
    used.update(ref for way in shoreline.values() for ref in way)
    used.update(ferry[0])
    used.update(node for node, _ in ORIGINS.values())
    return {'nodes': {ref: nodes[ref] for ref in sorted(used)}, 'roads': list(roads.values()),
            'shoreline': list(shoreline.values()), 'ferry': ferry}


def route(graph, start, end):
    queue = [(0.0, start)]
    best = {start: 0.0}
    previous = {}
    while queue:
        minutes, node = heapq.heappop(queue)
        if minutes != best[node]:
            continue
        if node == end:
            path = [end]
            while path[-1] != start:
                path.append(previous[path[-1]])
            return minutes, path[::-1]
        for target, duration in graph.get(node, ()):
            total = minutes + duration
            if total < best.get(target, math.inf):
                best[target] = total
                previous[target] = node
                heapq.heappush(queue, (total, target))
    return None


def component(graph, start):
    seen = {start}
    pending = [start]
    while pending:
        for target, _ in graph[pending.pop()]:
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def polyline(nodes, refs):
    return [[round(coord, 6) for coord in nodes[ref]] for ref in refs]


def budget_rows():
    data = json.loads((OUT / 'scr-data.json').read_text())['rows']
    rows = {r['id']: r for r in data if r['id'] in {'house-reading:6548', 'house-reading:6554'}}
    if len(rows) != 2:
        raise ValueError('The Senate crosswalk is missing a Bolinao bridge line.')
    return [
        {'title': title, 'house': int(row['house_php']), 'senate': int(row['senate_php']),
         'nep': int(row['nep_php']) if row['nep_php'] else None,
         'houseUrl': row['house_pdf_url'], 'senateUrl': row['senate_pdf_url']}
        for title, row in (('Bridge completion', rows['house-reading:6548']),
                           ('Bridge construction', rows['house-reading:6554']))
    ]


CORRIDOR_LINES = {
    'house-reading:6572': ('Access road', 'Names Pilar on Santiago Island and Siapar in Anda. The schedule gives chainage but no verified crossing or approach alignment.'),
    **dict.fromkeys(
        ('house-reading:321', 'house-reading:1700', 'house-reading:1699', 'house-reading:1698', 'house-reading:320'),
        ('National road', 'Alaminos–Bolinao road work. The schedule lists chainages that have not been tied to the modeled hospital routes.'),
    ),
    'house-reading:6776': ('Bridge', 'The budget names Siapar. The available record does not identify both banks or tie this bridge to the Pilar road.'),
    'house-reading:6587': ('Road rehabilitation', 'Work on the Bolinao–Patar corridor. The chainage was not located on the hospital routes.'),
    'house-reading:6569': ('Local road', 'Mainland Anda corridor. The budget lists barangays without an alignment suitable for routing.'),
    'house-reading:6808': ('Access road', 'San Roque segment. The schedule gives chainage without a verified route tie-in.'),
    'house-reading:6819': ('Access road', 'Tupa segment with printed endpoints.'),
    'house-reading:6791': ('Access road', 'Catuday segment with printed endpoints.'),
    'house-reading:6806': ('Access road', 'Samang Norte segment with printed endpoints.'),
    'house-reading:6780': ('Access road', 'Arnedo segment with printed endpoints.'),
    'house-reading:6805': ('Access road', 'Sablig segment. The chainage was not located on the hospital routes.'),
    'house-reading:6790': ('Access road', 'Carot segment with printed endpoints.'),
    'house-reading:6788': ('Access road', 'Cabungan segment with printed endpoints.'),
    'house-reading:2310': ('Coastal road', 'Regional coastal-road segment. The listed chainage was not located on the hospital routes.'),
    'house-reading:2309': ('Coastal road', 'Regional coastal-road segment. The listed chainage was not located on the hospital routes.'),
    'house_only:ib:p672:r7': ('Farm-to-market road', 'Sitio Bigat in mainland Anda. A separate FY2026 Awile line also exists. The shared barangay is insufficient to equate the two projects.'),
}
FMR_GAA = 'https://www.dbm.gov.ph/wp-content/uploads/GAA/GAA2026/VolumeIB/FMR.pdf'
FMR_ENDPOINTS = {
    'Doloaan, Anda': [(16.3272587, 119.9733977), (16.327986, 119.965473)],
    'Awile, Anda': [(16.259313, 119.971428), (16.261663, 119.962179)],
    'Mal-ong, Anda': [(16.2982, 119.9405461), (16.306935, 119.9464415)],
    'Liwa-Liwa, Bolinao': [(16.365121, 119.889882), (16.360522, 119.887115)],
    'Catuday, Bolinao': [(16.296914, 119.818425), (16.300603, 119.824953)],
}


def corridor_projects(origins):
    import re
    road_points = {
        tuple(point) for origin in origins for mode in ('ferry', 'bridge')
        for leg in (origin[mode]['legs'][0], origin[mode]['legs'][-1]) for point in leg
    }

    def endpoint_distances(points):
        return [round(1000 * min(km(point, road_point) for road_point in road_points)) for point in points]

    rows = {r['id']: r for r in json.loads((OUT / 'scr-data.json').read_text())['rows']}
    projects = []
    for identifier, (kind, note) in CORRIDOR_LINES.items():
        row = rows[identifier]
        points = [tuple(map(float, pair)) for pair in re.findall(r'(16\.\d+),\s*(119\.\d+)', row['title'])]
        projects.append({
            'title': row['title'], 'kind': kind, 'note': note,
            'nep': int(row['nep_php']) if row['nep_php'] else None,
            'house': int(row['house_php']), 'senate': int(row['senate_php']),
            'houseUrl': row['house_pdf_url'],
            'senateUrl': row['senate_pdf_url'] if row['senate_page'] else row['page_url'],
            'endpoints': points, 'routeDistancesMeters': endpoint_distances(points),
        })
    for place, points in FMR_ENDPOINTS.items():
        projects.append({
            'title': place, 'kind': 'Farm-to-market road', 'gaa2026': 5_000_000,
            'sourceUrl': FMR_GAA, 'endpoints': points, 'routeDistancesMeters': endpoint_distances(points),
            'note': 'FY2026 enacted line with printed endpoints. The available evidence does not establish completion, pavement condition, or the effect on farm travel.',
        })
    return projects


def build(snapshot):
    nodes = {int(ref): point for ref, point in snapshot['nodes'].items()}
    graph, undirected = defaultdict(list), defaultdict(list)
    for refs, speed, direction in snapshot['roads']:
        for a, b in zip(refs, refs[1:]):
            duration = km(nodes[a], nodes[b]) * 60 / speed
            if direction != '-1':
                graph[a].append((b, duration))
            if direction not in {'yes', '1', 'true'}:
                graph[b].append((a, duration))
            undirected[a].append((b, duration))
            undirected[b].append((a, duration))

    ferry, ferry_minutes = snapshot['ferry']
    island_port, mainland_port = ferry[0], ferry[-1]
    island = component(undirected, island_port)
    mainland = component(undirected, mainland_port)
    if island & mainland:
        raise ValueError('A road crossing already connects the ferry ports in this snapshot.')

    def nearest(point, candidates, limit):
        ref = min(candidates, key=lambda r: (km(nodes[r], point), r))
        distance = km(nodes[ref], point)
        if distance > limit:
            raise ValueError(f'Unable to connect {point} to a road within {limit} km.')
        return ref, distance

    bridge_island, island_gap = nearest(BRIDGE_SITES[0], island, 1)
    bridge_mainland, mainland_gap = nearest(BRIDGE_SITES[1], mainland, 1)
    bridge_path = [nodes[bridge_island], *BRIDGE_SITES, nodes[bridge_mainland]]
    bridge_km = sum(km(a, b) for a, b in zip(bridge_path, bridge_path[1:]))
    bridge_minutes = bridge_km * 60 / 30

    hospitals = json.loads((ROOT / 'data_sources/hospitals.json').read_text())['features']
    hospital = next(r for r in hospitals if r['properties'].get('name') == 'Bolinao Community Hospital')
    hospital_point = hospital['geometry']['coordinates'][::-1]
    hospital_node, hospital_gap = nearest(hospital_point, mainland, .25)
    destinations = []
    for name, (source_node, population) in ORIGINS.items():
        start, access_gap = nearest(nodes[source_node], island, .25)
        modes = {}
        for mode, from_node, to_node, crossing, duration in (
            ('ferry', island_port, mainland_port, polyline(nodes, ferry), ferry_minutes),
            ('bridge', bridge_island, bridge_mainland, bridge_path, bridge_minutes),
        ):
            island_leg = route(graph, start, from_node)
            mainland_leg = route(graph, to_node, hospital_node)
            if island_leg is None or mainland_leg is None:
                raise ValueError(f'No modeled {mode} route from {name} to the hospital.')
            island_minutes, island_path = island_leg
            mainland_minutes, mainland_path = mainland_leg
            minutes = island_minutes + duration + mainland_minutes + (access_gap + hospital_gap) * 60 / 15
            modes[mode] = {
                'minutes': round(minutes, 2),
                'roadKm': round(sum(km(nodes[a], nodes[b]) for path in (island_path, mainland_path)
                                    for a, b in zip(path, path[1:])) + access_gap + hospital_gap
                                + (bridge_km if mode == 'bridge' else 0), 2),
                'legs': [[nodes[source_node], *polyline(nodes, island_path)], crossing,
                         [*polyline(nodes, mainland_path), hospital_point]],
            }
        destinations.append({'name': name, 'population': population, 'point': nodes[source_node], **modes})

    budget = budget_rows()
    return {'snapshotDate': snapshot['snapshotDate'], 'origins': destinations, 'budget': budget,
            'nepUrl': NEP_URL, 'ferryMinutes': ferry_minutes, 'bridgeKm': round(bridge_km, 2),
            'bridgeSnapMeters': [round(island_gap * 1000), round(mainland_gap * 1000)],
            'hospital': hospital_point, 'corridorProjects': corridor_projects(destinations), 'roads': [polyline(nodes, refs) for refs, _, _ in snapshot['roads']],
            'shoreline': [polyline(nodes, refs) for refs in snapshot['shoreline']]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--osm', type=Path, nargs='+', help='Replace the local routing extract from downloaded OSM XML')
    parser.add_argument('--snapshot-date', help='Retrieval date for the supplied OSM XML files')
    args = parser.parse_args()
    source = DATA / 'osm-routing.json.gz'
    if args.osm:
        if not args.snapshot_date:
            parser.error('--snapshot-date is required with --osm')
        snapshot = {**read_osm(args.osm), 'snapshotDate': args.snapshot_date}
        payload = json.dumps(snapshot, separators=(',', ':')).encode()
        source.write_bytes(gzip.compress(payload, mtime=0))
    with gzip.open(source, 'rt', encoding='utf-8') as stream:
        data = build(json.load(stream))
    content = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    for target in (OUT, STATIC):
        (target / 'amendment-access-data.json').write_text(content, encoding='utf-8')
    print(f"Modeled road and ferry access for {len(data['origins'])} barangays.")


if __name__ == '__main__':
    main()
