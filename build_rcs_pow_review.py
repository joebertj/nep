#!/usr/bin/env python3
"""Build the active RCS page from parsed NEP POW evidence."""
import html
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ODV=ROOT.parent/'open-data-visualization'
STATIC=ODV/'static/nep-preview'
DATA=ROOT/'analysis_output/dpwh-in-depth-data.json'

ALLOCATION=4_200_000

def bill_key(value):
    import unicodedata, re
    text=unicodedata.normalize('NFKD',str(value or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',text).strip()

def unit_key(value):
    import re
    text=str(value or '').lower().replace('²','2').replace('³','3')
    text=re.sub(r'[^a-z0-9]+',' ',text).strip()
    return {'kgs':'kg','kilogram':'kg','kilograms':'kg','cubic meter':'cu m','cubic meters':'cu m','m3':'cu m',
            'sq m':'sq m','sqm':'sq m','square meter':'sq m','square meters':'sq m','m2':'sq m',
            'ls':'lump sum','l s':'lump sum','sum':'lump sum','lump':'lump sum','lumpsum':'lump sum',
            'ea':'each','unit':'each'}.get(text,text)

def read_unit_cost_bills():
    source=json.loads(DATA.read_text())
    merges=source.get('powBillMerges') or {}
    labels=source.get('powBillLabels') or {}
    bill_data={}
    projects=[p for p in source.get('projects',[])
              if 'rainwater collector system' in p.get('name','').lower()
              and round(float(p.get('allocationPesos') or 0))==ALLOCATION]
    for project in projects:
        doc=next((d for d in project.get('documents',[])
                  if d.get('kind')=='pow' and d.get('rows')),None)
        if not doc: continue
        grouped={}
        for row in doc.get('rows',[]):
            if row.get('costBasis')!='as_submitted' or not row.get('description'):
                continue
            unit=unit_key(row.get('unit'))
            amount=row.get('amountPesos'); quantity=row.get('quantity')
            if not unit or amount is None or quantity is None or float(quantity)<=0:
                continue
            printed=bill_key(row['description'])
            merged=merges.get(printed,printed)
            key=merged+'|'+unit
            item=grouped.setdefault(key,{'key':key,'merged':merged,'labels':set(),'unit':unit,
                'amount':0.0,'quantity':0.0,'pages':set(),'url':doc.get('url','')})
            item['labels'].add(str(row['description']).strip())
            item['amount']+=float(amount); item['quantity']+=float(quantity)
            if row.get('sourcePage'): item['pages'].add(int(row['sourcePage']))
        for key,item in grouped.items():
            if item['quantity']<=0: continue
            bill=bill_data.setdefault(key,{'key':key,'label':labels.get(item['merged']) or sorted(item['labels'])[0],
                'unit':item['unit'],'projects':{}})
            bill['projects'][project['code']]={'code':project['code'],'name':project.get('name',''),
                'office':project.get('office',''),'region':project.get('region',''),
                'unitCost':item['amount']/item['quantity'],'amount':item['amount'],'quantity':item['quantity'],
                'pages':sorted(item['pages']),'url':item['url']}
    output=[]
    for bill in bill_data.values():
        bill['rows']=sorted(bill.pop('projects').values(),key=lambda x:(-x['unitCost'],x['name']))
        bill['rows']= [r for r in bill['rows'] if r['unitCost']>0]
        if bill['rows']: output.append(bill)
    return sorted(output,key=lambda x:(-len(x['rows']),x['label'].lower(),x['unit']))

def esc(value):
    return html.escape(str(value if value is not None else ''),quote=True)

def money(value, cents=False):
    return '₱'+format(float(value),',.2f' if cents else ',.0f')

def read_evidence():
    source=json.loads(DATA.read_text())
    output=[]
    projects=sorted((p for p in source.get('projects',[])
                     if 'rainwater collector system' in p.get('name','').lower()
                     and round(float(p.get('allocationPesos') or 0))==ALLOCATION),
                    key=lambda p:(p.get('office',''),p.get('code','')))
    if not projects:
        raise RuntimeError('No ₱4.2M Rainwater Collector System projects found')
    for project in projects:
        code=project.get('code','')
        docs=[d for d in project.get('documents',[]) if d.get('kind')=='pow']
        doc=next((d for d in docs if d.get('url')),None)
        links=project.get('documentLinks') or []
        pow_link=next((x.get('url') for x in links
                       if isinstance(x,dict) and str(x.get('type','')).strip().lower()=='pow' and x.get('url')),None)
        pow_url=(doc or {}).get('url') or pow_link
        rows=(doc or {}).get('rows',[])
        facts=(doc or {}).get('summaryMetadata',{}).get('qualitativeFacts',[])
        declared_site_count=next((int(f['value']) for f in facts
                                  if f.get('kind')=='declared_count'
                                  and str(f.get('label','')).lower().rstrip('s')=='site'
                                  and str(f.get('value','')).isdigit()),None)
        submitted=[r for r in rows if r.get('costBasis')=='as_submitted' and r.get('amountPesos') is not None]
        contexts=set()
        for row in rows:
            for context in row.get('componentContexts') or []:
                if context: contexts.add(context.strip())
            if row.get('componentContext'):
                contexts.add(row['componentContext'].strip())
        grouped={}
        for row in submitted:
            description=str(row.get('description') or '').strip()
            if not description: continue
            item=grouped.setdefault(description,{'amount':0.0,'quantity':0.0,'units':set(),'pages':set(),'rows':0})
            item['amount']+=float(row['amountPesos'])
            if row.get('quantity') is not None:item['quantity']+=float(row['quantity'])
            if row.get('unit'):item['units'].add(str(row['unit']).strip())
            if row.get('sourcePage'):item['pages'].add(int(row['sourcePage']))
            item['rows']+=1
        description,leading=max(grouped.items(),key=lambda pair:(pair[1]['amount'],pair[0])) if grouped else ('',{})
        output.append({
            'code':code,'name':project.get('name',''),'office':project.get('office',''),
            'allocation':float(project.get('allocationPesos') or 0),'contexts':sorted(contexts),
            'item':description,'amount':leading.get('amount',0),'quantity':leading.get('quantity',0),
            'units':sorted(leading.get('units',set())),'rowCount':leading.get('rows',0),
            'pages':sorted(leading.get('pages',set())),'powUrl':pow_url,
            'unitMissing':not leading.get('units'),'powParsed':bool(submitted),
            'declaredSiteCount':declared_site_count,
        })
    return sorted(output,key=lambda row:(-max(len(row['contexts']),row['declaredSiteCount'] or 0),row['office'],row['code']))

def render(rows):
    header='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rainwater Collector System · POW scope review</title>
<style>
*{box-sizing:border-box}body{margin:0}main{box-sizing:border-box;width:100%;max-width:none;margin:0;padding:24px clamp(16px,2vw,32px)}.card{background:#fff;border:1px solid #d9e3e1;border-radius:14px;padding:22px;margin:22px 0}.lead{border-left:5px solid #b65b09;background:#fff8e9}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.94rem}th,td{text-align:left;vertical-align:top;padding:11px;border-bottom:1px solid #d9e3e1}th{background:#edf3f2}.money{white-space:nowrap;font-variant-numeric:tabular-nums}details{margin-top:7px}summary{cursor:pointer;color:#096f72;font-weight:700}.source a{font-weight:700}.note{color:#536873}.facility-list{margin:.5rem 0;padding-left:1.2rem}.tag{display:inline-block;padding:3px 8px;border-radius:999px;background:#fff0d4;color:#754500;font-weight:700;font-size:.82rem}@media(max-width:720px){main{padding:12px}table{min-width:720px}}
.rcs-unit-controls{display:flex;flex-wrap:wrap;align-items:end;gap:12px;margin:16px 0}.rcs-unit-controls label{display:grid;gap:5px;font-weight:650}.rcs-unit-controls select,.rcs-unit-controls input,.rcs-unit-controls button{min-height:40px;padding:8px 10px;border:1px solid #9bb8bf;border-radius:7px;background:white;color:inherit;font:inherit}.rcs-box-wrap svg{display:block;width:100%;height:auto}.rcs-box-grid{stroke:#d8e5e8;stroke-dasharray:3 4}.rcs-box-axis,.rcs-box-whisker,.rcs-box-cap{stroke:#536c76;stroke-width:1.5}.rcs-box-shape{fill:#d9eee9;fill-opacity:.62;stroke:#147d73;stroke-width:2}.rcs-box-median{stroke:#00246A;stroke-width:3}.rcs-box-observation{fill:#087e78;fill-opacity:.68;stroke:white;stroke-width:.35}.rcs-box-outlier{fill:#b65b09;fill-opacity:.96;stroke:white;stroke-width:.7}.rcs-box-tick,.rcs-box-summary{font-size:12px;fill:#526c78}.rcs-unit-pager{display:flex;align-items:center;gap:10px;margin-top:14px}.rcs-unit-pager span{margin-right:auto}
</style></head><body class="bettergov-research"><header><div class="eyebrow">FY2027 NEP · DPWH · Rainwater Collector System</div><h1>RCS · POW scope review</h1><p>Same proposed allocation, differing documented schools, buildings, and leading POW items.</p></header><main>'''
    from report_hero_module import STYLE as HERO_STYLE,hero as shared_hero
    lead=shared_hero('FY2027 NEP · DPWH · RCS', '199', 'district-office projects share one scheduled allocation', '₱4.2M', 'per project in the schedule', [
        ('Davao City POW examples','6 vs 14','named school sites'),
        ('Davao del Sur POW','₱3.89M','parsed tank line · 92.7% of allocation'),
    ], 'Different scopes and repeated allocations create a reason to compare the engineering estimates; they do not establish padding or wrongdoing.')
    parsed_count=sum(1 for r in rows if r['powParsed'])
    body=f'''<aside id="report-evidence-notice" class="report-disclaimer" role="note"><strong>Evidence limits.</strong> These are proposed allocations and machine-extracted POW entries, not verified spending. Parsed line totals and site contexts should be checked against each cited page. Different facility counts and identical budget amounts create a review lead; they do not by themselves establish padding, intent, or wrongdoing. The table includes all {len(rows)} projects scheduled at ₱4.2M; POW line details are currently extracted for {parsed_count}, and missing details are marked as not established.</aside>
<section class="card lead"><span class="tag">Priority review lead</span><h2>Was each POW priced from its actual scope, or shaped around a fixed per-office amount?</h2><p>Six and fourteen named school sites both sit under ₱4.2M allocations. A separate POW has a parsed 30-tank line worth about 92.7% of its allocation, while the unit and site count are not established in the extraction. The spread makes the repeated amount harder to explain from the schedule alone and warrants checking the engineering estimates, quantities, standard design, and any per-office cap. It is not proof that costs were added to exhaust a budget.</p></section>
<section class="card"><h2>POW buildings · same allocation, differing scopes and leading items</h2><p class="note">This exhaustive list covers every ₱4.2M Rainwater Collector System project in the in-depth dataset. Facility names and leading line items appear where extracted; “Not established” means the cached POW data does not currently support the detail. Open each POW link to review the source.</p><div class="tablewrap"><table><thead><tr><th>Project / office</th><th>Named schools or buildings</th><th>Leading extracted POW item</th><th>Project allocation</th><th>Evidence</th></tr></thead><tbody>'''
    for r in rows:
        scope=(f'<strong>{len(r["contexts"])} named facilities</strong>' if r['contexts'] else '<strong>Not established</strong><br><span class="note">No named facility contexts extracted</span>')
        if not r['contexts'] and r.get('declaredSiteCount'):
            scope=(f'<strong>No specific school/buildings mentioned in POW</strong><br>'
                   f'<span class="note">POW states {r["declaredSiteCount"]} sites; no site breakdown</span>')
        if r['contexts']:
            scope+=f'<details><summary>Show {len(r["contexts"])} names</summary><ul class="facility-list">'+''.join(f'<li>{esc(x)}</li>' for x in r['contexts'])+'</ul></details>'
        if r['powParsed']:
            qty=format(r['quantity'],',.0f')
            unit=(', '.join(esc(u) for u in r['units']) if r['units'] else 'unit not parsed')
            share=(r['amount']/r['allocation']*100) if r['allocation'] else 0
            item=f'<strong>{esc(r["item"])}</strong><br>{qty} {unit} · <span class="money">{money(r["amount"],cents=True)}</span> <span class="note">({share:.1f}% of allocation; extracted)</span>'
        else:
            item='<strong>Not established</strong><br><span class="note">No parsed submitted POW line item in the cached data.</span>'
        if r['code']=='2027DPWH-Proposal-00296':
            item+='<br><span class="note">14 per-school lines · 6 sets each</span>'
        if r['code']=='2027DPWH-Proposal-00130':
            item+='<br><span class="note">15 extracted line rows for 14 named facilities; reconcile possible duplicate or repeated entries.</span>'
        if r['unitMissing']:
            item+='<br><span class="note">Quantity unit is absent in the parsed row.</span>'
        page=f'#page={r["pages"][0]}' if r['pages'] else ''
        range_text=(f' · pp. {r["pages"][0]}–{r["pages"][-1]}' if len(r['pages'])>1 else (f' · p. {r["pages"][0]}' if r['pages'] else ''))
        evidence=(f'<a href="{esc(r["powUrl"]+page)}" target="_blank" rel="noopener">Open POW{range_text} ↗</a>' if r['powUrl'] else '<span class="note">POW link unavailable</span>')
        body+=f'<tr><td><strong>{esc(r["office"])}</strong><br><span class="note">{esc(r["code"])}</span></td><td>{scope}</td><td>{item}</td><td class="money">{money(r["allocation"])}</td><td class="source">{evidence}</td></tr>'
    body+='''</tbody></table></div></section>
<section class="card"><h2>RCS bills · cost per unit</h2><p class="note">Each plot uses parsed, as-submitted POW amounts divided by quantities, grouped by merged bill label and unit. One point is one project’s combined bill amount ÷ combined quantity. Only the 199 RCS projects at the scheduled ₱4.2M allocation are included; projects without a usable parsed bill are absent. This is a comparison screen, not a market-price or scope-adjusted estimate. Outliers follow the 1.5×IQR rule and are retained.</p><div class="rcs-unit-controls"><label for="rcs-bill-filter">Bill and unit</label><select id="rcs-bill-filter"></select><label for="rcs-project-filter">Find project</label><input id="rcs-project-filter" type="search" placeholder="Project or office"></div><p id="rcs-unit-summary" class="note" aria-live="polite"></p><div id="rcs-unit-boxplot" class="rcs-box-wrap" role="img" aria-label="RCS bill cost per unit box plot"></div><div class="tablewrap"><table><thead><tr><th>Project / office</th><th>Bill unit cost</th><th>Quantity</th><th>Amount</th><th>Source</th></tr></thead><tbody id="rcs-unit-rows"></tbody></table></div><div class="rcs-unit-pager"><button id="rcs-unit-previous" type="button">Previous</button><span id="rcs-unit-page-status" aria-live="polite"></span><button id="rcs-unit-next" type="button">Next</button></div></section>
<section class="card"><h2>What to verify</h2><ul><li>Whether the same ₱4.2M is a standard design package, a planning ceiling, or independently costed for each site.</li><li>Whether facilities, tanks, quantities, units, and item totals in each POW reconcile to the signed engineering estimate.</li><li>Whether the listed locations and delivery scope match the project implementation records.</li></ul><p><a href="dpwh.html">Open the DPWH in-depth POW review queue ↗</a> · <a href="rcs-rainfall-archive.html">Open the archived rainfall-only scenario ↗</a></p></section></main><script src="rcs-cost-unit.js"></script><footer style="text-align:center;padding:18px;color:#536873">A review lead for human verification, not a finding.</footer></body></html>'''
    body=body.replace('</aside>', '</aside>'+lead, 1)
    page=header.replace('</head>',HERO_STYLE+'</head>')+body
    from investigation_page_sections import apply_owned_sections
    page=apply_owned_sections(page,'rcs.html')
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    page=apply_uniform_menu_page(page,'rcs.html')
    from report_table_presentation import publish_assets,apply_page as apply_report_styles
    return apply_report_styles(page,publish_assets())

def main():
    out=STATIC/'rcs.html'
    unit_bills=read_unit_cost_bills()
    payload=json.dumps({'scope':'199 RCS projects locked to the ₱4.2M schedule','bills':unit_bills},ensure_ascii=False,separators=(',',':'))
    script=UNIT_COST_JS
    (STATIC/'rcs-cost-unit.js').write_text(script,encoding='utf-8')
    (ROOT/'analysis_output/rcs-cost-unit-data.json').write_text(payload+'\n',encoding='utf-8')
    (STATIC/'rcs-cost-unit-data.json').write_text(payload+'\n',encoding='utf-8')
    page=render(read_evidence()).replace('src="rcs-cost-unit.js"',f'src="rcs-cost-unit.js?v={hashlib.sha256(script.encode()).hexdigest()[:12]}"')
    out.write_text(page,encoding='utf-8')
    print(f'Wrote {out} with {len(unit_bills)} bill/unit plots from {sum(len(x["rows"]) for x in unit_bills)} project-bill observations')

UNIT_COST_JS=r'''(()=>{'use strict';
const $=id=>document.getElementById(id), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])), num=v=>Number(v).toLocaleString('en-PH',{maximumFractionDigits:2}), peso=v=>'₱'+num(v);
fetch('rcs-cost-unit-data.json').then(r=>{if(!r.ok)throw Error('RCS bill data unavailable');return r.json()}).then(DATA=>{
const select=$('rcs-bill-filter'), search=$('rcs-project-filter'), body=$('rcs-unit-rows'), status=$('rcs-unit-page-status'), host=$('rcs-unit-boxplot');let page=0;
select.innerHTML=DATA.bills.map(b=>`<option value="${esc(b.key)}">${esc(b.label)} · ${esc(b.unit)} · ${num(b.rows.length)} projects</option>`).join('');
function quantile(a,q){const x=(a.length-1)*q,lo=Math.floor(x),hi=Math.ceil(x);return a[lo]+(a[hi]-a[lo])*(x-lo)}
function draw(){const bill=DATA.bills.find(b=>b.key===select.value),q=search.value.trim().toLocaleLowerCase(),rows=(bill?.rows||[]).filter(r=>(r.name+' '+r.office).toLocaleLowerCase().includes(q));page=Math.min(page,Math.max(0,Math.ceil(rows.length/20)-1));const values=rows.map(r=>r.unitCost).sort((a,b)=>a-b);if(values.length<2){host.innerHTML='<p class="note">At least two projects with a usable amount and quantity are needed for a box plot.</p>'}else{const min=values[0],max=values.at(-1),q1=quantile(values,.25),med=quantile(values,.5),q3=quantile(values,.75),iqr=q3-q1,lf=q1-1.5*iqr,hf=q3+1.5*iqr,low=values.find(v=>v>=lf)??min,high=[...values].reverse().find(v=>v<=hf)??max,lo=Math.floor(Math.log10(min)),hi=Math.ceil(Math.log10(max)),ticks=[];for(let e=lo;e<=hi;e++)for(const m of[1,2,5]){const v=m*Math.pow(10,e);if(v>=min&&v<=max)ticks.push(v)}if(!ticks.length)ticks.push(min,max);const W=1160,left=55,right=1110,y=72,axis=115,span=Math.log10(max)-Math.log10(min)||1,x=v=>left+(Math.log10(v)-Math.log10(min))/span*(right-left),outliers=rows.filter(r=>r.unitCost<lf||r.unitCost>hf).length,parts=[`<svg viewBox="0 0 ${W} 150" role="img" aria-label="${esc(bill.label)} · ${num(rows.length)} RCS project unit costs; logarithmic scale"><text x="${left}" y="18" class="rcs-box-summary">${num(rows.length)} projects · ${num(outliers)} orange outliers · 1.5×IQR rule</text>`];for(const v of ticks)parts.push(`<line x1="${x(v)}" y1="34" x2="${x(v)}" y2="${axis}" class="rcs-box-grid"/><text x="${x(v)}" y="${axis+20}" text-anchor="middle" class="rcs-box-tick">${esc(peso(v))}</text>`);rows.forEach((r,i)=>{const out=r.unitCost<lf||r.unitCost>hf;parts.push(`<circle cx="${x(r.unitCost)}" cy="${y+((i%11)-5)*5}" r="${out?3:2.3}" class="${out?'rcs-box-outlier':'rcs-box-observation'}"><title>${esc(r.name)} · ${peso(r.unitCost)} per ${esc(bill.unit)} · ${out?'outside':'within'} 1.5×IQR</title></circle>`)});parts.push(`<line x1="${x(low)}" y1="${y}" x2="${x(high)}" y2="${y}" class="rcs-box-whisker"/><line x1="${x(low)}" y1="${y-12}" x2="${x(low)}" y2="${y+12}" class="rcs-box-cap"/><line x1="${x(high)}" y1="${y-12}" x2="${x(high)}" y2="${y+12}" class="rcs-box-cap"/><rect x="${x(q1)}" y="${y-20}" width="${Math.max(1,x(q3)-x(q1))}" height="40" rx="4" class="rcs-box-shape"/><line x1="${x(med)}" y1="${y-20}" x2="${x(med)}" y2="${y+20}" class="rcs-box-median"/><line x1="${left}" y1="${axis}" x2="${right}" y2="${axis}" class="rcs-box-axis"/><text x="${W/2}" y="148" text-anchor="middle" class="rcs-box-tick">Parsed POW amount ÷ quantity · ₱ per ${esc(bill.unit)} · logarithmic scale</text></svg>`);host.innerHTML=parts.join('')}
$('rcs-unit-summary').textContent=bill?`${bill.label} · ${bill.unit} · ${num(rows.length)} projects with usable amount and quantity · as-submitted basis. Rows are sorted by highest calculated unit cost.`:'No parsed RCS bill rows are available.';const start=page*20,shown=rows.slice(start,start+20);body.innerHTML=shown.map(r=>`<tr><td><strong>${esc(r.name)}</strong><br><span class="note">${esc(r.office)} · ${esc(r.code)}</span></td><td class="money">${peso(r.unitCost)} per ${esc(bill.unit)}</td><td>${num(r.quantity)} ${esc(bill.unit)}</td><td class="money">${peso(r.amount)}</td><td>${r.url?`<a href="${esc(r.url)}${r.pages[0]?'#page='+r.pages[0]:''}" target="_blank" rel="noopener">POW${r.pages[0]?' p. '+r.pages[0]:''} ↗</a>`:'Not linked'}</td></tr>`).join('')||'<tr><td colspan="5">No project rows match this search.</td></tr>';const pages=Math.max(1,Math.ceil(rows.length/20));status.textContent=rows.length?`${num(start+1)}–${num(Math.min(start+20,rows.length))} of ${num(rows.length)} projects · page ${num(page+1)} of ${num(pages)}`:'No matching projects';$('rcs-unit-previous').disabled=page===0;$('rcs-unit-next').disabled=page+1>=pages}
select.onchange=()=>{page=0;draw()};search.oninput=()=>{page=0;draw()};$('rcs-unit-previous').onclick=()=>{page--;draw()};$('rcs-unit-next').onclick=()=>{page++;draw()};draw();}).catch(e=>{console.error(e);host.innerHTML='<p class="note">RCS bill cost data could not be loaded.</p>'});})();'''

if __name__=='__main__':main()
