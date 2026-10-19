#!/usr/bin/env python3
"""Exercise the requested Burol document view with local cached POW/photo evidence."""
import json,sys,threading,urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from playwright.sync_api import sync_playwright
from inspect_report_table import Quiet,ROOT
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_documents.service import Handler
class View(Quiet):
    def proxy(self):
        path=self.path.replace('/api/nep-documents/','/projects/',1)
        request=urllib.request.Request(self.worker+path,method=self.command)
        try:response=urllib.request.urlopen(request,timeout=30)
        except HTTPError as exc:response=exc
        with response:
            raw=response.read();self.send_response(response.status);self.send_header('Content-Type',response.headers.get('Content-Type','application/json'));self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path.startswith('/api/nep-documents/'):return self.proxy()
        return super().do_GET()
    def do_POST(self):return self.proxy()
def main():
    worker=ThreadingHTTPServer(('127.0.0.1',0),Handler);View.worker=f'http://127.0.0.1:{worker.server_port}'
    static=ThreadingHTTPServer(('127.0.0.1',0),partial(View,directory=str(ROOT)))
    for server in (worker,static):threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            try:
                page=browser.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(f'http://127.0.0.1:{static.server_port}/static/nep-preview/project-documents.html?project=2027DPWH-Proposal-03421',wait_until='domcontentloaded')
                page.locator('#rows tr').first.wait_for();page.locator('#prepare').click();page.wait_for_function("document.querySelector('#status').textContent.includes('preparation finished')",timeout=30000)
                page.locator('#photos img').first.scroll_into_view_if_needed();page.wait_for_function("[...document.querySelectorAll('#photos img')].every(i=>i.complete&&i.naturalWidth>0)")
                result={'errors':errors,'costRows':page.locator('#rows tr').count(),'topRows':[page.locator('#rows tr').nth(i).inner_text() for i in range(2)],'rowStatus':page.locator('#rowStatus').inner_text(),'photoPages':page.locator('#photos img').count(),'status':page.locator('#status').inner_text()}
                output=Path(__file__).resolve().parents[1]/'analysis_output/burol_document_view_review.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
            finally:browser.close()
    finally:
        for server in (static,worker):server.shutdown();server.server_close()
if __name__=='__main__':main()
