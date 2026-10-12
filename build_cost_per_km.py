#!/usr/bin/env python3
"""Stated-length coverage and allocation/segment-meter proxies, separated by program."""
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from chainage import _PATTERN, parse_chainage
from hgab_matching import is_fap
from build_mpb_report import PAGE as MPB_PAGE

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
NUMBER=r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
LENGTH=re.compile(r'\b(?:length\s*(?:of|[:=])?\s*|L\s*[:=]\s*)('+NUMBER+r')\s*(kilomet(?:er|re)s?|km|meters?|metres?|m|l\.?m\.?)\b',re.I)
KM=re.compile(r'(?<![\w.+])('+NUMBER+r')\s*(?:km|kilomet(?:er|re)s?)\b(?!\s*\+)',re.I)


def lengths(title,context=''):
    text=title
    ranges,points=parse_chainage(text)
    method='Complete chainage range in title'
    # Only the parser's same-row project context may supply continuation lines.
    if context and not ranges:
        # Discard a preceding project's endpoint from the parser context.
        prefix=re.split(r'\bsta(?:tion)?\.?\s*[:=]?\s*\d',title,flags=re.I)[0].strip(' ,')
        start=context.find(prefix)
        if start<0:context=''
        else:context=context[start:]
        cr,cp=parse_chainage(context)
        if cr:
            ranges,points=cr,cp;method='Complete chainage range in same-row source context'
        elif len(cp)==2 and len(list(_PATTERN.finditer(context)))==2:
            # Printed start/end STA on separate project-column lines. An
            # arbitrary pair of station points elsewhere is not connected.
            if len(re.findall(r'\bsta(?:tion)?\.?\s*[:=]?\s*\d',context,re.I))==2:
                ranges=[(min(cp),max(cp))];points=[];method='Two printed STA endpoints in same-row FMR project context'
    explicit=[]
    for m in LENGTH.finditer(title):
        v=float(m[1].replace(',',''));explicit.append(v*(1000 if m[2].lower().startswith(('km','kilo')) else 1))
    for m in KM.finditer(title):
        explicit.append(float(m[1].replace(',',''))*1000)
    explicit=sorted(set(explicit))
    if ranges:
        # Keep an isolated station unallocated; a complete interval alone does
        # not cover a second isolated or incompletely printed segment.
        if points:return None,'Partial chainage: isolated station alongside ranges',method,ranges
        if any(a==b for a,b in ranges):return None,'Zero-length chainage requires review',method,ranges
        merged=[]
        for a,b in sorted(ranges):
            if merged and a<=merged[-1][1]:merged[-1][1]=max(b,merged[-1][1])
            else:merged.append([a,b])
        if len(ranges)>1 and (';' in title or len(re.findall(r'\b(?:road|highway)\b',title,re.I))>1):
            return None,'Multiple routes: common station reference unverified',method,ranges
        total=sum(b-a for a,b in merged)
        if explicit and (len(explicit)!=1 or abs(explicit[0]-total)>max(1,total*.01)):
            return None,'Chainage and explicit length disagree',method,ranges
        return total/1000,'Usable stated segment length',method+(' · overlapping intervals merged' if len(ranges)>1 else ''),ranges
    if len(explicit)==1 and explicit[0]>0:
        if points:return None,'Explicit length with incomplete station scope', 'Explicit length in title',[]
        return explicit[0]/1000,'Usable stated segment length','Explicit length in title',[]
    if len(explicit)>1:return None,'Multiple explicit lengths: scope unclear','Explicit lengths in title',[]
    return None,('Station points only: no connected range' if points else 'No usable stated length found'),'No derivable length',[]


def category(row):
    title=row['projectName'].lower();pap=row.get('pap3','').lower()
    if any(w in pap for w in ['flood','drainage','multi-purpose','water supply','rainwater','buildings and other']):return None
    road=bool(re.search(r'\broads?\b|\bhighway\b|\bfmr\b',title))
    bridge=bool(re.search(r'\bbridges?\b',title))
    if bridge and road:return 'Mixed roads / bridges'
    if bridge or ('bridge' in pap and 'access roads' not in pap):return 'Bridges'
    if road or ('road' in pap and 'access roads' not in pap):return 'Roads'
    return None


