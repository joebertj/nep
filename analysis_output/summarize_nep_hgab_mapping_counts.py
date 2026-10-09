#!/usr/bin/env python3
"""Summarize actual one-to-one assignments from the corrected HGAB screen."""
import json
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis_output'

def main():
    data=json.loads((OUT/'hb_nep_comparison_3rd_mapping.json').read_text())
    pairs=data['pairs']; summary=data['summary']
    exact=[p for p in pairs if p['kind']=='exact_scope']
    potential=[p for p in pairs if p['kind']=='potential']
    clear_api={p['apiId'] for p in exact if p.get('apiId')}
    any_api={p['apiId'] for p in pairs if p.get('apiId')}
    counts={
        'officialNepLineItems':summary['nepRecords'],
        'transparencyNepLineItems':summary['transparencyNepRecords'],
        'hgabExtractedAllocations':summary['hbCandidateRecords'],
        'nepClearlyLinkedByCompatibleScopeNormalizedTitle':len(exact),
        'transparencyNepClearlyLinked':len(clear_api),
        'hgabNoPlausibleNepCounterpart':summary['counts'].get('No plausible NEP title counterpart; review candidate',0),
        'hgabAmbiguousOrAlreadyPairedCounterparts':summary['counts'].get('Multiple or already paired NEP counterparts; review scope',0),
        'potentialNonexactOneToOnePairs':len(potential),
        'officialNepWithoutSelectedCounterpart':len(data['nepWithoutSelectedCounterpart']),
        'transparencyNepWithoutSelectedCounterpart':summary['transparencyNepRecords']-len(any_api),
        'exactScopePairsWithAmountChanges':sum(p['amountDeltaPesos']!=0 for p in exact),
        'exactScopePairsWithSameAmount':sum(p['amountDeltaPesos']==0 for p in exact),
    }
    assert len({p['nepId'] for p in pairs})==len(pairs)
    assert len({p['hgabId'] for p in pairs})==len(pairs)
    assert len(pairs)+counts['officialNepWithoutSelectedCounterpart']==counts['officialNepLineItems']
    assert len(pairs)+len(data['hgabWithoutSelectedCounterpart'])==counts['hgabExtractedAllocations']
    result={'title':'FY2027 DPWH Official NEP vs HGAB 3rd Reading mapping screen',
        'sources':{'mapping':'analysis_output/hb_nep_comparison_3rd_mapping.json','nep':'2027.json plus Official NEP source records from stage_trace_2027.json','hgab':'hb10858_3rd_dpwh_projects.json'},
        'counts':counts,'comparisonCategoryCounts':summary['counts'],
        'method':summary['comparisonMethod'],
        'limits':'Exact compatible title scopes are clear automated links, not manual certifications. Fuzzy pairs and unmatched or ambiguous rows remain for review. Ambiguous rows are excluded from the no-plausible-counterpart count.'}
    (OUT/'nep_hgab_mapping_counts.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(counts,indent=2))

if __name__=='__main__': main()
