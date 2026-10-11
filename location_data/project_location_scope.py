"""Veto explicit conflicting qualified locations; never infer identity from similarity."""
import re
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path
ROOT=Path(__file__).resolve().parent
from location_data.location_text import geographic_title,place_key,barangay_key
from location_data.build_database import norm

_DB=None
@lru_cache(maxsize=None)
def lookup(name,parent=None,levels=()):
    global _DB
    if _DB is None:
        _DB=sqlite3.connect((ROOT/'philippine_locations.sqlite').as_uri()+'?mode=ro',uri=True);_DB.row_factory=sqlite3.Row
    rows=_DB.execute('SELECT DISTINCT p.id,p.name,p.parent_id,p.level FROM aliases a JOIN places p ON p.id=a.place_id WHERE a.name_key=?',(norm(name).strip(' .'),))
    return tuple(dict(r) for r in rows if (parent is None or r['parent_id']==parent) and (not levels or r['level'] in levels))

@lru_cache(maxsize=None)
def qualified(title):
    text,_=geographic_title(title);fields=[f.strip(' .') for f in text.split(',')]
    if len(fields)<2:return None
    provinces=lookup(fields[-1],levels=('province',))
    if not provinces:return None
    pkeys={place_key(r['name']) for r in provinces}
    if len(pkeys)!=1:return None
    municipalities=[]
    for p in provinces:municipalities.extend(lookup(re.sub(r'^municipality of\s+','',fields[-2]),p['id'],('municipality','locality','city')))
    if not municipalities:return {'province':pkeys,'municipality':set(),'barangay':set()}
    towns={place_key(r['name']) for r in municipalities}
    markers=list(re.finditer(r'\b(?:barangay|brgy\.?|bgy\.?)\s+([^,;()]+)',','.join(fields[:-2])))
    barangays=set()
    # Multiple marked locations or route endpoints need scope review, not a
    # single-barangay veto inferred from the last endpoint.
    marker_count=len(re.findall(r'\b(?:barangay|brgy\.?|bgy\.?)\s+',','.join(fields[:-2])))
    if len(markers)==1 and marker_count==1:
        name=markers[0][1].strip(' .')
        # An explicitly marked complete field is location evidence even when
        # the local barangay inventory is incomplete. Compound routes stay out.
        if not re.search(r'\b(?:to|and|road|bridge|section|fmr|system|school|phase)\b|[/&]|\bsta\.?\s*\d',name):barangays.add(barangay_key(name))
        for town in municipalities:
            for r in lookup(name,town['id'],('barangay',)):barangays.add(barangay_key(r['name']))
            for prefix in ['Barangay ','Brgy. ']:
                for r in lookup(prefix+name,town['id'],('barangay',)):barangays.add(barangay_key(r['name']))
    return {'province':pkeys,'municipality':towns,'barangay':barangays}

def possible_spelling(a,b):
    # An abbreviation can prevent a veto; it never establishes a project match.
    def key(value):
        value=re.sub(r'^sto\.?\s+','santo ',re.sub(r'^sta\.?\s+','santa ',value))
        return re.sub(r'[^\w]+',' ',value).strip()
    return any(key(x)==key(y) for x in a for y in b)

def location_conflict(left,right):
    a,b=qualified(left),qualified(right)
    if not a or not b:return False
    for level in ['province','municipality','barangay']:
        if a[level] and b[level] and not (a[level]&b[level]) and not possible_spelling(a[level],b[level]):return True
    return False
