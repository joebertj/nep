#!/usr/bin/env python3
"""Conservative lane evidence from local ArcGIS inventories; no network access."""
import bisect
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT/'data_sources/arcgis_dpwh/archive/selected'
LANES=re.compile(r'\b(\d+)\s*[- ]?\s*lanes?\b',re.I)
SECTION=re.compile(r'\bS\d{5}[A-Z]{2}\b',re.I)
BRIDGE=re.compile(r'\bB\d{5}[A-Z]{2}\b',re.I)

def key(value):
    # Retain every place/directional word and route/bridge number.
    text=str(value or '').casefold()
    for pattern,replacement in [(r'\brd\b','road'),(r'\bh[ -]?way\b','highway'),(r'\bbr\b','bridge')]:
        text=re.sub(pattern,replacement,text)
    return re.sub(r'\s+',' ',re.sub(r'[^\w]+',' ',text)).strip()

def rows(profile,sources):
    root=ARCHIVE/profile
    if not (root/'status.json').exists():
        raise FileNotFoundError(f'Missing selected inventory {profile}')
    status=json.loads((root/'status.json').read_text())
    for relative,state in status['layers'].items():
        if state['state']!='complete':raise ValueError(f'Incomplete inventory {profile}')
        folder=root/state['path'];path=folder/'features.jsonl'
        metadata=json.loads((folder/'metadata.json').read_text())
        digest=hashlib.sha256();count=0
        with path.open('rb') as stream:
            for line in stream:
                digest.update(line);count+=1
                yield json.loads(line)['attributes']
        if count!=state['expected']:raise ValueError('Inventory count differs from manifest')
        sources.append({'profile':profile,'layer':relative,'file':str(path.relative_to(ROOT)),
            'url':'https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/'+relative,
            'sha256':digest.hexdigest(),'rows':count,'copyright':metadata.get('copyrightText'),
            'note':'Inventory vintage, not proof of FY2027 funded work quantities.'})

