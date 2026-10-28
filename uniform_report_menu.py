#!/usr/bin/env python3
"""Apply one menu and one final style block to all static budget reports."""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
LINKS=[('summary.html', 'Summary · investigative leads'), ('congress.html', 'Congressional District Allocations'), ('cost-per-km.html', 'Cost per meter'), ('repeats.html', 'Project repeat comparisons'), ('dpwh-hgab.html', 'DPWH · NEP → HGAB (3rd)'), ('rcs.html', 'RCS · POW scope review'), ('mpb.html', 'MPB · Multi-purpose buildings'), ('dpwh.html', 'DPWH POWs'), ('nia.html', 'NIA · irrigation and named projects'), ('deped.html', 'DepEd'), ('fmr.html', 'FMR'), ('hfep.html', 'HFEP'), ('budget-innovations.html', 'Budget Innovations'), ('out-of-place.html', 'Out of Place'), ('https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#compare', 'Budget stage comparisons ↗')]
NAV='<nav class="report-nav" aria-label="Budget report pages">'+''.join(f'<a href="{url}">{label}</a>' for url,label in LINKS)+'</nav>'
CSS='''<style id="uniform-report-menu-style">
header{padding-left:clamp(16px,2vw,32px)!important;padding-right:clamp(16px,2vw,32px)!important}
header .report-nav{box-sizing:border-box!important;display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;grid-auto-rows:34px!important;align-content:start!important;gap:8px 10px!important;width:100%!important;max-width:none!important;height:118px!important;min-height:118px!important;margin:16px 0 0!important;padding:0!important;font:12px/1.1 system-ui,sans-serif!important}
header .report-nav a,header .report-nav a:visited{box-sizing:border-box!important;display:flex!important;align-items:center!important;justify-content:center!important;min-width:0!important;height:34px!important;margin:0!important;padding:4px 7px!important;color:#FCD116!important;background:transparent!important;border:1px solid #ffffff55!important;border-radius:8px!important;text-align:center!important;text-decoration:none!important;font:12px/1.1 system-ui,sans-serif!important;overflow-wrap:anywhere!important}
header .report-nav a:hover{color:#fff!important;background:#ffffff12!important;border-color:#FCD116!important}
header .report-nav a:focus-visible{outline:2px solid #FCD116!important;outline-offset:2px!important}
.chart-legend-no-rank{list-style:none!important;padding-left:0!important}.chart-legend-no-rank li{grid-template-columns:minmax(0,1fr) auto!important}.chart-legend-no-rank li>span:first-child{overflow-wrap:anywhere}
@media(max-width:900px){header .report-nav{grid-template-columns:repeat(3,minmax(0,1fr))!important;height:202px!important;min-height:202px!important}}
@media(max-width:560px){header .report-nav{grid-template-columns:repeat(2,minmax(0,1fr))!important;height:328px!important;min-height:328px!important}}
body.bettergov-research>header.uniform-report-header{box-sizing:border-box!important;display:grid!important;grid-template-rows:176px 118px!important;gap:16px!important;align-content:start!important;height:361px!important;min-height:361px!important;padding-top:24px!important;padding-bottom:24px!important;border-bottom:3px solid #FCD116!important}
body.bettergov-research>header.uniform-report-header>.report-nav{margin:0!important;align-self:start!important}
body.bettergov-research>header .report-header-heading{display:grid!important;grid-template-rows:28px 20px 58px 1fr!important;gap:6px!important;min-width:0!important;min-height:0!important}
body.bettergov-research>header .report-header-brand{display:flex!important;align-items:center!important;justify-self:start!important;width:122px!important;height:28px!important;padding:3px 7px!important;box-sizing:border-box!important;background:#fff!important;border-radius:5px!important}
body.bettergov-research>header .report-header-brand img{display:block!important;width:108px!important;height:22px!important;max-width:108px!important;object-fit:contain!important}
body.bettergov-research>header .report-header-heading>.eyebrow{margin:0!important;font:11px/20px system-ui,sans-serif!important;letter-spacing:.08em!important;text-transform:uppercase!important;color:#FCD116!important}
body.bettergov-research>header .report-header-heading>h1{margin:0!important;padding:0!important;font-size:clamp(25px,2.3vw,36px)!important;line-height:1.2!important;align-self:start!important}
body.bettergov-research>header .report-header-heading>p{margin:0!important;padding:0!important;font-size:15px!important;line-height:1.55!important;max-width:none!important;align-self:start!important}
@media(max-width:900px){body.bettergov-research>header.uniform-report-header{height:495px!important;min-height:495px!important;grid-template-rows:226px 202px!important}body.bettergov-research>header .report-header-heading{grid-template-rows:26px 18px 66px 1fr!important;gap:6px!important}body.bettergov-research>header .report-header-brand{width:114px!important;height:26px!important}body.bettergov-research>header .report-header-brand img{width:100px!important;height:20px!important}body.bettergov-research>header .report-header-heading>h1{font-size:26px!important;line-height:1.25!important}body.bettergov-research>header .report-header-heading>p{font-size:14px!important}}
@media(max-width:560px){body.bettergov-research>header.uniform-report-header{height:647px!important;min-height:647px!important;padding-top:20px!important;padding-bottom:20px!important;grid-template-rows:260px 328px!important}body.bettergov-research>header .report-header-heading{grid-template-rows:26px 18px 68px 1fr!important;gap:6px!important}body.bettergov-research>header .report-header-brand{width:106px!important;height:24px!important;padding:2px 6px!important}body.bettergov-research>header .report-header-brand img{width:92px!important;height:20px!important}body.bettergov-research>header .report-header-heading>h1{font-size:22px!important;line-height:1.2!important}body.bettergov-research>header .report-header-heading>p{font-size:13px!important;line-height:1.5!important}}
</style>'''

