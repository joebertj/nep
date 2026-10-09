#!/usr/bin/env python3
"""Build a provenance-preserving SQLite location/LEG/DEO database from workspace files."""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ODV = ROOT.parent / 'open-data-visualization'
DATA = ODV / 'static/data'
OUT = Path(__file__).resolve().parent

def norm(value):
    s = unicodedata.normalize('NFKD', str(value or ''))
    return re.sub(r'\s+', ' ', ''.join(c for c in s if not unicodedata.combining(c)).casefold()).strip()

def identity_key(value):
    # Lookup accent folding must not merge distinct source identities.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC',str(value or '')).casefold()).strip()

def uid(*values):
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()[:32]

def city_name(name):
    s = re.sub(r'^city of\s+', '', str(name).strip(), flags=re.I)
    return re.sub(r'\s+city$', '', s, flags=re.I).strip()

def district(value):
    s = norm(value)
    m = re.fullmatch(r'(lone|[1-9](?:st|nd|rd|th))(?: district)?', s)
    return ('Lone District' if m.group(1)=='lone' else m.group(1)+' District') if m else None

def is_city(name):
    return bool(re.search(r'^city of\b|\bcity\b', str(name), re.I))

def clean_person(name):
    return re.sub(r'\s+', ' ', re.sub(r'\[[^]]+\]', '', str(name or ''))).strip()

