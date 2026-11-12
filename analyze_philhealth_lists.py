#!/usr/bin/env python3
"""Extract PhilHealth accredited hospital and YAKAP PDFs and join records to PSGC."""
import json,re,sys,hashlib
from collections import Counter,defaultdict
from pathlib import Path
import pymupdf
ROOT=Path(__file__).resolve().parent; SRC=ROOT/'data_sources/education_health_official'; OUT=ROOT/'analysis_output'
sys.path.insert(0,str(ROOT));import build_education_health as e
PLACES={r['code']:r for r in (json.loads(x) for x in (ROOT/'data_sources/bettergov-psgc-locations.jsonl').read_text().splitlines() if x.strip())}
REGION_ALIAS={e.normalize_place(k):v for k,v in {'region i':'0100000000','region ii':'0200000000','region iii':'0300000000','region iv a':'0400000000','region iv b':'1700000000','region v':'0500000000','region vi':'0600000000','region vii':'0700000000','region viii':'0800000000','region ix':'0900000000','region x':'1000000000','region xi':'1100000000','region xii':'1200000000','region xiii':'1600000000','car':'1400000000','cordillera administrative region':'1400000000','ncr':'1300000000','national capital region':'1300000000','nir':'1800000000','negros island region':'1800000000','mimaropa':'1700000000','caraga':'1600000000','barmm':'1900000000','armm':'1900000000','caraga region':'1600000000','national capital region & rizal':'1300000000','bangsamoro autonomous region of muslim mindanao':'1900000000'}.items()}
PROVINCES=defaultdict(list);MUNICIPALITIES=defaultdict(list)
for p in PLACES.values():
 if p['level']=='province':
  PROVINCES[e.normalize_place(p['name'])].append(p)
  PROVINCES[e.normalize_place('province of '+p['name'])].append(p)
  PROVINCES[e.normalize_place(p['name']+' province')].append(p)
 if p['level'] in {'municipality','city','sub_municipality'}:MUNICIPALITIES[e.normalize_place(p['name'])].append(p)
PROVINCES[e.normalize_place('western samar')].extend(PROVINCES[e.normalize_place('samar (western samar)')])
PROVINCES[e.normalize_place('north cotabato')].extend(PROVINCES[e.normalize_place('cotabato')])

