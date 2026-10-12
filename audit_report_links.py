#!/usr/bin/env python3
"""Audit local generated report links, assets and statically declared dynamic anchors."""
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
class Page(HTMLParser):
    def __init__(self,text):
        super().__init__();self.ids=Counter();self.links=[];self.feed(text)
        # Existing builders generate program sections at runtime from configs.
        for prefix in re.findall(r"section\.id\s*=\s*['\"]([^'\"]+)['\"]\s*\+\s*c\.id",text):
            for ident in re.findall(r"\{id:\s*['\"]([^'\"]+)['\"]",text):
                if prefix=='mpb-' and ident=='repeats' and "configs.filter(c=>c.id!=='repeats')" in text:continue
                self.ids[prefix+ident]+=1
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if a.get('id'):self.ids[a['id']]+=1
        if tag=='a' and a.get('name'):self.ids[a['name']]+=1
        for field in ('href','src'):
            if a.get(field):self.links.append((tag,field,a[field]))

def audit():
    pages={p:Page(p.read_text()) for p in STATIC.glob('*.html')}
    failures=[];skips=[];checked=0;anchors=0
    for source,page in pages.items():
        for tag,field,url in page.links:
            parts=urlsplit(url)
            if parts.scheme or parts.netloc or url.startswith(('data:','javascript:')):continue
            path=unquote(parts.path)
            if path.startswith('/'):
                if path.startswith('/static/'):target=ROOT.parent/'open-data-visualization'/path.lstrip('/')
                else:skips.append({'source':source.name,'url':url,'reason':'Application route outside static report scope'});continue
            else:target=(source.parent/path).resolve() if path else source
            if target.is_dir():target=target/'index.html'
            checked+=1
            if not target.exists():failures.append({'source':source.name,'url':url,'reason':'Missing local file'});continue
            if parts.fragment and target.suffix=='.html':
                anchors+=1
                dest=pages.get(target)
                if dest is None:dest=Page(target.read_text())
                if unquote(parts.fragment) not in dest.ids:failures.append({'source':source.name,'url':url,'reason':'Missing section anchor'})
    json_pages=[]
    def visit(value,source):
        if isinstance(value,dict):
            for k,v in value.items():
                if k in ('page','href','url') and isinstance(v,str) and re.match(r'^[\w-]+\.html(?:#.*)?$',v):json_pages.append((source,v))
                else:visit(v,source)
        elif isinstance(value,list):
            for v in value:visit(v,source)
    for name in ['summary-data.json','line-item-review-queue.json']:
        p=STATIC/name
        if p.exists():visit(json.loads(p.read_text()),name)
    for source,url in json_pages:
        parts=urlsplit(url);target=STATIC/parts.path
        if target not in pages or (parts.fragment and parts.fragment not in pages[target].ids):failures.append({'source':source,'url':url,'reason':'Missing JSON page/anchor target'})
    result={'pages':len(pages),'checkedLocalLinksAndAssets':checked,'checkedHtmlAnchorLinks':anchors,'checkedJsonPageLinks':len(json_pages),'broken':failures,'duplicateIds':{p.name:[k for k,n in page.ids.items() if n>1] for p,page in pages.items() if any(n>1 for n in page.ids.values())},'unverifiedApplicationRoutes':skips,'limits':'Local HTML/file audit plus builder-declared dynamic section IDs and JSON page references; external URLs and browser interactions are not checked.'}
    (ROOT/'analysis_output/report_link_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result
if __name__=='__main__':print(json.dumps(audit(),ensure_ascii=False,indent=2))
