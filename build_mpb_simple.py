#!/usr/bin/env python3
"""Own mpb-simple.html: six static, accessible MPB infographics."""
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
    facilities = load('education-health-data.json')
    regional = load('mpb-regional-province-data.json')
    base = load('mpb-barangay-base-data.json')
    history, current = Counter(), Counter()
    returning = first = earlier_only = neither = 0
    for place in base['barangays']:
        groups = place.get('buildings', [])
        earlier = sum(any(2015 <= int(e.get('year') or 0) <= 2026 for e in g.get('levelHistory', [])) for g in groups)
        now = sum(any(int(e.get('year') or 0) == 2027 for e in g.get('levelHistory', [])) for g in groups)
        history[earlier] += 1
        if now:
            current[now] += 1
            returning += earlier > 0
            first += earlier == 0
        elif earlier:
            earlier_only += 1
        else:
            neither += 1
    official = regional['summary']['officialBarangays']
    if sum(history.values()) != official:
        raise ValueError('Historical barangay universe does not reconcile with the regional page')
    if returning + first + earlier_only + neither != official:
        raise ValueError('Current and historical barangay cohorts do not reconcile')
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
    province_rates = regional.get('provincePovertyIncidence2023AmongFamiliesPct', {})
    poorest_provinces = sorted(
        ({'province': name, 'povertyPct': rate} for name, rate in province_rates.items() if not name.startswith('ncr,')),
        key=lambda row: (-row['povertyPct'], row['province']),
    )
    mpb_by_province = {str(row.get('province') or '').strip().casefold(): row for row in regional['provinces']}
    for row in poorest_provinces:
        mpb = mpb_by_province.get(row['province'].casefold())
        row['mpbProjectRows'] = mpb['projectRows'] if mpb else None
        row['mpbAllocationPesos'] = mpb['allocationPesos'] if mpb else None
        row['mpbOfficialBarangays'] = mpb['officialBarangays'] if mpb else None
        row['mpbAllocationPerOfficialBarangayPesos'] = (
            mpb['allocationPesos'] / mpb['officialBarangays']
            if mpb and mpb.get('officialBarangays') else None
        )
    return {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'facilityRatios': {
            'mpbProjectRows': facilities['mpbProjectRows'],
            'mpbYearRange': facilities['fiscalYearRange'],
            'mpbStages': facilities['stages'],
            'schoolRecords': facilities['facilityInventories']['depedSchools']['municipalityMatched'],
            'schoolRecordsTotal': facilities['facilityInventories']['depedSchools']['sourceRows'],
            'hospitalRecords': facilities['facilityInventories']['philhealthHospitals']['summary']['governmentUniqueJoined'],
            'hospitalRecordsTotal': facilities['facilityInventories']['philhealthHospitals']['summary']['governmentRows'],
            'hospitalBeds': facilities['facilityInventories']['philhealthHospitals']['summary']['governmentBedsJoined'],
        },
        'recipientBarangays2027': {'returning': returning, 'firstTime': first, 'total': returning + first},
        'documents2027': docs,
        'coverage2027': {'officialBarangays': official, 'recipientBarangays': sum(current.values()),
                         'earlierOnlyBarangays': earlier_only, 'noMappedRecordAnyPeriod': neither,
                         'titleBarangayMatches': sum(k*v for k, v in current.items()),
                         'barangaysWithOneTitle': current[1],
                         'barangaysWithMultipleTitles': sum(v for k, v in current.items() if k > 1)},
        'history2015To2026': {'officialBarangays': official, 'none': history[0],
                              'oneToThree': sum(v for k, v in history.items() if 1 <= k <= 3),
                              'fourOrMore': sum(v for k, v in history.items() if k >= 4)},
        'poverty2015To2027': {'points': points, 'tests': tests, 'dataSnapshotUtc': regional['generatedAtUtc']},
        'poorestProvinces2023AmongFamilies': poorest_provinces[:10],
        'provincePovertyPoints': [
            {'region': row['province'].title(), 'povertyPct': row['povertyPct'],
             'allocationPerBarangayPesos': row['mpbAllocationPerOfficialBarangayPesos'],
             'projectRows': row['mpbProjectRows'], 'allocationPesos': row['mpbAllocationPesos'],
             'officialBarangays': row['mpbOfficialBarangays']}
            for row in poorest_provinces if row.get('mpbAllocationPerOfficialBarangayPesos') is not None
        ],
        'poorestProvince2023AmongFamilies': poorest_provinces[0] if poorest_provinces else None,
        'provincePoverty2025Update': {'provincesAbove30Pct': 0, 'highestRange': '20% to less than 30%'},
        'poorestLgu2023AmongPopulation': {'locality': 'Siayan', 'province': 'Zamboanga del Norte', 'povertyPct': 67.8},
        'lguPoverty2023Categories': [
            {'label': '0–20%', 'localities': 881},
            {'label': '20.1–40%', 'localities': 603},
            {'label': '40.1–60%', 'localities': 119},
            {'label': '60.1–80%', 'localities': 8},
        ],
        'sourceSha256': {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest() for name in
                         ['mpb_analysis.json', 'mpb-regional-province-data.json', 'mpb-barangay-base-data.json']},
    }


