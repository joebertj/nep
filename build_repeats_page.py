#!/usr/bin/env python3
"""Collate generated project-repeat sections, preserving their tables and evidence."""
import csv
import hashlib
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'
SECTION=re.compile(r'<section\b[^>]*>(?:(?!<section\b).)*?</section>',re.S)
CACHE=OUT/'repeat_page_fragments.json'
HGAB_GAA_DATA=STATIC/'repeat-hgab-historical-gaa.json'
SPLIT_GAA_DATA=STATIC/'repeats-historical-data.json'

def build():
    """Build only repeats.html from cached, page-independent repeat fragments."""
    if not CACHE.exists():
        raise FileNotFoundError(f"Repeat section cache is required: {CACHE}")
    fragments=json.loads(CACHE.read_text(encoding='utf-8'))
    required={'within','survival'}
    missing=required-set(fragments)
    if missing:
        raise ValueError('Missing repeat sections in cache: '+', '.join(sorted(missing)))
    from build_repeats_split import build_repeats_page as render_repeats_page
    result=render_repeats_page(fragments)
    html=result.pop('html')
    from build_five_million_evidence import apply_page as apply_five_million_evidence
    html=apply_five_million_evidence(html)
    from report_table_presentation import apply_page_table_module
    html,_=apply_page_table_module('repeats.html',html)
    html=html.rstrip()+'\n'
    (STATIC/'repeats.html').write_text(html,encoding='utf-8')
    (OUT/'repeats.html').write_text(html,encoding='utf-8')
    return result

if __name__ == '__main__':
    print(build())

SCRIPT=r'''<script>(()=>{
const D=JSON.parse(document.getElementById('repeat-page-data').textContent),search=document.getElementById('priorityRepeatSearch'),year=document.getElementById('priorityRepeatYear'),category=document.getElementById('repeatCategory'),body=document.getElementById('priorityRepeatBody'),pager=document.getElementById('priorityRepeatPager');let page=0,filtered=[];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),peso=v=>'₱'+Number(v||0).toLocaleString('en-PH');
for(const c of [...new Set(D.map(r=>r.category))].sort()){const o=document.createElement('option');o.value=o.textContent=c;category.append(o)}
function evidenceCell(value,row){
 const text=esc(value);
 if(!row.overlapDiagram)return text;
 return text.replace(/\boverlap\b/i,word=>'<button type="button" class="chainage-overlap-link" aria-label="Show chainage overlap diagram" data-chainage-diagram="'+esc(JSON.stringify(row.overlapDiagram))+'">'+word+'</button>');
}
function draw(){filtered=D.filter(r=>(year.value==='all'||String(r.comparison_year)===year.value)&&(category.value==='all'||r.category===category.value)&&JSON.stringify(r).toLowerCase().includes(search.value.toLowerCase()));page=Math.min(page,Math.max(0,Math.ceil(filtered.length/25)-1));
const start=page*25;body.innerHTML=filtered.slice(start,start+25).map(r=>'<tr data-chainage-pair="'+esc(JSON.stringify([r.source_code,String(r.comparison_year),r.prior_source]))+'">'+[r.category,r.project,r.current_chainage,r.office,peso(r.amount_2027),'FY'+r.comparison_year,r.prior_project,r.prior_chainage,r.chainage_status+(r.chainage_overlap?' · '+r.chainage_overlap:'')+' · '+r.tranche_status+(r.category==='Multi-purpose building'?' · Printed-point separation: '+(r.distanceMeters!=null?Number(r.distanceMeters).toLocaleString('en-PH')+' meters':'Not established')+' · '+r.barangayEvidence:''),peso(r.prior_amount),r.similarity_pct+'%',r.prior_source].map((v,i)=>'<td'+(i===8?' data-chainage-evidence="true"':'')+'>'+(i===8?evidenceCell(v,r):esc(v))+'</td>').join('')+'</tr>').join('');pager.innerHTML='<button id="repeatPrev">Previous</button><span>'+filtered.length+' filtered pairs · page '+(page+1)+'</span><button id="repeatNext">Next</button>';document.getElementById('repeatPrev').disabled=page===0;document.getElementById('repeatNext').disabled=start+25>=filtered.length;document.getElementById('repeatPrev').onclick=()=>{page--;draw()};document.getElementById('repeatNext').onclick=()=>{page++;draw()};
const graph=document.getElementById('repeatGraph');if(graph){const years=[...new Set(filtered.map(r=>Number(r.comparison_year)))].sort((a,b)=>b-a),counts=years.map(y=>filtered.filter(r=>Number(r.comparison_year)===y).length),max=Math.max(...counts,1),height=54+years.length*38;graph.innerHTML='<svg viewBox="0 0 900 '+height+'" role="img" aria-label="Filtered historical comparison pairs by enacted GAA year">'+years.map((y,i)=>{const n=counts[i],width=560*n/max,top=34+i*38;return '<text x="8" y="'+(top+17)+'" font-size="14" font-weight="700">FY'+y+'</text><rect x="100" y="'+top+'" width="560" height="22" rx="7" fill="#e7efed"/><rect x="100" y="'+top+'" width="'+width+'" height="22" rx="7" fill="#087e78"/><text x="675" y="'+(top+17)+'" font-size="14">'+n.toLocaleString('en-PH')+' pairs</text>'}).join('')+'</svg>'}}
for(const el of [search,year,category])el.oninput=el.onchange=()=>{page=0;draw()};
function download(name,rows){const csv=rows.map(r=>r.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
const btn=document.getElementById('repeatCsv');if(btn)btn.onclick=()=>{const keys=Object.keys(D[0]);download('dpwh_historical_filtered.csv',[keys,...filtered.map(r=>keys.map(k=>Array.isArray(r[k])?r[k].join('; '):r[k]))])};
window.downloadReportTable=(id,name)=>download(name,[...document.getElementById(id).rows].map(r=>[...r.cells].map(c=>c.innerText)));
draw();})();</script>'''
