#!/usr/bin/env python3
"""Recover explicitly labelled party-list identities from official indexed pages."""
import html
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'

def identity(name):
    # Exact official-name tokens only: no nickname, substring or surname joins.
    return re.sub(r'[^a-z0-9]+', ' ', unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()).strip()

def build():
    snapshot = json.loads((DATA / 'house_party_list_indexed_sources.json').read_text())
    records, rejected = {}, []
    for result in snapshot['results']:
        for block in result.split('--------------------------------------------------------------------------------'):
            url = re.search(r'\((https://(?:www\.)?congress\.gov\.ph/[^\s)]+)\)', block)
            if not url:
                continue
            source = url.group(1)
            extracted = []
            for name, status, org in re.findall(r'^## ([^\n]+)\n\n(?:(Dropped from the Roll|Resigned|Deceased)\n\n)?Party-list Representative · ([^\n]+)', block, re.M):
                extracted.append((name, org, status))
            for name, org in re.findall(r'^Image: ([^|\n]+)\s*\|[^\n]+?\|\s*Party-list\s*\|\s*([^\n]+)', block, re.M):
                extracted.append((name, org, ''))
            for name, org in re.findall(r'^([A-Za-zÀ-ž][^\n|]+?) Party-list Representative\n([^\n]+)', block, re.M):
                extracted.append((name, org, ''))
            for name, org, status in extracted:
                name, org = name.strip(), org.strip()
                if ',' not in name or len(org) > 50 or re.search(r'Image:|Representative|District|https?://|\||[\ue000-\uf8ff]', name + org):
                    rejected.append({'name': name, 'organization': org, 'source': source, 'reason': 'Incomplete or contaminated indexed snippet'})
                    continue
                key = (identity(name), org.casefold())
                row = records.setdefault(key, {'organization': org, 'representative': name, 'relevantRoles': '', 'membershipStatus': 'Listed in indexed roster; current status not independently verified', 'sources': [], 'roleSources': []})
                if source not in row['sources']:
                    row['sources'].append(source)
                if status:
                    row['membershipStatus'] = status
    committee = json.loads((DATA / 'appropriations_roster.json').read_text())
    leadership = json.loads((DATA / 'house_leadership_roles.json').read_text())
    for row in records.values():
        roles = []
        for m in committee['members']:
            if identity(m['officialName']) == identity(row['representative']):
                roles.append('Appropriations Committee · ' + m['role'])
                row['roleSources'].append(m.get('source', committee['source']))
        for m in leadership['members']:
            if m.get('partyList') == row['organization'] and identity(m['officialName']) == identity(row['representative']):
                roles.insert(0, m['role'])
                row['roleSources'].append(m.get('source', leadership['source']))
        row['relevantRoles'] = '; '.join(dict.fromkeys(roles))
        row['roleSources'] = list(dict.fromkeys(row['roleSources']))
    rows = sorted(records.values(), key=lambda r: (r['organization'].casefold(), r['representative'].casefold()))
    enrich_family_links(rows)
    for row in rows:
        row['additionalVerifiedRoles']=row['relevantRoles']
        row['hasAdditionalVerifiedRole']=bool(row['additionalVerifiedRoles'])
        base='Party-list representative'
        if not row['membershipStatus'].startswith('Listed'):
            base+=' · historical record'
        row['relevantRoles']='; '.join(filter(None,[base,row['additionalVerifiedRoles']]))
    doc = {'asOf': snapshot['asOf'], 'source': 'https://congress.gov.ph/house-members', 'complete': False,
           'scope': 'Recovered explicitly labelled party-list identities, including any explicitly inactive records. Search-index gaps and historical/current differences prevent certification of a complete current roster.',
           'methodology': 'Exact official full-name tokens link roles. No surname-only or fuzzy joins. Organization comes only from an explicit party-list label. Current retrieval date is not an appointment date. A missing role is unverified, not proof of non-membership. No geographic allocation totals are assigned.',
           'summary': {'recoveredIdentities': len(rows), 'organizations': len({r['organization'] for r in rows}), 'withVerifiedRoles': sum(r['hasAdditionalVerifiedRole'] for r in rows), 'roleCountBasis':'Additional leadership or committee roles; the base representative designation is shown for every recovered identity.'}, 'rows': rows}
    for path in [DATA / 'house_party_list_roster.json', STATIC / 'house-party-list-roster.json']:
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + '\n')
    (DATA / 'house_party_list_extraction_review.json').write_text(json.dumps({'rejectedSnippets': rejected, 'summary': doc['summary']}, ensure_ascii=False, indent=2) + '\n')
    return doc

