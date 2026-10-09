#!/usr/bin/env python3
"""Publish auditable native-program/office breakdowns and filtered domestic insertions."""
import csv
import html
import json
import re
from collections import defaultdict
from pathlib import Path
from hgab_matching import UNMATCHED, is_fap

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
PROGRAMS = {'Asset Preservation Program':'Asset Preservation', 'Network Development Program':'Network Development',
            'Bridge Program':'Bridges', 'Flood Management Program':'Flood Management',
            'Convergence and Special Support Program':'CSSP', 'Local Program':'Local Program',
            'FOREIGN-ASSISTED PROJECTS':'FAPs'}

def program(row):
    if is_fap(row): return 'FAPs'
    return PROGRAMS.get(row.get('pap1'), row.get('pap1') or 'Unspecified program')

def office_type(row):
    office = row.get('office','').strip()
    if office.lower() == 'central office': return 'Central Office'
    if 'district engineering office' in office.lower(): return 'DEOs'
    if 'regional office' in office.lower(): return 'Regional Offices'
    return 'Other / unspecified'

def identity(row):
    return (row['projectName'], int(row['amountPesos']), str(row.get('sourcePage','')), row.get('office',''))

def totals(rows, key):
    groups = defaultdict(lambda: {'count':0,'amountPesos':0})
    for row in rows:
        group=groups[row[key]];group['count']+=1;group['amountPesos']+=int(row['amountPesos'])
    return groups

def breakdown(insertions, removals, key, labels):
    a,b=totals(insertions,key),totals(removals,key)
    return [{'label':label,'insertionCount':a[label]['count'],'insertionPesos':a[label]['amountPesos'],
             'removalCount':b[label]['count'],'removalPesos':b[label]['amountPesos']} for label in labels]

def count_chart(rows, title):
    ceiling=max([r[k] for r in rows for k in ('insertionCount','removalCount')]+[1])
    width=1000; baseline=215; parts=[]; cell=width/len(rows)
    for i,r in enumerate(rows):
        for j,(key,color) in enumerate([('insertionCount','#087e78'),('removalCount','#ba5c16')]):
            height=r[key]/ceiling*160;x=i*cell+cell*.26+j*cell*.25
            parts.append(f'<rect x="{x:.1f}" y="{baseline-height:.1f}" width="{cell*.2:.1f}" height="{height:.1f}" fill="{color}"><title>{html.escape(r["label"])} · {key}: {r[key]:,}</title></rect><text x="{x+cell*.1:.1f}" y="{baseline-height-6:.1f}" text-anchor="middle">{r[key]:,}</text>')
        parts.append(f'<text x="{(i+.5)*cell:.1f}" y="240" text-anchor="middle">{html.escape(r["label"])}</text>')
    return '<figure class="comparison-graphic"><figcaption><strong>'+title+'</strong><span>Teal: insertion candidates · Orange: removal candidates. FAP insertions are unpaired review records, shown separately from domestic candidates.</span></figcaption><svg viewBox="0 0 1000 260" style="width:100%;height:auto;max-height:340px;font:13px sans-serif" role="img" aria-label="'+title+'">'+''.join(parts)+'</svg></figure>'

def stats_table(rows, label):
    body=''.join(f'<tr><td>{html.escape(r["label"])}</td><td class="num">{r["insertionCount"]:,}</td><td class="num">₱{r["insertionPesos"]:,}</td><td class="num">{r["removalCount"]:,}</td><td class="num">₱{r["removalPesos"]:,}</td></tr>' for r in rows)
    return '<div class="tablewrap"><table><thead><tr><th>'+label+'</th><th>Insertion candidate lines</th><th>HGAB allocation</th><th>Removal candidate lines</th><th>Original NEP allocation</th></tr></thead><tbody>'+body+'</tbody></table></div>'

