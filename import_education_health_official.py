#!/usr/bin/env python3
"""Extract retained official facility sources into an auditable site ledger."""
import hashlib,json,re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'data_sources/education_health_official'
OUT=ROOT/'analysis_output'
class Tables(HTMLParser):
    def __init__(self):
        super().__init__();self.depth=0;self.cell=None;self.row=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.depth+=1
        if self.depth and tag=='tr':self.row=[]
        if self.depth and tag in ('td','th'):self.cell=[]
        if self.cell is not None and tag=='br':self.cell.append(' ')
    def handle_data(self,data):
        if self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:self.row.append(' '.join(''.join(self.cell).split()));self.cell=None
        if tag=='tr' and self.depth and self.row:self.rows.append(self.row)
        if tag=='table':self.depth-=1

def norm(s):
    s=s.casefold().replace('sto.','santo').replace('sta.','santa')
    return ' '.join(re.findall(r'[a-z0-9]+',s))
def build():
    path=SOURCE/'qc-evacuation.html';parser=Tables();parser.feed(path.read_text())
    places={r['code']:r for r in map(json.loads,(ROOT/'data_sources/bettergov-psgc-locations.jsonl').read_text().splitlines())}
    barangays={norm(r['name']):r['code'] for r in places.values() if r.get('parent_code')=='1381300000' and r['level']=='barangay'}
    aliases={'n s amoranto':'n s amoranto salvacion','santa cruz':'santa cruz','e rodriguez':'e rodriguez','duyan duyan':'duyan duyan','bagong pag asa':'bagong pag asa','st ignatius':'saint ignatius'}
    records=[];seen=set();duplicates=[]
    for row in parser.rows:
        if len(row)!=4 or row[0].casefold()=='barangay':continue
        brgy,name,address,kind=row
        if not name:continue
        identity=(norm(brgy),norm(name))
        if identity in seen:duplicates.append(row);continue
        seen.add(identity)
        key=norm(brgy);key=aliases.get(key,key)
        records.append({'id':f'qc-evacuation:{len(records)+1:04d}','category':'evacuation','name':name,'address':address,'siteType':kind,'barangayAsPublished':brgy,'barangayPsgc':barangays.get(key),'municipalityPsgc':'1381300000','sourceUrl':'https://quezoncity.gov.ph/qcitizen-guides/quezon-city-evacuation-centers/','source':'Quezon City government evacuation-site directory','retrievedDate':'2026-11-12'})
    payload={'sourceSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'records':records,'audit':{'extractedRows':len(records)+len(duplicates),'uniqueSites':len(records),'duplicateRowsExcluded':len(duplicates),'unmatchedBarangays':dict(Counter(r['barangayAsPublished'] for r in records if not r['barangayPsgc'])),'siteTypes':dict(Counter(r['siteType'] for r in records)),'coverage':'Quezon City only. Designated evacuation sites, including temporary and semi-permanent sites; not a count of dedicated buildings.'}}
    (OUT/'education-health-official-sites.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(payload['audit'],ensure_ascii=False,indent=2))
if __name__=='__main__':build()
