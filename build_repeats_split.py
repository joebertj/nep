#!/usr/bin/env python3
"""Page renderers for the separate current and historical project-repeat reports."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
OUT = ROOT / 'analysis_output'

def build_repeats_page(within, scr_survival, nep_survival):
    common_style = '''<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f5;color:#18303b;font:15px/1.55 system-ui,sans-serif}main{width:100%;padding:24px clamp(16px,2vw,32px)}section{margin:20px 0;padding:22px;border:1px solid #c6dbd6;border-radius:14px;background:#fff}.repeat-hero{padding:22px;border-left:7px solid #FCD116;border-radius:14px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff}.repeat-hero h2{margin:0 0 8px;color:#fff}.repeat-hero p{margin:0}.toolbar,.pagination{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.toolbar input,.toolbar select{font:inherit;padding:8px;border:1px solid #b6c9c4;border-radius:8px}.toolbar input{min-width:min(320px,100%);flex:1}button{font:inherit;padding:8px 12px;border:1px solid #0038A8;border-radius:8px;background:#fff;color:#0038A8;cursor:pointer}button:hover{background:#eef3fb}button:disabled{opacity:.45;cursor:not-allowed}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:9px;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;text-align:left}th{background:#eef5f3}.num{white-space:nowrap;text-align:right}.repeat-summary{display:flex;flex-wrap:wrap;gap:10px}.repeat-summary strong{font-size:1.35rem}.historical-hero-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:16px 0}.historical-hero-metrics>div{padding:12px;border:1px solid #ffffff55;border-radius:10px;background:#ffffff12}.historical-hero-metrics strong{display:block;font-size:clamp(22px,3vw,32px);font-variant-numeric:tabular-nums}.historical-hero-metrics span{display:block;font-size:13px}.year-chart{overflow:auto}.year-chart svg{display:block;width:100%;min-width:660px;height:auto}.year-chart-legend{display:flex;flex-wrap:wrap;gap:16px;margin:8px 0 0;font-size:13px}.year-chart-legend span::before{content:'';display:inline-block;width:11px;height:11px;margin-right:6px;border-radius:3px;background:#FCD116}.year-chart-legend span+span::before{background:#6de0d4}.repeat-nav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.repeat-nav a{padding:7px 10px;border:1px solid #b6c9c4;border-radius:8px;background:#fff;color:#0038A8;text-decoration:none;font-weight:650}
</style>'''
    from uniform_report_menu import apply_page
    from review_report_language import NOTICE
    common_style += '''
<style>
#within-stage-repeats .repeat-pair-table{overflow-x:auto!important}
#within-stage-repeats .repeat-pair-table table{min-width:1050px!important;table-layout:auto!important}
#within-stage-repeats .repeat-pair-table :is(th,td).report-card-hidden-column{display:table-cell!important}
#within-stage-repeats .repeat-pair-table col{width:auto!important;display:table-column!important}
#within-stage-repeats .repeat-pair-table :is(th,td):nth-child(-n+2){width:22%!important}
</style>'''

    def publish(filename, title, teaser, body, extra_script=''):
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title} | BetterGov</title>{common_style}</head><body><header><div class="eyebrow">BetterGov · Budget research</div><h1>{title}</h1><p>{teaser}</p></header>'
                f'<main>{NOTICE}{body}{extra_script}</main></body></html>')
        html = apply_page(html, filename)
        from report_currency_module import format_tables
        html,_=format_tables(html)
        if filename == 'repeats.html':
            from chainage_overlap_module import build_asset, publish_asset, attach_viewer
            overlap_asset,_=build_asset()
            overlap_version=publish_asset(overlap_asset)
            html=attach_viewer(html,overlap_version)
        from report_table_presentation import apply_page_table_module
        html,_=apply_page_table_module(filename,html)
        html = '\n'.join(line.rstrip() for line in html.splitlines()) + '\n'
        return html

    body_2027 = (
        '<section class="repeat-hero"><h2>2027-only comparison sets</h2>'
        '<p>Review similar line items within NEP, HGAB 3rd reading and SCR, then trace which candidates carried into the next stage. '
        'See the <a href="repeats-historical.html">historical report</a> for the GAA comparison tables.</p></section>'
        '<nav class="repeat-nav" aria-label="2027 repeat sections"><a href="#inter-nep">Within NEP</a>'
        '<a href="#inter-hgab">Within HGAB</a><a href="#inter-scr">Within SCR</a>'
        '<a href="#repeat-scr-survival">HGAB → SCR</a><a href="#repeat-hgab-survival">NEP → HGAB</a></nav>'
        + within + scr_survival + nep_survival
    )
    html=publish('repeats.html', 'Project repeats · 2027', 'Compare FY2027 line items within and across NEP, HGAB and SCR.', body_2027)

    return {'page':'repeats.html','html':html,'withinSections':['Inter-NEP','Inter-HGAB','Inter-SCR']}


def build_repeats_historical_page(fragments=None):
    from analyze_priority_repeats import previous_rows
    from build_scr_historical_repeats import build as build_scr_historical_repeats

    if fragments is None:
        fragments_path = OUT / 'repeat_page_fragments.json'
        if not fragments_path.exists():
            raise FileNotFoundError(f'Historical repeat fragments are missing: {fragments_path}')
        fragments = json.loads(fragments_path.read_text(encoding='utf-8'))
    missing = {'fmr', 'nia'} - set(fragments)
    if missing:
        raise ValueError('Missing FY2025 historical agency repeat sections: ' + ', '.join(sorted(missing)))
    dpwh = json.loads((STATIC / 'dpwh-data.json').read_text(encoding='utf-8'))
    nep_rows = [row for row in dpwh.get('priorityRepeats', [])
                if 2016 <= int(row.get('comparison_year') or 0) <= 2026]
    hgab_data = json.loads((STATIC / 'repeat-hgab-historical-gaa.json').read_text(encoding='utf-8'))
    historical_rows = hgab_data.get('rows', [])
    historical = previous_rows(list(range(2016, 2027)))
    payload = {
        'scope': 'FY2027 NEP, HGAB 3rd reading and SCR comparisons with enacted DPWH GAAs FY2016–FY2026. FY2015 grouped PAP rows lack the project-level detail required for title matching.',
        'nepVsGaa': {'rows': nep_rows, 'years': sorted({int(r['comparison_year']) for r in nep_rows})},
        'hgabVsGaa': hgab_data,
        'scrVsGaa': build_scr_historical_repeats(historical),
    }
    data_path = STATIC / 'repeats-historical-data.json'
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    version = hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:12]

    common_style = '''<style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f5;color:#18303b;font:15px/1.55 system-ui,sans-serif}main{width:100%;padding:24px clamp(16px,2vw,32px)}section{margin:20px 0;padding:22px;border:1px solid #c6dbd6;border-radius:14px;background:#fff}.repeat-hero{padding:22px;border-left:7px solid #FCD116;border-radius:14px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff}.repeat-hero h2{margin:0 0 8px;color:#fff}.repeat-hero p{margin:0}.toolbar,.pagination{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0}.toolbar input,.toolbar select{font:inherit;padding:8px;border:1px solid #b6c9c4;border-radius:8px}.toolbar input{min-width:min(320px,100%);flex:1}button{font:inherit;padding:8px 12px;border:1px solid #0038A8;border-radius:8px;background:#fff;color:#0038A8;cursor:pointer}button:hover{background:#eef3fb}button:disabled{opacity:.45;cursor:not-allowed}.tablewrap{overflow:auto}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{padding:9px;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere;text-align:left}th{background:#eef5f3}.num{white-space:nowrap;text-align:right}.repeat-summary{display:flex;flex-wrap:wrap;gap:10px}.repeat-summary strong{font-size:1.35rem}.historical-hero-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.historical-hero-metrics>div{padding:12px;border:1px solid #ffffff55;border-radius:10px;background:#ffffff12}.historical-hero-metrics strong{display:block;font-size:clamp(22px,3vw,32px);font-variant-numeric:tabular-nums}.historical-hero-metrics span{display:block;font-size:13px}.repeat-nav{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}.repeat-nav a{padding:7px 10px;border:1px solid #b6c9c4;border-radius:8px;background:#fff;color:#0038A8;text-decoration:none;font-weight:650}
.year-chart-panel{--nep-bar:#a06e00;--hgab-bar:#087e74;--scr-bar:#9d407e}
.year-chart{max-width:980px}
.year-chart-group{display:grid;grid-template-columns:4rem minmax(0,1fr);align-items:center;margin:12px 0}
.year-chart-bars,.year-chart-legend{display:grid;gap:4px}
.year-chart-bar{display:grid;grid-template-columns:minmax(0,1fr) 2.8rem;gap:8px;align-items:center;font-size:13px;line-height:1.1}
.year-chart-track{display:block;border-radius:4px;background:#e8eff1}
.year-chart-fill{display:block;height:13px;border-radius:4px;background:var(--bar-color)}
.year-chart-legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin:12px 0 0;font-size:13px}
.year-chart-legend span::before{content:'';display:inline-block;width:11px;height:11px;margin-right:6px;border-radius:3px;background:var(--bar-color)}
.year-chart-panel [data-series="nep"]{--bar-color:var(--nep-bar)}
.year-chart-panel [data-series="hgab"]{--bar-color:var(--hgab-bar)}
.year-chart-panel [data-series="scr"]{--bar-color:var(--scr-bar)}
.repeat-hero .historical-hero-metrics a{color:inherit}
@media(max-width:640px){.historical-hero-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style>'''
    from uniform_report_menu import apply_page
    from review_report_language import NOTICE

    def publish(filename, title, teaser, body, extra_script=''):
        html = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title} | BetterGov</title>{common_style}</head><body><header><div class="eyebrow">BetterGov · Budget research</div><h1>{title}</h1><p>{teaser}</p></header>'
                f'<main>{NOTICE}{body}{extra_script}</main></body></html>')
        html = apply_page(html, filename)
        from report_currency_module import format_tables
        html,_=format_tables(html)
        if filename == 'repeats.html':
            from chainage_overlap_module import build_asset, publish_asset, attach_viewer
            overlap_asset,_=build_asset()
            overlap_version=publish_asset(overlap_asset)
            html=attach_viewer(html,overlap_version)
        from report_table_presentation import apply_page_table_module
        html,_=apply_page_table_module(filename,html)
        html = '\n'.join(line.rstrip() for line in html.splitlines()) + '\n'
        return html

    historical_body = '''
<section class="repeat-hero"><h2>Historical GAA title comparisons</h2><p>Compare FY2027 budget proposals with enacted DPWH GAA records. The NEP screen ranks titles by similarity. The HGAB and SCR screens require an exact title and place match. Review the scope of work, contracts and payments before drawing conclusions about duplication.</p><div class="historical-hero-metrics"><div><strong id="hero-nep-count">—</strong><span>NEP-to-GAA comparison pairs</span></div><div><strong id="hero-hgab-count">—</strong><span>HGAB-to-GAA comparison pairs</span></div><div><a href="#scr-historical"><strong id="hero-scr-count">—</strong><span>SCR-to-GAA comparison pairs</span></a></div><div><strong id="hero-year-count">—</strong><span>historical GAA years</span></div></div><p>FY2016–FY2019 and FY2020–FY2026 are included where project-level detail is available. FY2019 uses the DBM technical DPWH GAA schedule. FY2015 PAP groups are excluded because their codes do not identify unique projects. <a href="gaa-2015-dpwh-technical.html">Search FY2015 parsed lines</a>.</p></section><section class="year-chart-panel"><h2>Comparison pairs by GAA year</h2><p>The chart updates with the year and search filters in all three comparison tables.</p><div id="historical-year-chart" class="year-chart" role="img" aria-label="Filtered historical comparison pairs by year"></div><div class="year-chart-legend"><span data-series="nep">NEP title candidates</span><span data-series="hgab">HGAB exact title and place</span><span data-series="scr">SCR exact title and place</span></div></section>
<section id="nep-historical"><h2>FY2027 NEP vs enacted DPWH GAA · FY2016–FY2026</h2><p>Ranked title candidates from the NEP against prior enacted DPWH GAA records. FY2019 is included using the DBM technical schedule; FY2015 PAP groups are incompatible with this project-level matching method and excluded. Amounts and source titles remain separate for review.</p><div class="repeat-summary"><span><strong id="nep-count">—</strong> comparison pairs</span><span><strong id="nep-years">—</strong> GAA years</span></div><div class="toolbar"><label>GAA year <select id="nep-year"><option value="all">All years</option></select></label><input id="nep-search" type="search" placeholder="Search title, office, or source"><button id="nep-export">Export CSV</button></div><div class="tablewrap"><table><thead><tr><th>NEP project · category</th><th>Office</th><th>GAA year</th><th>Historical GAA title · source</th><th class="num">NEP amount</th><th class="num">GAA amount</th><th>Title score</th></tr></thead><tbody id="nep-body"></tbody></table></div><div class="pagination"><button id="nep-prev">Previous</button><span id="nep-page">Page 1</span><button id="nep-next">Next</button></div><p id="nep-status" class="note"></p></section>
<section id="hgab-historical"><h2>HGAB 3rd vs historical GAA · exact title and place</h2><p>HGAB lines with an exact normalized title and qualified municipality/province match in the available FY2016–FY2019 DPWH source layers and FY2020–FY2026 GAA records. FY2019 uses DBM’s technical DPWH schedule. FY2015 source records are available, but are not included in exact-title counts for the PAP-code and title-structure reasons described above.</p><div class="repeat-summary"><span><strong id="hgab-count">—</strong> comparison pairs</span><span><strong id="hgab-projects">—</strong> HGAB lines</span><span><strong id="hgab-years">—</strong> GAA years</span></div><div class="toolbar"><label>GAA year <select id="hgab-year"><option value="all">All years</option></select></label><input id="hgab-search" type="search" placeholder="Search HGAB title, GAA title, office, or source"><button id="hgab-export">Export CSV</button></div><div class="tablewrap"><table><thead><tr><th>HGAB project · office · page</th><th>GAA year</th><th>Historical GAA title · source</th><th class="num">HGAB amount</th><th class="num">GAA amount</th><th class="num">Change</th><th>Chainage evidence</th></tr></thead><tbody id="hgab-body"></tbody></table></div><div class="pagination"><button id="hgab-prev">Previous</button><span id="hgab-page">Page 1</span><button id="hgab-next">Next</button></div><p id="hgab-status" class="note"></p></section>
'''
    historical_body += '''
<section id="scr-historical">
  <h2>FY2027 SCR vs historical GAA · exact title and place</h2>
  <p>Compares positive DPWH allocations in the Senate Committee Report with enacted FY2016–FY2026 road, bridge, multi-purpose building and flood-control lines. Titles must match after removing trailing station or coordinate details, and the municipality and province must agree. The source links point to SCR Annex A-4 or the House schedule for lines carried into the SCR.</p>
  <div class="repeat-summary"><span><strong id="scr-count">—</strong> comparison pairs</span><span><strong id="scr-projects">—</strong> SCR lines</span><span><strong id="scr-years">—</strong> GAA years covered</span></div>
  <div class="toolbar"><label>GAA year <select id="scr-year"><option value="all">All years</option></select></label><input id="scr-search" type="search" aria-label="Search SCR comparisons" placeholder="Search SCR title, GAA title, office, or source"><button id="scr-export">Export CSV</button></div>
  <div class="tablewrap"><table><thead><tr><th>SCR project · office · source</th><th>GAA year</th><th>Historical GAA title · source</th><th class="num">SCR amount</th><th class="num">GAA amount</th><th class="num">Change</th><th>Chainage evidence</th></tr></thead><tbody id="scr-body"></tbody></table></div>
  <div class="pagination"><button id="scr-prev">Previous</button><span id="scr-page">Page 1</span><button id="scr-next">Next</button></div><p id="scr-status" class="note" aria-live="polite"></p>
</section>
'''
    fmr_section = fragments['fmr'].replace('<section ', '<section id="fmr" ', 1)
    nia_section = fragments['nia'].replace('<section ', '<section id="nia" ', 1)
    historical_body += (
        '<section id="fy2025-agency-repeats" class="year-chart-panel"><h2>FY2027 vs FY2025 GAA · agency-level review screens</h2>'
        '<p>These additional FMR and NIA comparisons use the available FY2025 enacted schedules. They are candidate screens, not verified repeat work. FY2026 schedule data is unavailable for these agency comparisons.</p>'
        '<nav class="repeat-nav" aria-label="Agency historical comparisons"><a href="#fmr">FMR</a><a href="#nia">NIA irrigation</a></nav></section>'
        + fmr_section + nia_section
    )
    hist_script = f'''<script>
(()=>{{
  const load = () => (async()=>{{const D=await fetch('repeats-historical-data.json?v={version}').then(r=>{{if(!r.ok)throw Error(r.status);return r.json()}}),$=id=>document.getElementById(id),peso=n=>'₱'+Number(n||0).toLocaleString('en-PH'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const nep = D.nepVsGaa.rows, size = 50;
let pn = 0, nf = [];
const exactTables = [
  {{prefix:'hgab', label:'HGAB', occurrence:'hgabId', total:'hgabOccurrences', data:D.hgabVsGaa, page:0, filtered:[]}},
  {{prefix:'scr', label:'SCR', occurrence:'scrId', total:'scrOccurrences', data:D.scrVsGaa, page:0, filtered:[]}}
];
function initYear(select,years){{for(const y of years){{const o=document.createElement('option');o.value=y;o.textContent='FY'+y+' GAA';$(select).append(o)}}}}
initYear('nep-year', D.nepVsGaa.years);
$('hero-nep-count').textContent = nep.length.toLocaleString('en-PH');
const years = [...new Set([...D.nepVsGaa.years, ...exactTables.flatMap(table => table.data.summary.years)])];
$('hero-year-count').textContent = years.length.toLocaleString('en-PH');

function drawYearChart() {{
  const chart = $('historical-year-chart');
  const series = [
    {{key:'nep', label:'NEP', year:'comparison_year', rows:nf}},
    {{key:'hgab', label:'HGAB', year:'gaaYear', rows:exactTables[0].filtered}},
    {{key:'scr', label:'SCR', year:'gaaYear', rows:exactTables[1].filtered}}
  ];
  const counts = new Map();
  series.forEach((item, i) => {{
    for (const row of item.rows) {{
      const year = Number(row[item.year]);
      if (!counts.has(year)) counts.set(year, [0, 0, 0]);
      counts.get(year)[i]++;
    }}
  }});
  if (!counts.size) {{
    const message = 'No comparison pairs match the selected filters.';
    chart.textContent = message;
    chart.setAttribute('aria-label', message);
    return;
  }}
  const max = Math.max(...[...counts.values()].flat());
  const orderedYears = [...counts.keys()].sort((a,b) => a-b);
  chart.innerHTML = orderedYears.map(year => {{
    const bars = series.map((item, i) => {{
      const count = counts.get(year)[i];
      return `<div class="year-chart-bar" data-series="${{item.key}}" data-count="${{count}}" title="${{item.label}} FY${{year}}: ${{count}} pairs">
        <span class="year-chart-track"><span class="year-chart-fill" style="width:${{100 * count / max}}%"></span></span><span>${{count}}</span>
      </div>`;
    }}).join('');
    return `<div class="year-chart-group" data-year="${{year}}" aria-hidden="true"><strong>FY${{year}}</strong><div class="year-chart-bars">${{bars}}</div></div>`;
  }}).join('');
  chart.setAttribute('aria-label', orderedYears.map(year =>
    'FY' + year + ', ' + series.map((item, i) => item.label + ' ' + counts.get(year)[i]).join(', ')
  ).join('. '));
}}

function drawNep(){{const q=$('nep-search').value.toLowerCase().trim(),y=$('nep-year').value;nf=nep.filter(r=>(y==='all'||String(r.comparison_year)===y)&&JSON.stringify(r).toLowerCase().includes(q)).sort((a,b)=>b.similarity_pct-a.similarity_pct);const pages=Math.max(1,Math.ceil(nf.length/size));pn=Math.min(pn,pages-1);$('nep-body').innerHTML=nf.slice(pn*size,(pn+1)*size).map(r=>'<tr><td>'+esc(r.project)+'<br><small>'+esc(r.category)+'</small></td><td>'+esc(r.office)+'</td><td>FY'+r.comparison_year+'</td><td>'+esc(r.prior_project)+'<br><small>'+esc(r.prior_source)+'</small></td><td class="num">'+peso(r.amount_2027)+'</td><td class="num">'+peso(r.prior_amount)+'</td><td>'+Number(r.similarity_pct||0)+'%</td></tr>').join('')||'<tr><td colspan="7">No matching records.</td></tr>';$('nep-page').textContent='Page '+(pn+1)+' of '+pages+' · '+nf.length.toLocaleString()+' pairs';$('nep-prev').disabled=pn===0;$('nep-next').disabled=pn>=pages-1;$('nep-count').textContent=nep.length.toLocaleString('en-PH');$('nep-years').textContent=D.nepVsGaa.years.length.toLocaleString('en-PH');$('nep-status').textContent=nf.length.toLocaleString('en-PH')+' filtered title candidates; similarity is a screen, not a duplicate finding.'}}
function drawExact(table) {{
  const field = name => $(table.prefix + '-' + name);
  const q = field('search').value.toLowerCase().trim(), year = field('year').value;
  table.filtered = table.data.rows.filter(r => (year === 'all' || String(r.gaaYear) === year)
    && JSON.stringify(r).toLowerCase().includes(q));
  const pages = Math.max(1, Math.ceil(table.filtered.length / size));
  table.page = Math.min(table.page, pages - 1);
  field('body').innerHTML = table.filtered.slice(table.page * size, (table.page + 1) * size).map(r => {{
    const source = esc(r.sourceVolume) + (r.sourcePage ? ' · p. ' + esc(r.sourcePage) : '');
    const citation = r.sourceUrl ? `<a href="${{esc(r.sourceUrl)}}">${{source}}</a>` : source;
    const change = (r.changePesos >= 0 ? '+' : '−') + peso(Math.abs(r.changePesos));
    return `<tr><td>${{esc(r.projectName)}}<br><small>${{esc(r.office)}} · ${{citation}}</small></td>
      <td>FY${{r.gaaYear}}</td><td>${{esc(r.gaaTitle)}}<br><small>${{esc(r.gaaSource)}}</small></td>
      <td class="num">${{peso(r.amountPesos)}}</td><td class="num">${{peso(r.gaaAmountPesos)}}</td>
      <td class="num">${{change}}</td><td>${{esc(r.chainageStatus)}}${{r.chainageOverlap ? ' · ' + esc(r.chainageOverlap) : ''}}</td></tr>`;
  }}).join('') || '<tr><td colspan="7">No matching records.</td></tr>';
  field('page').textContent = 'Page ' + (table.page + 1) + ' of ' + pages + ' · ' + table.filtered.length.toLocaleString('en-PH') + ' pairs';
  field('prev').disabled = table.page === 0;
  field('next').disabled = table.page >= pages - 1;
  field('status').textContent = table.filtered.length.toLocaleString('en-PH') + ' filtered exact-title and qualified-place comparisons.';
}}
function csv(name,rows,keys){{const out=[keys,...rows.map(r=>keys.map(k=>r[k]))].map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\\r\\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+out],{{type:'text/csv;charset=utf-8'}}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}}
for (const id of ['nep-search','nep-year']) $(id).oninput = $(id).onchange = () => {{ pn=0; drawNep(); drawYearChart(); }};
$('nep-prev').onclick = () => {{ pn--; drawNep(); }};
$('nep-next').onclick = () => {{ pn++; drawNep(); }};
$('nep-export').onclick = () => csv('nep-historical-gaa-repeats.csv',nf,['category','project','office','comparison_year','prior_project','amount_2027','prior_amount','similarity_pct','prior_source']);
for (const table of exactTables) {{
  const field = name => $(table.prefix + '-' + name);
  const summary = table.data.summary;
  initYear(table.prefix + '-year', summary.years);
  const count = table.data.rows.length.toLocaleString('en-PH');
  $('hero-' + table.prefix + '-count').textContent = count;
  field('count').textContent = count;
  field('projects').textContent = summary[table.total].toLocaleString('en-PH');
  field('years').textContent = summary.years.length.toLocaleString('en-PH');
  for (const name of ['search', 'year']) field(name).oninput = field(name).onchange = () => {{
    table.page = 0;
    drawExact(table);
    drawYearChart();
  }};
  field('prev').onclick = () => {{ table.page--; drawExact(table); }};
  field('next').onclick = () => {{ table.page++; drawExact(table); }};
  const columns = [table.occurrence,'projectName','office','gaaYear','gaaTitle','amountPesos','gaaAmountPesos','changePesos','gaaSource','chainageStatus','chainageOverlap'];
  if (table.prefix === 'scr') columns.push('sourceVolume','sourcePage','sourceUrl','sourceEvidence');
  field('export').onclick = () => csv(table.prefix + '-historical-gaa-repeats.csv', table.filtered, columns);
  drawExact(table);
}}
drawNep();
drawYearChart();
}})().catch(e=>{{
  for (const id of ['nep-status', 'hgab-status', 'scr-status']) document.getElementById(id).textContent = 'Historical repeat data unavailable: ' + e.message;
}});
  if ('IntersectionObserver' in window) {{
    const observer = new IntersectionObserver(entries => {{
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      load();
    }}, {{rootMargin: '320px'}});
    for (const selector of ['.repeat-hero', '#nep-historical', '#hgab-historical', '#scr-historical', '#historical-year-chart']) {{
      observer.observe(document.querySelector(selector));
    }}
  }} else load();
}})();
</script>'''
    from build_repeat_project_browser import publish as publish_project_browser
    browser = publish_project_browser(payload, historical)
    html=publish('repeats-historical.html', 'Project repeats · Historical', 'Compare project titles against enacted historical GAA records.', historical_body, hist_script)
    html = html.replace('<main>', '<main>' + browser, 1)
    return {'page':'repeats-historical.html','html':html,'dataFilename':'repeats-historical-data.json','data':serialized,'nepVsGaaPairs':len(nep_rows),'hgabVsGaaPairs':len(historical_rows),'scrVsGaaPairs':payload['scrVsGaa']['summary']['comparisonPairs']}
