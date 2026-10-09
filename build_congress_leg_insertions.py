#!/usr/bin/env python3
"""Generalize the domestic insertion screen to all strictly attributed LEG districts."""
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from hgab_matching import UNMATCHED, is_fap
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

BLOCK='''<section class="card scenario" id="leg-district-insertions"><h2>Potential additions per legislative district (LEG)</h2>
<p class="sub">HGAB 3rd-reading domestic line items without a plausible NEP counterpart, assigned to exactly one legislative district by the PH location DB strict rules. Names describe geographic coverage, not sponsorship. Shared and unresolved locations and FAP records are excluded. These are potential insertions, pending project-scope verification.</p>
<p class="sub" id="leg-add-coverage"></p>
<div class="toolbar"><input id="leg-add-search" type="search" placeholder="Search legislative district or representative" aria-label="Search legislative districts"><select id="leg-add-sort" aria-label="Sort districts"><option value="amount">Largest potential addition allocation</option><option value="count">Most potential addition line items</option><option value="name">District A–Z</option></select><select id="leg-add-zero" aria-label="District coverage"><option value="all">All strictly covered districts, including zero</option><option value="positive">Districts with potential additions</option></select><button id="leg-add-csv" class="export-btn" type="button">Export filtered LEG summary CSV</button></div>
<figure><figcaption>Top 15 filtered districts · chart follows allocation or line-item ranking</figcaption><div id="leg-add-graph"></div></figure>
<p class="sub" id="leg-add-total"></p>
<div class="tablewrap"><table><thead><tr><th>Legislative district</th><th>Representative</th><th>Potential addition line items</th><th>Potential addition HGAB allocation</th><th>All strictly assigned HGAB lines</th><th>Project details</th></tr></thead><tbody id="leg-add-body"></tbody></table></div><div class="pagination"><button id="leg-add-prev" type="button">Previous</button><span id="leg-add-page"></span><button id="leg-add-next" type="button">Next</button></div>
<p class="sub">“All strictly assigned HGAB lines” is a separate denominator, not an insertion count. A zero means no assigned line survives the current insertion screen; it does not establish that the district received no additions.</p>
<h3 id="leg-add-detail-title">Potential additions · selected LEG</h3><div class="toolbar"><select id="leg-add-district" aria-label="District project details"></select><button id="leg-add-project-csv" class="export-btn" type="button">Export selected LEG project CSV</button></div>
<p class="sub" id="leg-add-detail-total"></p><div class="tablewrap"><table><thead><tr><th>HGAB project</th><th>Implementing office</th><th>HGAB allocation</th><th>Closest NEP title (not a selected match)</th><th>Source</th></tr></thead><tbody id="leg-add-detail-body"></tbody></table></div><div class="pagination"><button id="leg-add-detail-prev" type="button">Previous</button><span id="leg-add-detail-page"></span><button id="leg-add-detail-next" type="button">Next</button></div></section>'''

