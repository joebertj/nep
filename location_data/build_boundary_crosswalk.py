#!/usr/bin/env python3
"""Overlay cached ArcGIS polygons; no network access or allocation attribution.

Requires Shapely 2.2. Run with an isolated environment containing Shapely.
"""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from shapely import build_area, make_valid
from shapely.geometry import MultiLineString
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / 'data_sources/arcgis_dpwh/archive/selected'
OUTPUT = ROOT / 'analysis_output/deo_leg_boundary_crosswalk.json'

def cached(profile):
    status = json.loads((ARCHIVE/profile/'status.json').read_text())
    layers = list(status['layers'].values())
    if len(layers) != 1 or layers[0]['state'] != 'complete':
        raise ValueError(f'{profile}: requires one completed layer')
    folder = ARCHIVE/profile/layers[0]['path']
    meta = json.loads((folder/'metadata.json').read_text())
    if meta['extent']['spatialReference'].get('latestWkid', meta['extent']['spatialReference']['wkid']) != 32651:
        raise ValueError('Unexpected CRS: no implicit reprojection permitted')
    path = folder/'features.jsonl'
    digest = hashlib.sha256()
    rows = []
    with path.open('rb') as stream:
        for line in stream:
            digest.update(line)
            rows.append(json.loads(line))
    if len(rows) != layers[0]['expected']:
        raise ValueError('Incomplete source file')
    source = {'path':str(path.relative_to(ROOT)), 'sha256':digest.hexdigest(),
              'count':len(rows), 'crs':'EPSG:32651', 'copyright':meta.get('copyrightText'),
              'effectiveFrom':None, 'effectiveTo':None, 'layerMetadata':str((folder/'metadata.json').relative_to(ROOT))}
    return rows, source

def polygons(rows):
    result = []
    for row in rows:
        rings = row.get('geometry',{}).get('rings')
        if not rings:
            raise ValueError(f'Missing polygon: {row["attributes"]}')
        # GEOS BuildArea determines shell/hole containment rather than assuming
        # that every Esri ring is an independent filled polygon.
        geom = build_area(MultiLineString(rings))
        repaired = not geom.is_valid
        if geom.is_empty:
            # Node self-crossing source ring linework before reconstructing
            # containment. Preserve a repair marker for review.
            geom = build_area(unary_union(MultiLineString(rings)))
            repaired = True
        if repaired:
            geom = make_valid(geom)
        if geom.is_empty or geom.area <= 0:
            raise ValueError(f'Empty/zero-area boundary: {row["attributes"]}')
        result.append((row['attributes'], geom, repaired))
    return result

def main():
    deo_rows, deo_source = cached('engineering_districts')
    leg_rows, leg_source = cached('congressional_districts')
    municipality_rows, municipality_source = cached('city_municipal_boundaries')
    deos, legs = polygons(deo_rows), polygons(leg_rows)
    tree = STRtree([x[1] for x in legs])
    pairs = []
    for number, (d, dg, dr) in enumerate(deos, 1):
        for index in tree.query(dg, predicate='intersects'):
            l, lg, lr = legs[int(index)]
            area = dg.intersection(lg).area
            if area <= 0:
                continue  # Touching alone is not shared coverage.
            df, lf = area/dg.area, area/lg.area
            pairs.append({'deoObjectId':d['OBJECTID'], 'deo':d['DEO'],
                'deoProvince':d.get('PROVINCE'), 'legObjectId':l['OBJECTID'],
                'leg':l['CONG_DIST'], 'legProvince':l.get('PROVINCE'),
                'intersectionAreaSquareMeters':area, 'deoAreaFraction':df,
                'legAreaFraction':lf,
                'status':'small_intersection_review' if area < 10000 or min(df,lf) < .001 else 'spatial_overlap_dates_unverified',
                'geometryRepairApplied':dr or lr,
                'effectiveFrom':None, 'effectiveTo':None})
        print(f'Overlay {number}/{len(deos)}', flush=True)
    municipalities = [{'objectId':r['attributes']['OBJECTID'], 'province':r['attributes'].get('PROVINCE'),
        'municipality':r['attributes'].get('MUNICIPAL'), 'sourceMunicipalCode':r['attributes'].get('MUN_CODE'),
        'deo':r['attributes'].get('DEO'), 'leg':r['attributes'].get('CONG_DIST'),
        'status':'source_label_dates_unverified'} for r in municipality_rows]
    significant = [p for p in pairs if p['status']=='spatial_overlap_dates_unverified']
    deo_counts = Counter(p['deo'] for p in significant)
    leg_counts = Counter(p['leg'] for p in significant)
    payload = {'schemaVersion':1, 'sources':{'deo':deo_source,'leg':leg_source,'municipal':municipality_source},
        'method':{'geometry':'GEOS BuildArea from Esri rings; make_valid only when needed',
            'area':'Planar EPSG:32651 area for boundary screening only; never allocation weights',
            'smallIntersectionReview':'area < 10,000 square meters OR less than 0.1% of either boundary; retained, not discarded',
            'dates':'Copyright and edit timestamps are not effective boundary dates',
            'attribution':'No project, representative or peso assignment is inferred from these intersections'},
        'summary':{'pairs':len(pairs), 'substantialPairs':len(significant),
            'smallIntersectionPairs':len(pairs)-len(significant),
            'deosCoveringMultipleLegs':sum(n>1 for n in deo_counts.values()),
            'legsCoveredByMultipleDeos':sum(n>1 for n in leg_counts.values()),
            'deosWithoutSubstantialIntersection':[d['DEO'] for d,g,r in deos if d['DEO'] not in deo_counts],
            'legsWithoutSubstantialIntersection':[l['CONG_DIST'] for l,g,r in legs if l['CONG_DIST'] not in leg_counts],
            'repairedDeoGeometries':sum(r for d,g,r in deos), 'repairedLegGeometries':sum(r for l,g,r in legs)},
        'pairs':pairs,'municipalityLabels':municipalities}
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    with OUTPUT.with_suffix('.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    print(json.dumps(payload['summary'],indent=2))

if __name__ == '__main__':
    main()
