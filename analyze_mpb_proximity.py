#!/usr/bin/env python3
"""Printed-coordinate proximity evidence; never infer buildings or local need."""
import csv
import hashlib
import json
import math
import re
from collections import Counter,defaultdict
from itertools import combinations
from pathlib import Path
from location_data.project_location_scope import qualified
from location_data.location_text import geographic_title,barangay_key,place_key

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
CATEGORY='BIP - Multi-Purpose Buildings/ Facilities to support Social Services'
ARCGIS_BOUNDARIES=ROOT/'data_sources/arcgis_dpwh/archive/selected/city_municipal_boundaries/layers/City_Municipal_Boundaries_FeatureServer_0-0340fd6a/features.jsonl'
NUMBER=r'([+-]?\d{1,3}\.\d+)'
PAIR=re.compile(r'(?<![\d.])'+NUMBER+r'\s*°?\s*[,;/]\s*'+NUMBER+r'(?![\d.])')

def coordinates(title):
    candidates=[]
    for m in PAIR.finditer(title):
        a,b=float(m[1]),float(m[2]);orientation='latitude, longitude'
        if 4<=a<=22 and 116<=b<=127:lat,lon=a,b
        elif 116<=a<=127 and 4<=b<=22:lat,lon=b,a;orientation='longitude, latitude'
        else:continue
        candidates.append({'latitude':lat,'longitude':lon,'raw':m[0],'orientation':orientation,
                           'decimalPlaces':min(len(m[1].split('.')[1]),len(m[2].split('.')[1]))})
    # Labeled latitude/longitude may be separated by words rather than a comma.
    lat=re.search(r'\blat(?:itude)?\s*[:=]?\s*'+NUMBER+r'\s*°?\s*([NS])?\b',title,re.I)
    lon=re.search(r'\b(?:long|lon|longitude)\s*[:=]?\s*'+NUMBER+r'\s*°?\s*([EW])?\b',title,re.I)
    if lat and lon:
        a=float(lat[1])*(-1 if (lat[2] or '').upper()=='S' else 1)
        b=float(lon[1])*(-1 if (lon[2] or '').upper()=='W' else 1)
        if 4<=a<=22 and 116<=b<=127:candidates.append({'latitude':a,'longitude':b,'raw':lat[0]+'; '+lon[0],'orientation':'explicit latitude/longitude labels','decimalPlaces':min(len(lat[1].split('.')[1]),len(lon[1].split('.')[1]))})
    unique={(r['latitude'],r['longitude']):r for r in candidates}
    if len(unique)!=1:return {'status':'Multiple printed coordinate pairs · verify site' if unique else 'No unambiguous decimal coordinate pair recovered'}
    r=next(iter(unique.values()));r['status']='Usable printed point' if r['decimalPlaces']>=4 else 'Coarse printed coordinates · distance withheld'
    return r

def place(title):
    # Manila's administrative district of Malate is a distinct polygon in the
    # DPWH boundary layer and is wholly assigned to Manila's fifth district.
    if re.search(r'\bMalate\s*,\s*Manila\b',title,re.I):
        return {'key':('city','Malate',None),'label':'Malate · Manila',
                'status':'City district explicitly named; Malate boundary used'}
    # Marikina is a highly urbanized city with its own boundary. Resolve an
    # explicit city mention independently of the barangay/municipality join.
    if re.search(r'\bMarikina\b',title,re.I):
        return {'key':('city','Marikina City'),'label':'Marikina City','status':'City explicitly named; city boundary used'}
    q=qualified(title)
    if q and all(len(q[k])==1 for k in ['province','municipality','barangay']):
        key=tuple(next(iter(q[k])) for k in ['province','municipality','barangay'])
        return {'key':key,'label':' · '.join(reversed(key)),'status':'Qualified barangay, municipality and province agree'}
    if q and len(q.get('province',()))==1 and len(q.get('municipality',()))==1:
        province=next(iter(q['province']));municipality=next(iter(q['municipality']))
        return {'key':(province,municipality,None),'label':municipality+' · '+province,
                'status':'Qualified municipality and province; barangay not established'}
    # Retain explicitly matching city wording as provisional, never a verified
    # same-barangay assignment or a province-wide name join.
    text,_=geographic_title(title);fields=[s.strip(' .') for s in text.split(',')]
    match=re.search(r'\b(?:barangay|brgy\.?|bgy\.?)\s+([^,;()]+)',text)
    if match and len(re.findall(r'\b(?:barangay|brgy\.?|bgy\.?)\s+',text))==1 and fields and re.search(r'\bcity\b',fields[-1]) and not re.search(r'\b(?:and|to)\b|[/&]',match[1]):
        return {'key':('unverified city wording',fields[-1],barangay_key(match[1])),'label':match[1]+' · '+fields[-1],'status':'Same explicit barangay/city wording only · administrative identity unverified'}
    return {'key':None,'label':'Unresolved barangay identity','status':'Barangay identity unresolved'}

