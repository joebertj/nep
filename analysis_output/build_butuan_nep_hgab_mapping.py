#!/usr/bin/env python3
"""Build current source-preserving mapping cases, with Butuan first.

Select by NEP source IDs and current assignments, never old parser row IDs.
"""
import csv
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis_output'

def main():
    api=json.loads((ROOT/'2027.json').read_text())['data']['data']
    hb_payload=json.loads((ROOT/'hb10858_3rd_dpwh_projects.json').read_text())
    hb=hb_payload['data']['data']
    mapping=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    with (OUT/'hb_nep_comparison_3rd.csv').open(newline='') as f:
        assessments={r['hgab_id']:r for r in csv.DictReader(f)}
    api_by_code={r.get('code') or r.get('id'):r for r in api}
    pairs_by_api={p['apiId']:p for p in mapping['pairs'] if p.get('apiId')}
    def enrich(row):
        return {**row,'comparisonAssessment':assessments.get(row['id'])}
    def case(ident,codes,fragment=None):
        nep=[{**api_by_code[c],'amountPesos':round(float(api_by_code[c]['amount'])*1000)} for c in codes]
        pairs=[pairs_by_api[c] for c in codes if c in pairs_by_api]
        paired_ids={p['hgabId'] for p in pairs}
        selected=[enrich(r) for r in hb if r['id'] in paired_ids]
        related=[enrich(r) for r in hb if fragment and re.search(fragment,r['projectName'],re.I) and r['id'] not in paired_ids]
        return {'caseId':ident,'nep':nep,'hgab':selected,'pairDetails':pairs,
            'nepWithoutSelectedCounterpart':[c for c in codes if c not in pairs_by_api],
            'otherHgabRowsNamingSameAsset':related,
            'note':'Titles, amounts, offices and physical PDF pages come from the current source records. Related asset names are contextual records, not automatically assigned counterparts.'}
    is_deo=lambda r:bool(re.search(r'^Butuan City (?:District Engineering Office|DEO)\b',r.get('office',''),re.I))
    named=lambda r:bool(re.search(r'\bButuan City\b',r.get('projectName',''),re.I))
    local=[r for r in api if is_deo(r)]
    local_hb=[r for r in hb if is_deo(r)]
    butuan_cases=[case('water-system-mahay-villa-kanangga',['2027DPWH-Proposal-38923']),
        case('water-system-villa-kanangga-bancasi',['2027DPWH-Proposal-38924']),
        case('water-system-relief-pipe',['2027DPWH-Proposal-38925']),
        case('multi-purpose-building-butuan',['2027DPWH-Proposal-38931']),
        case('scout-ranger-quarters',['2027DPWH-Proposal-04590'])]
    cases=[{'caseId':'butuan-local-allocation','priority':1,'scope':'Butuan City DEO and named Butuan City projects',
        'finding':'The corrected parser recovers full water-system sections and the Scout Ranger project once, with their printed amounts and source pages.','cases':butuan_cases},
        case('same-project-amount-changed',['2027DPWH-Proposal-33737']),
        case('same-road-distinct-chainage-segments',[f'2027DPWH-Proposal-{n}' for n in ['39579','39580','39581','39582']],r'Impasug.?ong.*Malaybalay'),
        case('pandi-by-pass',['2027DPWH-Proposal-20581'],r'Pandi.*By.?pass'),
        case('two-padada-mainit-flood-projects',['2027DPWH-Proposal-21401','2027DPWH-Proposal-21402'],r'Padada.*Mainit'),
        case('tagum-panabo-route-segments',['2027DPWH-Proposal-38549','2027DPWH-Proposal-38550']),
        case('tandu-bato-tulayan-bridge',[],r'Tandu Bato.*Tulayan.*Bridge')]
    local_total=sum(round(float(r['amount'])*1000) for r in local)
    result={'title':'FY2027 DPWH NEP to HGAB 3rd Reading mapping detail; Butuan first','unit':'pesos',
        'sources':{'nep':'2027.json and Official NEP source records from stage_trace_2027.json',
            'hgab':'hb10858_3rd_dpwh_projects.json','mapping':'analysis_output/hb_nep_comparison_3rd_mapping.json'},
        'method':{'matching':mapping['summary']['comparisonMethod'],'extraction':hb_payload['metadata']['extractionMethod'],
            'limits':'Provisional automated links. No manual certification of additions/removals. Engineering-office allocation labels are not legislative district assignments.'},
        'summary':{'nepButuanDeoRecords':len(local),'nepButuanDeoTotalPesos':local_total,
            'hgabRowsWithButuanCityDeoOfficeLabel':len(local_hb),'hgabOfficeLabelRawExtractedTotalPesos':sum(r['amountPesos'] for r in local_hb),
            'hgabRowsNamedButuanCityOrAssignedButuanDeo':sum(is_deo(r) or named(r) for r in hb),
            'pdfCrossCheck':{'sourceFile':'DPWH per district.pdf','amountPesos':8834267000,
                'differenceNepMinusPdfPesos':local_total-8834267000,'note':'A district summary cross-check; the document edition is not established.'}},
        'mappingCases':cases,
        'nepButuanDeoRecords':[{**r,'amountPesos':round(float(r['amount'])*1000)} for r in local],
        'nepButuanCityRouteReferencesOtherOffices':[r for r in api if named(r) and not is_deo(r)],
        'hgabButuanCityOrOfficeRecords':[enrich(r) for r in hb if is_deo(r) or named(r)],
        'hgabButuanonNameHitsExcluded':[enrich(r) for r in hb if re.search(r'\bbutuanon\b',r['projectName'],re.I)]}
    (OUT/'butuan_nep_hgab_mapping.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))

if __name__=='__main__': main()
