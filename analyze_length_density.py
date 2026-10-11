#!/usr/bin/env python3
"""Exploratory length-band comparisons and within-program allocation change points."""
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict, Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'analysis_output'
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
MAX_CANDIDATES=31
MIN_PROGRAM=80
MIN_SIDE=20


def fit(rows,knot=None):
    x=[math.log(r['lengthMeters']) for r in rows]
    y=[math.log(r['amountPesos']) for r in rows]
    n=len(x);xm=statistics.mean(x);ym=statistics.mean(y)
    xx=sum((v-xm)**2 for v in x);xy=sum((a-xm)*(b-ym) for a,b in zip(x,y))
    if xx<=1e-12:return None
    b=xy/xx;hcoef=0;hm=0
    if knot is not None:
        h=[max(0,v-math.log(knot)) for v in x];hm=statistics.mean(h)
        hh=sum((v-hm)**2 for v in h);xh=sum((a-xm)*(v-hm) for a,v in zip(x,h));hy=sum((a-hm)*(b-ym) for a,b in zip(h,y))
        det=xx*hh-xh*xh
        if det<=1e-12:return None
        b=(xy*hh-hy*xh)/det;hcoef=(hy*xx-xy*xh)/det
    else:h=[0]*n
    intercept=ym-b*xm-hcoef*hm
    rss=sum((actual-intercept-b*length-hcoef*hinge)**2 for actual,length,hinge in zip(y,x,h))
    # Search over a breakpoint is counted as an additional fitted parameter.
    bic=n*math.log(max(rss/n,1e-12))+(4 if knot is not None else 2)*math.log(n)
    return {'bic':bic,'slopeBelow':b,'slopeAbove':b+hcoef,'intercept':intercept,'rss':rss}


def candidate_boundaries(rows):
    counts=Counter(r['lengthMeters'] for r in rows)
    values=sorted(counts);cumulative=0;candidates=[]
    for a,b in zip(values,values[1:]):
        cumulative+=counts[a]
        if cumulative>=MIN_SIDE and len(rows)-cumulative>=MIN_SIDE:
            candidates.append(math.sqrt(a*b))
    if len(candidates)>MAX_CANDIDATES:
        candidates=[candidates[round(i*(len(candidates)-1)/(MAX_CANDIDATES-1))] for i in range(MAX_CANDIDATES)]
    return candidates


