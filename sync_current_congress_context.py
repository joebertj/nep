#!/usr/bin/env python3
"""Synchronize current geographic representative labels across public reports."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
sys.path.insert(0, str(ROOT.parent / 'open-data-visualization/analysis'))
import enrich_nep_preview_representatives as reps


def sync():
    before = json.loads(reps.ROSTER_PATH.read_text())
    after = reps.roster_rows()
    names = {a['representative']: b['representative'] for a,b in zip(before,after)
             if a.get('representative') != b.get('representative')}
    districts = {f"{a['province']} · {('Lone District' if reps.district_key(a['district']) == 'lone' else a['district']+' District')}": b.get('displayDistrict')
                 for a,b in zip(before,after) if b.get('displayDistrict')}
    current_data=json.loads((STATIC/'integrated-district-data.json').read_text())
    district_rows={reps.norm(row['district']):row for row in current_data['districts']}
    for old,new in districts.items():
        if reps.norm(new) in district_rows:district_rows[reps.norm(old)]=district_rows[reps.norm(new)]
    city_aliases={}
    for key,row in district_rows.items():
        alias=re.sub(r'\bcity\b','',key);alias=' '.join(alias.split())
        city_aliases.setdefault(alias,[]).append(row)
    changed_files = []
    def change(value, field='', representative_card=False):
        if isinstance(value, dict):
            if representative_card and value.get('district'):
                key=reps.norm(value['district']);seat=district_rows.get(key)
                if not seat:
                    options={r['districtId']:r for r in city_aliases.get(' '.join(re.sub(r'\bcity\b','',key).split()),[])}
                    seat=next(iter(options.values())) if len(options)==1 else None
                if seat:
                    value.update(name=seat['representative'],officialName=seat['representative'],district=seat['district'],photoUrl=seat['representativePhotoUrl'],
                                 resolutionStatus='current_roster_geographic_context',memberStatus=seat.get('memberStatus','active'))
            for k,v in list(value.items()):
                value[k] = change(v, k, representative_card or field == 'representativeCards')
        elif isinstance(value, list):
            return [change(v,field,representative_card or field == 'representativeCards') for v in value]
        elif isinstance(value, str):
            if field in {'representative','representatives','congressional_representatives','representativePhotoName'} or (representative_card and field == 'name'):
                return names.get(value,value)
            if field in {'district','districts','reportDistrict','legDistricts'}:
                return districts.get(value) or value
        return value
    for filename in ['congress-district-review-data.json','congress-data.json','dpwh-data.json','dpwh-hgab-comparison.json','mpb-data.json','fmr-data.json','deped-data.json','nia-irrigation-data.json']:
        path = STATIC / filename
        if not path.exists():continue
        old = path.read_text()
        if not any(name in old for name in names) and not any(name in old for name in districts):continue
        data = json.loads(old);data = change(data)
        new = json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n'
        if json.loads(old) != data:
            path.write_text(new);changed_files.append(filename)
    # Retain official profile IDs used by existing pages; fill the five seats
    # absent from the original asset roster and disambiguate special elections.
    path=STATIC/'congress-district-roster.json'
    roster=json.loads(path.read_text());old_by_photo={r['photoUrl']:r for r in roster['districts'] if r.get('photoUrl')}
    old_by_id={r['districtId']:r for r in roster['districts']}
    data=current_data
    items=[]
    for seat in data['districts']:
        original=seat.get('representativePhotoOriginalUrl') or seat.get('representativePhotoUrl')
        prefix,number=seat['districtId'].rsplit(':',1)
        old=old_by_photo.get(original) or old_by_id.get(seat['districtId']) or old_by_id.get(prefix+'-city:'+number) or {}
        items.append({'districtId':old.get('districtId',seat['districtId']), 'district':seat['district'],
                      'name':seat['representative'],'status':'resolved','photoUrl':original if seat.get('memberStatus')=='active' else None,
                      'sourceName':old.get('sourceName') or old.get('name') or seat['representative'],
                      'memberStatus':seat.get('memberStatus','active'),
                      'lastRepresentative':seat.get('lastRepresentative'),
                      'verifiedPhotoUrl':seat['representativePhotoUrl'] if seat['representativePhotoStatus']=='verified_image' else None,
                      'photoVerification':seat['representativePhotoStatus'],
                      'portraitSourceUrl':seat['representativePhotoSourceUrl'],
                      'profileUrl':old.get('profileUrl') or 'https://www.congress.gov.ph/house-members'})
    roster.update(count=len(items),districts=items,currentRosterSource='static/data/20th_congress_roster_corrections.json',rosterContext='Current 20th Congress geographic coverage only')
    path.write_text(json.dumps(roster,ensure_ascii=False,separators=(',',':'))+'\n')
    # Update data fetch versions only; preserve all navigation markup/styles.
    page=STATIC/'congress.html'
    if page.exists():
        text=page.read_text()
        text=text.replace('photoUrl:r.photoUrl','photoUrl:r.verifiedPhotoUrl||r.photoUrl')
        for filename in ['congress-district-roster.json','congress-data.json','congress-district-review-data.json']:
            version=hashlib.sha256((STATIC/filename).read_bytes()).hexdigest()[:12]
            text=re.sub(r"fetch\('"+re.escape(filename)+r"(?:\?v=[^']*)?'\)","fetch('"+filename+"?v="+version+"')",text)
        page.write_text(text)
    # Older pages embed public data models. Update only decoded JSON fields;
    # never replace names in project titles, source quotations, menus or JS.
    decoder=json.JSONDecoder()
    for root in (STATIC,ROOT/'analysis_output'):
        for path in root.glob('*.html'):
            text=path.read_text();changes=[]
            for match in re.finditer(r'\b(?:const\s+D|window\.[A-Z_]+_DATA)\s*=\s*(?=\{)',text):
                try:payload,end=decoder.raw_decode(text[match.end():])
                except ValueError:continue
                original=json.dumps(payload,ensure_ascii=False,sort_keys=True)
                fixed=change(payload)
                if json.dumps(fixed,ensure_ascii=False,sort_keys=True)!=original:
                    changes.append((match.end(),match.end()+end,json.dumps(fixed,ensure_ascii=False,separators=(',',':'))))
            for match in re.finditer(r'<script\b[^>]*\btype=["\']application/json["\'][^>]*>(.*?)</script>',text,re.S):
                try:payload=json.loads(match[1])
                except ValueError:continue
                original=json.dumps(payload,ensure_ascii=False,sort_keys=True);fixed=change(payload)
                if json.dumps(fixed,ensure_ascii=False,sort_keys=True)!=original:
                    changes.append((match.start(1),match.end(1),json.dumps(fixed,ensure_ascii=False,separators=(',',':'))))
            if changes:
                for start,end,replacement in sorted(changes,reverse=True):text=text[:start]+replacement+text[end:]
                path.write_text(text)
    return {'updatedContextFiles':changed_files,'currentRosterDistricts':len(items)}


if __name__=='__main__':print(json.dumps(sync()))
