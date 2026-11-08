#!/usr/bin/env python3
"""Build a role-comparison page from parsed POW and Development Council evidence."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
ROLE_ORDER = ('Governor', 'Mayor', 'District Engineer', 'Assistant District Engineer', 'Engineer', 'Development Council Chair')
NAME_MERGES = ROOT / 'project_documents' / 'development_council_name_merges.json'
SOURCE_LABELS = {
    'senate hgab · pow': 'Senate HGAB · parsed POW',
    'proposal · pow': 'Proposal · parsed POW',
    'senate hgab · development council': 'Senate HGAB · Development Council',
    'proposal · rdc': 'Proposal · Development Council',
    'proposal · pdc': 'Proposal · Development Council',
    'proposal · ldc': 'Proposal · Development Council',
}


def normalized(value):
    return re.sub(r'[^a-z0-9]+', ' ', str(value or '').casefold()).strip()


def name_key(value):
    value = re.sub(r'^(?:(?:the\s+)?(?:hon(?:ourable|orable)?|gov(?:ernor)?|mayor|engr|eng|attorney|atty|dr)\.?\s+)+', '', str(value or '').strip(), flags=re.I)
    return normalized(value)


def clean_name(value):
    value = re.sub(r'^(?:(?:the\s+)?(?:hon(?:ourable|orable)?|gov(?:ernor)?|mayor|engr|eng|attorney|atty|dr)\.?\s+)+', '', str(value or '').strip(), flags=re.I)
    value = re.sub(r'\s*,\s*(jr\.?|sr\.?|ii|iii|iv)\.?$', r' \1', value, flags=re.I)
    value = re.sub(r'\s+', ' ', value).strip(' ,.')
    value = re.sub(r'\b(jr|sr)\.?$', lambda m: m.group(1).upper()+'.', value, flags=re.I)
    return value.upper()


def load_name_merges():
    data = json.loads(NAME_MERGES.read_text()) if NAME_MERGES.exists() else {'merges': []}
    aliases = {}
    displays = {}
    for item in data.get('merges', []):
        canonical = clean_name(item.get('canonical'))
        canonical_key = name_key(canonical)
        if not canonical_key:
            continue
        displays[canonical_key] = canonical
        for name in [canonical, *item.get('aliases', [])]:
            key = name_key(name)
            if key:
                aliases[key] = canonical_key
                displays[canonical_key] = canonical
    return aliases, displays


def role_group(value):
    value = str(value or '')
    if re.search(r'\bassistant\s+district\s+engineer\b', value, re.I):
        return 'Assistant District Engineer'
    if re.search(r'\bdistrict\s+engineer\b', value, re.I):
        return 'District Engineer'
    if re.search(r'\bengineer\b|\beng(?:r)?\.?\b', value, re.I):
        return 'Engineer'
    if re.search(r'\bgovernor\b', value, re.I):
        return 'Governor'
    if re.search(r'\bmayor\b', value, re.I):
        return 'Mayor'
    return None


def role_groups(value):
    value = str(value or '')
    found = []
    if re.search(r'\bchair(?:person|man)?\b', value, re.I) and re.search(r'\b(?:RDC|PDC|LDC|development\s+council)\b', value, re.I):
        found.append('Development Council Chair')
    for role in ('Governor', 'Mayor', 'District Engineer', 'Assistant District Engineer', 'Engineer'):
        if role_group(value) == role and role not in found:
            found.append(role)
    return found


def build_data():
    source = json.loads((OUT / 'hgab-document-coverage.json').read_text())
    name_aliases, merge_displays = load_name_merges()
    try:
        import build_rcs_analysis
        office_province = {normalized(r['office']): r['province'] for r in build_rcs_analysis.read_rcs_rows()[0] if r.get('province')}
    except Exception:
        office_province = {}
    records = {}
    project_meta = {}
    for project in source.get('projects', []):
        hgab_id = project.get('hgabId')
        if not hgab_id:
            continue
        project_meta[hgab_id] = {
            'hgabId': hgab_id,
            'title': project.get('title') or '',
            'office': project.get('office') or '',
            'region': project.get('region') or '',
            'province': office_province.get(normalized(project.get('office')),
                        'Metropolitan Manila' if (project.get('region') or '').casefold() in ('ncr', 'national capital region') and 'central office' not in (project.get('office') or '').casefold() else ''),
            'amountPesos': int(project.get('amountPesos') or 0),
            'sources': set(),
        }
        for person in project.get('signatories', []):
            sources = {SOURCE_LABELS[s.casefold()] for s in person.get('sources', []) if s.casefold() in SOURCE_LABELS}
            if not sources:
                continue
            raw_name = ' '.join(str(person.get('name') or '').split())
            raw_key = name_key(raw_name)
            if not raw_key:
                continue
            canonical_key = name_aliases.get(raw_key, raw_key)
            name = merge_displays.get(canonical_key, clean_name(raw_name))
            for role in role_groups(person.get('role')):
                key = (hgab_id, canonical_key, role)
                row = records.setdefault(key, {'hgabId': hgab_id, 'name': name, 'role': role, 'sources': set()})
                row['sources'].update(sources)
                project_meta[hgab_id]['sources'].update(sources)
    candidates = []
    per_person = defaultdict(lambda: {'name': None, 'projects': {}, 'sources': set()})
    for (hgab_id, canonical_id, role), row in records.items():
        project = project_meta[hgab_id]
        sources = sorted(row['sources'])
        candidate = {
            'hgabId': hgab_id,
            'name': row['name'],
            'role': role,
            'title': project['title'],
            'office': project['office'],
            'region': project['region'],
            'province': project['province'],
            'amountPesos': project['amountPesos'],
            'sources': sources,
        }
        candidates.append(candidate)
        person_key = canonical_id
        aggregate = per_person[person_key]
        aggregate['name'] = aggregate['name'] or row['name']
        aggregate.setdefault('roles', set()).add(role)
        aggregate['projects'][hgab_id] = {'amountPesos': project['amountPesos'], 'title': project['title'], 'office': project['office'], 'region': project['region'], 'province': project['province']}
        aggregate['sources'].update(sources)
    by_project = defaultdict(list)
    for row in candidates:
        by_project[row['hgabId']].append(row)
    related_roles = {
        'Governor': {'District Engineer', 'Assistant District Engineer', 'Engineer'},
        'Mayor': {'District Engineer', 'Assistant District Engineer', 'Engineer'},
        'Development Council Chair': {'District Engineer', 'Assistant District Engineer', 'Engineer'},
        'District Engineer': {'Governor', 'Mayor', 'Development Council Chair', 'Assistant District Engineer', 'Engineer'},
        'Assistant District Engineer': {'Governor', 'Mayor', 'Development Council Chair', 'District Engineer', 'Engineer'},
        'Engineer': {'Governor', 'Mayor', 'Development Council Chair', 'District Engineer', 'Assistant District Engineer'},
    }
    for row in candidates:
        row['sameProjectSignatories'] = [
            {'name': other['name'], 'role': other['role'], 'sources': other['sources']}
            for other in by_project[row['hgabId']]
            if other is not row and other['role'] in related_roles[row['role']] and name_key(other['name']) != name_key(row['name'])
        ]
    candidates.sort(key=lambda x: (ROLE_ORDER.index(x['role']), -x['amountPesos'], normalized(x['name']), x['hgabId']))
    people = []
    for _, aggregate in per_person.items():
        project_values = list(aggregate['projects'].values())
        people.append({
            'roles': sorted(aggregate['roles'], key=ROLE_ORDER.index),
            'name': aggregate['name'],
            'projectCount': len(project_values),
            'allocationPesos': sum(p['amountPesos'] for p in project_values),
            'projectTitles': sorted({p['title'] for p in project_values if p['title']}),
            'offices': sorted({p['office'] for p in project_values if p['office']}),
            'regions': sorted({p['region'] for p in project_values if p['region']}),
            'provinces': sorted({p['province'] for p in project_values if p['province']}),
            'sources': sorted(aggregate['sources']),
        })
    people.sort(key=lambda x: (-x['projectCount'], -x['allocationPesos'], normalized(x['name'])))
    role_summary = {}
    for role in ROLE_ORDER:
        group = [x for x in candidates if x['role'] == role]
        unique_names = {name_key(x['name']) for x in group}
        rows = group
        role_summary[role] = {
            'uniquePeople': len(unique_names),
            'candidateProjectRows': len(rows),
            'distinctProjects': len({x['hgabId'] for x in rows}),
            'projectAllocationPesos': sum(project_meta[x['hgabId']]['amountPesos'] for x in {r['hgabId']: r for r in rows}.values()),
        }
    included_projects = [p for p in project_meta.values() if p['sources']]
    for p in included_projects:
        p['sources'] = sorted(p['sources'])
    return {
        'title': 'Project signatories · parsed POW and Development Council documents',
        'generatedAtUtc': source.get('generatedAtUtc'),
        'sourceScope': 'HGAB project rows with extracted Governor, Mayor, District Engineer, Assistant District Engineer, other Engineer or Development Council Chair candidates from parsed POW or Development Council documents only. The supplied files are not machine-readable; extraction is best-effort and incomplete, so these results are partial. Names are deduplicated across roles after conservative formatting normalization and reviewed alias merges. Candidate roles and names require source review and do not establish a current office, project sponsor or personal benefit.',
        'extractionLimitations': 'Only parsed and matched POW and Development Council documents are included. The supplied files are not machine-readable; best-effort extraction can miss or misread text, names and roles. Absence from this page does not establish that a person did not sign or that no document exists.',
        'counts': {
            'projectsWithParsedRoleCandidates': len(included_projects),
            'projectsWithRoleCandidates': len({x['hgabId'] for x in candidates}),
            'candidateProjectRows': len(candidates),
            'uniqueCandidates': len(people),
            'byRole': role_summary,
            'sourceProjectRows': {
                source: sum(source in p['sources'] for p in included_projects)
                for source in sorted({source for p in included_projects for source in p['sources']})
            },
        },
        'projects': sorted(included_projects, key=lambda x: (-x['amountPesos'], normalized(x['title']), x['hgabId'])),
        'people': people,
        'candidates': candidates,
    }


MAIN = '''<main class="wrap" id="development-council-main">
<section class="dc-hero"><span class="dc-eyebrow">FY2027 · parsed project documents</span><h2>Who signs the project documents?</h2><p>Compare Governor, Mayor, District Engineer, Assistant District Engineer, other Engineer and Development Council Chair candidates named in matched POW and Development Council documents. A Development Council Chair may also appear as a Governor or Mayor; names are merged across roles. Same-project associations use the HGAB project code and do not prove collaboration, sponsorship or responsibility.</p><div class="dc-metrics"><div><strong id="dc-project-count">—</strong><span>projects with extracted role candidates</span></div><div><strong id="dc-candidate-count">—</strong><span>candidate-project records</span></div><div><strong id="dc-people-count">—</strong><span>distinct names across roles</span></div></div></section>
<section class="panel" id="dc-extraction-limits" role="note"><h2>Scope and extraction limits</h2><p><strong>Only parsed POW and Development Council documents matched to HGAB projects are included.</strong> The supplied files are not machine-readable, so names and roles were recovered through best-effort extraction. Results are partial: extraction may miss or misread text, names or roles. A person or document missing here should not be treated as evidence that they did not sign or that no document exists. Check the source document before relying on an individual result.</p></section>
<section class="panel"><h2>Compare roles</h2><p class="muted">Counts deduplicate candidate names within each role. Project allocations are associated with the document rows and are not personal receipts.</p><div id="dc-role-cards" class="dc-role-cards"></div><div id="dc-role-bars" class="dc-role-bars" aria-label="Candidate project rows by role"></div></section>
<section class="panel"><h2>Candidate rankings by geography</h2><p class="muted">Rank Development Council Chairs or Engineers named in parsed POW or Development Council documents by distinct HGAB project codes or associated allocation, grouped by region, province or DEO. Allocation is the project amount, not a payment to the candidate.</p><div class="filters"><label>Geography <select id="dc-rank-geography"><option value="region">Region</option><option value="province">Province</option><option value="deo">DEO</option></select></label><label>Place <select id="dc-rank-place"></select></label><label>Position <select id="dc-rank-role"><option value="">All roles</option></select></label><label>Rank by <select id="dc-rank-metric"><option value="projectCount">Project count</option><option value="allocationPesos">Associated allocation</option></select></label></div><div id="dc-rank-chart" class="dc-rank-chart" aria-label="Candidate ranking chart"></div></section>
<section class="panel"><h2>All-time candidate rankings</h2><p class="muted">Chair–Engineer pairs are ranked when a project has exactly one distinct candidate in each role. Projects without an unambiguous pair appear in a separate fallback ranking of Chair or Engineer candidates. Each pair or candidate is counted once per HGAB project; allocation is not a payment to a candidate.</p><h3>Chair + Engineer pairs</h3><div class="dc-alltime-grid"><div><h4>Most linked projects</h4><div id="dc-alltime-pairs-projects" class="dc-rank-chart" aria-label="Chair and Engineer pairs ranked by distinct projects"></div></div><div><h4>Largest associated allocation</h4><div id="dc-alltime-pairs-allocation" class="dc-rank-chart" aria-label="Chair and Engineer pairs ranked by associated allocation"></div></div></div><h3>Fallback candidates · no unique pair</h3><div class="dc-alltime-grid"><div><h4>Most linked projects</h4><div id="dc-alltime-singles-projects" class="dc-rank-chart" aria-label="Unpaired Chair or Engineer candidates ranked by distinct projects"></div></div><div><h4>Largest associated allocation</h4><div id="dc-alltime-singles-allocation" class="dc-rank-chart" aria-label="Unpaired Chair or Engineer candidates ranked by associated allocation"></div></div></div></section>
<section class="panel"><h2>Candidate comparison · ranked by linked projects</h2><div class="filters"><label>Position <select id="dc-person-role"><option value="">All roles</option></select></label><label>Search person, office or project <input id="dc-person-search" type="search" placeholder="Name, project, district office, region"></label></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Role</th><th>Candidate</th><th>Linked projects</th><th>Associated project allocations</th><th>Document sources</th></tr></thead><tbody id="dc-person-rows"><tr><td colspan="6">Loading parsed-document candidates…</td></tr></tbody></table></div><div class="pagination"><button id="dc-person-prev" type="button" disabled>Previous</button><span id="dc-person-page"></span><button id="dc-person-next" type="button" disabled>Next</button><label>Rows <select id="dc-person-size"><option>25</option><option selected>50</option><option>100</option></select></label></div></section>
<section class="panel"><h2>Project-level signatory candidates</h2><p class="muted">Only matched POW and Development Council evidence is included. Name variants are normalized and reviewed aliases merged; repeated mentions of one person in the same project and role are deduplicated. Candidates listed together share an HGAB project code; this does not establish collaboration.</p><div class="filters"><label>Position <select id="dc-row-role"><option value="">All roles</option></select></label><label>Document source <select id="dc-source"><option value="">POW and Development Council</option></select></label><label>Region <select id="dc-region"><option value="">All regions</option></select></label><label>Search <input id="dc-row-search" type="search" placeholder="Candidate, project or office"></label></div><p id="dc-row-count" class="muted" aria-live="polite"></p><div class="table-wrap"><table><thead><tr><th>Role</th><th>Candidate</th><th>Same-project signatories · same HGAB code</th><th>Project · HGAB code</th><th>Office · region</th><th>HGAB allocation</th><th>Parsed document source</th></tr></thead><tbody id="dc-candidate-rows"><tr><td colspan="7">Loading rows…</td></tr></tbody></table></div><div class="pagination"><button id="dc-row-prev" type="button" disabled>Previous</button><span id="dc-row-page"></span><button id="dc-row-next" type="button" disabled>Next</button><label>Rows <select id="dc-row-size"><option>25</option><option selected>50</option><option>100</option></select></label></div><p><a href="development-council-data.json" download>Download the filtered project and candidate dataset ↗</a></p></section>
<section class="panel"><h2>Scope and limits</h2><p>Sources are restricted to parsed POW and Development Council document matches associated with HGAB project rows. The role labels are extracted candidates and may reflect an “Officer-in-Charge” designation, OCR variation or a historical signature. They are not a verified current roster. A document signature does not show who proposed, sponsored, approved or benefited from a project. Source file paths and direct Senate file links are not published.</p></section>
</main>'''

STYLE = '''<style id="development-council-style">#development-council-main{width:100%;max-width:none;margin:0;padding:24px clamp(16px,2vw,32px)}.dc-hero{margin:18px 0 22px;padding:clamp(24px,4vw,42px);border-left:8px solid #FCD116;border-radius:16px;background:linear-gradient(120deg,#00246A,#0038A8);color:#fff}.dc-eyebrow{color:#FCD116;font-size:12px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}#development-council-main .dc-hero h2{margin:8px 0;color:#fff!important;font-size:clamp(26px,3vw,42px)}.dc-hero p{max-width:1000px;color:#f5f5f5}.dc-metrics,.dc-role-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:20px}.dc-metrics>div,.dc-role-card{display:flex;flex-direction:column;gap:5px;padding:16px;border:1px solid #ffffff55;border-radius:10px;background:#ffffff12}.dc-metrics strong{color:#FCD116;font-size:clamp(27px,3vw,40px)}.dc-metrics span{font-size:14px}.dc-role-cards{grid-template-columns:repeat(6,minmax(0,1fr));margin:14px 0}.dc-role-card{background:#f5f8fb;border-color:#d7e0e4}.dc-role-card strong{font-size:26px;color:#0038A8}.dc-role-card span,.dc-role-card small{color:#52636d}.dc-role-bars{display:grid;gap:9px;margin:18px 0}.dc-role-bar{display:grid;grid-template-columns:minmax(170px,240px) minmax(100px,1fr) 100px;gap:12px;align-items:center}.dc-role-track{height:18px;border-radius:5px;background:#edf1f4;overflow:hidden}.dc-role-track i{display:block;height:100%;background:#16867b}.dc-role-bar strong{text-align:right;font-variant-numeric:tabular-nums}.dc-rank-chart{display:grid;gap:9px;margin:20px 0}.dc-alltime-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.dc-alltime-grid h4{margin:8px 0;color:#52636d}.dc-rank-row{display:grid;grid-template-columns:minmax(180px,300px) minmax(90px,1fr) minmax(90px,150px);gap:12px;align-items:center}.dc-rank-name{overflow-wrap:anywhere}.dc-rank-track{height:20px;border-radius:5px;background:#edf1f4;overflow:hidden}.dc-rank-track i{display:block;height:100%;background:#16867b}.dc-rank-value{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.dc-source-list{font-size:13px}.dc-source-list small{display:block}@media(max-width:1000px){.dc-role-cards{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:760px){.dc-alltime-grid{grid-template-columns:1fr}.dc-metrics{grid-template-columns:1fr}.dc-role-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.dc-role-bar{grid-template-columns:125px minmax(45px,1fr) 72px;gap:7px;font-size:12px}.dc-rank-row{grid-template-columns:minmax(110px,1.1fr) minmax(50px,1fr) 94px;gap:7px;font-size:12px}}</style>'''

JS = r'''(()=>{'use strict';const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),num=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+num(v),roles=['Governor','Mayor','District Engineer','Assistant District Engineer','Engineer','Development Council Chair'];let data={},personPage=0,rowPage=0;const roleOrder=new Map(roles.map((v,i)=>[v,i]));function page(rows,p,size,label,prev,next,draw){const n=Number(size.value)||50,pages=Math.max(1,Math.ceil(rows.length/n));p.value=Math.max(0,Math.min(p.value,pages-1));const start=p.value*n;label.textContent=rows.length?`Page ${p.value+1} of ${pages} · ${start+1}–${Math.min(start+n,rows.length)} of ${num(rows.length)}`:'No rows';prev.disabled=p.value===0;next.disabled=p.value+1>=pages;return rows.slice(start,start+n)}function personRows(){const q=$('dc-person-search').value.trim().toLocaleLowerCase(),role=$('dc-person-role').value;return(data.people||[]).filter(x=>(!role||(x.roles||[]).includes(role))&&[x.name,...(x.roles||[]),...x.sources,...x.projectTitles,...x.offices,...x.regions].join(' ').toLocaleLowerCase().includes(q)).sort((a,b)=>b.projectCount-a.projectCount||b.allocationPesos-a.allocationPesos||a.name.localeCompare(b.name))}function drawPeople(){const rows=personRows(),shown=page(rows,{get value(){return personPage},set value(v){personPage=v}},$('dc-person-size'),$('dc-person-page'),$('dc-person-prev'),$('dc-person-next'));const offset=personPage*(Number($('dc-person-size').value)||50);$('dc-person-rows').innerHTML=shown.map((x,i)=>'<tr><td>'+(offset+i+1)+'</td><td>'+esc((x.roles||[]).join(', '))+'</td><td><strong>'+esc(x.name)+'</strong></td><td>'+num(x.projectCount)+'</td><td class="amount">'+peso(x.allocationPesos)+'</td><td class="dc-source-list">'+x.sources.map(esc).join('<br>')+'</td></tr>').join('')||'<tr><td colspan="6">No candidates match these filters.</td></tr>'}function candidateRows(){const q=$('dc-row-search').value.trim().toLocaleLowerCase(),role=$('dc-row-role').value,source=$('dc-source').value,region=$('dc-region').value;return(data.candidates||[]).filter(x=>(!role||x.role===role)&&(!source||x.sources.includes(source))&&(!region||x.region===region)&&[x.name,x.title,x.hgabId,x.office,x.region,x.role,...x.sources].join(' ').toLocaleLowerCase().includes(q))}function drawRows(){const rows=candidateRows(),shown=page(rows,{get value(){return rowPage},set value(v){rowPage=v}},$('dc-row-size'),$('dc-row-page'),$('dc-row-prev'),$('dc-row-next'));const offset=rowPage*(Number($('dc-row-size').value)||50);$('dc-row-count').textContent=num(rows.length)+' candidate-project records · '+num(new Set(rows.map(x=>x.hgabId)).size)+' projects';$('dc-candidate-rows').innerHTML=shown.map(x=>'<tr><td>'+esc(x.role)+'</td><td><strong>'+esc(x.name)+'</strong></td><td>'+((x.sameProjectSignatories||[]).map(y=>esc(y.name)+' · '+esc(y.role)).join('<br>')||'—')+'</td><td>'+esc(x.title)+'<small>'+esc(x.hgabId)+'</small></td><td>'+esc(x.office)+(x.region?'<small>'+esc(x.region)+(x.province?' · '+esc(x.province):'')+'</small>':'')+'</td><td class="amount">'+peso(x.amountPesos)+'</td><td class="dc-source-list">'+x.sources.map(esc).join('<br>')+'</td></tr>').join('')||'<tr><td colspan="7">No candidate rows match these filters.</td></tr>'}function drawRank(){const geo=$('dc-rank-geography').value,place=$('dc-rank-place').value,role=$('dc-rank-role').value,metric=$('dc-rank-metric').value,field=geo==='province'?'province':geo==='deo'?'office':'region',map=new Map();for(const x of (data.candidates||[])){if(!x[field]||x[field]!==place||(role==='engineers'?!/Engineer/.test(x.role):role&&x.role!==role))continue;const groupRole=role==='engineers'?'Engineers':x.role,key=(groupRole==='Engineers'?'':x.role+'|')+x.name;if(!map.has(key))map.set(key,{name:x.name,role:groupRole,projects:new Map()});map.get(key).projects.set(x.hgabId,Number(x.amountPesos||0))}const rows=[...map.values()].map(x=>({name:x.name,role:x.role,projectCount:x.projects.size,allocationPesos:[...x.projects.values()].reduce((a,b)=>a+b,0)})).sort((a,b)=>b[metric]-a[metric]||a.name.localeCompare(b.name)).slice(0,25),max=Math.max(1,...rows.map(x=>x[metric]));$('dc-rank-chart').innerHTML=rows.map((x,i)=>'<div class="dc-rank-row"><span class="dc-rank-name">'+(i+1)+'. '+esc(x.name)+' <small>· '+esc(x.role)+'</small></span><div class="dc-rank-track"><i style="width:'+100*x[metric]/max+'%"></i></div><strong class="dc-rank-value">'+(metric==='allocationPesos'?peso(x.allocationPesos):num(x.projectCount)+' projects')+'</strong></div>').join('')||'<p class="muted">No candidates for this geography and position.</p>'}function updatePlaces(){const geo=$('dc-rank-geography').value,field=geo==='province'?'province':geo==='deo'?'office':'region',values=[...new Set((data.candidates||[]).map(x=>x[field]).filter(Boolean))].sort((a,b)=>a.localeCompare(b));$('dc-rank-place').innerHTML=values.map(x=>'<option>'+esc(x)+'</option>').join('');drawRank()}function drawAllTime(){const projects=new Map();for(const x of(data.candidates||[])){if(!projects.has(x.hgabId))projects.set(x.hgabId,{amount:Number(x.amountPesos||0),chairs:new Set(),engineers:new Set()});const p=projects.get(x.hgabId);if(x.role==='Development Council Chair')p.chairs.add(x.name);else if(/Engineer/.test(x.role))p.engineers.add(x.name)}const pairs=new Map(),singles=new Map(),add=(store,key,label,role,id,amount)=>{if(!store.has(key))store.set(key,{label,role,projects:new Map()});store.get(key).projects.set(id,amount)};for(const[id,p]of projects){const chairs=[...p.chairs],engineers=[...p.engineers];if(chairs.length===1&&engineers.length===1&&chairs[0]!==engineers[0]){const c=chairs[0],e=engineers[0];add(pairs,c+'|'+e,c+' ↔ '+e,'Chair + Engineer',id,p.amount);continue}for(const name of new Set([...chairs,...engineers])){const chair=p.chairs.has(name),engineer=p.engineers.has(name),role=chair&&engineer?'Chair / Engineer':chair?'Development Council Chair':'Engineer';add(singles,role+'|'+name,name,role,id,p.amount)}}const rows=store=>[...store.values()].map(x=>({label:x.label,role:x.role,projectCount:x.projects.size,allocationPesos:[...x.projects.values()].reduce((a,b)=>a+b,0)})),draw=(host,items,field,format,empty)=>{const ranked=[...items].sort((a,b)=>b[field]-a[field]||a.label.localeCompare(b.label)).slice(0,25),max=Math.max(1,...ranked.map(x=>Number(x[field]||0)));$(host).innerHTML=ranked.map((x,i)=>'<div class="dc-rank-row"><span class="dc-rank-name">'+(i+1)+'. '+esc(x.label)+' <small>· '+esc(x.role)+'</small></span><div class="dc-rank-track"><i style="width:'+100*Number(x[field]||0)/max+'%"></i></div><strong class="dc-rank-value">'+esc(format(x[field]))+'</strong></div>').join('')||'<p class="muted">'+esc(empty)+'</p>'};const paired=rows(pairs),fallback=rows(singles);draw('dc-alltime-pairs-projects',paired,'projectCount',v=>num(v)+' projects','No unambiguous Chair–Engineer pairs were found.');draw('dc-alltime-pairs-allocation',paired,'allocationPesos',peso,'No unambiguous Chair–Engineer pairs were found.');draw('dc-alltime-singles-projects',fallback,'projectCount',v=>num(v)+' projects','No unpaired Chair or Engineer candidates were found.');draw('dc-alltime-singles-allocation',fallback,'allocationPesos',peso,'No unpaired Chair or Engineer candidates were found.')}function fillRoleSelect(id){$(id).innerHTML='<option value="">All roles</option>'+roles.map(x=>'<option>'+esc(x)+'</option>').join('')}function init(d){data=d;const c=d.counts||{};$('dc-project-count').textContent=num(c.projectsWithRoleCandidates);$('dc-candidate-count').textContent=num(c.candidateProjectRows);$('dc-people-count').textContent=num(c.uniqueCandidates);$('dc-role-cards').innerHTML=roles.map(role=>{const x=c.byRole?.[role]||{};return'<div class="dc-role-card"><span>'+esc(role)+'</span><strong>'+num(x.uniquePeople)+' people</strong><small>'+num(x.candidateProjectRows)+' candidate-project rows · '+num(x.distinctProjects)+' projects</small></div>'}).join('');const max=Math.max(1,...roles.map(r=>Number(c.byRole?.[r]?.candidateProjectRows||0)));$('dc-role-bars').innerHTML=roles.map(r=>'<div class="dc-role-bar"><span>'+esc(r)+'</span><div class="dc-role-track"><i style="width:'+100*Number(c.byRole?.[r]?.candidateProjectRows||0)/max+'%"></i></div><strong>'+num(c.byRole?.[r]?.candidateProjectRows)+' rows</strong></div>').join('');fillRoleSelect('dc-person-role');fillRoleSelect('dc-row-role');const sources=[...new Set((d.candidates||[]).flatMap(x=>x.sources))].sort();$('dc-source').innerHTML='<option value="">POW and Development Council</option>'+sources.map(x=>'<option>'+esc(x)+'</option>').join('');const regions=[...new Set((d.candidates||[]).map(x=>x.region).filter(Boolean))].sort((a,b)=>a.localeCompare(b));$('dc-region').innerHTML='<option value="">All regions</option>'+regions.map(x=>'<option>'+esc(x)+'</option>').join('');for(const id of ['dc-person-role','dc-person-search'])$(id).addEventListener(id.endsWith('search')?'input':'change',()=>{personPage=0;drawPeople()});$('dc-person-size').onchange=()=>{personPage=0;drawPeople()};$('dc-person-prev').onclick=()=>{personPage--;drawPeople()};$('dc-person-next').onclick=()=>{personPage++;drawPeople()};for(const id of ['dc-row-role','dc-source','dc-region','dc-row-search'])$(id).addEventListener(id.endsWith('search')?'input':'change',()=>{rowPage=0;drawRows()});$('dc-row-size').onchange=()=>{rowPage=0;drawRows()};$('dc-row-prev').onclick=()=>{rowPage--;drawRows()};$('dc-row-next').onclick=()=>{rowPage++;drawRows()};$('dc-rank-role').innerHTML='<option value="">All roles</option><option value="Development Council Chair">Development Council Chair</option><option value="engineers">Engineers · DE/ADE/other</option>'+roles.filter(x=>x!=='Development Council Chair'&&x!=='Engineer').map(x=>'<option>'+esc(x)+'</option>').join('');$('dc-rank-geography').onchange=updatePlaces;$('dc-rank-place').onchange=drawRank;$('dc-rank-role').onchange=drawRank;$('dc-rank-metric').onchange=drawRank;updatePlaces();drawAllTime();drawPeople();drawRows()}fetch('development-council-data.json?v=__DATA_VERSION__').then(r=>{if(!r.ok)throw Error('Development Council evidence unavailable ('+r.status+')');return r.json()}).then(init).catch(e=>{document.getElementById('dc-candidate-rows').innerHTML='<tr><td colspan="6">'+esc(e.message)+'</td></tr>';console.error(e)})})();'''


def build_page(data_version):
    congress = (STATIC / 'congress.html').read_text()
    congress = re.sub(r'<script\b[^>]*>.*?</script>', '', congress, flags=re.S)
    main = congress.find('<main')
    if main < 0:
        raise RuntimeError('congress.html does not contain a main section')
    prefix = congress[:main]
    prefix = re.sub(r'<title>.*?</title>', '<title>Development Council · project signatory candidates</title>', prefix, count=1, flags=re.S)
    prefix = re.sub(r'<h1>.*?</h1>', '<h1>Development Council · project signatories</h1>', prefix, count=1, flags=re.S)
    prefix = re.sub(r'(<header\b.*?<h1>.*?</h1>)\s*<p>.*?</p>', r'\1<p>Compare Governor, Mayor, District Engineer, Assistant District Engineer and Development Council Chair candidates extracted from parsed POW and Development Council documents.</p>', prefix, count=1, flags=re.S)
    prefix = prefix.replace('</head>', STYLE + '</head>', 1)
    footer = '''<footer class="site-ai-credit"><p><strong>Evidence scope and limitations:</strong> only parsed POW and Development Council documents matched to HGAB project rows are included. The supplied files are not machine-readable; best-effort extraction is partial and can miss or misread names and roles. Candidate names and roles require verification against source pages and do not establish sponsorship, responsibility or personal benefit.</p><p>Source file paths and direct Senate file links are withheld. Local data export contains only project metadata, candidate names, role labels and document type labels.</p></footer>'''
    html = prefix + MAIN + footer + '<script src="development-council.js?v=' + data_version + '"></script></body></html>'
    sys.path.insert(0, str(ROOT))
    import uniform_report_menu
    html = uniform_report_menu.apply_page(html, 'development-council.html')
    from report_table_presentation import apply_page_table_module
    html,_=apply_page_table_module('development-council.html',html)
    return html


def publish_menu_links():
    sys.path.insert(0, str(ROOT))
    import uniform_report_menu
    import importlib
    uniform_report_menu = importlib.reload(uniform_report_menu)
    for root in (STATIC, OUT):
        for path in root.rglob('*.html'):
            text = path.read_text(errors='ignore')
            if not re.search(r'<nav\b[^>]*class="report-nav"', text):
                continue
            relative = path.relative_to(root)
            nav = uniform_report_menu.page_nav(relative)
            text = re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>', lambda _m: nav, text, count=1, flags=re.S)
            path.write_text(text)


def main():
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    version = hashlib.sha256(payload.encode()).hexdigest()[:12]
    js = JS.replace('__DATA_VERSION__', version)
    for root in (OUT, STATIC):
        (root / 'development-council-data.json').write_text(payload)
        (root / 'development-council.js').write_text(js)
        (root / 'development-council.html').write_text(build_page(version))
    publish_menu_links()
    print(json.dumps(data['counts'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