def distance(a,b):
    x,y=map(math.radians,[a['latitude'],b['latitude']]);dx=y-x;dy=math.radians(b['longitude']-a['longitude'])
    h=math.sin(dx/2)**2+math.cos(x)*math.cos(y)*math.sin(dy/2)**2
    return 6371008.8*2*math.asin(min(1,math.sqrt(h)))

def utm51_to_wgs84(easting,northing):
    """Convert the archived ArcGIS EPSG:32651 boundary vertices to lon/lat."""
    a=6378137.0;f=1/298.257223563;e2=f*(2-f);ep2=e2/(1-e2);k0=.9996
    x=(easting-500000.0)/k0;y=northing/k0
    m=y
    mu=m/(a*(1-e2/4-3*e2**2/64-5*e2**3/256))
    e1=(1-math.sqrt(1-e2))/(1+math.sqrt(1-e2))
    j1=3*e1/2-27*e1**3/32;j2=21*e1**2/16-55*e1**4/32
    j3=151*e1**3/96;j4=1097*e1**4/512
    fp=mu+j1*math.sin(2*mu)+j2*math.sin(4*mu)+j3*math.sin(6*mu)+j4*math.sin(8*mu)
    sf=math.sin(fp);cf=math.cos(fp);tf=math.tan(fp)
    n1=a/math.sqrt(1-e2*sf*sf);r1=a*(1-e2)/(1-e2*sf*sf)**1.5
    c1=ep2*cf*cf;t1=tf*tf;d=x/n1
    lat=fp-(n1*tf/r1)*(d*d/2-(5+3*t1+10*c1-4*c1*c1-9*ep2)*d**4/24+(61+90*t1+298*c1+45*t1*t1-252*ep2-3*c1*c1)*d**6/720)
    lon=math.radians(123)+(d-(1+2*t1+c1)*d**3/6+(5-2*c1+28*t1-3*c1*c1+8*ep2+24*t1*t1)*d**5/120)/cf
    return [round(math.degrees(lon),7),round(math.degrees(lat),7)]