TOOLBAR='''<div class="toolbar"><input id="hbInsertionSearch" type="search" placeholder="Search project, representative, office, or NEP title">
<select id="hbInsertionFilter" aria-label="Program"><option value="all">All domestic programs</option></select>
<select id="hbInsertionOfficeType" aria-label="Office category"><option value="all">All office categories</option></select>
<select id="hbInsertionOffice" aria-label="Implementing office"><option value="all">All implementing offices</option></select>
<select id="hbInsertionRegion" aria-label="Region"><option value="all">All regions</option></select>
<select id="hbInsertionSort" aria-label="Sort insertion candidates"><option value="amount-desc">Largest allocation first</option><option value="amount-asc">Smallest allocation first</option><option value="name">Project name A–Z</option><option value="similarity-desc">Closest NEP similarity first</option><option value="source">Source page</option></select>
<button class="export-btn" id="insertionCsv" type="button">Export filtered insertions to CSV</button></div>
<p class="sub" id="hbInsertionFilteredTotal" aria-live="polite"></p>
<figure class="comparison-graphic"><figcaption><strong>Largest allocations in the selected domestic insertion candidates</strong><span>Top ten by allocation; hover a bar for its complete title. Filters update the chart and table. Table order follows the selected sort.</span></figcaption><div id="insertionGraph" style="width:100%;min-height:100px"></div></figure>'''

RENDERER=r'''const hbInsertionSearch=document.getElementById('hbInsertionSearch'),hbInsertionFilter=document.getElementById('hbInsertionFilter'),hbInsertionBody=document.getElementById('hbInsertionBody'),hbInsertionPager=document.getElementById('hbInsertionPager');let hbInsertionPage=0;
const insertionSelectors=[['hbInsertionFilter','program'],['hbInsertionOfficeType','officeType'],['hbInsertionOffice','office'],['hbInsertionRegion','region']];
for(const [id,key] of insertionSelectors){const el=document.getElementById(id);for(const value of [...new Set(D.hbInsertions.map(r=>r[key]||'Unspecified'))].sort()){const option=document.createElement('option');option.value=value;option.textContent=value;el.append(option)}el.onchange=()=>{hbInsertionPage=0;drawHbInsertions()}}
function drawHbInsertions(){const q=hbInsertionSearch.value.trim().toLowerCase();let rows=D.hbInsertions.filter(r=>insertionSelectors.every(([id,key])=>document.getElementById(id).value==='all'||(r[key]||'Unspecified')===document.getElementById(id).value)&&Object.values(r).some(v=>String(v).toLowerCase().includes(q)));const sort=document.getElementById('hbInsertionSort').value;rows.sort((a,b)=>{let cmp=sort==='amount-asc'?a.amountPesos-b.amountPesos:sort==='name'?a.projectName.localeCompare(b.projectName):sort==='similarity-desc'?Number(b.title_similarity_pct)-Number(a.title_similarity_pct):sort==='source'?Number(a.sourcePage)-Number(b.sourcePage):b.amountPesos-a.amountPesos;return cmp||a.projectName.localeCompare(b.projectName)||String(a.hgab_id).localeCompare(String(b.hgab_id))});
 document.getElementById('hbInsertionFilteredTotal').textContent=fmt(rows.length)+' potential domestic insertion lines · '+peso(rows.reduce((t,r)=>t+Number(r.amountPesos),0))+' in HGAB allocations';
 const top=[...rows].sort((a,b)=>b.amountPesos-a.amountPesos).slice(0,10),max=Math.max(1,...top.map(r=>Number(r.amountPesos))),cell=1000/Math.max(1,top.length),base=245;
 document.getElementById('insertionGraph').innerHTML=top.length?'<svg viewBox="0 0 1000 310" style="display:block;width:100%;height:auto;max-height:390px;font:13px sans-serif" role="img" aria-label="Top ten filtered insertion allocations">'+top.map((r,i)=>{const h=Number(r.amountPesos)/max*180,x=i*cell+cell*.18;return `<rect x="${x}" y="${base-h}" width="${cell*.64}" height="${h}" fill="#087e78"><title>${esc(r.projectName)} · ${esc(r.program)} · ${esc(peso(r.amountPesos))}</title></rect><text x="${(i+.5)*cell}" y="${base-h-8}" text-anchor="middle">${esc('₱'+(r.amountPesos/1e6).toLocaleString('en-PH',{maximumFractionDigits:1})+'M')}</text><text x="${(i+.5)*cell}" y="267" text-anchor="middle">${i+1}</text><text x="${(i+.5)*cell}" y="287" text-anchor="middle">p. ${esc(r.sourcePage)}</text>`}).join('')+'</svg>':'<p class="sub">No candidates match these filters.</p>';
 document.getElementById('secondReadingCsv').onclick=()=>downloadCsv('dpwh_hgab_2nd_reading_review_records.csv',D.hbInsertions2nd);document.getElementById('insertionCsv').onclick=()=>downloadCsv('dpwh_hgab_3rd_domestic_insertions_filtered.csv',rows);
 const size=25,pages=Math.max(1,Math.ceil(rows.length/size));hbInsertionPage=Math.max(0,Math.min(hbInsertionPage,pages-1));const start=hbInsertionPage*size;hbInsertionBody.innerHTML=rows.slice(start,start+size).map(r=>`<tr><td class="title">${esc(r.projectName)}</td><td>${esc(r.program)}</td><td>${esc(r.officeType)}<br>${esc(r.office||'Unspecified')}</td><td>${esc((r.congressional_representatives||[]).join('; ')||'—')}</td><td>${esc(r.region)}</td><td class="num">${peso(r.amountPesos)}</td><td class="title">${esc(r.closest_nep_title)}</td><td>No plausible NEP counterpart · closest title ${fmt(r.title_similarity_pct)}%</td><td>${esc(r.sourceVolume)} · p. ${esc(r.sourcePage)}<br>${esc(r.hgab_id)}</td></tr>`).join('')||'<tr><td colspan="9" class="empty">No matching candidate lines</td></tr>';hbInsertionPager.innerHTML=`<button ${hbInsertionPage===0?'disabled':''} data-dir="-1">Previous</button><span>${rows.length?fmt(start+1):0}–${fmt(Math.min(start+size,rows.length))} of ${fmt(rows.length)}</span><button ${hbInsertionPage>=pages-1?'disabled':''} data-dir="1">Next</button>`;hbInsertionPager.querySelectorAll('button').forEach(b=>b.onclick=()=>{hbInsertionPage+=Number(b.dataset.dir);drawHbInsertions()})}
hbInsertionSearch.oninput=()=>{hbInsertionPage=0;drawHbInsertions()};document.getElementById('hbInsertionSort').onchange=()=>{hbInsertionPage=0;drawHbInsertions()};
'''

