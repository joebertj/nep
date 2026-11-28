"""Compare existing mapped roads with a straight-line 30 km/h benchmark for FMR proposals."""
import json
from collections import defaultdict

from scipy.spatial import cKDTree

from build_amendment_access import km, route
from build_bridge_hospital_routes import OUT, PBF, STATIC, Roads, adjacent, tile


def endpoints(row):
    return [(row[f'{end}Latitude'], row[f'{end}Longitude']) for end in ('start', 'end')]


def midpoint(points):
    return tuple((a + b) / 2 for a, b in zip(*points))


def compare(roads, points):
    cells = adjacent(tile(midpoint(points)))
    edges = [edge for cell in cells for edge in roads.edges[cell]]
    coordinates = {n: p for a, b, u, v, *_ in edges for n, p in ((a, u), (b, v))}
    if not coordinates:
        return None
    keys = list(coordinates)
    tree = cKDTree([coordinates[n] for n in keys])
    start, end = [keys[i] for i in tree.query(points)[1]]
    if start == end:
        return None
    gaps = [km(point, coordinates[node]) for point, node in zip(points, (start, end))]
    if max(gaps) > .075:
        return None
    graph = defaultdict(list)
    for a, b, u, v, speed, direction, *_ in edges:
        duration = km(u, v) * 60 / speed
        if duration <= 0:
            continue
        if direction != '-1':
            graph[a].append((b, duration))
        if direction not in {'yes', '1', 'true'}:
            graph[b].append((a, duration))
    benchmark = km(*points) * 2
    # Add the same final approach at both ends at a conservative access speed.
    tie_in = sum(gaps) * 60 / 15
    comparisons = []
    for label, (a, b) in (('Start to end', (start, end)), ('End to start', (end, start))):
        path = route(graph, a, b)
        if not path or path[0] + tie_in > benchmark - .2:
            continue
        length = sum(km(coordinates[u], coordinates[v]) for u, v in zip(path[1], path[1][1:])) + sum(gaps)
        comparisons.append({'direction': label, 'existingMinutes': round(path[0] + tie_in, 2),
                            'existingKm': round(length, 2), 'points': [
                                [round(axis, 6) for axis in coordinates[node]] for node in path[1]
                            ]})
    if comparisons:
        return {'benchmarkMinutes': round(benchmark, 2), 'tiesMeters': [round(d * 1000) for d in gaps],
                'routes': comparisons}
    return None


def main():
    rows = json.loads((STATIC / 'connectivity-data.json').read_bytes())['projects']
    eligible = [row for row in rows if not row['coordinateQualityFlag']
                and row['coordinateBasis'] == 'Printed start/end pair'
                and all(None not in point for point in endpoints(row))
                and .2 <= km(*endpoints(row)) <= 5]
    roads = Roads({cell for row in eligible for cell in adjacent(tile(midpoint(endpoints(row))))})
    print(len(eligible), 'endpoint pairs screened', flush=True)
    roads.apply_file(str(PBF), locations=True, idx='flex_mem')
    print('Road extract loaded', flush=True)
    results = {}
    for row in eligible:
        comparison = compare(roads, endpoints(row))
        if comparison:
            results[row['id']] = comparison
    payload = {'screened': len(eligible), 'minimumDifferenceMinutes': .2, 'benchmarkKph': 30,
               'results': results}
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (OUT, STATIC):
        (path / 'fmr-route-alternatives.json').write_text(content)
    print(len(results), 'FMRs with an existing mapped connection that beats the benchmark')


if __name__ == '__main__':
    main()
