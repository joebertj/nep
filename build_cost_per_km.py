#!/usr/bin/env python3
"""Stated-length coverage and allocation/segment-meter proxies, separated by program."""
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from chainage import _PATTERN, parse_chainage, has_ambiguous_chainage
from hgab_matching import is_fap
from build_mpb_report import PAGE as MPB_PAGE

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
NUMBER=r'(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?'
LENGTH=re.compile(r'\b(?:length\s*(?:of|[:=])?\s*|L\s*[:=]\s*)('+NUMBER+r')\s*(kilomet(?:er|re)s?|km|meters?|metres?|m|l\.?m\.?)\b',re.I)
KM=re.compile(r'(?<![\w.+])('+NUMBER+r')\s*(?:km|kilomet(?:er|re)s?)\b(?!\s*\+)',re.I)


def legacy_chainage(text):
    """Recompute the earlier plus-form-only rules for a coverage comparison."""
    ranges,points=[],[]
    for m in _PATTERN.finditer(text):
        start=float(m[1])*1000+float(m[2])
        if m[3] is None:points.append(start)
        else:
            end=float(m[3])*1000+float(m[4])
            ranges.append((min(start,end),max(start,end)))
    return ranges,points


def lengths(title,context='',chainage_parser=parse_chainage):
    text=title
    if chainage_parser is parse_chainage and has_ambiguous_chainage(title):
        return None,'Incomplete chainage: mixed bare and plus-form endpoints; units or kilometer component unresolved','Incomplete chainage in title',[]
    ranges,points=chainage_parser(text)
    method='Complete chainage range in title'
    # Only the parser's same-row project context may supply continuation lines.
    if context and not ranges:
        # Discard a preceding project's endpoint from the parser context.
        prefix=re.split(r'\bsta(?:tion)?\.?\s*[:=]?\s*\d',title,flags=re.I)[0].strip(' ,')
        start=context.find(prefix)
        if start<0:context=''
        else:context=context[start:]
        if chainage_parser is parse_chainage and has_ambiguous_chainage(context):
            return None,'Incomplete chainage: mixed bare and plus-form endpoints; units or kilometer component unresolved','Incomplete chainage in same-row source context',[]
        cr,cp=chainage_parser(context)
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
        if len(ranges)>1 and (';' in title or len(re.findall(r'\b(?:road|highway)\b',title,re.I))>1 or (chainage_parser is parse_chainage and len(set(re.findall(r'\bS\d{5}[A-Z]{2}\b',title,re.I)))>1)):
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
    # A named elevated structure is not an ordinary road peer merely because
    # its title also identifies the road on which it stands.
    if re.search(r'\boverpass\b|\bflyover\b|\bviaduct\b',title):return 'Bridges'
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
    from approximate_coordinate_lengths import approximate
    ledger_path=ROOT/'data_sources/fmr_analyst/hgab_fmr_coordinates_normalized.json'
    coordinate_ledger={r['project_id']:r for r in json.loads(ledger_path.read_text())['projects']} if ledger_path.exists() else {}
    rows=[];coordinate_only=[]
    for source in raw+fmr:
        fmr_row=source.get('agency')=='Department of Agriculture'
        group='FMR' if fmr_row else category(source)
        if is_fap(source):continue
        if not group:
            if 'multi-purpose' not in source.get('pap3','').lower() and not re.search(r'\bmulti[ -]?purpose\b',source['projectName'],re.I):
                proxy=approximate(source)
                if proxy['approximateLengthMeters'] is not None:
                    coordinate_category='Flood control' if any(w in source['pap3'].lower() for w in ['flood','drainage']) else 'Roads' if re.search(r'\broad|\bboulevard|\bhighway',source['projectName'],re.I) else 'Other non-MPB'
                    if re.search(r'\bbuilding|\bquarters|\bschool',source['projectName'],re.I):
                        proxy['approximateAllocationPerMeter']=None
                        proxy['approximationStatus']='Building-location separation only · linear-work cost per meter withheld'
                    coordinate_only.append({'id':source.get('hgab_id') or source['id'],'projectName':source['projectName'],'program':source['pap3'],
                        'category':coordinate_category,
                        'amountPesos':int(source['amountPesos']),'sourceLabel':source['sourceVolume']+' · p. '+str(source['sourcePage']),**proxy})
            continue
        km,status,method,ranges=lengths(source['projectName'],source.get('sourceContext','') if fmr_row else '')
        previous_km,previous_status,_,_=lengths(source['projectName'],source.get('sourceContext','') if fmr_row else '',legacy_chainage)
        # A mixed road/bridge appropriation cannot produce a single-work rate.
        rate=round(int(source['amountPesos'])/km,2) if km and group!='Mixed roads / bridges' else None
        rows.append({'id':source.get('hgab_id') or source['id'],'category':group,
                     'program':'FMR' if fmr_row else source['pap3'],'projectName':source['projectName'],
                     'office':source.get('office',''),'region':source.get('region',''),'amountPesos':int(source['amountPesos']),
                     'lengthKm':km,'lengthStatus':status,'lengthMethod':method,
                     'allocationPerStatedKm':rate,
                     'lengthMeters':round(km*1000,6) if km is not None else None,
                     'allocationPerStatedMeter':round(int(source['amountPesos'])/(km*1000),2) if km and group!='Mixed roads / bridges' else None,
                     'rangesMeters':ranges,
                     'sourceVolume':source['sourceVolume'],'sourcePage':source['sourcePage'],
                     'lengthEvidence':source.get('sourceContext') if fmr_row else source['projectName'],
                     'lengthRecoveredByNotationUpdate':km is not None and previous_km is None,
                     'earlierNotationLengthMeters':previous_km*1000 if previous_km is not None else None,
                     'earlierNotationLengthStatus':previous_status,
                     'scopeNote':('Mixed scope: no single-work cost/m shown' if group=='Mixed roads / bridges' else
                                  'Bridge chainage can include approaches; not verified span length' if group=='Bridges' else
                                  'Whole line-item allocation divided by stated segment; work quantities, width and funded extent unverified')})
        rows[-1].update(approximate(source,coordinate_ledger.get(source.get('analystSourceId')) if fmr_row else None))
        if group=='Mixed roads / bridges':rows[-1]['approximateAllocationPerMeter']=None
    from lane_cost_enrichment import enrich as enrich_lanes
    lane_data=enrich_lanes({'projects':rows})
    coverage=[]
    groups=defaultdict(list)
    for row in rows:groups[(row['category'],row['program'])].append(row)
    for (group,program),members in groups.items():coverage.append(coverage_row(group,program,members))
    totals=[coverage_row(group,'All selected programs · coverage only',[r for r in rows if r['category']==group]) for group in ['Roads','Bridges','FMR','Mixed roads / bridges']]
    notation_coverage=[]
    for total in totals:
        members=[r for r in rows if r['category']==total['category']]
        notation_coverage.append({'category':total['category'],'lineItems':len(members),
            'earlierUsableLengths':sum(r['earlierNotationLengthMeters'] is not None for r in members),
            'earlierLengthsStillUsable':sum(r['earlierNotationLengthMeters'] is not None and r['lengthMeters'] is not None for r in members),
            'earlierLengthsNowWithheld':sum(r['earlierNotationLengthMeters'] is not None and r['lengthMeters'] is None for r in members),
            'currentUsableLengths':total['withLength'],
            'newlyRecoveredLengths':sum(r['lengthRecoveredByNotationUpdate'] for r in members),
            'withoutUsableLength':total['withoutLength'],'missingPct':total['missingPct']})
    data={'edition':'HGAB 3rd reading','summary':totals,'coverage':coverage,'projects':rows,'laneCost':lane_data,
          'coordinateOnlyProjects':coordinate_only,
          'notationCoverage':notation_coverage,
          'coordinateApproximationPolicy':'Haversine separation (Earth radius 6,371,008.8 meters) of two printed points, or sum of separately labeled normalized FMR segment chords. Winding alignments can make chord-based rates higher than actual route-based rates. Endpoint roles, funded scope and construction quantities require verification. Coordinate approximations never fill stated lengths or enter high-rate flags. Building-location and mixed-work rates are withheld.',
          'policy':'Allocation per stated segment meter is a screening proxy, not construction unit cost. No missing length is estimated from budget, coordinates or another stage.',
          'displayUnits':{'length':'meters','rate':'pesos per stated meter'},
          'sources':[{'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [OUT/'hb_nep_comparison_3rd.csv',ROOT/'hgab_3rd_editions.json']+([ledger_path] if ledger_path.exists() else [])],
          'scope':f'Domestic DPWH road/bridge selected title/PAP records and {len(fmr)} Department of Agriculture FMR records. Mixed work separated; flood/MPB/water titles and FAP excluded. Counts are extracted allocation occurrences.'}
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    (OUT/'cost_per_km.json').write_text(serialized);(STATIC/'cost-per-km-data.json').write_text(serialized)
    from analyze_length_density import build as build_density
    density=build_density(data)
    from screen_high_meter_rates import enrich as screen_rates
    screen_rates(data,density)
    # A shared two-lane baseline keeps bridges with known stated lengths
    # comparable when neither the project nor the inventory gives lane count.
    # This estimate is for visualization only and does not enter peer flags.
    for row in data['projects']:
        if row['category']=='Bridges' and row.get('lengthMeters') and not row.get('titleStatedLanes') and not row.get('inventoryEffectiveLanes'):
            row['manualLaneEstimateLanes']=2
            row['allocationPerManualLaneMeter']=round(row['amountPesos']/(row['lengthMeters']*2),2)
            row['manualLaneEstimateBasis']='Assumed 2 lanes for group comparison; actual lanes and funded span are unverified'
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    (OUT/'cost_per_km.json').write_text(serialized);(STATIC/'cost-per-km-data.json').write_text(serialized)
    density['sourceCostDataSha256']=hashlib.sha256(serialized.encode()).hexdigest()
    density_text=json.dumps(density,ensure_ascii=False,indent=2)+'\n'
    (OUT/'length_density_groups.json').write_text(density_text);(STATIC/'length-density-groups.json').write_text(density_text)
    export_lane_evidence(data)
    build_page(data,density)
    return data


def export_lane_evidence(data):
    fields=['id','category','program','projectName','office','region','amountPesos','lengthMeters','titleStatedLanes','titleLaneMeters','allocationPerTitleLaneMeter','inventoryEffectiveLanes','inventoryLaneMetersProxy','allocationPerInventoryLaneMeterProxy','inventoryAssetLengthMeters','inventoryAssetLaneMeters','allocationPerInventoryAssetLaneMeter','laneRateStatus','laneInventoryEvidence','surfaceDisplay','recordedConditionDisplay','surfacingYearDisplay','surfacePeerGroup','rehabGoodFairReview','recentSurfacingReview','bridgeGoodFairContextReview','inventoryPriorityReview','assetContextEvidence','sourceVolume','sourcePage']
    fields[1:1]=['matchedInventoryId','inventoryAssetWidthMeters','inventoryAssetEffectiveLanes','inventoryDimensionsStatus','inventoryDimensionsEvidence']
    projects=[{k:r.get(k) for k in fields} for r in data['projects']]
    text=json.dumps({**data['laneCost'],'projects':projects},ensure_ascii=False,indent=2)+'\n'
    (OUT/'lane_cost_evidence.json').write_text(text);(STATIC/'lane-cost-evidence.json').write_text(text)
    import io
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()} for r in projects)
    (OUT/'lane_cost_evidence.csv').write_text(stream.getvalue());(STATIC/'lane-cost-evidence.csv').write_text(stream.getvalue())


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
    head=MPB_PAGE.split('</head>')[0].replace('MPB · Multi-purpose building allocations','Cost per meter and lane-meter · coverage and scope')+'</head>'
    hero='<section class="repeat-hero"><div class="repeat-hero-primary"><span class="repeat-hero-kicker">HGAB 3rd reading · stated lengths</span><div class="repeat-hero-total"><strong>'+str(sum(r['withLength'] for r in data['summary']))+'</strong><span>line items with derivable stated segment lengths</span></div><p>Coverage is reported separately for roads, bridges, FMR and mixed work.</p></div><div class="repeat-hero-detail"><div class="repeat-hero-breakdown">'+''.join('<div><span>'+r['category']+'</span><strong>'+str(r['withLength'])+'/'+str(r['lineItems'])+' lengths · '+str(r['missingPct'])+'% without usable length</strong></div>' for r in data['summary'])+'</div><p>No coordinate distances or inferred lengths fill missing values.</p></div></section>'
    hero=hero.replace('<strong>'+str(sum(r['withLength'] for r in data['summary']))+'</strong>', '<strong>'+str(data['highRateScreen']['candidates'])+'</strong>',1).replace('line items with derivable stated segment lengths','high-rate candidates for scope review').replace('Coverage is reported separately for roads, bridges, FMR and mixed work.','Compared within the same program and similar stated-length group.')
    intro='''<section class="card"><h2>Which projects have unusually high allocation per meter?</h2><p>The first tables compare each rate with the typical rate in the same official program and a similar stated-length group. A high-rate candidate is more than twice the typical peer rate and unusually high within its peer group. This is a scope-review queue, not a verified overpricing finding. Extreme values remain visible as individual points in rate charts. Printed segments under 10m remain in tables and CSV but are excluded from rate charts. Coverage denominators include all selected extracted occurrences in each category, including those without a usable length.</p><p class="caution">These are whole line-item allocations divided by stated segment lengths, not verified construction unit costs. Bridge chainage may cover approaches rather than bridge span. Missing percentage means no usable length was recovered from the current title/project context; it does not establish that the original budget or engineering documents omit length.</p><p><a href="cost-per-km-data.json" download>Download all records and length evidence</a></p></section>'''
    intro+='<p class="caution">Outliers remain visible in rate charts as individual points. Printed segments under 10m remain in tables and CSV but are not plotted. Peer screening needs at least 20 usable records. Missing or sparse peers do not establish a normal price.</p><h3>How high-rate candidates are identified</h3><p>'+data['highRateScreen']['method']+'</p>'
    methods='''<section class="card"><h2>Length extraction and coverage methodology</h2><ul><li>Complete STA/Station/K/KM plus-form ranges are converted to meters. Explicit “Chainage 287 - Chainage 1287” values are meter offsets, giving a 1,000-meter range. Mixed bare/plus notation, such as Chainage 200 to Chainage 3 + 500, is incomplete: the bare endpoint may lack a kilometer component. No length or rate is calculated until its units and endpoint are verified. For repeat screening only, printed endpoints are assumed to be ordered min/max: a known maximum at another segment’s known minimum excludes positive overlap even if length remains uncertain. Overlapping numerical intervals are merged, never double-counted. Multiple named routes with unverified station references are withheld.</li><li>A single explicitly labeled length in meters or kilometers can supply a length. Widths, isolated stations and coordinate straight-line distances do not supply a road length.</li><li>FMR length extraction uses only the current project's row-bounded source context, including printed STA labels in the analyst's coordinate cell. Context preceding the current project title is discarded, preventing a previous project’s endpoint from becoming part of the current length. Exactly two printed STA endpoints in the remaining context can form a range. The context is retained in the downloadable data; nearby unrelated text is not searched for endpoints.</li><li>Partial or zero-length chainage, conflicting explicit lengths and ambiguous multi-route scopes remain without a usable length. No allocation amount is used to infer missing length.</li><li>The missing percentage is (all category occurrences minus occurrences with usable stated length) / all category occurrences. It includes both absent metadata and metadata that needs review. A separate rate count distinguishes usable lengths from permissible single-category ratios.</li><li>Mixed road/bridge titles are separated and no single-work rate is shown. Flood, building/water PAPs and foreign-assisted schedules are outside this page's denominator. Classification uses explicit titles and PAPs; it is not a complete inventory of physical road assets.</li><li>No rate averages are pooled across categories or PAPs. Every point identifies one allocation occurrence; rankings can change with scope, width, structures, terrain, total project components and parser corrections. High rates warrant source/quantity review, not an allegation.</li><li>Graphs and CSV follow table filters. Grouped box plots show allocation per stated meter by official program, with quartiles and every observed value; outliers are marked, not removed. Segments under 10m and rows without usable length remain in the table/CSV but are not plotted. Source volume/page and original length evidence are included. Historical stages are not used to fill current-stage gaps.</li></ul><p>The summary links to two separate leads: length-data coverage and allocation per stated meter. Coverage gaps are extraction observations, and ratios are scope-dependent screening proxies. Extremely short printed ranges can produce extreme rates; verify station endpoints and funded scope on original pages before interpreting them. Request bills of quantities, designs, funded segment boundaries, bridge spans and roadway widths before comparing actual costs.</p></section>'''
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
    controls=controls.replace("const search=section.querySelector('input')", CONTEXT_CONTROLS+"const search=section.querySelector('input')")
    controls=controls.replace("for(const c of configs){\n const section=document.createElement", "for(const c of configs){\n if(!D[c.id]?.length)continue;\n const section=document.createElement")
    controls=controls.replace("filter(r=>(!group", "filter(r=>(!surfaceFilter.value||r.surfaceDisplay===surfaceFilter.value)&&(!conditionFilter.value||r.recordedConditionDisplay===conditionFilter.value)&&(!priorityFilter.value||(priorityFilter.value==='rehab'?r.rehabGoodFairReview:priorityFilter.value==='recent'?r.recentSurfacingReview:priorityFilter.value==='bridge'?r.bridgeGoodFairContextReview:(r.rehabGoodFairReview||r.recentSurfacingReview||r.bridgeGoodFairContextReview)))&&(!group")
    controls=controls.replace("c.id==='coverage'||c.id.startsWith('coordinate-')||c.id.startsWith('lane-')", "c.id==='coverage'||c.id.startsWith('coordinate-')||c.id.startsWith('lane-')||c.id.startsWith('context-')")
    controls=controls.replace("!c.id.startsWith('lane-')&&D[c.id]", "!c.id.startsWith('lane-')&&!c.id.startsWith('context-')&&D[c.id]")
    controls=controls.replace("const max=Math.max(1,...points.map",BOXPLOT_BRANCH+"\n const max=Math.max(1,...points.map")
    controls=controls.replace("c.chart==='retention'?'Comparison pairs by HGAB retention status · all filtered rows'", "c.chart==='boxplot'?'Allocation per stated meter by official program · quartiles, whiskers and all observations (log scale)':c.chart==='retention'?'Comparison pairs by HGAB retention status · all filtered rows'")
    controls=controls.replace("/pesos|projects|count/i.test(key)","/pesos|projects|count|lengthmeters|allocationper|lineitems|withlength|withoutlength|missingpct/i.test(key)")
    approximation_note='<section class="card"><h2>Coordinate-based allocation per meter · approximation</h2><p>Additional tables below divide whole allocations by straight-line separation between two printed endpoints. Separately labeled FMR segment chords are summed. A road can curve or include structures, so this distance is not a measured road or bridge length. These approximate rates are kept outside stated-length coverage, historical price comparisons and high-rate flags. Review flags, coincident endpoints, unpaired coordinate lists and mixed road/bridge rates are withheld. No distance between different projects supplies a project-length denominator.</p></section>'
    spatial_chart='''<section class="card" id="road-bridge-3d"><h2>Roads and bridges · length, lanes and allocation density</h2><p>Each chart stacks projects in planes of five parallel road strips: five side by side, then the next five above them. Strips share a starting edge. Length runs along each strip, lane count sets its crosswise width, and allocation per lane-meter sets gently log-scaled thickness. The charts show the 30 projects with the highest allocation density in each group; all eligible projects remain in the tables. Each group's thickness scale is separate. This is a screening comparison, not a verified construction cost.</p><p id="road-bridge-3d-count" class="caution"></p><h3>Roads · 30 highest density</h3><div id="roads-3d-plot" role="img" aria-label="Interactive 3D chart of the 30 highest-density road strips arranged five per plane, showing project length, lanes, and log-scaled density thickness" style="width:100%;min-height:500px"></div><h3>Bridges · 30 highest density</h3><div id="bridges-3d-plot" role="img" aria-label="Interactive 3D chart of the 30 highest-density bridge strips arranged five per plane, showing project length, lanes, and log-scaled density thickness" style="width:100%;min-height:500px"></div><p class="caution">Drag to rotate and zoom. Hover on a strip for the project, exact dimensions, lane-count basis, allocation and source. Thickness uses a gentler, slightly expanded log₁₀ allocation-per-lane-meter scale within each group; each plane is separated for visibility. Projects without a usable length and lane-count basis stay in their tables.</p></section>'''
    chart_rows=[];spatial_counts={}
    for category in ('Roads','Bridges'):
        eligible=[]
        for row in data['projects']:
            if row.get('category')!=category or float(row.get('lengthMeters') or 0)<10 or float(row.get('amountPesos') or 0)<=0:continue
            if float(row.get('titleStatedLanes') or 0)>0:lanes=float(row['titleStatedLanes']);basis='Stated in project title/context'
            elif float(row.get('inventoryEffectiveLanes') or 0)>0:lanes=float(row['inventoryEffectiveLanes']);basis='Matched existing-road inventory estimate'
            elif float(row.get('inventoryAssetEffectiveLanes') or 0)>0:lanes=float(row['inventoryAssetEffectiveLanes']);basis='Matched existing-asset dimensions'
            elif category=='Bridges' and float(row.get('manualLaneEstimateLanes') or 0)>0:lanes=float(row['manualLaneEstimateLanes']);basis='Assumed 2 lanes for group comparison'
            else:continue
            eligible.append({**row,'plotLanes':lanes,'laneBasis':basis,'density':float(row['amountPesos'])/(float(row['lengthMeters'])*lanes)})
        spatial_counts[category]=len(eligible)
        chart_rows.extend(sorted(eligible,key=lambda row:float(row['density']),reverse=True)[:30])
    spatial_script = r'''
try{
const chartData=JSON.parse(document.getElementById('road-bridge-3d-data').textContent),spatialRows=chartData.projects||[],spatialCounts=chartData.counts||{};
document.getElementById('road-bridge-3d-count').textContent=`${Number(spatialCounts.Roads||0).toLocaleString()} eligible road and ${Number(spatialCounts.Bridges||0).toLocaleString()} eligible bridge projects · chart selects 30 highest-density projects per group · five strips per plane · length = stated meters · width = lane count · thickness = amplified log-scaled allocation per lane-meter.`;
function renderStatic3D(category,id,error){const target=document.getElementById(id),rows=spatialRows.filter(r=>r.category===category).sort((a,b)=>Number(b.density)-Number(a.density)).slice(0,30);if(!target)return;const maxLength=Math.max(1,...rows.map(r=>Number(r.lengthMeters))),logs=rows.map(r=>Math.log10(Math.max(1,Number(r.density)))),minLog=Math.min(...logs),maxLog=Math.max(...logs),width=1100,height=470,depth=16,faces=[];rows.forEach((r,index)=>{const col=index%5,plane=Math.floor(index/5),x=44+col*205,y=74+plane*60,len=38+Math.max(0,Number(r.lengthMeters))/maxLength*112,thick=6+(maxLog===minLog?1:(Math.log10(Math.max(1,Number(r.density)))-minLog)/(maxLog-minLog))*20,side=category==='Roads'?'#00246A':'#8E1020',top=category==='Roads'?'#6EA6FF':'#FF9D9D',front=category==='Roads'?'#0038A8':'#CE1126',title=`${r.projectName} · ${Number(r.lengthMeters).toLocaleString()} m · ${r.plotLanes} lanes · ₱${Number(r.density).toLocaleString(undefined,{maximumFractionDigits:2})}/lane-meter`;faces.push(`<g><title>${title.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')}</title><polygon points="${x+len},${y-thick} ${x+len+depth},${y-depth-thick} ${x+len+depth},${y-depth+Math.max(8,r.plotLanes*3)-thick} ${x+len},${y+Math.max(8,r.plotLanes*3)-thick}" fill="${side}"/><polygon points="${x},${y-thick} ${x+depth},${y-depth-thick} ${x+len+depth},${y-depth-thick} ${x+len},${y-thick}" fill="${top}"/><polygon points="${x},${y-thick} ${x+len},${y-thick} ${x+len},${y+Math.max(8,r.plotLanes*3)-thick} ${x},${y+Math.max(8,r.plotLanes*3)-thick}" fill="${front}"/><text x="${x}" y="${y+31}" font-size="10" fill="#212121">${index+1}</text></g>`)});target.innerHTML=`<p class="caution">Interactive WebGL could not initialize; showing a static 3D view. Hover a block for its project and values.${error?' '+String(error.message||error).slice(0,140):''}</p><svg style="display:block;width:100%;height:auto;max-height:520px" viewBox="0 0 ${width} ${height}" role="img" aria-label="Static isometric 3D ${category.toLowerCase()} comparison">${faces.join('')}</svg>`}
function supportsWebGL(){try{const c=document.createElement('canvas');return !!(c.getContext('webgl2')||c.getContext('webgl')||c.getContext('experimental-webgl'))}catch(e){return false}}
function cuboidTrace(category,color){const rows=spatialRows.filter(r=>r.category===category).sort((a,b)=>Number(b.density)-Number(a.density)).slice(0,30);const maxLength=Math.max(1,...rows.map(r=>Number(r.lengthMeters))),maxLanes=Math.max(1,...rows.map(r=>r.plotLanes)),logs=rows.map(r=>Math.log10(Math.max(1,r.density))),minLog=Math.min(...logs),maxLog=Math.max(...logs),lengthScale=18/maxLength,laneScale=.62,rowGap=maxLanes*laneScale+1.25,planePitch=3.8,t={type:'mesh3d',name:category,color,opacity:.96,flatshading:true,hoverinfo:'text',x:[],y:[],z:[],i:[],j:[],k:[],text:[],hovertemplate:'%{text}<extra>'+category+'</extra>'};const faces=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]];rows.forEach((r,index)=>{const position=index%5,plane=Math.floor(index/5),x0=0,y0=position*rowGap,z0=plane*planePitch,dx=Math.max(.08,Number(r.lengthMeters)*lengthScale),dy=Math.max(.45,r.plotLanes*laneScale),logDensity=Math.log10(Math.max(1,r.density)),normalized=maxLog===minLog?1:(logDensity-minLog)/(maxLog-minLog),dz=.4+Math.pow(normalized,.9)*2.0,vertices=[[x0,y0,z0],[x0+dx,y0,z0],[x0+dx,y0+dy,z0],[x0,y0+dy,z0],[x0,y0,z0+dz],[x0+dx,y0,z0+dz],[x0+dx,y0+dy,z0+dz],[x0,y0+dy,z0+dz]],base=t.x.length;vertices.forEach(v=>{t.x.push(v[0]);t.y.push(v[1]);t.z.push(v[2]);t.text.push('<b>'+r.projectName+'</b><br>'+category+' · plane '+(plane+1)+'<br>'+r.program+'<br>Length: '+Number(r.lengthMeters).toLocaleString()+' m<br>Lanes: '+r.plotLanes+' · '+r.laneBasis+'<br>Allocation: ₱'+Number(r.amountPesos).toLocaleString()+'<br>Density: ₱'+Number(r.density).toLocaleString(undefined,{maximumFractionDigits:2})+'/lane-meter<br>Source: '+r.sourceVolume+' · p. '+r.sourcePage)});faces.forEach(f=>{t.i.push(base+f[0]);t.j.push(base+f[1]);t.k.push(base+f[2])})});return t}
function renderRoadBridge3D(){if(!window.Plotly||!supportsWebGL()){renderStatic3D('Roads','roads-3d-plot');renderStatic3D('Bridges','bridges-3d-plot');return}for(const [category,color,id] of [['Roads','#0038A8','roads-3d-plot'],['Bridges','#CE1126','bridges-3d-plot']]){const target=document.getElementById(id),trace=cuboidTrace(category,color),layout={autosize:true,height:600,margin:{l:0,r:0,b:0,t:12},paper_bgcolor:'rgba(0,0,0,0)',scene:{aspectmode:'manual',aspectratio:{x:3.1,y:2.4,z:1.3},xaxis:{visible:false},yaxis:{visible:false},zaxis:{title:'Log density · stacked planes',visible:true,gridcolor:'#dce5e3',zerolinecolor:'#b9c9c6'},camera:{eye:{x:1.6,y:1.5,z:1.25}}},font:{family:'system-ui, sans-serif',color:'#212121'}};try{Promise.resolve(Plotly.newPlot(target,[trace],layout,{responsive:true,displaylogo:false,scrollZoom:true})).then(()=>requestAnimationFrame(()=>{if(!target.querySelector('canvas'))renderStatic3D(category,id,new Error('Plotly did not create its WebGL canvas'))})).catch(error=>renderStatic3D(category,id,error))}catch(error){renderStatic3D(category,id,error)}}}
renderRoadBridge3D();window.addEventListener('resize',()=>{if(window.Plotly){Plotly.Plots.resize('roads-3d-plot');Plotly.Plots.resize('bridges-3d-plot')}});
}catch(error){for(const id of ['roads-3d-plot','bridges-3d-plot']){const target=document.getElementById(id);if(target&&!target.querySelector('svg,canvas'))target.innerHTML=`<p class=\"caution\">3D comparison could not initialize: ${String(error.message||error).slice(0,200)}</p>`}}
'''
    # Matching/coverage evidence and allocation calculations share controls/data,
    # but render disjoint table sets. The evidence page is an internal link only.
    evidence_name='cost-matching.html'
    matching_ids="['coverage','context-review','lane-dimensions-roads','lane-dimensions-bridges']"
    computation_start=start+"\nconfigs.splice(0,configs.length,...configs.filter(c=>!"+matching_ids+".includes(c.id)));\n"
    matching_start=start+"\nconfigs.splice(0,configs.length,...configs.filter(c=>"+matching_ids+".includes(c.id)));\n"
    data_script='<script id="length-data" type="application/json">'+json.dumps(data,ensure_ascii=False).replace('</','<\\/')+'</script>'
    chart_data_script='<script id="road-bridge-3d-data" type="application/json">'+json.dumps({'projects':chart_rows,'counts':spatial_counts},ensure_ascii=False).replace('</','<\\/')+'</script>'
    links='<section class="card"><h2>Calculations and supporting evidence</h2><p><a href="cost-per-km.html">Cost calculations and peer comparisons</a> · <a href="cost-matching.html">Asset matching, dimensions and length coverage</a></p></section>'
    lane_note='<p>Lane-meter calculations divide allocation by meters × lanes. Title-stated lanes, existing-inventory lane estimates and whole-bridge asset estimates are displayed separately. <a href="cost-matching.html#lane-meter-evidence">See matching rules, exclusions and source vintage</a>. Existing asset size does not fill a missing funded length.</p>'
    evidence_limits='<aside id="report-evidence-notice" role="note"><strong>Evidence limits.</strong> These are budget allocations paired with stated or inventory-derived dimensions, not verified unit costs or completed work. Inventory dimensions do not establish funded scope; missing or ambiguous lengths remain unresolved. Check the cited records before comparing projects.</aside>'
    plotly_asset=STATIC/'plotly-2.35.2.min.js'
    if not plotly_asset.is_file():raise FileNotFoundError(f'Local Plotly bundle missing: {plotly_asset}')
    plotly_version=hashlib.sha256(plotly_asset.read_bytes()).hexdigest()[:12]
    page=head+'<body class="bettergov-research"><header><div class="eyebrow">BetterGov · Budget research</div><h1>Cost per meter and lane-meter</h1><p>HGAB 3rd reading · calculations and peer comparisons</p></header><main>'+evidence_limits+hero+links+intro+spatial_chart+lane_note+approximation_note+'<div id="sections"></div>'+year_comparison+render_density(density)+'</main>'+data_script+chart_data_script+'<script src="plotly-2.35.2.min.js?v='+plotly_version+'"></script><script>'+computation_start+controls+'</script><script>'+spatial_script+'</script></body></html>'
    from build_report_heroes import STYLE,hero as lead_card
    page=page.replace('__HERO_STYLE__',STYLE)
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    page=apply_uniform_menu_page(page,'cost-per-km.html')
    from report_table_presentation import publish_assets,apply_page as apply_report_styles
    page=apply_report_styles(page,publish_assets())
    (STATIC/'cost-per-km.html').write_text(page);(OUT/'cost-per-km.html').write_text(page)
    recovered=sum(r['assetLengthRecords'] for r in data['laneCost']['summary'])
    evidence_hero=lead_card('HGAB 3rd reading · matching and coverage',f'{recovered:,}',
        'line items with recovered existing-asset length','', 'source-backed asset dimensions',
        [(r['category'],f"{r['assetLengthRecords']:,} / {r['lineItems']:,}",'existing-asset lengths recovered') for r in data['laneCost']['summary']],
        'Asset dimensions and funded segment lengths have separate coverage counts. Inventory extent does not establish funded work quantities.')
    evidence_head=head.replace('Cost per meter and lane-meter · coverage and scope','Asset matching and length coverage')
    evidence_limits='<aside id="report-evidence-notice" role="note"><strong>Evidence limits.</strong> These are budget allocations paired with stated or inventory-derived dimensions, not verified unit costs or completed work. Inventory dimensions do not establish funded scope; missing or ambiguous lengths remain unresolved. Check the cited records before comparing projects.</aside>'
    evidence_page=evidence_head+'<body class="bettergov-research"><header><div class="eyebrow">BetterGov · Budget research</div><h1>Asset matching and length coverage</h1><p>HGAB 3rd reading · road and bridge inventory evidence</p></header><main>'+evidence_limits+evidence_hero+links+lane_overview(data)+notation_overview(data)+'<div id="sections"></div>'+length_overview(data)+methods+'</main>'+data_script+'<script>'+matching_start+controls+'</script></body></html>'
    evidence_page=evidence_page.replace('__HERO_STYLE__',STYLE)
    # The template can contain the style placeholder; the shared hero helper
    # needs the same stylesheet when it is not present in that template.
    if 'id="report-hero-style"' not in evidence_page:evidence_page=evidence_page.replace('</head>',STYLE+'</head>',1)
    evidence_page=apply_uniform_menu_page(evidence_page,evidence_name)
    evidence_page=apply_report_styles(evidence_page,publish_assets())
    (STATIC/evidence_name).write_text(evidence_page);(OUT/evidence_name).write_text(evidence_page)



