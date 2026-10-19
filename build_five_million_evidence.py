#!/usr/bin/env python3
"""Restore exact-PHP5M office clustering at its summary-linked evidence anchor."""
import csv,html,io,json,math,re
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent;STATIC=ROOT.parent/'open-data-visualization/static/nep-preview';OUT=ROOT/'analysis_output'
ID='dpwh-investigation-evidence'
def esc(v):return html.escape(str(v),quote=True)
def table(headers,rows):
    output=io.StringIO();writer=csv.writer(output);writer.writerow(headers);writer.writerows(rows)
    return '<button class="export-btn" data-csv="'+esc(output.getvalue())+'">Export CSV</button><div class="evidence-table"><table><thead><tr>'+''.join('<th>'+esc(v)+'</th>' for v in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def render():
    from compute_five_million_stats import ROAD,FLOOD
    data=json.loads((STATIC/'dpwh-data.json').read_text());test=data['fiveMillionStats']['results'][0];year=int(test['fiscal_year']);groups=defaultdict(lambda:{'road':0,'flood':0})
    for row in data['fiveMillionRows']:
        if int(row['fiscal_year'])!=year:continue
        if float(row['amount'])!=5_000_000:raise ValueError('Unexpected amount in exact-PHP5M input')
        kind='road' if row['category']==ROAD else 'flood' if row['category'] in FLOOD else None
        if kind:groups[(row['office'],row['region'])][kind]+=1
    road=sum(v['road']>0 for v in groups.values());flood=sum(v['flood']>0 for v in groups.values());both=[(office,region,v) for (office,region),v in groups.items() if v['road'] and v['flood']]
    if (road,flood,len(both))!=(test['road_offices'],test['flood_offices'],test['overlap_offices']):raise ValueError('Clustering rows differ from statistical denominator; recompute before publication')
    N=test['district_offices'];a=len(both);b=road-a;c=flood-a;d=N-a-b-c;odds=a*d/(b*c);se=math.sqrt(sum(1/n for n in (a,b,c,d)));lo=math.exp(math.log(odds)-1.96*se);hi=math.exp(math.log(odds)+1.96*se)
    expected=test['independent_expected_overlap'];regional=test['region_controlled_expected_overlap'];values=[('Observed shared offices',a,'#087e78'),('Independent assignment',expected,'#355b92'),('Regional assignment',regional,'#b65b09')];maximum=max(v[1] for v in values)
    svg='<svg class="evidence-graphic" viewBox="0 0 950 300" role="img" aria-label="Observed shared offices versus expected overlap under two assignment models">'
    for i,(label,value,color) in enumerate(values):
        x=100+i*290;h=190*value/maximum
        svg+=f'<rect x="{x}" y="{235-h:.2f}" width="150" height="{h:.2f}" fill="{color}"><title>{esc(label)}: {value:.2f}</title></rect><text x="{x}" y="{223-h:.2f}">{value:.2f} offices</text><text x="{x-25}" y="270">{esc(label)}</text>'
    svg+='</svg>'
    body=f'<section id="{ID}" class="investigation-evidence"><h2>Exact ₱5M road and flood allocations cluster in the same offices</h2><p><strong>{a} offices have both categories, compared with {expected:.1f} expected under independent assignment.</strong> FY{year} NEP: {road} of {N} DEOs have exact ₱5M access-road/bridge entries and {flood} have exact ₱5M flood entries. This is office-level co-occurrence, not evidence of repeated projects or overpriced work.</p>'+svg
    body+='<h3>Exploratory statistical evidence</h3>'+table(['Statistic','Result'],[
        ['Budget stage',f'FY{year} NEP; not HGAB'],['District Engineering Offices in denominator',N],['Offices with both exact ₱5M categories',a],['Expected overlap · independent assignment',f'{expected:.2f} offices'],['One-sided hypergeometric p-value',f'{test["hypergeometric_p_value"]:.6g}'],['Office odds ratio · approximate 95% interval',f'{odds:.2f} · {lo:.2f}–{hi:.2f}'],['Expected overlap · region-controlled assignment',f'{regional:.2f} offices'],['Region-controlled simulated p-value',f'{test["region_controlled_simulated_p_value"]:.6g}'],['Region-controlled randomizations',f'{test["simulation_repetitions"]:,}']])
    body+='<h3>District offices with exact ₱5M entries in both categories</h3><p>Counts are budget entries, not independently verified distinct projects. The listed amount counts each included entry once; it is not a loss estimate. All offices satisfying the same rule are included.</p>'
    rows=[]
    for office,region,v in sorted(both,key=lambda r:(-(r[2]['road']+r[2]['flood']),r[0])):
        rows.append([year,office,region,v['road'],v['flood'],f'₱{5_000_000*(v["road"]+v["flood"]):,}'])
    body+=table(['NEP year','District Engineering Office','Region','Road / bridge entries','Flood entries','Combined listed amount'],rows)
    from render_allocation_amount_patterns import render as amount_patterns
    body+=amount_patterns(data)
    body+='<h3>Methodology and limits</h3><p>The road category is BIP access roads/bridges leading to major or strategic public buildings/facilities. Flood categories are construction/maintenance of flood-mitigation structures and drainage systems, and construction/rehabilitation of flood-mitigation facilities within major river basins and principal rivers. Exact ₱5M means a printed allocation of ₱5,000,000, with no rounding band.</p><p>The hypergeometric test fixes the number of road and flood offices among the year’s DEOs, then evaluates the probability of at least the observed overlap under independent assignment. The regional permutation test keeps road-office membership fixed and reshuffles flood membership within regions, preserving regional flood-office counts. The odds-ratio interval is an approximate log-Wald interval.</p><p class="caution">The amount threshold and categories were selected after noticing the pattern. These exploratory p-values and confidence intervals are unadjusted for that selection or multiple comparisons. Office workload, project mix, engineering need and standard designs can explain clustering. Small p-values reject the stated assignment model; they do not establish coordination, procurement splitting, overpricing or intent.</p><p>Next steps: pre-specify controls for work type, office workload and historical prices, then inspect quantities and engineering specifications. Group-level clustering is not a finding about any representative or signatory.</p><p><a href="dpwh-data.json" download>Source rows and statistical methods · JSON</a> · CSV buttons export every row of their table, including pages not currently shown.</p></section>'
    return body

def apply():
    from report_table_presentation import apply_page,publish_assets
    path=STATIC/'repeats.html';text=path.read_text();block=render()
    pattern=rf'<section\b[^>]*id="{ID}"[^>]*>.*?</section>'
    old=re.search(pattern,text,re.S)
    if old and 'Exact ₱5M road and flood allocations cluster in the same offices' not in old[0]:
        # Preserve the independent repeat-denominator evidence under its own ID.
        renamed=old[0].replace(f'id="{ID}"','id="repeat-denominator-evidence"',1).replace('Repeat denominators and allocation clustering','Repeat denominators',1)
        text=text[:old.start()]+renamed+block+text[old.end():]
    elif old:text=text[:old.start()]+block+text[old.end():]
    else:text=text.replace('</main>',block+'</main>',1)
    text=apply_page(text,publish_assets());path.write_text(text);(OUT/'repeats.html').write_text(text)
    # Keep the stored fragment from reintroducing the clustering ID on denominators.
    cache=OUT/'repeat_page_fragments.json'
    if cache.exists():
        fragments=json.loads(cache.read_text())
        if 'denominators' in fragments:
            fragments['denominators']=fragments['denominators'].replace(f'id="{ID}"','id="repeat-denominator-evidence"',1).replace('Repeat denominators and allocation clustering','Repeat denominators',1)
            cache.write_text(json.dumps(fragments,ensure_ascii=False,indent=2)+'\n')
    return {'anchor':ID,'officeRows':json.loads((STATIC/'dpwh-data.json').read_text())['fiveMillionStats']['results'][0]['overlap_offices'],'stage':'FY2027 NEP','additionalAmountPatterns':True}
if __name__=='__main__':print(json.dumps(apply(),indent=2))
