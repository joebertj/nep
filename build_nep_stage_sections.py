#!/usr/bin/env python3
"""Expose source-checked NEP/HGAB comparisons while retaining separate reading analyses."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OUT=ROOT/'analysis_output';STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'

def apply(data=None):
    from build_investigation_summary import inject,section,table,esc
    from build_nep_agency_baselines import build
    data=data or build();s=data['summary'];rows=data['niaNamedComparisons']
    def signed(v):return ('+' if v>0 else '−' if v<0 else '')+'₱'+f'{abs(v):,}'
    def bars(labels,left,right):
        maximum=max(left+right+[1]);svg='<svg class="evidence-graphic" viewBox="0 0 1050 340" role="img" aria-label="NEP versus HGAB allocations"><text x="20" y="22">Teal: NEP · Orange: HGAB 3rd · billions of pesos</text>'
        for i,(label,a,b) in enumerate(zip(labels,left,right)):
            x=70+i*(900/max(len(labels),1))
            for offset,value,color in [(0,a,'#087e78'),(40,b,'#b65b09')]:
                h=210*value/maximum;svg+=f'<rect x="{x+offset}" y="{255-h}" width="32" height="{h}" fill="{color}"><title>{esc(label)} · ₱{value:,}</title></rect><text x="{x+offset}" y="{250-h}" font-size="11">{value/1e9:.3f}</text>'
            svg+=f'<text x="{x}" y="280" font-size="11">{esc(label)}</text>'
        return svg+'</svg>'
    changed=[r for r in rows if r['adjustmentPesos'] not in (None,0) and r['visibleHgabRowVerified']]
    body='<p>This compares FY2027 NEP named-entry allocations with HGAB 3rd-reading named rows. Earlier House reading comparisons are on the dedicated comparison page. All 32 HGAB named title/amount rows have visible-PDF checks. Blank NEP amounts are not zeros; ambiguous repeated names stay unresolved.</p>'+bars([f'Project {i+1}' for i in range(len(changed))],[r['nepPesos'] for r in changed],[r['hgabPesos'] for r in changed])
    ordered=changed+[r for r in rows if r not in changed]
    body+=table(['Graph project','NIA named project','NEP allocation pesos','HGAB allocation pesos','Allocation adjustment pesos','Comparison evidence','NEP workbook rows','HGAB PDF page'],[[changed.index(r)+1 if r in changed else '—',r['projectName'],r['nepPesos'] if r['nepPesos'] is not None else 'Not established',r['hgabPesos'],signed(r['adjustmentPesos']) if r['adjustmentPesos'] is not None else 'Not established',r['status'],r['workbookRows'] or 'Unresolved',r['sourcePage']] for r in ordered])
    body+=f'<p>{s["niaFundedEntries"]} grouped NIA entries carry positive allocations; {s["niaZeroEntries"]} have explicit zero and {s["niaBlankEntries"]} have blank amounts. These counts include activities and programme envelopes, not only construction projects. Named HGAB rows are a subset of the NIA budget: do not treat their net adjustment as the agency’s total change.</p>'
    body+='<h3>Grouping and source methodology</h3><p>'+esc(data['method'])+'</p><ul>'+''.join('<li>'+esc(x)+'</li>' for x in data['limits'])+'</ul><p><a href="nep-agency-baselines.json" download>Every source component, grouped entry and comparison JSON</a> · <a href="nep-agency-stage-controls.json" download>Visible PDF row/control evidence</a></p>'
    inject('nia.html','nia-nep-stage-comparison',section('nia-nep-stage-comparison','Named NIA allocations · NEP → HGAB 3rd reading',body))
    h=data['hfepStageComparison']
    body='<p>Programme-level comparison: the NEP workbook and printed HGAB programme control both separate MOOE and Capital Outlays. This does not compare individual facilities with a programme envelope. The 513 extracted HGAB facility rows total exactly the printed ₱10.021659B Capital Outlays control.</p>'+bars(['Capital Outlays','MOOE','Programme total'],[h['nepCapitalPesos'],h['nepMooePesos'],h['nepTotalPesos']],[h['hgabCapitalPesos'],h['hgabMooePesos'],h['hgabTotalPesos']])
    body+=table(['Same budget category','NEP allocation pesos','HGAB allocation pesos','Allocation adjustment pesos'],[[label,a,b,signed(b-a)] for label,a,b in [('Capital Outlays',h['nepCapitalPesos'],h['hgabCapitalPesos']),('MOOE',h['nepMooePesos'],h['hgabMooePesos']),('Programme total',h['nepTotalPesos'],h['hgabTotalPesos'])]])
    body+='<h3>Printed control and facility reconciliation</h3>'+table(['Source','PDF page','Printed page','Programme Capital Outlays pesos','Extracted facility total pesos','Reconciliation difference pesos'],[[h['source']['sourceVolume'],h['source']['sourcePage'],h['source']['printedPage'],h['hgabCapitalPesos'],h['hgabCapitalPesos'],0]])
    body+='<p>A programme allocation decrease is not a finding of misconduct or proof that specific facilities were removed. The NEP workbook has programme entries, not a facility-by-facility HFEP annex. Facility insertions/removals remain unestablished without that detailed baseline. Earlier House reading comparisons are on the dedicated comparison page.</p><h3>Workbook grouping methodology</h3><p>'+esc(data['scope'])+'</p><p>Group by agency, PREXC identifier, operating unit and region; sum the object/fund components while retaining every source row. DOH Office of the Secretary only. Source amounts are thousands of pesos, multiplied by 1,000. Confirmed amount controls and source-row provenance are downloadable.</p><p><a href="nep-agency-baselines.json" download>Workbook rows and stage comparisons JSON</a> · <a href="nep-agency-stage-controls.json" download>Printed HFEP control evidence JSON</a></p>'
    inject('hfep.html','hfep-nep-stage-comparison',section('hfep-nep-stage-comparison','HFEP programme allocations · NEP → HGAB 3rd reading',body))
    body='<p>The NEP workbook contains NIA named project and programme-level subsidy entries. The HGAB irrigation appendix contains finer works such as canal components and stated segments. These are different hierarchy levels and cannot establish appendix-level insertions simply through absent exact titles.</p><p><a href="nia.html#nia-nep-stage-comparison">Compare source-checked named NIA allocations against NEP →</a> · <a href="nep-agency-baselines.json" download>Inspect grouped NEP entries and source components</a></p>'
    inject('nia-irrigation.html','nia-nep-scope',section('nia-nep-scope','NEP coverage · named projects versus detailed irrigation works',body))
    for name in ['nia.html','hfep.html']:
        p=STATIC/name;text=p.read_text();identifier='nia-nep-stage-comparison' if name=='nia.html' else 'hfep-nep-stage-comparison'
        text=text.replace('</header>',f'<p><a href="#{identifier}" style="color:#a7ddd1">NEP → HGAB allocation comparison ↓</a></p></header>',1) if f'href="#{identifier}"' not in text else text;p.write_text(text)
    return {'niaChangedRows':len(changed),'hfepCapitalAdjustmentPesos':h['capitalAdjustmentPesos']}
if __name__=='__main__':print(json.dumps(apply(),indent=2))
