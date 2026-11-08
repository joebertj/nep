#!/usr/bin/env python3
"""Build the historical named-barangay allocation view as separate data and HTML."""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
OUT = ROOT / 'analysis_output'
INTEGRATED = STATIC / 'integrated-project-data.json'
MPB = ROOT / 'analysis_output' / 'mpb-barangay-data.json'
PAGE = 'barangay-historical.html'
DATA = 'barangay-historical-data.json'

from build_barangay_allocations import BARANGAY, GENERIC, clean_name, context_for
from uniform_report_menu import apply_page
from report_json_shards import write_sharded_json, attach_loader

NORMALIZE = re.compile(r'[^a-z0-9]+')
REMOVE_FACILITY = re.compile(r'\s+(?:Health Station|Health Center|Health Centre|Covered Court|Multi[- ]Purpose Building|Hall|FMR)$', re.I)


def norm(value: str) -> str:
    return NORMALIZE.sub(' ', str(value or '').casefold()).strip()


def main():
    integrated = json.loads(INTEGRATED.read_text(encoding='utf-8'))
    mpb = json.loads(MPB.read_text(encoding='utf-8'))
    grouped: dict[tuple[str, str], dict] = {}

    def add(place_name, locality, region, record):
        key = (norm(place_name), norm(locality))
        if not key[0]:
            return
        place = grouped.setdefault(key, {
            'barangay': place_name, 'localityContext': locality, 'region': region or '',
            'projects': {}, 'officeExamples': set(),
        })
        place['projects'][record['id']] = record
        if record.get('office'):
            place['officeExamples'].add(record['office'])

    # Non-MPB project families are taken from the classified historical district
    # series. MPBs are replaced below with the broader official-barangay matcher.
    non_mpb_rows = 0
    for index, row in enumerate(integrated.get('projects', [])):
        year = int(row.get('year') or 0)
        if not (2015 <= year <= 2026) or row.get('stage') != 'GAA':
            continue
        if row.get('category') == 'Multi-purpose building':
            continue
        title = str(row.get('name') or '')
        matches = list(BARANGAY.finditer(title))
        if not matches:
            continue
        names = []
        for match in matches:
            name = REMOVE_FACILITY.sub('', clean_name(match.group(1)), count=1).strip()
            if (not name or name.casefold() in GENERIC or len(name) < 2
                    or re.fullmatch(r'\d+', name)
                    or re.fullmatch(r'(?i)(?:no\.?|various|different|selected|identified|several)\s+barangays?', name)):
                continue
            if name not in names:
                names.append(name)
        if not names:
            continue
        district_hint = str(row.get('districtId') or '')
        locality = context_for(title, matches, names, '', district_hint)
        record_id = hashlib.sha1(f"GAA|{year}|{index}|{title}|{row.get('source')}".encode()).hexdigest()[:18]
        record = {
            'id': record_id, 'year': year, 'stage': 'GAA',
            'projectName': title, 'category': row.get('category') or '',
            'amountPesos': int(row.get('amountPesos') or 0),
            'office': '', 'source': row.get('source') or f'FY{year} DPWH GAA',
            'districtId': district_hint, 'locationBasis': 'Barangay title parse · unique-district historical series',
        }
        non_mpb_rows += 1
        for name in names:
            add(name, locality, '', record)

    # The dedicated MPB layer resolves official barangay identities and includes
    # rows without a unique legislative-district assignment. Keep full amounts
    # under each named barangay; place totals therefore overlap for shared lines.
    mpb_links = 0
    for place in mpb.get('barangays', []):
        locality = ', '.join(x for x in (place.get('municipality'), place.get('province')) if x)
        for row in place.get('projects', []):
            year = int(row.get('year') or 0)
            if not (2015 <= year <= 2026) or row.get('stage') != 'GAA':
                continue
            project_index = row.get('projectIndex')
            record_id = f"MPB:{year}:{project_index if project_index is not None else row.get('sourceId') or norm(row.get('name'))}"
            record = {
                'id': record_id, 'year': year, 'stage': 'GAA',
                'projectName': row.get('name') or '', 'category': 'Multi-purpose building',
                'amountPesos': int(row.get('amountPesos') or 0),
                'office': row.get('office') or '', 'source': row.get('source') or f'FY{year} DPWH GAA MPB candidate',
                'districtId': '', 'locationBasis': 'official barangay matcher',
            }
            add(str(place.get('barangay') or ''), locality, str(place.get('region') or ''), record)
            mpb_links += 1

    places = []
    for item in grouped.values():
        projects = sorted(item['projects'].values(), key=lambda r: (-r['year'], -r['amountPesos'], r['projectName'].casefold()))
        years = sorted({r['year'] for r in projects})
        places.append({
            'barangay': item['barangay'], 'localityContext': item['localityContext'], 'region': item['region'],
            'officeExamples': sorted(item['officeExamples']), 'years': years,
            'projectCount': len(projects), 'allocationPesos': sum(r['amountPesos'] for r in projects),
            'projects': projects,
        })
    places.sort(key=lambda r: (-r['allocationPesos'], -r['projectCount'], r['barangay'].casefold(), r['localityContext'].casefold()))
    integrated_coverage = [r for r in integrated.get('coverage', []) if 2015 <= int(r.get('year') or 0) <= 2026]
    mpb_periods = [r for r in mpb.get('periods', []) if 2015 <= int(r.get('year') or 0) <= 2026]
    records = {r['id']: r for place in places for r in place['projects']}
    payload = {
        'title': 'Historical DPWH project allocations associated with named barangays',
        'source': 'Integrated historical DPWH project-family series and official-barangay MPB series, FY2015–FY2026',
        'years': sorted({year for place in places for year in place['years']}),
        'summary': {
            'barangayPlaceCount': len(places), 'projectPlaces': sum(p['projectCount'] for p in places),
            'uniqueProjectRows': len(records), 'allocationAcrossBarangayPlacesPesos': sum(p['allocationPesos'] for p in places),
            'nonMpbTitleParsedRows': non_mpb_rows, 'mpbOfficialBarangayLinks': mpb_links,
            'caveat': 'A line naming multiple barangays is associated with each named place at its full allocation; place totals overlap. Non-MPB rows are limited to uniquely assigned rows in the district historical series and use title-parsed locality context. MPB rows use the separate official-barangay matcher. Allocations are not payments or verified construction.',
        },
        'coverage': {'districtSeries': integrated_coverage, 'mpbSeries': mpb_periods},
        'places': places,
    }
    serialized = json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n'
    for path in (STATIC / DATA, OUT / DATA):
        path.write_text(serialized, encoding='utf-8')
        write_sharded_json(path, payload)
    data_version = hashlib.sha256((STATIC / DATA).read_bytes()).hexdigest()[:12]

    template = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Barangay Historical · DPWH GAA</title><style>
