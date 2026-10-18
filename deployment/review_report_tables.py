#!/usr/bin/env python3
"""Inspect actual report-table styling, pagination and overflow in local Chrome."""
import argparse,json,threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
from inspect_report_table import Quiet,ROOT
INSPECT=r'''()=>[...document.querySelectorAll('table')].filter(t=>t.getClientRects().length).map(t=>{
 const rows=[...t.tBodies].flatMap(b=>[...b.rows]).filter(r=>r.cells.length>1),shown=rows.filter(r=>r.getClientRects().length),wrap=t.closest('.report-table-scroll'),th=t.querySelector('th'),rect=t.getBoundingClientRect();
 return {id:t.id||t.tBodies[0]?.id||null,section:t.closest('section,article')?.querySelector('h2,h3')?.textContent?.trim(),headers:[...(t.tHead?.rows[0]?.cells||[])].map(c=>c.textContent.trim()),rows:rows.length,shownRows:shown.length,styled:!!wrap,headerColor:th?getComputedStyle(th).backgroundColor:null,needsPagination:shown.length>10,horizontalOverflow:!!wrap&&wrap.scrollWidth>wrap.clientWidth+2,width:rect.width,wrapper:wrap?.className||t.parentElement.className};})'''
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pages',nargs='*');parser.add_argument('--width',type=int,default=1440);parser.add_argument('--output',default=str(Path(__file__).resolve().parents[1]/'analysis_output/table_render_review.json'));args=parser.parse_args()
 names=args.pages or ['dpwh-hgab.html']+[p.name for p in sorted((ROOT/'static/nep-preview').glob('*.html')) if p.name!='dpwh-hgab.html']
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)));threading.Thread(target=server.serve_forever,daemon=True).start();results=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   try:
    for name in names:
     if '/' in name or not name.endswith('.html'):raise ValueError('Select report filenames only')
     page=browser.new_page(viewport={'width':args.width,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(error.stack or str(error)))
     try:
      page.goto(f'http://127.0.0.1:{server.server_port}/static/nep-preview/{name}',wait_until='domcontentloaded',timeout=30000);page.wait_for_timeout(3000)
      tables=page.evaluate(INSPECT);record={'page':name,'errors':errors,'tables':tables,'bodyOverflow':page.evaluate('document.documentElement.scrollWidth>innerWidth+2')};results.append(record)
      print(json.dumps({'page':name,'tables':len(tables),'unstyled':sum(not t['styled'] for t in tables),'missingPagination':sum(t['needsPagination'] for t in tables),'overflow':sum(t['horizontalOverflow'] for t in tables),'errors':errors}),flush=True)
     except Exception as exc:results.append({'page':name,'error':str(exc)[:500]});print(name,type(exc).__name__,flush=True)
     finally:page.close()
     Path(args.output).write_text(json.dumps({'viewportWidth':args.width,'pages':results},indent=2)+'\n')
   finally:browser.close()
 finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
