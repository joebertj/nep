#!/usr/bin/env python3
"""Collate generated project-repeat sections, preserving their tables and evidence."""
import csv
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'
SECTION=re.compile(r'<section\b[^>]*>(?:(?!<section\b).)*?</section>',re.S)
CACHE=OUT/'repeat_page_fragments.json'

def build():
    from analyze_mpb_proximity import build as build_proximity,render as render_proximity
    proximity=build_proximity()
    from build_report_heroes import STYLE
    from build_investigation_summary import CSS,JS
    fragments=json.loads(CACHE.read_text()) if CACHE.exists() else {}
    sources={'dpwh.html': [('history','Potential repeated line items:'),('survival','id="repeat-hgab-survival"'),('within','id="within-stage-repeats"')],
             'fmr.html':[('fmr','Potential FMR repeats:')], 'nia.html':[('nia','Potential NIA irrigation repeats:')]}
    for name,targets in sources.items():
        path=STATIC/name;text=path.read_text()
        for key,marker in targets:
            found=next((m for m in SECTION.finditer(text) if marker in m[0]),None)
            if found:
                fragments[key]=found[0]
                text=text[:found.start()]+f'<p class="repeat-page-link"><a href="repeats.html#{key}">Project repeat comparisons and source evidence →</a></p>'+text[found.end():]
        if name=='dpwh.html' and ('fiveMillionBody' in text or 'priorityRepeatSearch' in text):
            # Keep allocation clustering here; move the repeat denominators.
            match=next((m for m in SECTION.finditer(text) if 'id="dpwh-investigation-evidence"' in m[0]),None)
            if match and 'Chainage evidence' in match[0] and '<h3>Exact ₱5M' in match[0]:
                start,end=match[0].split('<h3>Exact ₱5M',1)
                fragments['denominators']=start+'</section>'
                replacement='<section id="dpwh-investigation-evidence" class="investigation-evidence"><h2>Allocation clustering · exact ₱5M road/flood co-occurrence</h2><h3>Exact ₱5M'+end
                text=text[:match.start()]+replacement+text[match.end():]
            text=re.sub(r'function drawPriorityRepeats\(\)\{(?:if\(!priorityRepeatSearch\)return;)*', 'function drawPriorityRepeats(){if(!priorityRepeatSearch)return;',text)
            text=re.sub(r'(?:if\(priorityRepeatSearch\))*priorityRepeatSearch.oninput=', 'if(priorityRepeatSearch)priorityRepeatSearch.oninput=',text)
            text=re.sub(r'(?:if\(priorityRepeatYear\))*priorityRepeatYear.onchange=', 'if(priorityRepeatYear)priorityRepeatYear.onchange=',text)
            # The repeat hero is now on the dedicated page; the DPWH patterns
            # page retains its other allocation-pattern views.
            card='<section id="report-hero"><div class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">FY2027 DPWH · NEP allocation patterns</span><div class="repeat-hero-total"><strong>₱5M</strong><span>exact allocation clustering to review</span></div><p>Explore allocation patterns by program and implementing office.</p></div><div class="repeat-hero-detail"><p><a href="repeats.html" style="color:white">Historical and within-stage project repeat comparisons →</a></p><p>Equal amounts and statistical associations are screening leads, not findings of wrongdoing.</p></div></div></section>'
            if 'id="report-hero"' in text:
                text=re.sub(r'<section id="report-hero">.*?</section>',card,text,count=1,flags=re.S)
            else:
                text=re.sub(r'(<main\b[^>]*>)',lambda m:m[0]+card,text,count=1)
        path.write_text(text)
    mpb=STATIC/'mpb.html'
    if mpb.exists():
        text=mpb.read_text().replace('for(const c of configs){', "for(const c of configs.filter(c=>c.id!=='repeats')){")
        if 'id="mpb-repeat-link"' not in text:text=text.replace('<div id="sections"></div>','<p id="mpb-repeat-link"><a href="repeats.html#history">MPB historical repeats · choose Multi-purpose building in the program filter →</a></p><div id="sections"></div>')
        mpb.write_text(text)
    required={'history','survival','within','fmr','nia','denominators'}
    if not required.issubset(fragments):raise ValueError('Missing repeat sections: '+str(required-set(fragments)))
    CACHE.write_text(json.dumps(fragments,ensure_ascii=False,indent=2)+'\n')
    # Keep the original historical IDs and controls, so table/graph filters and
    # CSV exports remain useful after moving the section.
    history=fragments['history']
    history=re.sub(r'<section id="report-hero">.*?</section>','',history,flags=re.S)
    history=re.sub(r'<div class="repeat-hero"[^>]*>.*?(?=<h2>)','',history,flags=re.S)
    history=re.sub(r'<canvas\b[^>]*id="repeatGraph"[^>]*>.*?</canvas>', '<div id="repeatGraph"></div>', history, flags=re.S)
    history=history.replace('<select id="priorityRepeatYear">','<select id="repeatCategory"><option value="all">All DPWH programs</option></select><select id="priorityRepeatYear">',1)
    history=re.sub(r'<figcaption>.*?</figcaption>', '<figcaption>Potential historical comparison pairs by enacted GAA year · filtered rows</figcaption>',history,count=1,flags=re.S)
    with (OUT/'priority_program_year_on_year_candidates.csv').open(newline='',encoding='utf-8') as stream:
        candidates=list(csv.DictReader(stream))
    data=[]
    for row in candidates:
        if row['rank']!='1' or float(row.get('similarity') or 0)<0.90:
            continue
        if row['category']=='Bridge' and row.get('chainage_status')!='overlap':
            continue
        data.append({
            'category':row['category'],'project':row['name'],'source_code':row['source'],
            'office':row['office'],'region':row['region'],'amount_2027':int(float(row['amount'] or 0)),
            'comparison_year':int(row['prior_year']),'prior_project':row['prior_name'],
            'prior_amount':int(float(row['prior_amount'] or 0)),'prior_source':row['prior_source'],
            'similarity_pct':round(float(row['similarity'] or 0)*100),
            'current_chainage':row.get('current_chainage',''),'prior_chainage':row.get('prior_chainage',''),
            'chainage_overlap':row.get('chainage_overlap',''),'chainage_status':row.get('chainage_status','not stated'),
            'tranche_status':row.get('tranche_status','not stated'),'tranche_detail':row.get('tranche_detail',''),
            'tranche_conflict':row.get('tranche_conflict','False').lower()=='true'})
    data.sort(key=lambda row:(-row['similarity_pct'],row['category'],row['project'],row['comparison_year']))
    years=sorted({row['comparison_year'] for row in data},reverse=True)
    matched_projects={row['source_code'] for row in data}
    multiple_year_projects={code for code in matched_projects
                            if len({row['comparison_year'] for row in data if row['source_code']==code})>1}
    from chainage import parse_chainage
    for row in data:
        if row['chainage_status']!='overlap':continue
        left,_=parse_chainage(row['project']);right,_=parse_chainage(row['prior_project'])
        overlaps=sorted(set((max(a,c),min(b,d)) for a,b in left for c,d in right if min(b,d)>max(a,c)))
        if overlaps:
            row['overlapDiagram']={'left':row['project'],'right':row['prior_project'],'leftLabel':'FY2027 NEP',
                'rightLabel':'FY'+str(row['comparison_year'])+' GAA','leftSource':row['source_code'],'rightSource':row['prior_source'],
                'leftRanges':left,'rightRanges':right,'overlapRanges':overlaps}
    year_range=f'FY{min(years)}–FY{max(years)}' if years else 'available years'
    year_options=''.join(f'<option value="{year}">FY2027 NEP → FY{year} GAA</option>' for year in years)
    history=re.sub(r'<p class="sub">Multi-purpose buildings, roads, bridges, and flood-control projects\..*?</p>', f'<p class="sub">Multi-purpose buildings, roads, bridges and flood-control projects screened against all enacted DPWH GAA line-item data available in ODV ({year_range}). The FY2020–FY2025 annual datasets are in thousands of pesos; FY2026 uses the DPWH Details Enrolled Copy in pesos. BetterGov Budget documents enacted GAA coverage through FY2026 (<a href="https://budget.bettergov.ph/docs" target="_blank" rel="noreferrer">dataset documentation</a>); the separate FY2026 committee-amendments file is not an enacted GAA and is excluded. Filters, counts and graphs use the selected year and search. Bridge candidates require positive-length chainage overlap. Road and flood-control candidates with explicit non-overlapping ranges, including adjacent ranges that only touch at an endpoint, are excluded. Missing chainage and tranche differences require scope review. Opposing directions are excluded. Title similarity does not prove duplicated work.</p>',history,count=1,flags=re.S)
    history=re.sub(r'<select id="priorityRepeatYear">.*?</select>', '<select id="priorityRepeatYear"><option value="all">All available GAA years</option>'+year_options+'</select>',history,count=1,flags=re.S)
    survival=json.loads((OUT/'repeat_nep_hgab_survival.json').read_text())
    within=json.loads((OUT/'within_stage_repeats.json').read_text())
    hero='<div class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">Historical and within-stage project screens</span><div class="repeat-hero-total"><strong>'+str(len(data))+'</strong><span>DPWH NEP–GAA comparison pairs across '+str(len(years))+' years</span></div><div class="repeat-hero-breakdown"><strong>'+str(len(matched_projects))+'</strong><small>distinct FY2027 NEP lines with a screened match</small><strong>'+str(len(multiple_year_projects))+'</strong><small>match more than one GAA year</small></div></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown">'+''.join('<div><span>'+r['stage']+' · within-stage</span><strong>'+str(r['candidatePairs'])+' candidate pairs</strong><small>'+str(r['positiveOverlapPairs'])+' with explicit chainage overlap</small></div>' for r in within['summary'])+'</div><p>Missing chainage never establishes overlapping scope. Review source documents and engineering quantities.</p></div></div>'
    content=hero+'<p>Use the DPWH program and GAA year filters for comparisons against every available enacted year. FMR and NIA historical screens follow. HFEP currently has repeated-amount and facility review screens, not an equivalent validated historical project-repeat table; see <a href="hfep.html">HFEP</a>. Different years and stages remain separate, with their existing source and scope limits.</p><p><a href="#history">DPWH vs GAA</a> · <a href="#survival">HGAB survival</a> · <a href="#within">Within-stage comparisons</a> · <a href="#fmr">FMR</a> · <a href="#nia">NIA</a> · <a href="#denominators">Method and denominators</a></p>'
    for key,part in [('history',history),('survival',fragments['survival']),('within',fragments['within']),('fmr',fragments['fmr']),('nia',fragments['nia']),('denominators',fragments['denominators'])]:
        content+='<div id="'+key+'">'+part+'</div>'
        if key=='history':content+=render_proximity(proximity,keys=('historical',))
    style='<style>*{box-sizing:border-box}body{margin:0;font:15px/1.55 system-ui,sans-serif;color:#18303b;background:#f3f6f5}header{background:#102f3e;color:#fff;padding:32px}h1{font-size:clamp(30px,4vw,48px)}main{width:100%;padding:24px clamp(16px,2vw,32px)}a{color:#087e78}section{margin:24px 0;padding:22px;border:1px solid #c6dbd6;border-radius:14px;background:white}.tablewrap{width:100%}table{width:100%;table-layout:fixed;border-collapse:collapse}th,td{padding:9px;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;white-space:normal!important}th{background:#eef5f3}.toolbar,.pagination{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}input,select,button{font:inherit;padding:8px;border:1px solid #b6c9c4;border-radius:8px}input{flex:1;min-width:180px}svg{display:block;width:100%;height:auto;max-height:420px}.compare-track{background:#eef5f3;height:18px}.compare-track i{display:block;height:18px;background:#087e78}.comparison-graphic{margin:18px 0}</style>'
    page='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Project repeat comparisons · Budget analysis</title>'+style+STYLE+CSS+'</head><body><header><h1>Project repeat comparisons</h1><p>Past GAA, HGAB survival and possible repetition within the same budget stage.</p></header><main>'+content+'</main><script id="repeat-page-data" type="application/json">'+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+'</script>'+SCRIPT+JS+'</body></html>'
    (STATIC/'repeats.html').write_text(page);(OUT/'repeats.html').write_text(page)
    # Update links to the corresponding moved section IDs on the new page.
    for p in STATIC.glob('*.html'):
        text=p.read_text().replace('dpwh.html#repeat-hgab-survival','repeats.html#repeat-hgab-survival').replace('dpwh.html#within-stage-repeats','repeats.html#within-stage-repeats')
        p.write_text(text)
    for fname in ['summary-data.json']:
        p=STATIC/fname;p.write_text(p.read_text().replace('dpwh.html#repeat-hgab-survival','repeats.html#repeat-hgab-survival'))
    from build_five_million_evidence import apply as restore_clustering
    restore_clustering()
    return {'page':'repeats.html','historicalDpwhPairs':len(data),'collatedSections':sorted(required)}

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
const start=page*25;body.innerHTML=filtered.slice(start,start+25).map(r=>'<tr data-chainage-pair="'+esc(JSON.stringify([r.source_code,String(r.comparison_year),r.prior_source]))+'">'+[r.category,r.project,r.current_chainage,r.office,(r.congressional_representatives||[]).join('; ')||'—',peso(r.amount_2027),'FY'+r.comparison_year,r.prior_project,r.prior_chainage,r.chainage_status+(r.chainage_overlap?' · '+r.chainage_overlap:'')+' · '+r.tranche_status+(r.category==='Multi-purpose building'?' · Printed-point separation: '+(r.distanceMeters!=null?Number(r.distanceMeters).toLocaleString('en-PH')+' meters':'Not established')+' · '+r.barangayEvidence:''),peso(r.prior_amount),r.similarity_pct+'%',r.prior_source].map((v,i)=>'<td'+(i===9?' data-chainage-evidence="true"':'')+'>'+(i===9?evidenceCell(v,r):esc(v))+'</td>').join('')+'</tr>').join('');pager.innerHTML='<button id="repeatPrev">Previous</button><span>'+filtered.length+' filtered pairs · page '+(page+1)+'</span><button id="repeatNext">Next</button>';document.getElementById('repeatPrev').disabled=page===0;document.getElementById('repeatNext').disabled=start+25>=filtered.length;document.getElementById('repeatPrev').onclick=()=>{page--;draw()};document.getElementById('repeatNext').onclick=()=>{page++;draw()};
const graph=document.getElementById('repeatGraph');if(graph){const years=[...new Set(filtered.map(r=>Number(r.comparison_year)))].sort((a,b)=>b-a),counts=years.map(y=>filtered.filter(r=>Number(r.comparison_year)===y).length),max=Math.max(...counts,1),height=54+years.length*38;graph.innerHTML='<svg viewBox="0 0 900 '+height+'" role="img" aria-label="Filtered historical comparison pairs by enacted GAA year">'+years.map((y,i)=>{const n=counts[i],width=560*n/max,top=34+i*38;return '<text x="8" y="'+(top+17)+'" font-size="14" font-weight="700">FY'+y+'</text><rect x="100" y="'+top+'" width="560" height="22" rx="7" fill="#e7efed"/><rect x="100" y="'+top+'" width="'+width+'" height="22" rx="7" fill="#087e78"/><text x="675" y="'+(top+17)+'" font-size="14">'+n.toLocaleString('en-PH')+' pairs</text>'}).join('')+'</svg>'}}
for(const el of [search,year,category])el.oninput=el.onchange=()=>{page=0;draw()};
function download(name,rows){const csv=rows.map(r=>r.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
const btn=document.getElementById('repeatCsv');if(btn)btn.onclick=()=>{const keys=Object.keys(D[0]);download('dpwh_historical_filtered.csv',[keys,...filtered.map(r=>keys.map(k=>Array.isArray(r[k])?r[k].join('; '):r[k]))])};
window.downloadReportTable=(id,name)=>download(name,[...document.getElementById(id).rows].map(r=>[...r.cells].map(c=>c.innerText)));
draw();})();</script>'''
