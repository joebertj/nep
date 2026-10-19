#!/usr/bin/env python3
"""Build the active RCS page from parsed NEP POW evidence."""
import html
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ODV=ROOT.parent/'open-data-visualization'
STATIC=ODV/'static/nep-preview'
DATA=ROOT/'analysis_output/dpwh-in-depth-data.json'

FOCUS_ITEMS={
    '2027DPWH-Proposal-00294':'Water Tank (Polyethylene)',
    '2027DPWH-Proposal-00296':'Water Tank (Polyethylene)',
    '2027DPWH-Proposal-00130':'Cold Water Lines',
    '2027DPWH-Proposal-00301':'Water Tank, Stainless',
}

def esc(value):
    return html.escape(str(value if value is not None else ''),quote=True)

def money(value, cents=False):
    return '₱'+format(float(value),',.2f' if cents else ',.0f')

def read_evidence():
    source=json.loads(DATA.read_text())
    projects={p['code']:p for p in source.get('projects',[]) if p.get('code') in FOCUS_ITEMS}
    if set(projects)!=set(FOCUS_ITEMS):
        raise RuntimeError('One or more featured RCS projects are missing from the in-depth dataset')
    output=[]
    for code,description in FOCUS_ITEMS.items():
        project=projects[code]
        doc=next((d for d in project.get('documents',[]) if d.get('kind')=='pow' and d.get('url')),None)
        if not doc:
            raise RuntimeError(f'Missing POW link for {code}')
        rows=[r for r in doc.get('rows',[]) if r.get('description')==description and r.get('costBasis')=='as_submitted' and r.get('amountPesos') is not None]
        if not rows:
            raise RuntimeError(f'Missing submitted POW row {description} for {code}')
        contexts=set()
        for row in doc.get('rows',[]):
            for context in row.get('componentContexts') or []:
                if context: contexts.add(context.strip())
            if row.get('componentContext'):
                contexts.add(row['componentContext'].strip())
        amount=sum(float(r['amountPesos']) for r in rows)
        quantity=sum(float(r['quantity']) for r in rows if r.get('quantity') is not None)
        units=sorted({str(r.get('unit')).strip() for r in rows if r.get('unit')})
        pages=sorted({int(r['sourcePage']) for r in rows if r.get('sourcePage')})
        output.append({
            'code':code,'name':project.get('name',''),'office':project.get('office',''),
            'allocation':float(project.get('allocationPesos') or 0),'contexts':sorted(contexts),
            'item':description,'amount':amount,'quantity':quantity,'units':units,
            'rowCount':len(rows),'pages':pages,'powUrl':doc['url'],
            'unitMissing':not units,
        })
    return output

def render(rows):
    header='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rainwater Collector System · POW scope review</title>
