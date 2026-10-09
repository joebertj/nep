#!/usr/bin/env python3
"""Show increases and decreases on retained domestic projects separately from removals."""
import json
import re
from pathlib import Path
from hgab_matching import is_fap

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

SECTION='''<section class="card section" id="allocation-adjustments-domestic"><h2>Allocation adjustments · retained domestic projects</h2>
<p class="sub">These selected NEP/HGAB counterparts remain in both stages with different allocations. Positive changes are increases; negative changes are decreases. Nonexact title counterparts remain provisional. These lines are excluded from the insertion and removal shortlists.</p>
<div class="toolbar"><input id="adjust-search" type="search" placeholder="Search project, office or source ID"><select id="adjust-direction"><option value="all">Increases and decreases</option><option value="increase">Increases</option><option value="decrease">Decreases</option></select><select id="adjust-basis"><option value="all">Exact and potential counterparts</option><option value="exact_scope">Exact counterparts</option><option value="potential">Potential counterparts · review</option></select><button class="export-btn" id="adjust-csv" type="button">Export filtered CSV</button></div>
<svg id="adjust-graph" viewBox="0 0 720 250" style="display:block;width:100%;max-height:300px;font:14px sans-serif" role="img" aria-label="Allocation increases and decreases for the filtered retained projects"></svg><p class="sub" id="adjust-caption"></p>
<div class="tablewrap"><table><thead><tr><th>Match basis</th><th>NEP project</th><th>HGAB project</th><th>NEP allocation</th><th>HGAB allocation</th><th>Adjustment</th><th>Office / sources</th></tr></thead><tbody id="adjust-body"></tbody></table></div>
<div class="pagination"><button id="adjust-prev" type="button">Previous</button><span id="adjust-page"></span><button id="adjust-next" type="button">Next</button></div></section>'''

SCRIPT=r'''<script id="allocation-adjustments-script">
(()=>{const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),money=v=>'₱'+Number(v).toLocaleString('en-PH');
fetch('dpwh-data.json').then(r=>{if(!r.ok)throw Error('Could not load allocation adjustments');return r.json()}).then(D=>{const rows=D.allocationAdjustments.domestic,search=document.getElementById('adjust-search'),direction=document.getElementById('adjust-direction'),basis=document.getElementById('adjust-basis');let page=0;
const selected=()=>rows.filter(r=>(direction.value==='all'||(direction.value==='increase'?r.deltaPesos>0:r.deltaPesos<0))&&(basis.value==='all'||r.basis===basis.value)&&Object.values(r).join(' ').toLowerCase().includes(search.value.trim().toLowerCase())).sort((a,b)=>Math.abs(b.deltaPesos)-Math.abs(a.deltaPesos));
const draw=()=>{const data=selected(),pages=Math.max(1,Math.ceil(data.length/25));page=Math.max(0,Math.min(page,pages-1));const values=['exact_scope','potential'].flatMap(b=>[1,-1].map(sign=>({basis:b,sign,value:data.filter(r=>r.basis===b&&Math.sign(r.deltaPesos)===sign).reduce((t,r)=>t+Math.abs(r.deltaPesos),0)}))),scale=Math.max(1,...values.map(v=>v.value));document.getElementById('adjust-graph').innerHTML='<line x1="50" x2="690" y1="115" y2="115" stroke="#637381"/>'+values.map((v,i)=>{const height=v.value/scale*70,x=80+i*155,y=v.sign>0?115-height:115;return `<rect x="${x}" y="${y}" width="90" height="${height}" fill="${v.sign>0?'#087e78':'#a65b08'}"/><text x="${x+45}" y="${v.sign>0?y-8:y+height+18}" text-anchor="middle">${money(v.value)}</text><text x="${x+45}" y="220" text-anchor="middle">${v.basis==='exact_scope'?'Exact':'Potential'} ${v.sign>0?'increase':'decrease'}</text>`}).join('');const net=data.reduce((t,r)=>t+r.deltaPesos,0);document.getElementById('adjust-caption').textContent=`${data.length.toLocaleString()} retained-project adjustments · net change ${money(net)}. Potential matches are provisional. The graph follows both filters and search.`;
document.getElementById('adjust-body').innerHTML=data.slice(page*25,page*25+25).map(r=>`<tr><td>${r.basis==='exact_scope'?'Exact counterpart':'Potential counterpart · review'}</td><td>${esc(r.nepTitle)}</td><td>${esc(r.hgabTitle)}</td><td>${money(r.nepPesos)}</td><td>${money(r.hgabPesos)}</td><td>${r.deltaPesos>0?'+':''}${money(r.deltaPesos)}</td><td>${esc(r.office)}<br>NEP p.${esc(r.nepPage??'Unknown')} · ${esc(r.nepId)}<br>${esc(r.hgabVolume)} p.${esc(r.hgabPage)} · ${esc(r.hgabId)}</td></tr>`).join('')||'<tr><td colspan="7">No allocation adjustments in this view.</td></tr>';document.getElementById('adjust-page').textContent=`${data.length?page*25+1:0}–${Math.min(page*25+25,data.length)} of ${data.length}`;document.getElementById('adjust-prev').disabled=page===0;document.getElementById('adjust-next').disabled=page>=pages-1};
search.oninput=direction.onchange=basis.onchange=()=>{page=0;draw()};document.getElementById('adjust-prev').onclick=()=>{page--;draw()};document.getElementById('adjust-next').onclick=()=>{page++;draw()};document.getElementById('adjust-csv').onclick=()=>{const cols=['basis','nepId','hgabId','nepTitle','hgabTitle','nepPesos','hgabPesos','deltaPesos','office','nepPage','hgabPage','hgabVolume'],csv=[cols,...selected().map(r=>cols.map(k=>r[k]??''))].map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\ufeff',csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='dpwh_domestic_allocation_adjustments_3rd.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};draw()}).catch(e=>{document.getElementById('adjust-body').innerHTML='<tr><td colspan="7">'+esc(e.message)+'</td></tr>'});})();
</script>'''


