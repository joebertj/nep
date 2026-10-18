#!/usr/bin/env python3
"""Render comparisons from the preferred reviewed NIA/HFEP source ledgers."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'data_sources/csiiiv';OUT=ROOT/'analysis_output';STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
def apply():
    policy_path=BASE/'source_policy.json'
    if not policy_path.exists():return
    from build_investigation_summary import inject,section,table,esc
    policy=json.loads(policy_path.read_text());accepted=BASE/'accepted'
    def read(name):return json.loads((accepted/name).read_text())
    def graph(rows):
        maximum=max([v for r in rows for v in [r[1],r[2]]]+[1]);svg='<figure><figcaption>Teal: NEP · orange: HGAB · billions of pesos. Numbered groups correspond to table rows.</figcaption><svg class="evidence-graphic" viewBox="0 0 1100 330" role="img" aria-label="NEP versus HGAB reviewed annex controls">'
        step=960/max(len(rows),1)
        for i,r in enumerate(rows):
            x=60+i*step
            for offset,value,color in [(0,r[1],'#087e78'),(step*.35,r[2],'#b65b09')]:
                height=210*value/maximum
                svg+=f'<rect x="{x+offset:.2f}" y="{245-height:.2f}" width="{step*.3:.2f}" height="{height:.2f}" fill="{color}"><title>{esc(r[0])} · ₱{value:,}</title></rect>'
            svg+=f'<text x="{x}" y="275">{i+1}</text>'
        return svg+'</svg></figure>'
    nia=read('nep_nia_dataset.json');house=read('hgab_nia_tree.json');hfep_nep=read('nep_hfep_data_list.json');hfep_house=read('hgab_hfep_data_list.json')
    controls={r['label']:r['printed_amount_php'] for r in house['nodes'] if r['kind']=='subprogram_control'}
    rows=[]
    for r in nia['sub_programs']:
        label='Extension/Expansion of Existing Irrigation System Sub-Program' if r['sub_program']=='Extension/Expansion' else r['sub_program']+' Sub-Program'
        rows.append([r['sub_program'],r['control_amount'],controls[label],controls[label]-r['control_amount']])
    credits='<p>Preferred extraction: <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/">csiiiv budget-analysis workbench</a> · <a href="'+policy['source']+'/tree/'+policy['commit']+'">pinned source revision</a>. Documented human corrections take priority over the older automated extraction. Raw titles, repair history, unresolved flags and source identifiers are preserved. This does not claim that every row was individually image-reviewed.</p>'
    downloads='<p><a href="reviewed-annex-baselines.json" download>Download accepted NEP/HGAB annex rows and provenance (JSON)</a> · <a href="reviewed-source-adoption.json" download>Source adoption and reading-equivalence record</a></p>'
    nep_total=sum(r['amount_php'] for r in nia['projects']);house_rows=[r for r in house['nodes'] if r['kind']=='project'];house_total=sum(r['printed_amount_php'] for r in house_rows)
    body=credits+f'<p>Compare the same printed irrigation sub-programs: NEP {len(nia["projects"]):,} rows / ₱{nep_total:,}; HGAB {len(house_rows):,} rows / ₱{house_total:,}. Net adjustment: ₱{house_total-nep_total:,}. The old 423-row local extraction missed part of the annex; correcting that extraction is not a legislative insertion. Named major NIA projects are a separate scope.</p>'+graph(rows)+table(['Sub-program','NEP allocation pesos','HGAB allocation pesos','Allocation adjustment pesos'],rows)+'<p>Controls are directly comparable at sub-program level. The difference in project counts does not identify individual insertions or removals. Annex text equivalence between the local House readings is preserved in the adoption record.</p>'+downloads
    inject('nia-irrigation.html','reviewed-nia-controls',section('reviewed-nia-controls','Reviewed irrigation annex · NEP → HGAB 3rd reading',body))
    n=hfep_nep['document']['verification']['summary'];h=hfep_house['document']['verification']['summary']
    rows=[]
    for label,key in [('Infrastructure','infrastructure'),('Medical equipment','medical_equipment'),('Motor vehicles','motor_vehicle')]:
        a=sum(r['amounts_php'].get(key,0) for r in hfep_nep['items']);b=sum(r['amounts_php'].get(key,0) for r in hfep_house['items']);rows.append([label,a,b,b-a])
    a=n['facility_ledger_total_php'];b=h['facility_ledger_total_php'];rows.append(['Facility-ledger total',a,b,b-a])
    body=credits+f'<p>The accepted detailed baseline contains {n["facilities"]} NEP facilities and {h["facilities"]} House facilities. The NEP printed control exceeds its facility ledger by ₱{n["grand_total_php"]-a:,}; the source discrepancy is preserved and is not assigned to a fabricated facility. Funding columns below sum facility records only.</p>'+graph(rows)+table(['Funding type','NEP facility allocation pesos','HGAB facility allocation pesos','Allocation adjustment pesos'],rows)
    nc={r['label']:r['amounts_php']['total'] for r in hfep_nep['controls'] if r['kind']=='category_control'};hc={r['label']:r['amounts_php']['total'] for r in hfep_house['controls'] if r['kind']=='category_control'}
    categories=[[label,nc.get(label,0),hc.get(label,0),hc.get(label,0)-nc.get(label,0)] for label in sorted(set(nc)|set(hc))]
    body+='<h3>Facility categories · retained source controls</h3><p>A category absent from an annex contributes zero to this ledger comparison; it does not establish zero funding outside the annex. Opposing changes do not prove a direct transfer or service consequences.</p>'+graph(categories)+table(['Category','NEP allocation pesos','HGAB allocation pesos','Allocation adjustment pesos'],categories)+downloads
    inject('hfep.html','reviewed-hfep-annex',section('reviewed-hfep-annex','Reviewed HFEP facility annex · NEP → HGAB 3rd reading',body))
    for page,anchor in [('nia-irrigation.html','reviewed-nia-controls'),('hfep.html','reviewed-hfep-annex')]:
        p=STATIC/page;text=p.read_text();link=f'<p class="reviewed-annex-jump"><a href="#{anchor}">Reviewed NEP → HGAB annex comparison ↓</a></p>'
        if 'class="reviewed-annex-jump"' not in text:text=text.replace('</header>',link+'</header>',1)
        p.write_text(text)
    data={'sourcePolicy':policy,'nia':{'nep':nia,'house':house},'hfep':{'nep':hfep_nep,'house':hfep_house}}
    serialized=json.dumps(data,ensure_ascii=False,indent=2)+'\n';(OUT/'reviewed_annex_baselines.json').write_text(serialized);(STATIC/'reviewed-annex-baselines.json').write_text(serialized)
