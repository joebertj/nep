"""Resolve exact bridge-ID projects through ArcGIS DEO and CONG_DIST fields."""
import re

from location_data.location_text import text_key

BRIDGE_ID=re.compile(r'\bB\d{5}[A-Z]{2}\b')
ORDINALS={'lone':'lone','first':'1st','second':'2nd','third':'3rd','fourth':'4th',
          'fifth':'5th','sixth':'6th','seventh':'7th','eighth':'8th','ninth':'9th'}

def leg_key(label,seats):
    match=re.fullmatch(r'\s*(.*?)\s*\(([^()]*)\)\s*',label or '')
    if not match:return None
    designation=match.group(2).strip().lower().replace(' district','')
    designation=ORDINALS.get(designation,designation)
    jurisdiction=text_key(match.group(1))
    candidates={(text_key(row['province']),row['districtLabel']) for row in seats
                if row['districtLabel']==designation and row['province']==jurisdiction}
    if not candidates and jurisdiction.startswith('city of '):
        jurisdiction=jurisdiction[len('city of '):]
        candidates={(text_key(row['province']),row['districtLabel']) for row in seats
                    if row['districtLabel']==designation and row['province']==jurisdiction}
    if not candidates and jurisdiction.endswith(' city'):
        jurisdiction=jurisdiction[:-len(' city')]
        candidates={(text_key(row['province']),row['districtLabel']) for row in seats
                    if row['districtLabel']==designation and row['province']==jurisdiction}
    return next(iter(candidates)) if len(candidates)==1 else None

def build_contexts(projects,bridge_rows,seats):
    """Return project-keyed bridge evidence; ambiguous labels remain unresolved."""
    by_id={}
    for row in bridge_rows:
        attributes=row.get('attributes',row)
        bridge_id=str(attributes.get('BRIDGE_ID') or '').upper()
        if bridge_id:by_id.setdefault(bridge_id,[]).append(attributes)
    output={}
    counts={'exactUniqueBridgeId':0,'uniqueCurrentLEG':0,'unmappedLEG':0,'regionConflict':0}
    for title,row in projects.items():
        ids=sorted(set(BRIDGE_ID.findall((row.get('projectName') or '').upper())))
        if len(ids)!=1 or len(by_id.get(ids[0],[]))!=1:continue
        counts['exactUniqueBridgeId']+=1
        source=by_id[ids[0]][0]
        if row.get('region') and text_key(row['region'])!=text_key(source.get('REGION')):
            counts['regionConflict']+=1
            continue
        seat=leg_key(source.get('CONG_DIST'),seats)
        if not seat or not source.get('DEO'):
            counts['unmappedLEG']+=1
            continue
        counts['uniqueCurrentLEG']+=1
        output[text_key(title)]={
            'bridgeId':ids[0], 'objectId':source.get('OBJECTID'), 'deo':source.get('DEO'),
            'congDist':source.get('CONG_DIST'), 'seatKeys':[list(seat)],
            'region':source.get('REGION'), 'municipality':source.get('MUNICIPAL'),
            'province':source.get('PROVINCE'),
            'basis':'Exact bridge ID links the project title to one ArcGIS bridge record. That record lists this DEO and CONG_DIST; the district label matches one current LEG roster entry. Used only when title geography does not resolve.'}
    return output,counts
