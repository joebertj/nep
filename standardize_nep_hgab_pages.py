#!/usr/bin/env python3
"""Agency pages use NEP -> HGAB; reading-to-reading results live on their dedicated page."""
import json,re
from pathlib import Path
from build_mpb_report import PAGE
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'

def make_page(name):
    from build_report_heroes import STYLE,hero,peso
    irrigation=name=='nia-irrigation.html';payload=json.loads((STATIC/('nia-irrigation-data.json' if irrigation else 'deped-data.json')).read_text())
    if irrigation:
        native=json.loads((ROOT/'hgab_3rd_editions.json').read_text())['nia_irrigation']
        rows=[{'projectName':r['projectName'],'amountPesos':r['amountPesos'],'sourcePage':r['sourcePage'],'sourceVolume':r['sourceVolume'],'sourceId':r['id'],'region':r.get('region') or 'Region unestablished','nepComparison':'Not established · comparable detailed NEP baseline missing'} for r in native]
        title='NIA irrigation · NEP → HGAB 3rd reading';intro='Detailed irrigation works, with NEP comparison coverage stated separately from observed HGAB allocations.'
        columns=[['HGAB irrigation work','projectName'],['HGAB allocation pesos','amountPesos'],['NEP counterpart status','nepComparison'],['HGAB PDF page','sourcePage'],['Source occurrence ID','sourceId']]
        limits='The workbook provides NIA named-project and programme subsidy entries, while this appendix lists finer irrigation works and segments. An unmatched title across these hierarchy levels cannot establish an insertion. A comparable detailed NEP baseline is not established. See <a href="nia.html#nia-nep-stage-comparison">source-checked named NIA comparisons</a> for the seven allocation changes at the named-project level. The locally available FY2025 historical screen found no displayed high-title-match candidates in this appendix; that is a separate historical comparison.'
    else:
        rows=[{'projectName':r['name'],'region':r['region'],'division':r['division'],'amountPesos':r['thirdTotal'],'jhsPsPesos':r['thirdJhsPs'],'jhsMooePesos':r['thirdJhsMooe'],'shsMooePesos':r['thirdShsMooe'],'sourcePage':r['sourcePage'],'nepComparison':'Not established · comparable NEP school baseline not built'} for r in payload['rows']]
        title='DepEd · NEP → HGAB 3rd reading';intro='HGAB school operating allocations and the evidence needed for a school-level NEP comparison.'
        columns=[['School','projectName'],['Region','region'],['Division','division'],['HGAB total pesos','amountPesos'],['Junior-high personnel pesos','jhsPsPesos'],['Junior-high MOOE pesos','jhsMooePesos'],['Senior-high MOOE pesos','shsMooePesos'],['NEP counterpart status','nepComparison'],['HGAB PDF page','sourcePage']]
        limits='A comparable NEP school-level baseline has not been constructed and reconciled. NEP-to-HGAB changes, insertions and removals are therefore not established. These are school operating allocations, not school-building construction projects. The HGAB total covers the extracted schedule fields only; it is not the entire DepEd budget.'
    total=sum(r['amountPesos'] for r in rows)
    card=hero('NEP → HGAB 3rd reading','Not established','comparable NEP baseline',peso(total),'HGAB allocation across the extracted schedule',[
        ('HGAB occurrences',f'{len(rows):,}','detailed works' if irrigation else 'school allocation rows'),('NEP difference','Not established','no zero substituted for a missing comparison')], 'The page reports observed HGAB allocations. A missing comparable baseline cannot establish unchanged budgets or insertions.')
    data={'schedule':rows};configs=[{'id':'schedule','title':'HGAB 3rd-reading allocation schedule','note':'Search, filter and sort the current House schedule. NEP columns remain unestablished until a comparable baseline is verified.','columns':columns,'metric':'amountPesos','chart':'vertical'}]
    head=PAGE.split('</head>')[0].replace('MPB · Multi-purpose building allocations',title)+'</head>'
    controls='function graphic(rows,c,metric){'+PAGE.split('function graphic(rows,c,metric){',1)[1].split('</script>',1)[0]
    controls=controls.replace("section.id='mpb-'+c.id","section.id='agency-'+c.id").replace("a.download='mpb-'+c.id", "a.download='agency-'+c.id").replace('r.office||r.buildingType','r.office||r.region||r.buildingType')
    script='<script>const D='+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+';const configs='+json.dumps(configs,ensure_ascii=False)+''';const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+Number(v||0).toLocaleString('en-PH');'''+controls+'</script>'
    page=head+'<body><header><h1>'+title+'</h1><p>'+intro+'</p></header><main><section id="report-hero">'+card+'</section><section class="card"><h2>NEP comparison coverage</h2><p>'+limits+'</p><p><a href="dpwh-hgab-comparison.html#other-agency-readings">HGAB 2nd-versus-3rd results are on the dedicated reading-comparison page →</a></p></section><div id="sections"></div><section class="card"><h2>Methodology and source limits</h2><p>Source occurrences and their printed allocation fields are retained. Amounts are proposals, not payments or losses. A missing baseline is represented by an explicit status, not numeric zero. Source PDF page references come from the current candidate extraction and require original-page scope review. Graphs show the first 12 filtered rows; CSV exports all filtered rows.</p></section></main>'+script+'</body></html>'
    page=page.replace('__HERO_STYLE__',STYLE);(STATIC/name).write_text(page);(OUT/name).write_text(page)
    return {'page':name,'hgabRows':len(rows),'hgabPesos':total,'nepDifference':None}