def extract(filename,kind):
 path=SRC/filename; pdf=pymupdf.open(path); rows=[];current_region='';current_province=''
 for page_no,page in enumerate(pdf):
  words=page.get_text('words'); lines=defaultdict(list)
  for w in words:lines[round(w[1])].append(w)
  events=[]
  for y,ws in lines.items():
   ws.sort(key=lambda w:w[0]); left=[w for w in ws if w[0]<270]
   if not left:continue
   first=left[0]
   if first[0]<40 and re.fullmatch(r'\d+',first[4]) and y>70:
    events.append((y,'row',int(first[4])))
   elif first[0]<28 and y>70:
    heading=' '.join(w[4] for w in left)
    events.append((y,'heading',heading))
  events.sort()
  starts=[(y,n) for y,t,n in events if t=='row']
  for ei,(y,typ,val) in enumerate(events):
   if typ=='heading':
    h=e.normalize_place(val)
    if h in REGION_ALIAS:current_region=REGION_ALIAS[h];current_province=''
    elif len(PROVINCES.get(h,[]))==1:current_province=PROVINCES[h][0]['code']
    continue
   next_y=next((event[0] for event in events[ei+1:]),9999)
   span=[w for w in words if y-1<=w[1]<next_y-1]
   # Remove the page footer and only retain this row's printed columns.
   name_max=245
   name=' '.join(w[4] for w in sorted(span,key=lambda w:(round(w[1]),w[0])) if 35<=w[0]<name_max and not re.fullmatch(r'\d+',w[4]) and not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',w[4]))
   if kind=='hospitals':
    municipality=' '.join(w[4] for w in sorted(span,key=lambda w:(round(w[1]),w[0])) if 790<=w[0]<930 and not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',w[4]))
    street=' '.join(w[4] for w in sorted(span,key=lambda w:(round(w[1]),w[0])) if 600<=w[0]<790)
    sec=''.join(w[4] for w in span if w[0]>=980 and w[4] in {'G','P'})
    beds=next((int(w[4]) for w in span if 260<=w[0]<291 and w[4].isdigit()),None)
    cat=' '.join(w[4] for w in span if 290<=w[0]<325 and w[4] in {'LEVEL','INF/DISP','1','2','3'})
   else:
    municipality=' '.join(w[4] for w in sorted(span,key=lambda w:(round(w[1]),w[0])) if 615<=w[0]<715 and not re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',w[4]))
    street=' '.join(w[4] for w in sorted(span,key=lambda w:(round(w[1]),w[0])) if 470<=w[0]<615)
    sec=''.join(w[4] for w in span if w[0]>=760 and w[4] in {'G','P'})
    beds=None;cat=''
   if not name or sec not in {'G','P'}:continue
   municipality=re.sub(r'\s+',' ',municipality).strip();street=re.sub(r'\s+',' ',street).strip()
   # Add a unique municipality/region record only; otherwise leave unmatched.
   mn=e.normalize_place(municipality); candidates=[];join_method='unresolved'
   if current_province:
    candidates=[p for p in MUNICIPALITIES.get(mn,[]) if p.get('parent_code')==current_province]
   if len(candidates)==1:join_method='municipality-province'
   if len(candidates)!=1 and current_region:
    candidates=[p for p in MUNICIPALITIES.get(mn,[]) if next((a['code'] for a in ancestors(p) if a.get('level')=='region'), '')==current_region]
    if len(candidates)==1:join_method='unique-municipality-region'
   if len(candidates)!=1:
    candidates=MUNICIPALITIES.get(mn,[])
    if len(candidates)==1:join_method='unique-municipality-national'
   place=candidates[0] if len(candidates)==1 else None
   province=ancestor(place,'province') if place else None;region=ancestor(place,'region') if place else None
   rows.append({'sourceIndex':val,'name':name,'municipality':municipality,'street':street,'ownership':'government' if sec=='G' else 'private','beds':beds,'category':cat,'regionCode':region['code'] if region else current_region or None,'provinceCode':province['code'] if province else current_province or None,'municipalityCode':place['code'] if place else None,'joinMethod':join_method if place else 'unresolved','page':page_no+1})
 return rows

def ancestors(p):
 c=p
 while c:
  yield c;c=PLACES.get(c.get('parent_code'))
def ancestor(p,level):return next((x for x in ancestors(p) if x.get('level')==level),None)

def summarize(rows):
 unique={(e.normalize_place(r['name']),r['municipalityCode'],e.normalize_place(r.get('street'))) for r in rows if r['municipalityCode']}
 gov=[r for r in rows if r['ownership']=='government']
 gov_unique={(e.normalize_place(r['name']),r['municipalityCode'],e.normalize_place(r.get('street'))):r for r in gov if r['municipalityCode']}
 return {'sourceRows':len(rows),'distinctJoinedFacilities':len(unique),'governmentRows':len(gov),'privateRows':len(rows)-len(gov),'governmentUniqueJoined':len(gov_unique),'governmentUnmatchedRows':sum(not r['municipalityCode'] for r in gov),'allUniqueJoined':len(unique),'unmatchedRows':sum(not r['municipalityCode'] for r in rows),'governmentBeds':sum(r['beds'] or 0 for r in gov) if rows and rows[0].get('beds') is not None else None,'governmentBedsJoined':sum(r['beds'] or 0 for r in gov_unique.values()) if rows and rows[0].get('beds') is not None else None,'joinRate':round(sum(bool(r['municipalityCode']) for r in rows)*100/max(1,len(rows)),1)}

def build():
 specs={'hospitals':('philhealth-hospitals-infirmaries-2026-09-30.pdf','hospitals'),'yakap':('philhealth-yakap-2026-09-30.pdf','yakap')};result={}
 for key,(file,kind) in specs.items():
  rows=extract(file,kind);result[key]={'source':'PhilHealth Accredited Health Facilities, updated 30 September 2026','sourceUrl':'https://www.philhealth.gov.ph/partners/providers/facilities/accredited/','downloadUrl':{'hospitals':'https://www.philhealth.gov.ph/partners/providers/facilities/accredited/HOSP_093026.pdf','yakap':'https://www.philhealth.gov.ph/partners/providers/facilities/accredited/YAKAP.pdf'}[key],'sha256':hashlib.sha256((SRC/file).read_bytes()).hexdigest(),'summary':summarize(rows),'records':rows}
 print(json.dumps({k:v['summary'] for k,v in result.items()},indent=2))
 (OUT/'education-health-philhealth.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
if __name__=='__main__':build()