def build_municipality_boundaries(current):
    requested={}
    for row in current:
        if row.get('adminLevel')=='city' and row.get('city'):
            requested[('city',place_key(row['city']))]=row.get('localityGroup',row['city'])
            continue
        # A title can explicitly name a city without a province-qualified
        # barangay match. Use that city's outline for visualization while
        # retaining the existing unverified place-evidence status.
        municipality=row.get('municipality')
        if municipality and not row.get('province') and re.search(r'\bcity\b',municipality,re.I):
            city_name_key=place_key(municipality)
            named_in_title=any(city_name_key and city_name_key in place_key(str(row.get(field,'')))
                               for field in ('projectName','otherProject'))
            if named_in_title:
                requested[('city',place_key(municipality))]=row.get('municipalityGroup',municipality)
                continue
        if row.get('municipality') and row.get('province'):
            key=('municipality',place_key(row['municipality']),place_key(row['province']))
            requested[key]=row['municipalityGroup']
    # Match common current labels to the official names in the 2022 layer.
    province_alias={'compostela valley':'davao de oro','samar':'samar (western samar)'}
    # Mabini is common; only Davao de Oro uses the parenthetical ArcGIS label.
    municipality_alias={('mabini','davao de oro'):'mabini (dona alicia)'}
    wanted={}
    for key,group in requested.items():
        if key[0]=='city':
            wanted[('city',key[1])]=group
        else:
            _,m,p=key
            wanted[('municipality',municipality_alias.get((m,p),m),province_alias.get(p,p))]=group
    found={}
    if ARCGIS_BOUNDARIES.exists():
        for line in ARCGIS_BOUNDARIES.open(encoding='utf-8'):
            feature=json.loads(line);attrs=feature.get('attributes',{})
            # The source layer splits some cities by legislative district.
            # Combine those features into one city boundary for the map.
            center_type=str(attrs.get('CENTERS','')).strip().lower()
            source_city_name=str(attrs.get('MUNICIPAL') or attrs.get('MUN_DBM') or '')
            is_city=(center_type=='city' or
                     (center_type=='capital' and re.search(r'\bcity\b',source_city_name,re.I)))
            city_key=('city',place_key(source_city_name)) if is_city else None
            municipal_key=('municipality',place_key(attrs.get('MUN_DBM')),place_key(attrs.get('PROV_DBM')))
            key=city_key if city_key in wanted else municipal_key
            group=wanted.get(key)
            if not group:continue
            rings=[]
            for ring in feature.get('geometry',{}).get('rings',[]):
                coords=[utm51_to_wgs84(*point[:2]) for point in ring]
                if len(coords)>=4:rings.append(coords)
            if group not in found:
                is_city=key[0]=='city'
                found[group]={'localityGroup':group,'municipalityGroup':group,'adminLevel':'city' if is_city else 'municipality',
                    'city':attrs.get('MUNICIPAL') if is_city else None,
                    'municipality':None if is_city else attrs.get('MUN_DBM'),
                    'province':attrs.get('PROV_DBM'),'congressionalDistrict':attrs.get('CONG_DIST'),'rings':[]}
            found[group]['rings'].extend(rings)
    return {'source':{'title':'DPWH ArcGIS City-Municipal Boundaries','url':'https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/City_Municipal_Boundaries/FeatureServer/0',
        'sourceNote':'Original source from NAMRIA, rectified digitally by DPWH GIS staff; layer metadata cites March 2022 and references OpenStreetMap and the Philippine Statistics Authority.',
        'input':str(ARCGIS_BOUNDARIES.relative_to(ROOT)),'sha256':hashlib.sha256(ARCGIS_BOUNDARIES.read_bytes()).hexdigest() if ARCGIS_BOUNDARIES.exists() else None,
        'spatialReference':'EPSG:32651; converted to WGS84 for mapping'},
        'features':list(found.values()),'unmatchedMunicipalityGroups':sorted(set(requested.values())-set(found))}

def point_in_rings(point,rings):
    """Even-odd polygon inclusion for ArcGIS rings in WGS84."""
    x,y=point['longitude'],point['latitude'];inside=False
    for ring in rings:
        hit=False
        for i in range(len(ring)):
            x1,y1=ring[i-1];x2,y2=ring[i]
            if (y1>y)!=(y2>y) and x<(x2-x1)*(y-y1)/(y2-y1)+x1:hit=not hit
        if hit:inside=not inside
    return inside

def distance_to_rings_km(point,rings):
    """Approximate nearest boundary distance in a local tangent plane."""
    lat=math.radians(point['latitude']);best=float('inf')
    for ring in rings:
        projected=[((x-point['longitude'])*111320*math.cos(lat),(y-point['latitude'])*111320) for x,y in ring]
        for (x1,y1),(x2,y2) in zip(projected,projected[1:]):
            dx=x2-x1;dy=y2-y1;t=max(0,min(1,-(x1*dx+y1*dy)/(dx*dx+dy*dy or 1)))
            best=min(best,math.hypot(x1+t*dx,y1+t*dy))
    return best/1000