EXPORT_SCRIPT=r'''<script id="hgab-headline-export">(()=>{document.getElementById('hgabBreakdownCsv').onclick=()=>{const rows=JSON.parse(document.getElementById('hgab-headline-data').textContent),cols=['dimension','label','insertionCount','insertionPesos','removalCount','removalPesos'],csv=[cols,...rows.map(r=>cols.map(k=>r[k]))].map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(PHLocation.createBlob(['\ufeff',csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='dpwh_nep_hgab_3rd_headline_breakdowns.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}})();</script>'''

def refresh():
    path=STATIC/'dpwh-data.json';data=json.loads(path.read_text())
    native=json.loads((ROOT/'hb10858_3rd_dpwh_projects.json').read_text())['data']
    if isinstance(native,dict):native=native['data']
    native_by_id={r['id']:r for r in native}
    representatives={identity(r):r.get('congressional_representatives',[]) for r in data['hbInsertions']}
    inserted=[]
    with (ROOT/'analysis_output/hb_nep_comparison_3rd.csv').open() as f:
        for r in csv.DictReader(f):
            if r['comparison']!=UNMATCHED:continue
            original=native_by_id[r['hgab_id']]
            if r['projectName']!=original['projectName'] or int(r['amountPesos'])!=original['amountPesos']:raise ValueError('Source identity mismatch')
            row={**{k:r[k] for k in ['comparison','projectName','region','office','closest_nep_title','sourceVolume','sourcePage','hgab_id']},'amountPesos':int(r['amountPesos']),'title_similarity_pct':float(r['title_similarity_pct'] or 0),
                 'program':program(original),'officeType':office_type(original),'scope':'FAP' if is_fap(original) else 'Domestic'}
            row['congressional_representatives']=representatives.get(identity(row),[])
            inserted.append(row)
    mapping=json.loads((ROOT/'analysis_output/hb_nep_comparison_3rd_mapping.json').read_text())
    nep={r['sourceNepId']:r for r in mapping['nepWithoutSelectedCounterpart']}
    removed=[]
    for scope in ['domestic','fap']:
        for r in data['removals'][scope]['rows']:
            original=nep[r['nepId']]
            if r['nepTitle']!=original['projectName'] or r['nepPesos']!=original['amountPesos']:raise ValueError('Removal identity mismatch')
            removed.append({**r,'amountPesos':r['nepPesos'],'program':program(original),'officeType':office_type(original)})
    offices=breakdown(inserted,removed,'officeType',['Central Office','DEOs','Regional Offices','Other / unspecified'])
    programs=breakdown(inserted,removed,'program',list(PROGRAMS.values()))
    for groups in [offices,programs]:
        for rows,prefix in [(inserted,'insertion'),(removed,'removal')]:
            if sum(r[prefix+'Count'] for r in groups)!=len(rows) or sum(r[prefix+'Pesos'] for r in groups)!=sum(r['amountPesos'] for r in rows):raise ValueError('Breakdown failed reconciliation')
    data['hbInsertions']=sorted([r for r in inserted if r['scope']=='Domestic'],key=lambda r:-r['amountPesos'])
    data['hgabHeadline']={'officeBreakdown':offices,'programBreakdown':programs,'insertionCount':len(inserted),'removalCount':len(removed),
        'method':'Domestic HGAB-only candidates plus separately reviewed unpaired FAP records; reverse-screened NEP-only removal candidates. Amounts use HGAB for insertions and original NEP for removals.'}
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    (ROOT/'analysis_output/dpwh_hgab_headline_stats.json').write_text(json.dumps(data['hgabHeadline'],ensure_ascii=False,indent=2)+'\n')
    section='''<section class="card section" id="hgab-headline-breakdowns"><h2>Where are the potential insertions and removals?</h2>
<p class="sub">Our corrected comparison identifies <strong>4,606 domestic insertion candidates</strong> and <strong>860 domestic removal candidates</strong>. Another <strong>4 unpaired FAP records</strong> are reviewed separately, giving 4,610 HGAB-only review records in these breakdowns. No FAP removal candidates remain. These are provisional line-item matches, not confirmed legislative changes.</p>
<p class="sub">The externally reported 5,837 insertions / 2,139 removals belong to a different comparison and are not the totals generated by this pipeline. Our removal shortlist excludes 280 unpaired NEP records with plausible HGAB counterparts. Retained projects with allocation increases or decreases belong to allocation adjustments below.</p>
<p class="sub">Implementing offices and programs come from each source schedule, not inferred project geography. Missing offices remain unspecified, including the four FAP records. Insertion amounts are HGAB allocations; removal amounts are original NEP allocations, not certified savings.</p>
<button class="export-btn" id="hgabBreakdownCsv" type="button">Export headline breakdowns to CSV</button>'''
    section+=count_chart(offices,'Central Office versus DEOs and other implementing offices')+stats_table(offices,'Implementing office category')
    section+=count_chart(programs,'Insertion and removal candidates by source program')+stats_table(programs,'Program')+'</section>'
    export_rows=[dict(r,dimension=dimension) for dimension,rows in [('Office',offices),('Program',programs)] for r in rows]
    section+='<script type="application/json" id="hgab-headline-data">'+json.dumps(export_rows,ensure_ascii=False).replace('</','<\\/')+'</script>'
    page_path=STATIC/'dpwh-hgab.html';page=page_path.read_text()
    page=re.sub(r'<section class="card section" id="hgab-headline-breakdowns">.*?</section>\s*<script type="application/json" id="hgab-headline-data">.*?</script>','',page,flags=re.S)
    page=re.sub(r'body\[data-page="insertions"\] main>[^{}]+\{display:none!important\}', 'body[data-page="insertions"] main>:not(#hgab-insertion):not(#report-hero):not(#hgab-headline-breakdowns):not(#subtractions-domestic):not(#subtractions-fap):not(#allocation-adjustments-domestic):not(#foreign-assisted-review){display:none!important}', page)
    page=page.replace('<section id="hgab-insertion"',section+'\n<section id="hgab-insertion"',1)
    page=re.sub(r'<div class="toolbar"><input id="hbInsertionSearch".*?</figure>',lambda _:TOOLBAR,page,count=1,flags=re.S)
    page=page.replace('<th>Extracted HGAB record</th><th>District office</th>','<th>Extracted HGAB record</th><th>Program</th><th>Implementing office</th>')
    page=re.sub(r'const hbInsertionSearch=.*?(?=function update\(\))',lambda _:RENDERER,page,count=1,flags=re.S)
    page=re.sub(r'<script id="hgab-headline-export">.*?</script>','',page,flags=re.S)
    page=page.replace('</body>',EXPORT_SCRIPT+'\n</body>',1)
    page_path.write_text(page)
    print(json.dumps(data['hgabHeadline'],indent=2))

if __name__=='__main__':refresh()
