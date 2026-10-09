#!/usr/bin/env python3
"""Refresh all static report table names from PH location DB and strict location evidence."""
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter,defaultdict
from functools import lru_cache
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
ODV=ROOT.parent/'open-data-visualization'
STATIC=ODV/'static/nep-preview'
sys.path.insert(0,str(ODV/'analysis'))
from strict_congress_geography import GeographicAttribution, text_key, place_key, seat_key

TITLE_KEYS=['projectName','nepTitle','hgabTitle','project','project_name','name','largest_project_name','title']


class PHLocations:
    def __init__(self):
        self.path=ROOT/'location_data/philippine_locations.sqlite'
        self.db=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True);self.db.row_factory=sqlite3.Row
        self.members=defaultdict(set)
        for r in self.db.execute("SELECT d.jurisdiction,d.designation,r.name FROM representative_terms t JOIN representatives r ON r.id=t.representative_id JOIN leg_districts d ON d.id=t.leg_id JOIN sources s ON s.id=t.source_id WHERE s.family='20th_congress_roster'"):
            if seat_key(r['designation']) and text_key(r['name'])!='special election':
                self.members[text_key(r['jurisdiction']),seat_key(r['designation'])].add(r['name'])
        self.seats=[{'province':j,'districtLabel':s} for j,s in sorted(self.members)]
        self.geography=GeographicAttribution(ODV/'static/data',self.seats)
        review=json.loads((STATIC.parent/'data/congress_location_scope_reviews.json').read_text())
        self.held_titles={text_key(v['projectName']) for v in review['decisions'].values() if v.get('holdUnresolved')}

    @lru_cache(maxsize=None)
    def place_candidates(self,name,level,parent_name=''):
        result={}
        # Exact names and structural city labels only; no token or DEO matching.
        keys={text_key(name)}
        if level=='city':keys.update([place_key(name)+' city','city of '+place_key(name)])
        for key in keys:
            for r in self.db.execute('SELECT DISTINCT p.*,a.name_key alias_key FROM places p JOIN aliases a ON a.place_id=p.id WHERE a.name_key=?',(key,)):
                if level=='province' and r['level']!='province':continue
                if level=='city' and r['level']!='city':continue
                if level=='municipality' and r['level'] not in {'city','municipality','locality'}:continue
                if level=='barangay' and r['level']!='barangay':continue
                if parent_name:
                    parent=self.db.execute('SELECT * FROM places WHERE id=?',(r['parent_id'],)).fetchone()
                    if not parent or place_key(parent['name'])!=place_key(parent_name):continue
                result[r['id']]=dict(r)
        return tuple(result.values())

    @lru_cache(maxsize=None)
    def project(self,title):
        if not title or text_key(title) in self.held_titles:return ()
        decision=self.geography.resolve({'projectName':title})
        if not decision['indices']:return ()
        for evidence in decision['evidence']:
            level=evidence.get('level')
            if level=='city':candidates=self.place_candidates(evidence['name'],'city')
            elif level=='municipality':candidates=self.place_candidates(evidence['name'],'municipality',evidence['province'])
            elif level=='barangay':candidates=self.place_candidates(evidence['name'],'barangay',evidence['city'])
            else:continue
            if len(candidates)!=1:return ()
        names=set()
        for i in decision['indices']:
            seat=self.seats[i];people=self.members[text_key(seat['province']),seat_key(seat['districtLabel'])]
            if len(people)!=1:return ()
            names.update(people)
        return tuple(sorted(names))

    @lru_cache(maxsize=None)
    def district(self,label):
        if ' · ' not in label:return ()
        jurisdiction,designation=label.split(' · ',1)
        names=self.members.get((text_key(jurisdiction),seat_key(designation)),set())
        return tuple(sorted(names)) if len(names)==1 else ()

    @lru_cache(maxsize=None)
    def province(self,label):
        if len(self.place_candidates(label,'province'))!=1:return ()
        groups=[v for (j,s),v in self.members.items() if j==text_key(label)]
        # A colliding city and province roster jurisdiction cannot supply a
        # province-wide group by name alone.
        seat_labels={s for j,s in self.members if j==text_key(label)}
        if 'lone' in seat_labels and len(seat_labels)>1:return ()
        if not groups or any(len(v)!=1 for v in groups):return ()
        return tuple(sorted(set().union(*groups)))


