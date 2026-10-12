#!/usr/bin/env python3
"""Apply one menu and one final style block to all static budget reports."""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
LINKS=[('summary.html', 'Summary · investigative leads'), ('congress.html', 'Congressional District Allocations'), ('dpwh.html', 'DPWH · NEP patterns'), ('repeats.html', 'Project repeat comparisons'), ('dpwh-hgab.html', 'DPWH · NEP → HGAB (3rd)'), ('dpwh-hgab-comparison.html', 'DPWH · HGAB 2nd vs 3rd'), ('mpb.html', 'MPB · Multi-purpose buildings'), ('cost-per-km.html', 'Cost per meter'), ('nia-irrigation.html', 'NIA irrigation'), ('deped.html', 'DepEd'), ('rcs.html', 'RCS · rainfall scenario'), ('fmr.html', 'FMR'), ('nia.html', 'NIA'), ('hfep.html', 'HFEP'), ('budget-innovations.html', 'Budget Innovations')]
NAV='<nav class="report-nav" aria-label="Budget report pages">'+''.join(f'<a href="{url}">{label}</a>' for url,label in LINKS)+'</nav>'
CSS='''<style id="uniform-report-menu-style">
header{padding-left:clamp(16px,2vw,32px)!important;padding-right:clamp(16px,2vw,32px)!important}
header .report-nav{box-sizing:border-box!important;display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;grid-auto-rows:34px!important;align-content:start!important;gap:8px 10px!important;width:100%!important;max-width:none!important;height:118px!important;min-height:118px!important;margin:16px 0 0!important;padding:0!important;font:12px/1.1 system-ui,sans-serif!important}
header .report-nav a,header .report-nav a:visited{box-sizing:border-box!important;display:flex!important;align-items:center!important;justify-content:center!important;min-width:0!important;height:34px!important;margin:0!important;padding:4px 7px!important;color:#a7ddd1!important;background:transparent!important;border:1px solid #ffffff55!important;border-radius:8px!important;text-align:center!important;text-decoration:none!important;font:12px/1.1 system-ui,sans-serif!important;overflow-wrap:anywhere!important}
header .report-nav a:hover{color:#fff!important;background:#ffffff12!important;border-color:#a7ddd1!important}
header .report-nav a:focus-visible{outline:2px solid #a7ddd1!important;outline-offset:2px!important}
@media(max-width:900px){header .report-nav{grid-template-columns:repeat(3,minmax(0,1fr))!important;height:202px!important;min-height:202px!important}}
@media(max-width:560px){header .report-nav{grid-template-columns:repeat(2,minmax(0,1fr))!important;height:328px!important;min-height:328px!important}}
</style>'''

def apply_page(text):
    text=re.sub(r'<style id="(?:report-nav-layout|summary-nav-layout|uniform-report-menu-style)">.*?</style>','',text,flags=re.S)
    if re.search(r'<nav\b[^>]*class="report-nav"',text):
        text=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',lambda m:NAV,text,flags=re.S)
    else:
        text=text.replace('</header>',NAV+'</header>',1)
    return text.replace('</head>',CSS+'</head>',1)

def apply():
    results=[]
    for path in sorted(STATIC.glob('*.html')):
        text=apply_page(path.read_text());path.write_text(text)
        mirror=ROOT/'analysis_output'/path.name
        if mirror.exists():mirror.write_text(text)
        navs=re.findall(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',text,re.S)
        styles=re.findall(r'<style id="uniform-report-menu-style">.*?</style>',text,re.S)
        if navs!=[NAV] or styles!=[CSS]:raise ValueError('Menu differs: '+path.name)
        results.append({'page':path.name,'links':len(LINKS),'uniformMarkup':True,'uniformStyles':True})
    report={'pages':results,'pageCount':len(results),'menuHeightsPx':{'desktop':118,'tablet':202,'mobile':328},'scope':'Generated markup and CSS audit; no browser rendering test.'}
    (ROOT/'analysis_output/report_menu_review.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':print(json.dumps(apply(),indent=2))