def lane_overview(data):
    from build_investigation_summary import table,esc
    lane=data['laneCost']
    body='<section class="card" id="lane-meter-evidence"><h2>How much allocation per lane-meter?</h2><p>One lane-meter is one meter of one lane. A two-lane, 100-meter funded segment has 200 lane-meters. Only explicit title lane counts supply the title-stated measure below. Existing inventory lanes supply a separate estimate; they do not verify the lanes funded by the allocation. Widening needs the additional lanes actually funded.</p>'
    body+='<figure><figcaption>Usable lane-rate records by category · teal: title-stated lanes; orange: stated-length inventory estimates; blue: existing-asset bridge estimates. Counts can overlap.</figcaption><svg viewBox="0 0 1000 280" role="img" aria-label="Title lane-rate and inventory estimate coverage">'
    maximum=max(1,max(max(r['titleLaneRateRecords'],r['inventoryProxyRateRecords'],r['existingAssetLaneRateRecords']) for r in lane['summary']))
    for i,row in enumerate(lane['summary']):
        x=80+i*230
        for offset,field,color in [(0,'titleLaneRateRecords','#087e78'),(60,'inventoryProxyRateRecords','#b65b09'),(120,'existingAssetLaneRateRecords','#4768a8')]:
            height=180*row[field]/maximum
            body+=f'<rect x="{x+offset}" y="{210-height}" width="48" height="{height}" fill="{color}"/><text x="{x+offset}" y="{200-height}">{row[field]:,}</text>'
        body+=f'<text x="{x}" y="245">{esc(row["category"])}</text>'
    body+='</svg></figure>'
    body+=table(['Category','Line items','Title-stated lane rates','Inventory matches','Stated-length inventory lane-rate estimates','Existing-asset lane-rate estimates','Without title lane rate (%)'],[[r['category'],r['lineItems'],r['titleLaneRateRecords'],r['inventoryMatchedRecords'],r['inventoryProxyRateRecords'],r['existingAssetLaneRateRecords'],r['withoutTitleLaneRatePct']] for r in lane['summary']])
    body+='<h3>Dimensions recovered from matched assets</h3><p>Existing asset dimensions can be recovered even when a title does not state the funded length. Road figures describe the recorded contiguous extent of the matched inventory section, which may not cover the whole section; bridge figures describe the existing bridge. They are separate from funded-project length coverage and do not fill missing project lengths or enter per-meter price flags. Counts are budget line items, so an asset may occur more than once.</p>'
    body+='<figure><figcaption>Recovered inventory dimensions by category · teal: asset length; blue: lanes; orange: width. Counts overlap.</figcaption><svg viewBox="0 0 1000 280" role="img" aria-label="Recovered asset dimensions coverage">'
    maximum=max([r['assetLengthRecords'] for r in lane['summary']]+[1])
    for i,r in enumerate(lane['summary']):
        x=60+i*245
        for offset,field,color in [(0,'assetLengthRecords','#087e78'),(55,'assetLaneRecords','#4768a8'),(110,'assetWidthRecords','#b65b09')]:
            height=180*r[field]/maximum
            body+=f'<rect x="{x+offset}" y="{210-height}" width="42" height="{height}" fill="{color}"/><text x="{x+offset}" y="{200-height}">{r[field]:,}</text>'
        body+=f'<text x="{x}" y="245">{esc(r["category"])}</text>'
    body+='</svg></figure>'
    body+=table(['Category','Line items','Matched asset ID','Asset length recovered','Asset lanes recovered','Asset width recovered','Missing stated length, asset length available'],[[r['category'],r['lineItems'],r['inventoryMatchedRecords'],r['assetLengthRecords'],r['assetLaneRecords'],r['assetWidthRecords'],r['missingStatedLengthWithAssetLengthRecords']] for r in lane['summary']])
    body+='<h3>Lane matching and exclusions</h3><ul>'+''.join('<li>'+esc(v)+'</li>' for v in lane['methodology'])+'</ul>'
    context=lane['assetContext']
    body+='<h3>Surface, condition and prior surfacing</h3><p>'+esc(context['method'])+'</p><p>'+esc(context['limits'])+'</p>'
    body+='<figure><figcaption>Condition evidence · green: matched context (may be partial); blue: fully assessed road ranges; orange: Good/Fair rehabilitation flags; gray: undated Good/Fair bridge review. Counts overlap.</figcaption><svg viewBox="0 0 1000 280" role="img" aria-label="Matched asset condition and review coverage">'
    maximum=max([r['withContext'] for r in context['byCategory'].values()]+[1])
    for i,(category,row) in enumerate(context['byCategory'].items()):
        x=40+i*245
        for offset,field,color in [(0,'withContext','#087e78'),(45,'fullyAssessedRoadRecords','#4768a8'),(90,'rehabGoodFairCandidates','#b65b09'),(135,'bridgeGoodFairUndatedContext','#79848b')]:
            height=180*row[field]/maximum
            body+=f'<rect x="{x+offset}" y="{210-height}" width="36" height="{height}" fill="{color}"/><text x="{x+offset}" y="{200-height}">{row[field]:,}</text>'
        body+=f'<text x="{x}" y="245">{esc(category)}</text>'
    body+='</svg></figure>'
    body+=table(['Category','Line items','Matched context · can be partial','Fully assessed road ranges','Rehab on assessed Good/Fair','Recent surfacing · five-year screen','Good/Fair bridges · assessment date unknown'],[[k,r['lineItems'],r['withContext'],r['fullyAssessedRoadRecords'],r['rehabGoodFairCandidates'],r['recentSurfacingCandidates'],r['bridgeGoodFairUndatedContext']] for k,r in context['byCategory'].items()])
    body+='<p>Surface and condition filters apply to the cost tables below. Price peers use the same recorded surface, condition and assessment-year group when available; records without a supported match are compared only within the explicitly unknown-context group. A condition flag and a high-rate flag answer different questions. Last surfacing comes from the older lane inventory, whose latest reported years are not a complete record of subsequent works. The five-year threshold is a disclosed screening choice, not an engineering service-life standard. Bridge construction, edit and copyright dates never substitute for a condition assessment date.</p>'
    body+='<p>Lane tables and charts below have program filters, sorting and CSV exports. Estimates do not enter the existing per-meter high-rate flags or historical comparison. Named overpasses, flyovers and viaducts now use bridge peers, including Burol Overpass; ordinary road peers are not appropriate for those structures.</p>'
    body+='<h3>Inventory sources and vintage</h3>'+table(['Inventory','Rows','Source vintage statement'],[[r['profile'],r['rows'],r['copyright']] for r in lane['sources']])
    body+='<p>The matched inventory ID column shows the supported road section ID or bridge ID, rather than a budget occurrence ID or an ArcGIS object ID. A dash means no supported inventory match. Asset identity does not verify funded quantities or district attribution.</p><p><a href="lane-cost-evidence.csv" download>Download all lane matches, rates and exclusions (CSV)</a> · <a href="lane-cost-evidence.json" download>Download full lane evidence, methodology and source hashes (JSON)</a></p>'
    return body+'</section>'