SCRIPT=r'''<script id="leg-insertions-script">(()=>{const DATA=__DATA__,districts=DATA.districts,$=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),peso=v=>'₱'+Number(v).toLocaleString('en-PH'),fmt=v=>Number(v).toLocaleString('en-PH');let page=0,detailPage=0;
function csv(name,rows,cols){const text=[cols,...rows.map(r=>cols.map(k=>r[k]??''))].map(r=>r.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(PHLocation.createBlob(['\ufeff',text],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function selected(){const q=$('leg-add-search').value.trim().toLowerCase(),sort=$('leg-add-sort').value;return districts.filter(d=>(d.district+' '+d.representative).toLowerCase().includes(q)&&($('leg-add-zero').value==='all'||d.candidateLines>0)).sort((a,b)=>(sort==='count'?b.candidateLines-a.candidateLines:sort==='name'?a.district.localeCompare(b.district):b.candidateAllocationPesos-a.candidateAllocationPesos)||a.district.localeCompare(b.district))}
$('leg-add-coverage').textContent=fmt(DATA.assignedCandidateLines)+' of '+fmt(DATA.domesticCandidateLines)+' domestic insertion candidates ('+peso(DATA.assignedCandidatePesos)+') qualify for a unique LEG. '+fmt(DATA.excludedCandidateLines)+' candidates remain outside this table because their locations are shared or unresolved.';
for(const d of [...districts].sort((a,b)=>a.district.localeCompare(b.district))){const opt=document.createElement('option');opt.value=d.district;opt.textContent=d.district+' · '+d.representative;$('leg-add-district').append(opt)}
function draw(){const rows=selected(),pages=Math.max(1,Math.ceil(rows.length/25));page=Math.max(0,Math.min(page,pages-1));const start=page*25; $('leg-add-total').textContent=fmt(rows.length)+' districts · '+fmt(rows.reduce((t,r)=>t+r.candidateLines,0))+' potential addition lines · '+peso(rows.reduce((t,r)=>t+r.candidateAllocationPesos,0));
const byCount=$('leg-add-sort').value==='count',top=[...rows].sort((a,b)=>byCount?b.candidateLines-a.candidateLines:b.candidateAllocationPesos-a.candidateAllocationPesos).slice(0,15),value=d=>byCount?d.candidateLines:d.candidateAllocationPesos,max=Math.max(1,...top.map(value)),cell=1200/Math.max(1,top.length);$('leg-add-graph').innerHTML=top.length?'<svg viewBox="0 0 1200 420" style="display:block;width:100%;height:auto;max-height:460px;font:12px sans-serif" role="img" aria-label="Top legislative district potential additions">'+top.map((d,i)=>{const h=value(d)/max*180;return `<g><title>${esc(d.district)} · ${esc(d.representative)} · ${fmt(d.candidateLines)} lines · ${peso(d.candidateAllocationPesos)}</title><rect x="${i*cell+cell*.2}" y="${210-h}" width="${cell*.6}" height="${h}" fill="#087e78"/><text x="${(i+.5)*cell}" y="${202-h}" text-anchor="middle">${byCount?fmt(value(d)):'₱'+(value(d)/1e6).toFixed(0)+'M'}</text><text transform="translate(${(i+.5)*cell},225) rotate(45)" text-anchor="start">${esc(d.district)}</text></g>`}).join('')+'</svg>':'<p class="sub">No districts match these filters.</p>';
$('leg-add-body').innerHTML=rows.slice(start,start+25).map(d=>`<tr><td>${esc(d.district)}</td><td>${esc(d.representative||'—')}</td><td>${fmt(d.candidateLines)}</td><td>${peso(d.candidateAllocationPesos)}</td><td>${fmt(d.acceptedDistrictLines)}</td><td><button type="button" data-leg="${esc(d.district)}">View projects</button></td></tr>`).join('')||'<tr><td colspan="6">No matching districts.</td></tr>';for(const b of $('leg-add-body').querySelectorAll('button'))b.onclick=()=>{$('leg-add-district').value=b.dataset.leg;detailPage=0;detail();$('leg-add-detail-title').scrollIntoView({behavior:'smooth',block:'start'})};$('leg-add-page').textContent=(rows.length?start+1:0)+'–'+Math.min(start+25,rows.length)+' of '+rows.length;$('leg-add-prev').disabled=page===0;$('leg-add-next').disabled=page===pages-1;}
function detail(){const d=districts.find(d=>d.district===$('leg-add-district').value);if(!d)return;const pages=Math.max(1,Math.ceil(d.rows.length/20));detailPage=Math.max(0,Math.min(detailPage,pages-1));const start=detailPage*20;$('leg-add-detail-title').textContent='Potential additions · '+d.district;$('leg-add-detail-total').textContent=fmt(d.candidateLines)+' potential additions · '+peso(d.candidateAllocationPesos)+' · '+fmt(d.acceptedDistrictLines)+' total strictly assigned HGAB lines. Projects ranked by allocation.';$('leg-add-detail-body').innerHTML=d.rows.slice(start,start+20).map(r=>`<tr><td>${esc(r.projectName)}</td><td>${esc(r.office)}</td><td>${peso(r.amountPesos)}</td><td>${esc(r.closestNepTitle)}</td><td>${esc(r.sourceVolume)} · p. ${esc(r.sourcePage)}<br>${esc(r.id)}</td></tr>`).join('')||'<tr><td colspan="5">No assigned line survives the current insertion screen. This does not establish that this district has no insertions.</td></tr>';$('leg-add-detail-page').textContent=(d.rows.length?start+1:0)+'–'+Math.min(start+20,d.rows.length)+' of '+d.rows.length;$('leg-add-detail-prev').disabled=detailPage===0;$('leg-add-detail-next').disabled=detailPage===pages-1;}
for(const id of ['leg-add-search','leg-add-sort','leg-add-zero'])$(id)[id==='leg-add-search'?'oninput':'onchange']=()=>{page=0;draw()};$('leg-add-prev').onclick=()=>{page--;draw()};$('leg-add-next').onclick=()=>{page++;draw()};$('leg-add-district').onchange=()=>{detailPage=0;detail()};$('leg-add-detail-prev').onclick=()=>{detailPage--;detail()};$('leg-add-detail-next').onclick=()=>{detailPage++;detail()};$('leg-add-csv').onclick=()=>csv('potential_additions_by_LEG.csv',selected(),['district','representative','candidateLines','candidateAllocationPesos','acceptedDistrictLines']);$('leg-add-project-csv').onclick=()=>{const d=districts.find(d=>d.district===$('leg-add-district').value);if(d)csv('potential_additions_'+d.district.replace(/[^a-z0-9]+/gi,'_')+'.csv',d.rows,['district','representative','id','projectName','amountPesos','office','closestNepTitle','similarityPct','sourceVolume','sourcePage'])};draw();detail();})();</script>'''

