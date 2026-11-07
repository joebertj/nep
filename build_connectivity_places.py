#!/usr/bin/env python3
"""Build reusable venue and private-property source layers; never fetch roads.

Default: normalize cached public OSM snapshots. --download refreshes the saved
Overpass queries first. Source locations are review evidence, not valuations,
ownership verification, road connections, or project allocation assignments.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from build_connectivity_report import utm51

ROOT = Path(__file__).resolve().parent
RAW = ROOT / 'data_sources/connectivity_online'
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
BOUNDARIES = ROOT / 'data_sources/arcgis_dpwh/archive/selected/city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
SOURCES = (
    ('osm-visitor-venues', 'https://overpass-api.de/api/interpreter'),
    ('osm-additional-venues', 'https://overpass-api.de/api/interpreter'),
    ('osm-private-properties', 'https://overpass-api.de/api/interpreter'),
    ('osm-large-residential', 'https://overpass-api.de/api/interpreter'),
    ('osm-expanded-venues', 'https://overpass-api.de/api/interpreter'),
    ('osm-private-access-properties', 'https://overpass-api.de/api/interpreter'),
    ('osm-public-services', 'https://download.geofabrik.de/asia/philippines-261104.osm.pbf'),
)
QUERIES = {
    'osm-visitor-venues': '[out:json][timeout:180];area["ISO3166-1"="PH"][admin_level=2]->.ph;(nwr["tourism"~"^(hotel|motel|guest_house|chalet|hostel|resort)$"](area.ph);nwr["leisure"="resort"](area.ph);nwr["amenity"="events_venue"](area.ph););out body geom;',
    'osm-additional-venues': '[out:json][timeout:120];area["ISO3166-1"="PH"][admin_level=2]->.ph;(nwr["tourism"~"^(rest_house|resthouse|holiday_home|holiday_house|villa|pension|inn)$"](area.ph);nwr["amenity"~"^(event_venue|conference_centre)$"](area.ph);nwr["name"~"rest[ -]?house|events? (place|venue|center|centre)|function hall",i](area.ph););out center tags;',
    'osm-private-properties': '[out:json][timeout:180];area["ISO3166-1"="PH"][admin_level=2]->.ph;(nwr["building"~"^(villa|mansion)$"](area.ph);nwr["landuse"="residential"]["name"~"subdivision|subd[.]?|estate|hacienda|village",i](area.ph);nwr["residential"~"^(gated|gated_community|mansions|subdivision)$"](area.ph););out body geom;',
    'osm-large-residential': '[out:json][timeout:180];area["ISO3166-1"="PH"][admin_level=2]->.ph;(way["building"~"^(house|detached|villa|mansion|residential)$"](area.ph)(if:length()>110););out body geom;',
    'osm-expanded-venues': '[out:json][timeout:180];area["ISO3166-1"="PH"][admin_level=2]->.ph;(nwr["tourism"~"^(apartment|camp_site|caravan_site|holiday_home|holiday_house|villa|alpine_hut|wilderness_hut)$"](area.ph);nwr["leisure"~"^(beach_resort|spa_resort|water_park|golf_course)$"](area.ph);nwr["amenity"~"^(event_venue|events_place|conference_centre)$"](area.ph););out body geom;',
    'osm-private-access-properties': '[out:json][timeout:180];area["ISO3166-1"="PH"][admin_level=2]->.ph;(nwr["landuse"="residential"]["access"~"^(private|residents|permit)$"](area.ph);nwr["residential"~"^(gated|gated_community|private|apartments|apartment_complex)$"](area.ph);nwr["leisure"~"^(garden|swimming_pool|sports_centre|pitch)$"]["access"~"^(private|members)$"](area.ph););out body geom;',
}
PUBLIC_OPERATOR = re.compile(r'government|municipal|barangay|\bLGU\b|\bTIEZA\b|tourism infrastructure|department of|provincial capitol|city hall', re.I)
PROPERTY_CUE = re.compile(r'\b(subdivision|subd\.?|estate|hacienda|village)\b', re.I)
REST_HOUSE = re.compile(r'\brest[ -]?house\b', re.I)
EVENT = re.compile(r'\bevents?\s+(place|venue|center|centre)|\bfunction hall\b', re.I)
SMALL_HOME = {'apartments', 'residential', 'dormitory'}
# Whole-word screening avoids hiding ordinary names that merely contain a
# short substring. Keep this limited to clear profanity and common slurs.
OFFENSIVE_NAME = re.compile(
    r'(?<!\w)(?:'
    r'fuck(?:er|ers|ing|ed|s)?|motherfucker(?:s)?|shit(?:ty|head|heads|s)?|'
    r'bullshit|asshole(?:s)?|bitch(?:es|y)?|bastard(?:s)?|cunt(?:s)?|'
    r'dickhead(?:s)?|cock(?:sucker|suckers)?|piss(?:ed)?|'
    r'putang.?ina|putangina|tang.?ina|tangina|gago|gaga|putragis|'
    r'puta|punyeta|punyemas|pakshet|pakshit|pucha|puchang|leche|lintik|'
    r'buwisit|bwisit|tarantado|ang\s+tanga|tanga\s+(?:ka|mo|naman)|'
    r'ang\s+bobo|bobo\s+(?:ka|mo|naman)|kupal|hindot|iyot|kantot|'
    r'puke|pekpek|puki|burat|titi|etits|tae|ulol|unggoy|'
    r'nigger(?:s)?|nigga(?:s)?|faggot(?:s)?|retard(?:ed|s)?|kike(?:s)?|'
    r'chink(?:s)?|spic(?:s)?|tranny|whore(?:s)?|slut(?:s)?'
    r')(?!\w)', re.IGNORECASE)


def clean_osm_name(value):
    """Replace clearly offensive mapped names before writing public outputs."""
    name = str(value or '')
    if OFFENSIVE_NAME.search(name):
        return 'Name withheld', True
    return name, False


def compact(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n'


def refresh():
    RAW.mkdir(parents=True, exist_ok=True)
    for stem, endpoint in SOURCES:
        query = RAW / (stem + '.overpassql')
        query.write_text(QUERIES[stem])
        request = urllib.request.Request(endpoint, data=urllib.parse.urlencode({'data': query.read_text()}).encode(), headers={'User-Agent': 'BetterGov public budget research'})
        try:
            raw = urllib.request.urlopen(request, timeout=240).read()
            data = json.loads(raw)
            if data.get('remark'):
                raise ValueError(data['remark'])
            if not isinstance(data.get('elements'), list):
                raise ValueError('Response has no elements array')
            (RAW / (stem + '-raw.json')).write_bytes(raw)
            print(stem, len(data['elements']), 'records', flush=True)
        except Exception as exc:
            print(stem, 'refresh failed; retained previous snapshot:', exc, flush=True)


def ring_area(ring):
    points = [utm51(lon, lat) for lon, lat in ring]
    if len(points) < 4 or ring[0] != ring[-1]:
        return None
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]))) / 2


def element_geometry(el):
    if el['type'] == 'way':
        coords = [[p['lon'], p['lat']] for p in el.get('geometry', []) if 'lon' in p and 'lat' in p]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            return {'type': 'Polygon', 'coordinates': [coords]}
    if el['type'] == 'relation' and el.get('tags', {}).get('type') == 'multipolygon':
        roles = defaultdict(list)
        for member in el.get('members', []):
            coords = [[p['lon'], p['lat']] for p in member.get('geometry', []) if 'lon' in p and 'lat' in p]
            if member.get('type') == 'way' and len(coords) >= 2:
                roles[member.get('role') or 'outer'].append(coords)
        def join_rings(paths):
            pending, rings = list(paths), []
            while pending:
                ring = pending.pop()
                while ring[0] != ring[-1]:
                    for i, path in enumerate(pending):
                        if ring[-1] == path[0]:
                            ring.extend(path[1:])
                        elif ring[-1] == path[-1]:
                            ring.extend(path[-2::-1])
                        elif ring[0] == path[-1]:
                            ring = path[:-1] + ring
                        elif ring[0] == path[0]:
                            ring = path[:0:-1] + ring
                        else:
                            continue
                        pending.pop(i)
                        break
                    else:
                        return None
                if len(ring) < 4:
                    return None
                rings.append(ring)
            return rings
        outer, inner = join_rings(roles['outer']), join_rings(roles['inner'])
        if outer and inner is not None:
            polygons = [[r] for r in outer]
            valid = True
            for hole in inner:
                holders = [p for p in polygons if inside(hole[0], p[0])]
                if len(holders) != 1:
                    valid = False
                    break
                holders[0].append(hole)
            if valid:
                return {'type': 'Polygon', 'coordinates': polygons[0]} if len(polygons) == 1 else {'type': 'MultiPolygon', 'coordinates': polygons}
    # Incomplete relation geometries retain their source location, not an
    # invented boundary or a sum of potentially overlapping member polygons.
    if el.get('center'):
        return {'type': 'Point', 'coordinates': [el['center']['lon'], el['center']['lat']]}
    if 'lat' in el and 'lon' in el:
        return {'type': 'Point', 'coordinates': [el['lon'], el['lat']]}
    bounds = el.get('bounds')
    if bounds:
        return {'type': 'Point', 'coordinates': [(bounds['minlon']+bounds['maxlon'])/2, (bounds['minlat']+bounds['maxlat'])/2]}
    return None


def location(geom):
    if geom['type'] == 'Point':
        return geom['coordinates']
    points = geom['coordinates'][0] if geom['type'] == 'Polygon' else [p for polygon in geom['coordinates'] for p in polygon[0]]
    return [(min(p[0] for p in points)+max(p[0] for p in points))/2,
            (min(p[1] for p in points)+max(p[1] for p in points))/2]


def geometry_area(geom):
    if geom['type'] == 'Point':
        return None
    polygons = [geom['coordinates']] if geom['type'] == 'Polygon' else geom['coordinates']
    total = 0
    for polygon in polygons:
        areas = [ring_area(r) for r in polygon]
        if any(a is None for a in areas):
            return None
        area = areas[0] - sum(areas[1:])
        if area <= 0:
            return None
        total += area
    return total


def inside(point, ring):
    x, y = point
    result = False
    previous = ring[-1]
    for current in ring:
        ax, ay = previous[:2]
        bx, by = current[:2]
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            result = not result
        previous = current
    return result


class Places:
    def __init__(self):
        self.features = []
        self.grid = defaultdict(list)
        with BOUNDARIES.open() as handle:
            for line in handle:
                feature = json.loads(line)
                rings = feature.get('geometry', {}).get('rings') or []
                points = [p for r in rings for p in r]
                if not points:
                    continue
                bounds = (min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points))
                index = len(self.features)
                self.features.append((bounds, rings, feature['attributes']))
                for x in range(int(bounds[0]//20000), int(bounds[2]//20000)+1):
                    for y in range(int(bounds[1]//20000), int(bounds[3]//20000)+1):
                        self.grid[x, y].append(index)

    def match(self, lon, lat):
        point = utm51(lon, lat)
        matches = []
        for idx in self.grid.get((int(point[0]//20000), int(point[1]//20000)), []):
            bounds, rings, attrs = self.features[idx]
            if not (bounds[0] <= point[0] <= bounds[2] and bounds[1] <= point[1] <= bounds[3]):
                continue
            if sum(inside(point, r) for r in rings) % 2:
                matches.append(attrs)
        identities = {(a.get('PROVINCE'), a.get('MUN_DBM') or a.get('MUNICIPAL')) for a in matches}
        if len(identities) != 1:
            return {'region': '', 'province': '', 'municipality': '', 'adminType': '', 'placeEvidence': 'Boundary match unresolved'}
        a = matches[0]
        admin_type = a.get('CENTERS') or ''
        if admin_type == 'Capital':
            admin_type = 'City' if re.search(r'\bcity\b', a.get('MUNICIPAL') or '', re.I) else 'Municipality'
        return {'region': a.get('REGION') or '', 'province': a.get('PROVINCE') or '',
                'municipality': a.get('MUN_DBM') or a.get('MUNICIPAL') or '', 'adminType': admin_type,
                'placeEvidence': 'Source point / bounding-box center in DPWH municipality/city polygon (March 2022)'}


def excluded(tags):
    if tags.get('operator:type', '') in {'government', 'public', 'municipal_government', 'school', 'religious'} or tags.get('ownership') in {'government', 'public'} or PUBLIC_OPERATOR.search(tags.get('operator', '')) or PUBLIC_OPERATOR.search(tags.get('owner', '')):
        return 'Government / public operator indicated'
    if tags.get('amenity') in {'marketplace', 'public_building', 'townhall', 'community_centre', 'place_of_worship', 'school', 'social_facility'}:
        return 'Public market / government / community facility'
    if any(tags.get(k) not in (None, '', 'no') for k in ('disused', 'abandoned', 'demolished', 'construction', 'disused:tourism', 'abandoned:tourism', 'demolished:tourism')):
        return 'Closed / disused / construction indicated'
    return None


def venue_type(tags):
    name = tags.get('name', '')
    tourism, leisure, amenity = (tags.get(k, '') for k in ('tourism', 'leisure', 'amenity'))
    if tags.get('building') in SMALL_HOME and not (leisure in {'resort', 'beach_resort', 'spa_resort'} or tourism in {'hotel', 'resort', 'apartment', 'holiday_home', 'holiday_house', 'villa'} or amenity in {'events_venue', 'event_venue'}):
        return None
    if leisure in {'water_park', 'golf_course'}:
        return {'water_park': 'Water park', 'golf_course': 'Golf course'}[leisure]
    if leisure in {'resort', 'beach_resort', 'spa_resort'} or tourism == 'resort':
        return 'Resort'
    if amenity in {'events_venue', 'event_venue', 'events_place', 'conference_centre'}:
        return 'Event venue'
    mapped_lodging = {'hotel': 'Hotel', 'motel': 'Motel', 'hostel': 'Hostel', 'guest_house': 'Guest house', 'chalet': 'Rest house / chalet', 'rest_house': 'Rest house / chalet', 'resthouse': 'Rest house / chalet', 'inn': 'Guest house', 'pension': 'Guest house',
                      'apartment': 'Holiday apartment', 'holiday_home': 'Holiday home / villa', 'holiday_house': 'Holiday home / villa', 'villa': 'Holiday home / villa', 'camp_site': 'Campsite', 'caravan_site': 'Caravan site', 'alpine_hut': 'Visitor hut', 'wilderness_hut': 'Visitor hut'}
    if tourism in mapped_lodging:
        if REST_HOUSE.search(name) or tourism == 'chalet':
            return 'Rest house / chalet'
        if re.search(r'\bresort\b', name, re.I):
            return 'Resort'
        if EVENT.search(name):
            return 'Event venue'
        return mapped_lodging[tourism]
    if EVENT.search(name) and (tags.get('building') == 'commercial' or tags.get('shop') or tags.get('office') == 'company'):
        return 'Event venue'
    return None


def public_service_type(tags):
    amenity=tags.get('amenity','');healthcare=tags.get('healthcare','');education=tags.get('education','')
    if amenity in {'school','kindergarten','college','university'} or education in {'school','kindergarten','college','university'}:
        return 'School / education facility'
    if amenity in {'hospital','clinic','doctors','dentist','health_centre','health_post'} or healthcare in {'hospital','clinic','doctor','dentist','health_centre','centre','health_post','dispensary','rehabilitation','midwife'}:
        return 'Health / medical facility'
    if amenity in {'fire_station','police','ambulance_station'}:
        return 'Emergency-response facility'
    if amenity in {'community_centre','social_facility','townhall','public_building','library'}:
        return 'Civic / community service'
    return None


def build():
    places = Places()
    inputs, elements, property_elements, service_elements = [], {}, {}, {}
    for stem, endpoint in SOURCES:
        path = RAW / (stem + '-raw.json')
        if not path.exists():
            continue
        raw = path.read_bytes()
        source = json.loads(raw)
        inputs.append({'file': str(path.relative_to(ROOT)), 'endpoint': source.get('bettergovEndpoint', endpoint), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'snapshotUtc': source.get('osm3s', {}).get('timestamp_osm_base'), 'rawElements': len(source['elements'])})
        if source.get('bettergovSourceSha256'):
            inputs[-1].update(countryExtract=source['bettergovSourceFile'], countryExtractSha256=source['bettergovSourceSha256'])
        dest = service_elements if stem == 'osm-public-services' else property_elements if stem in {'osm-private-properties', 'osm-large-residential', 'osm-private-access-properties'} else elements
        for element in source['elements']:
            if source.get('bettergovCountryFilter'):
                geom = element_geometry(element)
                if not geom or not places.match(*location(geom)).get('adminType'):
                    continue  # Bounding-box queries also cover foreign territory.
            dest[element['type'], element['id']] = element
    venues, review, properties, public_services, discarded = [], [], [], [], Counter()
    by_name = defaultdict(list)
    for key, el in elements.items():
        tags = el.get('tags', {})
        reason = excluded(tags)
        if reason:
            discarded[reason] += 1
            continue
        geom = element_geometry(el)
        if not geom:
            discarded['No usable location'] += 1
            continue
        lon, lat = location(geom)
        kind = venue_type(tags)
        raw_name = tags.get('name') or tags.get('name:en') or f'Unnamed mapped {kind or "venue"}'
        name, name_sanitized = clean_osm_name(raw_name)
        row = {'id': f'osm:{el["type"]}:{el["id"]}', 'name': name, 'type': kind or 'Name cue · business use unverified',
               'latitude': lat, 'longitude': lon, 'coordinateBasis': 'OSM node' if el['type'] == 'node' else 'OSM bounding-box center',
               'recordKind': 'Visitor venue', 'geometry': geom,
               'source': 'OpenStreetMap', 'sourceUrl': f'https://www.openstreetmap.org/{el["type"]}/{el["id"]}',
               'evidence': '; '.join(f'{k}={tags[k]}' for k in ('tourism', 'leisure', 'amenity', 'building') if tags.get(k)),
               'ownershipStatus': 'Private/public ownership unverified; government indicators screened',
               'operatingStatus': 'Mapped at source snapshot; current operation unverified'}
        if name_sanitized:
            row['nameSanitized'] = True
            row['nameScreen'] = 'Potentially offensive source name withheld'
        row.update(places.match(lon, lat))
        if not kind:
            if REST_HOUSE.search(name) or EVENT.search(name):
                row['name'] = 'Rest-house name cue · business use unverified' if REST_HOUSE.search(name) else 'Event-place name cue · business use unverified'
                row['evidence'] += '; visitor-venue name cue only'
                review.append(row)
            else:
                discarded['Not a qualifying visitor venue'] += 1
            continue
        # Use the source name only in this in-memory dedup key; never serialize it.
        norm = ' '.join(re.findall(r'\w+', raw_name.casefold())) if not raw_name.startswith('Unnamed mapped') else row['id']
        duplicate = None
        for previous in by_name[norm]:
            distance = math.hypot((lon-previous['longitude'])*111320*math.cos(math.radians(lat)), (lat-previous['latitude'])*110540)
            if distance <= 50:
                duplicate = previous
                break
        if duplicate:
            duplicate.setdefault('duplicateSourceUrls', []).append(row['sourceUrl'])
            if duplicate['geometry']['type'] == 'Point' and geom['type'] != 'Point':
                duplicate['geometry'] = geom
                duplicate['geometrySourceUrl'] = row['sourceUrl']
            discarded['Same-name OSM record within 50 m merged'] += 1
        else:
            by_name[norm].append(row)
            venues.append(row)

    for key, el in property_elements.items():
        tags = el.get('tags', {})
        if excluded(tags) or venue_type(tags):
            continue
        geom = element_geometry(el)
        if not geom:
            continue
        lon, lat = location(geom)
        area = geometry_area(geom)
        name = tags.get('name', '')
        is_subdivision = bool((tags.get('landuse') == 'residential' and re.search(r'\b(subdivision|subd\.?|village)\b', name, re.I)) or tags.get('residential') in {'gated', 'gated_community', 'subdivision'})
        is_estate = bool((re.search(r'\b(estate|hacienda)\b', name, re.I) and tags.get('landuse') == 'residential') or tags.get('residential') == 'mansions')
        private_residential = ((tags.get('landuse') == 'residential' and tags.get('access') in {'private', 'residents', 'permit'})
                               or tags.get('residential') in {'private', 'apartments', 'apartment_complex'})
        private_recreation = tags.get('leisure') in {'garden', 'swimming_pool', 'sports_centre', 'pitch'} and tags.get('access') in {'private', 'members'}
        large_house = tags.get('building') in {'house', 'detached', 'villa', 'mansion', 'residential'} and area is not None and area >= 1000
        if is_subdivision:
            kind = 'Subdivision / residential village cue'
        elif is_estate:
            kind = 'Residential estate cue'
        elif large_house:
            kind = 'Large residential footprint · ≥1,000 m²'
        elif tags.get('building') in {'villa', 'mansion'}:
            kind = 'Villa / mansion tag · size/value unverified'
        elif private_residential:
            kind = 'Residential compound · restricted-access tag'
        elif private_recreation:
            kind = 'Recreation property · private / members-access tag'
        else:
            continue
        properties.append({'id': f'osm:{el["type"]}:{el["id"]}', 'type': kind, 'name': kind, 'recordKind': 'Private-property cue',
                           'latitude': lat, 'longitude': lon, 'areaSquareMeters': round(area, 1) if area is not None else None,
                           'geometry': geom, 'buildingTag': tags.get('building') or '', 'landuseTag': tags.get('landuse') or '',
                           'accessTag': tags.get('access') or '', 'leisureTag': tags.get('leisure') or '',
                           'source': 'OpenStreetMap', 'sourceUrl': f'https://www.openstreetmap.org/{el["type"]}/{el["id"]}',
                           'valuationPesos': None, 'ownershipStatus': 'Unverified; no owner data published',
                           'reviewSignal': 'remote_road_subdivision_connection' if is_subdivision else 'remote_road_estate_proximity' if is_estate else 'remote_road_large_residential_proximity' if large_house else 'remote_road_restricted_access_property' if private_residential or private_recreation else 'remote_road_villa_tag_review',
                           'connectionStatus': 'Not evaluated against remote roads', **places.match(lon, lat)})

    service_seen=defaultdict(list)
    for key,el in service_elements.items():
        tags=el.get('tags',{});kind=public_service_type(tags)
        if not kind: continue
        geom=element_geometry(el)
        if not geom: continue
        lon,lat=location(geom);raw_name=tags.get('name') or tags.get('name:en') or kind
        name,name_sanitized=clean_osm_name(raw_name)
        norm=' '.join(re.findall(r'\w+',raw_name.casefold())) if tags.get('name') or tags.get('name:en') else f'{el["type"]}:{el["id"]}'
        if any(math.hypot((lon-r['longitude'])*111320*math.cos(math.radians(lat)),(lat-r['latitude'])*110540)<=75 for r in service_seen[(kind,norm)]):
            continue
        row={'id':f'osm:{el["type"]}:{el["id"]}','name':name,'type':kind,'latitude':lat,'longitude':lon,
             'coordinateBasis':'OSM node' if el['type']=='node' else 'OSM bounding-box center',
             'source':'OpenStreetMap','sourceUrl':f'https://www.openstreetmap.org/{el["type"]}/{el["id"]}',
             'evidence':'; '.join(f'{k}={tags[k]}' for k in ('amenity','healthcare','education','office') if tags.get(k)),
             **places.match(lon,lat)}
        if name_sanitized: row['nameSanitized']=True
        service_seen[(kind,norm)].append(row);public_services.append(row)
    public_services.sort(key=lambda r:(r['province'],r['municipality'],r['type'],r['name'],r['id']))

    venues.sort(key=lambda r: (r['province'], r['municipality'], r['type'], r['name']))
    properties.sort(key=lambda r: (r['province'], r['municipality'], r['type'], r['id']))
    from connectivity_place_enrichment import enrich
    official_rows = enrich(venues, RAW, inputs, datetime.fromtimestamp((RAW/'san-juan-dot-directory.html').stat().st_mtime, timezone.utc).isoformat()
                          if (RAW/'san-juan-dot-directory.html').exists() else None)
    common = {'builtAtUtc': datetime.now(timezone.utc).isoformat(), 'source': 'OpenStreetMap contributors',
              'sourceUrl': 'https://www.openstreetmap.org/copyright', 'license': 'ODbL 1.0', 'inputs': inputs,
              'adminBoundarySource': 'Archived DPWH City-Municipal Boundaries, March 2022; point/bounding-box-center containment; unresolved matches retained',
              'bufferMeters': 100, 'offensiveNamesWithheld': sum(bool(r.get('nameSanitized')) for r in venues),
              'nameScreen': 'Clear profanity and slurs in mapped names are replaced with a neutral label in public outputs',
              'roadJoinStatus': 'Source place inventory only; remote-road proximity and access require a separate spatial join'}
    inventories = {
        'connectivity-venues-data': {**common, 'scope': 'Philippine mapped hotels, resorts, guest houses, rest houses/chalets, motels, hostels and event venues',
                                     'count': len(venues), 'typeCounts': dict(Counter(r['type'] for r in venues)), 'excludedCounts': dict(discarded),
                                     'deduplication': 'Same normalized business name within 50 m merged; anonymous businesses retained separately',
                                     'rows': venues},
        'connectivity-venue-review-data': {**common, 'scope': 'Rest-house and event-place name cues lacking sufficient business-use tags; not qualified businesses', 'count': len(review), 'rows': review},
        'connectivity-official-venues-data': {**common, 'scope': 'Municipal tourism directory listings; unmatched listings retain no coordinates and do not enter proximity calculations',
                                            'source': 'San Juan municipal tourism directory and map-name reconciliation',
                                            'sourceUrl': 'https://www.sanjuanbatangas.gov.ph/tourism/dot-accredited-enterprises',
                                            'license': 'Government source listing; original source retained',
                                            'count': len(official_rows), 'matchedMapRecords': sum(bool(r['matchedOsmIds']) for r in official_rows),
                                            'rows': official_rows},
        'connectivity-property-indicators-data': {**common, 'scope': 'Subdivision/village, residential-estate, villa/mansion, large-house footprint and restricted-access residential/recreation review candidates',
                                                 'count': len(properties), 'typeCounts': dict(Counter(r['type'] for r in properties)),
                                                 'largeHouseMinimumFootprintSquareMeters': 1000,
                                                 'limits': ['Footprint area is measured in UTM 51N; incomplete relation boundaries retain a source location and no measured area.',
                                                            'Estate/village names may refer to whole developments; they do not establish a single private owner.',
                                                            'Property value is unknown. A large footprint does not establish an expensive house.',
                                                            'Proximity is not an established entrance or connection; no budget amounts are assigned by this inventory.',
                                                            'Owner names, private-property labels, contact details and full street addresses are omitted.'],
                                                 'rows': properties},
        'connectivity-public-services-data': {**common, 'scope': 'Mapped schools, healthcare, emergency-response and civic/community service sites; proximity is a review exemption cue, not proof of actual service use or access',
                                              'count': len(public_services),'typeCounts':dict(Counter(r['type'] for r in public_services)),
                                              'deduplication':'Same normalized name and facility type within 75 m merged; unnamed facilities remain distinct',
                                              'rows':public_services},
    }
    for stem, data in inventories.items():
        for directory in (OUT, STATIC):
            (directory / (stem + '.json')).write_text(compact(data))
            fields = list(dict.fromkeys(k for r in data['rows'] for k in r if k not in {'geometry', 'duplicateSourceUrls'})) or ['id', 'name', 'type', 'sourceUrl']
            with (directory / (stem + '.csv')).open('w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                                  for k, v in row.items()} for row in data['rows'])
        features = [{'type': 'Feature', 'id': r['id'], 'geometry': r.get('geometry') or ({'type': 'Point', 'coordinates': [r['longitude'], r['latitude']]} if r.get('longitude') is not None else None),
                     'properties': {k: v for k, v in r.items() if k not in {'geometry', 'latitude', 'longitude'}}} for r in data['rows']]
        (OUT / (stem + '.geojson')).write_text(compact({'type': 'FeatureCollection', 'features': features, 'license': data['license']}))
    notes = ['# Connectivity place source inventory', '',
             'Current OSM snapshots; source links and SHA-256 hashes are retained in each JSON inventory. Clear profanity and slurs in mapped venue names are replaced with a neutral label in public outputs. No new road dataset is acquired by this builder.', '',
             '## Visitor venues', '', f'{len(venues):,} normalized mapped venue records; same-name records within 50 m merged.', '']
    notes += [f'- {kind}: {count:,}' for kind, count in sorted(Counter(r['type'] for r in venues).items())]
    notes += ['', f'Official municipal tourism listings: {len(official_rows):,}; unique map-name matches: {sum(bool(r["matchedOsmIds"]) for r in official_rows):,}. Unmatched directory listings have no inferred coordinates. Directory/boundary municipality conflicts remain explicit.', '']
    notes += ['', '## Public-service sites', '', f'{len(public_services):,} mapped schools, health/medical, emergency-response, and civic/community-service features. The source snapshot and feature tags are retained in `connectivity-public-services-data.json`; proximity is used only as an exemption cue.', '']
    notes += [f'- {kind}: {count:,}' for kind, count in sorted(Counter(r['type'] for r in public_services).items())]
    notes += ['', '## Private-property review candidates', '', f'{len(properties):,} mapped source features. These are not yet joined to remote roads and are not confirmed beneficiary properties.', '']
    notes += [f'- {kind}: {count:,}' for kind, count in sorted(Counter(r['type'] for r in properties).items())]
    notes += ['', 'Large residential footprints use a provisional threshold of 1,000 m². Land-use estate/village cues may represent an entire development; private ownership and property value are unverified. Owner names and private-property labels are omitted.', '',
              'A 100 m road-alignment buffer identifies proximity leads. A subdivision connection requires evidence of a road entrance or intersection. City and national roads remain excluded from the remote-road screen.', '',
              '## Files', '', '- `connectivity-venues-data.json/.csv/.geojson`', '- `connectivity-property-indicators-data.json/.csv/.geojson`', '- `connectivity-public-services-data.json/.csv/.geojson`',
             '- `connectivity-venue-review-data.json/.csv/.geojson`: unverified name cues; excluded from the business inventory.',
             '- `connectivity-remote-fmr-venues.json/.csv`: generated separately by `build_connectivity_venue_links.py`; coordinate-backed FMR route/venue proximity pairs.',
             f'- Potentially offensive venue names withheld: {common["offensiveNamesWithheld"]:,}.', '',
              'JSON/CSV copies are served separately from HTML under ODV `static/nep-preview/`; GeoJSON is saved in NEP `analysis_output/` for GIS use.', '',
              '© OpenStreetMap contributors, ODbL 1.0: https://www.openstreetmap.org/copyright', '']
    (OUT / 'connectivity-place-sources.md').write_text('\n'.join(notes))
    print(compact({stem: {'count': data['count'], 'types': data.get('typeCounts', {})} for stem, data in inventories.items()}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    if args.download:
        refresh()
    build()