def apply():
    from build_investigation_summary import inject,section,table
    for name in ['nia-irrigation.html','deped.html']:make_page(name)
    for name in ['nia.html','hfep.html']:
        p=STATIC/name;s=p.read_text()
        s=re.sub(r'<section\b[^>]*id="edition-current"[^>]*>.*?</section>','',s,flags=re.S)
        s=re.sub(r'<script\b[^>]*>.*?</script>',lambda m:'' if 'editionMetrics' in m[0] and 'hgab-revision-data.json' in m[0] else m[0],s,flags=re.S)
        s=re.sub(r'<h2 class="edition-archive-heading">.*?</h2>','<h2>Supporting HGAB schedule analysis</h2>',s,flags=re.S)
        s=s.replace('Historical 2nd-reading repeat screen:','Historical GAA repeat screen:');p.write_text(s)
    revision=json.loads((STATIC/'hgab-revision-data.json').read_text());labels={'fmr':'FMR','nia_named':'NIA named projects','nia_irrigation':'NIA detailed irrigation','hfep':'HFEP','deped':'DepEd school operations'}
    rendered=[]
    for k,label in labels.items():
        s=revision[k]['summary'];rendered.append([label,s['secondRows'],s['thirdRows'],s['secondTotal'],s['thirdTotal'],s['thirdTotal']-s['secondTotal'],s['statusCounts'].get('Allocation changed',0)])
    body='<p>Reading-to-reading results belong here. These compare the two House versions, not NEP with HGAB. Zero below is an observed extraction result for this specific transition; it is not used as a substitute for missing NEP data.</p>'+table(['Schedule','2nd rows','3rd rows','2nd allocation pesos','3rd allocation pesos','Reading adjustment pesos','Changed allocation rows'],rendered)+'<p><a href="hgab-revision-data.json" download>Download complete reading-stage rows and source references</a></p>'
    inject('dpwh-hgab-comparison.html','other-agency-readings',section('other-agency-readings','Other agency schedules · HGAB 2nd versus 3rd',body))
    fmr=json.loads((STATIC/'fmr-data.json').read_text())['summary'];baseline=json.loads((STATIC/'nep-agency-baselines.json').read_text());h=baseline['hfepStageComparison']
    matched=[r for r in baseline['niaNamedComparisons'] if r['nepPesos'] is not None]
    irrigation_total=sum(r['amountPesos'] for r in json.loads((ROOT/'hgab_3rd_editions.json').read_text())['nia_irrigation'])
    deped_total=json.loads((STATIC/'deped-data.json').read_text())['summary']['thirdTotal']
    coverage=[['FMR annex',fmr['nepPesos'],fmr['hgabPesos'],fmr['netAdjustmentPesos'],'Programme controls; individual counterpart confidence stays separate'],
              ['NIA exact named-title subset',sum(r['nepPesos'] for r in matched),sum(r['hgabPesos'] for r in matched),sum(r['adjustmentPesos'] for r in matched),'Matched subset only; not the whole NIA budget'],
              ['HFEP programme total',h['nepTotalPesos'],h['hgabTotalPesos'],h['totalAdjustmentPesos'],'MOOE and Capital Outlays matched at programme level'],
              ['NIA irrigation appendix','Not established',irrigation_total,'Not established','Detailed NEP works baseline missing'],
              ['DepEd school operations','Not established',deped_total,'Not established','Comparable NEP school baseline not built']]
    preferred_nep=ROOT/'data_sources/csiiiv/accepted/nep_nia_dataset.json'
    if preferred_nep.exists():
        nep_rows=json.loads(preferred_nep.read_text())['projects'];nep_total=sum(r['amount_php'] for r in nep_rows)
        coverage[3]=['NIA irrigation annex',nep_total,irrigation_total,irrigation_total-nep_total,'Reviewed detailed annex controls; project identity remains separate']
    inject('summary.html','summary-neutral',section('summary-neutral','Other schedules · NEP → HGAB comparison coverage','<p>Compare the same budget hierarchy before calculating changes. Missing comparable NEP data is not zero. The schedules and matched subsets below overlap other findings and must not be summed.</p>'+table(['Scope','NEP allocation pesos','HGAB allocation pesos','Allocation adjustment pesos','Coverage limit'],coverage)))
    for p in [STATIC/'summary-data.json',OUT/'investigation_summary.json']:
        if p.exists():
            payload=json.loads(p.read_text());payload['agencyComparisonCoverage']=[{'scope':r[0],'nepPesos':r[1] if isinstance(r[1],int) else None,'hgabPesos':r[2],'adjustmentPesos':r[3] if isinstance(r[3],int) else None,'limit':r[4]} for r in coverage];p.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    return {'agencyPages':'NEP → HGAB 3rd','readingComparisons':'dpwh-hgab-comparison.html'}
if __name__=='__main__':print(json.dumps(apply(),indent=2))
