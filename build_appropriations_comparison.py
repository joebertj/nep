#!/usr/bin/env python3
"""Source-backed committee roles and descriptive strict geographic comparisons."""
import argparse
import json
from pathlib import Path
from statistics import median
ROOT = Path(__file__).resolve().parent
DEFAULT = ROOT / 'analysis_output/appropriations_roster.json'

def enrich_rows(rows, roster_path=DEFAULT):
    roster = json.loads(roster_path.read_text())
    leadership=json.loads((ROOT/'analysis_output/house_leadership_roles.json').read_text())
    leaders={m['district']:m for m in leadership['members'] if m.get('district')}
    members, review = {}, set()
    for m in roster['members']:
        review.update(m.get('unresolvedDistrictCandidates', []))
        if m.get('district'):
            members.setdefault(m['district'], []).append(m)
    for r in rows:
        found = members.get(r['district'], [])
        if any(m['representative'].casefold() != r['representative'].casefold() for m in found):
            raise ValueError('Committee representative identity conflict: '+r['district'])
        r['committeeStatus'] = 'member' if found else 'identity-review' if r['district'] in review else 'not-listed'
        r['committeeRole'] = '; '.join(dict.fromkeys(m['role'] for m in found))
        groups = {'minority' if 'Minority' in m['role'] else 'majority' if 'Majority' in m['role'] else 'unspecified' for m in found}
        specified = groups - {'unspecified'}
        r['committeeBloc'] = next(iter(specified)) if len(specified)==1 else 'unspecified'
        r['relevantRoles'] = r['committeeRole']
        r['roleSources'] = [roster['source']] if found else []
        if r['district'] in leaders:
            name, role = leaders[r['district']]['representative'], leaders[r['district']]['role']
            if r['representative'] != name: raise ValueError('Leadership identity conflict')
            r['relevantRoles'] = '; '.join(filter(None, [role, r['committeeRole']]))
            leader=leaders[r['district']]
            r['roleSources'].extend(dict.fromkeys(filter(None, [leader.get('source', leadership['source']), leader.get('roleDesignationSource'), leader.get('identitySource')])))
        r['roleSources']=list(dict.fromkeys(r['roleSources']))
        r['bicamStatus'] = 'FY2027 appointment not verified'
    return {'source': roster['source'], 'asOf': roster['asOf'], 'numberedEntries':len(roster['members']),
            'uniqueOfficialNames':len({m['officialName'].casefold() for m in roster['members']}),
            'mappedDistricts':len(members), 'unresolvedDistricts':sorted(review),
            'dateBasis':roster['dateBasis'], 'absencePolicy':roster['absencePolicy'],
            'leadershipRoleScope':leadership['scope'], 'leadershipSource':leadership['source'],
            'leadershipAsOf':leadership['asOf'], 'leadershipDateBasis':leadership['dateBasis'],
            'blocPolicy':'Majority/minority is copied only from the official committee role. Chair and vice-chair roles alone do not establish bloc. Minority is not a certified opposition label.',
            'bicam':{'status':'No FY2027 appointed conferee roster verified in the official sources searched as of 2026-10-11.',
                     'source':'https://www.congress.gov.ph/media/press-releases/10187',
                     'context':'House statement discusses opening budget bicam proceedings; it does not name an appointed delegation. No committee member is inferred to be a conferee.'}}

def comparison(rows):
    members=[r for r in rows if r['committeeStatus']=='member']
    result={}
    for metric in ['strictHGABPesos','potentialInsertionPesos','strictHGABLines','potentialInsertionLines']:
        ranked=sorted(rows,key=lambda r:(-r[metric],r['district']))
        listed=[r for r in ranked if r['committeeStatus']=='member']
        absent=[r for r in ranked if r['committeeStatus']=='not-listed']
        result[metric]={'highestListedMember':listed[0] if listed else None,
                        'highestNotListed':absent[0] if absent else None,
                        'notListedAboveHighestListed':[r for r in absent if listed and r[metric]>listed[0][metric]],
                        'lowestListedMembers':sorted(members,key=lambda r:(r[metric],r['district']))[:10]}
    groups={}
    for group in ['majority','minority','unspecified']:
        subset=[r for r in members if r['committeeBloc']==group]; positive=[r for r in subset if r['strictHGABLines']>0]
        groups[group]={'districts':len(subset),'noAcceptedAttribution':len(subset)-len(positive),
                       'medianStrictAllocationIncludingZeros':median(r['strictHGABPesos'] for r in subset) if subset else None,
                       'medianStrictAllocationPositiveOnly':median(r['strictHGABPesos'] for r in positive) if positive else None}
    return {'metrics':result,'blocDescriptiveStatistics':groups,
            'interpretation':'Partial DPWH geographic attribution cannot establish exclusion, preferential treatment, opposition status or a causal effect of committee membership. Zeros mean no accepted attribution, not no budget.'}

