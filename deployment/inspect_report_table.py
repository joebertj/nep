#!/usr/bin/env python3
"""Reproduce a reported static-table display issue using isolated local Chrome."""
import argparse,json,threading
from functools import partial
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]/'open-data-visualization'
class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--page',default='mpb.html');parser.add_argument('--section',default='mpb-coordinate-proximity');parser.add_argument('--width',type=int,default=1440);parser.add_argument('--screenshot',default='/private/tmp/nep-table-diagnostic.png');args=parser.parse_args()
    static=ROOT/'static/nep-preview';target=(static/args.page).resolve()
    if not target.is_relative_to(static) or target.suffix!='.html' or not target.is_file():parser.error('Select an existing static report HTML file')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(ROOT)));threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            try:
                page=browser.new_page(viewport={'width':args.width,'height':1000});errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}/static/nep-preview/{args.page}',wait_until='domcontentloaded');page.wait_for_timeout(4000)
                section=page.locator('[id='+json.dumps(args.section)+']');section.evaluate('(element)=>window.scrollTo(0,window.scrollY+element.getBoundingClientRect().top-20)')
                page.screenshot(path=args.screenshot)
                tables=section.locator('table').evaluate_all('''tables=>tables.map(t=>({headers:[...t.tHead.rows[0].cells].map(c=>c.textContent),rows:[...t.tBodies[0].rows].slice(0,4).map(r=>[...r.cells].map(c=>({text:c.innerText.slice(0,100),width:c.getBoundingClientRect().width}))) }))''')
                print(json.dumps({'page':args.page,'section':args.section,'errors':errors,'screenshot':args.screenshot,'tables':tables},indent=2))
            finally:browser.close()
    finally:server.shutdown();server.server_close()
if __name__=='__main__':main()
