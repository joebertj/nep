#!/usr/bin/env python3
"""Publish NEP-only line-item removal candidates by domestic/FAP scope."""
import json
import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from hgab_matching import is_fap, title_key, compatible

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def reverse_screen(mapping):
    """Do not count a NEP line as absent if an HGAB scope counterpart is plausible."""
    hgab = [p['hgab'] for p in mapping['pairs']] + mapping['hgabWithoutSelectedCounterpart']
    exact=defaultdict(set); inverted=defaultdict(set); variants=[]
    stop={'construction','rehabilitation','improvement','road','bridge','barangay','city','municipality','province','along','system','of','the','and','in','to','multi','purpose','building','flood','control'}
    for j,row in enumerate(hgab):
        keys={title_key(row),title_key(row,row.get('sourceTitle'))};variants.append(keys)
        for key in keys:
            exact[key].add(j)
            for token in set(key.split())-stop:inverted[token].add(j)
    hints={}
    for i,row in enumerate(mapping['nepWithoutSelectedCounterpart']):
        keys={title_key(row),title_key(row,row.get('officialNepTitle'))}
        candidates=set().union(*(exact.get(key,set()) for key in keys))
        candidates={j for j in candidates if is_fap(row)==is_fap(hgab[j]) and compatible(row,hgab[j])}
        if candidates:
            j=min(candidates);score=1.
        else:
            votes=Counter()
            tokens=set().union(*(set(k.split())-stop for k in keys))
            for token in sorted(tokens,key=lambda t:(len(inverted.get(t,[])),t))[:16]:
                for j in inverted.get(token,[]):votes[j]+=1
            score=0.;j=None
            for candidate,_ in votes.most_common(80):
                if is_fap(row)!=is_fap(hgab[candidate]) or not compatible(row,hgab[candidate]):continue
                value=max(SequenceMatcher(None,left,right,autojunk=False).ratio() for left in keys for right in variants[candidate])
                if value>score:score=value;j=candidate
        if score>=.83:
            hints[row['sourceNepId']]={'hgabId':hgab[j]['id'],'hgabTitle':hgab[j]['projectName'],'similarity':score,
                                      'reason':'Plausible counterpart exists but was not selected one-to-one; excluded from removal shortlist.'}
        if i and i%200==0:print(f'Reverse-screened {i:,} unpaired NEP lines',flush=True)
    return hints


def build_scope(mapping, foreign, hints):
    rows = []
    for old in sorted(mapping['nepWithoutSelectedCounterpart'], key=lambda r:r['amountPesos'], reverse=True):
        if is_fap(old) != foreign or old['sourceNepId'] in hints: continue
        rows.append({'status': 'Unpaired NEP line · removal review', 'basis': 'No selected counterpart; not a confirmed deletion',
                     'nepId': old['sourceNepId'], 'hgabId': '', 'nepTitle': old['projectName'], 'hgabTitle': '',
                     'nepPesos': old['amountPesos'], 'hgabPesos': None, 'deltaPesos': None,
                     'office': old.get('office',''), 'nepPage': old.get('sourcePage'), 'hgabPage': None,
                     'hgabVolume': None, 'similarity': None})
    linked_count = sum(is_fap(p['nep']) == foreign for p in mapping['pairs'])
    return {'rows': rows, 'summary': {
        'unpairedNepRows': len(rows),
        'unpairedNepAllocationPesos': sum(r['nepPesos'] for r in rows),
        'pairedNepRows': linked_count,
        'heldOutPlausibleCounterparts':sum(is_fap(r)==foreign and r['sourceNepId'] in hints for r in mapping['nepWithoutSelectedCounterpart']),
        'method': 'Removals are NEP line items without HGAB counterparts, not allocation decreases on retained projects. Unpaired records remain removal review candidates; renaming, segmentation and unresolved matches can obscure continued projects. The displayed cost is their NEP allocation, not a certified budget reduction.'}}



def section(key, group):
    s=group['summary']; label='Foreign assisted' if key=='fap' else 'Domestic'
    maximum=max(s['pairedNepRows'],s['unpairedNepRows'],s['heldOutPlausibleCounterparts'],1)
    bars=''.join(f'<text x="0" y="{28+i*65}">{name}</text><rect x="180" y="{10+i*65}" width="{value/maximum*480:.2f}" height="26" fill="{color}"/><text x="180" y="{54+i*65}">{value:,} lines</text>' for i,(name,value,color) in enumerate([('Selected counterparts',s['pairedNepRows'],'#087e78'),('Removal candidates',s['unpairedNepRows'],'#a65b08')]))
    return f'''<section class="card section" id="subtractions-{key}"><h2>Potential removals · {label.lower()} NEP-only line items</h2>
<p class="sub"><strong>{s['unpairedNepRows']:,} NEP lines have no selected or plausible HGAB counterpart</strong>, carrying <strong>₱{s['unpairedNepAllocationPesos']/1e9:,.3f}B</strong> in NEP allocations. The reverse title screen holds out another {s['heldOutPlausibleCounterparts']:,} lines with compatible counterparts scoring at least 83%. These are candidates for line-item removal, pending scope verification. A lower allocation on a retained project is not a removal. Renaming and segmentation may conceal a counterpart; absence from this matching result does not certify deletion.</p>
<svg viewBox="0 0 720 145" style="display:block;width:100%;max-height:190px;font:15px sans-serif" role="img" aria-label="{label} NEP lines with and without selected HGAB counterparts">{bars}</svg>
<div class="toolbar"><input type="search" id="sub-search-{key}" placeholder="Search project, office or source ID"><select id="sub-filter-{key}"><option value="amount">Largest NEP allocation</option><option value="name">Project name</option></select><button class="export-btn" id="sub-csv-{key}" type="button">Export filtered CSV</button></div>
<div class="tablewrap"><table><thead><tr><th>Status</th><th>NEP project</th><th>NEP allocation</th><th>Implementing office</th><th>NEP source</th></tr></thead><tbody id="sub-body-{key}"></tbody></table></div><div class="pagination"><button id="sub-prev-{key}" type="button">Previous</button><span id="sub-page-{key}"></span><button id="sub-next-{key}" type="button">Next</button></div></section>'''



