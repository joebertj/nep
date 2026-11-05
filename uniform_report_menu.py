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
MENU_GROUPS=[
    ('Summary',[('summary.html','Summary · investigative leads')]),
    ('Budget 2027',[
        ('dpwh.html','DPWH Transparency'),
        ('congress.html','Project flags + district allocations'),
        ('flags.html','Flags'),
        ('undocumented-hgab.html','Undocumented HGAB'),('repeats.html','Project repeats'),
        ('out-of-place.html','Out of Place'),('cost-per-km.html','Cost per meter'),
        ('pccp-cost-per-unit.html','Cost Per Unit · DPWH Atlas'),
        ('cost-per-unit.html','Cost per Unit · peer comparison'),
        ('rcs.html','RCS · POW scope'),('mpb.html','MPB Flags'),('barangay.html','Barangay allocations'),
    ]),
    ('Historical',[
        ('flood-control.html','Flood-control pattern'),('repeats-historical.html','Project repeats'),
        ('integrated-district-allocations.html','District allocations'),
        ('mpb-barangay.html','MPB'),('mpb-historical.html','DPWH'),
        ('barangay-historical.html','Barangay'),('contractors.html','Contractors'),('connectivity.html','Road connectivity'),
    ]),
]
def render_menu_group(group, links):
    if len(links) == 1:
        url, _label = links[0]
        return f'<a class="report-nav-single" href="/static/nep-preview/{url}">{group}</a>'
    return ('<details class="report-nav-group"><summary>'+group+'</summary><div class="report-nav-links">'+
            ''.join(f'<a href="/static/nep-preview/{url}">{label}</a>' for url,label in links)+
            '</div></details>')
def page_nav(page):
    depth=max(0,len(Path(page).parts)-1) if page else 0
    if not depth:return NAV
    prefix='../'*depth
    return re.sub(r'href="(?!https?://|/|#)([^"]+)"',lambda m:'href="'+prefix+m[1]+'"',NAV)

NAV='<nav class="report-nav" aria-label="Budget report sections">'+''.join(
    render_menu_group(group, links) for group,links in MENU_GROUPS)+'</nav>'
MENU_BEHAVIOR_SCRIPT='''<script id="report-menu-exclusive-groups">(()=>{const groups=[...document.querySelectorAll('header .report-nav-group')];groups.forEach(group=>group.addEventListener('toggle',()=>{if(group.open)groups.forEach(other=>{if(other!==group)other.open=false})}))})();</script>'''
def apply_menu_behavior(text):
    text=re.sub(r'<script id="report-menu-exclusive-groups">.*?</script>','',text,flags=re.S)
    return text.replace('</body>',MENU_BEHAVIOR_SCRIPT+'</body>',1)
