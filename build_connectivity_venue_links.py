#!/usr/bin/env python3
"""Link coordinate-backed remote FMR routes to mapped visitor venues."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from build_connectivity_report import point_segment_distance, utm51
from build_connectivity_places import Places

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
FMR = OUT / 'fmr_corrected_dataset.json'
VENUES = OUT / 'connectivity-venues-data.json'
CELL = 1000
BUFFER = 100


def valid_lonlat(p):
    try:
        lon, lat = float(p[0]), float(p[1])
    except (TypeError, ValueError, IndexError):
        return False
    return math.isfinite(lon) and math.isfinite(lat) and 115 <= lon <= 128 and 3 <= lat <= 24


def project_rows():
    data = json.loads(FMR.read_text())
    for row in data.get('projects', []):
        for segment in row.get('segments', []):
            coords = segment.get('coordinates') or []
            if len(coords) < 2 or not all(valid_lonlat(p) for p in (coords[0], coords[-1])):
                continue
            source = row.get('source') or {}
            yield {
                'id': row.get('project_id'), 'year': 2027, 'stage': 'HGAB 3rd',
                'sourceType': 'FY2027 HGAB 3rd-reading DA FMR', 'title': row.get('title', ''),
                'amountPesos': int(row.get('amount_php') or 0),
                'sourcePage': source.get('printed_page') or source.get('pdf_page'),
                'sourceUrl': 'https://budget.bettergov.ph/hgab/2027/farm-to-market-roads',
                'coordinates': [coords[0], coords[-1]], 'routeStatus': 'Budgeted project',
            }

    for year in (2024, 2025):
        layers = ROOT / f'data_sources/arcgis_dpwh/archive/selected/da_fmr_fy{year}/layers'
        for feature_path in layers.glob('*/features.jsonl'):
            for line in feature_path.open():
                feature = json.loads(line)
                attrs = feature.get('attributes') or {}
                try:
                    coords = [[float(attrs['start_x']), float(attrs['start_y'])],
                              [float(attrs['end_x']), float(attrs['end_y'])]]
                except (KeyError, TypeError, ValueError):
                    continue
                if not all(valid_lonlat(p) for p in coords):
                    continue
                yield {
                    'id': f"da-fmr-{year}:{attrs.get('objectid')}", 'year': year,
                    'stage': f'DA FMR GIS · FY{year}', 'sourceType': f'DA FMR ArcGIS FY{year}',
                    'title': attrs.get('Project_Description_note') or attrs.get('Contract_Name_note') or 'DA FMR project',
                    'amountPesos': None, 'sourcePage': None,
                    'sourceUrl': f'https://services1.arcgis.com/IwZZTMxZCmAmFYvF/arcgis/rest/services/DA_FMR_FY{year}_LiveView/FeatureServer/0',
                    'coordinates': coords, 'routeStatus': attrs.get('PC_Status_note') or 'Status unavailable',
                }


def build():
    venue_data = json.loads(VENUES.read_text())
    venues = []
    for row in venue_data.get('rows', []):
        if row.get('adminType') != 'Municipality':
            continue
        x, y = utm51(float(row['longitude']), float(row['latitude']))
        venues.append((x, y, row))

    venue_grid = defaultdict(list)
    for idx, (x, y, _) in enumerate(venues):
        venue_grid[int(x // CELL), int(y // CELL)].append(idx)

    places = Places()
    matches, exclusions = [], Counter()
    candidates = list(project_rows())
    for road in candidates:
        coords = road['coordinates']
        route_places = [places.match(*point) for point in coords]
        route_types = [p.get('adminType') for p in route_places]
        if route_types != ['Municipality', 'Municipality']:
            exclusions['Route endpoints not both in a mapped municipality'] += 1
            continue

        a, b = utm51(*coords[0]), utm51(*coords[1])
        xmin, xmax = min(a[0], b[0]) - BUFFER, max(a[0], b[0]) + BUFFER
        ymin, ymax = min(a[1], b[1]) - BUFFER, max(a[1], b[1]) + BUFFER
        nearby_ids = set()
        for gx in range(int(xmin // CELL), int(xmax // CELL) + 1):
            for gy in range(int(ymin // CELL), int(ymax // CELL) + 1):
                nearby_ids.update(venue_grid.get((gx, gy), ()))

        route_matches = []
        for idx in nearby_ids:
            x, y, venue = venues[idx]
            distance = point_segment_distance((x, y), a, b)
            if distance <= BUFFER:
                route_matches.append((distance, venue))
        if not route_matches:
            exclusions['No municipal visitor venue within 100 m'] += 1
            continue

        for distance, venue in sorted(route_matches, key=lambda pair: (pair[0], pair[1]['name'])):
            matches.append({
                'roadId': road['id'], 'year': road['year'], 'stage': road['stage'],
                'roadSourceType': road['sourceType'], 'roadTitle': road['title'],
                'roadStatus': road['routeStatus'], 'allocationPesos': road['amountPesos'],
                'sourcePage': road['sourcePage'], 'roadSourceUrl': road['sourceUrl'],
                'venueName': venue['name'], 'venueType': venue['type'],
                'municipality': venue.get('municipality', ''), 'province': venue.get('province', ''),
                'region': venue.get('region', ''), 'distanceMeters': round(distance, 1),
                'venueSourceUrl': venue['sourceUrl'],
                'remoteScreen': 'Both route endpoints fall in DPWH municipality boundaries',
                'geometryBasis': 'Straight segment between source start/end coordinates; route alignment is not available',
            })

    matches.sort(key=lambda row: (-row['year'], row['distanceMeters'], row['roadTitle'], row['venueName']))
    payload = {
        'scope': 'Coordinate-backed DA FMR project routes with both endpoints in a mapped DPWH municipality and one or more OSM classified visitor venues within 100 m.',
        'builtAtUtc': venue_data.get('builtAtUtc'), 'source': 'FY2027 HGAB DA FMR rows; DA FMR ArcGIS FY2024/FY2025; OSM visitor venue inventory.',
        'bufferMeters': BUFFER, 'candidateRouteSegments': len(candidates),
        'uniqueCandidateRoadRecords': len({r['id'] for r in candidates}),
        'matchedRoadVenuePairs': len(matches), 'uniqueRoadRecords': len({r['roadId'] for r in matches}),
        'venuePairsBySource': dict(Counter(r['roadSourceType'] for r in matches)),
        'exclusionCounts': dict(exclusions),
        'limits': ['A municipality endpoint match is a provisional remote-area proxy; it does not prove the whole alignment is remote.',
                   'Project geometries are reconstructed from source start/end coordinates as straight segments and may not follow the actual road path.',
                   'A 100 m proximity is a review lead, not proof of road access or that a venue is operating.',
                   'Municipal mapped venues are included; city and unresolved venue locations are excluded.',
                   'The DA FY2024/FY2025 ArcGIS tracker includes project progress/status records, not budget allocations.'],
        'rows': matches,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'
    for directory in (OUT, STATIC):
        (directory / 'connectivity-remote-fmr-venues.json').write_text(encoded)
        fields = list(matches[0]) if matches else ['roadId', 'year', 'roadTitle', 'venueName', 'venueType', 'distanceMeters']
        with (directory / 'connectivity-remote-fmr-venues.csv').open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(matches)
    print(json.dumps({k: payload[k] for k in ('candidateRouteSegments', 'uniqueCandidateRoadRecords', 'matchedRoadVenuePairs', 'uniqueRoadRecords', 'venuePairsBySource', 'exclusionCounts')}, ensure_ascii=False))
    # Refresh the separate, lazy-loaded SVG map asset after its route/venue
    # source files are current.  The popup data stays out of the HTML bundle.
    from build_connectivity_map_data import build as build_map_data
    build_map_data()


if __name__ == '__main__':
    build()