def build():
    if (ROOT/'data_sources/fmr_analyst/hgab_fmr_coordinates_normalized.json').exists():
        from build_fmr_dataset import build as build_fmr_dataset
        build_fmr_dataset()
    with (OUT/'hb_nep_comparison_3rd.csv').open() as f:raw=list(csv.DictReader(f))
    fmr=json.loads((ROOT/'hgab_3rd_editions.json').read_text())['fmr']
    rows=[]
    for source in raw+fmr:
        fmr_row=source.get('agency')=='Department of Agriculture'
        group='FMR' if fmr_row else category(source)
        if not group or is_fap(source):continue
        km,status,method,ranges=lengths(source['projectName'],source.get('sourceContext','') if fmr_row else '')
        # A mixed road/bridge appropriation cannot produce a single-work rate.
        rate=round(int(source['amountPesos'])/km,2) if km and group!='Mixed roads / bridges' else None
        rows.append({'id':source.get('hgab_id') or source['id'],'category':group,
                     'program':'FMR' if fmr_row else source['pap3'],'projectName':source['projectName'],
                     'office':source.get('office',''),'amountPesos':int(source['amountPesos']),
                     'lengthKm':km,'lengthStatus':status,'lengthMethod':method,
                     'allocationPerStatedKm':rate,
                     'lengthMeters':round(km*1000,6) if km is not None else None,
                     'allocationPerStatedMeter':round(int(source['amountPesos'])/(km*1000),2) if km and group!='Mixed roads / bridges' else None,
                     'rangesMeters':ranges,
                     'sourceVolume':source['sourceVolume'],'sourcePage':source['sourcePage'],
                     'lengthEvidence':source.get('sourceContext') if fmr_row else source['projectName'],
                     'scopeNote':('Mixed scope: no single-work cost/m shown' if group=='Mixed roads / bridges' else
                                  'Bridge chainage can include approaches; not verified span length' if group=='Bridges' else
                                  'Whole line-item allocation divided by stated segment; work quantities, width and funded extent unverified')})
    coverage=[]
    groups=defaultdict(list)
    for row in rows:groups[(row['category'],row['program'])].append(row)
    for (group,program),members in groups.items():coverage.append(coverage_row(group,program,members))
    totals=[coverage_row(group,'All selected programs · coverage only',[r for r in rows if r['category']==group]) for group in ['Roads','Bridges','FMR','Mixed roads / bridges']]
    data={'edition':'HGAB 3rd reading','summary':totals,'coverage':coverage,'projects':rows,
          'policy':'Allocation per stated segment meter is a screening proxy, not construction unit cost. No missing length is estimated from budget, coordinates or another stage.',
          'displayUnits':{'length':'meters','rate':'pesos per stated meter'},
          'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [OUT/'hb_nep_comparison_3rd.csv',ROOT/'hgab_3rd_editions.json']],
          'scope':f'Domestic DPWH road/bridge selected title/PAP records and {len(fmr)} Department of Agriculture FMR records. Mixed work separated; flood/MPB/water titles and FAP excluded. Counts are extracted allocation occurrences.'}
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    (OUT/'cost_per_km.json').write_text(serialized);(STATIC/'cost-per-km-data.json').write_text(serialized)
    from analyze_length_density import build as build_density
    density=build_density(data)
    from screen_high_meter_rates import enrich as screen_rates
    screen_rates(data,density)
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    (OUT/'cost_per_km.json').write_text(serialized);(STATIC/'cost-per-km-data.json').write_text(serialized)
    density['sourceCostDataSha256']=hashlib.sha256(serialized.encode()).hexdigest()
    density_text=json.dumps(density,ensure_ascii=False,indent=2)+'\n'
    (OUT/'length_density_groups.json').write_text(density_text);(STATIC/'length-density-groups.json').write_text(density_text)
    build_page(data,density)
    return data


def coverage_row(group,program,rows):
    known=[r for r in rows if r['lengthKm'] is not None];missing=len(rows)-len(known)
    return {'category':group,'program':program,'lineItems':len(rows),'withLength':len(known),
            'withoutLength':missing,'missingPct':round(100*missing/len(rows),2) if rows else 0,
            'withRate':sum(r['allocationPerStatedKm'] is not None for r in rows),
            'allocationPesos':sum(r['amountPesos'] for r in rows),'unusableLengthAllocationPesos':sum(r['amountPesos'] for r in rows if r['lengthKm'] is None)}


