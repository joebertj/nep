#!/usr/bin/env python3
"""FMR page from audited project ledgers; geographic chords never become road length."""
import html,json,math,re,statistics,subprocess
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from build_fmr_dataset import build,ROOT,OUT,STATIC
from build_mpb_report import PAGE
from build_cost_per_km import lengths
from hgab_matching import normalize
from chainage import compare_chainage,has_directional_conflict,compare_tranche
from location_data.project_location_scope import qualified,location_conflict

MANUAL_RED_LABELS={
    'sizeable-private-property-connection':'Endpoint connects to a sizeable private property',
    'section2-visitor-venue':'Section 2 · Near a mapped visitor venue',
    'section2-subdivision-village':'Section 2 · Near a subdivision or village',
    'section2-large-residential-property':'Section 2 · Near a large residential property',
    'section2-restricted-access-property':'Section 2 · Near a restricted-access property',
    'section2-private-property-cue':'Section 2 · Near another mapped private-property cue',
    'section2-coordinate-quality':'Section 2 · Coordinate quality needs review',
    'baywalk-shoreline-review':'Baywalk / shoreline ecological review',
}

def history(data):
    from analyze_priority_repeats import query
    path=ROOT.parent/'open-data-visualization/data/parquet/budget_2025.parquet'
    old=query(f"SELECT description,amount,agency_desc FROM read_parquet('{path}') WHERE department_desc ILIKE '%Agriculture%' AND regexp_matches(upper(coalesce(description,'')), 'FARM.?TO.?MARKET| FMR ')")
    idx=defaultdict(list)
    for r in old:
        q=qualified(r['description'])
        if q and q['province'] and q['municipality']:idx[(tuple(sorted(q['province'])),tuple(sorted(q['municipality'])))].append(r)
    result=[]
    for p in data['projects']:
        q=qualified(p['title'])
        if not q or not q['province'] or not q['municipality']:continue
        candidates=[]
        for r in idx[(tuple(sorted(q['province'])),tuple(sorted(q['municipality'])))]:
            a,b=p['title'],r['description']
            if location_conflict(a,b) or has_directional_conflict(a,b):continue
            chain=compare_chainage(a,b)
            if chain['chainage_status']=='disjoint':continue
            score=SequenceMatcher(None,normalize(a),normalize(b),autojunk=False).ratio()
            if score>=.9:candidates.append((score,r,chain))
        if candidates:
            score,r,chain=max(candidates,key=lambda c:c[0]);result.append({'projectName':p['title'],'hgabId':p['project_id'],'amountPesos':p['amount_php'],'priorProject':r['description'],'priorAmountPesos':round(r['amount']*1000),'priorYear':2025,'priorSource':'ODV data/parquet/budget_2025.parquet · '+r['agency_desc'],'similarity':round(score,4),'chainage':chain,'tranche':compare_tranche(p['title'],r['description']),'sourcePage':p['source']['pdf_page']})
    return result

def google_map_links(row):
    try:
        start=(float(row['startLatitude']),float(row['startLongitude']))
        end=(float(row['endLatitude']),float(row['endLongitude']))
        if not all(math.isfinite(v) for v in (*start,*end)):
            raise ValueError('non-finite coordinates')
        if not (-90<=start[0]<=90 and -180<=start[1]<=180 and -90<=end[0]<=90 and -180<=end[1]<=180):
            raise ValueError('coordinates out of range')
    except (KeyError,TypeError,ValueError):
        return 'Map links unavailable · source coordinates missing'
    sat_start=f'https://www.google.com/maps/@{start[0]:.6f},{start[1]:.6f},17z/data=!3m1!1e3'
    sat_end=f'https://www.google.com/maps/@{end[0]:.6f},{end[1]:.6f},17z/data=!3m1!1e3'
    route='https://www.google.com/maps/dir/?api=1&origin='+f'{start[0]:.6f}%2C{start[1]:.6f}'+'&destination='+f'{end[0]:.6f}%2C{end[1]:.6f}'+'&travelmode=driving'
    return (f'<a href="{html.escape(sat_start,quote=True)}" target="_blank" rel="noopener noreferrer" title="Google Maps satellite view at the printed start coordinate">Google Maps satellite · start ↗</a>'
            f'<br><a href="{html.escape(sat_end,quote=True)}" target="_blank" rel="noopener noreferrer" title="Google Maps satellite view at the printed end coordinate">Google Maps satellite · end ↗</a>'
            f'<br><a href="{html.escape(route,quote=True)}" target="_blank" rel="noopener noreferrer" title="Google Maps suggested driving route and distance between printed endpoints; not the project alignment or straight-line measurement">Route + distance ↗</a>')


