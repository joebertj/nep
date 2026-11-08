#!/usr/bin/env python3
"""Page module for Historical · DPWH allocations by project type."""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
OUT = ROOT / 'analysis_output'


def build_page():
    """Publish classified historical DPWH allocations for four project types."""
    source = STATIC / 'integrated-project-data.json'
    integrated = json.loads(source.read_text(encoding='utf-8'))
    category_map = {'Flood control': 'Flood Control', 'Multi-purpose building': 'MPB', 'Road': 'Roads', 'Bridge': 'Bridges'}
    grouped = defaultdict(lambda: {'projectCount': 0, 'allocationPesos': 0})
    for row in integrated.get('projects', []):
        if row.get('stage') != 'GAA' or row.get('category') not in category_map: continue
        try: year, amount = int(row.get('year') or 0), int(float(row.get('amountPesos') or 0))
        except (TypeError, ValueError): continue
        if not year: continue
        key = (year, category_map[row['category']])
        grouped[key]['projectCount'] += 1
        grouped[key]['allocationPesos'] += amount
    import re
    site_signal_rules = [
        ('Subdivision named', re.compile(r'\bsubdivision\b', re.I)),
        ('HOA named', re.compile(r'\bHOA\b|homeowners?\s*(?:association|assoc)', re.I)),
        ('Village named · weak location cue', re.compile(r'\bvillage\b', re.I)),
        ('Explicit private-land wording', re.compile(r'\bprivate(?:ly)?\b|private\s+(?:land|lot|property)', re.I)),
        ('Land/lot transaction wording', re.compile(r'\b(?:land|lot)\s+(?:acquisition|purchase|donation|donated|leased|owned)\b', re.I)),
    ]
    site_rows = []
    for row in integrated.get('projects', []):
        if row.get('category') != 'Multi-purpose building': continue
        year, stage, title = int(row.get('year') or 0), str(row.get('stage') or ''), str(row.get('name') or '')
        if not (stage == 'GAA' and 2015 <= year <= 2026 or year == 2027 and stage == 'HGAB 3rd'): continue
        signals = [label for label, pattern in site_signal_rules if pattern.search(title)]
        if signals:
            site_rows.append({'year': year, 'stage': stage, 'title': title, 'signals': signals,
                              'amountPesos': int(float(row.get('amountPesos') or 0)), 'source': str(row.get('source') or '')})
    site_rows.sort(key=lambda x: (-x['amountPesos'], x['year'], x['title']))
    site_payload = {'scope': 'FY2015–FY2026 enacted GAA and FY2027 HGAB 3rd reading; title cues only.', 'rows': site_rows,
                    'method': 'MPB title screen. Village is a weak location cue and does not establish ownership.'}
    site_serialized = json.dumps(site_payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (STATIC / 'mpb-site-indicators-data.json', OUT / 'mpb-site-indicators-data.json'):
        path.write_text(site_serialized, encoding='utf-8')
    categories = ['Flood Control', 'MPB', 'Roads', 'Bridges']
    years = sorted({year for year, _ in grouped})
    payload = {'source': 'integrated-project-data.json', 'method': 'GAA-stage classified DPWH project rows grouped by fiscal year and source category.', 'years': years, 'categories': categories,
        'rows': [{'year': year, 'projectType': category, **grouped.get((year, category), {'projectCount': 0, 'allocationPesos': 0})} for year in years for category in categories]}
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    version = hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:12]
    for path in (STATIC / 'historical-allocations-data.json', OUT / 'historical-allocations-data.json'): path.write_text(serialized, encoding='utf-8')
    page = f'''<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Historical allocations · BetterGov</title>
<style>body{{margin:0;background:#eef3f4;color:#18303b;font:16px/1.5 system-ui,sans-serif}}header{{background:#142e3b;color:white;padding:24px 2vw}}h1{{margin:0;font-size:30px}}main{{padding:24px 2vw;max-width:none}}section.card{{background:white;border:1px solid #ccdcd8;border-radius:14px;padding:24px;margin:24px 0}}h2{{margin-top:0}}a{{color:#087e78}}.controls{{display:flex;align-items:center;gap:10px;margin:16px 0}}select{{font:inherit;padding:8px;border:1px solid #aebdca;border-radius:8px;background:white}}.chart{{display:grid;gap:8px;margin:16px 0 22px}}.bar-row{{display:grid;grid-template-columns:70px minmax(80px,1fr) minmax(130px,auto);align-items:center;gap:10px}}.track{{height:13px;background:#e7edf2;border-radius:20px;overflow:hidden}}.fill{{height:100%;background:linear-gradient(90deg,#0038a8,#168c86)}}table{{width:100%;border-collapse:collapse;table-layout:fixed}}th,td{{padding:10px;text-align:left;vertical-align:top;border-bottom:1px solid #d9e3e1;overflow-wrap:anywhere}}th{{background:#edf4f2}}.num{{text-align:right;white-space:nowrap}}.note{{color:#526773}}@media(max-width:650px){{th,td{{font-size:12px;padding:6px}}section.card{{padding:14px}}.bar-row{{grid-template-columns:52px minmax(50px,1fr) minmax(95px,auto);font-size:12px}}}}</style></head><body><header><h1>Historical DPWH allocations</h1><p>Classified GAA allocations for Flood Control, MPB, Roads and Bridges</p></header><main>
<section class=\"card\"><h2>Annual allocation by project type</h2><p>Counts and listed allocations use the integrated DPWH GAA project dataset. Categories follow that dataset's classification; this is not a complete account of every DPWH budget line. Allocations are not spending.</p><div class=\"controls\"><label for=\"type\">Project type</label><select id=\"type\"><option>Flood Control</option><option>MPB</option><option>Roads</option><option>Bridges</option></select></div><div id=\"chart\" class=\"chart\" aria-label=\"Annual allocation chart\"></div><div class=\"table-wrap\"><table><thead><tr><th>Fiscal year</th><th>Project type</th><th class=\"num\">Classified project rows</th><th class=\"num\">Listed allocation</th></tr></thead><tbody id=\"rows\"><tr><td colspan=\"4\">Loading historical allocations…</td></tr></tbody></table></div><p><a href=\"contractors.html?type=MPB\">Browse MPB contractors →</a></p><p class=\"note\">Source: integrated-project-data.json · GAA-stage DPWH rows · <a href=\"historical-allocations-data.json\" download>Download grouped data</a>.</p></section>
</main><script>fetch('historical-allocations-data.json?v={version}').then(r=>{{if(!r.ok)throw Error(r.status);return r.json()}}).then(d=>{{const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x),type=document.getElementById('type'),rows=document.getElementById('rows'),chart=document.getElementById('chart');function draw(){{const items=d.rows.filter(x=>x.projectType===type.value),max=Math.max(1,...items.map(x=>Number(x.allocationPesos||0)));rows.innerHTML=items.map(x=>'<tr><td>FY'+Number(x.year)+'</td><td>'+x.projectType+'</td><td class=\"num\">'+n(x.projectCount)+'</td><td class=\"num\">'+peso(x.allocationPesos)+'</td></tr>').join('')||'<tr><td colspan=\"4\">No rows for this category.</td></tr>';chart.innerHTML=items.map(x=>'<div class=\"bar-row\"><strong>FY'+Number(x.year)+'</strong><span class=\"track\"><span class=\"fill\" style=\"display:block;width:'+Math.max(0,Math.min(100,100*Number(x.allocationPesos||0)/max))+'%\"></span></span><span class=\"num\">'+peso(x.allocationPesos)+'</span></div>').join('')||'<p class=\"note\">No allocation values available.</p>'}}type.addEventListener('change',draw);draw()}}).catch(e=>{{document.getElementById('rows').innerHTML='<tr><td colspan=\"4\">Historical allocation data unavailable: '+String(e.message)+'</td></tr>'}});</script></body></html>'''
    site_section = '''<section class="card" id="mpb-site-indicators"><h2>MPB sites with subdivision, village or private-land cues</h2><p class="note">FY2015–FY2026 enacted GAA and FY2027 HGAB 3rd-reading MPB titles. “Village” is a weaker location cue; no title signal proves private ownership or restricted access. Verify title, donation, authorization and public purpose against source documents.</p><p id="mpb-site-summary" aria-live="polite">Loading…</p><div class="controls"><label for="mpb-site-year">Year</label><select id="mpb-site-year"><option value="all">All years</option></select><label for="mpb-site-search">Project</label><input id="mpb-site-search" type="search" placeholder="Search title or source" style="font:inherit;padding:8px;min-width:220px"></div><div class="table-wrap"><table data-report-table-exempt="true"><thead><tr><th>Year / stage</th><th>Project title</th><th>Title cue</th><th class="num">Allocation</th><th>Source</th></tr></thead><tbody id="mpb-site-rows"></tbody></table></div><div class="controls"><button id="mpb-site-prev" type="button">Previous</button><span id="mpb-site-page"></span><button id="mpb-site-next" type="button">Next</button></div><p class="note">Separate screening data: <a href="mpb-site-indicators-data.json" download>download JSON</a>.</p></section>'''
    page = page.replace('</main>', site_section + '</main>', 1)
    site_script = '''<script>fetch('mpb-site-indicators-data.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{const rows=d.rows,year=document.getElementById('mpb-site-year'),search=document.getElementById('mpb-site-search'),body=document.getElementById('mpb-site-rows'),summary=document.getElementById('mpb-site-summary'),pageLabel=document.getElementById('mpb-site-page'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));[...new Set(rows.map(x=>x.year))].sort((a,b)=>a-b).forEach(y=>year.add(new Option(`FY${y}`,y)));const n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(x);let page=0;function draw(){const q=search.value.trim().toLowerCase(),filtered=rows.filter(x=>(year.value==='all'||String(x.year)===year.value)&&(!q||`${x.title} ${x.source} ${x.signals.join(' ')}`.toLowerCase().includes(q))),size=25,pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages-1);const shown=filtered.slice(page*size,(page+1)*size),total=filtered.reduce((a,x)=>a+Number(x.amountPesos||0),0),village=filtered.filter(x=>x.signals.some(y=>y.startsWith('Village')));summary.textContent=`${n(filtered.length)} project lines · ${peso(total)} listed allocation; ${n(village.length)} have the weaker village cue (${peso(village.reduce((a,x)=>a+Number(x.amountPesos||0),0))}). Title screens are not ownership findings.`;body.innerHTML=shown.map(x=>`<tr><td>FY${x.year}<br>${esc(x.stage)}</td><td>${esc(x.title)}</td><td>${x.signals.map(esc).join('<br>')}</td><td class="num">${peso(x.amountPesos)}</td><td>${esc(x.source||'Source detail unavailable')}</td></tr>`).join('')||'<tr><td colspan="5">No title-screen matches.</td></tr>';pageLabel.textContent=`${filtered.length?page*size+1:0}–${Math.min((page+1)*size,filtered.length)} of ${filtered.length} · Page ${page+1} of ${pages}`;document.getElementById('mpb-site-prev').disabled=page===0;document.getElementById('mpb-site-next').disabled=page>=pages-1}year.addEventListener('change',()=>{page=0;draw()});search.addEventListener('input',()=>{page=0;draw()});document.getElementById('mpb-site-prev').onclick=()=>{page--;draw()};document.getElementById('mpb-site-next').onclick=()=>{page++;draw()};draw()}).catch(e=>{document.getElementById('mpb-site-summary').textContent='MPB title-screen data unavailable: '+e.message});</script>'''
    page = page.replace('</body>', site_script + '</body>', 1)
    from review_report_language import NOTICE
    from build_investigation_summary import CSS as EVIDENCE_CSS
    page = page.replace('<main>', '<main>' + NOTICE, 1).replace('</head>', EVIDENCE_CSS + '</head>', 1)
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    page = apply_uniform_menu_page(page, 'mpb-historical.html')
    from report_table_presentation import publish_assets, apply_page as apply_report_styles
    page = apply_report_styles(page, publish_assets())
    for path in (STATIC / 'mpb-historical.html', OUT / 'mpb-historical.html'): path.write_text(page, encoding='utf-8')