def notation_overview(data):
    from build_investigation_summary import table, esc
    rows=data['notationCoverage'];gained=sum(r['newlyRecoveredLengths'] for r in rows)
    body=f'<section id="chainage-coverage-update" class="card"><h2>{gained:,} more line items now have usable stated lengths</h2><p>The parser now recognizes two consecutive Station labels without a dash, and numeric Chainage ranges. For example, Station 1+215 Station 2+065 gives 850 meters; Chainage 1287 - Chainage 2288 gives 1,001 meters. Rates, peer groups, high-rate rankings and the FY2026 comparison use the refreshed lengths.</p>'
    body+='<figure><figcaption>Length coverage by category · teal: earlier lengths still usable; orange: newly recovered; gray: still missing or unusable. Each bar represents 100% of that category.</figcaption><svg viewBox="0 0 1050 250" role="img" aria-label="Usable length coverage gained from expanded chainage notation">'
    for i,r in enumerate(rows):
        y=25+55*i;x=220
        body+=f'<text x="8" y="{y+22}" font-size="15">{esc(r["category"])}</text>'
        for key,color in [('earlierLengthsStillUsable','#087e78'),('newlyRecoveredLengths','#b65b09'),('withoutUsableLength','#adb5bd')]:
            width=750*r[key]/r['lineItems'] if r['lineItems'] else 0
            body+=f'<rect x="{x:.2f}" y="{y}" width="{width:.2f}" height="30" fill="{color}"><title>{esc(r["category"])} · {esc(key)}: {r[key]:,}</title></rect>';x+=width
    body+='</svg></figure>'
    body+=table(['Category','Line items','Usable lengths · earlier rules','Newly recovered lengths','Earlier lengths now withheld','Usable lengths · current','Missing / unusable (%)'],[[r['category'],r['lineItems'],r['earlierUsableLengths'],r['newlyRecoveredLengths'],r['earlierLengthsNowWithheld'],r['currentUsableLengths'],r['missingPct']] for r in rows])
    return body+'<p>Earlier-rule counts are recomputed on the same current HGAB records using the previous plus-form parser, including existing explicit-length and row-bounded FMR rules. Both runs use the same records. The current rules also withhold multiple road IDs whose station references cannot safely be combined; the withheld column makes that quality correction explicit. Every record in the download includes its earlier length status and whether this update recovered a usable length. Recognizing a range does not verify its funded physical extent; adjacent endpoints do not imply overlapping work.</p><p><a href="cost-per-km-data.json" download>Download current lengths, rates and notation-recovery evidence</a></p></section>'


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


