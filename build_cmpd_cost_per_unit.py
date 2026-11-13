#!/usr/bin/env python3
"""Build CMPD office-level rates and match POW bill candidates."""
import csv,json,re,hashlib
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent; OUT=ROOT/'analysis_output'; STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
POW=OUT/'dpwh-in-depth-data.json'; SOURCE=ROOT/'data_sources/CMPD GLOBAL 1ST SEM CY 2026.csv'

def number(value):
 value=str(value or '').strip()
 try:return float(value) if value else None
 except ValueError:return None

def rates():
 grouped=defaultdict(list); materials=[]; office_names=set(); regions=set(); priced=0; unpriced=0
 required={'region_code','region_name','implementing_office','material_code','material_description','unit','price','price_status','price_category','price_source','regional_average_price','material_notes','source_row'}
 with SOURCE.open(encoding='utf-8-sig',newline='') as stream:
  reader=csv.DictReader(stream)
  missing=required-set(reader.fieldnames or [])
  if missing:raise ValueError(f'CMPD CSV is missing required columns: {sorted(missing)}')
  for row in reader:
   code=row['material_code'].strip()
   if not code:continue
   amount=number(row['price']); office_names.add(row['implementing_office'].strip()); regions.add(row['region_code'].strip())
   priced+=amount is not None; unpriced+=amount is None
   grouped[code].append({'code':code,'description':row['material_description'].strip(),'unit':row['unit'].strip(),
       'groupCode':row['material_group_code'].strip(),'group':row['material_group'].strip(),
       'average':amount,'region':row['region_code'].strip(),'regionName':row['region_name'].strip(),
       'office':row['implementing_office'].strip(),'regionalAverage':number(row['regional_average_price']),
       'priceStatus':row['price_status'].strip() or None,'priceCategory':row['price_category'].strip() or None,
       'priceSource':row['price_source'].strip() or None,'notes':row['material_notes'].strip() or None,
       'sourceRow':row['source_row'].strip() or None})
 for code,items in grouped.items():
  first=items[0]
  materials.append({'code':code,'description':first['description'],'unit':first['unit'],
                    'groupCode':first['groupCode'],'group':first['group'],
                    'rowCount':len(items),'pricedRows':sum(item['average'] is not None for item in items),
                    'regions':sorted({item['region'] for item in items})})
 materials.sort(key=lambda item:(item['description'].casefold(),item['code']))
 return materials,grouped,{'rows':priced+unpriced,'pricedRows':priced,'unpricedRows':unpriced,
                            'implementingOffices':len(office_names),'regions':len(regions),
                            'regionCodes':sorted(regions)}
def norm(s):return re.sub(r'[^a-z0-9]+',' ',str(s or '').lower()).strip()
def main():
 materials,office_rates,coverage=rates(); doc=json.loads(POW.read_text()); candidates=[]
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
 shard_payloads={};shard_names={};rate_payloads={};rate_names={}
 for code,items in office_rates.items():
  content=json.dumps(items,ensure_ascii=False,separators=(',',':'))
  digest=hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
  slug=re.sub(r'[^a-z0-9]+','-',items[0]['description'].lower()).strip('-')[:64]
  name=f'cmpd-cost-per-unit-rate-shards/{slug}-{code.lower().replace(".","-")}-{digest}.json'
  rate_payloads[name]=content;rate_names[code]=name
 for category,items in grouped.items():
  slug=re.sub(r'[^a-z0-9]+','-',category.lower()).strip('-')
  for offset in range(0,len(items),800):
   chunk=items[offset:offset+800]
   content=json.dumps(chunk,ensure_ascii=False,separators=(',',':'))
   digest=hashlib.sha256(content.encode('utf-8')).hexdigest()[:12]
   name=f'cmpd-cost-per-unit-shards/{slug}-{offset//800:02d}-{digest}.json'
   shard_payloads[name]=content
   shard_names.setdefault(category,[]).append(name)
 source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
 data={'source':SOURCE.name,'sourceSha256':source_hash,'referencePeriod':'1st semester · CY 2026',
       'coverage':coverage,'materials':materials,'rateShards':rate_names,'candidateShards':shard_names}
 payloads=list(rate_payloads.values())+list(shard_payloads.values())
 data['version']=hashlib.sha256(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode('utf-8')+'|'.join(payloads).encode('utf-8')).hexdigest()[:12]
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
  rate_dir=target/'cmpd-cost-per-unit-rate-shards';rate_dir.mkdir(exist_ok=True)
  for stale in rate_dir.glob('*.json'):stale.unlink()
  for name,content in rate_payloads.items():
   dest=target/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content,encoding='utf-8')
 print(json.dumps({'officeRates':coverage['rows'],'materials':len(materials),'implementingOffices':coverage['implementingOffices'],'regions':coverage['regions'],'powCandidates':len(candidates),'page':'cmpd-cost-per-unit.html'}))
if __name__=='__main__':main()
