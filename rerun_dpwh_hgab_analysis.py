#!/usr/bin/env python3
"""Audit NEP, rebuild HGAB comparisons, and refresh local review pages."""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def run(*args):
    print('\nRunning: '+' '.join(map(str,args)),flush=True)
    subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,check=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--text-cache',type=Path)
    p.add_argument('--reparse-nep',action='store_true',help='Regenerate the national workbook JSON/Parquet before the source-cell audit')
    a=p.parse_args()
    if a.reparse_nep:
        run('parse_nep_xlsx.py')
    run('analysis_output/audit_nep_parsing.py')
    for edition,file,out in [('2ND','hb10858_projects.json','hb_nep_comparison.csv'),('3RD','hb10858_3rd_dpwh_projects.json','hb_nep_comparison_3rd.csv')]:
        cmd=['extract_hb_projects.py','--pdf-dir',f'HB 10858 FOR {edition} READING','--out',file]
        if a.text_cache: cmd.extend(['--text-cache',a.text_cache])
        run(*cmd)
        run('compare_hb_nep.py','--hb',file,'--official-nep-trace','analysis_output/stage_trace_2027.json','--out',f'analysis_output/{out}')
    run('compare_dpwh_hgab_readings.py','--second','hb10858_projects.json','--third','hb10858_3rd_dpwh_projects.json','--out','analysis_output/dpwh_hgab_2nd_vs_3rd.json')
    run('analysis_output/audit_hgab_parsing.py')
    run('analysis_output/summarize_nep_hgab_mapping_counts.py')
    run('analysis_output/build_butuan_nep_hgab_mapping.py')
    run('compare_hgab_non_dpwh_nep.py')
    run('build_fmr_report.py')
    run('build_nia_report.py')
    run('build_hfep_report.py')
    run('build_report.py')


if __name__=='__main__': main()
