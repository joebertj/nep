#!/usr/bin/env python3
"""Extract visible CMPD rates, match POW bill candidates, and build CMPD page."""
import json,re,hashlib
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'analysis_output'; STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OCR=Path('/tmp/cmpd-vision.json'); POW=OUT/'dpwh-in-depth-data.json'; SOURCE=ROOT/'data_sources/Nationwide CMPD_compressed.pdf'

def rates():
 pages=json.loads(OCR.read_text())['pages'];out=[]
 for p in pages:
  pg=p['page']; region='NCR' if pg<=10 else 'CAR' if 12<=pg<=17 else 'Region I'
  if region=='Region I' and pg>20:continue
  words=p['words']; codes=[w for w in words if w[0]<165 and re.fullmatch(r'M[A-Z0-9]{1,3}\.\d{4}',w[4].replace('ł','1'))]
  for c in codes:
   y=c[1]
   row=[w for w in words if abs(w[1]-y)<8]
   desc=' '.join(w[4] for w in sorted(row,key=lambda w:w[0]) if 175<w[0]<700)
   unit_aliases={'CUM':'CUM','M3':'CUM','M³':'CUM','SQM':'SQM','M2':'SQM','M²':'SQM',
                 'KG':'KG','KGS':'KG','BAG':'BAG','PC':'PC','PCS':'PC','PCI':'PC',
                 'EA':'PC','EACH':'PC','SET':'SET','M':'M','LM':'M','LTR':'LTR',
                 'L':'LTR','GAL':'GAL','NONE':'NONE'}
   unit=next((unit_aliases.get(w[4].strip().upper().strip('.,:;')) for w in sorted(row,key=lambda w:w[0])
              if 700<w[0]<1100 and w[4].strip().upper().strip('.,:;') in unit_aliases),'')
   if not unit and re.search(r'\b40\s*kg\b',desc,re.I):unit='BAG'
   avg=next((w[4] for w in sorted(row,key=lambda w:w[0],reverse=True) if w[0]>2200),'')
   val=re.sub(r'[^0-9.,]','',avg).replace(',','')
   try: amount=float(val)
   except: amount=None
   code=c[4].replace('ł','1')
   if desc:out.append({'code':code,'description':desc,'unit':unit,'average':amount,'region':region,'page':pg})
 # deduplicate OCR same code/page
 seen=set();return [r for r in out if not ((r['code'],r['region']) in seen or seen.add((r['code'],r['region'])))]
def norm(s):return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()
def main():
 refs=rates(); doc=json.loads(POW.read_text()); candidates=[]
 aliases=[('cement concrete pavement',r'\b(?:cement concrete pavement|concrete pavement|pccp)\b'),('asphalt concrete',r'\b(?:asphalt concrete|hot laid asphalt|bituminous concrete)\b'),('aggregate subbase',r'\b(?:aggregate subbase|subbase course)\b'),('aggregate base course',r'\b(?:aggregate base course|base course)\b'),('common borrow',r'\bcommon borrow\b'),('selected borrow',r'\bselected borrow\b'),('reinforcing steel',r'\b(?:reinforcing steel|deformed bars|reinforcing bars)\b'),('portland cement',r'\bportland cement\b'),('ready mix concrete',r'\b(?:ready mix concrete|ready mixed concrete)\b'),('concrete hollow blocks',r'\b(?:concrete hollow block|chb)\b'),('fine aggregate sand',r'\b(?:fine aggregate|concrete sand)\b'),('gravel',r'\bgravel\b')]
 for project in doc['projects']:
  for d in project.get('documents',[]):
   if d.get('kind')!='pow':continue
   for row in d.get('rows',[]):
    desc=row.get('description',''); u=norm(row.get('unit')); txt=norm(desc)
    for label,pat in aliases:
     if re.search(pat,txt):
      unit=('sq.m' if u in ('sq m','sqm','m2') else 'cu.m' if u in ('cu m','cum','m3') else 'kg' if u in ('kg','kgs') else 'm' if u in ('m','lin m','linear m') else row.get('unit') or '—')
      candidates.append({'material':label,'description':desc,'itemCode':row.get('itemCode'),'unit':unit,'unitCost':row.get('calculatedUnitCostPesos') or row.get('printedUnitCostPesos'),'amount':row.get('amountPesos'),'quantity':row.get('quantity'),'project':project.get('name'),'code':project.get('code'),'office':project.get('office'),'region':project.get('region'),'powUrl':d.get('url'),'page':row.get('sourcePage')})
 grouped=defaultdict(list)
 for candidate in candidates:grouped[candidate['material']].append(candidate)
 shard_payloads={};shard_names={}
 for category,items in grouped.items():
  slug=re.sub(r'[^a-z0-9]+','-',category.lower()).strip('-')
  for offset in range(0,len(items),800):
   chunk=items[offset:offset+800]
   content=json.dumps(chunk,ensure_ascii=False,separators=(',',':'))
   digest=hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
   name=f'cmpd-cost-per-unit-shards/{slug}-{offset//800:02d}-{digest}.json'
   shard_payloads[name]=content
   shard_names.setdefault(category,[]).append(name)
 data={'source':SOURCE.name,'referencePeriod':'1st semester · CY 2026','coverage':'Supplied extract includes NCR (pp. 4–10), CAR (pp. 12–17), and only pp. 19–20 of Region I.','rates':refs,'candidateShards':shard_names}
 data['version']=hashlib.sha256(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')+'|'.join(shard_payloads.values()).encode('utf-8')).hexdigest()[:12]
 from report_table_presentation import apply_page as apply_tables, publish_assets
 from uniform_report_menu import apply_page as apply_menu
 page=(ROOT/'project_documents/cmpd-cost-per-unit.html').read_text(encoding='utf-8')
 script=(ROOT/'project_documents/cmpd-cost-per-unit.js').read_text(encoding='utf-8')
 script_version=hashlib.sha256(script.encode()).hexdigest()[:12]
 page=page.replace('</head>',f'<meta name="cmpd-data-version" content="{data["version"]}"></head>')
 page=page.replace('src="cmpd-cost-per-unit.js"',f'src="cmpd-cost-per-unit.js?v={script_version}"')
 page=apply_tables(apply_menu(page,'cmpd-cost-per-unit.html'),publish_assets())
 for target in (OUT,STATIC):
  target.mkdir(parents=True,exist_ok=True)
  (target/'cmpd-cost-per-unit.html').write_text(page,encoding='utf-8')
  (target/'cmpd-cost-per-unit.js').write_text(script,encoding='utf-8')
  (target/'cmpd-cost-per-unit-data.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
  shard_dir=target/'cmpd-cost-per-unit-shards';shard_dir.mkdir(exist_ok=True)
  for stale in shard_dir.glob('*.json'):stale.unlink()
  for name,content in shard_payloads.items():
   dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content,encoding='utf-8')
 print(json.dumps({'rates':len(refs),'powCandidates':len(candidates),'page':'cmpd-cost-per-unit.html'}))
if __name__=='__main__':main()