def build_page(data,density):
    from analyze_length_density import render as render_density
    from compare_meter_rates_2026 import build as build_year_comparison, render as render_year_comparison
    year_comparison = render_year_comparison(build_year_comparison(data))
    # Reuse the framework-free graph/table controls; source builders retain
    # shared responsive width, fixed menu and hero styles through final review.
    head=MPB_PAGE.split('</head>')[0].replace('MPB · Multi-purpose building allocations','Cost per meter · stated-length coverage')+'</head>'
    hero='<section class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">HGAB 3rd reading · stated lengths</span><div class="repeat-hero-total"><strong>'+str(sum(r['withLength'] for r in data['summary']))+'</strong><span>line items with derivable stated segment lengths</span></div><p>Coverage is reported separately for roads, bridges, FMR and mixed work.</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown">'+''.join('<div><span>'+r['category']+'</span><strong>'+str(r['withLength'])+'/'+str(r['lineItems'])+' lengths · '+str(r['missingPct'])+'% without usable length</strong></div>' for r in data['summary'])+'</div><p>No coordinate distances or inferred lengths fill missing values.</p></div></section>'
    hero=hero.replace('<strong>'+str(sum(r['withLength'] for r in data['summary']))+'</strong>', '<strong>'+str(data['highRateScreen']['candidates'])+'</strong>',1).replace('line items with derivable stated segment lengths','high-rate candidates for scope review').replace('Coverage is reported separately for roads, bridges, FMR and mixed work.','Compared within the same program and similar stated-length group.')
    intro='''<section class="card"><h2>Which projects have unusually high allocation per meter?</h2><p>The first tables compare each rate with the typical rate in the same official program and a similar stated-length group. A high-rate candidate is more than twice the typical peer rate and unusually high within its peer group. This is a scope-review queue, not a verified overpricing finding. Extreme values are omitted from rate graphs and described alongside them; they remain in the tables and CSV. Coverage denominators include all selected extracted occurrences in each category, including those without a usable length.</p><p class="caution">These are whole line-item allocations divided by stated segment lengths, not verified construction unit costs. Bridge chainage may cover approaches rather than bridge span. Missing percentage means no usable length was recovered from the current title/project context; it does not establish that the original budget or engineering documents omit length.</p><p><a href="cost-per-km-data.json" download>Download all records and length evidence</a></p></section>'''
    intro+='<p class="caution">'+str(data['highRateScreen']['graphExtremeRecords'])+' extreme or very-short-range records are kept off rate charts. Use the Extreme values filter to inspect them; all records remain downloadable. Peer screening needs at least 20 usable records. Missing or sparse peers do not establish a normal price.</p><h3>How high-rate candidates are identified</h3><p>'+data['highRateScreen']['method']+'</p>'
    methods='''<section class="card"><h2>Length extraction and coverage methodology</h2><ul><li>Complete STA/K/KM plus-form ranges are converted to meters. Overlapping numerical intervals are merged, never double-counted. Multiple named routes with unverified station references are withheld.</li><li>A single explicitly labeled length in meters or kilometers can supply a length. Widths, isolated stations and coordinate straight-line distances do not supply a road length.</li><li>FMR length extraction uses only the current project's row-bounded source context, including printed STA labels in the analyst's coordinate cell. Context preceding the current project title is discarded, preventing a previous project’s endpoint from becoming part of the current length. Exactly two printed STA endpoints in the remaining context can form a range. The context is retained in the downloadable data; nearby unrelated text is not searched for endpoints.</li><li>Partial or zero-length chainage, conflicting explicit lengths and ambiguous multi-route scopes remain without a usable length. No allocation amount is used to infer missing length.</li><li>The missing percentage is (all category occurrences minus occurrences with usable stated length) / all category occurrences. It includes both absent metadata and metadata that needs review. A separate rate count distinguishes usable lengths from permissible single-category ratios.</li><li>Mixed road/bridge titles are separated and no single-work rate is shown. Flood, building/water PAPs and foreign-assisted schedules are outside this page's denominator. Classification uses explicit titles and PAPs; it is not a complete inventory of physical road assets.</li><li>No rate averages are pooled across categories or PAPs. Every point identifies one allocation occurrence; rankings can change with scope, width, structures, terrain, total project components and parser corrections. High rates warrant source/quantity review, not an allegation.</li><li>Graphs and CSV follow table filters. Paired bars compare project allocation/meter with the median of its own peer group; up to 12 non-extreme records are displayed. Extreme values are described beside the graph; all filtered rows, including missing lengths, remain in the table/CSV. Source volume/page and original length evidence are included. Historical stages are not used to fill current-stage gaps.</li></ul><p>The summary links to two separate leads: length-data coverage and allocation per stated meter. Coverage gaps are extraction observations, and ratios are scope-dependent screening proxies. Extremely short printed ranges can produce extreme rates; verify station endpoints and funded scope on original pages before interpreting them. Request bills of quantities, designs, funded segment boundaries, bridge spans and roadway widths before comparing actual costs.</p></section>'''
    start=JS_START
    controls=MPB_PAGE[MPB_PAGE.index('function graphic('):MPB_PAGE.index('</script></body>')]
    # Separate all program rates, expose unknowns, and never format meter
    # quantities as pesos or silently turn missing values into zeros.
    controls=controls.replace('r.projectName||r.nepTitle||r.office||r.buildingType', 'r.projectName||r.nepTitle||r.office||r.program||r.buildingType')
    controls=controls.replace('r.buildingType||r.retention||r.region','r.program||r.lengthStatus')
    controls=controls.replace('[r.buildingType,r.retention,r.region]','[r.program,r.lengthStatus]')
    controls=controls.replace("/pesos|allocation|adjustment/i.test(label)","/pesos|allocation|adjustment/i.test(label)")
    controls=controls.replace("'mpb-'+c.id+'.csv'","'cost-per-km-'+c.id+'.csv'")
    controls=controls.replace("section.id='mpb-'+c.id", "section.id='cost-'+c.id")
    controls=controls.replace("<button class=\"export\" type=\"button\">", "<select class=\"review-filter\" aria-label=\"Review status\"><option value=\"\">All records</option><option value=\"high\">High-rate candidates</option><option value=\"extreme\">Extreme values excluded from graphs</option></select><button class=\"export\" type=\"button\">")
    controls=controls.replace("const search=section.querySelector('input')", "const review=section.querySelector('.review-filter');if(c.id==='coverage')review.hidden=true;if(D[c.id].some(r=>r.highRateCandidate))review.value='high';review.addEventListener('change',()=>{page=0;render()});const search=section.querySelector('input')")
    controls=controls.replace("filter(r=>(!group", "filter(r=>(!review.value||(review.value==='high'?r.highRateCandidate:r.graphExtreme))&&(!group")
    controls=controls.replace("const max=Math.max(1,...points.map",SCATTER_BRANCH+"\n const max=Math.max(1,...points.map")
    controls=controls.replace("c.chart==='retention'?'Comparison pairs by HGAB retention status · all filtered rows'", "c.chart==='scatter'?'Project rate versus typical peer rate · extreme values omitted and described below':c.chart==='retention'?'Comparison pairs by HGAB retention status · all filtered rows'")
    controls=controls.replace("/pesos|projects|count/i.test(key)","/pesos|projects|count|lengthmeters|allocationper|lineitems|withlength|withoutlength|missingpct/i.test(key)")
    page=head+'<body><header><h1>Cost per meter · stated-length coverage</h1><p>HGAB 3rd reading · roads, bridges and farm-to-market roads</p></header><main>'+hero+intro+'<div id="sections"></div>'+year_comparison+length_overview(data)+render_density(density)+methods+'</main><script id="length-data" type="application/json">'+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+'</script><script>'+start+controls+'</script></body></html>'
    from build_report_heroes import STYLE
    page=page.replace('__HERO_STYLE__',STYLE)
    (STATIC/'cost-per-km.html').write_text(page);(OUT/'cost-per-km.html').write_text(page)


