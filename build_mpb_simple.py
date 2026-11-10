#!/usr/bin/env python3
"""Own mpb-simple.html: five static, accessible MPB infographics."""
from collections import Counter
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
PAGE = 'mpb-simple.html'


def load(name):
    return json.loads((OUT / name).read_text(encoding='utf-8'))


def collect():
    analysis = load('mpb_analysis.json')
    regional = load('mpb-regional-province-data.json')
    base = load('mpb-barangay-base-data.json')
    history, current = Counter(), Counter()
    returning = first = 0
    for place in base['barangays']:
        groups = place.get('buildings', [])
        earlier = sum(any(2015 <= int(e.get('year') or 0) <= 2026 for e in g.get('levelHistory', [])) for g in groups)
        now = sum(any(int(e.get('year') or 0) == 2027 for e in g.get('levelHistory', [])) for g in groups)
        history[earlier] += 1
        if now:
            current[now] += 1
            returning += earlier > 0
            first += earlier == 0
    official = regional['summary']['officialBarangays']
    if sum(history.values()) != official:
        raise ValueError('Historical barangay universe does not reconcile with the regional page')
    fy = analysis['summary']['fy2027HistoricalDistribution']
    if (sum(current.values()), sum(k*v for k, v in current.items()), returning, first) != (
        fy['coveredBarangays'], fy['historicalTitleMatches'], fy['previouslyMappedBarangays'], fy['firstTimeBarangays']
    ):
        raise ValueError('FY2027 mapped title/barangay totals do not reconcile with the MPB page')
    docs = analysis['summary']['fy2027DocumentCoverage']
    if sum(x['projectRows'] for x in docs['countsByMatchedTypeCount']) != docs['denominatorProjectRows']:
        raise ValueError('Document-type distribution does not reconcile')
    complete = sum(x['projectRows'] for x in docs['countsByMatchedTypeCount'] if x['matchedTypeCount'] >= 4)
    if (complete, docs['denominatorProjectRows'] - complete) != (docs['completeDocumentProjectRows'], docs['incompleteDocumentProjectRows']):
        raise ValueError('Document completeness counts do not reconcile')
    tests = regional['statisticalTests']['povertyAssociations']
    excluded = set(tests['excludedForBoundaryOverlap'])
    points = []
    for region in regional['regions']:
        poverty = regional['povertyIncidence2023AmongFamiliesPct'].get(region['region'])
        if region['region'] not in excluded and poverty is not None:
            points.append({'region': region['region'], 'povertyPct': poverty,
                           'allocationPerBarangayPesos': region['allocationPesos'] / region['officialBarangays']})
    if len(points) != tests['n']:
        raise ValueError('Poverty chart does not reconcile with its statistical test')
    return {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'recipientBarangays2027': {'returning': returning, 'firstTime': first, 'total': returning + first},
        'documents2027': docs,
        'coverage2027': {'officialBarangays': official, 'recipientBarangays': sum(current.values()),
                         'titleBarangayMatches': sum(k*v for k, v in current.items()),
                         'barangaysWithMultipleTitles': sum(v for k, v in current.items() if k > 1)},
        'history2015To2026': {'officialBarangays': official, 'none': history[0],
                              'oneToThree': sum(v for k, v in history.items() if 1 <= k <= 3),
                              'fourOrMore': sum(v for k, v in history.items() if k >= 4)},
        'poverty2015To2027': {'points': points, 'tests': tests, 'dataSnapshotUtc': regional['generatedAtUtc']},
        'sourceSha256': {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in
                         ['mpb_analysis.json', 'mpb-regional-province-data.json', 'mpb-barangay-base-data.json']},
    }


