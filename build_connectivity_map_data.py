#!/usr/bin/env python3
"""Build compact, source-linked map geometry for the connectivity detail popup."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
CONNECTIVITY = ROOT / 'analysis_output/connectivity-data.json'
VENUE_LINKS = ROOT / 'analysis_output/connectivity-remote-fmr-venues.json'
VENUES = ROOT / 'analysis_output/connectivity-venues-data.json'
ROAD = ROOT / 'data_sources/arcgis_dpwh/archive/selected/road_classification/layers/Road_Classification_FeatureServer_1-b0aa1cb4/features.jsonl'
OUT = ROOT / 'analysis_output/connectivity-map-data.json'


def simplify(points: list[list[float]], tolerance: float = 35.0) -> list[list[float]]:
    """Iterative Douglas-Peucker simplification in the layer's native metres."""
    if len(points) <= 2:
        return points
    keep = {0, len(points) - 1}
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        ax, ay = points[first][:2]
        bx, by = points[last][:2]
        dx, dy = bx - ax, by - ay
        denom = dx * dx + dy * dy
        best_distance, best_index = -1.0, None
        for index in range(first + 1, last):
            px, py = points[index][:2]
            t = 0 if denom == 0 else max(0.0, min(1.0, ((px-ax)*dx+(py-ay)*dy)/denom))
            distance = math.hypot(px-(ax+t*dx), py-(ay+t*dy))
            if distance > best_distance:
                best_distance, best_index = distance, index
        if best_index is not None and best_distance > tolerance:
            keep.add(best_index)
            stack.extend(((first, best_index), (best_index, last)))
    return [[round(float(value), 1) for value in points[index][:2]] for index in sorted(keep)]


def read_json(path: Path):
    return json.loads(path.read_text())


def build() -> dict:
    connectivity = read_json(CONNECTIVITY)
    links = read_json(VENUE_LINKS)
    venue_by_url = {row.get('sourceUrl'): row for row in read_json(VENUES).get('rows', [])}
    venues_by_route: dict[str, list[dict]] = {}
    venue_match_counts: dict[str, int] = {}
    for row in links.get('rows', []):
        route_id = str(row.get('roadId'))
        venue_match_counts[route_id] = venue_match_counts.get(route_id, 0) + 1
        venue = venue_by_url.get(row.get('venueSourceUrl'))
        if not venue or venue.get('latitude') is None or venue.get('longitude') is None:
            continue
        venues_by_route.setdefault(route_id, []).append({
            'name': venue.get('name'), 'type': venue.get('type'),
            'latitude': venue.get('latitude'), 'longitude': venue.get('longitude'),
            'distanceMeters': row.get('distanceMeters'), 'sourceUrl': row.get('venueSourceUrl'),
        })

    projects = {}
    sections = set()
    for row in connectivity.get('projects', []):
        project_id = str(row['id'])
        sections.add(str(row.get('roadSection') or ''))
        projects[project_id] = {
            'id': project_id, 'title': row.get('title'), 'region': row.get('region'),
            'start': [row.get('startLongitude'), row.get('startLatitude')],
            'end': [row.get('endLongitude'), row.get('endLatitude')],
            'roadSection': row.get('roadSection'), 'roadName': row.get('roadName'),
            'roadClass': row.get('roadClass'), 'nearestDistanceMeters': row.get('nearestDistanceMeters'),
            'closestEnd': row.get('closestEnd'), 'venues': venues_by_route.get(project_id, []),
            'venueMatchCount': venue_match_counts.get(project_id, 0),
        }

    # Section 2 also includes FY2024/FY2025 coordinate-backed DA tracker rows.
    needed = {str(row.get('roadId')) for row in links.get('rows', [])}
    for year in (2024, 2025):
        layer_root = ROOT / f'data_sources/arcgis_dpwh/archive/selected/da_fmr_fy{year}/layers'
        for feature_path in layer_root.glob('*/features.jsonl'):
            with feature_path.open() as source:
                for line in source:
                    feature = json.loads(line)
                    attrs = feature.get('attributes') or {}
                    route_id = f"da-fmr-{year}:{attrs.get('objectid')}"
                    if route_id not in needed:
                        continue
                    try:
                        start = [float(attrs['start_x']), float(attrs['start_y'])]
                        end = [float(attrs['end_x']), float(attrs['end_y'])]
                    except (KeyError, TypeError, ValueError):
                        continue
                    if not (115 <= start[0] <= 128 and 3 <= start[1] <= 24 and 115 <= end[0] <= 128 and 3 <= end[1] <= 24):
                        continue
                    projects[route_id] = {
                        'id': route_id,
                        'title': attrs.get('Project_Description_note') or attrs.get('Contract_Name_note') or 'DA FMR project',
                        'region': attrs.get('Region_note'), 'start': start, 'end': end,
                        'roadSection': None, 'roadName': None, 'roadClass': None,
                        'nearestDistanceMeters': None, 'venues': venues_by_route.get(route_id, []),
                        'venueMatchCount': venue_match_counts.get(route_id, 0),
                    }

    roads = {}
    with ROAD.open() as source:
        for line in source:
            feature = json.loads(line)
            attrs = feature.get('attributes') or {}
            section = str(attrs.get('SECTION_ID') or '')
            if section not in sections or section in roads:
                continue
            paths = []
            for path in (feature.get('geometry') or {}).get('paths') or []:
                simplified = simplify(path)
                if len(simplified) >= 2:
                    paths.append(simplified)
            roads[section] = {
                'name': attrs.get('ROAD_NAME'), 'class': attrs.get('ROAD_SEC_CLASS'),
                'roadId': attrs.get('ROAD_ID'), 'pathsUtm51': paths,
            }

    payload = {
        'source': 'DPWH Road Classification FeatureServer layer 1; FY2027 HGAB FMR endpoint rows; DA FMR ArcGIS FY2024/FY2025; OSM visitor venues.',
        'roadSpatialReference': 'EPSG:32651',
        'municipalityBoundaries': 'out-of-place-boundaries.json (DPWH City-Municipal Boundaries, WGS84 rings)',
        'routeGeometryBasis': 'Straight line between the source start/end coordinates; not a surveyed alignment.',
        'farmLocationAvailable': False,
        'projects': projects,
        'roads': roads,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    OUT.write_text(encoded)
    (STATIC / 'connectivity-map-data.json').write_text(encoded)
    print(json.dumps({'projects': len(projects), 'roadSections': len(roads), 'venueRoutes': sum(bool(p['venues']) for p in projects.values()), 'bytes': len(encoded)}))
    return payload


if __name__ == '__main__':
    build()
