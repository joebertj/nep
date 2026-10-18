#!/usr/bin/env python3
"""Compare project attribution with boundary labels without promoting old boundaries."""
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from build_database import ROOT, OUT, norm
from location_text import geographic_title, place_key

def main():
    audit_path=ROOT/'analysis_output/congress_geographic_attribution_db_3rd.json'
    boundary_path=ROOT/'analysis_output/deo_leg_boundary_crosswalk.json'
    source_path=ROOT/'hb10858_3rd_dpwh_projects.json'
    audit=json.loads(audit_path.read_text())
    native=json.loads(source_path.read_text())['data']['data']
    by_id={r['id']:r for r in native}
    if len(by_id)!=len(native) or {r['id'] for r in audit['projects']}!=set(by_id):
        raise ValueError('Attribution audit does not cover the current HGAB source IDs')
    db=sqlite3.connect((OUT/'philippine_locations.sqlite').as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    labels=defaultdict(list)
    for r in db.execute('SELECT e.*,l.jurisdiction,l.designation FROM boundary_locality_evidence e LEFT JOIN leg_districts l ON l.id=e.leg_id'):
        labels[norm(r['province_label']),place_key(r['locality_label'])].append(dict(r))
    records=[];counts=Counter();pesos=Counter();groups=defaultdict(lambda:{'lineItems':0,'amountPesos':0})
    for row in audit['projects']:
        source=by_id[row['id']]
        if row['projectName']!=source['projectName'] or row['amountPesos']!=source['amountPesos']:
            raise ValueError('Attribution audit title/amount differs from HGAB source')
        title,_=geographic_title(row['projectName'])
        fields=[f.strip(' .') for f in title.split(',')]
        candidates=labels.get((norm(fields[-1]),place_key(fields[-2])),[]) if len(fields)>=2 else []
        if not candidates:
            counts['no_exact_qualified_boundary_label']+=1
            continue
        matched_seats=sorted({r['jurisdiction']+' · '+r['designation'] for r in candidates if r['leg_id']})
        raw_labels=sorted({json.loads(r['raw_json'])['leg'] for r in candidates})
        # Existing assigned seat labels retain the current roster's jurisdiction.
        # Only exact canonical identity agreement counts as corroboration here.
        existing={norm(s) for s in row['districts']}
        proposed={norm(s) for s in matched_seats}
        all_linked=all(r['leg_id'] for r in candidates)
        if not all_linked:
            status='boundary_leg_identity_unresolved'
        elif len(proposed)!=1:
            status='boundary_labels_multiple_districts'
        elif not existing:
            status='unassigned_project_with_boundary_candidate_requires_current_evidence'
        elif existing==proposed:
            status='agrees_with_existing_assignment_dates_unverified'
        else:
            status='assignment_boundary_disagreement_requires_review'
        counts[status]+=1;pesos[status]+=row['amountPesos']
        key=fields[-2]+' · '+fields[-1]+' | '+status
        groups[key]['lineItems']+=1;groups[key]['amountPesos']+=row['amountPesos']
        records.append({'id':row['id'],'projectName':row['projectName'],
            'amountPesos':row['amountPesos'],'province':fields[-1], 'municipality':fields[-2],
            'currentDistricts':row['districts'],'boundaryDistrictCandidates':matched_seats,
            'rawBoundaryLabels':raw_labels,'boundaryObjectIds':[json.loads(r['raw_json'])['objectId'] for r in candidates],
            'status':status,'currentReasons':row['reasons'],
            'newAssignmentApproved':False})
    out={'summary':{'sourceProjects':len(native),'projectsWithExactQualifiedBoundaryLabels':len(records),
        'statusCounts':dict(counts),'amountPesosByMatchedStatus':dict(pesos),
        'safeNewAssignmentsFromBoundaryEvidenceAlone':0},
        'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [audit_path,boundary_path,source_path]},
        'methodology':['Exact adjacent municipality/city and province fields after existing metadata normalization.',
            'No DEO-only inference, fuzzy place match, area-based budget split or automatic legacy-to-current LEG rename.',
            'Source boundary dates remain unknown. Agreement corroborates a label, not the funded construction segment.',
            'Disagreement is a review question, not proof the existing assignment is incorrect.',
            'No assignment is promoted from boundary labels alone; all names and geographic levels remain qualified.'],
        'locationReviewGroups':sorted([dict(location=k,**v) for k,v in groups.items()],key=lambda r:-r['amountPesos']),
        'projects':records}
    target=ROOT/'analysis_output/congress_boundary_accuracy_review.json'
    target.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    with target.with_suffix('.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader()
        writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,list) else v for k,v in r.items()} for r in records)
    print(json.dumps(out['summary'],ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
