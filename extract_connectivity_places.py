#!/usr/bin/env python3
"""Extract visitor venues, public services and property cues from a country PBF.

Requires osmium. Three passes retain only the node locations needed by selected
features, avoiding an in-memory index of every node in the Philippines extract.
"""
import argparse
import hashlib
import json
from pathlib import Path

import osmium
from build_connectivity_places import RAW, venue_type


def venue(tags):
    return venue_type(tags) is not None


def property_cue(tags):
    return ((tags.get('landuse') == 'residential' and tags.get('access') in {'private', 'residents', 'permit'})
            or tags.get('residential') in {'gated', 'gated_community', 'private', 'apartments', 'apartment_complex'}
            or (tags.get('leisure') in {'garden', 'swimming_pool', 'sports_centre', 'pitch'}
                and tags.get('access') in {'private', 'members'}))


def public_service(tags):
    amenity=tags.get('amenity',''); healthcare=tags.get('healthcare',''); education=tags.get('education','')
    return (amenity in {'school','kindergarten','college','university','hospital','clinic','doctors','dentist','health_centre','health_post','fire_station','police','ambulance_station','community_centre','social_facility','townhall','public_building','library'}
            or healthcare in {'hospital','clinic','doctor','dentist','health_centre','centre','health_post','dispensary','rehabilitation','midwife'}
            or education in {'school','kindergarten','college','university'})


def extract(path):
    selections = {'osm-expanded-venues': {}, 'osm-private-access-properties': {}, 'osm-public-services': {}}
    ways, relations, required_nodes, relation_ways = {}, {}, set(), set()

    class Select(osmium.SimpleHandler):
        def add(self, element, kind):
            tags = dict(element.tags)
            targets = [stem for stem, keep in [('osm-expanded-venues', venue),
                        ('osm-private-access-properties', property_cue),
                        ('osm-public-services', public_service)] if keep(tags)]
            if not targets: return
            row = {'type': kind, 'id': element.id, 'tags': tags}
            if kind == 'node':
                if not element.location.valid(): return
                row.update(lon=element.location.lon, lat=element.location.lat)
            elif kind == 'way':
                refs = [node.ref for node in element.nodes]; ways[element.id] = refs; required_nodes.update(refs)
            else:
                members = [{'type': 'way', 'ref': member.ref, 'role': member.role}
                           for member in element.members if member.type == 'w']
                row['members'] = members; relations[element.id] = row
                relation_ways.update(member['ref'] for member in members)
            for stem in targets: selections[stem][kind, element.id] = row

        def node(self, node): self.add(node, 'node')
        def way(self, way): self.add(way, 'way')
        def relation(self, relation): self.add(relation, 'relation')

    Select().apply_file(str(path), filters=[osmium.filter.KeyFilter('tourism', 'leisure', 'amenity', 'landuse', 'residential', 'healthcare', 'education')])
    print('Selected features', {key: len(value) for key, value in selections.items()}, flush=True)

    class MemberWays(osmium.SimpleHandler):
        def way(self, way):
            if way.id in relation_ways and way.id not in ways:
                refs = [node.ref for node in way.nodes]; ways[way.id] = refs; required_nodes.update(refs)

    if relation_ways: MemberWays().apply_file(str(path), filters=[osmium.filter.IdFilter(relation_ways)])
    coords = {}

    class Locations(osmium.SimpleHandler):
        def node(self, node):
            if node.id in required_nodes and node.location.valid(): coords[node.id] = {'lon': node.location.lon, 'lat': node.location.lat}

    Locations().apply_file(str(path), filters=[osmium.filter.IdFilter(required_nodes)])
    geometries = {key: [coords[ref] for ref in refs] for key, refs in ways.items() if all(ref in coords for ref in refs)}
    with osmium.io.Reader(str(path)) as reader:
        timestamp = reader.header().get('osmosis_replication_timestamp')
    with path.open('rb') as handle:
        source_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
    for stem, selected in selections.items():
        output = []
        for (kind, feature_id), row in selected.items():
            if kind == 'way':
                geometry = geometries.get(feature_id)
                if not geometry: continue
                row['geometry'] = geometry
            elif kind == 'relation':
                if any(member['ref'] not in geometries for member in row['members']): continue
                for member in row['members']: member['geometry'] = geometries[member['ref']]
                geometry = [point for member in row['members'] for point in member['geometry']]
                if not geometry: continue
            else: geometry = []
            if geometry:
                row['bounds'] = {'minlon': min(p['lon'] for p in geometry), 'maxlon': max(p['lon'] for p in geometry),
                                 'minlat': min(p['lat'] for p in geometry), 'maxlat': max(p['lat'] for p in geometry)}
            output.append(row)
        payload = {'generator': 'BetterGov tag-filtered Geofabrik country extract',
                   'osm3s': {'timestamp_osm_base': timestamp}, 'bettergovSourceFile': path.name,
                   'bettergovSourceSha256': source_hash,
                   'bettergovEndpoint': 'https://download.geofabrik.de/asia/' + path.name,
                   'elements': sorted(output, key=lambda row: (row['type'], row['id']))}
        (RAW/(stem+'-raw.json')).write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':'))+'\n')
        print(stem, len(output), 'records with recovered geometry', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pbf', type=Path)
    extract(parser.parse_args().pbf)