def refresh():
    mapping=json.loads((ROOT/'analysis_output/hb_nep_comparison_3rd_mapping.json').read_text())
    rows=[]
    for p in mapping['pairs']:
        if is_fap(p['hgab']) or p['amountDeltaPesos']==0:continue
        old,new=p['nep'],p['hgab']
        rows.append({'basis':p['kind'],'nepId':p['nepId'],'hgabId':p['hgabId'],
                     'nepTitle':old['projectName'],'hgabTitle':new['projectName'],
                     'nepPesos':old['amountPesos'],'hgabPesos':new['amountPesos'],
                     'deltaPesos':p['amountDeltaPesos'],'office':new.get('office',''),
                     'nepPage':old.get('sourcePage'),'hgabPage':new.get('sourcePage'),
                     'hgabVolume':new.get('sourceVolume')})
    path=STATIC/'dpwh-data.json';data=json.loads(path.read_text());data['allocationAdjustments']={'domestic':rows}
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    for name in ['dpwh.html','dpwh-hgab.html']:
        path=STATIC/name;page=path.read_text()
        page=re.sub(r'<section class="card section" id="allocation-adjustments-domestic">.*?</section>','',page,flags=re.S)
        page=re.sub(r'<script id="allocation-adjustments-script">.*?</script>','',page,flags=re.S)
        page,n=re.subn(r'(<section class="card section" id="subtractions-domestic">.*?</section>)',lambda m:m[1]+SECTION,page,count=1,flags=re.S)
        if n!=1:raise ValueError('Missing domestic removals section: '+name)
        page=page.replace('Foreign assisted projects · separate NEP → HGAB review','Foreign assisted projects · allocation adjustments and reconciliation')
        path.write_text(page.replace('</body>',SCRIPT+'</body>',1))
    print(json.dumps({'domesticAllocationAdjustments':len(rows),'increases':sum(r['deltaPesos']>0 for r in rows),'decreases':sum(r['deltaPesos']<0 for r in rows)},indent=2))


if __name__=='__main__':refresh()
