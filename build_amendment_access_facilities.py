"""Find school, hospital and evacuation-site map points near printed FMR alignments and matched bridge spans."""
import json
import math
import re

from scipy.spatial import cKDTree

from build_amendment_access import ROOT, OUT, STATIC, km
from build_education_health import FACILITIES, FACILITIES_RAW, is_evacuation_candidate

LIMIT_KM = .5


def segment_distance(point, a, b):
    lon_scale = math.cos(math.radians(sum(p[0] for p in (point, a, b)) / 3))
    px, py = (point[1] - a[1]) * lon_scale, point[0] - a[0]
    dx, dy = (b[1] - a[1]) * lon_scale, b[0] - a[0]
    portion = max(0, min(1, (px * dx + py * dy) / max(dx * dx + dy * dy, 1e-20)))
    return km(point, (a[0] + portion * dy, a[1] + portion * (b[1] - a[1])))


def facilities(filename, amenity):
    doc = json.loads((ROOT / 'data_sources' / filename).read_bytes())
    rows = {}
    for feature in doc['features']:
        props = feature['properties']
        name = props.get('name')
        if props.get('amenity') != amenity or not name or feature['geometry']['type'] != 'Point':
            continue
        if amenity == 'hospital' and (not re.search(r'\bhospital\b|\bmedical (?:center|centre)\b', name, re.I)
                                      or re.search(r'veterinary|animal|dental', name, re.I)):
            continue
        lon, lat = feature['geometry']['coordinates']
        if 4 <= lat <= 22 and 115 <= lon <= 128:
            rows.setdefault((round(lat, 5), round(lon, 5)), name)
    return rows


def evacuation_candidates():
    ids = {
        f"osm:{feature['type']}:{feature['id']}"
        for feature in json.loads(FACILITIES_RAW.read_bytes())['elements']
        if is_evacuation_candidate(feature.get('tags', {}))
    }
    return {
        (round(row['latitude'], 5), round(row['longitude'], 5)): row['name']
        for row in json.loads(FACILITIES.read_bytes())['rows']
        if row['id'] in ids
    }


def main():
    layers = {kind: facilities(kind + 's.json', kind) for kind in ('school', 'hospital')}
    layers['evacuation'] = evacuation_candidates()
    indexes = {kind: (list(rows), cKDTree(list(rows))) for kind, rows in layers.items()}
    projects = json.loads((STATIC / 'connectivity-data.json').read_bytes())['projects']
    alignments = {
        project['id']: [[point[::-1] for point in part] for part in project['routeParts']]
        for project in projects if not project['coordinateQualityFlag']
    }
    bridges = json.loads((STATIC / 'bridge-hospital-routes.json').read_bytes())
    for project in bridges['projects']:
        span = bridges['scenarios'].get(project['scenario'], {}).get('span')
        if span:
            alignments[project['id']] = span

    results = {}
    assessed = []
    for project_id, parts in alignments.items():
        segments = [(a, b) for part in parts for a, b in zip(part, part[1:])]
        if not segments:
            continue
        assessed.append(project_id)
        found = {}
        for kind, rows in layers.items():
            points, tree = indexes[kind]
            nearby = {}
            for a, b in segments:
                center = tuple((x+y)/2 for x, y in zip(a,b))
                radius = (km(a, b) / 2 + LIMIT_KM) / 102
                for index in tree.query_ball_point(center, radius):
                    dist = segment_distance(points[index], a, b)
                    if dist <= LIMIT_KM:
                        nearby[index] = min(dist, nearby.get(index, math.inf))
            closest = sorted(nearby, key=lambda i: (nearby[i], rows[points[i]]))
            if closest:
                found[kind] = {'count': len(closest), 'nearest': [
                    {'name': rows[points[i]], 'point': points[i], 'meters': round(nearby[i])} for i in closest[:3]
                ]}
        if found:
            results[project_id] = found
    payload = {'source': 'MPB school and hospital maps and OpenStreetMap evacuation-site candidates', 'radiusMeters': 500,
               'assessed': assessed, 'results': results}
    content = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (OUT, STATIC):
        (path / 'amendment-access-facilities.json').write_text(content, encoding='utf-8')
    print(len(assessed), 'alignments screened;', len(results), 'near a mapped facility')


if __name__ == '__main__':
    main()
