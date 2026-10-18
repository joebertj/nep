#!/usr/bin/env python3
"""Compare local enacted DPWH FY2026 with HGAB FY2027 stated-meter proxies."""
import hashlib
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path
from analyze_priority_repeats import query
from build_cost_per_km import category, lengths, OUT, STATIC, ROOT
from hgab_matching import normalize

SOURCE=ROOT.parent/'open-data-visualization/data/parquet/parsed_dpwh_2026.parquet'

def build(current=None):
    current=current or json.loads((OUT/'cost_per_km.json').read_text())
    programs={normalize(r['program']):r['program'] for r in current['projects'] if r['category']!='FMR'}
    raw=query(f"SELECT _excel_row, {','.join('col_'+c for c in 'CDEFGHIJ')}, amount FROM read_parquet('{SOURCE}') ORDER BY _excel_row")
    ancestors={};old=[]
    for r in raw:
        for c in 'CDEFGHI':
            v=(r['col_'+c] or '').strip()
            if not v or re.fullmatch(r'[0-9]+',v):continue
            if re.fullmatch(r'[a-z]\.',v):continue
            ancestors={k:x for k,x in ancestors.items() if k<c};ancestors[c]=v
        title=(r['col_J'] or '').strip()
        if not title or not r['amount'] or r['amount']<=0:continue
        context=' | '.join(ancestors.values())
        if ancestors.get('C')!='OPERATIONS' or re.search(r'foreign.assisted|JICA|loan no\.',context+' | '+title,re.I):continue
        candidates=[programs[normalize(v)] for v in ancestors.values() if normalize(v) in programs]
        pap=candidates[-1] if candidates else 'Unmatched FY2026 program context'
        group=category({'projectName':title,'pap3':pap})
        if not group:continue
        km,status,method,_=lengths(title)
        old.append({'id':f'GAA2026-excel-{r["_excel_row"]}','category':group,'program':pap,'projectName':title,
                    'amountPesos':r['amount'],'lengthMeters':round(km*1000,6) if km else None,
                    'rate':r['amount']/(km*1000) if km and group!='Mixed roads / bridges' else None,
                    'lengthStatus':status,'lengthMethod':method,'sourceExcelRow':r['_excel_row'],'hierarchy':ancestors.copy()})
    new=[{**r,'rate':r['allocationPerStatedMeter']} for r in current['projects'] if r['category']!='FMR']
    summaries=[];comparisons=[];cells=[]
    for cat in ['Roads','Bridges','Mixed roads / bridges']:
        for stage,records in [('FY2026 GAA',old),('FY2027 HGAB 3rd',new)]:
            allrows=[r for r in records if r['category']==cat];usable=[r for r in allrows if r['rate'] is not None and r['lengthMeters']>=10]
            summaries.append({'category':cat,'stage':stage,'selectedOccurrences':len(allrows),'withLength':sum(r['lengthMeters'] is not None for r in allrows),'rateRecordsAtLeast10m':len(usable),'medianRate':statistics.median(r['rate'] for r in usable) if usable else None})
        for pap in sorted({r['program'] for r in new if r['category']==cat}):
            a=[r for r in old if r['category']==cat and r['program']==pap and r['rate'] is not None and r['lengthMeters']>=10]
            b=[r for r in new if r['category']==cat and r['program']==pap and r['rate'] is not None and r['lengthMeters']>=10]
            if len(a)<20 or len(b)<20:continue
            ma=statistics.median(r['rate'] for r in a);mb=statistics.median(r['rate'] for r in b)
            # FY2026-derived quartiles; identical boundaries applied to both stages.
            cuts=sorted(set(statistics.quantiles([r['lengthMeters'] for r in a],n=4,method='inclusive')))
            bounds=[10]+[v for v in cuts if v>10]+[float('inf')]
            supported=[]
            for low,high in zip(bounds,bounds[1:]):
                aa=[r['rate'] for r in a if low<=r['lengthMeters']<high];bb=[r['rate'] for r in b if low<=r['lengthMeters']<high]
                if len(aa)<20 or len(bb)<20:continue
                am=statistics.median(aa);bm=statistics.median(bb)
                cell={'category':cat,'program':pap,'lowerMeters':low,'upperMetersExclusive':None if high==float('inf') else high,'gaaRecords':len(aa),'hgabRecords':len(bb),'gaaMedian':am,'hgabMedian':bm,'ratio':bm/am}
                cells.append(cell);supported.append(cell)
            weight=sum(c['gaaRecords'] for c in supported)
            comparisons.append({'category':cat,'program':pap,'gaaRecords':len(a),'hgabRecords':len(b),'gaaMedian':ma,'hgabMedian':mb,'unadjustedChangePct':100*(mb/ma-1),'lengthAdjustedChangePct':100*(sum(c['ratio']*c['gaaRecords'] for c in supported)/weight-1) if weight else None,'supportedLengthBands':len(supported),'supportedGaaRecords':weight,'supportedHgabRecords':sum(c['hgabRecords'] for c in supported)})
    comparisons.sort(key=lambda r:-(r['lengthAdjustedChangePct'] if r['lengthAdjustedChangePct'] is not None else -1e9))
    data={'stages':['FY2026 enacted GAA','FY2027 HGAB 3rd reading proposal'],'coverage':summaries,'programComparisons':comparisons,'lengthBandComparisons':cells,'gaaProjects':old,
          'method':'Same length parser as current page; positive domestic DPWH OPERATIONS col_J occurrences only from local parsed FY2026 schedule. Peso amounts already in pesos. Official PAP joins use case/punctuation normalization only; unmatched programs excluded from peer comparisons. Lengths below 10m withheld from rate comparisons. Program medians need at least 20 usable records per stage. Length adjustment uses FY2026 length quartiles, at least 20 records per stage per band, and a FY2026-count-weighted mean of band median ratios. Unsupported bands are excluded, never extrapolated.',
          'limits':['Different projects and stage scope; not paired contracts or measured construction cost inflation.','Surface, recorded condition, width, lanes, terrain, structures, geography and funded quantities remain uncontrolled in this cross-year table. Current-page surface/condition screening does not turn this into a matched-context historical comparison. Rates are whole allocation/stated meters.','FY2026 column-J leaf scope can omit records at other hierarchy depths; selected coverage is not the complete DPWH budget. Missing metadata can bias comparisons.','FMR is not compared here: this historical comparison reads the DPWH schedule only.','Medians resist extreme-rate influence; no extreme individual rate dots or bars shown. No formal significance or causal claim.'],
          'sources':[{'file':str(SOURCE.relative_to(ROOT.parent)),'sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest()},{'file':'cost_per_km.json','sha256':hashlib.sha256((OUT/'cost_per_km.json').read_bytes()).hexdigest()}]}
    text=json.dumps(data,ensure_ascii=False,indent=2)+'\n';(OUT/'meter_rates_2026_comparison.json').write_text(text);(STATIC/'meter-rates-2026-comparison.json').write_text(text)
    return data

def render(data):
    from build_investigation_summary import table,esc
    rows=data['programComparisons'];shown=[r for r in rows if r['lengthAdjustedChangePct'] is not None][:8]
    body='<section id="gaa-2026-meter-comparison" class="card"><h2>Are stated-meter allocations higher than FY2026 GAA?</h2><p>Compare the same official work program first, then comparable stated-length groups. FY2026 is enacted GAA; FY2027 is the HGAB 3rd-reading proposal. These are allocations per stated meter, not verified construction prices or a finding of overpricing.</p>'
    if shown:
        maxrate=max(max(r['gaaMedian'],r['hgabMedian']) for r in shown)
        svg='<svg viewBox="0 0 1100 360" role="img" aria-label="Median allocation per stated meter by official program in FY2026 GAA and FY2027 HGAB"><text x="25" y="20">Teal: FY2026 GAA · Orange: FY2027 HGAB · medians, not individual extremes</text>'
        for i,r in enumerate(shown):
            x=35+i*130
            for offset,key,color in [(0,'gaaMedian','#087e78'),(38,'hgabMedian','#b65b09')]:
                h=220*r[key]/maxrate
                svg+=f'<rect x="{x+offset}" y="{260-h}" width="30" height="{h}" fill="{color}"><title>{esc(r["program"])}: ₱{r[key]:,.0f}/meter</title></rect><text x="{x+offset}" y="{253-h}" font-size="10">{r[key]/1000:.1f}k</text>'
            svg+=f'<text x="{x}" y="285">Program {i+1}</text>'
        body+='<figure><figcaption>Program medians · pesos per stated meter. Length-adjusted changes are in the table.</figcaption>'+svg+'</svg></figure>'
    body+=table(['Official program · graph number','Category','Usable records · 2026 / 2027','2026 median pesos/meter','2027 median pesos/meter','Unadjusted change (%)','Length-adjusted change (%)'],[[r['program']+' · '+str(next((i+1 for i,x in enumerate(shown) if x is r),'not graphed')),r['category'],f'{r["gaaRecords"]} / {r["hgabRecords"]}',round(r['gaaMedian'],2),round(r['hgabMedian'],2),round(r['unadjustedChangePct'],1),round(r['lengthAdjustedChangePct'],1) if r['lengthAdjustedChangePct'] is not None else 'Insufficient comparable length bands'] for r in rows])
    body+='<h3>Coverage and exclusions</h3>'+table(['Category','Budget stage','Selected line items','With stated lengths','Rate records ≥10 meters','Median pesos/meter · project mix uncontrolled'],[[r['category'],r['stage'],r['selectedOccurrences'],r['withLength'],r['rateRecordsAtLeast10m'],round(r['medianRate'],2) if r['medianRate'] is not None else 'Not comparable'] for r in data['coverage']])
    body+='<h3>Method and limits</h3><p>'+esc(data['method'])+'</p><ul>'+''.join('<li>'+esc(v)+'</li>' for v in data['limits'])+'</ul><p><a href="meter-rates-2026-comparison.json" download>Download all FY2026 records, band calculations and input hashes</a></p></section>'
    bands=table(['Category','Official program','Length group · meters','2026 / 2027 records','2026 median pesos/meter','2027 median pesos/meter','Rate change (%)'],[[r['category'],r['program'],f'{r["lowerMeters"]:g}–<{r["upperMetersExclusive"]:g}' if r['upperMetersExclusive'] is not None else f'≥{r["lowerMeters"]:g}',f'{r["gaaRecords"]} / {r["hgabRecords"]}',round(r['gaaMedian'],2),round(r['hgabMedian'],2),round(100*(r['ratio']-1),1)] for r in data['lengthBandComparisons']])
    body=body.replace('</section>','<h3>Supporting length-group calculations</h3><p>The adjusted percentage is the mean of the group rate ratios, weighted by the FY2026 record count. Only the groups shown qualify; omitted groups do not count toward the result.</p>'+bands+'</section>')
    return body

if __name__=='__main__':
    d=build();print(json.dumps({'coverage':d['coverage'],'programComparisons':d['programComparisons']},indent=2))
