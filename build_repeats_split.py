#!/usr/bin/env python3
"""Page renderers for the separate current and historical project-repeat reports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
OUT = ROOT / 'analysis_output'

def build_repeats_page(fragments):
    within = fragments['within']
    within = within.replace('<h3>FY2027 NEP · first 50 review pairs</h3>', '<h3 id="inter-nep">FY2027 NEP · first 50 review pairs</h3>')
    within = within.replace('<h3>FY2027 HGAB 3rd · first 50 review pairs</h3>', '<h3 id="inter-hgab">FY2027 HGAB 3rd · first 50 review pairs</h3>')
    survival = fragments['survival']
    fmr = fragments['fmr']
    nia = fragments['nia']

    common_style = '''<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f5;color:#18303b;font:15px/1.55 system-ui,sans-serif}main{width:100%;padding:24px clamp(16px,2vw,32px)}section{margin:20px 0;padding:22px;border:1px solid #c6dbd6;border-radius:14px;background:#fff}.repeat-hero{padding:22px;border-left:7px solid #FCD116;border-radius:14px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff}.repeat-hero h2{margin:0 0 8px;color:#fff}.repeat-hero p{margin:0}.toolbar,.pagination{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.toolbar input,.toolbar select{font:inherit;padding:8px;border:1px solid #b6c9c4;border-radius:8px}.toolbar input{min-width:min(320px,100%);flex:1}button{font:inherit;padding:8px 12px;border:1px solid #0038A8;border-radius:8px;background:#fff;color:#0038A8;cursor:pointer}button:hover{background:#eef3fb}button:disabled{opacity:.45;cursor:not-allowed}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:9px;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;text-align:left}th{background:#eef5f3}.num{white-space:nowrap;text-align:right}.repeat-summary{display:flex;flex-wrap:wrap;gap:10px}.repeat-summary strong{font-size:1.35rem}.historical-hero-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0}.historical-hero-metrics>div{padding:12px;border:1px solid #ffffff55;border-radius:10px;background:#ffffff12}.historical-hero-metrics strong{display:block;font-size:clamp(22px,3vw,32px);font-variant-numeric:tabular-nums}.historical-hero-metrics span{display:block;font-size:13px}.year-chart{overflow:auto}.year-chart svg{display:block;width:100%;min-width:660px;height:auto}.year-chart-legend{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0 0;font-size:13px}.year-chart-legend span::before{content:'';display:inline-block;width:11px;height:11px;margin-right:6px;border-radius:3px;background:#FCD116}.year-chart-legend span+span::before{background:#6de0d4}.repeat-nav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.repeat-nav a{padding:7px 10px;border:1px solid #b6c9c4;border-radius:8px;background:#fff;color:#0038A8;text-decoration:none;font-weight:650}
</style>'''
    from uniform_report_menu import apply_page
    from review_report_language import NOTICE

    def publish(filename, title, teaser, body, extra_script=''):
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title} | BetterGov</title>{common_style}</head><body><header><div class="eyebrow">BetterGov · Budget research</div><h1>{title}</h1><p>{teaser}</p></header>'
                f'<main>{NOTICE}{body}{extra_script}</main></body></html>')
        html = apply_page(html, filename)
        from report_currency_module import format_tables
        html,_=format_tables(html)
        if filename == 'repeats.html':
            from chainage_overlap_module import build_asset, publish_asset, attach_viewer
            overlap_asset,_=build_asset()
            overlap_version=publish_asset(overlap_asset)
            html=attach_viewer(html,overlap_version)
        from report_table_presentation import apply_page_table_module
        html,_=apply_page_table_module(filename,html)
        html = '\n'.join(line.rstrip() for line in html.splitlines()) + '\n'
        return html

    body_2027 = (
        '<section class="repeat-hero"><h2>2027-only comparison sets</h2>'
        '<p>Review similar line items within the NEP, within HGAB 3rd reading, and across NEP-to-HGAB. Historical GAA comparisons are on <a href="repeats-historical.html">Project repeats · Historical</a>.</p></section>'
        '<nav class="repeat-nav" aria-label="2027 repeat sections"><a href="#inter-nep">Within NEP</a><a href="#inter-hgab">Within HGAB</a><a href="#repeat-hgab-survival">NEP ↔ HGAB</a><a href="#fmr">FMR</a><a href="#nia">NIA</a></nav>'
        + within + survival + '<section id="fmr">' + fmr + '</section><section id="nia">' + nia + '</section>'
    )
    html=publish('repeats.html', 'Project repeats · 2027', 'Compare 2027 line items within each budget stage and across NEP and HGAB.', body_2027)

    return {'page':'repeats.html','html':html,'withinSections':['Inter-NEP','Inter-HGAB','Inter-NEP-HGAB']}


def build_repeats_historical_page():
    dpwh = json.loads((STATIC / 'dpwh-data.json').read_text(encoding='utf-8'))
    nep_rows = [row for row in dpwh.get('priorityRepeats', [])
                if 2016 <= int(row.get('comparison_year') or 0) <= 2026]
    hgab_data = json.loads((STATIC / 'repeat-hgab-historical-gaa.json').read_text(encoding='utf-8'))
    historical_rows = hgab_data.get('rows', [])
    payload = {
        'scope': 'Historical comparisons from 2027 NEP to enacted DPWH GAAs FY2016–FY2026, plus exact-title/location HGAB 3rd-reading recurrence in historical DPWH GAA data. FY2015 grouped PAP rows are excluded because they are not project-level records compatible with title matching.',
        'nepVsGaa': {'rows': nep_rows, 'years': sorted({int(r['comparison_year']) for r in nep_rows})},
        'hgabVsGaa': hgab_data,
    }
    data_path = STATIC / 'repeats-historical-data.json'
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    version = hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:12]

    common_style = '''<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f5;color:#18303b;font:15px/1.55 system-ui,sans-serif}main{width:100%;padding:24px clamp(16px,2vw,32px)}section{margin:20px 0;padding:22px;border:1px solid #c6dbd6;border-radius:14px;background:#fff}.repeat-hero{padding:22px;border-left:7px solid #FCD116;border-radius:14px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff}.repeat-hero h2{margin:0 0 8px;color:#fff}.repeat-hero p{margin:0}.toolbar,.pagination{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.toolbar input,.toolbar select{font:inherit;padding:8px;border:1px solid #b6c9c4;border-radius:8px}.toolbar input{min-width:min(320px,100%);flex:1}button{font:inherit;padding:8px 12px;border:1px solid #0038A8;border-radius:8px;background:#fff;color:#0038A8;cursor:pointer}button:hover{background:#eef3fb}button:disabled{opacity:.45;cursor:not-allowed}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:9px;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;text-align:left}th{background:#eef5f3}.num{white-space:nowrap;text-align:right}.repeat-summary{display:flex;flex-wrap:wrap;gap:10px}.repeat-summary strong{font-size:1.35rem}.historical-hero-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0}.historical-hero-metrics>div{padding:12px;border:1px solid #ffffff55;border-radius:10px;background:#ffffff12}.historical-hero-metrics strong{display:block;font-size:clamp(22px,3vw,32px);font-variant-numeric:tabular-nums}.historical-hero-metrics span{display:block;font-size:13px}.year-chart{overflow:auto}.year-chart svg{display:block;width:100%;min-width:660px;height:auto}.year-chart-legend{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0 0;font-size:13px}.year-chart-legend span::before{content:'';display:inline-block;width:11px;height:11px;margin-right:6px;border-radius:3px;background:#FCD116}.year-chart-legend span+span::before{background:#6de0d4}.repeat-nav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.repeat-nav a{padding:7px 10px;border:1px solid #b6c9c4;border-radius:8px;background:#fff;color:#0038A8;text-decoration:none;font-weight:650}
</style>'''
    from uniform_report_menu import apply_page
    from review_report_language import NOTICE

    def publish(filename, title, teaser, body, extra_script=''):
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title} | BetterGov</title>{common_style}</head><body><header><div class="eyebrow">BetterGov · Budget research</div><h1>{title}</h1><p>{teaser}</p></header>'
                f'<main>{NOTICE}{body}{extra_script}</main></body></html>')
        html = apply_page(html, filename)
        from report_currency_module import format_tables
        html,_=format_tables(html)
        if filename == 'repeats.html':
            from chainage_overlap_module import build_asset, publish_asset, attach_viewer
            overlap_asset,_=build_asset()
            overlap_version=publish_asset(overlap_asset)
            html=attach_viewer(html,overlap_version)
        from report_table_presentation import apply_page_table_module
        html,_=apply_page_table_module(filename,html)
        html = '\n'.join(line.rstrip() for line in html.splitlines()) + '\n'
        return html

    historical_body = '''
<section class="repeat-hero"><h2>Historical GAA title comparisons</h2><p>Compare FY2027 NEP candidates and HGAB exact-title-and-place matches with enacted DPWH GAA records. These are review leads, not findings of duplicate construction, contracts or payments.</p><div class="historical-hero-metrics"><div><strong id="hero-nep-count">—</strong><span>NEP-to-GAA comparison pairs</span></div><div><strong id="hero-hgab-count">—</strong><span>HGAB-to-GAA comparison pairs</span></div><div><strong id="hero-year-count">—</strong><span>historical GAA years</span></div></div><p>FY2016–FY2019 and FY2020–FY2026 are included where project-level detail is available. FY2019 uses the DBM technical DPWH GAA schedule. FY2015 PAP groups are excluded because their codes do not identify unique projects. <a href="gaa-2015-dpwh-technical.html">Search FY2015 parsed lines</a>.</p></section><section class="year-chart-panel"><h2>Comparison pairs by GAA year</h2><p>The chart updates with the year and search filters in both comparison tables.</p><div id="historical-year-chart" class="year-chart" role="img" aria-label="Filtered historical comparison pairs by year"></div><div class="year-chart-legend"><span>NEP title candidates</span><span>HGAB exact title and place</span></div></section>
<section id="nep-historical"><h2>FY2027 NEP vs enacted DPWH GAA · FY2016–FY2026</h2><p>Ranked title candidates from the NEP against prior enacted DPWH GAA records. FY2019 is included using the DBM technical schedule; FY2015 PAP groups are incompatible with this project-level matching method and excluded. Amounts and source titles remain separate for review.</p><div class="repeat-summary"><span><strong id="nep-count">—</strong> comparison pairs</span><span><strong id="nep-years">—</strong> GAA years</span></div><div class="toolbar"><label>GAA year <select id="nep-year"><option value="all">All years</option></select></label><input id="nep-search" type="search" placeholder="Search title, office, or source"><button id="nep-export">Export CSV</button></div><div class="tablewrap"><table><thead><tr><th>NEP project · category</th><th>Office</th><th>GAA year</th><th>Historical GAA title · source</th><th class="num">NEP amount</th><th class="num">GAA amount</th><th>Title score</th></tr></thead><tbody id="nep-body"></tbody></table></div><div class="pagination"><button id="nep-prev">Previous</button><span id="nep-page">Page 1</span><button id="nep-next">Next</button></div><p id="nep-status" class="note"></p></section>
<section id="hgab-historical"><h2>HGAB 3rd vs historical GAA · exact title and place</h2><p>HGAB lines with an exact normalized title and qualified municipality/province match in the available FY2016–FY2019 DPWH source layers and FY2020–FY2026 GAA records. FY2019 uses DBM’s technical DPWH schedule. FY2015 source records are available, but are not included in exact-title counts for the PAP-code and title-structure reasons described above.</p><div class="repeat-summary"><span><strong id="hgab-count">—</strong> comparison pairs</span><span><strong id="hgab-projects">—</strong> HGAB lines</span><span><strong id="hgab-years">—</strong> GAA years</span></div><div class="toolbar"><label>GAA year <select id="hgab-year"><option value="all">All years</option></select></label><input id="hgab-search" type="search" placeholder="Search HGAB title, GAA title, office, or source"><button id="hgab-export">Export CSV</button></div><div class="tablewrap"><table><thead><tr><th>HGAB project · office · page</th><th>GAA year</th><th>Historical GAA title · source</th><th class="num">HGAB amount</th><th class="num">GAA amount</th><th class="num">Change</th><th>Chainage evidence</th></tr></thead><tbody id="hgab-body"></tbody></table></div><div class="pagination"><button id="hgab-prev">Previous</button><span id="hgab-page">Page 1</span><button id="hgab-next">Next</button></div><p id="hgab-status" class="note"></p></section>
'''
    hist_script = f'''<script>
(async()=>{{const D=await fetch('repeats-historical-data.json?v={version}').then(r=>{{if(!r.ok)throw Error(r.status);return r.json()}}),$=id=>document.getElementById(id),peso=n=>'₱'+Number(n||0).toLocaleString('en-PH'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const nep=D.nepVsGaa.rows,hgab=D.hgabVsGaa.rows,size=50;let pn=0,ph=0,nf=[],hf=[];
function initYear(select,years){{for(const y of years){{const o=document.createElement('option');o.value=y;o.textContent='FY'+y+' GAA';$(select).append(o)}}}}
initYear('nep-year',D.nepVsGaa.years);initYear('hgab-year',D.hgabVsGaa.summary.years);$('hero-nep-count').textContent=nep.length.toLocaleString('en-PH');$('hero-hgab-count').textContent=hgab.length.toLocaleString('en-PH');$('hero-year-count').textContent=[...new Set([...D.nepVsGaa.years,...D.hgabVsGaa.summary.years])].length.toLocaleString('en-PH');
function drawYearChart(){{const chart=$('historical-year-chart'),counts=new Map();for(const r of nf){{const y=Number(r.comparison_year);counts.set(y,counts.get(y)||{{nep:0,hgab:0}});counts.get(y).nep++}}for(const r of hf){{const y=Number(r.gaaYear);counts.set(y,counts.get(y)||{{nep:0,hgab:0}});counts.get(y).hgab++}}const years=[...counts.keys()].filter(Boolean).sort((a,b)=>a-b),max=Math.max(1,...years.flatMap(y=>[counts.get(y).nep,counts.get(y).hgab])),height=40+years.length*46;chart.innerHTML=years.length?'<svg viewBox=\"0 0 850 '+height+'\" role=\"img\" aria-label=\"Filtered historical comparison pairs by GAA year\">'+years.map((y,i)=>{{const d=counts.get(y),top=14+i*46,w1=520*d.nep/max,w2=520*d.hgab/max;return '<text x=\"4\" y=\"'+(top+24)+'\" font-size=\"13\" font-weight=\"700\">FY'+y+'</text><rect x=\"64\" y=\"'+top+'\" width=\"520\" height=\"14\" rx=\"4\" fill=\"#ffffff44\"/><rect x=\"64\" y=\"'+top+'\" width=\"'+w1+'\" height=\"14\" rx=\"4\" fill=\"#FCD116\"/><text x=\"594\" y=\"'+(top+12)+'\" font-size=\"12\">'+d.nep+'</text><rect x=\"64\" y=\"'+(top+18)+'\" width=\"520\" height=\"14\" rx=\"4\" fill=\"#ffffff44\"/><rect x=\"64\" y=\"'+(top+18)+'\" width=\"'+w2+'\" height=\"14\" rx=\"4\" fill=\"#6de0d4\"/><text x=\"594\" y=\"'+(top+30)+'\" font-size=\"12\">'+d.hgab+'</text>'}}).join('')+'</svg>':'<p>No comparison pairs match the selected filters.</p>'}}

function drawNep(){{const q=$('nep-search').value.toLowerCase().trim(),y=$('nep-year').value;nf=nep.filter(r=>(y==='all'||String(r.comparison_year)===y)&&JSON.stringify(r).toLowerCase().includes(q)).sort((a,b)=>b.similarity_pct-a.similarity_pct);const pages=Math.max(1,Math.ceil(nf.length/size));pn=Math.min(pn,pages-1);$('nep-body').innerHTML=nf.slice(pn*size,(pn+1)*size).map(r=>'<tr><td>'+esc(r.project)+'<br><small>'+esc(r.category)+'</small></td><td>'+esc(r.office)+'</td><td>FY'+r.comparison_year+'</td><td>'+esc(r.prior_project)+'<br><small>'+esc(r.prior_source)+'</small></td><td class="num">'+peso(r.amount_2027)+'</td><td class="num">'+peso(r.prior_amount)+'</td><td>'+Number(r.similarity_pct||0)+'%</td></tr>').join('')||'<tr><td colspan="7">No matching records.</td></tr>';$('nep-page').textContent='Page '+(pn+1)+' of '+pages+' · '+nf.length.toLocaleString()+' pairs';$('nep-prev').disabled=pn===0;$('nep-next').disabled=pn>=pages-1;$('nep-count').textContent=nep.length.toLocaleString('en-PH');$('nep-years').textContent=D.nepVsGaa.years.length.toLocaleString('en-PH');$('nep-status').textContent=nf.length.toLocaleString('en-PH')+' filtered title candidates; similarity is a screen, not a duplicate finding.';drawYearChart()}}
function drawHgab(){{const q=$('hgab-search').value.toLowerCase().trim(),y=$('hgab-year').value;hf=hgab.filter(r=>(y==='all'||String(r.gaaYear)===y)&&JSON.stringify(r).toLowerCase().includes(q));const pages=Math.max(1,Math.ceil(hf.length/size));ph=Math.min(ph,pages-1);$('hgab-body').innerHTML=hf.slice(ph*size,(ph+1)*size).map(r=>'<tr><td>'+esc(r.projectName)+'<br><small>'+esc(r.office)+' · '+esc(r.sourceVolume)+' · p.'+esc(r.sourcePage)+'</small></td><td>FY'+r.gaaYear+'</td><td>'+esc(r.gaaTitle)+'<br><small>'+esc(r.gaaSource)+'</small></td><td class="num">'+peso(r.amountPesos)+'</td><td class="num">'+peso(r.gaaAmountPesos)+'</td><td class="num">'+(r.changePesos>=0?'+':'−')+peso(Math.abs(r.changePesos))+'</td><td>'+esc(r.chainageStatus)+(r.chainageOverlap?' · '+esc(r.chainageOverlap):'')+'</td></tr>').join('')||'<tr><td colspan="7">No matching records.</td></tr>';$('hgab-page').textContent='Page '+(ph+1)+' of '+pages+' · '+hf.length.toLocaleString()+' pairs';$('hgab-prev').disabled=ph===0;$('hgab-next').disabled=ph>=pages-1;$('hgab-count').textContent=hgab.length.toLocaleString('en-PH');$('hgab-projects').textContent=D.hgabVsGaa.summary.hgabOccurrences.toLocaleString('en-PH');$('hgab-years').textContent=D.hgabVsGaa.summary.years.length.toLocaleString('en-PH');$('hgab-status').textContent=hf.length.toLocaleString('en-PH')+' filtered exact-title and qualified-place comparisons.';drawYearChart()}}
function csv(name,rows,keys){{const out=[keys,...rows.map(r=>keys.map(k=>r[k]))].map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\\r\\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+out],{{type:'text/csv;charset=utf-8'}}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}}
for(const id of ['nep-search','nep-year'])$(id).oninput=$(id).onchange=()=>{{pn=0;drawNep()}};for(const id of ['hgab-search','hgab-year'])$(id).oninput=$(id).onchange=()=>{{ph=0;drawHgab()}};
for(const [prefix,setPage,draw] of [['nep',v=>pn=v,drawNep],['hgab',v=>ph=v,drawHgab]]){{$(`${{prefix}}-prev`).onclick=()=>{{setPage(prefix==='nep'?pn-1:ph-1);draw()}};$(`${{prefix}}-next`).onclick=()=>{{setPage(prefix==='nep'?pn+1:ph+1);draw()}}}}
$('nep-export').onclick=()=>csv('nep-historical-gaa-repeats.csv',nf,['category','project','office','comparison_year','prior_project','amount_2027','prior_amount','similarity_pct','prior_source']);$('hgab-export').onclick=()=>csv('hgab-historical-gaa-repeats.csv',hf,['hgabId','projectName','office','gaaYear','gaaTitle','amountPesos','gaaAmountPesos','changePesos','gaaSource','chainageStatus','chainageOverlap']);drawNep();drawHgab()}})().catch(e=>{{document.getElementById('nep-status').textContent='Historical repeat data unavailable: '+e.message}});
</script>'''
    html=publish('repeats-historical.html', 'Project repeats · Historical', 'Compare project titles against enacted historical GAA records.', historical_body, hist_script)
    return {'page':'repeats-historical.html','html':html,'dataFilename':'repeats-historical-data.json','data':serialized,'nepVsGaaPairs':len(nep_rows),'hgabVsGaaPairs':len(historical_rows)}