def coordinate_audit(rows,boundaries):
    by_group={f['municipalityGroup']:f for f in boundaries['features']};province_alias={'compostela valley':'davao de oro','samar':'samar (western samar)'};municipality_alias={('mabini','davao de oro'):'mabini (dona alicia)'}
    audit=[];unresolved=Counter();unresolved_projects=[];matched=0;district_matches=[]
    for r in rows:
        point=coordinates(r['projectName'])
        if point['status']!='Usable printed point':continue
        p=place(r['projectName'])
        city_district = p.get('status','').startswith('City district explicitly named')
        if not p['key'] or not (p['status'].startswith('Qualified') or city_district):
            unresolved[p['status']]+=1
            unresolved_projects.append({'projectId':r['hgab_id'],'projectName':r['projectName'],'reason':p['status']})
            continue
        if city_district:
            _,city_name,_=p['key'];province='Metropolitan Manila';municipality='Manila';barangay=city_name
            group=p['label'];feature=by_group.get(group)
        else:
            province,municipality,barangay=p['key'];group=municipality+' · '+province
            province_key=province_alias.get(place_key(province),place_key(province))
            key=(municipality_alias.get((place_key(municipality),province_key),place_key(municipality)),province_key)
            feature=by_group.get(group)
            # Boundary aliases are applied when features are emitted; use their canonical match if labels differ.
            if not feature:
                feature=next((f for f in boundaries['features'] if (place_key(f['municipality']),place_key(f['province']))==key),None)
        if not feature:
            unresolved['No matching municipal boundary']+=1
            unresolved_projects.append({'projectId':r['hgab_id'],'projectName':r['projectName'],'reason':'No matching municipal boundary'})
            continue
        matched+=1
        inside=point_in_rings(point,feature['rings'])
        if inside:
            if city_district and feature.get('congressionalDistrict'):
                district_matches.append({'projectId':r['hgab_id'],'projectName':r['projectName'],
                    'congressionalDistrict':feature['congressionalDistrict'],'place':p['label'],
                    'coordinateRaw':point['raw'],'boundarySource':'DPWH ArcGIS City-Municipal Boundaries'})
            continue
        audit.append({'projectName':r['projectName'],'projectId':r['hgab_id'],'sourcePage':r['sourcePage'],'sourceVolume':r['sourceVolume'],
            'amountPesos':int(r['amountPesos']),'province':province,'municipality':municipality,'barangay':barangay,
            'namedPlace':' · '.join(v for v in (barangay,municipality,province) if v),'coordinateRaw':point['raw'],'latitude':point['latitude'],'longitude':point['longitude'],
            'outsideBoundaryKm':round(distance_to_rings_km(point,feature['rings']),1),'boundaryMunicipality':feature.get('municipality') or feature.get('city'),'boundaryProvince':feature['province'],
            'boundarySource':'DPWH ArcGIS City-Municipal Boundaries · NAMRIA-derived · March 2022 metadata'})
    audit.sort(key=lambda r:(-r['outsideBoundaryKm'],r['projectId']))
    return audit,dict(unresolved),matched,unresolved_projects,district_matches

def evidence(left,right):
    a,b=coordinates(left),coordinates(right);pa,pb=place(left),place(right)
    meters=round(distance(a,b),1) if a['status']==b['status']=='Usable printed point' else None
    same=bool(pa['key'] and pb['key'] and len(pa['key'])==len(pb['key'])==3 and pa['key'][2] and pa['key']==pb['key']);verified=same and pa['status'].startswith('Qualified')
    continuation=bool(re.search(r'\bcompletion|rehabilitation|repair|renovation|improvement|extension|expansion\b',left+' '+right,re.I))
    band='Unknown distance' if meters is None else 'Under 50 meters' if meters<50 else '50–<100 meters' if meters<100 else '100–<250 meters' if meters<250 else '250–<1,000 meters' if meters<1000 else '1,000 meters or farther'
    site='Unresolved site identity' if meters is None else 'Likely same-site reference · building identity requires verification' if meters<50 else 'Nearby printed locations · site identity unresolved' if meters<100 else 'Separated printed locations · verify sites and service areas'
    review='Coordinates unavailable or require review' if meters is None else 'Compare funded scope, phase and quantities at the likely same site' if meters<50 else 'Verify building identities and funded scopes' if meters<100 else 'Compare sites and service areas; need remains unverified'
    if continuation:review+=' · completion/repair/improvement wording present'
    return {'distanceMeters':meters,'distanceBand':band,'leftCoordinates':a,'rightCoordinates':b,
            'sameBarangayVerified':verified,'sameBarangayLabels':same,'barangay':pa['label'] if same else 'Same barangay not established',
            'barangayEvidence':pa['status'] if same else 'Same barangay not established',
            'continuationWording':continuation,'siteInterpretation':site,'proximityReview':review}

