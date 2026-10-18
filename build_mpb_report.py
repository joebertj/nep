#!/usr/bin/env python3
"""Build a standalone MPB report from existing audited stage comparisons."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from build_report_heroes import STYLE
from hgab_matching import UNMATCHED, is_fap

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
CATEGORY = 'BIP - Multi-Purpose Buildings/ Facilities to support Social Services'


def build():
    from analyze_mpb_proximity import build as build_proximity,render as render_proximity
    proximity=build_proximity()
    inputs = ['hb_nep_comparison_3rd.csv', 'nep_dpwh_baseline.json',
              'dpwh_removals_3rd.json', 'repeat_nep_hgab_survival.json',
              'congress_geographic_attribution_db_3rd.json']
    with (OUT / inputs[0]).open() as f:
        rows = [r for r in csv.DictReader(f) if r['pap3'] == CATEGORY]
    attribution = {r['id']: r for r in json.loads((OUT / inputs[4]).read_text())['projects']}
    for row in rows:
        for key in ['amountPesos', 'amount_delta_pesos', 'closest_nep_amount_pesos']:
            row[key] = int(float(row[key])) if row[key] else None
        row['representatives'] = '; '.join(attribution.get(row['hgab_id'], {}).get('representatives', []))
        row['legDistricts'] = '; '.join(attribution.get(row['hgab_id'], {}).get('districts', []))
        row['buildingType'] = ('Evacuation center' if 'evacuation' in row['projectName'].lower() else
                               'School / educational facility' if any(w in row['projectName'].lower() for w in ('school', 'classroom', 'college', 'university')) else
                               'Other / unspecified building')
    insertions = [r for r in rows if r['comparison'] == UNMATCHED and not is_fap(r)]
    ambiguous = [r for r in rows if r['comparison'] not in (UNMATCHED, 'Exact normalized title found in NEP')]
    adjustments = [r for r in rows if r['paired_one_to_one'] == 'True' and r['amount_delta_pesos'] not in (None, 0)]
    baseline = json.loads((OUT / inputs[1]).read_text())['data']['data']
    mpb_ids = {r['id'] for r in baseline if r['pap3'] == CATEGORY}
    removals = [r for r in json.loads((OUT / inputs[2]).read_text())['domestic']['rows'] if r['nepId'] in mpb_ids]
    survival = json.loads((OUT / inputs[3]).read_text())
    repeats = [r for r in survival['comparisonPairs'] if r['category'] == 'Multi-purpose building']
    prices = []
    groups = defaultdict(list)
    for row in rows:
        groups[(row['buildingType'], row['amountPesos'])].append(row)
    for (kind, amount), group in groups.items():
        prices.append({'buildingType': kind, 'amountPesos': amount, 'projects': len(group),
                       'totalPesos': amount * len(group), 'offices': len({r['office'] for r in group})})
    distribution = []
    offices = defaultdict(list)
    for row in rows:
        offices[(row['region'], row['office'])].append(row)
    for (region, office), group in offices.items():
        added = [r for r in group if r in insertions]
        distribution.append({'region': region, 'office': office, 'projects': len(group),
                             'amountPesos': sum(r['amountPesos'] for r in group),
                             'insertionCount': len(added), 'insertionPesos': sum(r['amountPesos'] for r in added)})
    summary = {'hgabLines': len(rows), 'hgabPesos': sum(r['amountPesos'] for r in rows),
               'insertionCandidates': len(insertions), 'insertionPesos': sum(r['amountPesos'] for r in insertions),
               'ambiguousLines': len(ambiguous), 'ambiguousPesos': sum(r['amountPesos'] for r in ambiguous),
               'repeatPairs': len(repeats), 'repeatProposals': len({r['source_code'] for r in repeats}),
               'removalCandidates': len(removals), 'removalPesos': sum(r['nepPesos'] for r in removals),
               'adjustedLines': len(adjustments)}
    data = {'category': CATEGORY, 'summary': summary, 'insertions': insertions, 'ambiguous': ambiguous,
            'adjustments': adjustments, 'removals': removals, 'repeats': repeats, 'prices': prices,
            'distribution': distribution,'coordinateProximity':proximity,
            'sources': [{'file': name, 'sha256': hashlib.sha256((OUT / name).read_bytes()).hexdigest()} for name in inputs]}
    serialized = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'mpb_analysis.json').write_text(serialized)
    (STATIC / 'mpb-data.json').write_text(serialized)
    html = PAGE.replace('__HERO_STYLE__', STYLE).replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
    html=html.replace('<div id="sections"></div>','<p><a href="repeats.html#mpb-coordinate-proximity">Historical MPB repeat-location distances →</a></p>'+render_proximity(proximity,keys=('current',))+'<div id="sections"></div>')
    from build_investigation_summary import JS as evidence_exports
    html=html.replace('</body>',evidence_exports+'</body>')
    (STATIC / 'mpb.html').write_text(html)
    (OUT / 'mpb.html').write_text(html)
    return data


PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPB · Multi-purpose building allocations</title>
<style>body{margin:0;background:#eef3f4;color:#18303b;font:16px/1.5 system-ui,sans-serif}header{background:#142e3b;color:white;padding:24px 2vw}h1{margin:0;font-size:30px}main{padding:24px 2vw;max-width:none}section.card{background:white;border:1px solid #ccdcd8;border-radius:14px;padding:24px;margin:24px 0}h2{margin-top:0}a{color:#087e78}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.controls input,.controls select,.controls button{font:inherit;padding:8px;border:1px solid #a8bbb6;border-radius:8px}.export{background:#b65b09;color:white;font-weight:700}.controls input{flex:1;min-width:180px}table{width:100%;table-layout:fixed;border-collapse:collapse}th,td{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;white-space:normal}th{background:#edf4f2}figure{margin:16px 0}svg{display:block;width:100%;height:auto;max-height:420px}.note{color:#526773}.caution{padding:14px;background:#fff4dd;border-left:4px solid #ba7800}@media(max-width:650px){th,td{font-size:12px;padding:6px}section.card{padding:14px}}</style>__HERO_STYLE__</head><body><header><h1>MPB · Multi-purpose building allocations</h1><p>FY2027 NEP → HGAB 3rd reading · historical enacted GAA comparisons</p></header><main>
<div id="hero"></div>
<section class="card"><h2>What this page measures</h2><p>This page covers the BIP multi-purpose buildings/facilities PAP, including records named as evacuation centers. Category membership follows the parsed PAP, not a keyword search across every DPWH program. Titles, pages and amounts are retained from the current comparison.</p><p class="caution">Potential insertions have no plausible NEP counterpart identified by the current matching. They are review candidates, not certified new amendments. Ambiguous matches are separate. Budget amounts are appropriations, not expenditures or personal receipts; no finding establishes misconduct.</p><p><a href="mpb-data.json" download>Download complete analysis JSON</a> · <a href="dpwh-hgab.html">Full DPWH comparison and matching methodology</a></p></section>
<div id="sections"></div>
<section class="card"><h2>Supporting methodology and limitations</h2><ul><li>Insertion screening uses the same current native NEP/HGAB occurrence matching as the DPWH HGAB page. FAPs are excluded from domestic insertion candidates. A selected one-to-one counterpart is required for an allocation adjustment; approximate title similarity alone does not establish one.</li><li>Removal candidates are unpaired NEP records in this exact PAP. An absent selected link is not proof of deletion. Changes in wording, office, scope or aggregation can hide counterparts.</li><li>Repeat comparisons are FY2027 NEP versus available prior-year enacted GAA. The same NEP project can appear in multiple comparison years: comparison pairs and distinct proposals are different denominators. HGAB retention follows selected links; a missing link is not a confirmed removal.</li><li>Directions, tranches and explicit chainage remain part of the inherited repeat screen. Repeated building names do not establish duplicate components or paid work. Barangay/town/province homonyms require qualified geographic evidence.</li><li>Building types are a simple title-based descriptive split. Other/unspecified includes mixed uses and titles without clear purpose. Equal allocation amounts are not equal unit costs: floor area, design, quantities and site conditions are unavailable.</li><li>Office totals are administrative allocations, not legislative district totals. Names in project tables come from existing strict PH location DB attribution; blank cells mean unresolved or shared coverage. No name determines screening eligibility.</li><li>Graphs reflect the current table filters. Ranked project and office graphs show up to 12 rows; table counts and CSV include all filtered rows. Repeat graphs count all filtered comparison pairs by retention status. No hypothesis test or corruption probability is inferred from these descriptive plots.</li></ul><p>Request original-page adjudication, approved designs, floor areas, bills of quantities, contracts, project completion and disbursement records before drawing conclusions. MPB findings overlap the full DPWH insertion and repeat findings; their amounts must not be added together.</p><h3>Sources and reproducibility</h3><p>Local FY2027 NEP DPWH baseline; HB 10858 3rd-reading Volume I-C; native comparison/removal records; historical GAA repeat screen; PH location DB strict attribution. <a href="mpb-data.json">Analysis JSON</a> records each input filename and SHA256. Source pages are listed per project. All monetary exports contain numeric pesos.</p></section>
</main><script id="mpb-data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('mpb-data').textContent),S=D.summary;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+num(v),short=v=>'₱'+(v/1e9).toFixed(2)+'B';
document.getElementById('hero').innerHTML=`<section class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">MPB · NEP → HGAB 3rd reading</span><div class="repeat-hero-total"><strong>${num(S.insertionCandidates)}</strong><span>potential insertion candidates</span></div><p>${short(S.insertionPesos)} without a plausible NEP counterpart identified</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><span>HGAB MPB schedule</span><strong>${num(S.hgabLines)} lines · ${short(S.hgabPesos)}</strong></div><div><span>Ambiguous counterparts</span><strong>${num(S.ambiguousLines)} lines · ${short(S.ambiguousPesos)}</strong></div><div><span>Historical repeat screen</span><strong>${S.repeatPairs} pairs · ${S.repeatProposals} NEP projects</strong></div></div><p>Screening candidates require original-source and scope review.</p></div></section>`;
const projectColumns=[['Project','projectName'],['Office','office'],['LEG · strict attribution','legDistricts'],['Representative · geographic coverage','representatives'],['Building type','buildingType'],['HGAB allocation pesos','amountPesos'],['Closest NEP title · not necessarily a match','closest_nep_title'],['Matching basis','match_basis'],['Source volume','sourceVolume'],['HGAB page','sourcePage']];
const configs=[
{id:'insertions',title:'Potential insertions · no plausible NEP counterpart identified',note:'Domestic HGAB lines only. This bucket excludes ambiguous counterparts; verify original NEP and HGAB pages before confirming an insertion.',columns:projectColumns,metric:'amountPesos',chart:'bars'},
{id:'ambiguous',title:'Ambiguous counterparts · kept outside insertion totals',note:'Potential, multiple or already-paired counterparts require scope/occurrence review. These are not certified insertions.',columns:projectColumns.concat([['Counterpart status','comparison']]),metric:'amountPesos',chart:'bars'},
{id:'adjustments',title:'Allocation adjustments · selected retained counterparts',note:'Positive and negative budget changes on selected one-to-one links; counterpart confidence remains visible. Potential title links still need scope review. These rows can overlap the ambiguous-counterpart review, but not insertion candidates.',columns:[['HGAB project','projectName'],['NEP project','closest_nep_title'],['Office','office'],['Representative · geographic coverage','representatives'],['NEP allocation pesos','closest_nep_amount_pesos'],['HGAB allocation pesos','amountPesos'],['Adjustment pesos','amount_delta_pesos'],['Counterpart confidence','comparison'],['NEP page','nep_source_page'],['HGAB page','sourcePage']],metric:'amount_delta_pesos',chart:'diverging'},
{id:'removals',title:'Potential removals · unpaired NEP lines',note:'Unpaired records are removal-review candidates. Absence of a selected counterpart does not certify deletion.',columns:[['NEP project','nepTitle'],['Office','office'],['NEP allocation pesos','nepPesos'],['Review basis','basis'],['NEP page','nepPage']],metric:'nepPesos',chart:'bars'},
{id:'repeats',title:'Historical repeat comparisons · did the NEP proposal survive into HGAB?',note:'One row per NEP–GAA comparison pair. Distinct NEP proposals are counted separately in the hero. Potential retention is not a clear retained link.',columns:[['NEP project','project'],['Office','office'],['Representative · geographic coverage','congressional_representatives'],['NEP allocation pesos','amount_2027'],['GAA year','comparison_year'],['Prior GAA project','prior_project'],['Prior GAA allocation pesos','prior_amount'],['Prior source','prior_source'],['Chainage status','chainage_status'],['Tranche status','tranche_status'],['HGAB retention','retention'],['HGAB source page','hgabPage']],metric:'amount_2027',chart:'retention'},
{id:'prices',title:'Allocation amounts by building type · repeated amounts need scope context',note:'Counts of identical appropriation amounts, grouped by descriptive building type. This is not a construction unit-price comparison.',columns:[['Building type','buildingType'],['Allocation per project pesos','amountPesos'],['Projects at this amount','projects'],['Combined allocation pesos','totalPesos'],['Offices','offices']],metric:'projects',chart:'vertical'},
{id:'distribution',title:'MPB allocations by implementing office',note:'Central Office is its own administrative bucket. An implementing office is not a congressional district.',columns:[['Region','region'],['Office','office'],['HGAB projects','projects'],['HGAB allocation pesos','amountPesos'],['Potential insertions','insertionCount'],['Potential insertion allocation pesos','insertionPesos']],metric:'amountPesos',chart:'vertical'}];
D.repeats=D.repeats.map(r=>({...r,retention:r.hgabRetention.status,hgabPage:r.hgabRetention.hgabPage}));
function graphic(rows,c,metric){
 if(!rows.length)return '<p>No matching records to plot.</p>';
 let points=rows.slice(0,12).map((r,i)=>({label:r.projectName||r.nepTitle||r.office||r.buildingType+' · '+peso(r.amountPesos),value:Number(r[metric]||0)}));
 if(c.chart==='retention'){const groups={};rows.forEach(r=>groups[r.retention]=(groups[r.retention]||0)+1);points=Object.entries(groups).map(([label,value])=>({label,value}));}
 const max=Math.max(1,...points.map(p=>Math.abs(p.value))),money=/pesos|amount/i.test(metric),fmt=v=>money?peso(v):num(v);let body='';
 if(c.chart==='bars')points.forEach((p,i)=>{let y=35+i*28;body+=`<text x="8" y="${y}" font-size="12">${esc(p.label.slice(0,48))}<title>${esc(p.label)}</title></text><rect x="340" y="${y-12}" width="${510*Math.abs(p.value)/max}" height="17" fill="#087e78"><title>${esc(p.label)}: ${fmt(p.value)}</title></rect><text x="860" y="${y}" font-size="11">${fmt(p.value)}</text>`});
 else points.forEach((p,i)=>{const step=880/points.length,x=65+i*step,w=Math.max(8,step*.65),div=c.chart==='diverging',base=div?155:255,h=(div?110:190)*Math.abs(p.value)/max,y=div?(p.value>=0?base-h:base):base-h;body+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${p.value<0?'#b65b09':'#087e78'}"><title>${esc(p.label)}: ${fmt(p.value)}</title></rect><text x="${x}" y="${y-5}" font-size="10">${fmt(p.value)}</text><text transform="translate(${x+5},280) rotate(30)" font-size="10">${esc(p.label.slice(0,30))}<title>${esc(p.label)}</title></text>`;});
 return `<svg viewBox="0 0 1030 420" role="img" aria-label="${esc(c.title)}"><title>${esc(c.title)}</title>${body}</svg>`;
}
for(const c of configs){
 const section=document.createElement('section');section.id='mpb-'+c.id;section.className='card';const choices=[...new Set(D[c.id].map(r=>r.buildingType||r.retention||r.region).filter(Boolean))].sort();
 const sortOptions=[...new Map([[c.metric,c.columns.find(([label,key])=>key===c.metric)?.[0]||c.metric],...c.columns.filter(([label,key])=>/pesos|projects|count/i.test(key)).map(([label,key])=>[key,label])]).entries()];
 section.innerHTML=`<h2>${esc(c.title)}</h2><p>${esc(c.note)}</p><div class="controls"><input type="search" aria-label="Search ${c.id}" placeholder="Filter projects, locations or source records"><select aria-label="Filter group"><option value="">All groups</option>${choices.map(v=>`<option>${esc(v)}</option>`).join('')}</select><select class="sort" aria-label="Sort metric">${sortOptions.map(([key,label])=>`<option value="${esc(key)}">${esc(label)}</option>`).join('')}</select><select class="order" aria-label="Sort direction"><option value="desc">Largest first</option><option value="asc">Smallest first</option></select><button class="export" type="button">Export CSV</button></div><figure><figcaption></figcaption><div class="graph"></div></figure><p class="count"></p><table><thead><tr>${c.columns.map(([label])=>`<th>${esc(label)}</th>`).join('')}</tr></thead><tbody></tbody></table><div class="controls"><button class="prev">Previous</button><span class="page"></span><button class="next">Next</button></div>`;
 document.getElementById('sections').append(section);let filtered=[],page=0;
 const search=section.querySelector('input'),select=section.querySelector('select'),sort=section.querySelector('.sort'),order=section.querySelector('.order');
 function render(){const q=search.value.trim().toLowerCase(),group=select.value,metric=sort.value;filtered=D[c.id].filter(r=>(!group||[r.buildingType,r.retention,r.region].includes(group))&&(!q||JSON.stringify(r).toLowerCase().includes(q))).sort((a,b)=>(Number(b[metric]||0)-Number(a[metric]||0))*(order.value==='desc'?1:-1));const pages=Math.max(1,Math.ceil(filtered.length/25));page=Math.min(page,pages-1);section.querySelector('.graph').innerHTML=graphic(filtered,c,metric);section.querySelector('figcaption').textContent=c.chart==='retention'?'Comparison pairs by HGAB retention status · all filtered rows':'First '+Math.min(12,filtered.length)+' filtered rows · '+sort.selectedOptions[0].text+' · '+order.selectedOptions[0].text;section.querySelector('.count').textContent=num(filtered.length)+' filtered rows';section.querySelector('tbody').innerHTML=filtered.slice(page*25,(page+1)*25).map(r=>'<tr>'+c.columns.map(([label,key])=>'<td>'+esc(/pesos|allocation|adjustment/i.test(label)&&r[key]!=null&&r[key]!==''?peso(r[key]):r[key]??'—')+'</td>').join('')+'</tr>').join('')||`<tr><td colspan="${c.columns.length}">No matching records.</td></tr>`;section.querySelector('.page').textContent=`Page ${page+1} of ${pages}`;section.querySelector('.prev').disabled=page===0;section.querySelector('.next').disabled=page>=pages-1;}
 [search,select,sort,order].forEach(el=>el.addEventListener(el===search?'input':'change',()=>{page=0;render()}));section.querySelector('.prev').onclick=()=>{page--;render()};section.querySelector('.next').onclick=()=>{page++;render()};section.querySelector('.export').onclick=()=>{const quote=v=>'"'+String(v??'').replaceAll('"','""')+'"',csv=[c.columns.map(([label])=>quote(label)).join(','),...filtered.map(r=>c.columns.map(([label,key])=>quote(r[key])).join(','))].join('\r\n');const url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='mpb-'+c.id+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};render();
}
</script></body></html>'''

if __name__ == '__main__':
    print(json.dumps(build()['summary'], indent=2))
