#!/usr/bin/env python3
"""Fetch reviewed sources, adopt their corrections, and rebuild affected reports.
Usage: python3 update_csiiiv_reference.py --refresh-pages
       python3 update_csiiiv_reference.py --offline --refresh-pages
No commit, push or deployment. Downloaded source code is never executed.
"""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true',help='Reuse the last complete verified local snapshot')
    parser.add_argument('--refresh-pages',action='store_true',help='Adopt reviewed sources and rebuild calculations, source links and representative enrichment in local NEP/ODV pages')
    args=parser.parse_args()
    if not args.offline:subprocess.run([sys.executable,str(ROOT/'download_csiiiv_reference.py')],cwd=ROOT,check=True)
    from build_external_reference_review import build
    result=build()
    if args.refresh_pages:
        # The normal finalization pipeline calls the external review hook after
        # source-specific page generation; subsequent rebuilds retain the panels.
        from adopt_csiiiv_reference import adopt
        adopt()
        from build_investigation_summary import main as rebuild_reports
        rebuild_reports()
        subprocess.run([sys.executable,str(ROOT/'location_data/enrich_report_tables.py')],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    print(json.dumps({'sourceCommit':result['source']['commit'],'sourceWebsite':result['source']['website'],
        'changedSourceFiles':len(result['snapshotChanges']),'findings':len(result['findings']),
        'pagesRefreshed':args.refresh_pages,'review':'analysis_output/external_reference_review.md',
        'reviewedExtractionsPreferred':True,'deployed':False},indent=2))
if __name__=='__main__':main()