main{width:100%;padding:24px clamp(16px,2vw,32px)}section{margin:18px 0;padding:22px;background:#fff;border:1px solid #d7e0e8;border-radius:14px}.lede,.note{color:#52616f}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.stat{padding:14px;background:#eef4fa;border-left:4px solid #0038a8;border-radius:8px}.stat strong{display:block;color:#0038a8;font-size:24px}.toolbar{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin:12px 0}.toolbar label{display:grid;gap:4px;font-weight:650}.toolbar input,.toolbar select{padding:10px;border:1px solid #aebdca;border-radius:8px;font:inherit}.toolbar input{min-width:min(360px,75vw)}button{padding:7px 10px;border:1px solid #0038a8;border-radius:7px;background:#fff;color:#0038a8;font:inherit;font-weight:650;cursor:pointer}.bars{display:grid;gap:8px}.bar{display:grid;grid-template-columns:minmax(160px,260px) minmax(80px,1fr) auto;gap:10px;align-items:center}.bar-label{overflow-wrap:anywhere;font-size:14px}.track{height:14px;border-radius:99px;background:#e8edf2;overflow:hidden}.fill{height:100%;background:#0038a8;border-radius:99px}.bar-value{font-size:13px;font-weight:700;white-space:nowrap}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px;table-layout:fixed}th,td{padding:9px;border-bottom:1px solid #dce3e8;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#edf3f8;color:#233f5b}td.amount,th.amount{text-align:right;white-space:nowrap}.pages{display:flex;gap:12px;align-items:center;justify-content:flex-end;margin-top:12px}.disclaimer{border-left:4px solid #fcd116;background:#fffdf0;padding:14px 18px;color:#37424b;font-size:14px}.project-list small{display:block;color:#586575}.hidden{display:none!important}@media(max-width:700px){.stats{grid-template-columns:1fr}.bar{grid-template-columns:minmax(110px,1.2fr) minmax(60px,1fr)}.bar-value{grid-column:2;text-align:right}}
</style></head><body><header><div class="eyebrow">BetterGov · Budget research</div><h1>Barangay Historical</h1><p>Explore named DPWH project allocations across available historical GAA years, FY2015–FY2026.</p></header><main>
<section class="disclaimer"><strong>Scope.</strong> Non-MPB records use classified project-family rows with a unique district assignment, then parse barangay names and printed locality from titles. MPB records use the separate official-barangay matcher and include lines without unique district assignments. Some projects name multiple barangays; each place receives the full line amount, so place totals overlap. Title parsing does not verify the construction site, and allocations are not payments.</section>
<section><h2>Coverage</h2><p class="lede" id="coverage"></p><div class="stats"><div class="stat"><span>Barangay-place labels</span><strong id="places">—</strong></div><div class="stat"><span>Project/place associations</span><strong id="associations">—</strong></div><div class="stat"><span>Distinct source rows</span><strong id="projects">—</strong></div></div></section>
<section><h2>Top barangay-place allocations</h2><p class="note">Ranked amounts are associated allocations. They overlap when a project names multiple places.</p><div class="toolbar"><label>Fiscal year<select id="year"><option value="all">All years</option></select></label><label>Search barangay or locality<input id="search" type="search" placeholder="Barangay, municipality, province"></label><button id="export">Export filtered CSV</button></div><div id="chart" class="bars" role="img" aria-label="Top historical barangay-place allocations"></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Barangay</th><th>Printed locality / official identity</th><th>Years</th><th>Project rows</th><th class="amount">Associated allocation</th><th>Projects</th></tr></thead><tbody id="rows"></tbody></table></div><div class="pages"><button id="prev">Previous</button><span id="page"></span><button id="next">Next</button></div></section>
<section id="selected" class="hidden"><h2 id="selected-title"></h2><p id="selected-note" class="note"></p><div class="table-wrap"><table class="project-list"><thead><tr><th>Project title</th><th>Fiscal year</th><th>Category</th><th>Source / assignment</th><th class="amount">Allocation</th></tr></thead><tbody id="project-rows"></tbody></table></div></section>
</main><script>
(async()=>{const D=await fetch('barangay-historical-data.json?v=__VERSION__').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}),$=id=>document.getElementById(id),peso=n=>'₱'+Number(n||0).toLocaleString('en-PH'),num=n=>Number(n||0).toLocaleString('en-PH'),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let page=0,filtered=[],selected=null;const size=50;for(const y of D.years){const o=document.createElement('option');o.value=y;o.textContent='FY'+y+' GAA';$('year').append(o)}
function draw(){const y=$('year').value,q=$('search').value.trim().toLowerCase();filtered=D.places.filter(p=>(y==='all'||p.years.includes(Number(y)))&&[p.barangay,p.localityContext,p.region,...p.officeExamples].join(' ').toLowerCase().includes(q)).map(p=>{const projects=p.projects.filter(r=>y==='all'||r.year===Number(y));return {...p,shownProjects:projects,shownCount:projects.length,shownAmount:projects.reduce((a,r)=>a+Number(r.amountPesos||0),0)}}).filter(p=>p.shownCount).sort((a,b)=>b.shownAmount-a.shownAmount);const pages=Math.max(1,Math.ceil(filtered.length/size));page=Math.min(page,pages-1);const visible=filtered.slice(page*size,(page+1)*size),max=Math.max(1,...filtered.slice(0,20).map(p=>p.shownAmount));$('chart').innerHTML=filtered.slice(0,20).map(p=>'<div class="bar"><span class="bar-label">'+esc(p.barangay)+' · '+esc(p.localityContext)+'</span><div class="track"><div class="fill" style="width:'+Math.max(1,100*p.shownAmount/max)+'%"></div></div><span class="bar-value">'+peso(p.shownAmount)+'</span></div>').join('')||'<p>No barangay-place records match.</p>';$('rows').innerHTML=visible.map(p=>{const rank=filtered.indexOf(p)+1;return '<tr><td>'+num(rank)+'</td><td><strong>'+esc(p.barangay)+'</strong></td><td>'+esc(p.localityContext)+(p.region?'<small>'+esc(p.region)+'</small>':'')+'</td><td>'+esc(p.years.filter(v=>y==='all'||v===Number(y)).map(v=>'FY'+v).join(', '))+'</td><td>'+num(p.shownCount)+'</td><td class="amount">'+peso(p.shownAmount)+'</td><td><button data-place="'+rank+'">Projects</button></td></tr>'}).join('')||'<tr><td colspan="7">No matches.</td></tr>';$('page').textContent='Page '+(page+1)+' of '+pages+' · '+num(filtered.length)+' place labels';$('prev').disabled=page===0;$('next').disabled=page>=pages-1;$('rows').querySelectorAll('[data-place]').forEach(b=>b.onclick=()=>show(filtered[Number(b.dataset.place)-1]))}
function show(p){selected=p;$('selected').classList.remove('hidden');$('selected-title').textContent='Projects associated with '+p.barangay+' · '+p.localityContext;$('selected-note').textContent=num(p.shownCount)+' project rows · '+peso(p.shownAmount)+' associated allocation. Full project amounts may appear under multiple places.';$('project-rows').innerHTML=p.shownProjects.map(r=>'<tr><td>'+esc(r.projectName)+'<small>'+esc(r.id)+'</small></td><td>FY'+r.year+'</td><td>'+esc(r.category)+'</td><td>'+esc(r.source)+'<small>'+esc(r.locationBasis)+'</small></td><td class="amount">'+peso(r.amountPesos)+'</td></tr>').join('');$('selected').scrollIntoView({behavior:'smooth',block:'start'})}
function csv(){const rows=[['year','barangay','localityContext','projectName','category','amountPesos','source','locationBasis']];for(const p of filtered)for(const r of p.shownProjects)rows.push([r.year,p.barangay,p.localityContext,r.projectName,r.category,r.amountPesos,r.source,r.locationBasis]);const content=rows.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\\r\\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\\ufeff'+content],{type:'text/csv;charset=utf-8'}));a.download='barangay-historical-project-allocations.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
const c=D.coverage.districtSeries,m=D.coverage.mpbSeries;$('places').textContent=num(D.summary.barangayPlaceCount);$('associations').textContent=num(D.summary.projectPlaces);$('projects').textContent=num(D.summary.uniqueProjectRows);$('coverage').textContent='FY2015–FY2026. The district-family series provides '+num(c.reduce((a,r)=>a+r.assignedRows,0))+' uniquely district-assigned classified non-MPB lines across the available years; '+num(D.summary.nonMpbTitleParsedRows)+' rows with parsed barangay mentions are shown. The official MPB series contributes '+num(D.summary.mpbOfficialBarangayLinks)+' linked GAA barangay/project associations. District-family coverage by year and MPB coverage are recorded in the separate dataset.';$('year').onchange=()=>{page=0;draw()};$('search').oninput=()=>{page=0;draw()};$('prev').onclick=()=>{page--;draw()};$('next').onclick=()=>{page++;draw()};$('export').onclick=csv;draw()})().catch(e=>{document.querySelector('main').insertAdjacentHTML('afterbegin','<p class="disclaimer">Historical barangay data could not be loaded: '+String(e.message)+'</p>')});
</script></body></html>'''.replace('__VERSION__', data_version)
    page = apply_page(template, PAGE)
    page = attach_loader(page, PAGE)
    page = page.replace("fetch('barangay-historical-data.json?v=" + data_version + "')", "window.loadReportShardedJson('barangay-historical-data-index.json?v=" + data_version + "')")
    from report_table_presentation import apply_page_table_module
    page,_=apply_page_table_module(PAGE,page)
    page = '\n'.join(line.rstrip() for line in page.splitlines()) + '\n'
    for path in (STATIC / PAGE, OUT / PAGE):
        path.write_text(page, encoding='utf-8')
    print(json.dumps({'page': PAGE, 'data': DATA, **payload['summary']}, indent=2))


if __name__ == '__main__':
    main()