class Inventory:
    def __init__(self):
        self.sources=[];self.roads=defaultdict(list);self.names=defaultdict(set)
        self.bridges=defaultdict(list);self.posts=defaultdict(list)
        for row in rows('number_of_lanes',self.sources):
            section=row.get('SECTION_ID')
            self.roads[section].append(row)
            self.names[key(row.get('ROAD_NAME'))].add(section)
        for row in rows('bridge_inventory',self.sources):
            self.bridges[str(row.get('BRIDGE_ID','')).upper()].append(row)
        for row in rows('kilometer_posts',self.sources):
            match=re.fullmatch(r'K\s*(\d+)',str(row.get('KM_POST','')),re.I)
            if match and isinstance(row.get('LOCATION'),(int,float)):
                self.posts[row.get('SECTION_ID')].append((int(match[1])*1000,float(row['LOCATION']),row['OBJECTID']))

    def road_identity(self,row):
        title=row['projectName'];sections=sorted(set(SECTION.findall(title.upper())))
        if len(sections)>1:return None,'Multiple printed road section IDs; no unique asset',[]
        basis='Exact printed road section ID'
        if not sections:
            # Full road field preceding a station separator, never a token or
            # fuzzy match. Region/DEO must also agree and section must be unique.
            prefix=re.split(r'\s+-\s*(?=(?:K\d|STA\b|CHAINAGE\b))',title,maxsplit=1,flags=re.I)[0]
            sections=sorted(self.names.get(key(prefix),()))
            basis='Exact full road name plus region/DEO; unique section'
        filtered=[]
        for section in sections:
            candidates=self.roads.get(section,[])
            if not candidates:continue
            if row.get('region') and not any(key(r.get('REGION'))==key(row['region']) for r in candidates):continue
            if row.get('office') and 'district engineering office' in row['office'].casefold() and not any(key(r.get('DEO'))==key(row['office']) for r in candidates):continue
            filtered.append(section)
        if len(filtered)!=1:return None,'No unique section with compatible region/office',[]
        return filtered[0],basis,[]

    def road_match(self,row):
        section,basis,_=self.road_identity(row)
        if not section:return None,basis,[]
        title=row['projectName']
        merged=[]
        for a,b in sorted(row.get('rangesMeters') or []):
            if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
            else:merged.append([a,b])
        ranges=merged
        if not ranges:return None,'No usable funded station ranges to intersect inventory',[]
        anchors=defaultdict(set)
        for station,location,oid in self.posts[section]:anchors[station].add(location)
        if re.search(r'\bK\s*\d',title,re.I):
            if any(len(v)!=1 for v in anchors.values()):return None,'Conflicting kilometer-post locations in section',[]
            points=sorted((a,next(iter(b))) for a,b in anchors.items());xs=[p[0] for p in points]
            if len(points)<2 or any(b[1]<=a[1] for a,b in zip(points,points[1:])):
                return None,'Missing or non-monotonic kilometer-post reference',[]
            def convert(value):
                if value<xs[0] or value>xs[-1]:return None
                i=min(max(bisect.bisect_right(xs,value)-1,0),len(points)-2)
                a,b=points[i:i+2];slope=(b[1]-a[1])/(b[0]-a[0])
                if not .5<=slope<=2 or b[0]-a[0]>2000:return None
                return a[1]+(value-a[0])*slope
            mapped=[(convert(a),convert(b)) for a,b in ranges]
            if any(a is None or b is None or b<=a for a,b in mapped):return None,'Range outside supported kilometer-post brackets',[]
            basis+='; local measure interpolated between kilometer posts (no extrapolation)'
        elif SECTION.search(title) and re.search(r'\bchainage\b',title,re.I):
            mapped=ranges;basis+='; printed numeric chainage assumed section-local for proxy only'
        else:
            return None,'STA reference not proven compatible with inventory section measure',[]
        segments=self.roads[section];weighted=0;total=0;used=set();lanes_used=set()
        for low,high in mapped:
            cuts=sorted({low,high}|{float(r[k]) for r in segments for k in ['START','END_'] if isinstance(r.get(k),(int,float)) and low<r[k]<high})
            for a,b in zip(cuts,cuts[1:]):
                mid=(a+b)/2
                active=[r for r in segments if isinstance(r.get('START'),(int,float)) and isinstance(r.get('END_'),(int,float)) and r['START']<=mid<r['END_']]
                values=set()
                for r in active:
                    match=re.fullmatch(r'(\d+)\s*(?:-?\s*lanes?)?',str(r.get('NUM_LANES','')).strip(),re.I)
                    if not match:return None,'Unknown lane count in intersecting inventory segment',[]
                    values.add(int(match[1]))
                if len(values)!=1 or not next(iter(values),0):return None,'Inventory gap or conflicting lane count within funded range',[]
                n=next(iter(values));weighted+=(b-a)*n;total+=b-a;used.update(r['OBJECTID'] for r in active);lanes_used.add(n)
        if not total:return None,'No positive inventory measure overlap',[]
        return {'sectionId':section,'inventoryLanes':weighted/total,'inventoryLaneValues':sorted(lanes_used),
            'inventoryObjectIds':sorted(used),'mappedInventoryLengthMeters':total,
            'mappedInventoryRangesMeters':mapped,
            'stationEvidence':basis},'Inventory lane exposure available; funded lanes unverified',[]

    def dimensions(self,row):
        """Recover existing asset dimensions independently of funded extent/rates."""
        group=row['category'];title=row['projectName']
        evidence=None
        if group=='Bridges':
            ids=sorted(set(BRIDGE.findall(title.upper())))
            candidates=self.bridges.get(ids[0],[]) if len(ids)==1 else []
            if len(candidates)==1:
                b=candidates[0]
                def positive(value):
                    try:
                        value=float(value)
                        return value if value>0 else None
                    except (ValueError,TypeError):return None
                evidence={'bridgeId':ids[0],'inventoryObjectIds':[b['OBJECTID']],
                    'assetLengthMeters':positive(b.get('BR_LENGTH')),
                    'assetWidthMeters':positive(b.get('BR_WIDTH')),
                    'assetEffectiveLanes':positive(b.get('NUM_LANES')),
                    'basis':'Exact single printed bridge ID; existing bridge span/width/lanes, not funded quantities'}
        elif group=='Roads':
            section,basis,_=self.road_identity(row)
            if section:
                segments=self.roads[section]
                valid=[r for r in segments if isinstance(r.get('START'),(int,float)) and isinstance(r.get('END_'),(int,float)) and r['END_']>r['START']]
                cuts=sorted({float(r[k]) for r in valid for k in ['START','END_']})
                total=weighted=width_weighted=0;all_lanes=all_widths=True;gaps=0;used=set();lane_values=set()
                for a,b in zip(cuts,cuts[1:]):
                    active=[r for r in valid if r['START']<b and r['END_']>a]
                    if not active:gaps+=b-a;continue
                    total+=b-a;used.update(r['OBJECTID'] for r in active)
                    values=set();widths=set()
                    for r in active:
                        match=re.fullmatch(r'(\d+)\s*(?:-?\s*lanes?)?',str(r.get('NUM_LANES','')).strip(),re.I)
                        values.add(int(match[1]) if match else 0)
                        w0,w1=r.get('WIDTH_START'),r.get('WIDTH_END')
                        if all(isinstance(v,(int,float)) and v>0 for v in [w0,w1]):
                            # Linear width interpolation across this inventory segment.
                            widths.add(round((w0+(w1-w0)*(((a+b)/2-r['START'])/(r['END_']-r['START']))),6))
                        else:widths.add(None)
                    if len(values)==1 and next(iter(values))>0:
                        n=next(iter(values));weighted+=(b-a)*n;lane_values.add(n)
                    else:all_lanes=False
                    if len(widths)==1 and None not in widths:width_weighted+=(b-a)*next(iter(widths))
                    else:all_widths=False
                evidence={'sectionId':section,'inventoryObjectIds':sorted(used),
                    'assetLengthMeters':total if total and not gaps else None,
                    'inventoryCoveredMeters':total,'internalGapMeters':gaps,
                    'inventoryMeasureStart':cuts[0] if cuts else None,'inventoryMeasureEnd':cuts[-1] if cuts else None,
                    'assetEffectiveLanes':weighted/total if total and all_lanes and not gaps else None,
                    'assetWidthMeters':width_weighted/total if total and all_widths and not gaps else None,
                    'inventoryLaneValues':sorted(lane_values),
                    'basis':basis+'; union of existing inventory section measures, not project length. Overlaps counted once; conflicting/unknown lanes or widths withheld; gaps prevent aggregate dimensions. Recorded extent may not cover the entire road section.'}
        row['inventoryDimensionsEvidence']=evidence
        row['inventoryAssetLengthMeters']=evidence.get('assetLengthMeters') if evidence else None
        row['inventoryAssetWidthMeters']=evidence.get('assetWidthMeters') if evidence else None
        row['inventoryAssetEffectiveLanes']=round(evidence['assetEffectiveLanes'],6) if evidence and evidence.get('assetEffectiveLanes') else None
        row['inventoryDimensionsStatus']=evidence['basis'] if evidence else 'No unique compatible inventory identity'
        if evidence:row['matchedInventoryId']=evidence.get('bridgeId') or evidence.get('sectionId')

    def enrich(self,row):
        title=row['projectName'];group=row['category'];length=row.get('lengthMeters')
        evidence=None;reason='No compatible inventory match';bridge_ids=sorted(set(BRIDGE.findall(title.upper())))
        title_lanes=sorted(set(int(m[1]) for m in LANES.finditer(title)))
        row.update({'titleStatedLanes':title_lanes[0] if len(title_lanes)==1 else None,
            'titleLaneMeters':None,'allocationPerTitleLaneMeter':None,
            'inventoryEffectiveLanes':None,'inventoryLaneMetersProxy':None,
            'allocationPerInventoryLaneMeterProxy':None,'laneInventoryEvidence':None,
            'inventoryAssetLaneMeters':None,'allocationPerInventoryAssetLaneMeter':None,
            'inventoryAssetLengthMeters':None,
            'laneRateStatus':'No compatible lane evidence'})
        row['matchedInventoryId']=None
        self.dimensions(row)
        blocked=bool(re.search(r'\bwidening\b|\bapproaches\b|\bslips\b|\bslope\b|\boff.carriageway\b|\bdrainage\b',title+' '+row['program'],re.I))
        scope_blocked=blocked
        if group in ['FMR','Mixed roads / bridges']:
            row['laneRateStatus']='Outside compatible national-road/bridge inventory scope';return
        if group=='Bridges' and len(bridge_ids)==1:
            candidates=self.bridges.get(bridge_ids[0],[])
            if len(candidates)==1:
                b=candidates[0]
                match=re.fullmatch(r'\d+',str(b.get('NUM_LANES','')).strip())
                if match and int(match[0])>0:
                    evidence={'bridgeId':bridge_ids[0],'inventoryObjectIds':[b['OBJECTID']],
                        'inventoryLanes':int(match[0]),'inventoryLengthMeters':b.get('BR_LENGTH'),
                        'inventoryWidthMeters':b.get('BR_WIDTH'),'condition':b.get('CONDITION'),
                        'roadName':b.get('ROAD_NAME'),'province':b.get('PROVINCE'),
                        'stationEvidence':'Exact single printed bridge ID; inventory span is context, not funded length'}
                    reason='Bridge inventory lanes available; funded scope unverified'
                    eligible_asset=bool(re.search(r'\brehabilitation\b|\bmajor repair\b|\bretrofitting\b|\bstrengthening\b',row['program'],re.I))
                    if eligible_asset and not blocked and isinstance(b.get('BR_LENGTH'),(int,float)) and b['BR_LENGTH']>0:
                        # Normalize allocation by the existing whole asset,
                        # explicitly separate from funded project quantities.
                        row['inventoryAssetLengthMeters']=b['BR_LENGTH']
                        row['inventoryAssetLaneMeters']=b['BR_LENGTH']*int(match[0])
                        row['allocationPerInventoryAssetLaneMeter']=round(row['amountPesos']/row['inventoryAssetLaneMeters'],2)
                    if not length or not isinstance(b.get('BR_LENGTH'),(int,float)) or b['BR_LENGTH']<=0 or not .9<=length/b['BR_LENGTH']<=1.1:
                        blocked=True;reason='Stated range differs from inventory bridge span by more than 10%, or span missing'
                        if not length:reason='No stated funded length; existing-asset estimate only where eligible'
        elif group=='Roads':
            evidence,reason,_=self.road_match(row)
        row['laneInventoryEvidence']=evidence
        if evidence:row['matchedInventoryId']=evidence.get('bridgeId') or evidence.get('sectionId')
        if evidence:row['inventoryEffectiveLanes']=round(evidence['inventoryLanes'],6)
        if length and len(title_lanes)==1 and title_lanes[0]>0 and not blocked:
            row['titleLaneMeters']=length*title_lanes[0]
            row['allocationPerTitleLaneMeter']=round(row['amountPesos']/row['titleLaneMeters'],2)
        if length and evidence and not blocked:
            row['inventoryLaneMetersProxy']=length*evidence['inventoryLanes']
            row['allocationPerInventoryLaneMeterProxy']=round(row['amountPesos']/row['inventoryLaneMetersProxy'],2)
        row['laneRateStatus']=('Title-stated lane count; funded quantities still require verification' if row['allocationPerTitleLaneMeter'] is not None else
            'Inventory-normalized proxy only; funded lanes unverified' if row['allocationPerInventoryLaneMeterProxy'] is not None else
            'Lane rate withheld: widening, approaches or non-carriageway scope' if scope_blocked else reason)