ICONS = '''<svg class="icon-definitions" aria-hidden="true" width="0" height="0"><defs>
<symbol id="community-icon" viewBox="0 0 48 48"><path d="M10 22 24 10l14 12v20H10Z" fill="currentColor"/><path d="M6 23 24 7l18 16" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M21 29h7v13h-7zM14 24h5v5h-5zM31 24h4v5h-4z" fill="#fff"/><circle cx="5" cy="32" r="3" fill="currentColor"/><path d="M5 37v7M2 40h6" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></symbol>
<symbol id="stack-icon" viewBox="0 0 48 48"><use href="#community-icon" x="12" y="0" width="32" height="32"/><use href="#community-icon" x="6" y="8" width="32" height="32"/><use href="#community-icon" x="0" y="16" width="32" height="32"/></symbol>
<symbol id="folder-icon" viewBox="0 0 120 110"><path d="M9 28h40l10 10h52v61H9Z" fill="currentColor"/><rect x="23" y="10" width="72" height="70" rx="5" fill="#fff" stroke="currentColor" stroke-width="4"/><path d="M36 28h43M36 40h43M36 52h25" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M9 59h102l-9 43H18Z" fill="currentColor"/><path d="m45 81 10 9 22-22" stroke="#fff" stroke-width="6" fill="none" stroke-linejoin="round"/></symbol>
<symbol id="partial-folder-icon" viewBox="0 0 120 110"><path d="M9 28h40l10 10h52v61H9Z" fill="currentColor" opacity=".15"/><rect x="23" y="10" width="72" height="70" rx="5" fill="#fff" stroke="currentColor" stroke-width="4" stroke-dasharray="7 5"/><path d="M36 28h43M36 40h43" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M9 59h102l-9 43H18Z" fill="currentColor"/><path d="M48 82h24" stroke="#fff" stroke-width="6" stroke-linecap="round"/></symbol>
</defs></svg>'''


def pictogram(bands, label):
    icons = []
    for count, style, symbol in bands:
        icons.extend(f'<svg class="unit {style}" viewBox="0 0 48 48" aria-hidden="true"><use href="#{symbol}"/></svg>' for _ in range(count))
    if len(icons) != 100:
        raise ValueError('Pictograms must contain 100 rounded units')
    return f'<div class="pictogram" role="img" aria-label="{escape(label)}">' + ''.join(icons) + '</div>'


def legend(items):
    return '<div class="simple-legend">' + ''.join(f'<span><i class="swatch {style}"></i>{label}</span>' for style, label in items) + '</div>'


def details(text, link, label):
    return f'<details class="computations"><summary>Sources &amp; exact figures</summary><p>{text}</p><a href="{link}">{label} ↗</a></details>'


def card(number, period, headline, graphic, takeaway, methods):
    return f'''<section class="simple-panel" id="infographic-{number}">
<div class="simple-card-heading"><span class="simple-step">0{number}</span><span class="simple-period">{period}</span></div>
<h2>{headline}</h2><figure>{graphic}<figcaption>{takeaway}</figcaption></figure>{methods}</section>'''


def scatter(points):
    width, height = 760, 400
    left, right, top, bottom = 42, 28, 48, 60
    xmax = max(p['povertyPct'] for p in points) * 1.08
    ymax = max(p['allocationPerBarangayPesos'] for p in points) * 1.08
    X = lambda x: left + x/xmax*(width-left-right)
    Y = lambda y: height-bottom-y/ymax*(height-top-bottom)
    mx = sum(p['povertyPct'] for p in points)/len(points)
    my = sum(p['allocationPerBarangayPesos'] for p in points)/len(points)
    slope = sum((p['povertyPct']-mx)*(p['allocationPerBarangayPesos']-my) for p in points)/sum((p['povertyPct']-mx)**2 for p in points)
    intercept = my-slope*mx
    grid = ''.join(f'<line x1="{left}" y1="{Y(ymax*q):.2f}" x2="{width-right}" y2="{Y(ymax*q):.2f}" stroke="#E5EAF3"/>' for q in (0, .25, .5, .75, 1))
    dots = ''.join(f'<circle cx="{X(p["povertyPct"]):.2f}" cy="{Y(p["allocationPerBarangayPesos"]):.2f}" r="8" fill="#0038A8" stroke="#fff" stroke-width="2"><title>{escape(p["region"])}: {p["povertyPct"]:.1f}% poverty; ₱{p["allocationPerBarangayPesos"]/1e6:.2f}M per official barangay</title></circle>' for p in points)
    return f'''<svg class="poverty-plot" viewBox="0 0 {width} {height}" role="img" aria-label="Regional poverty versus allocation per official barangay: the overall relationship is downward."><defs><clipPath id="poverty-clip"><rect x="{left}" y="{top}" width="{width-left-right}" height="{height-top-bottom}"/></clipPath></defs>{grid}<text x="{left}" y="24" class="axis-label">More allocation per barangay ↑</text><line x1="{left}" y1="{Y(0)}" x2="{width-right}" y2="{Y(0)}" stroke="#8A97AA"/><line x1="{left}" y1="{top}" x2="{left}" y2="{Y(0)}" stroke="#8A97AA"/><g clip-path="url(#poverty-clip)"><line x1="{X(0)}" y1="{Y(intercept)}" x2="{X(xmax)}" y2="{Y(intercept+slope*xmax)}" stroke="#B45309" stroke-width="3" stroke-dasharray="8 8"/></g>{dots}<text x="{left}" y="{height-20}" class="axis-label">Lower poverty</text><text x="{width-right}" y="{height-20}" text-anchor="end" class="axis-label">Higher poverty →</text></svg>'''