def length_overview(data):
    from build_investigation_summary import table, esc, JS
    body='<section id="short-segment-evidence" class="card"><h2>Very short printed ranges · original PDF text checks</h2>'
    audit_path=OUT/'short_segment_audit.json'
    if audit_path.exists():
        audit=json.loads(audit_path.read_text())
        if audit.get('comparisonCsvSha256')==hashlib.sha256((OUT/'hb_nep_comparison_3rd.csv').read_bytes()).hexdigest():
            checked=[r for r in audit['sourceChecks'] if r['fullTitlePresentInVisiblePDFText']]
            body+='<p>The following extracted titles agree with visible text on the cited original PDF pages. This establishes printed notation, not its intended engineering meaning or the actual funded length. In particular, sub-meter road ranges require endpoint and scope clarification before interpreting allocation rates.</p>'
            body+=table(['Project','Calculated stated meters','HGAB allocation pesos','Original source'],[[r['projectName'],r['lengthMeters'],r['amountPesos'],r['sourceVolume']+' · p. '+str(r['sourcePage'])] for r in checked])
            body+='<p><a href="short-segment-audit.json" download>Download source-check evidence and full-population counts</a>. Tiny printed ranges may reflect source notation or source-document errors. Bridges can legitimately be shorter than roads; a short bridge range alone is not an anomaly.</p>'
    return body.replace('class="export-btn"','class="export export-btn"')+'</section>'+JS


