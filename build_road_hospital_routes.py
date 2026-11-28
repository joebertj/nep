"""Model hospital access when a farm-to-market road is paved or unavailable."""
import json
import re
from collections import defaultdict

from scipy.spatial import cKDTree

from build_bridge_hospital_routes import OUT, PBF, STATIC, Roads, adjacent, mapped_hospitals, tile
from build_amendment_access import km, route

HOUSE = 'https://budget-assets.bettergov.ph/hgab/2027/pdf/hb10858-3r-vol-ib.pdf'


def road_scenario(roads, endpoints, hospitals):
    midpoint = tuple((a + b) / 2 for a, b in zip(*endpoints))
    cells = adjacent(tile(midpoint))
    edges = [edge for cell in cells for edge in roads.edges[cell]]
    unpaved = [edge for edge in edges if edge[6] in roads.unpaved and not edge[7]]
    if not edges:
        return 'No mapped roads in the route area', None

    def road_edges(items, undirected=False):
        for a, b, u, v, speed, way_direction, *_ in items:
            distance = km(u, v)
            if distance <= 0:
                continue
            if undirected or way_direction != '-1':
                yield a, b, distance, speed
            if undirected or way_direction not in {'yes', '1', 'true'}:
                yield b, a, distance, speed

    def coordinates_for(items):
        return {ref: point for a, b, u, v, *_ in items for ref, point in ((a, u), (b, v))}

    def snapper(points):
        keys = list(points)
        tree = cKDTree([points[k] for k in keys])
        def snap(point, limit):
            key = keys[tree.query(point)[1]]
            return key if km(point, points[key]) <= limit else None
        return snap

    coordinates = coordinates_for(edges)
    snap = snapper(coordinates)
    start, end = (snap(point, .075) for point in endpoints)
    if start is None or end is None or start == end:
        return 'Printed endpoints did not identify both ends of a mapped road', None
    length_graph = defaultdict(list)
    for a, b, distance, _ in road_edges(edges, undirected=True):
        length_graph[a].append((b, distance))
    alignment = route(length_graph, start, end)
    if not alignment or alignment[0] > 1.5 * km(*endpoints):
        return 'No direct mapped road between printed endpoints', None
    length, alignment_nodes = alignment
    unpaved_pairs = {frozenset((a, b)) for a, b, *_ in unpaved}
    upgraded_segments = [(a, b) for a, b in zip(alignment_nodes, alignment_nodes[1:])
                         if frozenset((a, b)) in unpaved_pairs]
    upgraded_length = sum(km(coordinates[a], coordinates[b]) for a, b in upgraded_segments)
    can_pave = upgraded_length >= max(.10, length * .25)
    improved_pairs = {frozenset(pair) for pair in upgraded_segments}
    alignment_pairs = {frozenset(pair) for pair in zip(alignment_nodes, alignment_nodes[1:])}
    baseline, improved, closed = defaultdict(list), defaultdict(list), defaultdict(list)
    for a, b, distance, speed in road_edges(edges):
        duration = distance * 60 / speed
        key = frozenset((a, b))
        baseline[a].append((b, duration))
        improved[a].append((b, distance * 60 / 30 if can_pave and key in improved_pairs else duration))
        if key not in alignment_pairs:
            closed[a].append((b, duration))

    def nearest_places(candidates, radius, limit):
        nearby = sorted((km(midpoint, point), name, point) for name, point in candidates
                        if km(midpoint, point) <= radius)
        seen = set()
        for _, name, point in nearby[:limit]:
            node = snap(point, .25)
            if node is not None and node not in seen:
                seen.add(node)
                yield name, point, node

    destinations = list(nearest_places(hospitals, 6, 3))
    settlements = [item for cell in cells for item in roads.settlements[cell]]
    if not destinations:
        return 'No nearby mapped hospital with a road tie-in', None

    def describe(result):
        time, nodes = result
        return {'minutes': round(time, 2),
                'points': [[round(value, 6) for value in coordinates[n]] for n in nodes]}

    def uses(path, pairs):
        return any(frozenset((a, b)) in pairs for a, b in zip(path, path[1:]))

    results = {'paving': [], 'closure': []}
    for name, point, origin in nearest_places(settlements, 4, 30):
        found = set()
        for hospital, destination, node in destinations:
            before = route(baseline, origin, node)
            if not before:
                continue
            trip = {'name': name, 'point': point, 'hospitalName': hospital, 'hospital': destination}
            if can_pave and 'paving' not in found and len(results['paving']) < 6:
                after = route(improved, origin, node)
                if after and before[0] - after[0] >= .1 and uses(after[1], improved_pairs):
                    results['paving'].append({**trip, 'open': describe(before), 'closed': describe(after)})
                    found.add('paving')
            if 'closure' not in found and len(results['closure']) < 6 and uses(before[1], alignment_pairs):
                detour = route(closed, origin, node)
                if detour is None or detour[0] - before[0] >= .1:
                    results['closure'].append({**trip, 'open': describe(before),
                                               'closed': describe(detour) if detour else None})
                    found.add('closure')
        if len(results['closure']) >= 6 and (not can_pave or len(results['paving']) >= 6):
            break
    if results['paving']:
        mode, segments, distance = 'paving', upgraded_segments, upgraded_length
    elif results['closure']:
        mode, segments, distance = 'closure', list(zip(alignment_nodes, alignment_nodes[1:])), length
    else:
        return 'No sampled hospital trip changed under either scenario', None
    span = [[coordinates[a], coordinates[b]] for a, b in segments]
    return 'Hospital routes modeled', {'span': span, 'origins': results[mode], 'length': round(distance, 2),
                                       'mode': mode}