CONTEXT_CONTROLS=r'''
const contextOptions=field=>[...new Set(D[c.id].map(r=>r[field]).filter(Boolean))].sort().map(v=>'<option value="'+esc(v)+'">'+esc(v)+'</option>').join('');
section.querySelector('.controls').insertAdjacentHTML('beforeend','<select class="surface-filter" aria-label="Recorded surface"><option value="">All surfaces / materials</option>'+contextOptions('surfaceDisplay')+'</select><select class="condition-filter" aria-label="Recorded condition and assessment year"><option value="">All conditions / assessment years</option>'+contextOptions('recordedConditionDisplay')+'</select><select class="priority-filter" aria-label="Condition or surfacing review"><option value="">All condition / surfacing statuses</option><option value="rehab">Road rehab · recorded Good/Fair</option><option value="recent">Pavement work · surfaced within five budget years</option><option value="bridge">Good/Fair bridges · assessment date unknown</option><option value="any">Any condition / surfacing review</option></select>');
const surfaceFilter=section.querySelector('.surface-filter'),conditionFilter=section.querySelector('.condition-filter'),priorityFilter=section.querySelector('.priority-filter');
for(const control of [surfaceFilter,conditionFilter,priorityFilter]){control.hidden=!D[c.id].some(r=>r.assetContextEvidence);control.addEventListener('change',()=>{page=0;render()});}
'''