<link rel="stylesheet" href="research-theme.css?v=6b0f9a00e1f6"><link rel="stylesheet" href="report-table-readability.css?v=7d42000af5d9">
<style>
*{box-sizing:border-box}main{width:100%;padding:24px clamp(16px,2vw,32px)}.card{background:#fff;border:1px solid #d9e3e1;border-radius:14px;padding:22px;margin:22px 0}.lead{border-left:5px solid #b65b09;background:#fff8e9}.tablewrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.94rem}th,td{text-align:left;vertical-align:top;padding:11px;border-bottom:1px solid #d9e3e1}th{background:#edf3f2}.money{white-space:nowrap;font-variant-numeric:tabular-nums}details{margin-top:7px}summary{cursor:pointer;color:#096f72;font-weight:700}.source a{font-weight:700}.note{color:#536873}.facility-list{margin:.5rem 0;padding-left:1.2rem}.tag{display:inline-block;padding:3px 8px;border-radius:999px;background:#fff0d4;color:#754500;font-weight:700;font-size:.82rem}@media(max-width:720px){main{padding:12px}table{min-width:720px}}
</style></head><body class="bettergov-research"><header><div class="eyebrow">FY2027 NEP · DPWH · Rainwater Collector System</div><h1>Rainwater Collector System · POW scope review</h1><p>Same proposed allocation, differing documented schools, buildings, and leading POW items.</p></header><main>'''
    from build_report_heroes import STYLE as HERO_STYLE,hero as shared_hero
    lead=shared_hero('FY2027 NEP · DPWH · RCS', '199', 'district-office projects share one scheduled allocation', '₱4.2M', 'per project in the schedule', [
        ('Davao City POW examples','6 vs 14','named school sites'),
        ('Davao del Sur POW','₱3.89M','parsed tank line · 92.7% of allocation'),
    ], 'Different scopes and repeated allocations create a reason to compare the engineering estimates; they do not establish padding or wrongdoing.')
    body='''<aside id="report-evidence-notice" role="note"><strong>Evidence limits.</strong> These are proposed allocations and machine-extracted POW entries, not verified spending. Parsed line totals and site contexts should be checked against each cited page. Different facility counts and identical budget amounts create a review lead; they do not by themselves establish padding, intent, or wrongdoing.</aside>
<section class="card lead"><span class="tag">Priority review lead</span><h2>Was each POW priced from its actual scope, or shaped around a fixed per-office amount?</h2><p>Six and fourteen named school sites both sit under ₱4.2M allocations. A separate POW has a parsed 30-tank line worth about 92.7% of its allocation, while the unit and site count are not established in the extraction. The spread makes the repeated amount harder to explain from the schedule alone and warrants checking the engineering estimates, quantities, standard design, and any per-office cap. It is not proof that costs were added to exhaust a budget.</p></section>
<section class="card"><h2>POW examples · same allocation, differing scopes and leading items</h2><p class="note">Facility names and item entries below are taken from the in-depth POW extraction. Open each list and source link to review the underlying pages. Amount share is the extracted item total divided by the ₱4.2M project allocation.</p><div class="tablewrap"><table><thead><tr><th>Project / office</th><th>Named schools or buildings</th><th>Leading extracted POW item</th><th>Project allocation</th><th>Evidence</th></tr></thead><tbody>'''
    for r in rows:
        scope=(f'<strong>{len(r["contexts"])} named facilities</strong>' if r['contexts'] else '<strong>Not established</strong><br><span class="note">No named facility contexts extracted</span>')
        if r['contexts']:
            scope+=f'<details><summary>Show {len(r["contexts"])} names</summary><ul class="facility-list">'+''.join(f'<li>{esc(x)}</li>' for x in r['contexts'])+'</ul></details>'
        qty=format(r['quantity'],',.0f')
        unit=(', '.join(esc(u) for u in r['units']) if r['units'] else 'unit not parsed')
        share=(r['amount']/r['allocation']*100) if r['allocation'] else 0
        item=f'<strong>{esc(r["item"])}</strong><br>{qty} {unit} · <span class="money">{money(r["amount"],cents=True)}</span> <span class="note">({share:.1f}% of allocation; extracted)</span>'
        if r['code']=='2027DPWH-Proposal-00296':
            item+='<br><span class="note">14 per-school lines · 6 sets each</span>'
        if r['code']=='2027DPWH-Proposal-00130':
            item+='<br><span class="note">15 extracted line rows for 14 named facilities; reconcile possible duplicate or repeated entries.</span>'
        if r['unitMissing']:
            item+='<br><span class="note">Quantity unit is absent in the parsed row.</span>'
        page=f'#page={r["pages"][0]}' if r['pages'] else ''
        range_text=(f' · pp. {r["pages"][0]}–{r["pages"][-1]}' if len(r['pages'])>1 else (f' · p. {r["pages"][0]}' if r['pages'] else ''))
        body+=f'<tr><td><strong>{esc(r["office"])}</strong><br><span class="note">{esc(r["code"])}</span></td><td>{scope}</td><td>{item}</td><td class="money">{money(r["allocation"])}</td><td class="source"><a href="{esc(r["powUrl"]+page)}" target="_blank" rel="noopener">Open POW{range_text} ↗</a></td></tr>'
    body+='''</tbody></table></div></section>
<section class="card"><h2>What to verify</h2><ul><li>Whether the same ₱4.2M is a standard design package, a planning ceiling, or independently costed for each site.</li><li>Whether facilities, tanks, quantities, units, and item totals in each POW reconcile to the signed engineering estimate.</li><li>Whether the listed locations and delivery scope match the project implementation records.</li></ul><p><a href="dpwh.html">Open the DPWH in-depth POW review queue ↗</a> · <a href="rcs-rainfall-archive.html">Open the archived rainfall-only scenario ↗</a></p></section></main><footer style="text-align:center;padding:18px;color:#536873">A review lead for human verification, not a finding.</footer></body></html>'''
    body=body.replace('</aside>', '</aside>'+lead, 1)
    page=header.replace('</head>',HERO_STYLE+'</head>')+body
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    page=apply_uniform_menu_page(page,'rcs.html')
    from report_table_presentation import publish_assets,apply_page as apply_report_styles
    return apply_report_styles(page,publish_assets())

def main():
    out=STATIC/'rcs.html'
    out.write_text(render(read_evidence()),encoding='utf-8')
    print(f'Wrote {out}')

if __name__=='__main__':main()