def build():
    dpwh=json.loads((STATIC/'dpwh-data.json').read_text())
    historical=[]
    for r in dpwh['priorityRepeats']:
        if r['category']!='Multi-purpose building':continue
        e=evidence(r['project'],r['prior_project']);r.update(e)
        historical.append({**r,'pairType':'NEP vs historical GAA','projectName':r['project'],'otherProject':r['prior_project'],
            'sourceLabel':r['source_code'],'otherSource':r['prior_source'],'currentAllocationPesos':r['amount_2027'],'otherAllocationPesos':r['prior_amount']})
    (STATIC/'dpwh-data.json').write_text(json.dumps(dpwh,ensure_ascii=False,indent=2)+'\n')
    with (OUT/'hb_nep_comparison_3rd.csv').open() as f:rows=[r for r in csv.DictReader(f) if r['pap3']==CATEGORY]
    groups=defaultdict(list)
    for r in rows:
        p=place(r['projectName'])
        if p['key'] and len(p['key'])==3 and p['key'][2]:groups[p['key']].append(r)
    current=[]
    for members in groups.values():
        # Coordinate-ready pairs only; coverage below exposes missing records.
        ready=[r for r in members if coordinates(r['projectName'])['status']=='Usable printed point']
        for a,b in combinations(ready,2):
            pa=place(a['projectName']); place_key=pa['key'] or ('','','')
            municipality=place_key[1] if len(place_key)>1 else ''
            province=place_key[0] if place_key and place_key[0]!='unverified city wording' else ''
            municipality_status='Qualified municipality and province' if province else 'Municipality wording only · administrative identity unverified'
            current.append({'pairType':'HGAB 3rd · same barangay labels','projectName':a['projectName'],'otherProject':b['projectName'],
                'sourceLabel':a['hgab_id']+' · p. '+a['sourcePage'],'otherSource':b['hgab_id']+' · p. '+b['sourcePage'],
                'currentAllocationPesos':int(a['amountPesos']),'otherAllocationPesos':int(b['amountPesos']),
                'municipality':municipality,'province':province,
                'municipalityGroup':municipality+' · '+province if province else municipality+' · identity unverified',
                'municipalityEvidence':municipality_status,
                **evidence(a['projectName'],b['projectName'])})
    summary={'historicalPairs':len(historical),'historicalPairsWithDistance':sum(r['distanceMeters'] is not None for r in historical),
        'historicalUnder100m':sum(r['distanceMeters'] is not None and r['distanceMeters']<100 for r in historical),
        'historicalUnder50mSameSiteCandidates':sum(r['distanceMeters'] is not None and r['distanceMeters']<50 for r in historical),
        'hgabLines':len(rows),'hgabLinesWithUsablePoint':sum(coordinates(r['projectName'])['status']=='Usable printed point' for r in rows),
        'currentSameBarangayCoordinatePairs':len(current),'currentVerifiedSameBarangayPairs':sum(r['sameBarangayVerified'] for r in current),
        'currentUnder50mSameSiteCandidates':sum(r['distanceMeters']<50 for r in current)}
    boundary_inputs=list(current)
    # Municipal polygons also support checking every qualified coordinate-bearing title, not only repeated barangay pairs.
    for r in rows:
        if coordinates(r['projectName'])['status']!='Usable printed point':continue
        p=place(r['projectName'])
        if p['key'] and p['status'].startswith('Qualified'):
            province,municipality,_=p['key'];boundary_inputs.append({'province':province,'municipality':municipality,'municipalityGroup':municipality+' · '+province})
        elif p['key'] and p['status'].startswith('City district explicitly named'):
            _,city_name,_=p['key'];boundary_inputs.append({'adminLevel':'city','city':city_name,'localityGroup':p['label']})
    boundaries=build_municipality_boundaries(boundary_inputs)
    audit,unresolved_audit,audit_matched,unresolved_projects,district_matches=coordinate_audit(rows,boundaries)
    summary.update({'coordinateAuditQualifiedMatched':audit_matched,
        'coordinateAuditOutside':len(audit),'coordinateAuditUnmatched':sum(unresolved_audit.values()),
        'coordinateAuditPlaceUnresolved':unresolved_audit.get('Barangay identity unresolved',0)+unresolved_audit.get('Same explicit barangay/city wording only · administrative identity unverified',0),
        'coordinateAuditBoundaryUnmatched':unresolved_audit.get('No matching municipal boundary',0)})
    boundary_json=json.dumps(boundaries,ensure_ascii=False,indent=2)+'\n'
    (OUT/'mpb_municipality_boundaries.json').write_text(boundary_json)
    (STATIC/'mpb-municipality-boundaries.json').write_text(boundary_json)
    data={'summary':summary,'historical':historical,'current':current,'coordinateAudit':audit,'coordinateAuditUnresolved':unresolved_audit,'coordinateAuditUnresolvedProjects':unresolved_projects,'coordinateAuditDistrictMatches':district_matches,
        'method':'Haversine great-circle separation, radius 6,371,008.8 meters, between one unambiguous decimal point per title. Latitude/longitude order inferred only from nonoverlapping local screening ranges (4–22 latitude, 116–127 longitude), recorded per point. At least four decimal places required. No geocoding, centroid substitution, nearest-coordinate join or coordinate borrowing from other rows/stages.',
        'limits':['Printed points are not verified building footprints. Identical or nearby coordinates can be rounded, copied or reference a barangay center. Decimal precision is not positional accuracy.',
            'Under-50-meter pairs are interpreted as likely same-site references for scope review. They are not counted as two confirmed buildings. Site identity requires maps, asset IDs, designs or field verification; nearby plots can contain different structures.',
            'Municipality containment uses qualified title locations and the archived DPWH ArcGIS municipal boundary layer. Outside points are review candidates: title parsing, printed coordinates or boundaries may be wrong, and no barangay boundary layer was available.',
            'A same-barangay identity requires agreement at barangay, municipality and province levels. Matching city wording without a qualified hierarchy is separately marked unverified.',
            'One MPB per barangay is a needs-screening hypothesis, not a validated entitlement rule. Different functions, population, capacity, accessibility and hazard exposure may justify multiple facilities.',
            'Historical completion/repair allocations can fund the same legitimate building in successive years. A short distance does not establish two separate buildings or duplicate payment.',
            'Farther points can support a separate-site interpretation but do not establish need. The 50/100/250/1000-meter bins are descriptive review bands, not corruption thresholds.',
            'Pairs are not distinct projects; a cluster of three items yields three pairs. Do not sum pair allocations as losses.'],
        'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [OUT/'hb_nep_comparison_3rd.csv',OUT/'priority_program_year_on_year_candidates.csv',ROOT/'location_data/philippine_locations.sqlite']]}
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n';(OUT/'mpb_proximity.json').write_text(serialized);(STATIC/'mpb-proximity.json').write_text(serialized)
    audit_export={'summary':{k:v for k,v in summary.items() if k.startswith('coordinateAudit')},'source':boundaries['source'],'unresolved':unresolved_audit,'candidates':audit}
    audit_serialized=json.dumps(audit_export,ensure_ascii=False,indent=2)+'\n'
    (OUT/'mpb_coordinate_audit.json').write_text(audit_serialized);(STATIC/'mpb-coordinate-audit.json').write_text(audit_serialized)
    return data

def render(data,keys=('historical','current')):
    from build_investigation_summary import table,esc
    s=data['summary'];body=f'<section id="mpb-coordinate-proximity" class="card"><h2>MPB locations · same-site funding and separate-site review</h2><p>{s["historicalPairsWithDistance"]:,} of {s["historicalPairs"]:,} historical comparison pairs have usable coordinates at both ends. {s["hgabLinesWithUsablePoint"]:,} of {s["hgabLines"]:,} HGAB MPB entries have usable printed points. Pairs under 50 meters are reviewed as likely references to the same site. The question is whether allocations cover legitimate continuation, different components, or repeated funding of the same work. Pair counts describe allocations, not a verified inventory of distinct buildings.</p>'
    if 'current' in keys:
        body+='<div class="mpb-local-map"><h3>Where are these buildings?</h3><p>Choose a municipality to see the listed MPB locations against its municipal outline. The view starts with the largest distance between same-barangay matches.</p><div id="mpbMapStory" class="mpb-map-story"></div><label for="mpbMunicipalitySelect">Explore another municipality</label> <select id="mpbMunicipalitySelect" aria-label="Choose municipality for MPB coordinate map"></select><p id="mpbMapSummary" aria-live="polite"></p><div id="mpbMunicipalityPlot"></div><div class="mpb-map-legend"><span><i class="boundary-inside"></i> Listed point inside outline</span><span><i class="boundary-outside"></i> Outside outline · verify</span><span><i class="same-site"></i> Pair under 50 m</span><span><i class="extreme-site"></i> Pair 10 km or farther</span></div><p class="note">Dots are project coordinates printed in the titles; lines show straight-line distances. The outline is the DPWH ArcGIS City-Municipal Boundaries layer, sourced from NAMRIA and rectified by DPWH GIS staff (March 2022 layer metadata; references OpenStreetMap and PSA). A point outside the outline signals a location record to check, not a finding. <strong>Geographic congressional association:</strong> District association follows the project location in the PH location DB and describes geographic coverage; it does not imply sponsorship or control. <a href="https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/City_Municipal_Boundaries/FeatureServer/0" target="_blank" rel="noopener">Boundary layer source ↗</a></p></div>'
        audit=data.get('coordinateAudit',[]);ss=data['summary']
        body+=f'<h3 id="mpb-outside-boundary-queue">Printed coordinates outside the named municipality</h3><p>{ss.get("coordinateAuditOutside",0):,} of {ss.get("coordinateAuditQualifiedMatched",0):,} coordinate-bearing entries with qualified title locations plot outside their named municipality outline. These are leads for checking the source schedule, not evidence of a false location. {ss.get("coordinateAuditUnmatched",0):,} entries could not be matched to a municipal polygon or qualified place.</p>'
        body+='<p>Sorted by approximate distance beyond the municipality boundary. The title, raw printed point, and source row locator are shown for each candidate.</p>'
        body+=table(['Project · HGAB source ID','Title place','Printed coordinate pair','Approx. distance outside outline','Allocation pesos','Source volume · page'],[[r['projectName']+' · '+r['projectId'],r['namedPlace'],r['coordinateRaw'],r['outsideBoundaryKm'],r['amountPesos'],r['sourceVolume']+' · p. '+str(r['sourcePage'])] for r in audit])
        body+='<p><a href="mpb-coordinate-audit.json" download>Download all coordinate/title review candidates as JSON</a>. Distances use local projected approximations from the printed coordinate to the nearest municipal boundary.</p>'
    for key,title in [('historical','NEP vs GAA · repeat-location distance'),('current','HGAB 3rd · same-barangay location pairs')]:
        if key not in keys:continue
        rows=sorted(data[key],key=lambda r:(r['distanceMeters'] is None,r['distanceMeters'] or 0,r['projectName']))
        counts=Counter(r['distanceBand'] for r in rows);bands=['Under 50 meters','50–<100 meters','100–<250 meters','250–<1,000 meters','1,000 meters or farther','Unknown distance'];maximum=max(counts.values(),default=1)
        body+='<h3>'+title+'</h3><figure><figcaption>Allocation comparison pairs by printed-point separation · under 50 meters: likely same-site references, pending identity verification · unknown distances shown separately</figcaption><svg viewBox="0 0 1050 270" role="img" aria-label="MPB allocation pair counts by distance band, not building counts">'
        for i,band in enumerate(bands):
            x=35+i*170;h=160*counts[band]/maximum if maximum else 0
            body+=f'<rect x="{x}" y="{190-h}" width="120" height="{h}" fill="'+('#adb5bd' if band=='Unknown distance' else '#087e78')+f'"/><text x="{x}" y="{180-h}">{counts[band]}</text><text x="{x}" y="220" font-size="12">{esc(band)}</text>'
        body+='</svg></figure>'
        displayed=[r for r in rows if r['distanceMeters'] is not None]
        body+='<p>Table: '+str(len(displayed))+' coordinate-ready pairs, nearest first. Unknown distances remain in the chart, download and historical comparison table.</p>'
        body+=table(['First project · source','Second project · source','Straight-line meters','Site interpretation · distance band','Barangay evidence','Funded-work review'],[[r['projectName']+' · '+r['sourceLabel'],r['otherProject']+' · '+r['otherSource'],r['distanceMeters'],r['siteInterpretation']+' · '+r['distanceBand'],r['barangay']+' · '+r['barangayEvidence'],r['proximityReview']] for r in displayed])
    body+='<h3>Coordinate and needs-screening methodology</h3><p>'+esc(data['method'])+'</p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in data['limits'])+'</ul><p><a href="mpb-proximity.json" download>Download every distance, raw coordinate pair, place-evidence status and source locator</a>. Tables export all displayed rows as CSV.</p></section>'
    return body

if __name__=='__main__':print(json.dumps(build()['summary'],indent=2))