def main():
    projects = json.loads((STATIC / 'connectivity-data.json').read_bytes())['projects']
    rows, eligible = [], {}
    for source in projects:
        key = source['id']
        title = source['title']
        url = f"{HOUSE}#page={source['sourcePage']}"
        rows.append({'id': key, 'title': title, 'region': source['region'], 'url': url,
                     'amount': source['amountPesos'], 'status': 'Outside the paving and printed-endpoint screen'})
        if source['coordinateQualityFlag'] or source['coordinateBasis'] != 'Printed start/end pair':
            continue
        if not re.search(r'\b(?:concret\w*|pav(?:e|ed|ement|ing))\b', title, re.I):
            continue
        endpoints = [(source[prefix + 'Latitude'], source[prefix + 'Longitude']) for prefix in ('start', 'end')]
        if all(None not in point for point in endpoints) and .10 <= km(*endpoints) <= 5:
            eligible[key] = endpoints
    wanted = {cell for points in eligible.values()
              for cell in adjacent(tile(tuple((a + b) / 2 for a, b in zip(*points))))}
    roads = Roads(wanted)
    print('Screening', len(eligible), 'paving candidates in', len(wanted), 'tiles', flush=True)
    roads.apply_file(str(PBF), locations=True, idx='flex_mem')
    print('Road extract loaded', flush=True)
    hospitals = mapped_hospitals()
    # Preselect local hospitals so each candidate only scans nearby points.
    hospital_tiles = defaultdict(list)
    for name, point in hospitals:
        hospital_tiles[tile(point)].append((name, point))
    scenarios = {}
    for row in rows:
        if row['id'] in eligible:
            ends = eligible[row['id']]
            midpoint = tuple((a + b) / 2 for a, b in zip(*ends))
            local_hospitals = [item for cell in adjacent(tile(midpoint)) for item in hospital_tiles[cell]]
            row['status'], scenario = road_scenario(roads, ends, local_hospitals)
            if scenario:
                row['scenario'] = row['id']
                scenarios[row['id']] = {'name': row['title'], 'url': row['url'], 'kind': 'road', **scenario}
    payload = json.dumps({'projects': rows, 'scenarios': scenarios}, ensure_ascii=False, separators=(',', ':')) + '\n'
    for target in (OUT, STATIC):
        (target / 'road-hospital-routes.json').write_text(payload, encoding='utf-8')
    print(len(scenarios), 'road scenarios')


if __name__ == '__main__':
    main()
