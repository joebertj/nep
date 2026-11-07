#!/usr/bin/env python3
"""Measure municipal FMR-route proximity to mapped property footprints.

Run using the connectivity environment (requirements-connectivity.txt).
"""
import csv
import json
from collections import Counter

from pyproj import Transformer
from shapely import transform
from shapely.geometry import LineString, Point, shape
from shapely.strtree import STRtree

from build_connectivity_venue_links import OUT, STATIC, Places, project_rows

BUFFER = 100


def build():
    source = json.loads((OUT/'connectivity-property-indicators-data.json').read_text())
    project = Transformer.from_crs(4326, 32651, always_xy=True).transform
    properties, geometries = [], []
    for row in source['rows']:
        if row.get('adminType') != 'Municipality': continue
        geometry = shape(row['geometry']) if row.get('geometry') else Point(row['longitude'], row['latitude'])
        basis = 'Mapped property footprint' if geometry.geom_type in {'Polygon', 'MultiPolygon'} else 'Source point / bounding-box center'
        if geometry.is_empty or not geometry.is_valid:
            geometry = Point(row['longitude'], row['latitude']); basis = 'Source center; invalid footprint withheld'
        properties.append((row, basis)); geometries.append(transform(geometry, project, interleaved=False))
    index = STRtree(geometries)
    places, matches, exclusions = Places(), [], Counter()
    candidates = list(project_rows())
    for road in candidates:
        if any(places.match(*point).get('adminType') != 'Municipality' for point in road['coordinates']):
            exclusions['Route endpoints not both in a mapped municipality'] += 1; continue
        route = transform(LineString(road['coordinates']), project, interleaved=False)
        hits = index.query(route.buffer(BUFFER), predicate='intersects')
        if not len(hits): exclusions['No mapped municipal property within 100 m'] += 1
        for idx in hits:
            row, basis = properties[int(idx)]; distance = route.distance(geometries[int(idx)])
            matches.append({'roadId': road['id'], 'year': road['year'], 'stage': road['stage'],
                            'roadSourceType': road['sourceType'], 'roadTitle': road['title'], 'roadStatus': road['routeStatus'],
                            'allocationPesos': road['amountPesos'], 'sourcePage': road['sourcePage'], 'roadSourceUrl': road['sourceUrl'],
                            'startLatitude': road['coordinates'][0][1], 'startLongitude': road['coordinates'][0][0],
                            'endLatitude': road['coordinates'][-1][1], 'endLongitude': road['coordinates'][-1][0],
                            'placeId': row['id'], 'recordKind': 'Private-property cue',
                            'venueName': row['name'], 'venueType': row['type'], 'venueSourceUrl': row['sourceUrl'],
                            'latitude': row.get('latitude'), 'longitude': row.get('longitude'),
                            'municipality': row['municipality'], 'province': row['province'], 'region': row['region'],
                            'distanceMeters': round(distance, 1), 'distanceBasis': 'Straight source-endpoint route to '+basis.lower(),
                            'areaSquareMeters': row.get('areaSquareMeters'), 'accessTag': row.get('accessTag', ''),
                            'connectionStatus': 'Proximity lead; ownership, entrance and usable access unverified'})
    unique = {}
    for row in matches:
        key = (row['roadId'], row['year'], row['placeId'])
        if key not in unique or row['distanceMeters'] < unique[key]['distanceMeters']:
            unique[key] = row
    matches = list(unique.values())
    matches.sort(key=lambda row: (-row['year'], row['distanceMeters'], row['roadId'], row['placeId']))
    payload = {'builtAtUtc': source['builtAtUtc'], 'source': 'Existing HGAB/DA FMR endpoint routes and public mapped property cues',
               'bufferMeters': BUFFER, 'spatialReference': 'EPSG:32651', 'candidateRouteSegments': len(candidates),
               'uniqueRoadRecords': len({row['roadId'] for row in matches}), 'matchedRoadPlacePairs': len(matches),
               'distanceBasisCounts': dict(Counter(row['distanceBasis'] for row in matches)),
               'exclusionCounts': dict(exclusions),
               'limits': ['Routes are straight segments between source endpoints, not surveyed road alignments.',
                          'Polygon distance uses the mapped footprint; point distance uses a source point or bounds center.',
                          'Restricted-access tags do not verify legal ownership. Proximity does not establish an entrance, project benefit or wrongdoing.',
                          'Both route endpoints and each property must be mapped in municipalities; city and unresolved property records are excluded.'],
               'rows': matches}
    for folder in (OUT, STATIC):
        (folder/'connectivity-remote-fmr-properties.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n')
        with (folder/'connectivity-remote-fmr-properties.csv').open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(matches[0]) if matches else ['roadId','placeId','distanceMeters'])
            writer.writeheader(); writer.writerows(matches)
    # Keep the lazily loaded FMR map current with the just-built venue and
    # property match inventories so Section 2 map buttons always resolve.
    from build_connectivity_map_data import build as build_map_data
    build_map_data()
    print(json.dumps({key: payload[key] for key in ('uniqueRoadRecords','matchedRoadPlacePairs','distanceBasisCounts')}))
    return payload


if __name__ == '__main__': build()