JS_START=r'''
const D=JSON.parse(document.getElementById('length-data').textContent);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+num(v);
const configs=[];const coverageConfig={id:'coverage',title:'Length coverage by category and official program',note:'Each program has its own denominator. Missing means absent or unusable extracted length evidence; no construction price average is pooled.',columns:[['Category','category'],['Official program','program'],['Line items','lineItems'],['Usable lengths','withLength'],['Without usable length','withoutLength'],['Missing / unusable (%)','missingPct'],['Rate records','withRate'],['Allocation pesos','allocationPesos'],['Allocation without usable length pesos','unusableLengthAllocationPesos']],metric:'missingPct',chart:'vertical'};
D.projects.forEach(r=>{r.sourceLabel=r.sourceVolume+' · p. '+r.sourcePage;const e=r.laneInventoryEvidence;r.laneMatchEvidence=e?[e.bridgeId||e.sectionId,e.stationEvidence,'Inventory object IDs: '+e.inventoryObjectIds.join(', ')].join(' · '):'No compatible inventory match';});
const contextColumns=[['Surface / material','surfaceDisplay'],['Recorded condition / year','recordedConditionDisplay'],['Last surfaced year','surfacingYearDisplay']];
D['context-review']=D.projects.filter(r=>r.rehabGoodFairReview||r.recentSurfacingReview||r.bridgeGoodFairContextReview);
configs.push({id:'context-review',title:'Condition and recent-surfacing review candidates',note:'Rehabilitation on fully matched assessed Good/Fair roads, pavement work after recorded recent surfacing, and Good/Fair bridges awaiting assessment-date verification. These are source-review leads, not findings of unnecessary work. Surface, condition and review filters apply independently.',columns:[['Project','projectName'],['Official program','program'],...contextColumns,['Allocation pesos','amountPesos'],['Review evidence','inventoryPriorityReview'],['Source','sourceLabel']],metric:'amountPesos',chart:'vertical'});
for(const category of ['Roads','Bridges']){
 for(const basis of ['title','inventory']){
  const rate=basis==='title'?'allocationPerTitleLaneMeter':'allocationPerInventoryLaneMeterProxy',id='lane-'+basis+'-'+category.toLowerCase();
  D[id]=D.projects.filter(r=>r.category===category&&r[rate]!=null);
  configs.push({id,title:category+(basis==='title'?' · title-stated allocation per lane-meter':' · inventory lane-meter estimate'),note:basis==='title'?'Explicit lane count and usable length in the current project title/context. Whole allocation, not verified construction unit cost. No historical or inventory lane count fills a missing funded quantity.':'Existing inventory lanes, not verified funded lanes. Fully matched ranges only; widening, scope conflicts and bridge span mismatches withheld. Inventory estimates do not enter high-rate flags. Select a program before comparing scope.',columns:[['Project','projectName'],['Official program','program'],['Stated meters','lengthMeters'],[basis==='title'?'Title lanes':'Inventory effective lanes',basis==='title'?'titleStatedLanes':'inventoryEffectiveLanes'],['Allocation pesos','amountPesos'],[basis==='title'?'Allocation pesos per title lane-meter':'Estimated allocation pesos per inventory lane-meter',rate],['Lane-rate status','laneRateStatus'],['Inventory / station evidence','laneMatchEvidence'],['Source','sourceLabel']],metric:rate,chart:'vertical'});
 }
}
for(const category of ['Roads','Bridges']){
 const id='lane-dimensions-'+category.toLowerCase();D[id]=D.projects.filter(r=>r.category===category&&r.inventoryDimensionsEvidence);
 configs.push({id,title:category+' · recovered existing-asset dimensions',note:'Inventory dimensions, not funded work quantities. Road length is the union of recorded section measures with no internal gaps, not a guarantee of full road-section coverage; effective lanes and width are measure-weighted with conflicts withheld. Bridge length is existing span. Missing project lengths remain missing. Graph shows asset length; all dimensions and evidence remain in CSV.',columns:[['Project','projectName'],['Official program','program'],['Stated funded meters','lengthMeters'],['Existing asset meters','inventoryAssetLengthMeters'],['Existing asset effective lanes','inventoryAssetEffectiveLanes'],['Existing asset width meters','inventoryAssetWidthMeters'],['Allocation pesos','amountPesos'],['Dimension evidence','inventoryDimensionsStatus'],['Source','sourceLabel']],metric:'inventoryAssetLengthMeters',chart:'vertical'});
}
D['lane-asset-bridges']=D.projects.filter(r=>r.allocationPerInventoryAssetLaneMeter!=null);
configs.push({id:'lane-asset-bridges',title:'Bridges · allocation per existing-asset lane-meter',note:'Rehabilitation/major repair and strengthening/retrofitting only. Whole allocation divided by the inventory bridge span and existing lanes; funded repair extent is unknown. This is an asset-size estimate, not construction unit cost. Replacement, widening and new bridges are excluded. No asset length fills missing project length or enters high-rate flags.',columns:[['Project','projectName'],['Official program','program'],['Inventory bridge span meters','inventoryAssetLengthMeters'],['Inventory lanes','inventoryEffectiveLanes'],['Allocation pesos','amountPesos'],['Estimated allocation pesos per existing-asset lane-meter','allocationPerInventoryAssetLaneMeter'],['Inventory identity and evidence','laneMatchEvidence'],['Source','sourceLabel']],metric:'allocationPerInventoryAssetLaneMeter',chart:'vertical'});
D['lane-manual-estimate-bridges']=D.projects.filter(r=>r.manualLaneEstimateLanes!=null);
configs.push({id:'lane-manual-estimate-bridges',title:'Bridges · no stated lane count · cost density',note:'One comparison group of all bridge-category projects with usable stated lengths and no source-stated or inventory lane count. To calculate a comparable lane-meter cost density, every row uses the same assumed 2 lanes (the minimum baseline). This is not a claim about actual lanes or verified construction cost, and it does not enter peer flags. Printed chainage may include approaches or other scope.',columns:[['Project','projectName'],['Official program','program'],['Stated segment meters','lengthMeters'],['Assumed lanes for group comparison','manualLaneEstimateLanes'],['Allocation pesos','amountPesos'],['Cost density · pesos per assumed lane-meter','allocationPerManualLaneMeter'],['Group basis and scope caveat','manualLaneEstimateBasis'],['Source','sourceLabel']],metric:'allocationPerManualLaneMeter',chart:'vertical'});
D['bridges-no-length']=D.projects.filter(r=>r.category==='Bridges'&&r.costDensityReviewFlag);
configs.push({id:'bridges-no-length',title:'Bridges · missing length · cost-density review flags',note:'These bridge-category projects have no usable stated length, so their cost density cannot be calculated. Each red flag marks a missing denominator for human review; it is a data-coverage flag, not a finding. Rows are separate from the two-lane cost-density comparison.',columns:[['Project','projectName'],['Official program','program'],['Review flag','costDensityReviewFlag'],['Why flagged','costDensityReviewReason'],['Length extraction status','lengthStatus'],['Length evidence checked','lengthEvidence'],['Allocation pesos','amountPesos'],['Source','sourceLabel']],metric:'amountPesos',chart:'vertical'});
for(const category of ['Roads','Bridges','FMR','Mixed roads / bridges']){
 D.projects.forEach(r=>r.sourceLabel=r.sourceVolume+' · p. '+r.sourcePage);
 const summary=D.summary.find(r=>r.category===category),id=category.toLowerCase().replace(/[^a-z]+/g,'-');D[id]=D.projects.filter(r=>r.category===category&&(category!=='Bridges'||r.lengthMeters!=null));
 const title=category==='Bridges'?'Bridges · projects with usable lengths and stated-meter rates':category+' · all projects and stated-meter rates';
 configs.push({id,title,note:`${summary.withLength.toLocaleString()} of ${summary.lineItems.toLocaleString()} line items have usable stated lengths; ${summary.missingPct}% do not. ${summary.withRate} rate records. Choose an official program to keep work types separate.`,columns:[['Project','projectName'],['Official program','program'],['Stated meters','lengthMeters'],['Allocation pesos','amountPesos'],...(category==='Roads'||category==='Bridges'?[['Inventory lanes','inventoryEffectiveLanes'],['Allocation per stated lane-meter','allocationPerInventoryLaneMeterProxy'],['Allocation per existing-asset lane-meter','allocationPerInventoryAssetLaneMeter'],['Lane data status','laneRateStatus']]:[]),['Allocation per meter pesos','allocationPerStatedMeter'],['Typical peer rate pesos/meter','typicalPeerRate'],['Times typical peer rate','peerRateMultiple'],['Review status','rateReview'],['Source','sourceLabel']],metric:'allocationPerStatedMeter',chart:'boxplot'});
}
configs.push(coverageConfig);
for(const c of configs){if((c.id.startsWith('lane-')||['roads','bridges'].includes(c.id))&&D[c.id].some(r=>r.assetContextEvidence))c.columns.splice(2,0,...contextColumns);}
for(const category of ['Roads','Bridges','FMR','Mixed roads / bridges','Flood control','Other non-MPB']){
 const id='coordinate-'+category.toLowerCase().replace(/[^a-z]+/g,'-');
 D[id]=D.projects.concat(D.coordinateOnlyProjects||[]).filter(r=>r.category===category&&r.approximateLengthMeters!=null);
 configs.push({id,title:category+' · coordinate-distance APPROXIMATION',note:'Straight-line endpoint separation, not measured construction length. Search and CSV include coordinate normalization evidence. These rates do not contribute to high-rate flags or stated-length coverage. Mixed work and building-location separations have no linear-work rate.',columns:[['Project','projectName'],['Official program','program'],['Approximate meters','approximateLengthMeters'],['Allocation pesos','amountPesos'],['Approximate allocation per meter pesos','approximateAllocationPerMeter'],['Approximation status','approximationStatus'],['Source','sourceLabel']],metric:['Mixed roads / bridges','Other non-MPB'].includes(category)?'approximateLengthMeters':'approximateAllocationPerMeter',chart:'vertical'});
}
for(const c of configs){if(c.id.startsWith('lane-')||c.id.startsWith('context-')||/roads|bridges/.test(c.id))c.columns.splice(1,0,['Matched inventory ID','matchedInventoryId']);}
'''
BOXPLOT_BRANCH=r'''
if(c.chart==='boxplot'){
 const rates=rows.filter(r=>Number(r.lengthMeters)>=10&&Number(r.allocationPerStatedMeter)>0);
 if(!rates.length)return '<p>No projects with usable stated lengths to plot. All projects remain in the table.</p>';
 const groups=new Map();rates.forEach(r=>{const k=r.program||'Program not stated';if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r)});
 const series=[...groups.entries()].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]));
 const vals=rates.map(r=>Number(r.allocationPerStatedMeter)),min=Math.min(...vals),max=Math.max(...vals),lo=Math.log10(min),hi=Math.log10(max>min?max:min*1.05),left=300,right=1030,x=v=>left+(Math.log10(Math.max(min,v))-lo)/(hi-lo)*(right-left),rowH=36,height=58+series.length*rowH;
 let body='<text x="'+left+'" y="18" font-size="11" fill="#526c78">Stated-meter rates for segments ≥10m · box = middle 50% · dots = every project · log scale</text>';
 const ticks=[min,...Array.from({length:Math.max(0,Math.floor(hi)-Math.ceil(lo)+1)},(_,i)=>10**(Math.ceil(lo)+i)).filter(v=>v>min&&v<max),max];
 ticks.forEach(v=>{const xx=x(v);body+='<line x1="'+xx+'" y1="34" x2="'+xx+'" y2="'+(height-8)+'" stroke="#e0e8e6"/><text x="'+xx+'" y="31" text-anchor="middle" font-size="9" fill="#526c78">'+esc(peso(v))+'</text>'});
 series.forEach(([program,items],i)=>{
  const y=48+i*rowH+rowH/2,vs=items.map(r=>Number(r.allocationPerStatedMeter)).sort((a,b)=>a-b),quant=p=>vs[Math.floor((vs.length-1)*p)],q1=quant(.25),med=quant(.5),q3=quant(.75),fenceLo=q1-1.5*(q3-q1),fenceHi=q3+1.5*(q3-q1),inside=vs.filter(v=>v>=fenceLo&&v<=fenceHi),wlo=inside.length?inside[0]:vs[0],whi=inside.length?inside[inside.length-1]:vs[vs.length-1];
  body+='<text x="8" y="'+(y+4)+'" font-size="10" fill="#183643"><title>'+esc(program)+'</title>'+esc(program.length>43?program.slice(0,40)+'…':program)+'</text><text x="270" y="'+(y+4)+'" text-anchor="end" font-size="9" fill="#526c78">n='+items.length+'</text><line x1="'+x(wlo)+'" y1="'+y+'" x2="'+x(whi)+'" y2="'+y+'" stroke="#5f7881" stroke-width="2"/><line x1="'+x(wlo)+'" y1="'+(y-5)+'" x2="'+x(wlo)+'" y2="'+(y+5)+'" stroke="#5f7881"/><line x1="'+x(whi)+'" y1="'+(y-5)+'" x2="'+x(whi)+'" y2="'+(y+5)+'" stroke="#5f7881"/><rect x="'+x(q1)+'" y="'+(y-8)+'" width="'+Math.max(2,x(q3)-x(q1))+'" height="16" fill="#cfe8e2" stroke="#087e78"/><line x1="'+x(med)+'" y1="'+(y-9)+'" x2="'+x(med)+'" y2="'+(y+9)+'" stroke="#183643" stroke-width="2"/>';
  items.forEach((r,j)=>{const v=Number(r.allocationPerStatedMeter),outlier=v<fenceLo||v>fenceHi,cy=y+((j%5)-2)*2.4,color=outlier?'#c34b33':r.highRateCandidate?'#b65b09':'#087e78';body+='<circle cx="'+x(v)+'" cy="'+cy+'" r="3.1" fill="'+color+'"><title>'+esc(r.projectName)+' · '+peso(v)+'/meter · '+(outlier?'outside 1.5×IQR':r.highRateCandidate?'high-rate review candidate':'within 1.5×IQR')+' · '+esc(r.sourceLabel||'')+'</title></circle>'});
 });
 return '<p>Rows without usable length or with segments under 10m remain visible in the table but are not plotted. Red dots mark 1.5×IQR outliers; orange dots mark high-rate review candidates. Every plotted value, including outliers, is shown.</p><svg viewBox="0 0 1040 '+height+'" role="img" aria-label="Grouped box plots of allocation per stated meter by official program, with all project values shown"><title>'+esc(c.title)+'</title>'+body+'</svg>';
}
'''

if __name__=='__main__':
    print(json.dumps(build()['summary'],indent=2))