JS_START=r'''
const D=JSON.parse(document.getElementById('length-data').textContent);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+num(v);
const configs=[];const coverageConfig={id:'coverage',title:'Length coverage by category and official program',note:'Each program has its own denominator. Missing means absent or unusable extracted length evidence; no construction price average is pooled.',columns:[['Category','category'],['Official program','program'],['Line items','lineItems'],['Usable lengths','withLength'],['Without usable length','withoutLength'],['Missing / unusable (%)','missingPct'],['Rate records','withRate'],['Allocation pesos','allocationPesos'],['Allocation without usable length pesos','unusableLengthAllocationPesos']],metric:'missingPct',chart:'vertical'};
for(const category of ['Roads','Bridges','FMR','Mixed roads / bridges']){
 D.projects.forEach(r=>r.sourceLabel=r.sourceVolume+' · p. '+r.sourcePage);
 const summary=D.summary.find(r=>r.category===category),id=category.toLowerCase().replace(/[^a-z]+/g,'-');D[id]=D.projects.filter(r=>r.category===category);
 configs.push({id,title:category+' · high-rate candidates',note:`${summary.withLength.toLocaleString()} of ${summary.lineItems.toLocaleString()} line items have usable stated lengths; ${summary.missingPct}% do not. ${summary.withRate} rate records. Choose an official program to keep work types separate.`,columns:[['Project','projectName'],['Official program','program'],['Stated meters','lengthMeters'],['Allocation pesos','amountPesos'],['Allocation per meter pesos','allocationPerStatedMeter'],['Typical peer rate pesos/meter','typicalPeerRate'],['Times typical peer rate','peerRateMultiple'],['Review status','rateReview'],['Source','sourceLabel']],metric:'peerRateMultiple',chart:'scatter'});
}
configs.push(coverageConfig);
'''
SCATTER_BRANCH=r'''
 if(c.chart==='scatter'){
 const rates=rows.filter(r=>r.lengthMeters>0&&r.allocationPerStatedMeter!=null);
 const extremes=rates.filter(r=>r.graphExtreme),valid=rates.filter(r=>!r.graphExtreme&&r.typicalPeerRate!=null).slice(0,12);
 const largest=extremes.length?extremes.reduce((a,b)=>a.allocationPerStatedMeter>b.allocationPerStatedMeter?a:b):null;
 const note='<p class="note">'+extremes.length+' extreme values omitted from this graph.'+(largest?' Highest omitted rate: '+peso(largest.allocationPerStatedMeter)+'/meter over '+num(largest.lengthMeters)+' stated meters; source p. '+esc(largest.sourcePage)+'. Values remain in the table and CSV.':'')+'</p>';
 if(!valid.length)return note+'<p>No supported peer comparisons within the graph range. Check the table and source evidence.</p>';
 const maximum=Math.max(...valid.flatMap(r=>[r.allocationPerStatedMeter,r.typicalPeerRate]));
 let svg='<figure><figcaption>Orange: project allocation/meter · teal: typical peer allocation/meter · first 12 non-extreme filtered records</figcaption><svg viewBox="0 0 1100 400" role="img" aria-label="Project allocation rate versus typical peer rate">';
 valid.forEach((r,i)=>{const x=60+i*80,a=250*r.allocationPerStatedMeter/maximum,b=250*r.typicalPeerRate/maximum;svg+='<rect x="'+x+'" y="'+(290-a)+'" width="25" height="'+a+'" fill="#b65b09"><title>'+esc(r.projectName)+' · '+peso(r.allocationPerStatedMeter)+'/meter · '+r.peerRateMultiple+'× typical rate</title></rect><rect x="'+(x+27)+'" y="'+(290-b)+'" width="25" height="'+b+'" fill="#087e78"><title>'+r.peerRecords+' peers in '+esc(r.peerBand)+' · median '+peso(r.typicalPeerRate)+'/meter</title></rect><text x="'+x+'" y="315" font-size="12">'+(i+1)+': '+r.peerRateMultiple+'×</text>';});
 return '<p>Graph upper rate: '+peso(maximum)+'/meter. Each pair uses its own program/length peer group.</p>'+svg+'</svg></figure>'+note;
 }
'''

if __name__=='__main__':
    print(json.dumps(build()['summary'],indent=2))
