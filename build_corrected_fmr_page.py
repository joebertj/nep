#!/usr/bin/env python3
"""FMR page from audited project ledgers; geographic chords never become road length."""
import json,re,statistics,subprocess
from collections import Counter,defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from build_fmr_dataset import build,ROOT,OUT,STATIC
from build_mpb_report import PAGE
from build_cost_per_km import lengths
from hgab_matching import normalize
from chainage import compare_chainage,has_directional_conflict,compare_tranche
from location_data.project_location_scope import qualified,location_conflict

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

def generate():
    from build_investigation_summary import table,CSS,JS
    from build_report_heroes import STYLE
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
    head=PAGE.split('</head>')[0].replace('MPB · Multi-purpose building allocations','FMR · NEP and HGAB project schedules')+'</head>'
    hero=f'<section id="report-hero"><div class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">DA locally-funded FMR annex · FY2027</span><div class="repeat-hero-total"><strong>{s["hgabProjects"]}</strong><span>HGAB project allocations</span></div><div class="repeat-hero-cost"><strong>₱{s["hgabPesos"]/1e9:.4f}B</strong><span>audited project-ledger total</span></div></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown"><div><span>NEP proposal</span><strong>704 projects · ₱16B</strong></div><div><span>Net allocation adjustment</span><strong>+₱{s["netAdjustmentPesos"]/1e9:.4f}B</strong></div><div><span>Printed STA length evidence</span><strong>{len(lengthrows)} / 964 projects</strong></div><div><span>Coordinate review</span><strong>{s["hgabCoordinateReview"]} HGAB · {s["nepCoordinateReview"]} NEP rows</strong></div></div><p>Same FMR annex text in locally named 2nd/3rd copies; not authentication of the entire bill. Allocations are proposals, not payments.</p></div></div></section>'
    intro='<section class="card"><h2>Corrected FMR coverage and source integrity</h2><p>The previous parser recovered 795 rows carrying ₱14.035375B. The corrected ledger contains 964 project rows carrying ₱19.6281B: 169 more recovered occurrences and ₱5.592725B of additional extracted allocations. This is a parser correction, not a new budget-stage increase. The NEP annex contains 704 projects carrying ₱16B. Our bounded comparison independently found matching FMR annex text on PDF pages 667–726 after removing InDesign production-footer timestamps; all other content was retained.</p><p>Latitude/longitude normalization is not construction-length extraction. Straight-line distances cannot establish measured road alignment or paid scope. The cost-per-meter page now includes separately labeled approximate rates using endpoint chord distances, with coordinate review flags withheld. Only printed STA endpoints support the three stated-length rate rows below.</p><p><a href="fmr-data.json" download>Full project ledger, NEP counterparts and provenance JSON</a> · <a href="fmr-annex-equivalence.json" download>Annex equivalence audit</a> · <a href="repeats.html#fmr">Historical FMR repeat comparisons</a> · <a href="cost-per-km.html">Cost per meter · stated-length screens and coordinate-based approximations</a></p></section>'
    methods='<section class="card"><h2>Stage matching and normalization methodology</h2><p>'+data['method']+'</p><ul>'+''.join('<li>'+x+'</li>' for x in data['limits'])+'</ul><p>Coordinate flags do not remove monetary allocations. One project with several coordinate segments is counted once in the monetary ledger. Imported row IDs locate records in a document; they never assert cross-document project identity.</p></section>'
    historical_section='<section class="card section"><h2>Potential FMR repeats: FY2027 HGAB vs FY2025 GAA</h2><p>The corrected HGAB ledger is screened against locally available FY2025 enacted DA FMR records. Same qualified province and municipality are required; explicit barangay/location and direction conflicts or disjoint printed ranges veto. One best candidate per current occurrence, normalized full-title similarity ≥90%. Missing chainage and tranche differences require scope review. This is a conservative screening queue, not verified duplicate work. No FY2026 DA FMR GAA schedule is used.</p>'+table(['HGAB project','HGAB allocation pesos','FY2025 project','FY2025 allocation pesos','Title similarity','Chainage / tranche','HGAB PDF page'],[[r['projectName'],r['amountPesos'],r['priorProject'],r['priorAmountPesos'],r['similarity'],r['chainage']['chainage_status']+' · '+r['tranche']['tranche_status'],r['sourcePage']] for r in historical])+'<p><a href="fmr-historical-repeats.json" download>Every historical comparison and source evidence JSON</a></p></section>'
    controls='function graphic(rows,c,metric){'+PAGE.split('function graphic(rows,c,metric){',1)[1].split('</script>',1)[0]
    controls=controls.replace("section.id='mpb-'+c.id","section.id='fmr-'+c.id").replace("a.download='mpb-'+c.id", "a.download='fmr-'+c.id")
    controls=controls.replace('r.office||r.buildingType','r.office||r.region||r.buildingType')
    script="<script>const D="+json.dumps(d,ensure_ascii=False).replace('</','<\\/')+";const configs="+json.dumps(configs,ensure_ascii=False)+";const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+Number(v||0).toLocaleString('en-PH');"+controls+'</script>'
    page=head+'<body><header><h1>FMR · NEP and HGAB project schedules</h1><p>Audited annex totals, source-level stage comparison and stated-length limits.</p></header><main>'+hero+intro+'<div id="sections"></div>'+historical_section+methods+'</main>'+script+JS+'</body></html>'
    page=page.replace('__HERO_STYLE__',STYLE).replace('</head>',CSS+'</head>');(OUT/'fmr.html').write_text(page);(STATIC/'fmr.html').write_text(page)
    (STATIC/'fmr-annex-equivalence.json').write_text(json.dumps(data['annexEquivalence'],indent=2)+'\n')
    return {'summary':s,'statedLengthProjects':len(lengthrows),'historicalPairs':len(historical)}
if __name__=='__main__':print(json.dumps(generate(),indent=2))