class Builder:
    def __init__(self, con):
        self.db = con
        self.country = self.place('Philippines','country',None)

    def source(self,path,family,kind,disposition='imported',note=None):
        path = Path(path)
        sid = uid('source',str(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
        self.db.execute('INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?,?,?)',
                        (sid,str(path),digest,path.stat().st_size if path.exists() else None,family,kind,disposition,note))
        return sid

    def issue(self,kind,entity,sid,locator,detail):
        self.db.execute('INSERT OR IGNORE INTO issues VALUES(?,?,?,?,?,?)',
                        (uid(kind,entity,sid,locator,detail),kind,entity,sid,str(locator),json.dumps(detail,ensure_ascii=False)))

    def alias(self,pid,name,sid,kind='source_name'):
        if norm(name):
            self.db.execute('INSERT OR IGNORE INTO aliases VALUES(?,?,?,?,?)',(pid,str(name),norm(name),sid,kind))

    def place(self,name,level,parent,sid=None,locator='',claimed_level=None):
        name = str(name).strip()
        identity = city_name(name) if level=='city' else name
        pid = uid('place',level,parent,identity_key(identity))
        self.db.execute('INSERT OR IGNORE INTO places(id,level,parent_id,name,name_key) VALUES(?,?,?,?,?)',
                        (pid,level,parent,identity,norm(identity)))
        if sid:
            self.alias(pid,name,sid)
            self.db.execute('INSERT OR IGNORE INTO place_claims VALUES(?,?,?,?)',(pid,sid,str(locator),claimed_level or level))
            if parent:
                self.db.execute('INSERT OR IGNORE INTO parent_claims VALUES(?,?,?,?,?,?,?)',(pid,parent,'geographic_context',sid,str(locator),None,None))
            if level=='city':
                for alias in [identity,identity+' City','City of '+identity]:
                    self.alias(pid,alias,sid,'city_label_variant')
        return pid

    def region(self,name,sid,locator):
        # Region aliases are recorded without assuming today's boundaries.
        raw = str(name or '').strip()
        if not raw:return None
        number = re.fullmatch(r'region\s+(\d+)',norm(raw))
        roman = re.search(r'\bregion\s+([ivx]+(?:-[ab])?)\b',norm(raw))
        values={'i':'1','ii':'2','iii':'3','iv-a':'4-A','iv-b':'4-B','v':'5','vi':'6','vii':'7','viii':'8','ix':'9','x':'10','xi':'11','xii':'12','xiii':'13'}
        key = number.group(1) if number else values.get(roman.group(1)) if roman else None
        if 'cordillera' in norm(raw) or norm(raw)=='car':key='CAR'
        if 'capital region' in norm(raw) or norm(raw)=='ncr':key='NCR'
        if 'bangsamoro' in norm(raw) or norm(raw)=='barmm':key='BARMM'
        if 'autonomous region' in norm(raw) and 'muslim' in norm(raw) and not key:key='ARMM'
        pid=self.place('Region '+key if key else raw,'region',self.country,sid,locator)
        self.alias(pid,raw,sid,'region_label')
        return pid

    def province(self,name,sid,locator,region=None):
        if not str(name or '').strip():return None
        level='source_container' if norm(name).startswith('national capital region -') else 'province'
        pid=self.place(name,level,self.country,sid,locator)
        if region:
            self.db.execute('INSERT OR IGNORE INTO parent_claims VALUES(?,?,?,?,?,?,?)',(pid,region,'region_membership',sid,str(locator),None,None))
        return pid

    def locality(self,name,parent,sid,locator,level=None):
        return self.place(name,level or ('city' if is_city(name) else 'locality'),parent,sid,locator)

    def find(self,name,levels=None,parent=None):
        params=[norm(name)];sql='SELECT DISTINCT p.id FROM places p JOIN aliases a ON a.place_id=p.id WHERE a.name_key=?'
        if levels:
            sql+=' AND p.level IN ('+','.join('?' for _ in levels)+')';params+=list(levels)
        if parent:
            sql+=' AND p.parent_id=?';params.append(parent)
        return [r[0] for r in self.db.execute(sql,params)]

    def leg(self,jurisdiction,designation,sid,locator):
        des=district(designation)
        if not des:return None
        lid=uid('leg',norm(jurisdiction),des)
        self.db.execute('INSERT OR IGNORE INTO leg_districts VALUES(?,?,?,?)',(lid,jurisdiction,norm(jurisdiction),des))
        for pid in self.find(jurisdiction,('province','city')):
            self.db.execute('INSERT OR IGNORE INTO leg_jurisdiction_claims VALUES(?,?,?,?)',(lid,pid,sid,str(locator)))
        return lid

    def membership(self,candidates,lid,sid,locator,raw,scope='date_unknown',start=None,end=None):
        if not lid:return
        candidates=sorted(set(candidates));pid=candidates[0] if len(candidates)==1 else None
        status='located_source_claim' if pid else 'ambiguous_place' if candidates else 'unlocated_source_claim'
        self.db.execute('INSERT OR IGNORE INTO leg_memberships VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (uid('membership',sid,locator,lid),pid,lid,sid,str(locator),scope,start,end,status,json.dumps(candidates),json.dumps(raw,ensure_ascii=False)))
        if not pid:self.issue(status,lid,sid,locator,raw)

    def person(self,name,lid,sid,locator,term=None,start=None,end=None):
        name=clean_person(name)
        if not name or not lid or norm(name) in {'tbd','special election','district'}:return
        # A shared personal name across different seats is not proof of identity.
        rid=uid('person',lid,identity_key(name))
        self.db.execute('INSERT OR IGNORE INTO representatives VALUES(?,?,?)',(rid,name,norm(name)))
        self.db.execute('INSERT OR IGNORE INTO representative_terms VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                        (uid('term',sid,lid,identity_key(name),term,start,end),rid,lid,sid,str(locator),term,start,end,None,None,json.dumps({'name':name,'term':term},ensure_ascii=False)))

    def observed(self,sid,locator,kind,row):
        self.db.execute('INSERT OR IGNORE INTO observations VALUES(?,?,?,?,?)',(uid(sid,locator,kind),sid,str(locator),kind,json.dumps(row,ensure_ascii=False)))

    def unified(self,path):
        sid=self.source(path,'unified_locations','derived_hierarchy_and_districts',note='Derived merged dataset; not independent confirmation of its constituent maps.')
        for i,row in enumerate(json.loads(path.read_text())):
            reg=self.region(row.get('region'),sid,i);prov=self.province(row.get('province'),sid,i,reg)
            if not prov:continue
            town=self.locality(row['municipality'],prov,sid,i) if row.get('municipality') else None
            brgy=self.place(row['barangay'],'barangay',town,sid,i) if row.get('barangay') and town else None
            lid=self.leg(row.get('province',''),row.get('district'),sid,i)
            if lid:
                self.membership([brgy or town] if brgy or town else [],lid,sid,i,row,'derived_current_unknown')
                # Names in this merged dataset are retained as undated source claims.
                self.person(row.get('congressman'),lid,sid,'representative:'+str(i),'derived; dates unknown')

    def hierarchy(self,path):
        sid=self.source(path,'city_barangay_hierarchy','hierarchy')
        for province,cities in json.loads(path.read_text()).items():
            prov=self.province(province,sid,province)
            for city,barangays in cities.items():
                town=self.locality(city,prov,sid,province+'/'+city)
                for i,name in enumerate(barangays):self.place(name,'barangay',town,sid,province+'/'+city+'/'+str(i))

    def geo_database(self,path):
        sid=self.source(path,'geo_derived','derived_geometry_hierarchy',note='Existing derived city classifications are claims; bare names are not automatically classified as cities.')
        data=json.loads(path.read_text())
        for key,row in data.get('provinces',{}).items():
            reg=self.region(row.get('region_name'),sid,'provinces/'+key)
            self.province(row.get('name',key),sid,'provinces/'+key,reg)
        for group in ['cities','municipalities']:
            for key,rows in data.get(group,{}).items():
                for row in rows if isinstance(rows,list) else [rows]:
                    prov=self.province(row.get('province'),sid,group+'/'+key)
                    if not prov:continue
                    # Several bare municipalities were labeled city in this file.
                    level='city' if is_city(row.get('name',key)) else 'municipality' if group=='municipalities' else 'locality'
                    pid=self.locality(row.get('name',key),prov,sid,group+'/'+key,level)
                    if group=='cities' and level!='city':self.issue('uncorroborated_city_type',pid,sid,group+'/'+key,row)

    def district_maps(self,path,family,generated=False):
        sid=self.source(path,family,'leg_mapping',note='District boundaries and dates are source claims, not independently verified.')
        data=json.loads(path.read_text());data=data.get('districts',data)
        for jurisdiction,detail in data.items():
            if 'party-list' in norm(jurisdiction):continue
            if generated:
                prov=self.province(jurisdiction,sid,jurisdiction)
                for town,value in detail.items():
                    loc=jurisdiction+'/'+town
                    if isinstance(value,str):
                        candidates=self.find(town,('city','municipality','locality'),prov)
                        if not candidates:candidates=[self.locality(town,prov,sid,loc)]
                        # An election city can have its own LEG jurisdiction;
                        # its geographic province is not automatically that LEG.
                        city_label=self.city_roster_label(town) if is_city(town) else None
                        label=city_label or jurisdiction
                        lid=self.leg(label,value,sid,loc)
                        self.membership(candidates,lid,sid,loc,{'geographicProvince':jurisdiction,'locality':town,'district':value,
                                        'legJurisdiction':label,'jurisdictionBasis':'unique city identity + roster' if city_label else 'source province label; may require jurisdiction review'},'election_2025_derived_dates_unknown')
                    elif isinstance(value,dict):
                        candidates=self.find(town,('city',),prov) or self.find(town,('city',))
                        city=candidates[0] if len(candidates)==1 else self.locality(town,prov,sid,loc,'city')
                        for name,des in value.get('barangays',{}).items():
                            b=self.place(name,'barangay',city,sid,loc+'/'+name)
                            jurisdiction_name=self.db.execute('SELECT name FROM places WHERE id=?',(city,)).fetchone()[0]
                            # Roster aliases are attached separately; City is retained in jurisdiction labels.
                            label=city_name(town)+' City'
                            roster_label=self.city_roster_label(town)
                            lid=self.leg(roster_label or label,des,sid,loc+'/'+name)
                            self.membership([b],lid,sid,loc+'/'+name,{'city':town,'barangay':name,'district':des},'election_2025_derived_dates_unknown')
                continue
            if not isinstance(detail,dict):continue
            if detail.get('municipalities'):
                prov=self.province(jurisdiction,sid,jurisdiction)
                for town,des in detail['municipalities'].items():
                    loc=jurisdiction+'/municipalities/'+town
                    candidates=self.find(town,('city','municipality','locality'),prov)
                    if not candidates:candidates=[self.locality(town,prov,sid,loc)]
                    self.membership(candidates,self.leg(jurisdiction,des,sid,loc),sid,loc,{'jurisdiction':jurisdiction,'municipality':town,'district':des})
            if detail.get('barangays'):
                cities=self.find(jurisdiction,('city',))
                for des,names in detail['barangays'].items():
                    lid=self.leg(jurisdiction,des,sid,jurisdiction)
                    for name in names if isinstance(names,list) else []:
                        loc=jurisdiction+'/barangays/'+des+'/'+name
                        if norm(city_name(name))==norm(city_name(jurisdiction)):
                            self.issue('city_listed_as_barangay',lid,sid,loc,{'name':name});continue
                        candidates=[]
                        for city in cities:candidates.extend(self.find(name,('barangay',),city))
                        if not candidates and len(cities)==1:candidates=[self.place(name,'barangay',cities[0],sid,loc)]
                        self.membership(candidates,lid,sid,loc,{'city':jurisdiction,'barangay':name,'district':des})
            for des,name in detail.get('representatives',{}).items():
                lid=self.leg(jurisdiction,des,sid,jurisdiction)
                for j,part in enumerate(str(name).split(';')):
                    years=re.search(r'\((\d{4})\s*[-–]\s*(\d{4}|present)\)',part,re.I)
                    clean=re.sub(r'\s*\(\d{4}[^)]*\)', '',part).strip()
                    self.person(clean,lid,sid,jurisdiction+'/representatives/'+des+'/'+str(j),
                                'year range parsed from source text' if years else 'raw source; dates unknown',
                                int(years.group(1)) if years else None,
                                int(years.group(2)) if years and years.group(2).isdigit() else None)
                    self.observed(sid,jurisdiction+'/representatives/'+des+'/'+str(j),'raw_representative_text',{'text':part,'jurisdiction':jurisdiction,'district':des})

    def city_roster_label(self,name):
        if len(self.find(name,('city',)))!=1:return None
        labels={norm(city_name(row['province'])):row['province'] for row in self.roster_rows if is_city(row['province'])}
        if norm(city_name(name)) in labels:return labels[norm(city_name(name))]
        # For jurisdictions such as Cagayan de Oro whose roster label omits City,
        # require the exact base name and a known city record.
        for row in self.roster_rows:
            if norm(row['province'])==norm(city_name(name)) and self.find(name,('city',)):
                return row['province']
        return labels.get(norm(city_name(name)))

    def roster(self,path):
        sid=self.source(path,'20th_congress_roster','representative_roster')
        self.roster_rows=json.loads(path.read_text())
        for i,row in enumerate(self.roster_rows):
            lid=self.leg(row.get('province',''),row.get('district'),sid,i)
            self.person(row.get('representative'),lid,sid,i,'20th Congress; exact dates not supplied')

    def historical_reps(self,path):
        sid=self.source(path,'consolidated_representatives','historical_roster_and_coverage')
        for i,row in enumerate(json.loads(path.read_text())):
            jurisdiction=row.get('province');des=row.get('district_number');lid=self.leg(jurisdiction or '',des,sid,i)
            terms=row.get('terms') or []
            if isinstance(terms,str):
                try:terms=json.loads(terms)
                except json.JSONDecodeError:terms=[]
            for j,term in enumerate(terms or [{}]):
                self.person(row.get('display_name'),lid,sid,f'{i}/terms/{j}','source year ranges',term.get('start'),term.get('end'))
            parents=self.find(jurisdiction,('city',) if row.get('is_city_district') else ('province',))
            for j,name in enumerate(row.get('barangays') or []):
                candidates=[]
                for parent in parents:candidates+=self.find(name,('barangay',) if row.get('is_city_district') else ('city','municipality','locality'),parent)
                self.membership(candidates,lid,sid,f'{i}/coverage/{j}',{'name':name,'terms':terms},'historical_coverage_dates_not_individually_specified')

    def deo(self,name,sid):
        # Only an explicit expansion of DEO is normalized; the ordinal is retained.
        name=str(name).strip();key=norm(re.sub(r'\bDEO\b','District Engineering Office',name,flags=re.I))
        did=uid('deo',key)
        self.db.execute('INSERT OR IGNORE INTO deos VALUES(?,?,?)',(did,name,key))
        self.db.execute('INSERT OR IGNORE INTO deo_aliases VALUES(?,?,?,?)',(did,name,norm(name),sid))
        return did

    def deo_crosswalk(self,path,pdf):
        sid=self.source(path,'dpwh_district_pdf_transcription','deo_leg_crosswalk',note='Existing literal JavaScript transcription; fiscal year, stage and source pages unknown. Not project reallocation.')
        self.source(pdf,'dpwh_district_pdf','scanned_pdf','reference_only','Source of the existing transcription; no new OCR performed.')
        text=path.read_text();start=text.index('const deoLegRows=');end=text.index('const moneyMillions',start)
        rows=re.findall(r"\['([^']+)','([^']+)',([0-9]+)\]",text[start:end])
        for i,(name,leg,amount) in enumerate(rows):
            if ' · ' not in leg:continue
            jurisdiction,des=leg.split(' · ',1);lid=self.leg(jurisdiction,des,sid,'deoLegRows/'+str(i));did=self.deo(name,sid)
            if not lid:continue
            self.db.execute('INSERT OR IGNORE INTO deo_leg_claims VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                            (uid(sid,i),did,lid,sid,'deoLegRows/'+str(i),None,None,int(amount)*1000,None,None,'transcribed_reference_dates_unknown',json.dumps({'deo':name,'leg':leg,'amountThousands':int(amount),'zeroMeansPrintedDash':int(amount)==0,'pdf':str(pdf)},ensure_ascii=False)))

    def office_observations(self,path,stage='HGAB 3rd'):
        sid=self.source(path,'HGAB_3rd_DPWH' if stage=='HGAB 3rd' else 'NEP_DPWH','budget_office_observations')
        records=json.loads(path.read_text())['data']['data']
        for row in records:
            office=str(row.get('office') or '')
            if 'district engineering office' not in norm(office):continue
            did=self.deo(office,sid)
            self.observed(sid,row.get('id'),'budget_office',{'deoId':did,'office':office,'region':row.get('region'),'title':row.get('projectName'),'sourcePage':row.get('sourcePage'),'stage':stage,'fiscalYear':row.get('fiscalYear')})
        # Office labels identify administrators, not the locations of every project.

    def geo_file(self,path):
        sid=self.source(path,'local_geojson','geometry_metadata')
        data=json.loads(path.read_text());features=data.get('features',[data])
        for i,feature in enumerate(features):
            row=feature.get('properties',{});reg=self.region(row.get('region_name'),sid,i)
            prov=self.province(row.get('province_name'),sid,i,reg)
            if row.get('type')=='province' and not prov:prov=self.province(row.get('name'),sid,i,reg)
            town=None
            if prov and (row.get('city_name') or row.get('municipality_name')):
                town=self.locality(row.get('city_name') or row['municipality_name'],prov,sid,i,'city' if row.get('city_name') else 'municipality')
            for pid,level in [(reg,'region'),(prov,'province'),(town,'city' if row.get('city_name') else 'municipality')]:
                if pid and row.get(level+'_reference'):
                    self.db.execute('INSERT OR IGNORE INTO place_codes VALUES(?,?,?,?,?)',(pid,'geojson_'+level+'_reference',str(row[level+'_reference']),sid,str(i)))
            if not any([reg,prov,town]) and row.get('name'):self.observed(sid,i,'boundary_name',row)

    def mapping(self,path):
        sid=self.source(path,'province_city_cache','derived_hierarchy',note='Some lists contain municipality names; the file name is not evidence of city status.')
        for name,towns in json.loads(path.read_text()).items():
            prov=self.province(name,sid,name)
            for town in towns if isinstance(towns,list) else []:self.locality(town,prov,sid,name+'/'+town)

    def metro_aliases(self,path):
        sid=self.source(path,'metro_city_aliases','explicit_aliases')
        data=json.loads(path.read_text());prov=self.province(data['province'],sid,'province')
        for alias in data.get('aliases',[]):self.alias(prov,alias,sid,'source_alias')
        for i,row in enumerate(data.get('cities',[])):
            candidates=self.find(row['name'],('city','municipality','locality'),prov)
            pid=candidates[0] if len(candidates)==1 else self.locality(row['name'],prov,sid,i)
            for alias in row.get('aliases',[]):self.alias(pid,alias,sid,'source_alias')

    def rainfall_codes(self,path):
        sid=self.source(path,'legacy_rainfall_crosswalk','legacy_codes',note='Rainfall P-codes are source-specific legacy codes, not asserted current PSGC identifiers.')
        values={}
        for node in ast.parse(path.read_text()).body:
            if isinstance(node,ast.Assign):
                for target in node.targets:
                    if isinstance(target,ast.Name) and target.id in ['PCODE_PROVINCE','REGION_NAMES']:
                        values[target.id]=ast.literal_eval(node.value)
        for code,name in values.get('PCODE_PROVINCE',{}).items():
            reg=self.region(values.get('REGION_NAMES',{}).get(code[:4]),sid,code)
            prov=self.province(name,sid,code,reg)
            self.db.execute('INSERT OR IGNORE INTO place_codes VALUES(?,?,?,?,?)',(prov,'legacy_rainfall_pcode',code,sid,code))

    def edge_cases(self,path):
        sid=self.source(path,'butuan_location_review','derived_location_role_review',note='Source-specific scope review; does not establish district boundaries or adjust public allocations.')
        data=json.loads(path.read_text())
        for row in data.get('edgeCases',[]):
            self.observed(sid,row['id'],'location_edge_case',row)
            if row.get('edgeCase')=='Unresolved route-wide scope':
                self.issue('project_route_scope_review',row['id'],sid,row['id'],{'title':row['projectName'],'assessment':row['assessment'],'sourcePage':row['sourcePage']})

    def finish(self):
        for row in self.db.execute('SELECT place_id FROM leg_membership_review WHERE status="conflict"').fetchall():
            detail=[dict(r) for r in self.db.execute('SELECT d.jurisdiction,d.designation,s.path,m.scope,m.locator FROM leg_memberships m JOIN leg_districts d ON d.id=m.leg_id JOIN sources s ON s.id=m.source_id WHERE m.place_id=?',(row[0],))]
            self.issue('leg_membership_conflict',row[0],None,'membership_review',detail)
        for row in self.db.execute("SELECT name_key,parent_id,COUNT(DISTINCT level) n FROM places WHERE level IN ('city','municipality','locality') GROUP BY name_key,parent_id HAVING n>1").fetchall():
            self.issue('locality_type_conflict',uid(row[0],row[1]),None,'places',dict(row))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=OUT/'philippine_locations.sqlite');parser.add_argument('--with-gaa',action='store_true',help='Include local FY2020–FY2026 historical GAA name evidence');args=parser.parse_args()
    temp=args.output.with_suffix('.building.sqlite')
    if temp.exists():temp.unlink()
    con=sqlite3.connect(temp);con.row_factory=sqlite3.Row;con.executescript((OUT/'schema.sql').read_text())
    con.execute('INSERT INTO meta VALUES(?,?)',('schema_version','1'))
    b=Builder(con)
    def import_if(path,method,*extra):
        path=Path(path)
        if path.exists():
            print('Importing',path.name,flush=True);method(path,*extra)
        else:b.source(path,'unavailable_local_source','missing','missing','Not available in the current workspace; no external lookup.')
    import_if(DATA/'unified_locations.json',b.unified)
    import_if(ODV/'city_barangays_mapping.json',b.hierarchy)
    import_if(ODV/'database/philippine_locations.json',b.geo_database)
    for path in sorted(DATA.glob('*.geo.json')):b.geo_file(path)
    for name in ['philippines-provinces.json','philippines-regions.json','philippines_regions.geojson']:import_if(DATA/name,b.geo_file)
    for name in ['province_cities_mapping.json','province_cities_mapping_geojson.json']:import_if(DATA/name,b.mapping)
    import_if(ODV/'metropolitan-manila-cities.json',b.metro_aliases)
    import_if(ROOT/'build_rcs_analysis.py',b.rainfall_codes)
    import_if(DATA/'20th_congress_representatives.json',b.roster)
    for name,family,generated in [('districts_generated.json','election_generated',True),('districts.json','compiled_districts',False),('districts.json.wiki-backup','compiled_districts',False),('districts.json.pre-cities-backup','compiled_districts',False),('barmm_overrides.json','manual_barmm_overrides',False)]:
        import_if(DATA/name,b.district_maps,family,generated)
    import_if(DATA/'congressmen_consolidated.json',b.historical_reps)
    import_if(ODV/'static/nep-preview/congress.html',b.deo_crosswalk,ROOT/'DPWH per district.pdf')
    import_if(ROOT/'hb10858_3rd_dpwh_projects.json',b.office_observations)
    import_if(ROOT/'2027.json',b.office_observations,'NEP')
    if (ROOT/'analysis_output/butuan_congress_location_edge_cases.json').exists():
        b.edge_cases(ROOT/'analysis_output/butuan_congress_location_edge_cases.json')
    for name in ['unified_locations.parquet','unified_locations.duckdb']:
        b.source(DATA/name,'unified_locations','duplicate_serialization','not_reimported','JSON representation imported; these serializations are not independent evidence.')
    for name in ['dpwh_annex_a5_district_cache.json','congressman-ranking.json','top-200-congressmen.json']:
        b.source(DATA/name,'derived_project_rankings','derived_project_matching','reference_only','Derived matches/rankings are not administrative boundary evidence.')
    from apply_spelling_decisions import apply as apply_spelling
    apply_spelling(con)
    if args.with_gaa:
        from import_gaa_names import ingest
        ingest(b)
    from refine_database import refine
    refine(con)
    b.finish();con.commit()
    # Integrity checks are part of the build; publication is atomic.
    if con.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Foreign key integrity failure')
    if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failure')
    summary={'schemaVersion':1,'database':str(args.output),'placesByLevel':dict(con.execute('SELECT level,COUNT(*) FROM places GROUP BY level').fetchall()),'counts':{},'issuesByKind':dict(con.execute('SELECT kind,COUNT(*) FROM issues GROUP BY kind').fetchall()),'limitations':['All imported geography and boundaries are source claims, not newly verified official boundaries.','Unknown dates stay NULL; historical records do not establish current membership.','Derived datasets and backups do not establish independent corroboration.','No budget ranking or public ODV page was regenerated from this database.']}
    for table in ['sources','aliases','leg_districts','leg_memberships','representatives','representative_terms','deos','deo_leg_claims','observations','issues']:
        summary['counts'][table]=con.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    summary['sources']=[dict(r) for r in con.execute('SELECT path,family,kind,disposition,note FROM sources ORDER BY path')]
    con.execute('PRAGMA optimize');con.close();os.replace(temp,args.output)
    (OUT/'build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['sources','limitations']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
