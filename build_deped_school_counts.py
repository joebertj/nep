#!/usr/bin/env python3
"""Join DepEd SY2025-26 public school enrollment records to PSGC; retain row-level audit."""
import csv,gzip,hashlib,json,sys
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent; SRC=ROOT/'data_sources/education_health_official/nash-enrollment_panel_2025-26.csv.gz'; OUT=ROOT/'analysis_output'
sys.path.insert(0,str(ROOT));import build_education_health as e

def build():
    digest=hashlib.sha256(SRC.read_bytes()).hexdigest()
    sums=ROOT/'data_sources/education_health_official/nash-CHECKSUMS.sha256'
    expected=next(x.split()[0] for x in sums.read_text().splitlines() if x.endswith(SRC.name.replace('nash-','')))
    if digest!=expected:raise ValueError('DepEd school file checksum mismatch')
    places={r['code']:r for r in (json.loads(x) for x in (ROOT/'data_sources/bettergov-psgc-locations.jsonl').read_text().splitlines() if x.strip())}
    region_alias={'region i':'0100000000','region ii':'0200000000','region iii':'0300000000','region iv a':'0400000000','region iv b':'1700000000','region v':'0500000000','region vi':'0600000000','region vii':'0700000000','region viii':'0800000000','region ix':'0900000000','region x':'1000000000','region xi':'1100000000','region xii':'1200000000','region xiii':'1600000000','car':'1400000000','cordillera administrative region':'1400000000','ncr':'1300000000','national capital region':'1300000000','nir':'1800000000','negros island region':'1800000000','mimaropa':'1700000000','caraga':'1600000000','barmm':'1900000000','armm':'1900000000'}
    region_alias={e.normalize_place(k):v for k,v in region_alias.items()}
    munis=defaultdict(list);brgys=defaultdict(list)
    for p in places.values():
        if p['level'] not in ('municipality','city','sub_municipality'):continue
        chain=[];cur=p
        while cur:chain.append(cur);cur=places.get(cur.get('parent_code'))
        province=next((x for x in chain if x['level']=='province'),{})
        region=next((x for x in chain if x['level']=='region'),{})
        key=(e.normalize_place(p['name']),e.normalize_place(province.get('name')),region.get('code',''))
        munis[key].append((p,province,region))
        if p['level']=='city' and key[0].endswith(' city'):
            munis[(key[0][:-5],key[1],key[2])].append((p,province,region))
        if p['level']=='city' and key[0].endswith(' city'):
            munis[(key[0][:-5],key[1],'')].append((p,province,region))
        for b in places.values():
            if b['level']=='barangay' and b.get('parent_code')==p['code']:
                brgys[(p['code'],e.normalize_place(b['name']))].append(b)
    aliases={'negros':'negros','mindoro':'mindoro','maguindanao':'maguindanao','agusan':'agusan','misamis':'misamis','ilocos':'ilocos','camarines':'camarines'}
    rows=[];seen=set();unmatched=Counter();by_method=Counter();source_enrollment_total=0;source_enrollment_rows=0
    with gzip.open(SRC,'rt',newline='',encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            if r.get('sector','').strip().casefold()!='public':continue
            sid=r['school_id'].strip()
            if not sid or sid in seen:continue
            seen.add(sid)
            if r.get('enrol_total','').strip():
                source_enrollment_total += int(float(r['enrol_total']))
                source_enrollment_rows += 1
            mn=e.normalize_place(r.get('municipality'));pn=e.normalize_place(r.get('province'));rn=region_alias.get(e.normalize_place(r.get('region')),'')
            candidates=munis.get((mn,pn,rn),[]) if rn else []
            method='municipality-province-region'
            if len(candidates)!=1 and rn:
                fam=next((v for k,v in aliases.items() if k in pn.split()),[])
                if fam:candidates=[t for k,v in munis.items() if k[0]==mn and k[2]==rn and fam in k[1].split() for t in v];method='unique-municipality-province-family-region'
            if len(candidates)!=1:
                candidates=[t for k,v in munis.items() if k[0]==mn and k[2]==rn and len(k[1])>0 for t in v]
                if len(candidates)==1:method='unique-municipality-region'
            if len(candidates)!=1:
                candidates=[t for k,v in munis.items() if k[0]==mn and k[1]==pn for t in v];method='unique-municipality-province'
            if len(candidates)!=1 and rn:
                candidates=[t for k,v in munis.items() if k[0]==mn and k[2]==rn for t in v]
                if len(candidates)==1:method='unique-municipality-region'
            if len(candidates)!=1:
                unmatched['municipality']+=1;continue
            m,prov,reg=candidates[0]
            bk=(m['code'],e.normalize_place(r.get('barangay')));bs=brgys.get(bk,[])
            b=bs[0] if len(bs)==1 else None
            if b is None:unmatched['barangay']+=1
            else:by_method['barangay matched']+=1
            by_method[method]+=1
            enrollment=r.get('enrol_total','').strip()
            rows.append({'schoolId':sid,'schoolName':r.get('school_name',''),'enrollment':int(float(enrollment)) if enrollment else None,'regionCode':reg['code'],'provinceCode':prov.get('code',''),'municipalityCode':m['code'],'barangayCode':b['code'] if b else None,'sourceRegion':r.get('region'),'sourceProvince':r.get('province'),'sourceMunicipality':r.get('municipality'),'sourceBarangay':r.get('barangay'),'matchMethod':method if b else method+'; barangay unresolved'})
    result={'source':'DepEd enrollment panel SY 2025-26, distributed by NASH Reviewer; underlying school records from DepEd public datasets','sourceUrl':'https://nash.com.ph/blog/download-cleaned-deped-school-data','sha256':digest,'publicSchoolRows':len(seen),'reportedEnrollmentRows':source_enrollment_rows,'publicEnrollmentTotal':source_enrollment_total,'municipalityMatched':len(rows),'barangayMatched':sum(x['barangayCode'] is not None for x in rows),'unmatched':dict(unmatched),'joinMethods':dict(by_method),'records':rows}
    (OUT/'education-health-deped-schools.json').write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))
if __name__=='__main__':build()