AI_CREDIT='<footer class="site-ai-credit"><p><strong>Sources:</strong> <a href="https://visualizations.bettergov.ph/sources" target="_blank" rel="noreferrer">Common source catalog</a>. Each page identifies the years and records used in that analysis.</p><p><a href="__BUDGET_TRIVIA_HREF__">Budget Trivia · play the game</a></p><p><strong>AI assistance:</strong> OpenAI Codex contributed to software implementation and data-processing workflows for this site. This credit does not represent independent verification of the underlying sources, calculations, or conclusions.</p></footer>'
MPB_SOURCE_FOOTER='''<footer class="mpb-source-footer" id="mpb-source-footer"><p><strong>Sources and credits</strong> · <a href="https://visualizations.bettergov.ph/sources" target="_blank" rel="noreferrer">Full source catalog for legacy and current ODV pages</a></p><p>GAA project records: <a href="https://budget-assets.bettergov.ph/gaa-explorer/manifest.json" target="_blank" rel="noreferrer">BetterGov GAA Explorer and integrated GAA datasets</a> (FY2016–FY2018 title-classified DPWH baseline; FY2017–FY2018 MPB candidate layer; FY2020–FY2026 integrated datasets). FY2027 MPB records: <a href="https://budget.bettergov.ph/hgab/2027/multi-purpose/map" target="_blank" rel="noreferrer">BetterGov HGAB Multi-purpose Buildings map</a>. Barangay names and identities use BetterGov's unified geographic reference list.</p><p>MPB base artwork: Kenney, <a href="https://kenney.nl/assets/isometric-tiles-buildings" target="_blank" rel="noreferrer">Isometric Tiles Buildings</a> and <a href="https://kenney.nl/assets/isometric-tiles-city" target="_blank" rel="noreferrer">Isometric Tiles City</a>, both CC0. District attribution review references the <a href="https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/" target="_blank" rel="noreferrer">CSIIIV DPWH–NEP–HGAB workbench</a>. Project rows and allocations are review evidence, not proof of completed buildings or spending.</p></footer>'''
CSS='''<style id="uniform-report-menu-style">
header{padding-left:clamp(16px,2vw,32px)!important;padding-right:clamp(16px,2vw,32px)!important}
header .report-nav{box-sizing:border-box!important;display:flex!important;align-items:center!important;flex-wrap:wrap!important;gap:8px!important;width:100%!important;max-width:none!important;height:auto!important;min-height:0!important;margin:12px 0 0!important;padding:0!important;font:13px/1.3 system-ui,sans-serif!important;position:relative!important;z-index:20!important}
header .report-nav-group{position:relative!important;min-width:130px!important;height:42px!important;margin:0!important;padding:0!important;border:1px solid #ffffff66!important;border-radius:9px!important;background:#0038A8!important}
header .report-nav-group:first-of-type{min-width:150px!important}
header .report-nav-group>summary{list-style:none!important;display:flex!important;position:relative!important;align-items:center!important;justify-content:center!important;gap:12px!important;height:40px!important;min-height:40px!important;padding:8px 30px!important;color:#FCD116!important;font:700 14px/1.2 system-ui,sans-serif!important;cursor:pointer!important}
header .report-nav-group>summary::-webkit-details-marker{display:none!important}
header .report-nav-group>summary::after{position:absolute!important;right:12px!important;content:'+'!important;color:#fff!important;font-size:17px!important;line-height:1!important}
header .report-nav-group[open]>summary::after{content:'−'!important}
header .report-nav-group>summary:hover{color:#fff!important}
header .report-nav-group>summary:focus-visible{outline:2px solid #FCD116!important;outline-offset:2px!important;border-radius:8px!important}
header .report-nav-links{position:absolute!important;top:calc(100% + 8px)!important;left:0!important;z-index:1000!important;display:grid!important;grid-template-columns:repeat(2,minmax(180px,1fr))!important;gap:5px!important;width:min(600px,calc(100vw - 32px))!important;max-height:min(70vh,560px)!important;overflow:auto!important;padding:10px!important;border:1px solid #ccd7e5!important;border-radius:12px!important;background:#fff!important;box-shadow:0 14px 36px #001b4d38!important}
header .report-nav-group:last-child .report-nav-links{left:0!important;right:auto!important;width:min(420px,calc(100vw - 32px))!important}
header .report-nav a,header .report-nav a:visited{box-sizing:border-box!important;display:flex!important;align-items:center!important;min-width:0!important;min-height:38px!important;margin:0!important;padding:8px 10px!important;color:#0038A8!important;background:#f6f8fb!important;border:1px solid #e0e6ef!important;border-radius:8px!important;text-align:left!important;text-decoration:none!important;font:13px/1.25 system-ui,sans-serif!important;overflow-wrap:anywhere!important}
header .report-nav>a.report-nav-single,header .report-nav>a.report-nav-single:visited{box-sizing:border-box!important;display:flex!important;align-items:center!important;justify-content:center!important;height:42px!important;min-height:42px!important;padding:8px 15px!important;border:1px solid #ffffff66!important;border-radius:9px!important;background:#0038A8!important;color:#FCD116!important;text-decoration:none!important;font:700 14px/1.2 system-ui,sans-serif!important}
header .report-nav>a.report-nav-single:hover{color:#fff!important}
header .report-nav>a.report-nav-single:focus-visible{outline:2px solid #FCD116!important;outline-offset:2px!important}
header .report-nav a:hover{color:#00246A!important;background:#eef3fb!important;border-color:#0038A8!important}
header .report-nav a:focus-visible{outline:2px solid #0038A8!important;outline-offset:2px!important}
.chart-legend-no-rank{list-style:none!important;padding-left:0!important}.chart-legend-no-rank li{grid-template-columns:minmax(0,1fr) auto!important}.chart-legend-no-rank li>span:first-child{overflow-wrap:anywhere}
.site-ai-credit{box-sizing:border-box!important;width:100%!important;margin:36px 0 0!important;padding:14px clamp(16px,2vw,32px)!important;border-top:1px solid #BDBDBD!important;color:#5A6670!important;font:12px/1.55 system-ui,sans-serif!important}.site-ai-credit p{max-width:none!important;margin:0!important}.site-ai-credit p+p{margin-top:6px!important}.site-ai-credit a{color:#0038A8!important;text-underline-offset:2px!important}
.mpb-source-footer{box-sizing:border-box!important;width:100%!important;margin:36px 0 0!important;padding:16px clamp(16px,2vw,32px)!important;border-top:1px solid #BDBDBD!important;color:#5A6670!important;font:12px/1.55 system-ui,sans-serif!important}.mpb-source-footer p{max-width:none!important;margin:0 0 6px!important}.mpb-source-footer p:last-child{margin-bottom:0!important}.mpb-source-footer a{color:#0038A8!important;text-underline-offset:2px!important}
@media(max-width:680px){header .report-nav-group{flex:1 1 calc(33.333% - 8px)!important;min-width:100px!important}header .report-nav-single{flex:1 1 calc(33.333% - 8px)!important;min-width:100px!important}header .report-nav-group>summary{justify-content:center!important;min-height:40px!important}header .report-nav-group>summary::after{position:absolute!important;right:14px!important}header .report-nav-links{grid-template-columns:1fr!important;width:min(480px,calc(100vw - 32px))!important}header .report-nav-group:last-child .report-nav-links{right:0!important;left:auto!important}}
body.bettergov-research>header.uniform-report-header{box-sizing:border-box!important;display:grid!important;grid-template-rows:auto auto!important;gap:14px!important;align-content:start!important;height:auto!important;min-height:0!important;padding-top:22px!important;padding-bottom:18px!important;border-bottom:3px solid #FCD116!important;overflow:visible!important}
body.bettergov-research>header.uniform-report-header{background:#00246A!important;color:#fff!important}
body.bettergov-research>header.uniform-report-header>.report-nav{margin:0!important;align-self:start!important}
body.bettergov-research>header .report-header-heading{display:flex!important;flex-direction:column!important;gap:6px!important;min-width:0!important;min-height:0!important}
body.bettergov-research>header .report-header-brand{display:flex!important;align-items:center!important;justify-self:start!important;width:122px!important;height:28px!important;padding:3px 7px!important;box-sizing:border-box!important;background:#fff!important;border-radius:5px!important}
body.bettergov-research>header .report-header-brand img{display:block!important;width:108px!important;height:22px!important;max-width:108px!important;object-fit:contain!important}
body.bettergov-research>header .report-header-heading>.eyebrow{margin:0!important;font:11px/20px system-ui,sans-serif!important;letter-spacing:.08em!important;text-transform:uppercase!important;color:#FCD116!important}
body.bettergov-research>header .report-header-heading>h1{margin:0!important;padding:0!important;color:#fff!important;font-size:clamp(25px,2.3vw,36px)!important;line-height:1.2!important;align-self:start!important}
body.bettergov-research>header .report-header-heading>p{margin:0!important;padding:0!important;color:#F5F5F5!important;font-size:15px!important;line-height:1.55!important;max-width:none!important;align-self:start!important}
body.bettergov-research main :is(.repeat-hero,.unit-hero,.page-hero,.history-hero,.mpb-hero,.driver-hero){box-sizing:border-box!important;min-height:300px!important;margin:20px 0 24px!important;padding:clamp(22px,3vw,32px)!important;border:0!important;border-left:8px solid #FCD116!important;border-radius:18px!important;background:linear-gradient(120deg,#00246A 0%,#0038A8 100%)!important;color:#fff!important;box-shadow:0 14px 34px #00246A22!important;align-content:center!important}
body.bettergov-research main :is(.repeat-hero,.unit-hero,.page-hero,.history-hero,.mpb-hero,.driver-hero) :is(h2,h3){color:#fff!important}
body.bettergov-research main :is(.repeat-hero,.unit-hero,.page-hero,.history-hero,.mpb-hero,.driver-hero) :is(p,span){color:#F5F5F5!important}
body.bettergov-research main :is(.repeat-hero,.unit-hero,.page-hero,.history-hero,.mpb-hero,.driver-hero) :is(.repeat-hero-kicker,.unit-hero-kicker,.history-hero-kicker,.mpb-hero-kicker,.eyebrow){color:#FCD116!important}
body.bettergov-research main :is(.repeat-hero,.unit-hero,.page-hero,.history-hero,.mpb-hero,.driver-hero) a{color:#FCD116!important;text-underline-offset:2px!important}
body.bettergov-research main :is(.repeat-hero-breakdown>div,.unit-hero-stats>div,.hero-metric,.history-hero-stats>div,.mpb-hero-stat,.historical-hero-metrics>div){box-sizing:border-box!important;min-height:106px!important;border:1px solid #ffffff55!important;border-radius:11px!important;background:#ffffff12!important;color:#F5F5F5!important}
body.bettergov-research main :is(.repeat-hero-breakdown,.unit-hero-stats,.hero-metrics,.history-hero-stats,.mpb-hero-stats,.historical-hero-metrics){align-items:stretch!important}
body.bettergov-research main :is(.repeat-hero-breakdown>div,.unit-hero-stats>div,.hero-metric,.history-hero-stats>div,.mpb-hero-stat,.historical-hero-metrics>div) strong{color:#FCD116!important}
@media(max-width:720px){body.bettergov-research main :is(.repeat-hero,.unit-hero,.page-hero,.history-hero,.mpb-hero,.driver-hero){min-height:260px!important}}
@media(max-width:900px){body.bettergov-research>header .report-header-brand{width:114px!important;height:26px!important}body.bettergov-research>header .report-header-brand img{width:100px!important;height:20px!important}body.bettergov-research>header .report-header-heading>h1{font-size:26px!important;line-height:1.25!important}body.bettergov-research>header .report-header-heading>p{font-size:14px!important}}
@media(max-width:560px){body.bettergov-research>header.uniform-report-header{padding-top:18px!important;padding-bottom:16px!important}body.bettergov-research>header .report-header-brand{width:106px!important;height:24px!important;padding:2px 6px!important}body.bettergov-research>header .report-header-brand img{width:92px!important;height:20px!important}body.bettergov-research>header .report-header-heading>h1{font-size:22px!important;line-height:1.2!important}body.bettergov-research>header .report-header-heading>p{font-size:13px!important;line-height:1.5!important}}
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
    kicker='<div class="eyebrow">BetterGov · Budget research</div>'
    extra_links=[]
    def unlink(match):
        extra_links.append(match[0])
        return ''
    teaser=re.sub(r'<a\b[^>]*>.*?</a>',unlink,paragraphs[0] if paragraphs else '<p></p>',flags=re.S)
    teaser=re.sub(r'\s*(?:·|\|)\s*</p>','</p>',teaser)
    teaser_content=re.sub(r'^<p\b[^>]*>|</p>$','',teaser.strip(),flags=re.S)
    teaser='<p class="report-header-teaser">'+teaser_content+'</p>'
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
        text=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',lambda m:page_nav(page),text,flags=re.S)
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
    return apply_menu_behavior(apply_research_status(text,status))

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
        results.append({'page':path.name,'groups':len(MENU_GROUPS),'links':sum(len(items) for _,items in MENU_GROUPS),'uniformMarkup':True,'uniformStyles':True})
    for path in STATIC.rglob('*.html'):
        if path.parent==STATIC or path.name=='budget-trivia.html':continue
        text=path.read_text(errors='ignore')
        if 'class="report-nav"' not in text:continue
        text=normalize_header(text)
        text=re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',lambda m:page_nav(path.relative_to(STATIC)),text,flags=re.S)
        theme_link=f'<link id="research-theme-style" rel="stylesheet" href="research-theme.css?v={RESEARCH_THEME_VERSION}">'
        if 'research-theme.css' not in text:text=text.replace('</head>',theme_link+'</head>',1)
        else:text=re.sub(r'<link\b(?=[^>]*research-theme\.css)[^>]*>',theme_link,text,count=1)
        text=re.sub(r'<style id="uniform-report-menu-style">.*?</style>','',text,flags=re.S)
        text=text.replace('</head>',CSS+'</head>',1)
        path.write_text(apply_menu_behavior(apply_research_status(text,status)))
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
    report={'pages':results,'pageCount':len(results),'menuGroups':[{'label':label,'links':len(items)} for label,items in MENU_GROUPS],'menuBehavior':'Mutually exclusive native collapsible groups; opening one closes the other; panels are scrollable and responsive.','scope':'Generated markup and CSS audit; no browser rendering test.'}
    (ROOT/'analysis_output/report_menu_review.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':print(json.dumps(apply(),indent=2))
