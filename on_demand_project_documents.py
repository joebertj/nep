#!/usr/bin/env python3
"""Prepare only one requested project's POW/photos using the local PH connection."""
import argparse,json,os
from project_documents.service import CODE,CACHE,process,state

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('project_code');p.add_argument('--refresh-metadata',action='store_true');p.add_argument('--allow-unverified-pdf-tls',action='store_true',help='Explicitly bypass TLS verification only for the public s3.infrawatch.ph PDF host; API verification remains enabled');p.add_argument('--browser',action='store_true',help='Retrieve requested PDFs through an isolated Playwright Chrome session');args=p.parse_args()
    if args.browser:os.environ['DPWH_DOCUMENT_TRANSPORT']='browser'
    if args.allow_unverified_pdf_tls:os.environ['DPWH_DOCUMENT_ALLOW_UNVERIFIED_TLS']='1'
    if not CODE.fullmatch(args.project_code):p.error('Expected 2027DPWH-Proposal-00000 format')
    process(args.project_code,args.refresh_metadata);data=state(args.project_code)
    print(json.dumps({'projectCode':args.project_code,'cache':str(CACHE/args.project_code),'job':data['job'],'documents':[{'kind':d['kind'],'status':d['status'],'error':d.get('error'),'rows':len(d.get('pow',{}).get('rows',[])),'photos':len(d.get('photos',{}).get('pages',[]))} for d in (data['result'] or {}).get('documents',[])]},indent=2))
    if data['job'].get('hasErrors') or data['job'].get('status')=='error':raise SystemExit(1)
if __name__=='__main__':main()
