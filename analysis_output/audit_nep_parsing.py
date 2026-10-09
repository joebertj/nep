#!/usr/bin/env python3
"""Audit NEP workbook source cells, ledger totals and the DPWH comparison basis."""
from __future__ import annotations
import argparse
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis_output'
sys.path.insert(0,str(ROOT))
from parse_nep_xlsx import NS, col_index, read_shared_strings, sheet_path
from hgab_matching import load_nep


def query(sql):
    p=subprocess.run(['duckdb','-json','-c',sql],capture_output=True,text=True,check=True)
    return json.loads(p.stdout or '[]')


def check_source_cells(workbook,parquet):
    """Compare every original source field, independent of normalized fields."""
    n=0; amount_total=0; controls=[]
    with zipfile.ZipFile(workbook) as archive, tempfile.TemporaryDirectory(prefix='nep-source-audit-') as tmp:
        shared=read_shared_strings(archive); path=sheet_path(archive,'NEP 2027')
        def value(cell):
            kind=cell.get('t','n');v=cell.find(f'{{{NS}}}v')
            if kind=='inlineStr': return ''.join(t.text or '' for t in cell.iter(f'{{{NS}}}t'))
            if v is None or v.text is None: return ''
            if kind=='s': return shared[int(v.text)]
            if kind=='n':
                d=Decimal(v.text)
                return str(int(d)) if d==d.to_integral_value() else str(float(d))
            return v.text
        with archive.open(path) as f:
            iterator=ET.iterparse(f,events=('start','end'));data=None;reader=None;stream=None
            try:
                for event,e in iterator:
                    if event=='start' and e.tag==f'{{{NS}}}sheetData': data=e
                    if event!='end' or e.tag!=f'{{{NS}}}row': continue
                    source_row=int(e.get('r'))
                    cells={col_index(c.get('r')):value(c) for c in e.findall(f'{{{NS}}}c')}
                    if source_row==1:
                        headers=[cells.get(i,'') for i in range(max(cells)+1)]
                        fields=[{'DEPARTMENT':'departmentCode','AGENCY':'agencyCode'}.get(h,h) for h in headers]
                        columns=','.join('"'+h.replace('"','""')+'"' for h in fields)
                        dest=Path(tmp)/'source_cells.csv'
                        source_sql=str(parquet.resolve()).replace("'","''")
                        dest_sql=str(dest).replace("'","''")
                        subprocess.run(['duckdb','-c',f"COPY (SELECT sourceRow,{columns} FROM read_parquet('{source_sql}') ORDER BY sourceRow) TO '{dest_sql}' (HEADER, DELIMITER ',')"],check=True,capture_output=True,text=True)
                        stream=dest.open(newline='',encoding='utf-8');reader=csv.reader(stream);next(reader)
                    else:
                        actual=next(reader,None)
                        expected=[str(source_row)]+[cells.get(i,'') for i in range(len(headers))]
                        if actual!=expected:
                            raise ValueError(f'Workbook/Parquet source cell disagreement at row {source_row}')
                        amt=cells.get(headers.index('AMT'),'')
                        if amt:
                            pesos=int(Decimal(amt)*1000)
                            if not cells.get(headers.index('DEPARTMENT')): controls.append({'sourceRow':source_row,'pesos':pesos})
                            else: amount_total+=pesos
                        n+=1
                        if n%100000==0: print(f'Checked {n:,} workbook rows against Parquet source cells',flush=True)
                    if data is not None: data.clear()
                if next(reader,None) is not None: raise ValueError('Parquet contains extra source rows')
            finally:
                if stream: stream.close()
    if len(controls)!=1 or amount_total!=controls[0]['pesos']:
        raise ValueError('Independent source allocation total does not match workbook control')
    return {'rowsChecked':n,'allOriginalCellsAgree':True,'sourceAllocationPesos':amount_total,'sourceControls':controls}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--skip-source-cells',action='store_true',help='Use after source cells have already been audited and only the comparison loader changed')
    args=p.parse_args()
    summary=json.loads((ROOT/'nep_fy2027_all_summary.json').read_text())
    workbook=ROOT/'NEP-FY2027.xlsx';parquet=ROOT/'nep_fy2027_all.parquet'
    audit_path=OUT/'nep_parsing_audit.json'
    if args.skip_source_cells:
        previous=json.loads(audit_path.read_text())
        if previous['workbookSHA256']!=hashlib.sha256(workbook.read_bytes()).hexdigest() or previous['parquetSHA256']!=hashlib.sha256(parquet.read_bytes()).hexdigest():
            raise ValueError('Source files changed; run the complete source-cell audit')
        cells=previous['sourceCellAudit']
    else: cells=check_source_cells(workbook,parquet)
    ledger=query("SELECT count(*) n, count(DISTINCT sourceRow) unique_source_rows, sum(amountPesos)::BIGINT pesos, count_if(isBudgetAllocation)::BIGINT allocations, count_if(budgetRowType='grand_total' AND amountPesos IS NOT NULL)::BIGINT contaminated_controls FROM read_parquet('nep_fy2027_all.parquet')")[0]
    assert ledger['n']==cells['rowsChecked']==summary['records']
    assert ledger['n']==ledger['unique_source_rows']
    assert ledger['pesos']==cells['sourceAllocationPesos']==summary['budgetAllocationTotalPesos']
    assert ledger['contaminated_controls']==0
    assert summary['sourceSHA256']==hashlib.sha256(workbook.read_bytes()).hexdigest()
    dpwh=query("SELECT LEFT(PREXC_FPAP_ID,1) branch, sum(amountPesos)::BIGINT pesos FROM read_parquet('nep_fy2027_all.parquet') WHERE UACS_DPT_DSC ILIKE '%Public Works%' AND isBudgetAllocation GROUP BY 1 ORDER BY 1")
    funds=query("SELECT LEFT(FUNDCD,3) fund_prefix, sum(amountPesos)::BIGINT pesos FROM read_parquet('nep_fy2027_all.parquet') WHERE UACS_DPT_DSC ILIKE '%Public Works%' AND isBudgetAllocation GROUP BY 1 ORDER BY 1")
    trace=json.loads((OUT/'stage_trace_2027.json').read_text());rows,api_count=load_nep(ROOT/'2027.json',OUT/'stage_trace_2027.json')
    operations=next(v['pesos'] for v in dpwh if v['branch']=='3')
    assert operations==sum(r['amountPesos'] for r in rows)==trace['summary']['stages']['official_nep']['operations_php']
    new_appropriations=next(v['pesos'] for v in funds if v['fund_prefix']=='101')
    assert new_appropriations==trace['summary']['stages']['official_nep']['new_appropriations_php']
    api_pesos=sum(r['amountPesos'] for r in rows if r['apiId'])
    assert api_pesos==trace['summary']['stages']['transparency_nep']['php']
    outside=[r for r in rows if not r['apiId']]
    gaps=[r for r in outside if r['pap3']!='Foreign-assisted projects (FAP)']
    fap=[r for r in outside if r['pap3']=='Foreign-assisted projects (FAP)']
    assert len(gaps)==trace['summary']['transparency_to_official']['nep_not_in_transparency_rows']
    assert sum(r['amountPesos'] for r in gaps)==trace['summary']['transparency_to_official']['nep_not_in_transparency_php']
    result={'workbookSHA256':hashlib.sha256(workbook.read_bytes()).hexdigest(),'parquetSHA256':hashlib.sha256(parquet.read_bytes()).hexdigest(),
        'apiSnapshotSHA256':hashlib.sha256((ROOT/'2027.json').read_bytes()).hexdigest(),
        'officialSourceTraceSHA256':hashlib.sha256((OUT/'stage_trace_2027.json').read_bytes()).hexdigest(),
        'sourceCellAudit':cells,'ledger':ledger,'dpwhWorkbookBranches':dpwh,'dpwhWorkbookFunds':funds,
        'dpwhReconciliation':{'operationsPesos':operations,'newAppropriationsPesos':new_appropriations,'apiRows':api_count,'apiPesos':api_pesos,
            'officialRows':len(rows),'outsideApiNonFapRows':len(gaps),'outsideApiNonFapPesos':sum(r['amountPesos'] for r in gaps),
            'outsideApiFapRows':len(fap),'outsideApiFapPesos':sum(r['amountPesos'] for r in fap)},
        'sourceTitleConfidence':{'apiPairKinds':dict(Counter(r['apiPairKind'] for r in rows if r.get('apiPairKind'))),
            'officialTitlesAllowedOnlyAsPotential':sum(not r['officialTitleTrusted'] for r in rows),
            'primaryTitlesAllowedOnlyAsPotential':sum(not r['primaryTitleTrusted'] for r in rows)},
        'fixes':['Grand-total AMT retained as a control; excluded from normalized allocations to prevent counting the national budget twice.',
            'Entries without AMT are marked as lacking allocations, not counted as funded projects.',
            'Agency totals use department:agency codes to distinguish repeated Office of the Secretary labels.',
            'Exact integer peso conversion and formula/error validation preserve source amounts.',
            'Every trace API anchor checked against the actual local 2027.json; unique coverage and amount totals enforced.',
            'Uncorroborated ambiguous PDF/OCR titles excluded from clear exact matches.'],
        'limits':['No original Official NEP PDF or its extraction generator exists in the current workspace; PDF titles cannot be independently re-extracted here.',
            'The workbook provides DPWH PAP/office envelopes rather than detailed allocations for most named catalogue projects; it validates financial controls, not every project title.',
            'Fund prefix 104 includes allocations outside printed new appropriations; these remain in the workbook ledger with their original fund labels.']}
    audit_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    (OUT/'nep_dpwh_baseline.json').write_text(json.dumps({'metadata':{'source':'Local 2027.json, Official NEP source records in stage_trace_2027.json; independently reconciled with the workbook','operationsPesos':operations,'titleConfidence':'See per-record primaryTitleTrusted and officialTitleTrusted','limits':result['limits']},'data':{'data':rows}},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'ledger':ledger,'dpwhReconciliation':result['dpwhReconciliation'],'sourceTitleConfidence':result['sourceTitleConfidence']},indent=2))


if __name__=='__main__':main()