def enrich_family_links(rows):
    """Attach reported kinship only; never convert relatives into budget claims."""
    path=DATA/'pcij_party_list_directory_data.json'
    if not path.exists():return
    directory=json.loads(path.read_text())
    decisions=json.loads((DATA/'party_list_family_identity_decisions.json').read_text())
    aliases={(a['officialName'],a['organization']):a['directoryName'] for a in decisions['aliases']}
    def core(name):
        name=re.sub(r'"[^"]*"|“[^”]*”', '', name)
        return tuple(sorted(t for t in identity(name).split() if len(t)>1))
    def org_key(name):
        return re.sub(r'[^a-z0-9]','',name.lower())
    review=[]
    for row in rows:
        for update in decisions.get('membershipUpdates',[]):
            if update['officialName']==row['representative'] and update['organization']==row['organization']:
                row['membershipStatus']=update['status']
                if update['source'] not in row['sources']:row['sources'].append(update['source'])
        candidates=[r for r in directory['rows'] if org_key(r['organization'])==org_key(row['organization']) and
                    (core(r['name'])==core(row['representative']) or r['name']==aliases.get((row['representative'],row['organization'])))]
        row.update(documentedDistrictRelatives=[],familyLinkSources=[],familyEvidenceDate='',familyLinkStatus='Not established in reviewed sources')
        if len(candidates)!=1:continue
        item=candidates[0]
        # Stop before business evidence; exclude local board and party-list seats.
        relatives=[line.strip() for line in item['note'].split('Contractor link:',1)[0].splitlines()
                   if re.search(r'District\s+(?:Rep\.|Representative)',line,re.I) and '(' in line]
        if relatives:
            row.update(documentedDistrictRelatives=relatives,familyLinkSources=[directory['source'],directory['article']],familyEvidenceDate=directory['sourceDate']+' publication; directory retrieved '+directory['retrievedOn'],
                       familyLinkStatus='Reported family relationship; dated research snapshot, not allocation attribution')
        review.append({'officialName':row['representative'],'directoryName':item['name'],'organization':row['organization'],'districtRelativeLines':len(relatives),'identityBasis':'Explicit reviewed variant' if (row['representative'],row['organization']) in aliases else 'Same organization and exact name tokens after quoted nickname and middle-initial removal'})
    (DATA/'party_list_family_web_enrichment_review.json').write_text(json.dumps({'source':directory['source'],'asOf':directory['retrievedOn'],'identityMatches':review,'rowsWithDocumentedDistrictRelatives':sum(bool(r['documentedDistrictRelatives']) for r in rows),'policy':'Reported kinship only. No motive, personal receipt, control or transfer of allocations inferred. Unmatched identities remain unresolved.'},ensure_ascii=False,indent=2)+'\n')

