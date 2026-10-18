#!/usr/bin/env python3
"""Locate exact inventory assets, then apply existing current LEG screening rules.

Requires Shapely. Uses municipality polygons, never their old LEG labels.
"""
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from shapely.geometry import Point, LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from location_data.build_boundary_crosswalk import cached, polygons
from location_data.enrich_report_tables import PHLocations, STATIC, TITLE_KEYS
from location_data.location_text import text_key,place_key,geographic_title
from lane_cost_enrichment import Inventory, BRIDGE, SECTION, key
from build_cost_per_km import lengths

MAPS=['districts.json','districts_generated.json','20th_congress_representatives.json']

def cut_path(path,low,high):
    # Third ordinate is section measure only when hasM=true, hasZ=false.
    if len(path)<2 or any(len(p)!=3 or p[2] is None for p in path):return []
    if any(b[2]<=a[2] for a,b in zip(path,path[1:])):return []
    pieces=[]
    for a,b in zip(path,path[1:]):
        left,right=max(low,a[2]),min(high,b[2])
        if right<=left:continue
        def xy(value):
            fraction=(value-a[2])/(b[2]-a[2])
            return [a[0]+fraction*(b[0]-a[0]),a[1]+fraction*(b[1]-a[1])]
        pieces.append(LineString([xy(left),xy(right)]))
    return pieces