SCRIPT=r'''<script id="subtractions-script">
(()=>{const money=v=>v==null?'Unknown':'₱'+Number(v).toLocaleString('en-PH'),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
fetch('dpwh-data.json').then(r=>{if(!r.ok)throw Error('Could not load removal data');return r.json()}).then(D=>{for(const key of ['domestic','fap']){const rows=D.removals[key].rows,search=document.getElementById('sub-search-'+key),filter=document.getElementById('sub-filter-'+key);let page=0;
const selected=()=>rows.filter(r=>Object.values(r).join(' ').toLowerCase().includes(search.value.trim().toLowerCase())).sort((a,b)=>filter.value==='name'?a.nepTitle.localeCompare(b.nepTitle):b.nepPesos-a.nepPesos);
const draw=()=>{const data=selected(),pages=Math.max(1,Math.ceil(data.length/25));page=Math.max(0,Math.min(page,pages-1));document.getElementById('sub-body-'+key).innerHTML=data.slice(page*25,page*25+25).map(r=>`<tr><td>${esc(r.status)}</td><td>${esc(r.nepTitle)}</td><td>${money(r.nepPesos)}</td><td>${esc(r.office)}</td><td>NEP p.${esc(r.nepPage??'Unknown')}<br>${esc(r.nepId)}</td></tr>`).join('')||'<tr><td colspan="5">No records in this view.</td></tr>';document.getElementById('sub-page-'+key).textContent=`${data.length? page*25+1:0}–${Math.min(page*25+25,data.length)} of ${data.length}`;document.getElementById('sub-prev-'+key).disabled=page===0;document.getElementById('sub-next-'+key).disabled=page>=pages-1};
search.oninput=filter.onchange=()=>{page=0;draw()};document.getElementById('sub-prev-'+key).onclick=()=>{page--;draw()};document.getElementById('sub-next-'+key).onclick=()=>{page++;draw()};document.getElementById('sub-csv-'+key).onclick=()=>{const cols=['status','basis','nepId','nepTitle','nepPesos','office','nepPage'],csv=[cols,...selected().map(r=>cols.map(k=>r[k]??''))].map(row=>row.map(v=>'"'+String(v).replaceAll('"','""')+'"').join(',')).join('\r\n'),url=URL.createObjectURL(new Blob(['\ufeff',csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='dpwh_'+key+'_removals_3rd.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};draw()}}).catch(e=>{for(const key of ['domestic','fap'])document.getElementById('sub-body-'+key).innerHTML='<tr><td colspan="5">'+esc(e.message)+'</td></tr>'});})();
</script>'''


def refresh():
    mapping=json.loads((ROOT/'analysis_output/hb_nep_comparison_3rd_mapping.json').read_text())
    hints=reverse_screen(mapping)
    groups={key:build_scope(mapping,key=='fap',hints) for key in ['domestic','fap']}
    path=STATIC/'dpwh-data.json';data=json.loads(path.read_text());data.pop('subtractions', None);data['removals']=groups
    path.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n')
    (ROOT/'analysis_output/dpwh_removals_3rd.json').write_text(json.dumps(groups,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'analysis_output/dpwh_removals_held_out.json').write_text(json.dumps(hints,ensure_ascii=False,indent=2)+'\n')
    for name in ['dpwh.html','dpwh-hgab.html']:
        path=STATIC/name;page=path.read_text()
        page=re.sub(r'<section class="card section" id="subtractions-(?:domestic|fap)">.*?</section>','',page,flags=re.S)
        page=re.sub(r'<script id="subtractions-script">.*?</script>','',page,flags=re.S)
        page,n=re.subn(r'(<section id="hgab-insertion".*?</section>)',lambda m:m[1]+section('domestic',groups['domestic']),page,count=1,flags=re.S)
        if n!=1:raise ValueError('Missing additions section: '+name)
        page,n=re.subn(r'(<section class="card section" id="foreign-assisted-review">.*?</section>)',lambda m:m[1]+section('fap',groups['fap']),page,count=1,flags=re.S)
        if n!=1:raise ValueError('Missing FAP section: '+name)
        path.write_text(page.replace('</body>',SCRIPT+'</body>',1))
    print(json.dumps({key:group['summary'] for key,group in groups.items()},indent=2))
    from build_dpwh_allocation_adjustments import refresh as refresh_adjustments
    refresh_adjustments()


if __name__=='__main__':refresh()