def build(roster_path=DEFAULT):
    benchmark=json.loads((ROOT/'analysis_output/congress_benchmark.json').read_text())
    rows=benchmark['rows']; metadata=enrich_rows(rows,roster_path)
    result={'scope':benchmark['scope'],'roster':metadata,'comparisons':comparison(rows),'rows':rows}
    path=ROOT/'analysis_output/appropriations_comparison.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return path

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster',type=Path,default=DEFAULT)
    print(build(p.parse_args().roster))

def apply_roles_page(path):
    """Refresh role columns in the existing strict allocation and LEG tables."""
    import re
    rows=json.loads((ROOT/'analysis_output/congress_benchmark.json').read_text())['rows']
    roles={r['district']:{k:r[k] for k in ['representative','relevantRoles','committeeStatus','committeeBloc']} for r in rows}
    text=path.read_text()
    text=re.sub(r'<script id="congress-role-data">.*?</script>','',text,flags=re.S)
    encoded=json.dumps(roles,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
    text=text.replace('</head>','<script id="congress-role-data">window.CongressRoleData='+encoded+';</script></head>',1)
    strict_header='<th>Representative</th><th class="num">Accepted line items</th>'
    text=text.replace(strict_header,'<th>Representative</th><th>Relevant roles</th><th class="num">Accepted line items</th>')
    strict_cell='<td>${esc(x.representative)}</td><td class="num">${fmt(x.lineItems)}</td>'
    text=text.replace(strict_cell,'<td>${esc(x.representative)}</td><td>${esc((window.CongressRoleData[x.district]?.representative===x.representative?window.CongressRoleData[x.district]?.relevantRoles:null)||"No verified role in this view")}</td><td class="num">${fmt(x.lineItems)}</td>')
    text=text.replace("const columns=['district','representative','lineItems','totalPesos'", "const columns=['district','representative','relevantRoles','lineItems','totalPesos'")
    marker=" const s=D.summary;"
    if 'role-enrichment-start' not in text:
        text=text.replace(marker," /* role-enrichment-start */ D.strict.forEach(r=>{const role=window.CongressRoleData[r.district];r.relevantRoles=role?.representative===r.representative?role.relevantRoles:''}); /* role-enrichment-end */"+marker,1)
    leg_header='<th>Representative</th><th>Potential addition line items</th>'
    text=text.replace('<tr><td colspan="6">No matching districts.</td></tr>', '<tr><td colspan="7">No matching districts.</td></tr>')
    text=text.replace(leg_header,'<th>Representative</th><th>Relevant roles</th><th>Potential addition line items</th>')
    text=text.replace("<td>${esc(d.representative||'—')}</td><td>${fmt(d.candidateLines)}</td>","<td>${esc(d.representative||'—')}</td><td>${esc((window.CongressRoleData[d.district]?.representative===d.representative?window.CongressRoleData[d.district]?.relevantRoles:null)||'No verified role in this view')}</td><td>${fmt(d.candidateLines)}</td>")
    for marker in ['districts=DATA.districts;', 'districts=DATA.districts,']:
        if marker in text and 'leg-role-enrichment' not in text:
            # Avoid editing declarations: enrichment runs immediately before dropdown population.
            anchor='for(const d of [...districts].sort'
            text=text.replace(anchor, "/* leg-role-enrichment */ districts.forEach(d=>{const r=window.CongressRoleData[d.district];d.relevantRoles=r?.representative===d.representative?r.relevantRoles:''});\n"+anchor, 1)
    text=text.replace("['district','representative','candidateLines','candidateAllocationPesos','acceptedDistrictLines']","['district','representative','relevantRoles','candidateLines','candidateAllocationPesos','acceptedDistrictLines']")
    text=text.replace("`₱${(v/1e9).toFixed(0)}B`", "(v>=1e9?`₱${(v/1e9).toFixed(1)}B`:`₱${(v/1e6).toFixed(0)}M`)")
    path.write_text(text)
    public=path.parent/'appropriations-roster.json';public.write_text(DEFAULT.read_text())
