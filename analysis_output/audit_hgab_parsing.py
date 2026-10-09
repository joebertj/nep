#!/usr/bin/env python3
"""Audit native DPWH extraction against printed controls and a local trace."""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis_output'
sys.path.insert(0,str(ROOT))
from hgab_matching import compatible


def norm(t): return re.sub(r'[^a-z0-9]+',' ',str(t).lower()).strip()


def main():
    trace=json.loads((OUT/'stage_trace_2027.json').read_text())
    trace_house=[p['house'] for p in trace['projects'] if p.get('house')]
    editions={};baseline={}
    for edition,file in [('2nd','hb10858_projects.json'),('3rd','hb10858_3rd_dpwh_projects.json')]:
        payload=json.loads((ROOT/file).read_text()); rows=payload['data']['data'];audit=payload['metadata']['sourceFiles'][0]
        assert len(audit['programReconciliation'])==7
        assert all(c['differencePesos']==0 for c in audit['programReconciliation'])
        assert not audit['unresolvedExtractionRows']
        assert len({r['id'] for r in rows})==len(rows)
        assert all(r['sourceTitle'] and r['pap3'] for r in rows)
        rcs=[r for r in rows if r['pap3']=='Rainwater Collector System']
        assert Counter(r['amountPesos'] for r in rcs)==Counter({4200000:199,9000000:17,38400000:1})
        for fragment,amount in [('Mahay - Barangay Villa Kanangga',250000000),('Kanangga - Barangay Bancasi',300000000),('Scout Ranger Quarters',16000000)]:
            hit=[r for r in rows if fragment in r['projectName'] and r['amountPesos']==amount]
            assert len(hit)==1,(edition,fragment,len(hit))
        # Benchmark only the edition whose PDF hash equals the trace's source.
        same_source=audit['sourceSHA256']==trace['manifest']['source_documents']['house_details']['sha256']
        comparison={'samePdfAsStageTrace':same_source}
        if same_source:
            expected=Counter((h['pdf_page'],h['amount_php']) for h in trace_house)
            actual=Counter((h['sourcePage'],h['amountPesos']) for h in rows)
            comparison.update({'pageAmountOccurrencesAgree':expected==actual,'traceAllocations':len(trace_house),
                'tracePesos':sum(h['amount_php'] for h in trace_house),
                'missingPageAmountOccurrences':[list(k)+[v] for k,v in (expected-actual).items()],
                'additionalPageAmountOccurrences':[list(k)+[v] for k,v in (actual-expected).items()]})
        try:
            previous=json.loads(subprocess.check_output(['git','show','HEAD:'+file],cwd=ROOT,text=True))
            old=previous['data']['data']
            baseline[edition]={'rows':len(old),'rawExtractedPesos':sum(r['amountPesos'] for r in old),'extractionMethod':previous['metadata'].get('extractionMethod')}
        except subprocess.CalledProcessError: pass
        editions[edition]={'rows':len(rows),'pesos':sum(r['amountPesos'] for r in rows),
            'sourceSHA256':audit['sourceSHA256'],'offPageCharactersExcluded':audit['offPageCharactersExcluded'],
            'programReconciliation':audit['programReconciliation'],'rainwaterAllocations':dict(Counter(r['amountPesos'] for r in rcs)),
            'knownButuanRegressions':'all three fixtures recovered once at the printed amount',
            'benchmark':comparison}
    changes=json.loads((OUT/'dpwh_hgab_2nd_vs_3rd.json').read_text())
    additions=[r['third'] for r in changes['rows'] if r['status']=='New in 3rd reading']
    matching_checks={}
    for stem in ['hb_nep_comparison','hb_nep_comparison_3rd']:
        mapping_path=OUT/(stem+'_mapping.json')
        if not mapping_path.exists():
            continue
        mapping=json.loads(mapping_path.read_text()); pairs=mapping['pairs']; summary=mapping['summary']
        assert len({p['hgabId'] for p in pairs})==len(pairs)
        assert len({p['nepId'] for p in pairs})==len(pairs)
        assert all(compatible(p['hgab'],p['nep']) for p in pairs)
        assert len(pairs)+len(mapping['nepWithoutSelectedCounterpart'])==summary['nepRecords']
        assert len(pairs)+len(mapping['hgabWithoutSelectedCounterpart'])==summary['hbCandidateRecords']
        assert all(p['amountDeltaPesos']==p['hgab']['amountPesos']-p['nep']['amountPesos'] for p in pairs)
        matching_checks[stem]={'uniqueAssignments':True,'papDirectionChainageCompatibility':True,
            'completeSourceAccounting':True,'amountDeltasAgree':True,'counts':summary['counts']}
    result={'scope':'DPWH Volume I-C native PDF extraction, both HGAB editions',
        'findings':['Old txtwrite parser included invisible neighbouring spread text.',
            'Action-word/site-word filters dropped road and bridge names and flat office allocations.',
            'Continuation fragments and row baselines were merged across projects; amounts could be attached to headings.',
            'The supplied stage trace House PDF hash is the 2nd-reading PDF hash.',
            'Source hierarchy, wrapped descriptions, explicit amounts and genuine allocation occurrences are now retained.'],
        'baselineFromGitHEAD':baseline,'editions':editions,'readingComparison':changes['summary'],
        'matchingChecks':matching_checks,
        'thirdReadingAddedAllocations':additions,
        'limits':'Printed control reconciliation validates extraction totals, not project identity. OCR uncertainty remains in the Official NEP records supplied through the trace; matches and unmatched records remain provisional.'}
    (OUT/'hgab_parsing_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'editions':{k:{'rows':v['rows'],'pesos':v['pesos'],'benchmark':v['benchmark']} for k,v in editions.items()},'readingComparison':changes['summary']},indent=2))


if __name__=='__main__': main()