def normalize_header(text):
    match=re.search(r'<header\b[^>]*>(.*?)</header>',text,re.S)
    if not match:return text
    content=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>','',match[1],flags=re.S)
    title=re.search(r'<h1\b[^>]*>.*?</h1>',content,re.S)
    paragraphs=re.findall(r'<p\b[^>]*>.*?</p>',content,re.S)
    eyebrow=re.search(r'<div\b[^>]*class="eyebrow"[^>]*>.*?</div>',content,re.S)
    kicker=eyebrow[0] if eyebrow else '<div class="eyebrow">BetterGov · Budget research</div>'
    extra_links=[]
    def unlink(match):
        extra_links.append(match[0])
        return ''
    teaser=re.sub(r'<a\b[^>]*>.*?</a>',unlink,paragraphs[0] if paragraphs else '<p></p>',flags=re.S)
    teaser=re.sub(r'\s*(?:·|\|)\s*</p>','</p>',teaser)
    kicker=re.sub(r'<a\b[^>]*>.*?</a>',unlink,kicker,flags=re.S)
    brand='<a class="report-header-brand" href="https://bettergov.ph/" aria-label="BetterGov home"><img src="https://assets.bettergov.ph/logos/webp/horizontal-black.webp" alt="BetterGov"></a>'
    heading='<div class="report-header-heading">'+brand+kicker+(title[0] if title else '')+teaser+'</div>'
    text=text[:match.start()]+'<header class="uniform-report-header">'+heading+NAV+'</header>'+text[match.end():]
    # Source notes and supplemental jumps remain accessible without changing header height.
    previous=re.search(r'<div id="report-header-notes"[^>]*>(.*?)</div>',text,re.S)
    notes=(previous[1] if previous else '')+''.join(paragraphs[1:])+('<p>'+ ' · '.join(extra_links)+'</p>' if extra_links else '')
    text=re.sub(r'<div id="report-header-notes"[^>]*>.*?</div>','',text,flags=re.S)
    if notes:
        block='<div id="report-header-notes">'+notes+'</div>'
        index=text.rfind('</footer>')
        if index>=0:text=text[:index]+block+text[index:]
        else:text=text.replace('</body>','<footer>'+block+'</footer></body>',1)
    return text

def apply_page(text,page=None):
    if page!='nia-irrigation.html':
        text=re.sub(r'href="nia-irrigation\.html(?:#([^"]+))?"',lambda m:'href="nia.html#'+('nia-detail-'+m[1] if m[1] else 'nia-detailed-irrigation')+'"',text)
    if page:
        from report_teasers import apply_page as apply_teaser
        text=apply_teaser(text,page)
    text=text.replace('const legend=`<ol class="chart-legend">${points.map((p,i)=>`<li><span class="chart-legend-number">${i+1}</span><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join(\'\')}</ol>`;', 'const legend=`<ol class="chart-legend chart-legend-no-rank">${points.map(p=>`<li><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join(\'\')}</ol>`;')
    text=normalize_header(text)
    text=re.sub(r'<style id="(?:report-nav-layout|summary-nav-layout|uniform-report-menu-style)">.*?</style>','',text,flags=re.S)
    if re.search(r'<nav\b[^>]*class="report-nav"',text):
        text=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',lambda m:NAV,text,flags=re.S)
    else:
        text=text.replace('</header>',NAV+'</header>',1)
    return text.replace('</head>',CSS+'</head>',1)

def apply():
    from merge_nia_pages import merge
    merge()
    from summary_evidence_links import apply as link_summary_evidence
    link_summary_evidence()
    from report_table_presentation import publish_assets,apply_page as table_presentation
    versions=publish_assets()
    results=[]
    for path in sorted(STATIC.glob('*.html')):
        if path.name=='budget-trivia.html':continue  # secret quiz page intentionally has no shared menu
        text=table_presentation(apply_page(path.read_text(),path.name),versions);path.write_text(text)
        mirror=ROOT/'analysis_output'/path.name
        if mirror.exists():mirror.write_text(text)
        navs=re.findall(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',text,re.S)
        styles=re.findall(r'<style id="uniform-report-menu-style">.*?</style>',text,re.S)
        if navs!=[NAV] or styles!=[CSS]:raise ValueError('Menu differs: '+path.name)
        results.append({'page':path.name,'links':len(LINKS),'uniformMarkup':True,'uniformStyles':True})
    report={'pages':results,'pageCount':len(results),'menuHeightsPx':{'desktop':118,'tablet':202,'mobile':328},'headerHeightsPx':{'desktop':361,'tablet':495,'mobile':647},'scope':'Generated markup and CSS audit; no browser rendering test.'}
    (ROOT/'analysis_output/report_menu_review.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':print(json.dumps(apply(),indent=2))