def enrich(data):
    inventory=Inventory()
    from road_asset_context import Context,summary as context_summary
    context=Context(inventory)
    for row in data['projects']:
        inventory.enrich(row)
        context.enrich(row)
    summaries=[]
    for category in ['Roads','Bridges','FMR','Mixed roads / bridges']:
        selected=[r for r in data['projects'] if r['category']==category]
        summaries.append({'category':category,'lineItems':len(selected),
            'titleLaneRateRecords':sum(r['allocationPerTitleLaneMeter'] is not None for r in selected),
            'inventoryMatchedRecords':sum(r['matchedInventoryId'] is not None for r in selected),
            'inventorySegmentLaneMatchedRecords':sum(r['laneInventoryEvidence'] is not None for r in selected),
            'assetLengthRecords':sum(r['inventoryAssetLengthMeters'] is not None for r in selected),
            'assetLaneRecords':sum(r['inventoryAssetEffectiveLanes'] is not None for r in selected),
            'assetWidthRecords':sum(r['inventoryAssetWidthMeters'] is not None for r in selected),
            'missingStatedLengthWithAssetLengthRecords':sum(r.get('lengthMeters') is None and r['inventoryAssetLengthMeters'] is not None for r in selected),
            'inventoryProxyRateRecords':sum(r['allocationPerInventoryLaneMeterProxy'] is not None for r in selected),
            'existingAssetLaneRateRecords':sum(r['allocationPerInventoryAssetLaneMeter'] is not None for r in selected),
            'withoutTitleLaneRatePct':round(100*sum(r['allocationPerTitleLaneMeter'] is None for r in selected)/len(selected),2) if selected else 0})
    # No proxy enters the existing per-meter peer flags or Top 25 ranking.
    data['laneCost']={'summary':summaries,'sources':inventory.sources,
        'statusCounts':dict(Counter(r['laneRateStatus'] for r in data['projects'])),
        'methodology':['Title lane-meter rate = whole allocation / (usable stated meters × explicit title lane count). It is not verified construction cost.',
            'Inventory proxy = whole allocation / (stated meters × inventory lanes). Road lane counts are measure-weighted when counts vary along fully covered ranges.',
            'Existing-asset dimensions are recovered separately from funded project length: bridge inventory span/width/lanes, or the union of road section intervals with measure-weighted lanes/widths. Gaps and conflicting or unknown measurements are withheld. Section size never fills a missing funded segment.',
            'Only exact printed section/bridge IDs or a complete exact road name with compatible region/DEO and unique section qualify; no fuzzy names.',
            'Kilometer post brackets map global K station values to section-local measure by interpolation, never extrapolation. Ambiguous or conflicting references are withheld.',
            'Widening needs funded additional lanes; approaches, slope/drainage and mixed scopes are withheld. Bridge span mismatch above 10% prevents the proxy.',
            'Separate existing-bridge asset estimate = allocation / (inventory bridge span × inventory lanes), only for rehabilitation/major repair or retrofitting/strengthening. This is allocation intensity over the existing asset, not a funded-length rate; it never fills stated length or enters high-rate flags. Replacement, new construction and widening are excluded.',
            'Inventory copyright is preserved. Old inventory does not establish the lane count at the FY2027 funded segment.',
            'Inventory proxies remain separate from title-stated rates, historical comparisons and per-meter high-rate flags. No missing funded lane quantity is invented.']}
    data['laneCost']['assetContext']=context_summary(data)
    return data['laneCost']

if __name__=='__main__':
    data=json.loads((ROOT/'analysis_output/cost_per_km.json').read_text())
    print(json.dumps(enrich(data)['summary'],indent=2))