CSS = '''<style id="mpb-simple-style">
*{box-sizing:border-box}body{margin:0;background:#F4F6FA;color:#17233B;font-family:Inter,system-ui,sans-serif}header{background:#00246A;color:#fff;padding:35px 5vw}header h1{font-size:clamp(34px,5vw,60px);line-height:1.1;max-width:900px;margin:0}header p{max-width:800px}main.simple-main{max-width:1200px;margin:auto;padding:30px clamp(16px,4vw,40px)}.simple-intro{font-size:clamp(20px,2.6vw,30px);line-height:1.4;max-width:920px;margin:20px 0 35px;font-weight:600}.simple-panel{background:#fff;border:1px solid #DFE5EF;border-radius:20px;padding:clamp(22px,4vw,48px);margin:0 0 30px;box-shadow:0 8px 25px #00246A06;break-inside:avoid;scroll-margin-top:24px}.simple-card-heading{display:flex;align-items:center;gap:14px;margin-bottom:20px}.simple-step{background:#00246A;color:#fff;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-size:13px;font-weight:800}.simple-period{color:#616D81;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}.simple-panel h2{font-size:clamp(26px,3.8vw,42px)!important;line-height:1.15!important;max-width:900px;margin:0 0 25px!important;letter-spacing:-.03em}.simple-panel figure{margin:0}.simple-panel figcaption{font-size:clamp(17px,2vw,22px);line-height:1.5;color:#33425B;margin:25px 0 0}.simple-panel .big-fraction{font-size:clamp(52px,9vw,100px);font-weight:850;line-height:1;letter-spacing:-.07em;color:#00246A;margin:5px 0 28px}.simple-panel .big-fraction small{font-size:.25em;font-weight:650;letter-spacing:0;color:#616D81}.icon-definitions{position:absolute;width:0;height:0;overflow:hidden}.pictogram{display:grid;grid-template-columns:repeat(20,minmax(0,1fr));gap:7px}.pictogram .unit{display:block;width:100%;height:auto;aspect-ratio:1}.blue{color:#0038A8}.yellow{color:#BA8900}.muted-icon{color:#D1D7E1}.light-blue{color:#91B0E0}.simple-legend{display:flex;flex-wrap:wrap;gap:10px 24px;margin:20px 0 0;font-size:14px;color:#40516D}.simple-legend>span{display:inline-flex;gap:8px;align-items:center}.swatch{display:inline-block;width:11px;height:11px;background:currentColor;border-radius:3px;flex-shrink:0}.swatch.blue{background:#0038A8}.swatch.yellow{background:#BA8900}.swatch.muted-icon{background:#D1D7E1}.swatch.light-blue{background:#91B0E0}.folders{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(10px,4vw,45px);max-width:720px;margin:auto}.folders svg{width:100%;height:auto}.coverage-pair{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;text-align:center;gap:12px;max-width:650px;margin:30px auto}.coverage-pair strong{display:block;font-size:clamp(25px,5vw,46px);color:#00246A;line-height:1.2}.coverage-pair span{font-size:13px;color:#616D81}.coverage-pair .pair-separator{font-size:26px;color:#8A97AA}.poverty-plot{display:block;width:100%;height:auto;max-height:none}.axis-label{font:16px system-ui;fill:#596A84}.computations{border-top:1px solid #E2E7F0;margin-top:25px;padding-top:15px;font-size:13px;color:#596A84}.computations summary{cursor:pointer;font-size:12px;font-weight:650}.computations p{max-width:950px;line-height:1.65}.simple-main a{color:#0038A8}.simple-footer{font-size:13px;color:#596A84;line-height:1.6;padding:15px 0 35px}.simple-links{display:flex;gap:12px 22px;flex-wrap:wrap}.simple-download{display:inline-block;padding:10px 15px;background:#0038A8;color:#fff!important;border-radius:8px;text-decoration:none;font-weight:650;margin-bottom:16px}@media(max-width:650px){.pictogram{grid-template-columns:repeat(10,minmax(0,1fr));gap:6px}.simple-panel{border-radius:14px}.simple-legend{font-size:12px;gap:8px 12px}.axis-label{font-size:17px}}@media print{header nav,.computations,.simple-download{display:none}.simple-panel{box-shadow:none;break-inside:avoid}main.simple-main{padding:0}.pictogram{grid-template-columns:repeat(20,minmax(0,1fr))}*{print-color-adjust:exact}}
</style>'''


