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
from location_data.location_text import geographic_title,barangay_key

ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
CATEGORY='BIP - Multi-Purpose Buildings/ Facilities to support Social Services'
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
    q=qualified(title)
    if q and all(len(q[k])==1 for k in ['province','municipality','barangay']):
        key=tuple(next(iter(q[k])) for k in ['province','municipality','barangay'])
        return {'key':key,'label':' · '.join(reversed(key)),'status':'Qualified barangay, municipality and province agree'}
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

def evidence(left,right):
    a,b=coordinates(left),coordinates(right);pa,pb=place(left),place(right)
    meters=round(distance(a,b),1) if a['status']==b['status']=='Usable printed point' else None
    same=bool(pa['key'] and pa['key']==pb['key']);verified=same and pa['status'].startswith('Qualified')
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
        if p['key']:groups[p['key']].append(r)
    current=[]
    for members in groups.values():
        # Coordinate-ready pairs only; coverage below exposes missing records.
        ready=[r for r in members if coordinates(r['projectName'])['status']=='Usable printed point']
        for a,b in combinations(ready,2):
            current.append({'pairType':'HGAB 3rd · same barangay labels','projectName':a['projectName'],'otherProject':b['projectName'],
                'sourceLabel':a['hgab_id']+' · p. '+a['sourcePage'],'otherSource':b['hgab_id']+' · p. '+b['sourcePage'],
                'currentAllocationPesos':int(a['amountPesos']),'otherAllocationPesos':int(b['amountPesos']),**evidence(a['projectName'],b['projectName'])})
    summary={'historicalPairs':len(historical),'historicalPairsWithDistance':sum(r['distanceMeters'] is not None for r in historical),
        'historicalUnder100m':sum(r['distanceMeters'] is not None and r['distanceMeters']<100 for r in historical),
        'historicalUnder50mSameSiteCandidates':sum(r['distanceMeters'] is not None and r['distanceMeters']<50 for r in historical),
        'hgabLines':len(rows),'hgabLinesWithUsablePoint':sum(coordinates(r['projectName'])['status']=='Usable printed point' for r in rows),
        'currentSameBarangayCoordinatePairs':len(current),'currentVerifiedSameBarangayPairs':sum(r['sameBarangayVerified'] for r in current),
        'currentUnder50mSameSiteCandidates':sum(r['distanceMeters']<50 for r in current)}
    data={'summary':summary,'historical':historical,'current':current,
        'method':'Haversine great-circle separation, radius 6,371,008.8 meters, between one unambiguous decimal point per title. Latitude/longitude order inferred only from nonoverlapping local screening ranges (4–22 latitude, 116–127 longitude), recorded per point. At least four decimal places required. No geocoding, centroid substitution, nearest-coordinate join or coordinate borrowing from other rows/stages.',
        'limits':['Printed points are not verified building footprints. Identical or nearby coordinates can be rounded, copied or reference a barangay center. Decimal precision is not positional accuracy.',
            'Under-50-meter pairs are interpreted as likely same-site references for scope review. They are not counted as two confirmed buildings. Site identity requires maps, asset IDs, designs or field verification; nearby plots can contain different structures.',
            'Coordinates pass a broad Philippines numeric-range check, not a barangay/province boundary-containment check. Large separation under matching labels may reflect coordinate or location errors.',
            'A same-barangay identity requires agreement at barangay, municipality and province levels. Matching city wording without a qualified hierarchy is separately marked unverified.',
            'One MPB per barangay is a needs-screening hypothesis, not a validated entitlement rule. Different functions, population, capacity, accessibility and hazard exposure may justify multiple facilities.',
            'Historical completion/repair allocations can fund the same legitimate building in successive years. A short distance does not establish two separate buildings or duplicate payment.',
            'Farther points can support a separate-site interpretation but do not establish need. The 50/100/250/1000-meter bins are descriptive review bands, not corruption thresholds.',
            'Pairs are not distinct projects; a cluster of three items yields three pairs. Do not sum pair allocations as losses.'],
        'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [OUT/'hb_nep_comparison_3rd.csv',OUT/'priority_program_year_on_year_candidates.csv',ROOT/'location_data/philippine_locations.sqlite']]}
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n';(OUT/'mpb_proximity.json').write_text(serialized);(STATIC/'mpb-proximity.json').write_text(serialized)
    return data

def render(data,keys=('historical','current')):
    from build_investigation_summary import table,esc
    s=data['summary'];body=f'<section id="mpb-coordinate-proximity" class="card"><h2>MPB locations · same-site funding and separate-site review</h2><p>{s["historicalPairsWithDistance"]:,} of {s["historicalPairs"]:,} historical comparison pairs have usable coordinates at both ends. {s["hgabLinesWithUsablePoint"]:,} of {s["hgabLines"]:,} HGAB MPB entries have usable printed points. Pairs under 50 meters are reviewed as likely references to the same site. The question is whether allocations cover legitimate continuation, different components, or repeated funding of the same work. Pair counts describe allocations, not a verified inventory of distinct buildings.</p>'
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