def main():
    loc=PHLocations();catalog={};stats=Counter();pages=[]
    def record(title):
        if not isinstance(title,str) or not title.strip():return []
        names=list(loc.project(title));catalog[text_key(title)]=names
        return names
    def walk(value,path=''):
        if isinstance(value,list):
            for row in value:walk(row,path)
        elif isinstance(value,dict):
            titles=[value[k] for k in TITLE_KEYS if isinstance(value.get(k),str) and value[k].strip()]
            side=value.get('third') or value.get('second')
            if isinstance(side,dict) and side.get('projectName'):titles.insert(0,side['projectName'])
            for title in value.get('examples',[]) if isinstance(value.get('examples'),list) else []:
                record(title)
            for title in titles:record(title)
            if titles or 'congressional_representatives' in value:
                previous=value.get('congressional_representatives',[])
                # Current/primary title only; never concatenate it with a prior-year title.
                if '/allocationByProvince' in path:names=list(loc.province(str(value.get('province',''))))
                elif '/strict' in path:names=list(loc.district(str(value.get('district',''))))
                else:names=record(titles[0]) if titles else []
                value['congressional_representatives']=names
                stats['rowsReviewed']+=1;stats['rowsWithNames' if names else 'rowsUnresolved']+=1
                if previous and not names:stats['previousAssignmentsCleared']+=1
                if previous!=names:stats['assignmentsChanged']+=1
            for key,child in list(value.items()):
                if key not in {'congressional_representatives','locationDatabaseReview','summary','geographicEvidence'}:walk(child,path+'/'+key)
    for path in sorted(STATIC.glob('*.json')):
        data=json.loads(path.read_text());walk(data)
        path.write_text((json.dumps(data,ensure_ascii=False,indent=2) if path.name=='budget-innovations-data.json' else json.dumps(data,ensure_ascii=False,separators=(',',':')))+'\n')
    decoder=json.JSONDecoder()
    for path in sorted(STATIC.glob('*.html')):
        page=path.read_text();matches=list(re.finditer(r'(?:const|let|var)\s+\w+\s*=\s*(?=[{\[])',page))
        embedded=0
        for match in reversed(matches):
            try:value,end=decoder.raw_decode(page[match.end():])
            except json.JSONDecodeError:continue
            if not isinstance(value,(dict,list)):continue
            walk(value);embedded+=1
            page=page[:match.end()]+json.dumps(value,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')+page[match.end()+end:]
        # Include literal project cells on legacy tables, with exact full text.
        for cell in re.findall(r'<td\b[^>]*>(.*?)</td>',page,re.S):
            import html
            title=html.unescape(re.sub('<[^>]+>',' ',cell)).strip()
            if title and '${' not in title and len(title)>12:record(title)
        tables=re.findall(r'<thead>(.*?)</thead>',page,re.S)
        pages.append({'page':path.name,'tables':len(tables),'embeddedDocuments':embedded,
                      'tablesWithLocationColumns':sum(bool(re.search(r'project|facility|school|province|district|office|keyword|example|legislative|nep.*line|hgab.*line|line.*item|prior.*line|candidate|term',h,re.I)) for h in tables)})
        page=page.replace('new Blob(', 'PHLocation.createBlob(')
        if 'id="ph-location-table-script"' not in page:
            page=page.replace('</head>','<script id="ph-location-table-script" src="ph-location-representatives.js"></script></head>',1)
        page=re.sub(r'<p class="(?:sub |note )?rep-note">.*?</p>', '<p class="sub rep-note">PH location DB supplies current 20th Congress names through qualified geographic context and the strict local-map screening rules. Uncertain locations stay blank. Names describe geographic coverage, not sponsorship.</p>',page,flags=re.S)
        path.write_text(page)
    payload={'projects':catalog,'provinces':{},'districts':{},'policy':'PH location DB; current 20th Congress geographic coverage, not sponsorship. Undated historic claims do not create new assignments. DEO numbers never establish legislative seats.'}
    for jurisdiction,seat in loc.members:
        payload['districts'][text_key(jurisdiction+' · '+seat+' District')]=list(loc.district(jurisdiction+' · '+seat))
        payload['provinces'][jurisdiction]=list(loc.province(jurisdiction))
    template=(ROOT/'location_data/table_representatives.js').read_text()
    asset=template.replace('__PH_LOCATION_PAYLOAD__',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
    (STATIC/'ph-location-representatives.js').write_text(asset)
    version=hashlib.sha256(asset.encode()).hexdigest()[:12]
    for page in pages:
        path=STATIC/page['page'];text=path.read_text()
        text=re.sub(r'src="ph-location-representatives\.js(?:\?v=[^"]*)?"',f'src="ph-location-representatives.js?v={version}"',text)
        path.write_text(text)
    audit={'databaseName':'PH location DB','databaseSha256':hashlib.sha256(loc.path.read_bytes()).hexdigest(),
           'counts':dict(stats),'catalogTitles':len(catalog),'pages':pages,'policy':payload['policy'],
           'limitations':['A blank name is unresolved coverage, not absence of funding.','School names, DEO aggregates, generic scheme titles and geographic terms alone cannot identify a legislative seat.','Province-wide names are geographic context only; names for featured projects do not cover all projects in an aggregate.']}
    audit['limitations'].append('Row counts include repeated appearances across report data and embedded views; they are not distinct project counts.')
    (ROOT/'analysis_output/ph_location_representative_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
