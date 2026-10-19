#!/usr/bin/env python3
"""Check every summary evidence destination, including asynchronously built sections."""
import json,threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
from inspect_report_table import Quiet,ROOT
OUT=Path(__file__).resolve().parents[1]/'analysis_output/summary_evidence_link_review.json'
def main():
 data=json.loads((ROOT/'static/nep-preview/summary-data.json').read_text());server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)));threading.Thread(target=server.serve_forever,daemon=True).start();results=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   try:
    for finding in data['findings']:
     for link in finding['detailLinks']:
      page=browser.new_page(viewport={'width':1440,'height':1000})
      try:
       file,_,anchor=link['page'].partition('#');page.goto(f'http://127.0.0.1:{server.server_port}/static/nep-preview/{file}#{anchor}',wait_until='domcontentloaded')
       target=page.locator('[id='+json.dumps(anchor)+']');target.wait_for(state='visible',timeout=15000);page.wait_for_timeout(1200)
       result=target.evaluate('(element)=>({heading:element.querySelector("h2,h3")?.textContent?.trim(),top:element.getBoundingClientRect().top,tables:element.querySelectorAll("table").length})')
       result.update({'finding':finding['id'],'url':link['page'],'visible':True});results.append(result);print(json.dumps(result),flush=True)
      except Exception as exc:results.append({'finding':finding['id'],'url':link['page'],'visible':False,'error':str(exc)[:250]})
      finally:page.close()
      OUT.write_text(json.dumps({'links':results},indent=2)+'\n')
   finally:browser.close()
 finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