def generate():
    from build_investigation_summary import table,CSS,JS
    from report_hero_module import STYLE
    data=build();s=data['summary'];historical=history(data);(OUT/'fmr_historical_repeats_corrected.json').write_text(json.dumps(historical,ensure_ascii=False,indent=2)+'\n')
    (STATIC/'fmr-historical-repeats.json').write_text(json.dumps(historical,ensure_ascii=False,indent=2)+'\n')
    projects=[];lengthrows=[];coordinate=[];regions=defaultdict(lambda:{'projects':0,'amountPesos':0,'nepPesos':0,'nepProjects':0});prices=Counter()
    for p in data['nepProjects']:regions[p['region'].upper()].update(nepPesos=regions[p['region'].upper()]['nepPesos']+p['amount_php'],nepProjects=regions[p['region'].upper()]['nepProjects']+1)
    for p in data['projects']:
        km,status,method,_=lengths(p['title'],p['title']+'\n'+p['coordinates_raw']);row={'projectName':p['title'],'amountPesos':p['amount_php'],'region':p['region'],'sourcePage':p['source']['pdf_page'],'printedPage':p['source']['printed_page'],'sourceId':p['project_id'],'coordinateStatus':p['status'],'reviewFlags':'; '.join(p['review_flags']),'sectionCount':len(p['segments']),'statedMeters':round(km*1000,6) if km else None,'allocationPerMeterPesos':round(p['amount_php']/(km*1000),2) if km else None,'lengthEvidence':p['coordinates_raw'] if km else status}
        projects.append(row);prices[p['amount_php']]+=1;regions[p['region']]['projects']+=1;regions[p['region']]['amountPesos']+=p['amount_php']
        if km:lengthrows.append(row)
        if p['status']!='normalized':coordinate.append(row)
    totals=[{'region':k,**v,'adjustmentPesos':v['amountPesos']-v['nepPesos']} for k,v in regions.items()]
    inserts=[r for r in data['stageMatches'] if r['status'].startswith('Potential insertion')]
    adjustments=[r for r in data['stageMatches'] if r['nepId'] and r['allocationAdjustmentPesos']]
    removal=[{'projectName':p['title'],'amountPesos':p['amount_php'],'region':p['region'],'sourcePage':p['source']['pdf_page'],'sourceId':p['project_id']} for p in data['unpairedNep']]
    d={'projects':projects,'counterparts':[{**r,'retention':r['status']} for r in data['stageMatches']],'insertions':inserts,'adjustments':adjustments,'removals':removal,'coordinate':coordinate,'lengths':lengthrows,'regions':totals,'prices':[{'amountPesos':a,'projects':n,'totalPesos':a*n} for a,n in prices.most_common()]}
    cols=[['HGAB project','projectName'],['Region','region'],['Allocation pesos','amountPesos'],['Source PDF page','sourcePage'],['Source row ID','sourceId']]
    configs=[{'id':'regions','title':'Regional allocations · NEP versus HGAB','note':'Separate proposals for the same program; stages are not summed. The graph shows each region’s net allocation adjustment.','columns':[['Region','region'],['NEP projects','nepProjects'],['NEP allocation pesos','nepPesos'],['HGAB projects','projects'],['HGAB allocation pesos','amountPesos'],['Adjustment pesos','adjustmentPesos']],'metric':'adjustmentPesos','chart':'diverging'},
    {'id':'counterparts','title':'All HGAB-to-NEP counterpart statuses','note':'Every House occurrence, including exact, plausible and unresolved links. Text similarity is not a probability. Filter by match-evidence class.','columns':cols[:-1]+[['NEP title','nepTitle'],['NEP allocation pesos','nepPesos'],['Match evidence','status']],'metric':'amountPesos','chart':'retention'},
    {'id':'insertions','title':'Potential insertions · no plausible NEP counterpart found','note':'Our own conservative title/region and scoped-candidate screen, not an imported analyst pairing. Absence of a counterpart is provisional.','columns':cols[:-1]+[['Counterpart status','status'],['Coordinate review','coordinateStatus']],'metric':'amountPesos','chart':'vertical'},
    {'id':'adjustments','title':'Allocation adjustments · selected NEP counterparts','note':'Exact title/region links; normalized coordinates strengthen segment agreement. Allocation adjustment does not certify engineering-scope identity.','columns':cols[:-1]+[['NEP allocation pesos','nepPesos'],['Adjustment pesos','allocationAdjustmentPesos'],['Match evidence','status']],'metric':'allocationAdjustmentPesos','chart':'diverging'},
    {'id':'removals','title':'Unpaired NEP rows · removal review','note':'Some rows may be retained under changed titles or combined scope; unpaired does not certify removal.','columns':cols,'metric':'amountPesos','chart':'vertical'},
    {'id':'projects','title':'All HGAB FMR project occurrences','note':'964 independently counted source rows; no parent subtotals included. Source PDF pages differ from printed page numbers.','columns':cols+[['Printed page','printedPage'],['Coordinate status','coordinateStatus'],['Coordinate review flags','reviewFlags']],'metric':'amountPesos','chart':'vertical'},
    {'id':'prices','title':'Repeated allocation amounts','note':'Equal appropriations can reflect standard design or policy; they are not unit construction prices.','columns':[['Allocation per occurrence pesos','amountPesos'],['Project occurrences','projects'],['Combined allocation pesos','totalPesos']],'metric':'projects','chart':'vertical'},
    {'id':'coordinate','title':'Coordinate anomalies requiring source review','note':'14 projects retain coordinate flags. Monetary allocations remain in totals; coordinate anomalies do not establish financial wrongdoing.','columns':cols+[['Review flags','reviewFlags']],'metric':'amountPesos','chart':'vertical'},
    {'id':'lengths','title':'FMR allocation per stated meter · printed STA evidence only','note':'Only three projects have usable printed station endpoints. Coordinate distance never supplies a road-length denominator. Three observations do not support a peer overpricing screen.','columns':cols+[['Stated meters','statedMeters'],['Allocation per stated meter pesos','allocationPerMeterPesos'],['Printed length evidence','lengthEvidence']],'metric':'allocationPerMeterPesos','chart':'vertical'}]
    head=PAGE.split('</head>')[0].replace('MPB · Multi-purpose building allocations','FMR archive · NEP and HGAB project schedules')+'</head>'
    hero=f'<section id="report-hero"><div class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">DA locally-funded FMR annex · FY2027</span><div class="repeat-hero-total"><strong>{s["hgabProjects"]}</strong><span>HGAB project allocations</span></div><div class="repeat-hero-cost"><strong>₱{s["hgabPesos"]/1e9:.4f}B</strong><span>audited project-ledger total</span></div></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><span>NEP proposal</span><strong>704 projects · ₱16B</strong></div><div><span>Net allocation adjustment</span><strong>+₱{s["netAdjustmentPesos"]/1e9:.4f}B</strong></div><div><span>Printed STA length evidence</span><strong>{len(lengthrows)} / 964 projects</strong></div><div><span>Coordinate review</span><strong>{s["hgabCoordinateReview"]} HGAB · {s["nepCoordinateReview"]} NEP rows</strong></div></div><p>Same FMR annex text in locally named 2nd/3rd copies; not authentication of the entire bill. Allocations are proposals, not payments.</p></div></div></section>'
    intro='<section class="card"><h2>Corrected FMR coverage and source integrity</h2><p>The previous parser recovered 795 rows carrying ₱14.035375B. The corrected ledger contains 964 project rows carrying ₱19.6281B: 169 more recovered occurrences and ₱5.592725B of additional extracted allocations. This is a parser correction, not a new budget-stage increase. The NEP annex contains 704 projects carrying ₱16B. Our bounded comparison independently found matching FMR annex text on PDF pages 667–726 after removing InDesign production-footer timestamps; all other content was retained.</p><p>Latitude/longitude normalization is not construction-length extraction. Straight-line distances cannot establish measured road alignment or paid scope. The cost-per-meter page now includes separately labeled approximate rates using endpoint chord distances, with coordinate review flags withheld. Only printed STA endpoints support the three stated-length rate rows below.</p><p><a href="fmr-data.json" download>Full project ledger, NEP counterparts and provenance JSON</a> · <a href="fmr-annex-equivalence.json" download>Annex equivalence audit</a> · <a href="repeats-historical.html#fmr">Historical FMR repeat comparisons</a> · <a href="cost-per-km.html">Cost per meter · stated-length screens and coordinate-based approximations</a></p></section>'
    connectivity_style='<style id="fmr-manual-review-style">.fmr-manual-red-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}.fmr-manual-red-stats>div{display:flex;flex-direction:column;gap:4px;padding:14px;border:1px solid #e3c9c9;border-radius:10px;background:#fff8f7}.fmr-manual-red-stats strong{font-size:clamp(18px,2vw,24px);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.fmr-manual-red-stats span{font-size:13px;color:#52636d}.fmr-manual-red-chart{display:grid;gap:8px;margin:14px 0}.fmr-manual-red-bar{display:grid;grid-template-columns:minmax(180px,1fr) minmax(100px,2fr) auto;align-items:center;gap:10px}.fmr-manual-red-bar>div{height:12px;background:#f2e6e6;border-radius:99px;overflow:hidden}.fmr-manual-red-bar i{display:block;height:100%;background:#b4232e;border-radius:99px}.fmr-manual-red td small{display:block;color:#52636d}@media(max-width:760px){.fmr-manual-red-bar{grid-template-columns:minmax(120px,1fr) minmax(60px,1fr) auto}}@media(max-width:520px){.fmr-manual-red-stats{grid-template-columns:1fr}}</style>'
    methods='<section class="card"><h2>Stage matching and normalization methodology</h2><p>'+data['method']+'</p><ul>'+''.join('<li>'+x+'</li>' for x in data['limits'])+'</ul><p>Coordinate flags do not remove monetary allocations. One project with several coordinate segments is counted once in the monetary ledger. Imported row IDs locate records in a document; they never assert cross-document project identity.</p></section>'
    historical_section='<section class="card section"><h2>Potential FMR repeats: FY2027 HGAB vs FY2025 GAA</h2><p>The corrected HGAB ledger is screened against locally available FY2025 enacted DA FMR records. Same qualified province and municipality are required; explicit barangay/location and direction conflicts or disjoint printed ranges veto. One best candidate per current occurrence, normalized full-title similarity ≥90%. Missing chainage and tranche differences require scope review. This is a conservative screening queue, not verified duplicate work. No FY2026 DA FMR GAA schedule is used.</p>'+table(['HGAB project','HGAB allocation pesos','FY2025 project','FY2025 allocation pesos','Title similarity','Chainage / tranche','HGAB PDF page'],[[r['projectName'],r['amountPesos'],r['priorProject'],r['priorAmountPesos'],r['similarity'],r['chainage']['chainage_status']+' · '+r['tranche']['tranche_status'],r['sourcePage']] for r in historical])+'<p><a href="fmr-historical-repeats.json" download>Every historical comparison and source evidence JSON</a></p></section>'
    # This comparison belongs to the Historical repeats page. Keep its rendered
    # fragment as builder input so rebuilding FMR cannot put it back in fmr.html.
    fragment_cache=OUT/'repeat_page_fragments.json'
    fragments=json.loads(fragment_cache.read_text(encoding='utf-8')) if fragment_cache.exists() else {}
    fragments['fmr']=historical_section
    fragment_cache.write_text(json.dumps(fragments,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    controls='function graphic(rows,c,metric){'+PAGE.split('function graphic(rows,c,metric){',1)[1].split('</script>',1)[0]
    controls=controls.replace("section.id='mpb-'+c.id","section.id='fmr-'+c.id").replace("a.download='mpb-'+c.id", "a.download='fmr-'+c.id")
    controls=controls.replace('r.office||r.buildingType','r.office||r.region||r.buildingType')
    controls=controls.replace('const legend=`<ol class="chart-legend">${points.map((p,i)=>`<li><span class="chart-legend-number">${i+1}</span><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join(\'\')}</ol>`;', 'const legend=`<ul class="chart-legend chart-legend-no-rank">${points.map(p=>`<li><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join(\'\')}</ul>`;')
    controls=controls.replace("'<td>'+esc(/pesos|allocation|adjustment/i.test(label)&&r[key]!=null&&r[key]!==''?peso(r[key]):r[key]??'—')+'</td>'", "'<td>'+(/flags?/i.test(label)?flagCell(r[key]):esc(/pesos|allocation|adjustment/i.test(label)&&r[key]!=null&&r[key]!==''?peso(r[key]):r[key]??'—'))+'</td>'")
    script="<script>const D="+json.dumps(d,ensure_ascii=False).replace('</','<\\/')+";const configs="+json.dumps(configs,ensure_ascii=False)+";const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+Number(v||0).toLocaleString('en-PH'),flagIcons={missing_or_ambiguous_segment_endpoint:'📍',single_point_without_endpoint_roles:'🧭',source_numeric_repair_candidate:'🔢'},flagCell=v=>{const labels=String(v??'').split(/\\s*;\\s*/).filter(Boolean);return labels.length?labels.map(k=>'<span role=\"img\" aria-label=\"Review flag: '+esc(k)+'\" title=\"'+esc(k)+'\">'+(flagIcons[k]||'🔎')+'</span>').join(' '):'—'};"+controls+'</script>'
    page=head+'<body><header><h1>FMR archive · NEP and HGAB project schedules</h1><p>Audited annex totals, source-level stage comparison and stated-length limits. <a href="fmr.html">Manual red-flag review ↗</a></p></header><main>'+hero+intro+'<div id="sections"></div>'+methods+'</main>'+script+JS+'</body></html>'
    page=page.replace('__HERO_STYLE__',STYLE).replace('</head>',connectivity_style+CSS+'</head>')
    from uniform_report_menu import apply_page as apply_uniform_menu
    page=apply_uniform_menu(page,'fmr-archive.html')
    from build_investigation_summary import CSS as EVIDENCE_CSS
    page=page.replace('</head>',EVIDENCE_CSS+'<style id="fmr-chart-legend-style">.chart-legend-no-rank li{grid-template-columns:minmax(0,1fr) auto!important}</style></head>',1)
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module('fmr-archive.html',page)
    (OUT/'fmr-archive.html').write_text(page);(STATIC/'fmr-archive.html').write_text(page)
    (STATIC/'fmr-annex-equivalence.json').write_text(json.dumps(data['annexEquivalence'],indent=2)+'\n')
    return {'summary':s,'statedLengthProjects':len(lengthrows),'historicalPairs':len(historical)}
if __name__=='__main__':print(json.dumps(generate(),indent=2))
