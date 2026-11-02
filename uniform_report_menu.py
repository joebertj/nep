#!/usr/bin/env python3
"""Apply one menu and one final style block to all static budget reports."""
import json
import hashlib
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
RESEARCH_THEME_VERSION=hashlib.sha256((STATIC/'research-theme.css').read_bytes()).hexdigest()[:12]
RESEARCH_STATUS_VERSION=hashlib.sha256((STATIC/'research-status.js').read_bytes()).hexdigest()[:12]
LINKS=[('summary.html', 'Summary · investigative leads'), ('dpwh-OO2-hgab.html', 'DPWH · NEP → HGAB'), ('dpwh.html', 'DPWH Transparency'), ('congress.html', 'Project flags by district'), ('archive/congress-district-allocations.html', 'District allocations · HGAB 3rd'), ('flood-control.html', 'Flood-control pattern review'), ('repeats.html', 'Project repeat comparisons'), ('integrated.html', 'Historical'), ('out-of-place.html', 'Out of Place'), ('cost-per-km.html', 'Cost per meter'), ('cost-per-unit.html', 'Cost per Unit'), ('rcs.html', 'RCS · POW scope review'), ('mpb.html', 'MPB Flags'), ('mpb-barangay.html', 'MPB RTS'), ('barangay.html', 'Barangay allocations')]
NAV='<nav class="report-nav" aria-label="Budget report pages">'+''.join(f'<a href="{url}">{label}</a>' for url,label in LINKS)+'</nav>'
AI_CREDIT='<footer class="site-ai-credit"><p><strong>Sources:</strong> <a href="https://visualizations.bettergov.ph/sources" target="_blank" rel="noreferrer">Common source catalog</a>. Each page identifies the years and records used in that analysis.</p><p><a href="__BUDGET_TRIVIA_HREF__">Budget Trivia · play the game</a></p><p><strong>AI assistance:</strong> OpenAI Codex contributed to software implementation and data-processing workflows for this site. This credit does not represent independent verification of the underlying sources, calculations, or conclusions.</p></footer>'
MPB_SOURCE_FOOTER='''<footer class="mpb-source-footer" id="mpb-source-footer"><p><strong>Sources and credits</strong> · <a href="https://visualizations.bettergov.ph/sources" target="_blank" rel="noreferrer">Full source catalog for legacy and current ODV pages</a></p><p>GAA project records: <a href="https://budget-assets.bettergov.ph/gaa-explorer/manifest.json" target="_blank" rel="noreferrer">BetterGov GAA Explorer and integrated GAA datasets</a> (FY2016–FY2018 title-classified DPWH baseline; FY2017–FY2018 MPB candidate layer; FY2020–FY2026 integrated datasets). FY2027 MPB records: <a href="https://budget.bettergov.ph/hgab/2027/multi-purpose/map" target="_blank" rel="noreferrer">BetterGov HGAB Multi-purpose Buildings map</a>. Barangay names and identities use BetterGov's unified geographic reference list.</p><p>MPB base artwork: Kenney, <a href="https://kenney.nl/assets/isometric-tiles-buildings" target="_blank" rel="noreferrer">Isometric Tiles Buildings</a> and <a href="https://kenney.nl/assets/isometric-tiles-city" target="_blank" rel="noreferrer">Isometric Tiles City</a>, both CC0. District attribution review references the <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/" target="_blank" rel="noreferrer">CSIIIV DPWH–NEP–HGAB workbench</a>. Project rows and allocations are review evidence, not proof of completed buildings or spending.</p></footer>'''
CSS='''<style id="uniform-report-menu-style">
header{padding-left:clamp(16px,2vw,32px)!important;padding-right:clamp(16px,2vw,32px)!important}
header .report-nav{box-sizing:border-box!important;display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;grid-auto-rows:34px!important;align-content:start!important;gap:8px 10px!important;width:100%!important;max-width:none!important;height:118px!important;min-height:118px!important;margin:16px 0 0!important;padding:0!important;font:12px/1.1 system-ui,sans-serif!important}
header .report-nav a,header .report-nav a:visited{box-sizing:border-box!important;display:flex!important;align-items:center!important;justify-content:center!important;min-width:0!important;height:34px!important;margin:0!important;padding:4px 7px!important;color:#FCD116!important;background:transparent!important;border:1px solid #ffffff55!important;border-radius:8px!important;text-align:center!important;text-decoration:none!important;font:12px/1.1 system-ui,sans-serif!important;overflow-wrap:anywhere!important}
header .report-nav a:hover{color:#fff!important;background:#ffffff12!important;border-color:#FCD116!important}
header .report-nav a:focus-visible{outline:2px solid #FCD116!important;outline-offset:2px!important}
.chart-legend-no-rank{list-style:none!important;padding-left:0!important}.chart-legend-no-rank li{grid-template-columns:minmax(0,1fr) auto!important}.chart-legend-no-rank li>span:first-child{overflow-wrap:anywhere}
.site-ai-credit{box-sizing:border-box!important;width:100%!important;margin:36px 0 0!important;padding:14px clamp(16px,2vw,32px)!important;border-top:1px solid #BDBDBD!important;color:#5A6670!important;font:12px/1.55 system-ui,sans-serif!important}.site-ai-credit p{max-width:none!important;margin:0!important}.site-ai-credit p+p{margin-top:6px!important}.site-ai-credit a{color:#0038A8!important;text-underline-offset:2px!important}
.mpb-source-footer{box-sizing:border-box!important;width:100%!important;margin:36px 0 0!important;padding:16px clamp(16px,2vw,32px)!important;border-top:1px solid #BDBDBD!important;color:#5A6670!important;font:12px/1.55 system-ui,sans-serif!important}.mpb-source-footer p{max-width:none!important;margin:0 0 6px!important}.mpb-source-footer p:last-child{margin-bottom:0!important}.mpb-source-footer a{color:#0038A8!important;text-underline-offset:2px!important}
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

STATUS_CSS='''<style id="research-status-style">
.research-status{box-sizing:border-box;display:flex;justify-content:space-between;align-items:center;gap:6px 24px;width:100%;margin:0;padding:10px clamp(16px,2vw,32px);border-bottom:1px solid #E6D7A8;border-left:4px solid #FCD116;background:#FFF8E1;color:#212121;font:13px/1.5 system-ui,sans-serif}
.research-status p{margin:0!important}.research-status-copy{flex:1 1 640px}.research-status-meta{flex:0 1 auto;color:#616161;font-size:12px;white-space:nowrap;font-variant-numeric:tabular-nums}
@media(max-width:720px){.research-status{display:block}.research-status-meta{display:block;margin-top:4px!important;white-space:normal}}
</style>'''

def build_status():
    return (f'<aside class="research-status" role="note" aria-label="Research status">'
            '<p class="research-status-copy"><strong>Ongoing research.</strong> Figures are provisional and may change as documents are recovered, extracted data is corrected, records are reconciled, and calculations are checked against source documents. Use the deployment timestamp and commit shown here to identify this version; newer build details supersede older copies.</p>'
            '<p class="research-status-meta" data-site-build-meta>Deployment build information unavailable</p></aside>')

def apply_research_status(text,status=None):
    status=status or build_status()
    text=re.sub(r'<aside\b[^>]*class="research-status"[^>]*>.*?</aside>','',text,flags=re.S)
    text=re.sub(r'<style id="research-status-style">.*?</style>','',text,flags=re.S)
    text=re.sub(r'<script\b[^>]*id="research-status-script"[^>]*>\s*</script>','',text,flags=re.S)
    script=f'<script id="research-status-script" defer src="/static/nep-preview/research-status.js?v={RESEARCH_STATUS_VERSION}"></script>'
    text=text.replace('</head>',STATUS_CSS+script+'</head>',1)
    if '</header>' in text:
        text=text.replace('</header>','</header>'+status,1)
    return text

SHARE_BUILD_META_CSS='''<style id="share-build-meta-style">
.share-build-meta{box-sizing:border-box;display:flex;justify-content:flex-end;width:100%;margin:22px 0 0;padding:10px 0 0;border-top:1px solid #D8DEE2;color:#616161;font:12px/1.5 system-ui,sans-serif;font-variant-numeric:tabular-nums}
.share-build-meta a{color:#0038A8;text-underline-offset:2px}
@media(max-width:600px){.share-build-meta{font-size:11px;overflow-wrap:anywhere}}
</style>'''

def apply_share_build_meta(text):
    """Add the deploy-time timestamp and commit to standalone share cards."""
    text=re.sub(r'<(?:div|footer)\b[^>]*id="share-build-meta"[^>]*>.*?</(?:div|footer)>','',text,flags=re.S)
    text=re.sub(r'<style id="share-build-meta-style">.*?</style>','',text,flags=re.S)
    text=re.sub(r'<script\b[^>]*id="research-status-script"[^>]*>\s*</script>','',text,flags=re.S)
    script=f'<script id="research-status-script" defer src="/static/nep-preview/research-status.js?v={RESEARCH_STATUS_VERSION}"></script>'
    text=text.replace('</head>',SHARE_BUILD_META_CSS+script+'</head>',1)
    stamp='<footer id="share-build-meta" class="share-build-meta"><span data-site-build-meta>Loading deployment timestamp and commit…</span></footer>'
    if '</main>' in text:text=text.replace('</main>',stamp+'</main>',1)
    elif '</body>' in text:text=text.replace('</body>',stamp+'</body>',1)
    return text

def apply_mpb_source_footer(text):
    """Apply the shared source and asset credits to MPB pages."""
    text=re.sub(r'<footer\b[^>]*id="mpb-source-footer"[^>]*>.*?</footer>','',text,flags=re.S)
    if AI_CREDIT in text:
        return text.replace(AI_CREDIT,MPB_SOURCE_FOOTER+AI_CREDIT,1)
    if '</body>' in text:
        return text.replace('</body>',MPB_SOURCE_FOOTER+'</body>',1)
    return text

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

def apply_page(text,page=None,status=None):
    if page!='nia-irrigation.html':
        text=re.sub(r'href="nia-irrigation\.html(?:#([^"]+))?"',lambda m:'href="nia.html#'+('nia-detail-'+m[1] if m[1] else 'nia-detailed-irrigation')+'"',text)
    if page:
        from report_teasers import apply_page as apply_teaser
        text=apply_teaser(text,page)
    text=text.replace('const legend=`<ol class="chart-legend">${points.map((p,i)=>`<li><span class="chart-legend-number">${i+1}</span><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join(\'\')}</ol>`;', 'const legend=`<ol class="chart-legend chart-legend-no-rank">${points.map(p=>`<li><span>${esc(p.label)}</span><strong>${fmt(p.value)}</strong></li>`).join(\'\')}</ol>`;')
    text=normalize_header(text)
    theme_link=f'<link id="research-theme-style" rel="stylesheet" href="research-theme.css?v={RESEARCH_THEME_VERSION}">'
    if 'research-theme.css' not in text:
        text=text.replace('</head>',theme_link+'</head>',1)
    else:
        text=re.sub(r'<link\b(?=[^>]*research-theme\.css)[^>]*>',theme_link,text,count=1)
    text=re.sub(r'<body(?![^>]*\bclass=)([^>]*)>',r'<body class="bettergov-research"\1>',text,count=1)
    text=re.sub(r'<style id="(?:report-nav-layout|summary-nav-layout|uniform-report-menu-style)">.*?</style>','',text,flags=re.S)
    if re.search(r'<nav\b[^>]*class="report-nav"',text):
        text=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',lambda m:NAV,text,flags=re.S)
    else:
        text=text.replace('</header>',NAV+'</header>',1)
    if re.search(r'<nav\b[^>]*class="report-nav"',text):
        depth=max(0,len(Path(page).parts)-1) if page else 0
        trivia_href='../'*depth+'budget-trivia.html'
        trivia_link='<p><a href="'+trivia_href+'">Budget Trivia · play the game</a></p>'
        if 'Budget Trivia · play the game' not in text:
            footer=re.search(r'<footer\b[^>]*class="site-ai-credit"[^>]*>.*?</footer>',text,re.S)
            if footer:
                replacement=footer.group(0).replace('</footer>',trivia_link+'</footer>')
                text=text[:footer.start()]+replacement+text[footer.end():]
            else:
                credit=AI_CREDIT.replace('__BUDGET_TRIVIA_HREF__',trivia_href)
                text=text.replace('</body>',credit+'</body>',1)
    if page in {'mpb.html','mpb-barangay.html','mpb-base.html'}:
        text=apply_mpb_source_footer(text)
    text=text.replace('</head>',CSS+'</head>',1)
    return apply_research_status(text,status)

def apply():
    from merge_nia_pages import merge
    merge()
    from summary_evidence_links import apply as link_summary_evidence
    link_summary_evidence()
    from report_table_presentation import publish_assets,apply_page as table_presentation
    versions=publish_assets()
    results=[]
    status=build_status()
    for path in sorted(STATIC.glob('*.html')):
        if path.name in {'budget-trivia.html','pow.html'}:continue  # game and forensic pages intentionally use bespoke layouts; POW stays off-menu by request
        text=table_presentation(apply_page(path.read_text(),path.name,status),versions);path.write_text(text)
        if not re.search(r'<header\b',text) and re.search(r'<meta\s+http-equiv=["\']refresh',text,re.I):continue
        mirror=ROOT/'analysis_output'/path.name
        if mirror.exists():mirror.write_text(text)
        navs=re.findall(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',text,re.S)
        styles=re.findall(r'<style id="uniform-report-menu-style">.*?</style>',text,re.S)
        if navs!=[NAV] or styles!=[CSS]:raise ValueError('Menu differs: '+path.name)
        results.append({'page':path.name,'links':len(LINKS),'uniformMarkup':True,'uniformStyles':True})
    for path in STATIC.rglob('*.html'):
        if path.parent==STATIC or path.name=='budget-trivia.html':continue
        text=path.read_text(errors='ignore')
        if 'class="report-nav"' not in text:continue
        text=normalize_header(text)
        theme_link=f'<link id="research-theme-style" rel="stylesheet" href="research-theme.css?v={RESEARCH_THEME_VERSION}">'
        if 'research-theme.css' not in text:text=text.replace('</head>',theme_link+'</head>',1)
        else:text=re.sub(r'<link\b(?=[^>]*research-theme\.css)[^>]*>',theme_link,text,count=1)
        text=re.sub(r'<style id="uniform-report-menu-style">.*?</style>','',text,flags=re.S)
        text=text.replace('</head>',CSS+'</head>',1)
        path.write_text(apply_research_status(text,status))
    pow=STATIC/'pow.html'
    if pow.exists():
        text=pow.read_text(errors='ignore')
        if 'class="report-header-brand"' not in text:
            brand='<a class="report-header-brand" href="https://bettergov.ph/" aria-label="BetterGov home"><img src="https://assets.bettergov.ph/logos/webp/horizontal-black.webp" alt="BetterGov"></a>'
            text=text.replace('<header>', '<header>'+brand,1)
        theme_link=f'<link id="research-theme-style" rel="stylesheet" href="research-theme.css?v={RESEARCH_THEME_VERSION}">'
        if 'research-theme.css' not in text:text=text.replace('</head>',theme_link+'</head>',1)
        else:text=re.sub(r'<link\b(?=[^>]*research-theme\.css)[^>]*>',theme_link,text,count=1)
        pow.write_text(apply_research_status(text,status))
    report={'pages':results,'pageCount':len(results),'menuHeightsPx':{'desktop':118,'tablet':202,'mobile':328},'headerHeightsPx':{'desktop':361,'tablet':495,'mobile':647},'scope':'Generated markup and CSS audit; no browser rendering test.'}
    (ROOT/'analysis_output/report_menu_review.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':print(json.dumps(apply(),indent=2))
