#!/usr/bin/env python3
"""Inspect header/menu alignment and reserved teaser space across reports."""
import json,threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from playwright.sync_api import sync_playwright
from inspect_report_table import Quiet,ROOT
OUT=Path(__file__).resolve().parents[1]/'analysis_output/header_render_review.json'

def main():
 server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)));threading.Thread(target=server.serve_forever,daemon=True).start();results=[]
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   try:
    for width in (1440,768,390,320):
     for target in sorted((ROOT/'static/nep-preview').glob('*.html')):
      page=browser.new_page(viewport={'width':width,'height':1000})
      try:
       page.goto(f'http://127.0.0.1:{server.server_port}/static/nep-preview/{target.name}',wait_until='domcontentloaded');page.wait_for_timeout(150)
       result=page.evaluate('''()=>{const h=document.querySelector('body>header'),n=h.querySelector('.report-nav'),intro=h.querySelector('.report-header-heading'),teaser=intro.querySelector('p'),title=intro.querySelector('h1'),r=h.getBoundingClientRect(),nr=n.getBoundingClientRect(),ir=intro.getBoundingClientRect();return {height:r.height,menuTop:nr.top+scrollY,menuHeight:nr.height,nonMenuLinks:[...h.querySelectorAll('a')].filter(a=>!a.closest('.report-nav')).length,teaserOverflow:teaser.getBoundingClientRect().bottom>ir.bottom+1,titleOverflow:title.getBoundingClientRect().bottom>teaser.getBoundingClientRect().top+1,menuOverflow:n.scrollHeight>n.clientHeight+1,headerOverflow:h.scrollHeight>h.clientHeight+1}}''')
       results.append({'page':target.name,'width':width,**result})
      finally:page.close()
     group=[r for r in results if r['width']==width];print(json.dumps({'width':width,'heights':sorted(set(r['height'] for r in group)),'menuPositions':sorted(set(r['menuTop'] for r in group)),'issues':[r for r in group if any(r[k] for k in ('nonMenuLinks','teaserOverflow','titleOverflow','menuOverflow','headerOverflow'))]}),flush=True)
     OUT.write_text(json.dumps({'measurements':results},indent=2)+'\n')
   finally:browser.close()
 finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