def main():
    loc=PHLocations()
    # Generate against text-only rules, never corroborate an older supplement
    # with itself during a subsequent rebuild.
    loc.geography.inventory_context={}
    inventory=Inventory()
    towns,town_source=cached('city_municipal_boundaries')
    town_polygons=polygons(towns);tree=STRtree([g for a,g,r in town_polygons])
    bridge_features,bridge_source=cached('bridge_inventory')
    bridges=defaultdict(list)
    for r in bridge_features:bridges[str(r['attributes'].get('BRIDGE_ID','')).upper()].append(r)
    native_sources=[ROOT/'hb10858_3rd_dpwh_projects.json',ROOT/'2027.json']
    projects={};origins=defaultdict(list)
    for source in native_sources:
        for row in json.loads(source.read_text())['data']['data']:
            title=text_key(row['projectName']);projects.setdefault(title,row)
            origins[title].append({'file':source.name,'id':row['id'],'amountPesos':row.get('amountPesos')})
    # Existing report rows may have different historical wording. They can use
    # the same physical-asset resolver; inventory is geographic context only,
    # never proof of historical district membership or historical officeholders.
    def gather(value,source):
        if isinstance(value,list):
            for child in value:gather(child,source)
        elif isinstance(value,dict):
            for field in TITLE_KEYS:
                title=value.get(field)
                if not isinstance(title,str) or not BRIDGE.search(title.upper()):continue
                canonical=text_key(title)
                projects.setdefault(canonical,{'projectName':title})
                origins[canonical].append({'file':source,'id':value.get('id'),'note':'Existing report title; current geographic context only'})
            for child in value.values():
                if isinstance(child,(dict,list)):gather(child,source)
    for source in sorted(STATIC.glob('*.json')):
        gather(json.loads(source.read_text()),source.name)
    review=[];accepted={};road_candidates={};stats=Counter();details={}
    def qualify(row,geometry,bridge=None,evidence=None):
        if geometry.is_empty:return None,'Empty asset geometry'
        hits=[int(i) for i in tree.query(geometry,predicate='intersects')]
        details[text_key(row['projectName'])]={'municipalCandidates':[{'objectId':town_polygons[i][0]['OBJECTID'],
            'municipality':town_polygons[i][0].get('MUNICIPAL'),'province':town_polygons[i][0].get('PROVINCE')} for i in hits],
            'inventoryEvidence':evidence,'bridgeInventory':{k:bridge.get(k) for k in ['BRIDGE_ID','BR_NAME','MUNICIPAL','PROVINCE','BRGY','BR_LENGTH']} if bridge else None}
        if len(hits)!=1:return None,'Asset crosses or touches multiple municipal polygons, or none'
        a,g,repaired=town_polygons[hits[0]]
        if repaired:return None,'Municipal geometry required repair; manual review'
        # A bridge inventory point may be an endpoint. Full span plus 25 meters
        # of clearance conservatively avoids assigning cross-border bridges.
        margin=25
        if bridge:
            span=bridge.get('BR_LENGTH')
            if not isinstance(span,(int,float)) or span<=0:return None,'Bridge extent unavailable'
            margin+=span
            if place_key(a.get('MUNICIPAL'))!=place_key(bridge.get('MUNICIPAL')) or text_key(a.get('PROVINCE'))!=text_key(bridge.get('PROVINCE')):
                return None,'Bridge inventory location disagrees with containing municipality'
        if not g.buffer(-margin).covers(geometry):return None,'Asset extent is too near a municipality boundary'
        town,province=a.get('MUNICIPAL'),a.get('PROVINCE')
        if not town or not province:return None,'Qualified municipal identity absent'
        title,_=geographic_title(row['projectName']);fields=[x.strip(' .') for x in title.split(',')]
        if len(fields)>1 and text_key(fields[-1]) in loc.geography.province_names:
            if text_key(fields[-1])!=text_key(province):return None,'Explicit province conflicts with asset location'
            named=loc.geography.location_list(fields[-2])
            if named and (len(named)!=1 or named[0]!=place_key(town)):
                return None,'Explicit municipality/route scope conflicts with asset location'
        brgy=bridge.get('BRGY') if bridge else None
        if brgy and re.search(r'\b(?:barangay|brgy)\b',row['projectName'],re.I):
            if not re.search(r'\b(?:barangay|brgy\.?)\s+'+re.escape(text_key(brgy))+r'(?=$|[,;()/])',text_key(row['projectName'])):
                return None,'Marked barangay scope not corroborated by bridge inventory'
        context='Inventory location'+(', Barangay '+brgy if brgy else '')+', '+town+', '+province
        decision=loc.geography.resolve({'projectName':context})
        names=loc.project(context)
        if len(decision['indices'])!=1 or not names:
            return None,'Current LEG consensus or unique PH location DB identity is missing'
        seat=loc.seats[decision['indices'][0]]
        return {'originalTitle':row['projectName'],'contextTitle':context,
            'seatKeys':[[text_key(seat['province']),seat['districtLabel']]],
            'municipalObjectId':a['OBJECTID'],'province':province,'municipality':town,
            'barangay':brgy,'clearanceMetersRequired':margin,'inventoryEvidence':evidence,
            'basis':'Exact asset identity and geometry wholly inside one qualified municipality; current local-map consensus, not old LEG polygon labels'},None
    for title,row in projects.items():
        ids=sorted(set(BRIDGE.findall(row['projectName'].upper())))
        if ids:
            stats['titlesWithBridgeIds']+=1
            reason=None;result=None
            if len(ids)!=1 or len(bridges.get(ids[0],[]))!=1:reason='Multiple or nonunique bridge IDs'
            else:
                feature=bridges[ids[0]][0];a=feature['attributes'];geom=feature.get('geometry',{})
                if row.get('region') and key(row['region'])!=key(a.get('REGION')):reason='Source region conflicts with inventory'
                elif not {'x','y'}<=geom.keys():reason='Bridge point unavailable'
                else:result,reason=qualify(row,Point(geom['x'],geom['y']),a,{'bridgeId':ids[0],'objectId':a['OBJECTID'],'layer':bridge_source['path']})
            if result:accepted[title]=result;stats['supportedBridgeTitles']+=1
            else:review.append({'projectName':row['projectName'],'kind':'bridge','reason':reason});stats['bridge:'+reason]+=1
            continue
        km,status,method,ranges=lengths(row['projectName'])
        if not km or not re.search(r'\broad\b|\brd\b|\bhighway\b|\bh-way\b',row['projectName'],re.I):continue
        proxy={**row,'rangesMeters':ranges,'lengthMeters':km*1000}
        evidence,reason,_=inventory.road_match(proxy)
        if evidence:
            road_candidates[title]=(row,evidence)
    print('Geometry candidates:',len(road_candidates),'roads;',stats['supportedBridgeTitles'],'supported bridge titles',flush=True)
    needed=defaultdict(list)
    for title,(row,evidence) in road_candidates.items():needed[evidence['sectionId']].append(title)
    road_geometries=defaultdict(list);invalid=set()
    road_folder=next((ROOT/'data_sources/arcgis_dpwh/archive/selected/number_of_lanes').glob('layers/*/features.jsonl'))
    road_meta=json.loads((road_folder.parent/'metadata.json').read_text())
    sr=road_meta['extent']['spatialReference']
    if sr.get('latestWkid',sr['wkid'])!=32651:raise ValueError('Road/municipal CRS mismatch; no implicit reprojection')
    with road_folder.open() as stream:
        for line in stream:
            feature=json.loads(line);section=feature['attributes'].get('SECTION_ID')
            if section not in needed:continue
            geom=feature.get('geometry',{})
            if not geom.get('hasM') or geom.get('hasZ'):invalid.add(section);continue
            road_geometries[section]+=geom.get('paths',[])
    for title,(row,evidence) in road_candidates.items():
        section=evidence['sectionId']
        if section in invalid:
            review.append({'projectName':row['projectName'],'kind':'road','reason':'Unsupported geometry measure layout'});continue
        pieces=[];covered=[]
        for low,high in evidence['mappedInventoryRangesMeters']:
            intervals=[]
            for path in road_geometries[section]:
                clipped=cut_path(path,low,high)
                if clipped:
                    pieces+=clipped;intervals.append((max(low,path[0][2]),min(high,path[-1][2])))
            merged=[]
            for a,b in sorted(intervals):
                if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
                else:merged.append([a,b])
            covered.append(len(merged)==1 and abs(merged[0][0]-low)<.001 and abs(merged[0][1]-high)<.001)
        if not pieces or not all(covered):
            review.append({'projectName':row['projectName'],'kind':'road','reason':'No usable measured alignment'});continue
        geometry=unary_union(pieces)
        result,reason=qualify(row,geometry,evidence=evidence)
        if result:accepted[title]=result;stats['supportedRoadTitles']+=1
        else:review.append({'projectName':row['projectName'],'kind':'road','reason':reason});stats['road:'+reason]+=1
    baseline=json.loads((ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json').read_text())
    existing={r['id']:r for r in baseline['projects']}
    added=[]  # Count native occurrences, not unique titles.
    for row in json.loads(native_sources[0].read_text())['data']['data']:
        if text_key(row['projectName']) in accepted and not existing[row['id']]['districts']:
            added.append({'id':row['id'],'projectName':row['projectName'],'amountPesos':row['amountPesos'],'evidence':accepted[text_key(row['projectName'])]})
    map_hashes={name:hashlib.sha256((STATIC.parent/'data'/name).read_bytes()).hexdigest() for name in MAPS}
    for item in review:item['details']=details.get(text_key(item['projectName']))
    hierarchy=ROOT.parent/'open-data-visualization/city_barangays_mapping.json'
    out={'schemaVersion':1,'mapHashes':map_hashes,'hierarchySha256':hashlib.sha256(hierarchy.read_bytes()).hexdigest(),'methodology':['Municipal polygons locate assets only. Their CONG_DIST and DEO labels are never used to assign a LEG.',
        'Exact bridge ID with unique inventory point and full-span-plus-25m municipal clearance, or full measured road alignment with 25m clearance.',
        'Single municipality, explicit qualified location agreement, current local crosswalk consensus and unique PH location DB identity required.',
        'Old inventory positions and municipal boundaries require review if the asset moved or administrative coverage changed. No multi-place split is invented.'],
        'summary':{**dict(stats),'supportedTitles':len(accepted),'additionalHGABOccurrences':len(added),'additionalHGABPesos':sum(r['amountPesos'] for r in added)},
        'sources':inventory.sources+[town_source,bridge_source], 'contexts':accepted,'review':review,'additionalHGAB':added,'origins':dict(origins)}
    path=ROOT/'analysis_output/inventory_location_evidence.json';path.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    public={k:out[k] for k in ['schemaVersion','mapHashes','hierarchySha256','methodology','summary','sources','contexts']}
    (STATIC.parent/'data/inventory_location_contexts.json').write_text(json.dumps(public,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out['summary'],indent=2))

if __name__=='__main__':main()