def render(doc):
    data = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    return '''<p>Party-list organizations represent a national constituency rather than one geographic congressional district. This separate roster provides identity and role context; it does not estimate project allocations for these organizations.</p>
<p><a href="https://congress.gov.ph/house-members">Official House member index</a> · indexed records retrieved ''' + html.escape(doc['asOf']) + '''. <a href="house-party-list-roster.json">Download the recovered roster, sources and methodology</a>.</p>
<p><strong>Coverage:</strong> This is a partial recovered roster, not a certified list of all current members. Search-index gaps and changes in membership can affect coverage. Explicitly inactive records are labelled separately. Every row shows the base representative designation. Additional leadership or committee roles appear only where sourced. The additional-role filter concerns those extra roles; it does not determine whether the person is a representative. Roles reflect the recovered source snapshots, not a certified roster at the HGAB reading date. Missing roles mean unverified. Membership or office does not establish project authorship, receipts or control.</p>
<p>Reported family relationships come from <a href="https://pcij.org/2026/03/12/dynasties-contractors-capture-party-list-seats/">PCIJ’s dated research</a> and its <a href="https://phpartylist-20th-congress.vercel.app/">accompanying directory</a>. The relationship column retains the source’s district and kinship descriptions. It establishes neither project sponsorship nor control of district funds. Missing entries are unresolved, not proof of no relationship.</p><p><strong>Matching method:</strong> Organization labels require an explicit party-list designation. Role enrichment requires exact official full-name tokens after punctuation and accent normalization; surname-only and fuzzy joins are excluded. No geographic district totals are assigned.</p>
<div class="summary-controls"><input id="pl-search" type="search" placeholder="Search organization, representative or role" aria-label="Search party-list roster"><select id="pl-org" aria-label="Party-list organization"><option value="">All organizations</option></select><select id="pl-role" aria-label="Additional verified role coverage"><option value="">All additional-role coverage</option><option value="verified">Additional role recovered</option><option value="unverified">No additional role recovered</option></select><select id="pl-status" aria-label="Membership status"><option value="">All membership statuses</option><option value="listed">Listed; current status unverified</option><option value="inactive">Explicitly inactive</option></select><select id="pl-sort" aria-label="Sort party-list roster"><option value="organization">Organization A–Z</option><option value="representative">Representative A–Z</option></select><button class="export-btn" id="pl-csv" type="button">Export filtered roster CSV</button></div>
<p id="pl-count" aria-live="polite"></p><figure><svg id="pl-chart" class="evidence-graphic" style="display:block;width:100%;height:auto;max-height:400px" viewBox="0 0 1100 340" role="img" aria-label="Recovered representatives by organization"></svg><figcaption>Recovered representatives per organization · largest 15 in the current filter. Counts describe roster coverage, not allocations.</figcaption></figure>
<div class="evidence-table"><table data-ph-location-identity-source="roster"><thead><tr><th>Party-list organization</th><th>Representative · official name</th><th>Relevant roles</th><th>Reported relatives in district seats</th><th>Membership status</th><th>Sources</th></tr></thead><tbody id="pl-body"></tbody></table></div>
<script id="house-party-list-roster-data">(()=>{const D=''' + data + ''',$=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let current=[];
[...new Set(D.rows.map(r=>r.organization))].sort((a,b)=>a.localeCompare(b)).forEach(o=>{const op=document.createElement('option');op.value=o;op.textContent=o;$('pl-org').append(op)});
function render(){const q=$('pl-search').value.toLowerCase(),org=$('pl-org').value,role=$('pl-role').value,status=$('pl-status').value,k=$('pl-sort').value;current=D.rows.filter(r=>(!q||[r.organization,r.representative,r.relevantRoles,...(r.documentedDistrictRelatives||[])].join(' ').toLowerCase().includes(q))&&(!org||r.organization===org)&&(!role||(role==='verified')===r.hasAdditionalVerifiedRole)&&(!status||(status==='listed')===r.membershipStatus.startsWith('Listed'))).sort((a,b)=>a[k].localeCompare(b[k])||a.representative.localeCompare(b.representative));$('pl-count').textContent=current.length+' of '+D.rows.length+' recovered identities shown. This roster is partial.';
$('pl-body').innerHTML=current.map(r=>`<tr><td>${esc(r.organization)}</td><td>${esc(r.representative)}</td><td>${esc(r.relevantRoles||'Party-list representative')}</td><td>${(r.documentedDistrictRelatives||[]).map(esc).join("<br>")||"Not established in reviewed sources"}${r.familyEvidenceDate?"<br>Evidence snapshot: "+esc(r.familyEvidenceDate):""}</td><td>${esc(r.membershipStatus)}</td><td>${[...new Set([...r.sources,...r.roleSources,...(r.familyLinkSources||[])])].map((s,i)=>`<a href="${esc(s)}">Official source ${i+1}</a>`).join('<br>')}</td></tr>`).join('')||'<tr><td colspan="6">No matching records.</td></tr>';
const counts={};current.forEach(r=>counts[r.organization]=(counts[r.organization]||0)+1);const top=Object.entries(counts).sort((a,b)=>b[1]-a[1]||a[0].localeCompare(b[0])).slice(0,15),peak=Math.max(1,...top.map(r=>r[1])),w=1040/Math.max(1,top.length);$('pl-chart').innerHTML=top.map(([name,n],i)=>{const x=40+i*w,h=210*n/peak;return `<rect x="${x}" y="${240-h}" width="${w*.65}" height="${h}" fill="#087e78"><title>${esc(name)}: ${n} recovered representatives</title></rect><text x="${x}" y="${230-h}" font-size="13">${n}</text><text transform="translate(${x},255) rotate(30)" font-size="11">${esc(name)}</text>`}).join('');}
['pl-search','pl-org','pl-role','pl-status','pl-sort'].forEach(id=>$(id).addEventListener(id==='pl-search'?'input':'change',render));$('pl-csv').onclick=()=>{const cols=['organization','representative','relevantRoles','additionalVerifiedRoles','hasAdditionalVerifiedRole','documentedDistrictRelatives','familyLinkStatus','familyEvidenceDate','membershipStatus','sources','roleSources','familyLinkSources'],quote=v=>'"'+String(v??'').replace(/"/g,'""')+'"',csv=[cols,...current.map(r=>cols.map(c=>Array.isArray(r[c])?r[c].join('; '):r[c]))].map(r=>r.map(quote).join(',')).join('\\r\\n'),url=URL.createObjectURL(new Blob(['\\ufeff'+csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='house-party-list-roster-filtered.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};render();})();</script>'''

if __name__ == '__main__':
    print(json.dumps(build()['summary'], indent=2))