def band_edges(rows):
    values=sorted(r['lengthMeters'] for r in rows)
    bins=max(1,min(8,len(rows)//20))
    edges=[0]
    for i in range(1,bins):
        index=round(i*len(values)/bins)
        if 0<index<len(values) and values[index-1]!=values[index]:
            edges.append((values[index-1]+values[index])/2)
    return sorted(set(edges))+[float('inf')]


def best_knot(rows,knots=None):
    fitted=[]
    for knot in candidate_boundaries(rows) if knots is None else knots:
        below=sum(r['lengthMeters']<knot for r in rows)
        if below<MIN_SIDE or len(rows)-below<MIN_SIDE:continue
        result=fit(rows,knot)
        if result:fitted.append((result['bic'],knot,result))
    return min(fitted,key=lambda r:(r[0],r[1])) if fitted else None


def build(data=None):
    if data is None:data=json.loads((OUT/'cost_per_km.json').read_text())
    groups=defaultdict(list)
    for r in data['projects']:
        if r['allocationPerStatedMeter'] is not None and r['amountPesos']>0:groups[(r['category'],r['program'])].append(r)
    bands=[];changes=[];models=[]
    for (category,program),rows in sorted(groups.items()):
        program_bands=[]
        edges=band_edges(rows)
        for low,high in zip(edges,edges[1:]):
            bucket=[r for r in rows if low<=r['lengthMeters']<high]
            if not bucket:continue
            record={'category':category,'program':program,'band':f'{low:g}–<{high:g} m' if math.isfinite(high) else f'≥{low:g} m',
                    'minimumMeters':low,'maximumMetersExclusive':high if math.isfinite(high) else None,
                    'records':len(bucket),'medianLengthMeters':statistics.median(r['lengthMeters'] for r in bucket),
                    'medianAllocationPesos':statistics.median(r['amountPesos'] for r in bucket),
                    'medianPesosPerMeter':statistics.median(r['allocationPerStatedMeter'] for r in bucket),
                    'sparse':len(bucket)<20}
            bands.append(record);program_bands.append(record)
        for a,b in zip(program_bands,program_bands[1:]):
            # Compare consecutive populated bands, only with adequate support.
            if a['records']<20 or b['records']<20:continue
            ratio=a['medianPesosPerMeter']/b['medianPesosPerMeter']
            if ratio>=2 or ratio<=.5:
                changes.append({'category':category,'program':program,'shorterBand':a['band'],'longerBand':b['band'],
                                'shorterCount':a['records'],'longerCount':b['records'],
                                'shorterMedianPesosPerMeter':a['medianPesosPerMeter'],'longerMedianPesosPerMeter':b['medianPesosPerMeter'],
                                'shorterToLongerDensityRatio':ratio,'lengthBandMethod':'Within-program approximate quantile groups',
                                'shorterToLongerAllocationRatio':a['medianAllocationPesos']/b['medianAllocationPesos'],
                                'shorterToLongerMedianLengthRatio':a['medianLengthMeters']/b['medianLengthMeters'],
                                'lowerEdgeOfLongerBandMeters':b['minimumMeters']})
        model_rows=[r for r in rows if r['lengthMeters']>=10]
        if len(model_rows)<MIN_PROGRAM:
            models.append({'category':category,'program':program,'records':len(model_rows),'status':'Insufficient observations for breakpoint search'});continue
        knots=candidate_boundaries(model_rows)
        baseline=fit(model_rows);best=best_knot(model_rows,knots)
        if baseline is None or best is None:
            models.append({'category':category,'program':program,'records':len(model_rows),'status':'Insufficient length variation or observations on both sides'});continue
        _,knot,model=best;gain=baseline['bic']-model['bic']
        rng=random.Random(20271011);votes=Counter()
        for _ in range(100):
            sample=[rng.choice(model_rows) for i in model_rows];selected=best_knot(sample,knots)
            if selected:votes[selected[1]]+=1
        boot_values=sorted(value for value,count in votes.items() for _ in range(count))
        boot_low=boot_values[round(.1*(len(boot_values)-1))] if boot_values else None
        boot_high=boot_values[round(.9*(len(boot_values)-1))] if boot_values else None
        sensitivity=[r for r in model_rows if r['lengthMeters']>=25];sensitive=best_knot(sensitivity) if len(sensitivity)>=MIN_PROGRAM else None
        sensitivity_baseline=fit(sensitivity) if sensitive else None
        models.append({'category':category,'program':program,'records':len(model_rows),
                       'excludedBelow10m':len(rows)-len(model_rows),'candidateBoundaryMeters':knot,'searchedBoundariesMeters':knots,'bicImprovement':gain,
                       'status':'Exploratory slope change supported' if gain>=6 else 'No supported slope change',
                       'allocationSlopeBelow':model['slopeBelow'],'allocationSlopeAbove':model['slopeAbove'],
                       'impliedDensitySlopeBelow':model['slopeBelow']-1,'impliedDensitySlopeAbove':model['slopeAbove']-1,
                       'bootstrapWinningBoundaryShare':votes[knot]/100,'bootstrapVotes':dict(votes),
                       'bootstrapBoundary10thPercentile':boot_low,'bootstrapBoundary90thPercentile':boot_high,
                       'sensitivityMinimum25mBoundary':sensitive[1] if sensitive else None,
                       'sensitivityMinimum25mBicImprovement':sensitivity_baseline['bic']-sensitive[2]['bic'] if sensitive and sensitivity_baseline else None})
    changes.sort(key=lambda r:-abs(math.log(r['shorterToLongerDensityRatio'])))
    result={'sourceCostDataSha256':hashlib.sha256((OUT/'cost_per_km.json').read_bytes()).hexdigest(),'bands':bands,'densityChanges':changes,'models':models,
            'method':{'bands':'Within-PAP approximately equal-count length bands, up to eight, targeting at least 20 observations per band; duplicate observed lengths are never split.',
                      'changeRule':'At least 20 observations in each consecutive populated band of the same category and official PAP; median density differs by at least 2×. A descriptive screen, not a significance test.',
                      'breakpointModel':'Within one PAP: continuous piecewise log(allocation)=intercept+slope*log(length)+hinge at a data-derived candidate boundary. Compare against single-slope log allocation model with BIC.',
                      'candidateBoundaries':'Geometric midpoints between adjacent observed distinct lengths with at least 20 records per side; at most 31 candidates spaced across eligible distinct-length boundaries.','minimumModelRecords':80,'minimumRecordsEachSide':20,
                      'minimumModelLengthMeters':10,'bicImprovementScreen':6,'bootstrapRepetitions':100,'bootstrapSeed':20271011,
                      'limits':['Density=allocation/length; declining density can follow mechanically from a fixed budget.',
                                'Quantile-band counts and 2×/BIC screens are editorial exploratory choices, not calibrated corruption thresholds.',
                                'Models use total allocation rather than density to reduce the arithmetic-denominator trap.',
                                'Bootstrap votes measure selection stability in this sample, not the probability of a real engineering threshold.',
                                'Dependence between allocation occurrences, unknown width/terrain/structures and non-random missing lengths remain uncontrolled.',
                                'Sub-10m rows stay visible in bands but are excluded from model fits; ≥25m sensitivity is reported.',
                                'Multiple exploratory program/boundary searches are not confirmatory significance tests; no p-values or multiplicity-adjusted claims are made.',
                                'Sparse bridge/FMR data cannot establish an engineering threshold. No pooled cross-category rate model.']}}
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    (OUT/'length_density_groups.json').write_text(text);(STATIC/'length-density-groups.json').write_text(text)
    return result


def metric_graph(records,key,label):
    from html import escape
    chosen=sorted(records,key=lambda r:abs(r[key]),reverse=True)[:12]
    if not chosen:return '<p>No adequately supported comparisons to plot.</p>'
    maximum=max(abs(r[key]) for r in chosen) or 1
    body=f'<figure><figcaption>{escape(label)} · up to 12 largest magnitudes</figcaption><svg class="evidence-graphic" viewBox="0 0 1100 400" role="img" aria-label="{escape(label)}">'
    for i,r in enumerate(chosen):
        y=24+i*29;title=r['program'];value=r[key]
        body+=f'<text x="5" y="{y+12}" font-size="11">{escape(title[:62])}<title>{escape(title)}</title></text><rect x="425" y="{y}" height="17" width="{530*abs(value)/maximum}" fill="'+('#087e78' if value>=0 else '#b65b09')+f'"><title>{escape(title)}: {value:.2f}</title></rect><text x="970" y="{y+12}" font-size="12">{value:.2f}</text>'
    return body+'</svg></figure>'


def band_graph(rows):
    from html import escape
    groups=defaultdict(list)
    for r in rows:groups[r['program']].append(r)
    selected=sorted(groups,key=lambda p:-sum(r['records'] for r in groups[p]))[:5]
    points=[r for p in selected for r in groups[p] if r['medianLengthMeters']>0 and r['medianPesosPerMeter']>0]
    if not points:return '<p>No band medians to plot.</p>'
    xs=[math.log10(r['medianLengthMeters']) for r in points];ys=[math.log10(r['medianPesosPerMeter']) for r in points]
    xmin,xmax=min(xs),max(xs);ymin,ymax=min(ys),max(ys)
    colors=['#087e78','#b65b09','#355b92','#9b4483','#586424']
    svg='<figure><figcaption>Median allocation density vs median length · separate curves for up to five programs with most observations; both axes logarithmic</figcaption><svg class="evidence-graphic" viewBox="0 0 1100 510" role="img" aria-label="Within-program length band medians"><path d="M90 35 V300 H1010" fill="none" stroke="#526773"/>'
    svg+=f'<text x="90" y="325">{10**xmin:,.1f} m</text><text x="870" y="325">{10**xmax:,.1f} m</text><text x="3" y="45">₱{10**ymax:,.0f}/m</text><text x="3" y="300">₱{10**ymin:,.0f}/m</text>'
    for i,p in enumerate(selected):
        ordered=sorted(groups[p],key=lambda r:r['medianLengthMeters']);coords=[]
        for r in ordered:
            x=90+900*(math.log10(r['medianLengthMeters'])-xmin)/max(xmax-xmin,.01)
            y=300-260*(math.log10(r['medianPesosPerMeter'])-ymin)/max(ymax-ymin,.01)
            coords.append(f'{x:.1f},{y:.1f}')
            svg+=f'<circle cx="{x}" cy="{y}" r="4" fill="{colors[i]}"><title>{escape(p)} · {r["records"]} rows · {r["medianLengthMeters"]:.1f} m · ₱{r["medianPesosPerMeter"]:,.2f}/m</title></circle>'
        svg+=f'<polyline points="'+ ' '.join(coords)+f'" fill="none" stroke="{colors[i]}" stroke-width="2"/><text x="90" y="{365+i*25}" font-size="11" fill="{colors[i]}">{escape(p[:135])}</text>'
    return svg+'</svg></figure>'


def render(data):
    from build_investigation_summary import table,esc
    import html
    body='<section id="length-density-groups" class="card"><h2>At what stated lengths does allocation density change?</h2><p>Length bands are compared within the same category and official work program. Allocation density is pesos per stated meter. A shorter denominator can raise this ratio without an unusually large allocation, so the tables also show total allocation and a separate model of allocation versus length.</p><p class="caution">These are exploratory grouping boundaries, not engineering price standards or evidence of overpricing. Sparse samples, missing lengths and unmeasured project scope limit interpretation.</p>'
    supported=[r for r in data['models'] if r['status']=='Exploratory slope change supported']
    model_rows=[[r['category'],r['program'],r['records'],round(r['candidateBoundaryMeters'],2) if 'candidateBoundaryMeters' in r else '',round(r.get('bicImprovement',0),2) if 'bicImprovement' in r else '',r['status'],(f"{r['bootstrapBoundary10thPercentile']:.1f}–{r['bootstrapBoundary90thPercentile']:.1f}" if r.get('bootstrapBoundary10thPercentile') is not None else ''),round(r.get('bootstrapWinningBoundaryShare',0)*100,1) if 'bootstrapWinningBoundaryShare' in r else '',round(r['sensitivityMinimum25mBoundary'],2) if r.get('sensitivityMinimum25mBoundary') is not None else ''] for r in data['models']]
    changes=[[r['category'],r['program'],r['shorterBand'],r['longerBand'],r['shorterCount'],r['longerCount'],r['shorterMedianPesosPerMeter'],r['longerMedianPesosPerMeter'],round(r['shorterToLongerDensityRatio'],2),round(r['shorterToLongerAllocationRatio'],2)] for r in data['densityChanges']]
    body+='<h3>Where median density changes by at least 2×</h3><p>Only comparisons with at least 20 rows in each band are included. A ratio above 1 means the shorter-length band has higher allocation per meter. Bands with fewer observations remain in the complete band tables below.</p>'+metric_graph(data['densityChanges'],'shorterToLongerDensityRatio','Density ratio · shorter band / longer band')+table(['Category','Official program','Shorter band','Longer band','Shorter rows','Longer rows','Shorter median pesos/meter','Longer median pesos/meter','Density ratio · shorter / longer','Allocation ratio · shorter / longer'],changes)
    body+='<h3>Does total allocation show a length boundary too?</h3><p>The segmented model fits log total allocation against log stated length within each PAP. It needs 80 records and 20 per side, excludes lengths below 10 meters, and requires BIC improvement ≥6 over a single slope. The boundary is selected from observed-length candidates, not a fixed 100-meter threshold; bootstrap frequency describes how consistently it is selected. The 10th–90th percentile of bootstrap-selected boundaries describes an empirical stability window, not a confidence interval. The ≥25-meter sensitivity boundary is also shown.</p>'+metric_graph([r for r in data['models'] if 'bicImprovement' in r],'bicImprovement','Model BIC improvement · positive favors a slope change')+table(['Category','Official program','Model rows','Candidate boundary meters','BIC improvement','Model conclusion','Bootstrap 10th–90th boundary meters','Bootstrap same-boundary %','Sensitivity ≥25m boundary meters'],model_rows)
    body+='<h3>Complete length bands · separate categories and programs</h3><p>These descriptive medians remain separate by PAP. FMR and bridge samples may be too sparse for breakpoint inference.</p>'
    for category in ['Roads','Bridges','FMR']:
        rows=[r for r in data['bands'] if r['category']==category]
        body+=f'<details open><summary>{esc(category)} · full band statistics</summary>'+band_graph(rows)+table(['Official program','Length band','Rows','Median meters','Median allocation pesos','Median pesos/meter','Sample below 20 rows'],[[r['program'],r['band'],r['records'],r['medianLengthMeters'],r['medianAllocationPesos'],r['medianPesosPerMeter'],'Yes' if r['sparse'] else 'No'] for r in rows])+'</details>'
    body+='<h3>Method and limitations</h3><p>Length bands are derived separately within each PAP using approximately equal-count groups (up to eight, targeting at least 20 records per group). Equal observed lengths stay together. Breakpoint candidates are geometric midpoints between adjacent observed distinct lengths, requiring at least 20 records on either side; up to 31 candidates cover the eligible boundaries. No 100-meter boundary is prescribed. The searched boundary counts as an extra model parameter in BIC.</p><ul>'+''.join('<li>'+esc(v)+'</li>' for v in data['method']['limits'])+'</ul><p><a href="length-density-groups.json" download>Download all groups, model slopes, bootstrap votes and methodology</a>. Patterns direct source and engineering review; there is no universal safe or suspicious length.</p></section>'
    return body.replace('class="export-btn"','class="export export-btn"')

if __name__=='__main__':
    d=build();print(json.dumps({'changes':len(d['densityChanges']),'supported':[r for r in d['models'] if r['status']=='Exploratory slope change supported']},indent=2))
