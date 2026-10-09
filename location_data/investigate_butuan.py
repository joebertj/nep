#!/usr/bin/env python3
"""Trace the Butuan ranking and retain location-role edge cases without reallocating budgets."""
import csv
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from build_database import norm

ROOT=Path(__file__).resolve().parent.parent
ODV=ROOT.parent/'open-data-visualization'
OUT=ROOT/'analysis_output'
TARGET='Butuan · Lone District'

def main():
    public=json.loads((ODV/'static/nep-preview/congress-data.json').read_text())
    audit=json.loads((OUT/'congress_geographic_attribution_3rd.json').read_text())
    projects={p['id']:p for p in json.loads((ROOT/'hb10858_3rd_dpwh_projects.json').read_text())['data']['data']}
    source_csv=OUT/'hb_nep_comparison_3rd.csv'
    with source_csv.open(encoding='utf-8-sig',newline='') as f:stage={r['hgab_id']:r for r in csv.DictReader(f)}
    prior_commit='a99f5326e'
    prior=json.loads(subprocess.check_output(['git','-C',str(ODV),'show',prior_commit+':static/nep-preview/congress-data.json'],text=True))
    before=next(r for r in prior['strict'] if r['district']==TARGET)
    now=next(r for r in public['strict'] if r['district']==TARGET)
    # Reproduce the previous title matcher only to explain which rows changed.
    sys.path.insert(0,str(OUT))
    import investigate_congress_rankings as legacy
    seats,by_name,roster,index,provinces,first=legacy.setup()
    db=sqlite3.connect((ROOT/'location_data/philippine_locations.sqlite').resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    rows=[]
    for row in audit['projects']:
        if TARGET not in row['districts']:continue
        source=projects[row['id']];old_names=legacy.reps.infer_representatives(row['projectName'],roster,index,provinces,first)
        indices=sorted({i for n in old_names for i in by_name.get(legacy.reps.norm(legacy.builder.clean_name(n)),[])})
        old_seats=[f'{seats[i]["province"]} · {seats[i]["districtLabel"]}' for i in indices]
        trace=stage.get(row['id'],{})
        evidence=dict(row,legacyStrictSelectedOnCurrentInputs=len(indices)==1 and TARGET in old_seats,
                      legacyComputedDistrictsOnCurrentInputs=old_seats,sourceText=source.get('sourceText'),
                      nepComparison=trace.get('comparison'),nepTitle=trace.get('closest_nep_title'),
                      nepAmountPesos=trace.get('closest_nep_amount_pesos'),nepSourcePage=trace.get('nep_source_page'),
                      amountDeltaPesos=trace.get('amount_delta_pesos'))
        rows.append(evidence)
    changed_under_legacy=[r for r in rows if not r['legacyStrictSelectedOnCurrentInputs']]
    ids=['HB10858-3-0447-006385','HB10858-3-0447-006383','HB10858-3-0447-006392','HB10858-3-0447-006384','HB10858-3-0228-002167']
    explanations={
        ids[0]:('Unresolved route-wide scope','The user confirmed RTR means Remedios T. Romualdez in this title and requested that the project remain unresolved pending segment evidence. No chainage or explicit budget split establishes that the entire allocation lies within Butuan.'),
        ids[1]:('Cross-city route with a stated segment','Gingoog City is a separate city candidate in Misamis Oriental. The source specifies a chainage and ends in Butuan City; the road name alone does not locate that chainage across the boundary. Keep the city-qualified segment and route reference distinct; geometry or a project schedule is needed to independently verify the segment.'),
        ids[2]:('External route reference and local named section','Sibagat is a municipality/locality candidate in Agusan del Sur. Bugsukan and Antongalon have source claims as barangays under Butuan. The explicitly named section provides stronger local scope evidence than the route name; Bugsukan also occurs under Cantilan, Surigao del Sur, so it must be city-qualified.'),
        ids[3]:('Shared barangay names requiring city qualification','Babag occurs under several municipalities/cities. Babag and Lumbocan are also explicitly listed under Butuan in the local hierarchy. A barangay token alone cannot establish the location.'),
        ids[4]:('Geographic province versus LEG jurisdiction','Butuan City, Agusan del Norte is a geographic chain. It does not make Butuan part of the province LEG district. The roster lists a separate Butuan lone seat, while older local maps retain differing provincial district claims.')}
    cases=[]
    for pid in ids:
        row=next(r for r in rows if r['id']==pid);kind,note=explanations[pid]
        cases.append(dict(row,edgeCase=kind,assessment=note))
    lookups={}
    for name in ['Butuan City','RTR','Sibagat','Gingoog City','Babag','Lumbocan','Bugsukan','Antongalon']:
        lookups[name]=[dict(r) for r in db.execute('SELECT DISTINCT p.id,p.name,p.level,g.path FROM places p JOIN aliases a ON p.id=a.place_id JOIN geographic_paths g ON g.id=p.id WHERE a.name_key=?',(norm(name),))]
    summary={'source':'FY2027 DPWH HGAB 3rd Reading','previousCommit':prior_commit,'previousStrict':before,'currentStrict':now,
             'publishedNetLineChange':now['lineItems']-before['lineItems'],
             'publishedNetPesosChange':now['totalPesos']-before['totalPesos'],
             'legacyMatcherOnCurrentInputs':{'currentlyAcceptedRowsNotSelectedByLegacyMatcher':len(changed_under_legacy),
                                            'allocationPesos':sum(r['amountPesos'] for r in changed_under_legacy),
                                            'limitation':'Reconstructed decisions use current input files, not archived source files from the prior release. They do not establish historical per-row additions.'},
             'interpretation':'These are changes in automated attribution, not budget-stage increases. The rank also rises when other districts lose false or unresolved matches.',
             'sourceScopeWarning':'A single-seat city suffix does not establish that a route-wide project is entirely inside the city. No adjusted total is asserted by this investigation.'}
    output={'summary':summary,'edgeCases':cases,'exactDatabaseCandidates':lookups,'acceptedProjects':sorted(rows,key=lambda r:-r['amountPesos']),
            'requiredResolverRules':['Separate geographic province from LEG jurisdiction.','Require context for repeated barangay names.','Do not expand unestablished acronyms such as RTR.','Treat road endpoints separately from the stated construction section.','Keep inherited district boundary and term conflicts visible.'],
            'limitations':'Local sources only. Candidate matches and title-defined sections are not independently verified project coordinates or district boundaries. Allocation concentration does not establish corruption or sponsorship.'}
    (OUT/'butuan_congress_location_edge_cases.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    note=['# Butuan congressional location investigation','',f"Previous published accepted attribution: ₱{before['totalPesos']:,} across {before['lineItems']} rows. Current published accepted attribution: ₱{now['totalPesos']:,} across {now['lineItems']} rows.",'',f"The published net change is {now['lineItems']-before['lineItems']} rows and ₱{now['totalPesos']-before['totalPesos']:,}. This is not an HGAB budget increase. Reconstructed legacy matching uses current inputs and does not establish historical per-row additions.",'','## Location edge cases','']
    for row in cases:note.extend([f"### {row['edgeCase']}",'',row['projectName'],'',f"₱{row['amountPesos']:,}; HGAB page {row['sourcePage']}; closest NEP page {row['nepSourcePage']}; {row['nepComparison']}.",'',row['assessment'],''])
    note.extend(['## Assessment','','The ₱1.2B route is a material unresolved scope case. The other examples illustrate why route references, construction sections, geographic provinces and LEG jurisdictions must be represented separately. The local matching errors warrant review; they do not establish intentional budget diversion. No corrected district total or public page change is made by this script.'])
    (OUT/'butuan_congress_location_edge_cases.md').write_text('\n'.join(note)+'\n');db.close()
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