def main():
    congress=json.loads((STATIC/'congress-data.json').read_text())
    audit_path=ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json'
    comparison_path=ROOT/'analysis_output/hb_nep_comparison_3rd.csv'
    audit=json.loads(audit_path.read_text());decisions={r['id']:r for r in audit['projects']}
    with comparison_path.open(newline='') as f:comparison=list(csv.DictReader(f))
    domestic=[r for r in comparison if r['comparison']==UNMATCHED and not is_fap(r)]
    groups=defaultdict(list)
    for r in domestic:
        g=decisions[r['hgab_id']]
        if g['projectName']!=r['projectName'] or g['amountPesos']!=int(r['amountPesos']):raise ValueError('Source identity disagreement')
        if g['status']!='unique':continue
        if len(g['districts'])!=1:raise ValueError('Unique assignment has multiple districts')
        groups[g['districts'][0]].append({'id':r['hgab_id'],'district':g['districts'][0],'representative':'; '.join(g['representatives']),
            'projectName':r['projectName'],'amountPesos':int(r['amountPesos']),'office':r['office'],
            'closestNepTitle':r['closest_nep_title'],'similarityPct':float(r['title_similarity_pct'] or 0),
            'sourceVolume':r['sourceVolume'],'sourcePage':r['sourcePage']})
    reports=[]
    for d in congress['strict']:
        rows=sorted(groups.pop(d['district'],[]),key=lambda r:(-r['amountPesos'],r['id']))
        if len(rows)>d['lineItems'] or sum(r['amountPesos'] for r in rows)>d['totalPesos']:raise ValueError('Additions exceed accepted district totals')
        reports.append({'district':d['district'],'representative':d['representative'],'candidateLines':len(rows),
            'candidateAllocationPesos':sum(r['amountPesos'] for r in rows),'acceptedDistrictLines':d['lineItems'],'rows':rows})
    if groups:raise ValueError('Insertion district absent from current strict Congress data')
    reports.sort(key=lambda r:(-r['candidateAllocationPesos'],r['district']))
    assigned=sum(r['candidateLines'] for r in reports)
    document={'method':'Domestic HGAB-only candidates intersected with uniquely assigned scope-reviewed LEG geography; unresolved/shared locations and FAP excluded.',
        'domesticCandidateLines':len(domestic),'assignedCandidateLines':assigned,'excludedCandidateLines':len(domestic)-assigned,
        'assignedCandidatePesos':sum(r['candidateAllocationPesos'] for r in reports),'districts':reports,
        'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [comparison_path,audit_path]]}
    (ROOT/'analysis_output/congress_leg_insertions.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    path=STATIC/'congress.html';page=path.read_text()
    page=re.sub(r'<div id="focused-district-insertions">.*?</div><!-- focused-district-insertions-end -->','',page,flags=re.S)
    page=re.sub(r'<script id="focused-insertions-script">.*?</script>','',page,flags=re.S)
    page=re.sub(r'<section class="card scenario" id="leg-district-insertions">.*?</section>','',page,flags=re.S)
    page=re.sub(r'<script id="leg-insertions-script">.*?</script>','',page,flags=re.S)
    marker='<section class="card scenario" aria-labelledby="deoLegTitle">'
    if marker not in page:raise ValueError('Crosswalk insertion anchor missing')
    payload=json.dumps(document,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    page=page.replace(marker,BLOCK+marker,1).replace('</body>',SCRIPT.replace('__DATA__',payload)+'</body>',1)
    path.write_text(page)
    print(json.dumps({k:v for k,v in document.items() if k not in ['districts','sources']},indent=2))

if __name__=='__main__':main()