def build():
    data = collect()
    recipients, docs, cov, hist, poverty = (data[k] for k in ('recipientBarangays2027', 'documents2027', 'coverage2027', 'history2015To2026', 'poverty2015To2027'))
    total = recipients['total']
    repeat_pct = round(100*recipients['returning']/total)
    graphic = '<div class="big-fraction">3 in 4</div>' + pictogram(
        [(repeat_pct, 'blue', 'community-icon'), (100-repeat_pct, 'yellow', 'community-icon')],
        f'{recipients["returning"]:,} of {total:,} FY2027 recipient barangays have earlier mapped MPB records; rounded to 100 icons.')
    graphic += legend([('blue', 'Earlier MPB records'), ('yellow', 'First mapped record in 2027')])
    panels = [card(1, 'FY2027 HGAB · recipient barangays', 'Most recipient barangays already have earlier MPB records.', graphic,
                   'A new allocation does not always reach a new barangay.',
                   details(f'{recipients["returning"]:,} of {total:,} mapped recipient barangays ({100*recipients["returning"]/total:.2f}%) have at least one mapped record in FY2015–FY2026. {recipients["firstTime"]:,} have no earlier match in this dataset. Icons are rounded shares. Earlier allocations do not establish completed buildings or whether further work is justified.', 'mpb.html#fy2027-mpb-history', 'Review FY2027 title history'))]
    graphic = '<div class="big-fraction">About 1 in 3</div><div class="folders" role="img" aria-label="Approximately one third of FY2027 MPB project rows have fewer than four named document types matched.">' + ''.join(f'<svg class="{style}" viewBox="0 0 120 110" aria-hidden="true"><use href="#{symbol}"/></svg>' for style, symbol in [('blue', 'folder-icon'), ('blue', 'folder-icon'), ('yellow', 'partial-folder-icon')]) + '</div>'
    graphic += legend([('blue', 'At least 4 of 5 document types matched'), ('yellow', 'Below that threshold')])
    panels.append(card(2, 'FY2027 HGAB · document matches', 'About a third have incomplete document matches.', graphic,
                       'These allocations still need their supporting records checked.',
                       details(f'{docs["incompleteDocumentProjectRows"]:,} of {docs["denominatorProjectRows"]:,} MPB project rows ({100*docs["incompleteDocumentProjectRows"]/docs["denominatorProjectRows"]:.2f}%) have fewer than four of five named document types matched. {docs["completeDocumentProjectRows"]:,} meet the threshold. Named types: POW, BP 202, Development Council, geotagged photos and Certificate of Implementability. Proposal and Senate document matches are combined per project. A missing match does not prove a document is absent; file presence does not verify contents. Document snapshot: {escape(docs.get("documentCoverageGeneratedAtUtc") or "not recorded")}. The three folders show a rounded proportion.', 'mpb.html#fy2027-mpb-documents', 'Review document coverage')))
    coverage_pct = 100*cov['recipientBarangays']/cov['officialBarangays']
    colored = round(coverage_pct)
    graphic = f'<div class="big-fraction">{coverage_pct:.1f}% <small>of barangays</small></div>' + pictogram(
        [(colored, 'blue', 'community-icon'), (100-colored, 'muted-icon', 'community-icon')],
        f'{cov["recipientBarangays"]:,} of {cov["officialBarangays"]:,} official barangays have a mapped FY2027 HGAB MPB record.')
    graphic += legend([('blue', 'Has a mapped 2027 record'), ('muted-icon', 'No mapped 2027 record')])
    graphic += f'<div class="coverage-pair"><div><strong>{cov["titleBarangayMatches"]:,}</strong><span>title/barangay matches</span></div><span class="pair-separator">≠</span><div><strong>{cov["recipientBarangays"]:,}</strong><span>recipient barangays</span></div></div>'
    panels.append(card(3, 'FY2027 HGAB · mapped barangay coverage', 'Ten percent coverage does not mean one MPB each.', graphic,
                       'Some barangays have several project titles in the same year.',
                       details(f'{cov["recipientBarangays"]:,} / {cov["officialBarangays"]:,} = {coverage_pct:.2f}% mapped coverage. {cov["titleBarangayMatches"]:,} distinct title/barangay matches are distributed across these recipient barangays; {cov["barangaysWithMultipleTitles"]:,} have more than one. The matches are grouped normalized titles for a barangay, not verified physical buildings. Unmapped project records are outside this coverage measure. Icons are rounded shares. This mapped subset differs from the {docs["denominatorProjectRows"]:,} exact-program project rows used for document coverage.', 'mpb-regional-province.html', 'Review coverage methods')))
    none_pct = round(100*hist['none']/hist['officialBarangays'])
    many_pct = round(100*hist['fourOrMore']/hist['officialBarangays'])
    graphic = pictogram([(none_pct, 'muted-icon', 'community-icon'), (100-none_pct-many_pct, 'light-blue', 'community-icon'), (many_pct, 'blue', 'stack-icon')],
                        f'FY2015–FY2026: {hist["none"]:,} barangays have no mapped title match, {hist["oneToThree"]:,} have one to three, and {hist["fourOrMore"]:,} have four or more.')
    graphic += legend([('muted-icon', f'{none_pct}% · no earlier match'), ('light-blue', '1–3 title matches'), ('blue', f'{many_pct}% · 4 or more')])
    panels.append(card(4, 'FY2015–FY2026 · available GAA records', 'Some barangays appear repeatedly. Others do not appear.', graphic,
                       'Past MPB allocations are spread unevenly across barangays.',
                       details(f'Among {hist["officialBarangays"]:,} official barangays, {hist["none"]:,} have no mapped title match in the available FY2015–FY2026 GAA records; {hist["oneToThree"]:,} have one to three distinct title matches; {hist["fourOrMore"]:,} have four or more. A normalized title/barangay pair is counted once across those years. No mapped match does not establish that a barangay has no building or received no funding. This graphic excludes FY2027. Icons show rounded shares; stacked icons identify the four-or-more group.', 'mpb-barangay.html', 'Explore historical barangay records')))
    tests = poverty['tests']
    stat = tests['allocationPerBarangay']
    panels.append(card(5, 'FY2015–FY2027 records · 2023 poverty rates', 'Poorer regions tend to get less allocation per barangay.', scatter(poverty['points']),
                       'In the comparable regions, the overall relationship runs downward.',
                       details(f'Each dot is one of {tests["n"]} comparable regions. The vertical measure is the sum of available barangay-mapped allocations in FY2015–FY2026 GAA plus FY2027 HGAB, divided by all official barangays in that region. The horizontal measure is PSA 2023 poverty incidence among families. Spearman rank correlation ρ = {stat["rho"]:.3f}; two-sided permutation p = {stat["pValue"]:.4f} ({stat["permutations"]:,} permutations). The dashed line is a descriptive least-squares trend; its slope is not the Spearman coefficient. NIR, Region VI and Region VII are excluded because the poverty geographies overlap. This regional association does not establish the reason for allocations or measure poverty in each beneficiary barangay. Pooled allocations are nominal and include proposed FY2027 funding. Regional data snapshot: {escape(poverty["dataSnapshotUtc"])}.', 'mpb-regional-province.html', 'Review poverty comparison')))
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Five simple visuals explaining MPB recipient barangays, document matches, coverage, historical concentration and poverty."><title>MPB in five pictures · BetterGov</title>' + CSS + '</head><body class="mpb-simple"><header><h1>Who benefits from another MPB allocation?</h1><p>Five pictures from the budget records.</p></header>' + ICONS + '<main class="simple-main"><p class="simple-intro">More allocations deserve a simple question: who gets them, and what records support them?</p>' + ''.join(panels) + '<footer class="simple-footer"><a class="simple-download" href="mpb-simple-data.json" download>Download figures as JSON</a><p>MPB = multi-purpose building. HGAB is a proposed budget; GAA is an enacted budget. Records and title matches do not establish completed buildings, need, spending, or wrongdoing.</p><div class="simple-links"><a href="mpb.html">FY2027 MPB analysis ↗</a><a href="mpb-regional-province.html">Historical distribution ↗</a><a href="mpb-barangay.html">Barangay records ↗</a></div></footer></main></body></html>'
    from uniform_report_menu import apply_page as apply_menu
    from report_table_presentation import apply_page_table_module
    html = apply_menu(html, PAGE)
    html, contract = apply_page_table_module(PAGE, html)
    # The owner keeps supporting prose collapsed after shared editorial modules
    # have composed their content, so the five graphics remain the main reading flow.
    html = html.replace('<details class="computations" open>', '<details class="computations">')
    html = re.sub(r'(<aside\b[^>]*id="report-evidence-notice"[^>]*>.*?</aside>)',
                  r'<details class="computations simple-disclaimer"><summary>Read disclaimer</summary>\1</details>',
                  html, count=1, flags=re.S)
    for directory in (OUT, STATIC):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / PAGE).write_text(html, encoding='utf-8')
        (directory / 'mpb-simple-data.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return {'page': PAGE, 'infographics': len(panels), 'bytes': len(html.encode()), 'tableContract': contract}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
