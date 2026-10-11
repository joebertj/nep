#!/usr/bin/env python3
"""Join committee identities to the local roster, preserving unresolved names."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'analysis_output'
# Explicit identity review of nickname/full-name variants against the local
# representative roster. This map does not change project geography.
ALIASES={1:'Nueva Ecija · 1st District',14:'Davao de Oro · 1st District',20:'Laguna · 3rd District',22:'Mandaue · Lone District',23:'Calamba · Lone District',32:'Cagayan · 2nd District',35:'Sorsogon · 1st District',37:'Negros Oriental · 2nd District',67:'Negros Occidental · 3rd District',69:'Nueva Vizcaya · Lone District',71:'Quezon City · 6th District',72:'Taguig–Pateros · Lone District',81:'Albay · 2nd District',82:'South Cotabato · 1st District',91:'Manila · 2nd District',93:'Rizal · 1st District',98:'Bohol · 2nd District',123:'Batangas · 4th District'}
# Full-name disagreements require corroboration, not forced nickname matches.
UNRESOLVED={3:['Camarines Sur · 4th District'],61:['Sulu · 2nd District'],79:['Negros Occidental · 4th District'],88:['Ilocos Sur · 2nd District'],111:['Abra · Lone District']}

def build():
    doc=json.loads((DATA/'appropriations_identity_review.json').read_text())
    rows=json.loads((DATA/'congress_benchmark.json').read_text())['rows'];by_leg={r['district']:r for r in rows}
    for m in doc['members']:
        suggestions=m.pop('suggestions',[])
        district=ALIASES.get(m['number']) or (suggestions[0]['district'] if len(suggestions)==1 else None)
        m['district']=district
        m['representative']=by_leg[district]['representative'] if district else m['officialName']
        m['identityMethod']='explicit nickname review' if m['number'] in ALIASES else 'unique full-name token agreement' if district else 'no accepted local district identity'
        m['unresolvedDistrictCandidates']=UNRESOLVED.get(m['number'],[])
    doc['complete']=False
    doc['numberedRosterComplete']=not doc['missingNumbers']
    doc['absencePolicy']='Not listed in the recovered numbered roster is not certified non-membership: ex-officio roles and unresolved identities are separate.'
    doc['membershipScope']='Numbered elected committee roster, current indexed snapshot; reading-date history not fully verified.'
    path=DATA/'appropriations_roster.json';path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    print('Entries:',len(doc['members']),'Mapped district identities:',len({m['district'] for m in doc['members'] if m['district']}))
if __name__=='__main__':build()