ICONS = '''<svg class="icon-definitions" aria-hidden="true" width="0" height="0"><defs>
<symbol id="community-icon" viewBox="0 0 48 48"><path d="M10 22 24 10l14 12v20H10Z" fill="currentColor"/><path d="M6 23 24 7l18 16" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round"/><path d="M21 29h7v13h-7zM14 24h5v5h-5zM31 24h4v5h-4z" fill="#fff"/><circle cx="5" cy="32" r="3" fill="currentColor"/><path d="M5 37v7M2 40h6" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></symbol>
<symbol id="stack-icon" viewBox="0 0 48 48"><use href="#community-icon" x="12" y="0" width="32" height="32"/><use href="#community-icon" x="6" y="8" width="32" height="32"/><use href="#community-icon" x="0" y="16" width="32" height="32"/></symbol>
<symbol id="folder-icon" viewBox="0 0 120 110"><path d="M9 28h40l10 10h52v61H9Z" fill="currentColor"/><rect x="23" y="10" width="72" height="70" rx="5" fill="#fff" stroke="currentColor" stroke-width="4"/><path d="M36 28h43M36 40h43M36 52h25" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M9 59h102l-9 43H18Z" fill="currentColor"/><path d="m45 81 10 9 22-22" stroke="#fff" stroke-width="6" fill="none" stroke-linejoin="round"/></symbol>
<symbol id="partial-folder-icon" viewBox="0 0 120 110"><path d="M9 28h40l10 10h52v61H9Z" fill="currentColor" opacity=".15"/><rect x="23" y="10" width="72" height="70" rx="5" fill="#fff" stroke="currentColor" stroke-width="4" stroke-dasharray="7 5"/><path d="M36 28h43M36 40h43" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><path d="M9 59h102l-9 43H18Z" fill="currentColor"/><path d="M48 82h24" stroke="#fff" stroke-width="6" stroke-linecap="round"/></symbol>
<symbol id="school-icon" viewBox="0 0 48 48"><path d="M5 18 24 7l19 11v24H5Z" fill="currentColor"/><path d="M2 19 24 5l22 14" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linejoin="round"/><path d="M19 29h10v13H19zM10 24h6v6h-6zM32 24h6v6h-6z" fill="#fff"/><path d="M21 12h6v7h-6z" fill="#FCD116"/></symbol>
<symbol id="hospital-icon" viewBox="0 0 48 48"><path d="M7 8h34v34H7z" fill="currentColor"/><path d="M19 15h10v7h7v10h-7v7H19v-7h-7V22h7z" fill="#fff"/><path d="M4 43h40" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></symbol>
<symbol id="bed-icon" viewBox="0 0 48 48"><path d="M7 11v29M7 29h35v11M7 23h11a7 7 0 0 1 7 7v-1a7 7 0 0 1 7-7h3a7 7 0 0 1 7 7v1" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/><path d="M4 41h40" stroke="currentColor" stroke-width="4" stroke-linecap="round"/></symbol>
<symbol id="banknote-icon" viewBox="0 0 48 48"><rect x="4" y="11" width="40" height="26" rx="3" fill="none" stroke="currentColor" stroke-width="3.5"/><path d="M9 17c3 0 5-2 5-4m20 0c0 2 2 4 5 4M9 31c3 0 5 2 5 4m20 0c0-2 2-4 5-4" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><circle cx="24" cy="24" r="7" fill="none" stroke="currentColor" stroke-width="3"/><path d="M21 24h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></symbol>
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
    return f'''<svg class="poverty-plot" viewBox="0 0 {width} {height}" role="img" aria-label="Poverty versus MPB allocation per official barangay by geography; each point is named in its tooltip."><defs><clipPath id="poverty-clip"><rect x="{left}" y="{top}" width="{width-left-right}" height="{height-top-bottom}"/></clipPath></defs>{grid}<text x="{left}" y="24" class="axis-label">More allocation per barangay ↑</text><line x1="{left}" y1="{Y(0)}" x2="{width-right}" y2="{Y(0)}" stroke="#8A97AA"/><line x1="{left}" y1="{top}" x2="{left}" y2="{Y(0)}" stroke="#8A97AA"/><g clip-path="url(#poverty-clip)"><line x1="{X(0)}" y1="{Y(intercept)}" x2="{X(xmax)}" y2="{Y(intercept+slope*xmax)}" stroke="#B45309" stroke-width="3" stroke-dasharray="8 8"/></g>{dots}<text x="{left}" y="{height-20}" class="axis-label">Lower poverty</text><text x="{width-right}" y="{height-20}" text-anchor="end" class="axis-label">Higher poverty →</text></svg>'''


def province_bars(rows):
    maximum = max(row['povertyPct'] for row in rows)
    bars = []
    for i, row in enumerate(rows, 1):
        label = escape(row['province'].title())
        width = 100 * row['povertyPct'] / maximum
        mpb_allocation = row.get('mpbAllocationPerOfficialBarangayPesos')
        mpb_label = (f'Mapped MPB: ₱{mpb_allocation/1e6:.2f}M per official barangay'
                     if mpb_allocation is not None else 'No direct province-name match in MPB records')
        bars.append(
            f'<div class="province-poverty-row"><span class="province-poverty-rank">{i}</span>'
            f'<span class="province-poverty-name">{label}'
            f'<small>{mpb_label}</small></span>'
            f'<span class="province-poverty-track"><i style="width:{width:.1f}%"></i></span>'
            f'<strong>{row["povertyPct"]:.1f}%<small>poverty</small></strong></div>'
        )
    return '<div class="province-poverty-chart" role="img" aria-label="Province poverty versus mapped MPB allocation per official barangay">' + ''.join(bars) + '</div>'


CSS = '''<style id="mpb-simple-style">
*{box-sizing:border-box}body{margin:0;background:#F4F6FA;color:#17233B;font-family:Inter,system-ui,sans-serif}header{background:#00246A;color:#fff;padding:35px 5vw}header h1{font-size:clamp(34px,5vw,60px);line-height:1.1;max-width:900px;margin:0}header p{max-width:800px}main.simple-main{max-width:1200px;margin:auto;padding:30px clamp(16px,4vw,40px)}.simple-intro{font-size:clamp(20px,2.6vw,30px);line-height:1.4;max-width:920px;margin:20px 0 35px;font-weight:600}.simple-panel{background:#fff;border:1px solid #DFE5EF;border-radius:20px;padding:clamp(22px,4vw,48px);margin:0 0 30px;box-shadow:0 8px 25px #00246A06;break-inside:avoid;scroll-margin-top:24px}.simple-card-heading{display:flex;align-items:center;gap:14px;margin-bottom:20px}.simple-step{background:#00246A;color:#fff;width:38px;height:38px;border-radius:50%;display:grid;place-items:center;font-size:13px;font-weight:800}.simple-period{color:#616D81;font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase}.simple-panel h2{font-size:clamp(26px,3.8vw,42px)!important;line-height:1.15!important;max-width:900px;margin:0 0 25px!important;letter-spacing:-.03em}.simple-panel figure{margin:0}.simple-panel figcaption{font-size:clamp(17px,2vw,22px);line-height:1.5;color:#33425B;margin:25px 0 0}.simple-panel .big-fraction{font-size:clamp(52px,9vw,100px);font-weight:850;line-height:1;letter-spacing:-.07em;color:#00246A;margin:5px 0 28px}.simple-panel .big-fraction small{font-size:.25em;font-weight:650;letter-spacing:0;color:#616D81}.icon-definitions{position:absolute;width:0;height:0;overflow:hidden}.pictogram{display:grid;grid-template-columns:repeat(20,minmax(0,1fr));gap:7px}.pictogram .unit{display:block;width:100%;height:auto;aspect-ratio:1}.blue{color:#0038A8}.yellow{color:#BA8900}.muted-icon{color:#D1D7E1}.light-blue{color:#91B0E0}.simple-legend{display:flex;flex-wrap:wrap;gap:10px 24px;margin:20px 0 0;font-size:14px;color:#40516D}.simple-legend>span{display:inline-flex;gap:8px;align-items:center}.swatch{display:inline-block;width:11px;height:11px;background:currentColor;border-radius:3px;flex-shrink:0}.swatch.blue{background:#0038A8}.swatch.yellow{background:#BA8900}.swatch.muted-icon{background:#D1D7E1}.swatch.light-blue{background:#91B0E0}.folders{display:grid;grid-template-columns:repeat(3,1fr);gap:clamp(10px,4vw,45px);max-width:720px;margin:auto}.folders svg{width:100%;height:auto}.coverage-pair{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;text-align:center;gap:12px;max-width:650px;margin:30px auto}.coverage-pair strong{display:block;font-size:clamp(25px,5vw,46px);color:#00246A;line-height:1.2}.coverage-pair span{font-size:13px;color:#616D81}.coverage-pair .pair-separator{font-size:26px;color:#8A97AA}.poverty-plot{display:block;width:100%;height:auto;max-height:none}.axis-label{font:16px system-ui;fill:#596A84}.computations{border-top:1px solid #E2E7F0;margin-top:25px;padding-top:15px;font-size:13px;color:#596A84}.computations summary{cursor:pointer;font-size:12px;font-weight:650}.computations p{max-width:950px;line-height:1.65}.simple-main a{color:#0038A8}.simple-footer{font-size:13px;color:#596A84;line-height:1.6;padding:15px 0 35px}.simple-links{display:flex;gap:12px 22px;flex-wrap:wrap}.simple-download{display:inline-block;padding:10px 15px;background:#0038A8;color:#fff!important;border-radius:8px;text-decoration:none;font-weight:650;margin-bottom:16px}@media(max-width:650px){.pictogram{grid-template-columns:repeat(10,minmax(0,1fr));gap:6px}.simple-panel{border-radius:14px}.simple-legend{font-size:12px;gap:8px 12px}.axis-label{font-size:17px}}@media print{header nav,.computations,.simple-download{display:none}.simple-panel{box-shadow:none;break-inside:avoid}main.simple-main{padding:0}.pictogram{grid-template-columns:repeat(20,minmax(0,1fr))}*{print-color-adjust:exact}}
</style>'''

CSS += '''<style id="mpb-simple-coverage-style">
.coverage-views{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}.coverage-view{min-width:0;padding:20px;border:1px solid #E2E7F0;border-radius:14px;background:#FBFCFF}.coverage-view h3{margin:0 0 18px!important;color:#00246A}.simple-panel .coverage-view .big-fraction{font-size:clamp(38px,5vw,60px);margin:0 0 24px}.simple-panel .coverage-view .big-fraction small{display:block;font-size:14px;margin-top:9px}.coverage-view .pictogram{grid-template-columns:repeat(10,minmax(0,1fr));gap:5px}.coverage-view .simple-legend{display:grid;gap:8px;font-size:13px}@media(max-width:760px){.coverage-views{grid-template-columns:1fr}.coverage-view{padding:16px}}
.coverage-example{display:flex;align-items:center;justify-content:center;gap:clamp(16px,5vw,48px);margin:32px auto 0;padding:18px 20px;border-radius:16px;background:#F3F6FC;max-width:680px}.coverage-example>div{display:grid;justify-items:center;gap:8px}.coverage-example .coverage-place svg{width:82px;height:82px;color:#0038A8}.coverage-example .coverage-arrow{color:#8A97AA;font-size:34px;font-weight:700}.coverage-example .coverage-cards{display:flex;gap:8px}.coverage-example .coverage-cards i{display:grid;place-items:center;width:69px;height:82px;border:3px solid #0038A8;border-radius:7px;background:#fff;color:#0038A8;font-style:normal;font-size:12px;font-weight:800;box-shadow:0 4px 0 #DDE7FA}.coverage-example .coverage-label{color:#42526D;font-size:13px;font-weight:650;text-align:center}
@media(max-width:650px){.coverage-example{gap:10px;padding:14px 8px}.coverage-example .coverage-place svg{width:60px;height:60px}.coverage-example .coverage-cards i{width:53px;height:65px;font-size:10px}.coverage-example .coverage-arrow{font-size:24px}.coverage-example .coverage-label{font-size:11px}}
.province-poverty-chart{display:grid;gap:11px;max-width:850px;margin:24px auto}.province-poverty-row{display:grid;grid-template-columns:28px minmax(120px,220px) minmax(80px,1fr) 54px;align-items:center;gap:10px;font-variant-numeric:tabular-nums}.province-poverty-rank{color:#78859a;font-size:13px;text-align:right}.province-poverty-name{font-weight:700}.province-poverty-row small{display:block;margin-top:3px;color:#596A84;font-size:11px;font-weight:500;line-height:1.25}.province-poverty-track{height:15px;background:#edf1f7;border-radius:99px;overflow:hidden}.province-poverty-track i{display:block;height:100%;background:#B45309;border-radius:99px}.province-poverty-row strong{text-align:right;color:#8D3D0A}.lgu-poverty-callout{max-width:850px;margin:25px auto 0;padding:18px 22px;background:#F3F6FC;border-left:5px solid #0038A8;border-radius:10px}.lgu-poverty-callout strong{display:block;color:#00246A;font-size:clamp(24px,4vw,38px)}.poverty-province-compare{display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:900px;margin:22px auto}.poverty-province{padding:20px;background:#F3F6FC;border-radius:14px}.poverty-province h3{margin:0;color:#00246A;font-size:clamp(18px,2.5vw,25px)}.poverty-province p{margin:4px 0 18px;color:#596A84;font-size:14px}.poverty-token{margin:16px 0 0}.poverty-token strong{font-size:15px}.poverty-token-icons{display:flex;gap:5px;align-items:center;margin-top:8px;min-height:34px}.poverty-token-icons svg{width:32px;height:32px;color:#0038A8}.poverty-token-icons .money-token{color:#BA8900}.poverty-token-note{text-align:center;color:#596A84;font-size:13px;margin:0 auto}.poverty-update{max-width:850px;margin:22px auto;padding:14px 18px;background:#FFF8E6;border-radius:10px;line-height:1.55;color:#4F3C12}.poverty-update a{font-weight:700}@media(max-width:650px){.poverty-province-compare{grid-template-columns:1fr}.poverty-province{padding:16px}}
@media(max-width:650px){.province-poverty-row{grid-template-columns:22px minmax(95px,1fr) minmax(54px,.8fr) 45px;gap:6px;font-size:12px}.province-poverty-track{height:12px}}
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
    coverage_counts = [cov['barangaysWithOneTitle'], cov['barangaysWithMultipleTitles'],
                       cov['earlierOnlyBarangays'], cov['noMappedRecordAnyPeriod']]
    coverage_icons = [round(100*count/cov['officialBarangays']) for count in coverage_counts]
    coverage_icons[max(range(4), key=coverage_counts.__getitem__)] += 100-sum(coverage_icons)
    one_icons, multi_icons, past_icons, no_record_icons = coverage_icons
    graphic = f'<div class="big-fraction">{cov["officialBarangays"]:,} <small>all official barangays</small></div>' + pictogram(
        [(one_icons, 'light-blue', 'community-icon'), (multi_icons, 'blue', 'stack-icon'),
         (past_icons, 'yellow', 'community-icon'), (no_record_icons, 'muted-icon', 'community-icon')],
        f'Across all {cov["officialBarangays"]:,} official barangays: {cov["barangaysWithOneTitle"]:,} have one mapped FY2027 project title (light blue), {cov["barangaysWithMultipleTitles"]:,} have multiple titles (dark blue stacked icons), {cov["earlierOnlyBarangays"]:,} have earlier records only (yellow), and {cov["noMappedRecordAnyPeriod"]:,} have no mapped record in available FY2015–FY2027 data (grey). Icons show rounded shares.')
    graphic += legend([('light-blue', 'One FY2027 project title'), ('blue', 'Multiple FY2027 titles · stacked icons'),
                       ('yellow', 'Earlier records only'), ('muted-icon', 'No mapped record')])
    panels.append(card(3, 'FY2027 HGAB · recipients and historical coverage', 'One barangay does not always mean one project.', graphic,
                       'The blue groups show FY2027 recipients; stacked buildings mark barangays with multiple distinct project titles.',
                       details(f'This single graphic uses all {cov["officialBarangays"]:,} official barangays as its denominator. After grouping identical normalized FY2027 title/barangay pairs, {cov["barangaysWithOneTitle"]:,} ({100*cov["barangaysWithOneTitle"]/cov["officialBarangays"]:.2f}%) have exactly one distinct project title (light blue), and {cov["barangaysWithMultipleTitles"]:,} ({100*cov["barangaysWithMultipleTitles"]/cov["officialBarangays"]:.2f}%) have multiple titles (dark blue stacked icons). Together, these are {cov["recipientBarangays"]:,} barangays with a mapped FY2027 record. Another {cov["earlierOnlyBarangays"]:,} have FY2015–FY2026 records but no mapped FY2027 record (yellow), while {cov["noMappedRecordAnyPeriod"]:,} have no mapped record in the available FY2015–FY2027 data (grey). The four groups are mutually exclusive and sum to all official barangays. The number of distinct FY2027 titles per barangay is counted after title grouping, so repeated identical titles do not increase it. These are title groups, not verified physical buildings or findings of duplicate scope. No mapped record does not establish that a barangay has no MPB. Icons show rounded shares. This mapped subset differs from the {docs["denominatorProjectRows"]:,} exact-program project rows used for document coverage.', 'mpb-regional-province.html', 'Review coverage methods')))
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
    poorest_lgu = data['poorestLgu2023AmongPopulation']
    category_total = sum(row['localities'] for row in data['lguPoverty2023Categories'])
    category_max = max(row['localities'] for row in data['lguPoverty2023Categories'])
    category_bars = ''.join(
        f'<div class="province-poverty-row"><span class="province-poverty-name">{escape(row["label"])}</span>'
        f'<span class="province-poverty-track"><i style="width:{100*row["localities"]/category_max:.1f}%"></i></span>'
        f'<strong>{row["localities"]:,}</strong></div>'
        for row in data['lguPoverty2023Categories']
    )
    province_update = data['provincePoverty2025Update']
    highest = data['poorestProvince2023AmongFamilies']
    lowest = min(data['provincePovertyPoints'], key=lambda row: row['povertyPct'])
    poorest_total = highest['mpbAllocationPesos']
    lowest_total = lowest['allocationPesos']
    highest_mpb_icons = round(highest['mpbProjectRows'] / 100)
    lowest_mpb_icons = round(lowest['projectRows'] / 100)
    highest_bill_icons = round(poorest_total / 1e9)
    lowest_bill_icons = round(lowest_total / 1e9)
    def token_row(symbol, count, style):
        return ''.join(f'<svg class="{style}" viewBox="0 0 48 48" aria-hidden="true"><use href="#{symbol}"/></svg>' for _ in range(count))
    def bill_row(count):
        return ''.join('<svg class="money-token" viewBox="0 0 48 48" aria-hidden="true"><use href="#banknote-icon"/></svg>' for _ in range(count))
    province_figure = (
        f'<div class="poverty-compare-chart" role="img" aria-label="{escape(highest["province"].title())}: {highest["povertyPct"]:.1f}% poverty incidence, {highest["mpbProjectRows"]:,} MPB project rows shown as {highest_mpb_icons} building icons, and ₱{poorest_total/1e9:.2f} billion shown as {highest_bill_icons} bill icons. {escape(lowest["region"])}: {lowest["povertyPct"]:.1f}% poverty incidence, {lowest["projectRows"]:,} MPB project rows shown as {lowest_mpb_icons} building icons, and ₱{lowest_total/1e9:.2f} billion shown as {lowest_bill_icons} bill icons.">'
        f'<div class="poverty-compare-head"><span></span><div><strong>{escape(highest["province"].title())}</strong><small>{highest["povertyPct"]:.1f}% · highest poverty incidence</small></div><div><strong>{escape(lowest["region"])}</strong><small>{lowest["povertyPct"]:.1f}% · lowest poverty incidence</small></div></div>'
        f'<div class="poverty-compare-row"><strong class="poverty-compare-label">MPB project rows</strong><div class="poverty-compare-cell"><b>{highest["mpbProjectRows"]:,}</b><div class="poverty-compare-icons">{token_row("community-icon",highest_mpb_icons,"mpb-token")}</div><small>≈ {highest_mpb_icons} hundreds</small></div><div class="poverty-compare-cell"><b>{lowest["projectRows"]:,}</b><div class="poverty-compare-icons">{token_row("community-icon",lowest_mpb_icons,"mpb-token")}</div><small>≈ {lowest_mpb_icons} hundreds</small></div></div>'
        f'<div class="poverty-compare-row"><strong class="poverty-compare-label">Total mapped allocation</strong><div class="poverty-compare-cell"><b>₱{poorest_total/1e9:.2f}B</b><div class="poverty-compare-icons money">{bill_row(highest_bill_icons)}</div><small>≈ {highest_bill_icons} billions</small></div><div class="poverty-compare-cell"><b>₱{lowest_total/1e9:.2f}B</b><div class="poverty-compare-icons money">{bill_row(lowest_bill_icons)}</div><small>≈ {lowest_bill_icons} billions</small></div></div>'
        '<div class="poverty-compare-legend"><span><i class="mpb"></i>Buildings · MPB project rows</span><span><i class="money"></i>Bills · total allocation</span></div>'
        '</div><p class="poverty-token-note">Building icons represent about 100 project rows each; bill icons represent about ₱1 billion each. Province totals cover different numbers of barangays.</p>')
    panels.append(card(6, 'PSA · 2023 provincial poverty incidence',
                       f'{escape(highest["province"].title())} had fewer MPB rows and less total allocation than {escape(lowest["region"])}.', province_figure,
                       'Poverty estimates are among families. MPB icons show project-row counts; bills show total mapped allocations across FY2015–FY2027, including proposed FY2027 funding.',
                       details(f'Compares the province with the highest 2023 poverty incidence among families ({highest["povertyPct"]:.1f}%) with the province with the lowest ({lowest["povertyPct"]:.1f}%). {highest["province"].title()} has {highest["mpbProjectRows"]:,} mapped MPB project rows and ₱{poorest_total:,.0f} in cumulative mapped allocations; {lowest["region"]} has {lowest["projectRows"]:,} rows and ₱{lowest_total:,.0f}. Project-row counts differ by about {100*(1-highest["mpbProjectRows"]/lowest["projectRows"]):.0f}%, while total allocations differ by about {100*(1-poorest_total/lowest_total):.0f}%. These totals cover different numbers of barangays ({highest["mpbOfficialBarangays"]:,} versus {lowest["officialBarangays"]:,}) and should not be read as per-barangay comparisons. The allocations are nominal, include proposed FY2027 funding, and are not matched to specific facilities or local poverty estimates. This descriptive comparison does not establish a funding rule or measure local need. PSA’s 2023 local estimates use small-area estimation and cover {category_total:,} cities and municipalities, including 14 sub-municipalities in Manila. Eight localities were above 60%; Siayan, Zamboanga del Norte had the highest poverty incidence among population at 67.8%. Locality rates are among population while provincial rates are among families, so the measures should not be compared directly. Provincial source: <a href="https://psa.gov.ph/sites/default/files/phdsd/2023%20FY%20Official%20Poverty%20Statistics%20Publication_15August2024.pdf" target="_blank" rel="noopener">PSA 2023 Full Year Official Poverty Statistics</a>. Local estimates, precision measures, and exclusions: <a href="https://psa.gov.ph/sites/default/files/phdsd/2_2023%20SAE_with%20PSGC_noHUC_06Feb2026.xlsx" target="_blank" rel="noopener">PSA city and municipality workbook</a>. The local dataset excludes several highly urbanized cities already covered by direct estimates.', 'https://psa.gov.ph/statistics/poverty/node/1684082420', 'Open PSA poverty release')))
    ratios = data['facilityRatios']
    mpb_rows = ratios['mpbProjectRows']
    schools = ratios['schoolRecords']
    hospitals = ratios['hospitalRecords']
    school_ratio = schools / mpb_rows
    beds = ratios['hospitalBeds']
    beds_per_ten_mpb = 10 * beds / mpb_rows
    ratio_css = '<style>.facility-icon{display:block;width:78px;height:78px;margin:6px auto 14px;color:#0038A8}.ratio-pair{display:grid;grid-template-columns:1fr auto 1fr;gap:16px;align-items:center;text-align:center;max-width:760px;margin:24px auto}.ratio-stat{padding:22px 12px;background:#F3F6FC;border-radius:14px}.ratio-stat strong{display:block;color:#00246A;font-size:clamp(30px,6vw,56px);line-height:1.1}.ratio-stat span{display:block;color:#596A84;font-size:14px;margin-top:8px}.ratio-mark{font-size:25px;color:#8A97AA;font-weight:800}.ratio-bars{display:grid;gap:14px;max-width:760px;margin:20px auto 6px}.ratio-bar-row{display:grid;grid-template-columns:minmax(110px,220px) minmax(80px,1fr) 72px;gap:12px;align-items:center;font-size:14px}.ratio-bar-track{height:24px;background:#E8EDF5;border-radius:99px;overflow:hidden}.ratio-bar-track i{display:block;height:100%;background:#0038A8;border-radius:inherit}.ratio-bar-row.facility .ratio-bar-track i{background:#BA8900}.ratio-bar-row b{text-align:right;font-variant-numeric:tabular-nums}.ratio-caveat{font-size:14px;color:#596A84;line-height:1.6;max-width:850px;margin:16px auto 0}.icon-ratio{max-width:650px;margin:26px auto;text-align:center}.icon-ratio-summary{font-size:clamp(20px,3vw,28px);font-weight:750;color:#00246A}.icon-ratio-icons{display:grid;grid-template-columns:repeat(10,minmax(22px,42px));justify-content:center;gap:6px;max-width:500px;margin:18px auto}.icon-ratio-icons svg{display:block;width:100%;height:auto;aspect-ratio:1;color:#0038A8}.icon-ratio-icons svg.facility-token{color:#BA8900}.icon-ratio-legend{display:flex;justify-content:center;gap:18px;flex-wrap:wrap;color:#596A84;font-size:14px}.icon-ratio-legend span{display:inline-flex;gap:7px;align-items:center}.icon-ratio-swatch{width:12px;height:12px;border-radius:3px;background:#0038A8}.icon-ratio-swatch.facility{background:#BA8900}@media(max-width:560px){.ratio-pair{gap:6px}.ratio-stat{padding:16px 7px}.ratio-stat span{font-size:12px}.ratio-mark{font-size:18px}.ratio-bar-row{grid-template-columns:minmax(86px,1fr) minmax(60px,2fr) 58px;gap:7px;font-size:12px}.icon-ratio-icons{grid-template-columns:repeat(6,minmax(24px,42px));gap:5px}.icon-ratio-legend{font-size:12px}}</style>'
    province_compare_css = '<style>.poverty-compare-chart{max-width:920px;margin:24px auto;border:1px solid #DFE5EF;border-radius:16px;background:#FBFCFF;overflow:hidden}.poverty-compare-head,.poverty-compare-row{display:grid;grid-template-columns:minmax(150px,.8fr) 1fr 1fr;gap:12px;align-items:center;padding:16px 20px}.poverty-compare-head{background:#F3F6FC;border-bottom:1px solid #DFE5EF}.poverty-compare-head>div{text-align:center}.poverty-compare-head strong{display:block;color:#00246A;font-size:18px}.poverty-compare-head small,.poverty-compare-cell small{display:block;margin-top:4px;color:#596A84;font-size:12px;line-height:1.35}.poverty-compare-row+.poverty-compare-row{border-top:1px solid #E2E7F0}.poverty-compare-label{color:#33425B;font-size:14px}.poverty-compare-cell{text-align:center}.poverty-compare-cell>b{color:#17233B;font-size:16px;font-variant-numeric:tabular-nums}.poverty-compare-icons{display:flex;justify-content:center;align-items:center;gap:4px;margin:8px 0 0;min-height:34px}.poverty-compare-icons svg{width:31px;height:31px;color:#0038A8}.poverty-compare-icons.money svg{color:#BA8900}.poverty-compare-legend{display:flex;justify-content:center;gap:22px;flex-wrap:wrap;padding:13px 16px;border-top:1px solid #E2E7F0;color:#596A84;font-size:12px}.poverty-compare-legend span{display:inline-flex;align-items:center;gap:7px}.poverty-compare-legend i{width:11px;height:11px;border-radius:3px;background:#0038A8}.poverty-compare-legend i.money{background:#BA8900}@media(max-width:600px){.poverty-compare-head,.poverty-compare-row{grid-template-columns:1fr 1fr;padding:13px 12px;gap:8px}.poverty-compare-head>span{display:none}.poverty-compare-head strong{font-size:15px}.poverty-compare-head small{font-size:11px}.poverty-compare-label{grid-column:1/-1}.poverty-compare-icons{gap:2px}.poverty-compare-icons svg{width:25px;height:25px}.poverty-compare-legend{gap:10px;font-size:11px}}</style>'
    ratio_bars = lambda first_label, first_value, second_label, second_value: (
        '<div class="ratio-bars" role="img" aria-label="Proportional comparison of MPB project rows and facility records">'
        f'<div class="ratio-bar-row"><span>{first_label}</span><span class="ratio-bar-track"><i style="width:100%"></i></span><b>{first_value:,}</b></div>'
        f'<div class="ratio-bar-row facility"><span>{second_label}</span><span class="ratio-bar-track"><i style="width:{100*second_value/max(first_value,second_value):.1f}%"></i></span><b>{second_value:,}</b></div></div>')
    mini_icons = lambda symbol, count, style='': ''.join(f'<svg class="{style}" viewBox="0 0 48 48" aria-hidden="true"><use href="#{symbol}"/></svg>' for _ in range(count))
    school_graphic = f'<div class="icon-ratio" role="img" aria-label="17 MPB project rows for every 10 joined public schools"><div class="icon-ratio-summary">17 MPB rows for every 10 joined schools</div><div class="icon-ratio-icons">{mini_icons("community-icon",17)}{mini_icons("school-icon",10,"facility-token")}</div><div class="icon-ratio-legend"><span><i class="icon-ratio-swatch"></i>MPB project rows</span><span><i class="icon-ratio-swatch facility"></i>Joined public schools</span></div></div>'
    panels.append(card(7, 'GAA FY2015–FY2026 + FY2027 House Bill · DepEd SY 2025–26', '17 MPB project rows for every 10 joined public schools.', school_graphic,
        'The ratio compares cumulative MPB project rows with joined public-school records; it does not show that MPB projects served those schools.',
        details(f'{mpb_rows:,} mapped MPB project rows across FY2015–FY2027 (GAA FY2015–FY2026 plus FY2027 House Bill) compared with {schools:,} of {ratios["schoolRecordsTotal"]:,} DepEd public-school IDs uniquely joined to a municipality ({100*schools/ratios["schoolRecordsTotal"]:.1f}%). That is {1/school_ratio:.2f} MPB project rows per joined school record. The datasets overlap by geography and period but do not identify schools served by MPB projects. DepEd unmatched IDs are excluded. Source: NASH Reviewer DepEd SY 2025–26 public-school panel.', 'education-health.html#data-coverage', 'Review joined school counts')))
    rounded_beds = round(beds_per_ten_mpb)
    health_graphic = f'<div class="icon-ratio" role="img" aria-label="10 MPB project rows compared with {beds_per_ten_mpb:.1f} joined government hospital beds, shown as about {rounded_beds} bed icons"><div class="icon-ratio-summary">10 MPB rows for about {rounded_beds} joined hospital beds</div><div class="icon-ratio-icons">{mini_icons("community-icon",10)}{mini_icons("bed-icon",rounded_beds,"facility-token")}</div><div class="icon-ratio-legend"><span><i class="icon-ratio-swatch"></i>MPB project rows</span><span><i class="icon-ratio-swatch facility"></i>Joined hospital beds · {beds_per_ten_mpb:.1f} exact</span></div></div>'
    panels.append(card(8, 'GAA FY2015–FY2026 + FY2027 House Bill · PhilHealth list, 30 Sep 2026', '10 MPB project rows for about 8 reported government hospital beds.', health_graphic,
        f'About 10 MPB project rows for every {beds_per_ten_mpb:.1f} government hospital beds in the joined records. These records are not matched project by project.',
        details(f'{mpb_rows:,} mapped MPB project rows across FY2015–FY2027 compared with {beds:,} reported beds joined from {hospitals:,} government hospitals/infirmaries. That is {mpb_rows/beds:.2f} MPB project rows per joined bed, shown rounded to 10 rows versus about {rounded_beds} beds. No facility-to-project matching is available, so this compares aggregate record totals, not service coverage or construction. Source: PhilHealth accredited facilities list updated 30 September 2026.', 'education-health.html#data-coverage', 'Review health facility and bed counts')))
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Six simple visuals explaining MPB recipient barangays, document matches, coverage, historical concentration and poverty."><title>MPB in eight pictures · BetterGov</title>' + CSS + ratio_css + province_compare_css + '</head><body class="mpb-simple"><header><h1>Who benefits from another MPB allocation?</h1><p>Eight pictures from the budget records.</p></header>' + ICONS + '<main class="simple-main"><p class="simple-intro">More allocations deserve a simple question: who gets them, and what records support them?</p>' + ''.join(panels) + '<footer class="simple-footer"><a class="simple-download" href="mpb-simple-data.json" download>Download figures as JSON</a><p>MPB = multi-purpose building. HGAB is a proposed budget; GAA is an enacted budget. Records and title matches do not establish completed buildings, need, spending, or wrongdoing.</p><div class="simple-links"><a href="mpb.html">FY2027 MPB analysis ↗</a><a href="mpb-regional-province.html">Historical distribution ↗</a><a href="mpb-barangay.html">Barangay records ↗</a></div></footer></main></body></html>'
    from uniform_report_menu import apply_page as apply_menu
    from report_table_presentation import apply_page_table_module
    html = apply_menu(html, PAGE)
    html, contract = apply_page_table_module(PAGE, html)
    # The owner keeps supporting prose collapsed after shared editorial modules
    # have composed their content, so the six graphics remain the main reading flow.
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
