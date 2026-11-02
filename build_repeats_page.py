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

def build():
    from build_report_heroes import STYLE
    from build_investigation_summary import CSS, JS
    fragments=json.loads(CACHE.read_text()) if CACHE.exists() else {}
    sources={'dpwh.html':[('within','id="within-stage-repeats"')],
             'fmr.html':[('fmr','Potential FMR repeats:')],
             'nia.html':[('nia','Potential NIA irrigation repeats:')]}
    for name,targets in sources.items():
        path=STATIC/name
        text=path.read_text()
        for key,marker in targets:
            found=next((m for m in SECTION.finditer(text) if marker in m[0]),None)
            if found:
                fragments[key]=found[0]
                text=text[:found.start()]+f'<p class="repeat-page-link"><a href="repeats.html#{key}">Project repeat comparisons and source evidence →</a></p>'+text[found.end():]
        path.write_text(text)
    required={'within','fmr','nia'}
    if not required.issubset(fragments):
        raise ValueError('Missing repeat sections: '+str(required-set(fragments)))
    CACHE.write_text(json.dumps(fragments,ensure_ascii=False,indent=2)+'\n')

    # Historical agency screens compare current HGAB projects with enacted GAA.
    # Label that year explicitly in each table, even where the current source
    # covers one GAA year only.
    def add_table_column(fragment, after_index, header, value):
        def row_insert(match):
            row=match.group(0)
            cells=list(re.finditer(r'<t[dh]\b[^>]*>.*?</t[dh]>',row,re.S))
            if len(cells)<=after_index:
                return row
            insert_at=cells[after_index].end()
            tag='th' if cells[0].group(0).startswith('<th') else 'td'
            cell=f'<{tag}>{header if tag=="th" else value}</{tag}>'
            return row[:insert_at]+cell+row[insert_at:]
        return re.sub(r'<tr\b[^>]*>.*?</tr>',row_insert,fragment,flags=re.S)
    fmr=add_table_column(fragments['fmr'],1,'GAA year','FY2025')
    nia=add_table_column(fragments['nia'],2,'GAA year','FY2025')
    within_data=json.loads((OUT/'within_stage_repeats.json').read_text())
    hgab_summary=next(row for row in within_data['summary'] if row['stage']=='FY2027 HGAB 3rd')
    source_within=fragments['within']
    match=re.search(r'<h3>FY2027 HGAB 3rd · first 50 review pairs</h3>.*?(?=<h3>Methodology and exclusions</h3>)',source_within,re.S)
    if not match:
        raise ValueError('Could not isolate HGAB within-stage repeat records')
    within=('<section id="within-stage-repeats" class="investigation-evidence"><h2>Repeated line items within HGAB 3rd reading</h2>'
            '<p>Potentially similar HGAB 3rd-reading project lines for review. These are within-stage title comparisons, not confirmed duplicate work.</p>'
            '<div class="stats"><div><strong>'+str(hgab_summary['candidatePairs'])+'</strong><span>candidate pairs</span></div>'
            '<div><strong>'+str(hgab_summary['distinctFlaggedOccurrences'])+'</strong><span>distinct line occurrences</span></div>'
            '<div><strong>'+str(hgab_summary['positiveOverlapPairs'])+'</strong><span>pairs with explicit chainage overlap</span></div></div>'
            +match.group(0).replace('<h3>FY2027 HGAB 3rd · first 50 review pairs</h3>','<h3>First 50 review pairs</h3>',1)+'</section>')
    queue=json.loads((OUT/'line_item_review_queue.json').read_text())
    historical_rows=[]
    for project in queue.get('rankedOccurrences',[]):
        for prior in project.get('historicalMatches',[]):
            historical_rows.append({
                'hgabId':project['hgabId'],'projectName':project['projectName'],
                'program':project.get('program',''),'office':project.get('office',''),
                'region':project.get('region',''),'amountPesos':int(project['amountPesos']),
                'sourceVolume':project.get('sourceVolume',''),'sourcePage':project.get('sourcePage',''),
                'gaaYear':int(prior['year']),'gaaTitle':prior['title'],
                'gaaAmountPesos':int(prior['amountPesos']),'gaaSource':prior.get('source',''),
                'changePesos':int(project['amountPesos'])-int(prior['amountPesos']),
                'chainageStatus':prior.get('chainage',{}).get('chainage_status','not stated'),
                'chainageOverlap':prior.get('chainage',{}).get('chainage_overlap',''),
            })
    historical_rows.sort(key=lambda r:(-abs(r['changePesos']),r['gaaYear'],r['projectName'],r['hgabId']))
    historical_data={
        'scope':'HGAB 3rd-reading project lines with an exact normalized historical title and qualified municipality/province match in prior GAA data.',
        'method':queue.get('method',{}).get('historicalMatch',''),
        'summary':{'comparisonPairs':len(historical_rows),'hgabOccurrences':len({r['hgabId'] for r in historical_rows}),
                   'years':sorted({r['gaaYear'] for r in historical_rows})},
        'rows':historical_rows,
    }
    serialized=json.dumps(historical_data,ensure_ascii=False,separators=(',',':'))+'\n'
    HGAB_GAA_DATA.write_text(serialized,encoding='utf-8')
    (OUT/HGAB_GAA_DATA.name).write_text(serialized,encoding='utf-8')
    historical_version=hashlib.sha256(HGAB_GAA_DATA.read_bytes()).hexdigest()[:12]
    historical_section='''<section id="hgab-historical-gaa" class="investigation-evidence"><h2>HGAB 3rd vs historical GAA · recurring project titles</h2><p>HGAB lines with an exact normalized title and qualified municipality/province match in the available FY2016–FY2018 title-classified DPWH baseline and FY2020–FY2026 GAA records. The amount difference compares budget allocations; it is not proof that scope, contract value, or completed work is identical. Each GAA year is a separate comparison.</p><div class="stats"><div><strong id="historical-pair-count">—</strong><span>HGAB–GAA comparison pairs</span></div><div><strong id="historical-project-count">—</strong><span>distinct HGAB project lines</span></div><div><strong id="historical-year-count">—</strong><span>GAA years represented</span></div></div><p class="muted">FY2016–FY2018 are a separate title-classified DPWH project-family layer; FY2019 has no named DPWH project rows in the source snapshot. FY2000–2008 has partial/aggregate-only coverage; FY2001/2004/2006 had no new GAA; FY2009–2015 is unavailable or unreconciled. Unavailable years are excluded from matches and totals.</p><div class="toolbar"><label>GAA year <select id="historical-year"><option value="all">All available years</option></select></label><input id="historical-search" type="search" placeholder="Search project, program, office, or source"><button id="historical-csv" type="button">Export filtered CSV</button></div><div id="historical-year-chart" class="chart"></div><div class="tablewrap"><table><thead><tr><th>HGAB project · office · source page</th><th>GAA year</th><th>Historical GAA project · source</th><th>HGAB allocation</th><th>GAA allocation</th><th>Change</th><th>Chainage evidence</th></tr></thead><tbody id="historical-body"></tbody></table></div><div class="pagination"><button id="historical-prev" type="button">Previous</button><span id="historical-page">Page 1</span><button id="historical-next" type="button">Next</button></div><p class="muted" id="historical-status"></p></section>'''
    historical_script='''<script>fetch("repeat-hgab-historical-gaa.json?v=__DATA_VERSION__").then(r=>{if(!r.ok)throw Error("Historical GAA comparison data unavailable");return r.json()}).then(D=>{const $=id=>document.getElementById(id),peso=n=>"₱"+Number(n||0).toLocaleString("en-PH"),esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}[c])),year=$("historical-year"),search=$("historical-search"),body=$("historical-body"),size=50;let page=0,filtered=[];for(const y of D.summary.years){const o=document.createElement("option");o.value=y;o.textContent="FY"+y+" GAA";year.append(o)}for(let y=2000;y<2020;y++){if(D.summary.years.includes(y))continue;const o=document.createElement("option");o.value="unavailable-"+y;o.textContent="FY"+y+" · Data unavailable";o.disabled=true;year.append(o)}$("historical-pair-count").textContent=D.summary.comparisonPairs.toLocaleString("en-PH");$("historical-project-count").textContent=D.summary.hgabOccurrences.toLocaleString("en-PH");$("historical-year-count").textContent=D.summary.years.length.toLocaleString("en-PH");function draw(){const q=search.value.trim().toLowerCase();filtered=D.rows.filter(r=>(year.value==="all"||String(r.gaaYear)===year.value)&&(!q||[r.projectName,r.program,r.office,r.region,r.gaaTitle,r.gaaSource,r.sourceVolume].join(" ").toLowerCase().includes(q)));const pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages-1);const start=page*size;body.innerHTML=filtered.slice(start,start+size).map(r=>"<tr><td><strong>"+esc(r.projectName)+"</strong><br><small>"+esc(r.office)+" · "+esc(r.sourceVolume)+" · p."+esc(r.sourcePage)+"</small></td><td>FY"+r.gaaYear+"</td><td>"+esc(r.gaaTitle)+"<br><small>"+esc(r.gaaSource)+"</small></td><td class=\\\"num\\\">"+peso(r.amountPesos)+"</td><td class=\\\"num\\\">"+peso(r.gaaAmountPesos)+"</td><td class=\\\"num\\\">"+(r.changePesos>=0?"+":"−")+peso(Math.abs(r.changePesos))+"</td><td>"+esc(r.chainageStatus)+(r.chainageOverlap?" · "+esc(r.chainageOverlap):"")+"</td></tr>").join("")||"<tr><td colspan=\\\"7\\\">No matched HGAB–GAA titles for these filters.</td></tr>";$("historical-page").textContent="Page "+(page+1)+" of "+pages;$("historical-prev").disabled=page===0;$("historical-next").disabled=start+size>=filtered.length;$("historical-status").textContent=filtered.length.toLocaleString("en-PH")+" comparison pairs · changes are HGAB allocation minus the selected GAA year amount.";const counts=D.summary.years.map(y=>({y,n:D.rows.filter(r=>r.gaaYear===y).length})),max=Math.max(1,...counts.map(x=>x.n));$("historical-year-chart").innerHTML="<svg viewBox=\\\"0 0 850 "+(40+counts.length*36)+"\\\" role=\\\"img\\\" aria-label=\\\"HGAB historical GAA comparison pairs by year\\\">"+counts.map((x,i)=>"<text x=\\\"8\\\" y=\\\""+(30+i*36)+"\\\">FY"+x.y+"</text><rect x=\\\"90\\\" y=\\\""+(14+i*36)+"\\\" width=\\\"550\\\" height=\\\"22\\\" rx=\\\"6\\\" fill=\\\"#e7efed\\\"/><rect x=\\\"90\\\" y=\\\""+(14+i*36)+"\\\" width=\\\""+(550*x.n/max)+"\\\" height=\\\"22\\\" rx=\\\"6\\\" fill=\\\"#087e78\\\"/><text x=\\\"655\\\" y=\\\""+(30+i*36)+"\\\">"+x.n+" pairs</text>").join("")+"</svg>"}year.onchange=search.oninput=()=>{page=0;draw()};$("historical-prev").onclick=()=>{page--;draw()};$("historical-next").onclick=()=>{page++;draw()};$("historical-csv").onclick=()=>{const cols=["hgabId","projectName","program","office","sourceVolume","sourcePage","gaaYear","gaaTitle","amountPesos","gaaAmountPesos","changePesos","gaaSource","chainageStatus","chainageOverlap"],csv=[cols,...filtered.map(r=>cols.map(k=>r[k]))].map(row=>row.map(v=>"\\\""+String(v??"").replaceAll("\\\"","\\\"\\\"")+"\\\"").join(",")).join("\\r\\n"),a=document.createElement("a");a.href=URL.createObjectURL(new Blob(["\\ufeff"+csv],{type:"text/csv;charset=utf-8"}));a.download="hgab_historical_gaa_comparisons.csv";a.click()};draw()}).catch(e=>{document.getElementById("historical-status").textContent="Could not load the historical GAA comparison data.";console.error(e)});</script>'''.replace('__DATA_VERSION__',historical_version)
    # Avoid duplicate historical descriptions in the section header.
    hero='<div class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">Project repeat analysis</span><h2>Review patterns across years and within HGAB</h2><p>These are screening matches for source and scope review. They do not establish duplicate work.</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><strong>'+str(len(historical_rows))+'</strong><span>title-and-place comparisons across '+str(len(historical_data['summary']['years']))+' available GAA years</span></div><div><strong>'+str(hgab_summary['candidatePairs'])+'</strong><span>potential repeat pairs within HGAB 3rd reading</span></div><div><strong>'+str(hgab_summary['positiveOverlapPairs'])+'</strong><span>of these 97 pairs have explicit chainage overlap</span></div></div><p>Open each cited project and compare its location and funded scope.</p></div></div>'
    content=hero+'<p>NEP-to-HGAB comparisons are shown on <a href="dpwh-hgab.html">DPWH · NEP → HGAB</a>. This page focuses on potential repeats. Similar titles are review leads; they do not establish that work was duplicated.</p>'
    for key,part in [('hgab-historical-gaa',historical_section),('within',within),('fmr',fmr),('nia',nia)]:
        content+=part if key=='hgab-historical-gaa' else '<div id="'+key+'">'+part+'</div>'
    content+=historical_script
    style='<style>*{box-sizing:border-box}body{margin:0;font:15px/1.55 system-ui,sans-serif;color:#18303b;background:#f3f6f5}header{background:#102f3e;color:#fff;padding:32px}h1{font-size:clamp(30px,4vw,48px)}main{width:100%;padding:24px clamp(16px,2vw,32px)}a{color:#087e78}section{margin:24px 0;padding:22px;border:1px solid #c6dbd6;border-radius:14px;background:white}.tablewrap{width:100%}table{width:100%;table-layout:fixed;border-collapse:collapse}th,td{padding:9px;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;white-space:normal!important}th{background:#eef5f3}.toolbar,.pagination{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}input,select,button{font:inherit;padding:8px;border:1px solid #b6c9c4;border-radius:8px}input{flex:1;min-width:180px}svg{display:block;width:100%;height:auto;max-height:420px}.repeat-hero{margin:0 0 20px;padding:22px;border-radius:14px;color:white;background:#123b48}.repeat-hero-total strong{font-size:28px;display:block}.repeat-hero p{margin-bottom:0}</style>'
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project repeat comparisons · Budget analysis</title>'+style+STYLE+CSS+'</head><body><header><h1>Project repeat comparisons</h1><p>Potentially repeated project lines within HGAB and across GAA years.</p></header><main>'+content+'</main></body></html>'
    from uniform_report_menu import apply_page as apply_uniform_menu
    page=apply_uniform_menu(page,'repeats.html')
    from review_report_language import NOTICE
    EVIDENCE_CSS = CSS
    page=re.sub(r'(<main\b[^>]*>)',lambda m:m[0]+NOTICE,page,count=1)
    page=page.replace('</head>',EVIDENCE_CSS+'</head>',1)
    (STATIC/'repeats.html').write_text(page)
    (OUT/'repeats.html').write_text(page)
    return {'page':'repeats.html','sections':['HGAB vs historical GAA','within-stage HGAB','FMR HGAB vs GAA','NIA HGAB vs GAA'],'hgabHistoricalPairs':len(historical_rows)}

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
