#!/usr/bin/env python3
"""Build only dpwh-simple.html and its compact explanatory data file."""
from datetime import datetime, timezone
from html import escape
import hashlib
import json
from pathlib import Path
import re
import statistics
import unicodedata

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
PAGE = 'dpwh-simple.html'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values, p):
    values = sorted(values)
    if not values:
        return None
    at = (len(values) - 1) * p
    low, high = int(at), min(int(at) + 1, len(values) - 1)
    return values[low] + (values[high] - values[low]) * (at - low)


def ascii_key(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def family(name):
    if re.search(r'\b(?:multi\s*[- ]?purpose\s+building|mpb)\b', name or '', re.I):
        return 'Multi-Purpose Buildings (MPB)'
    if re.search(r'\bbridges?\b', name or '', re.I):
        return 'Bridges'
    if re.search(r'\broads?\b', name or '', re.I):
        return 'Roads'
    return re.sub(r'\s+[–—-]\s+.*\b(?:District Engineering Office|Regional Office)\b.*$', '', name or '', flags=re.I).strip()


def unit_key(value):
    value = (value or '').lower().replace('²', '2').replace('³', '3')
    value = re.sub(r'[^a-z0-9]+', ' ', value).strip()
    return {'ea': 'each', 'unit': 'each', 'each': 'each'}.get(value, value)


def billboard_rates():
    """Match the cost-per-unit page's proposal/HGAB precedence for signboards."""
    source_path = OUT / 'dpwh-in-depth-data.json'
    data = read_json(source_path)
    projects = {project['code']: project for project in data.get('projects', [])}
    merge_rules = data.get('powBillMerges') or {}
    results = {}
    for group in data.get('summaryPeerGroups', []):
        if group.get('family') not in {'Roads', 'Bridges'}:
            continue
        refs = {project.get('code') for project in group.get('projects', [])}
        selected_docs = {}
        for document in data.get('costUnitHgabResults', []):
            title = document.get('hgabTitle') or ''
            related = (document.get('proposalCode') in refs if document.get('proposalCode') else False)
            if not related and family(title).lower() != group['family'].lower():
                continue
            identity = document.get('proposalCode') or document.get('hgabId') or document.get('code')
            previous = selected_docs.get(identity)
            if not previous or len(document.get('rows') or []) > len(previous.get('rows') or []):
                selected_docs[identity] = document
        overrides = {document['proposalCode'] for document in selected_docs.values()
                     if document.get('proposalCode') and document.get('rows')}
        project_totals = {}

        def consume(code, name, rows):
            total = project_totals.setdefault(code, {'name': name, 'amount': 0.0, 'quantity': 0.0, 'pages': set(), 'source': ''})
            for row in rows or []:
                if (row.get('costBasis') or 'not_stated') != 'as_submitted' or not row.get('description'):
                    continue
                bill = ascii_key(row.get('description'))
                merged = merge_rules.get(bill, bill)
                if merged != 'project billboard signboard' or unit_key(row.get('unit')) != 'each':
                    continue
                try:
                    amount, quantity = float(row.get('amountPesos')), float(row.get('quantity'))
                except (TypeError, ValueError):
                    continue
                if amount <= 0 or quantity <= 0:
                    continue
                total['amount'] += amount
                total['quantity'] += quantity
                if row.get('sourcePage') is not None:
                    total['pages'].add(row['sourcePage'])

        for code in refs:
            project = projects.get(code)
            if not project or code in overrides:
                continue
            document = next((doc for doc in project.get('documents', [])
                             if doc.get('kind') == 'pow' and (doc.get('rows') or doc.get('costCategoryBreakdown'))), None)
            if document:
                consume(code, project.get('name', code), document.get('rows'))
                if project_totals.get(code, {}).get('quantity'):
                    project_totals[code]['source'] = 'Proposal POW'
        for document in selected_docs.values():
            if not document.get('rows'):
                continue
            code = document.get('proposalCode') or document.get('hgabId') or document.get('code')
            consume(code, document.get('hgabTitle') or code, document['rows'])
            if project_totals.get(code, {}).get('quantity'):
                project_totals[code]['source'] = 'Senate HGAB POW'

        rows = []
        for code, row in project_totals.items():
            if row['quantity'] > 0:
                rows.append({'code': code, 'name': row['name'], 'unitCost': row['amount'] / row['quantity'],
                             'amountPesos': row['amount'],
                             'quantity': row['quantity'], 'pages': sorted(row['pages']), 'source': row['source']})
        values = [row['unitCost'] for row in rows]
        maximum = max(rows, key=lambda row: row['unitCost']) if rows else None
        results[group['family']] = {
            'projectCount': len(rows), 'unit': 'each', 'costBasis': 'as_submitted',
            'q1Pesos': quantile(values, .25), 'medianPesos': quantile(values, .5),
            'q3Pesos': quantile(values, .75), 'maximumPesos': max(values) if values else None,
            'highestUnitRateProject': maximum,
        }
    if set(results) != {'Roads', 'Bridges'}:
        raise ValueError('Road and bridge billboard groups are missing from cost-per-unit data')
    return results, source_path


def collect():
    cost = read_json(OUT / 'cost_per_km.json')
    rehab = read_json(OUT / 'bridge-rehabilitation-review.json')
    category = {row['category']: row for row in cost['summary']}
    roads, bridges = category['Roads'], category['Bridges']
    if roads['withLength'] + roads['withoutLength'] != roads['lineItems']:
        raise ValueError('Road length coverage does not reconcile')
    if bridges['withLength'] + bridges['withoutLength'] != bridges['lineItems']:
        raise ValueError('Bridge length coverage does not reconcile')
    if sum(rehab['summary']['conditionCounts'].values()) != rehab['summary']['projects']:
        raise ValueError('Bridge rehabilitation condition rows do not reconcile')

    rates = {}
    outliers_per_meter = {}
    for name, rows in [('Roads', roads), ('Bridges', bridges)]:
        records = [row['allocationPerStatedMeter'] for row in cost['projects']
                   if row['category'] == name and isinstance(row.get('allocationPerStatedMeter'), (int, float))]
        rates[name] = {
            'records': len(records),
            'q1PesosPerMeter': quantile(records, .25),
            'medianPesosPerMeter': quantile(records, .5),
            'q3PesosPerMeter': quantile(records, .75),
        }
        maximum = max(
            (row for row in cost['projects']
             if row['category'] == name and isinstance(row.get('allocationPerStatedMeter'), (int, float))),
            key=lambda row: row['allocationPerStatedMeter'],
        )
        outliers_per_meter[name] = {
            'projectId': maximum['id'],
            'projectName': maximum['projectName'],
            'office': maximum['office'],
            'region': maximum['region'],
            'amountPesos': maximum['amountPesos'],
            'statedLengthMeters': maximum['lengthMeters'],
            'pesosPerStatedMeter': maximum['allocationPerStatedMeter'],
            'rateReview': maximum.get('rateReview'),
            'sourceVolume': maximum['sourceVolume'],
            'sourcePage': maximum['sourcePage'],
        }

    billboard, billboard_source = billboard_rates()
    lane = {row['category']: row for row in cost['laneCost']['summary']}
    inputs = [OUT / 'cost_per_km.json', OUT / 'bridge-rehabilitation-review.json', billboard_source]
    return {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'lengthCoverage': {
            'roads': {'lineItems': roads['lineItems'], 'withStatedLength': roads['withLength'],
                      'withoutUsableLength': roads['withoutLength'], 'assetLengthsMatched': lane['Roads']['assetLengthRecords'],
                      'assetLengthWhenTitleLengthMissing': lane['Roads']['missingStatedLengthWithAssetLengthRecords']},
            'bridges': {'lineItems': bridges['lineItems'], 'withStatedLength': bridges['withLength'],
                        'withoutUsableLength': bridges['withoutLength'], 'existingSpansMatched': lane['Bridges']['assetLengthRecords']},
            'policy': 'Existing road-section lengths and bridge spans are offline inventory dimensions. They do not replace the funded work length when the project title does not state a usable length.',
        },
        'allocationPerStatedMeter': rates,
        'highestAllocationPerStatedMeter': outliers_per_meter,
        'burolOverpass': next((row for row in rehab['projects'] if 'burol overpass' in row['project'].lower()), None),
        'bridgeRehabilitation': rehab['summary'],
        'transparencySnapshotRetrievedAtUtc': rehab.get('transparencySnapshotRetrievedAtUtc'),
        'billboards': billboard,
        'methods': {
            'costPerMeter': 'Whole HGAB allocation divided by a usable length stated in the project title. It is a screening ratio, not verified construction cost; scope, width, funded extent and quantities may differ.',
            'bridgeInventory': 'Bridge IDs and condition labels are supported matches to offline DPWH inventory records. Assessment dates are unavailable in the matched records.',
            'transparency': 'The DPWH Transparency snapshot reports listed document counts, not physical completion. Its snapshot date and exact-title reconciliation appear in bridge-rehabilitation-review.json.',
            'billboard': 'POW item amount divided by quantity, for the merged Project Billboard / Signboard item with unit each. Proposal POW rows are replaced by linked Senate HGAB POW rows where available.',
        },
        'sources': {str(path.relative_to(ROOT)): sha256(path) for path in inputs},
    }


def icon_grid(available, total, label, color='blue'):
    filled = round(100 * available / total) if total else 0
    units = ''.join(f'<i class="coverage-unit {color if i < filled else "empty"}"></i>' for i in range(100))
    return f'<div class="coverage-grid" role="img" aria-label="{escape(label)}">{units}</div>'


def rate_chart(data):
    rows = [data['allocationPerStatedMeter'][key] for key in ('Roads', 'Bridges')]
    labels = ['Roads', 'Bridges']
    allvals = [v for row in rows for v in (row['q1PesosPerMeter'], row['q3PesosPerMeter']) if v]
    lo, hi = min(allvals), max(allvals)
    lo_log, hi_log = __import__('math').log10(lo), __import__('math').log10(hi)
    left, right = 190, 900
    x = lambda value: left + (__import__('math').log10(value) - lo_log) / (hi_log - lo_log or 1) * (right - left)
    svg = ['<svg class="rate-chart" viewBox="0 0 980 210" role="img" aria-label="Middle half of allocation per stated meter for road and bridge line items, on a logarithmic scale">']
    for index, (label, row) in enumerate(zip(labels, rows)):
        y = 65 + index * 70
        svg.append(f'<text x="8" y="{y+6}" class="chart-label">{label}</text>')
        svg.append(f'<line x1="{x(row["q1PesosPerMeter"]):.1f}" y1="{y}" x2="{x(row["q3PesosPerMeter"]):.1f}" y2="{y}" stroke="#49a798" stroke-width="16" stroke-linecap="round"><title>Middle 50%: ₱{row["q1PesosPerMeter"]:,.0f} to ₱{row["q3PesosPerMeter"]:,.0f} per stated meter</title></line>')
        svg.append(f'<line x1="{x(row["medianPesosPerMeter"]):.1f}" y1="{y-14}" x2="{x(row["medianPesosPerMeter"]):.1f}" y2="{y+14}" stroke="#00246A" stroke-width="5"><title>Median ₱{row["medianPesosPerMeter"]:,.0f} per stated meter</title></line>')
        svg.append(f'<text x="{min(910,x(row["q3PesosPerMeter"])+18):.1f}" y="{y+6}" class="chart-value">₱{row["medianPesosPerMeter"]:,.0f} median</text>')
    svg.append(f'<line x1="{left}" y1="180" x2="{right}" y2="180" stroke="#80909c"/><text x="{(left+right)/2}" y="202" text-anchor="middle" class="chart-axis">Pesos per stated meter · logarithmic scale</text></svg>')
    return ''.join(svg)


def condition_chart(data):
    rehab = data['bridgeRehabilitation']
    counts = rehab['conditionCounts']
    labels = [
        ('Good', 'Good · assessment year unknown', '#16825d'),
        ('Fair', 'Fair · assessment year unknown', '#eab308'),
        ('Poor', 'Poor · assessment year unknown', '#d97706'),
        ('Bad', 'Bad · assessment year unknown', '#b42318'),
        ('No matched condition', 'No inventory condition match', '#8b98a5'),
    ]
    maximum = rehab['projects']
    svg = ['<svg class="condition-chart" viewBox="0 0 900 265" role="img" aria-label="Existing inventory condition labels across bridge rehabilitation and repair rows">']
    for index, (short, key, color) in enumerate(labels):
        y = 20 + index * 47
        count = counts[key]
        width = 560 * count / maximum
        svg.append(f'<text x="8" y="{y+18}" class="chart-label">{escape(short)}</text><rect x="220" y="{y}" width="560" height="26" rx="6" fill="#e9edf4"/><rect x="220" y="{y}" width="{width:.1f}" height="26" rx="6" fill="{color}"><title>{escape(key)}: {count} rows</title></rect><text x="{min(820,230+width):.1f}" y="{y+18}" class="chart-value">{count}</text>')
    svg.append('</svg>')
    return ''.join(svg)


def billboard_chart(data):
    vals = [data['billboards'][family]['medianPesos'] for family in ('Roads', 'Bridges')]
    maxval = max(data['billboards'][family]['q3Pesos'] for family in ('Roads', 'Bridges'))
    width = 760
    svg = ['<svg class="billboard-chart" viewBox="0 0 900 205" role="img" aria-label="Median extracted billboard unit rate in road and bridge project schedules">']
    for index, family_name in enumerate(('Roads', 'Bridges')):
        row = data['billboards'][family_name]
        y = 55 + index * 67
        bar = width * row['medianPesos'] / maxval if maxval else 0
        svg.append(f'<text x="8" y="{y+7}" class="chart-label">{family_name}</text><rect x="180" y="{y-12}" width="{width}" height="24" rx="12" fill="#e9edf4"/><rect x="180" y="{y-12}" width="{bar:.1f}" height="24" rx="12" fill="#2453b8"><title>Median ₱{row["medianPesos"]:,.0f} per each, based on {row["projectCount"]} projects</title></rect><text x="{min(820,192+bar):.1f}" y="{y+7}" class="chart-value">₱{row["medianPesos"]:,.0f} per each</text>')
    svg.append('</svg>')
    return ''.join(svg)


def outlier_card(category, value, rate_label, facts, source):
    fact_html = ''.join(f'<span><b>{escape(label)}</b>{escape(str(text))}</span>' for label, text in facts)
    return (
        f'<article class="outlier-card"><div class="outlier-category">{escape(category)} · highest listed rate</div>'
        f'<strong class="outlier-rate">{escape(rate_label)}</strong>'
        f'<h3>{escape(value)}</h3><div class="outlier-facts">{fact_html}</div>'
        f'<p class="outlier-source">Source: {escape(source)}</p></article>'
    )


def detail(text):
    return f'<details class="computations"><summary>Sources and exact figures</summary>{text}</details>'


def build():
    data = collect()
    coverage = data['lengthCoverage']
    roads, bridges = coverage['roads'], coverage['bridges']
    rehab = data['bridgeRehabilitation']
    condition = rehab['conditionCounts']
    good_fair = condition['Good · assessment year unknown'] + condition['Fair · assessment year unknown']
    poor_bad = condition['Poor · assessment year unknown'] + condition['Bad · assessment year unknown']
    burol = data['burolOverpass']
    if not burol:
        raise ValueError('Burol Overpass allocation/length row was not found')

    panels = []
    graphic = '<div class="coverage-pair"><div><h3>Road rows</h3>' + icon_grid(roads['withStatedLength'], roads['lineItems'], 'About half of road line items have a usable stated length') + f'<p><strong>{100*roads["withStatedLength"]/roads["lineItems"]:.0f} in 100</strong> have a stated length we can use.</p></div><div><h3>Bridge rows</h3>' + icon_grid(bridges['withStatedLength'], bridges['lineItems'], 'About six in 100 bridge line items have a usable stated length', 'orange') + f'<p><strong>{100*bridges["withStatedLength"]/bridges["lineItems"]:.0f} in 100</strong> have a stated length we can use.</p></div></div>'
    graphic += '<div class="asset-facts"><span><b>595</b> road asset lengths matched</span><span><b>754</b> existing bridge spans matched</span></div>'
    panels.append(('01', 'THE DENOMINATOR', 'Many bridge budget rows do not say how long the funded work is.', graphic,
                   'Existing asset lengths help identify a road or bridge. They cannot tell us how much work this year’s allocation will fund.'))

    rr, br = data['allocationPerStatedMeter']['Roads'], data['allocationPerStatedMeter']['Bridges']
    per_meter = data['highestAllocationPerStatedMeter']
    row = per_meter['Roads']
    road_length_label = escape(f'{row["statedLengthMeters"]:,.3f} m stated in title')
    road_drawing = f'<svg class="road-drawing" viewBox="0 0 900 260" role="img" aria-label="Illustration of a measured road segment between the title-stated endpoints"><rect x="28" y="24" width="844" height="212" rx="22" fill="#edf3fb"/><path d="M82 132H818" stroke="#273b55" stroke-width="88" stroke-linecap="round"/><path d="M82 132H818" stroke="#fff" stroke-width="7" stroke-dasharray="42 30"/><circle cx="82" cy="132" r="22" fill="#16a36a" stroke="white" stroke-width="7"/><circle cx="818" cy="132" r="22" fill="#d43c35" stroke="white" stroke-width="7"/><path d="M82 192v17m736-17v17M82 201h736" stroke="#2453b8" stroke-width="4"/><text x="450" y="228" text-anchor="middle" class="chart-label">{road_length_label}</text></svg>'
    graphic = (
        '<div class="integrated-outlier road-integrated">'
        '<div class="integrated-metrics">'
        f'<div class="integrated-metric"><strong>₱{row["amountPesos"]/1e6:,.0f}M</strong><span>proposed allocation</span></div>'
        '<span class="integrated-operator" aria-hidden="true">÷</span>'
        f'<div class="integrated-metric"><strong>{row["statedLengthMeters"]:,.3f} m</strong><span>printed in the title</span></div>'
        '<span class="integrated-operator" aria-hidden="true">=</span>'
        f'<div class="integrated-metric integrated-result"><strong>₱{row["pesosPerStatedMeter"]/1e6:,.1f}M</strong><span>per stated meter</span></div>'
        '</div>' + road_drawing +
        f'<h3 class="integrated-project-title">{escape(row["projectName"])}</h3>'
        f'<p class="integrated-context">Road median: ₱{rr["medianPesosPerMeter"]:,.0f} per stated meter · {escape(row["office"])} · {escape(row["region"])}</p>'
        f'<p class="integrated-source">Source: {escape(row["sourceVolume"])} · p. {row["sourcePage"]} · {escape(row["rateReview"] or "No review label")}</p>'
        '</div>'
    )
    panels.append(('02', 'ALLOCATION ÷ STATED LENGTH', 'One short printed length can make a project ratio look enormous.', graphic,
                   'These are whole-project allocations divided by title-stated lengths, not verified construction costs. Check the printed endpoints and scope before comparing them.'))

    burol_rate = burol['allocationPesos'] / burol['statedLengthMeters'] if burol.get('statedLengthMeters') else None
    bridge_drawing = '<svg class="burol-drawing" viewBox="0 0 800 170" role="img" aria-label="Illustration of a 25 meter bridge span, not to scale"><path d="M80 115h640M125 95h550M165 95V65h470v30M165 65l40-30h390l40 30M235 95V55m80 40V45m80 50V45m80 50V45m80 50V55" fill="none" stroke="#2453b8" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/><path d="M120 132h560m-560-9v18m560-18v18" stroke="#183643" stroke-width="3"/><text x="400" y="160" text-anchor="middle" class="chart-label">25 stated meters</text></svg>'
    graphic = f'<div class="burol-spotlight"><div class="burol-amount">₱{burol["allocationPesos"]/1e6:,.0f}M</div><div class="burol-rate">₱{burol_rate:,.0f}<small>per stated meter</small></div></div>' + bridge_drawing
    panels.append(('03', 'A BRIDGE RATE THAT NEEDS A CLOSER LOOK', 'Burol Overpass: ₱150 million divided by 25 stated meters.', graphic,
                   'This is an allocation-to-title-length ratio, not a verified bridge construction cost. The project has no matched inventory ID or condition in the available crosswalk.'))

    graphic = condition_chart(data)
    graphic += f'<div class="asset-facts"><span><b>{rehab["withInventoryBridgeId"]}/{rehab["projects"]}</b> rows with a matched bridge ID</span><span><b>{rehab["transparencyDocumentStatuses"]["5+ documents listed"]}</b> titles with 5+ listed documents · not completion proof</span></div>'
    panels.append(('04', 'WHAT THE INVENTORY SAYS', 'Bridge rehabilitation rows include both Good/Fair and Poor/Bad condition labels.', graphic,
                   f'Of {rehab["withInventoryCondition"]} rows with an inventory condition, {good_fair} are Good/Fair and {poor_bad} are Poor/Bad. The condition dates are unavailable. Transparency document counts do not show whether work was completed.'))

    billboard = data['billboards']
    road_billboard, bridge_billboard = billboard['Roads'], billboard['Bridges']
    for number, category, row in (('05', 'Roads', road_billboard), ('06', 'Bridges', bridge_billboard)):
        project = row.get('highestUnitRateProject') or {}
        pages_text = ', '.join(str(page) for page in project.get('pages', [])) or 'not recorded'
        median = row['medianPesos']
        quantity = project.get('quantity', 0)
        sign_word = 'sign' if quantity == 1 else 'signs'
        amount_total = project.get('amountPesos', project.get('unitCost', 0) * quantity)
        equation = '<span>' + escape(f'{quantity:,.0f} signs') + '</span><b>×</b><span>' + escape(f'₱{project.get("unitCost", 0):,.2f} each') + '</span><b>=</b><span>' + escape(f'₱{amount_total:,.2f} listed total') + '</span>'
        sign_quantity = escape(f'{quantity:,.0f}')
        sign = (
            '<svg class="signboard-drawing" viewBox="0 0 700 330" role="img" '
            f'aria-label="Project sign infographic showing ₱{project.get("unitCost", 0):,.2f} per sign and {sign_quantity} {sign_word}">'
            '<rect x="24" y="18" width="652" height="294" rx="22" fill="#edf3fb"/>'
            '<path d="M108 44h484v184H108z" fill="#fff" stroke="#2453b8" stroke-width="12" stroke-linejoin="round"/>'
            '<text x="350" y="125" text-anchor="middle" class="sign-price">'
            f'₱{project.get("unitCost", 0):,.0f}</text>'
            '<text x="350" y="168" text-anchor="middle" class="sign-unit">per sign</text>'
            '<path d="M226 228v61m248-61v61m-290 0h332" stroke="#52647b" stroke-width="18" stroke-linecap="round"/>'
            '<circle cx="532" cy="86" r="42" fill="#fcd116" stroke="#2453b8" stroke-width="8"/>'
            f'<text x="532" y="99" text-anchor="middle" class="sign-count">{sign_quantity}</text>'
            '</svg>'
        )
        project_name = escape(project.get('name') or 'Project title unavailable')
        source = escape(project.get('source') or 'POW')
        code = escape(project.get('code') or 'not recorded')
        graphic = (
            '<div class="integrated-outlier sign-integrated">' + sign +
            f'<h3 class="integrated-project-title">{project_name}</h3>'
            f'<p class="integrated-context">{escape(category)} · highest parsed unit rate · '
            f'median ₱{median:,.0f} per sign · {sign_quantity} {sign_word} listed</p>'
            f'<p class="integrated-source">Source: {source} · project code {code} · POW page {escape(pages_text)}</p>'
            '</div>'
        )
        title = 'A ROAD PROJECT SIGN, ONE PRICE AT A TIME' if category == 'Roads' else 'A BRIDGE PROJECT SIGN, ONE PRICE AT A TIME'
        panels.append((number, f'{category.upper()} · BILLBOARD PRICE', title,
                       graphic, 'The large price is the parsed item rate per sign. The pictured board is illustrative; sign specifications may differ. The median gives context across parsed projects.'))

    pages = []
    for number, label, headline, graphic, takeaway in panels:
        pages.append(f'<section class="simple-panel" id="lead-{number}"><div class="panel-label">{number} · {escape(label)}</div><h2>{escape(headline)}</h2><figure>{graphic}<figcaption>{escape(takeaway)}</figcaption></figure></section>')

    details = (
        f'<p><strong>Length coverage:</strong> Roads: {roads["withStatedLength"]:,} of {roads["lineItems"]:,} line items have a usable stated length; bridges: {bridges["withStatedLength"]:,} of {bridges["lineItems"]:,}. The offline DPWH inventory adds {roads["assetLengthsMatched"]:,} existing road-section length matches and {bridges["existingSpansMatched"]:,} existing bridge spans. These dimensions do not fill missing funded work lengths; {roads["assetLengthWhenTitleLengthMissing"]:,} road rows have an asset length while the title length is missing.</p>'
        f'<p><strong>Per-meter ratios:</strong> Roads use {rr["records"]:,} line items with stated lengths; median ₱{rr["medianPesosPerMeter"]:,.2f}/m, Q1 ₱{rr["q1PesosPerMeter"]:,.2f}, Q3 ₱{rr["q3PesosPerMeter"]:,.2f}. Bridges use {br["records"]:,}; median ₱{br["medianPesosPerMeter"]:,.2f}/m, Q1 ₱{br["q1PesosPerMeter"]:,.2f}, Q3 ₱{br["q3PesosPerMeter"]:,.2f}. These divide whole proposed allocation by title-stated length. They are not verified construction costs.</p>'
        f'<p><strong>Bridge rehabilitation:</strong> The review covers {rehab["projects"]:,} rehabilitation/repair rows; {rehab["withInventoryBridgeId"]:,} have an inventory bridge ID; {rehab["withInventoryCondition"]:,} have a condition label. Condition counts: Good {condition["Good · assessment year unknown"]:,}, Fair {condition["Fair · assessment year unknown"]:,}, Poor {condition["Poor · assessment year unknown"]:,}, Bad {condition["Bad · assessment year unknown"]:,}, no matched condition {condition["No inventory condition match"]:,}. The retained DPWH Transparency snapshot shows {rehab["transparencyDocumentStatuses"]["5+ documents listed"]:,} rows with 5+ documents listed, {rehab["transparencyDocumentStatuses"]["Fewer than 5 listed"]:,} with fewer than 5, and {rehab["transparencyDocumentStatuses"]["No verified title match in snapshot"]:,} without a verified title match. That snapshot records document listings, not completed construction; retrieved {data["transparencySnapshotRetrievedAtUtc"]}.</p>'
        f'<p><strong>Billboards:</strong> In parsed as-submitted POWs, reconciled to Senate HGAB POW rows where available: roads {road_billboard["projectCount"]:,} projects with a usable “Project Billboard / Signboard · each” rate (median ₱{road_billboard["medianPesos"]:,.2f}; Q1–Q3 ₱{road_billboard["q1Pesos"]:,.2f}–₱{road_billboard["q3Pesos"]:,.2f}; maximum ₱{road_billboard["maximumPesos"]:,.2f}); bridges {bridge_billboard["projectCount"]:,} (median ₱{bridge_billboard["medianPesos"]:,.2f}; Q1–Q3 ₱{bridge_billboard["q1Pesos"]:,.2f}–₱{bridge_billboard["q3Pesos"]:,.2f}; maximum ₱{bridge_billboard["maximumPesos"]:,.2f}). Item descriptions may cover different specifications; high values need source review.</p>'
    )

    data_text = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Six simple visuals about DPWH road and bridge allocations, stated lengths, bridge records and billboard unit rates."><title>Roads and bridges in six pictures · BetterGov</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6fa;color:#17233b;font-family:Inter,system-ui,sans-serif}}header{{background:#00246a;color:#fff;padding:34px 5vw}}header h1{{font-size:clamp(34px,5vw,60px);line-height:1.06;max-width:1000px;margin:0}}header p{{max-width:850px;line-height:1.5}}main{{max-width:1250px;margin:auto;padding:24px clamp(16px,4vw,44px)}}.simple-intro{{font-size:clamp(19px,2.3vw,27px);line-height:1.42;max-width:950px;margin:16px 0 30px;font-weight:600}}.simple-panel{{background:#fff;border:1px solid #dfe5ef;border-radius:20px;padding:clamp(20px,4vw,44px);margin:24px 0;box-shadow:0 7px 22px #17324d0a}}.panel-label{{color:#526b8c;font-size:12px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}}.simple-panel h2{{font-size:clamp(25px,3.1vw,39px);line-height:1.15;max-width:980px;margin:12px 0 22px}}figure{{margin:0}}figcaption{{color:#4d607a;line-height:1.55;margin:14px 0 4px}}.coverage-pair{{display:grid;grid-template-columns:1fr 1fr;gap:26px}}.coverage-pair h3{{margin:0 0 10px}}.coverage-grid{{display:grid;grid-template-columns:repeat(10,1fr);gap:5px;max-width:520px}}.coverage-unit{{height:17px;border-radius:4px;background:#2453b8}}.coverage-unit.orange{{background:#de8c18}}.coverage-unit.empty{{background:#e4e8f0}}.coverage-pair p{{font-size:18px;margin:11px 0}}.asset-facts{{display:flex;gap:12px;flex-wrap:wrap;margin-top:26px}}.asset-facts span{{background:#f1f5fa;border-radius:12px;padding:12px 18px}}.asset-facts b{{font-size:24px;color:#0038a8;display:block}}.outlier-card{{margin:16px 0 10px;padding:18px;border:1px solid #ccd7e6;border-left:5px solid #c45c17;border-radius:12px;background:#fbfcfe}}.outlier-pair{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px}}.outlier-spotlight{{min-width:0;padding:clamp(18px,3vw,30px);border:1px solid #ccd7e6;border-radius:18px;background:linear-gradient(145deg,#fff,#f5f8fc);box-shadow:0 8px 24px #17324d0c}}.outlier-category{{font-size:12px;font-weight:800;letter-spacing:.08em;text-transform:uppercase;color:#536982}}.spotlight-equation{{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:18px 0 5px;color:#354d68;font-size:clamp(14px,1.7vw,18px);font-weight:700}}.spotlight-equation span{{padding:8px 10px;border-radius:8px;background:#eaf0f8}}.spotlight-equation b{{color:#8390a0;font-size:22px}}.spotlight-rate{{display:block;margin:5px 0;font-size:clamp(34px,5.5vw,62px);letter-spacing:-.04em;line-height:1.05;color:#9a3412;overflow-wrap:anywhere}}.spotlight-subtitle{{margin:5px 0 12px;color:#536982;font-size:14px;font-weight:650}}.outlier-spotlight h3{{margin:14px 0;font-size:17px;line-height:1.4;overflow-wrap:anywhere}}.outlier-facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:8px;margin-top:12px}}.outlier-facts span{{padding:9px;background:#f0f4f8;border-radius:8px;font-size:13px;overflow-wrap:anywhere}}.outlier-facts b{{display:block;margin-bottom:3px;color:#52647b;font-size:11px;text-transform:uppercase;letter-spacing:.04em}}.outlier-source{{margin:10px 0 0;color:#53627a;font-size:12px;overflow-wrap:anywhere}}svg{{max-width:100%;height:auto}}.chart-label{{font-size:16px;fill:#183643}}.chart-value{{font-size:14px;font-weight:750;fill:#183643}}.chart-axis{{font-size:12px;fill:#526c78}}.rate-chart,.condition-chart{{width:100%;max-width:980px}}.burol-spotlight{{display:flex;align-items:center;justify-content:center;gap:clamp(24px,9vw,120px);flex-wrap:wrap;text-align:center}}.burol-amount{{font-size:clamp(54px,10vw,112px);font-weight:850;color:#00246a;letter-spacing:-.06em}}.burol-rate{{font-size:clamp(40px,7vw,78px);font-weight:850;color:#b45309;line-height:1}}.burol-rate small{{display:block;font-size:16px;letter-spacing:0;color:#465a72;font-weight:650;margin-top:8px}}.burol-drawing{{display:block;margin:10px auto 0;max-height:190px}}.billboard-icon{{width:100px;margin:0 auto 10px}}.billboard-icon svg{{width:100%}}.simple-footer{{text-align:center;color:#53627a;padding:28px 0 50px;line-height:1.6}}.simple-footer nav,.simple-links{{display:flex;gap:18px;justify-content:center;flex-wrap:wrap}}.simple-footer a{{color:#0038a8;font-weight:650}}.simple-download{{display:inline-block;background:#0038a8;color:white!important;padding:12px 18px;border-radius:8px;text-decoration:none}}.computations{{margin-top:14px;border-top:1px solid #e1e6ee;padding-top:12px;color:#53627a}}.computations summary{{cursor:pointer;font-weight:700;color:#334c6e}}.computations p{{line-height:1.55}}.integrated-outlier{{display:flex;flex-direction:column;align-items:center;gap:14px;text-align:center}}.integrated-metrics{{display:flex;align-items:center;justify-content:center;gap:clamp(12px,3vw,38px);flex-wrap:wrap;width:100%;text-align:center}}.integrated-metric{{display:flex;flex-direction:column;align-items:center;gap:3px}}.integrated-metric strong{{font-size:clamp(30px,5vw,58px);line-height:1;font-weight:850;letter-spacing:-.05em;color:#00246a;overflow-wrap:anywhere}}.integrated-metric span{{font-size:13px;font-weight:650;color:#536982}}.integrated-result strong{{color:#b45309}}.road-integrated .road-drawing{{margin-top:0}}.integrated-project-title{{max-width:950px;margin:4px 0 0;text-align:center;font-size:clamp(18px,2.1vw,24px);line-height:1.35;overflow-wrap:anywhere}}.integrated-context,.integrated-source{{margin:0;color:#536982;line-height:1.5}}.integrated-context{{font-size:15px;font-weight:650}}.integrated-source{{font-size:12px}}.signboard-drawing .sign-price{{font-size:54px;font-weight:850;fill:#00246a}}.signboard-drawing .sign-unit{{font-size:23px;font-weight:700;fill:#536982}}.sign-integrated .signboard-drawing{{max-width:900px}}@media(max-width:700px){{.coverage-pair{{grid-template-columns:1fr}}.coverage-unit{{height:13px}}.asset-facts{{display:grid;grid-template-columns:1fr 1fr}}}}
</style></head><body class="dpwh-simple"><header><div class="panel-label" style="color:#fcd116">BetterGov · Budget research</div><h1>Roads and bridges in six pictures</h1><p>What lengths are stated, what inventory can tell us, and what some visible project items cost.</p></header><main><p class="simple-intro">A budget title is only a starting point. These visuals show the records we can compare—and where the available evidence runs out.</p>{''.join(pages)}<section class="simple-panel"><h2>How to read these comparisons</h2><p>HGAB amounts are proposed allocations, not verified spending. Per-meter figures divide the whole allocation by the length stated in the title; they are screening ratios, not confirmed construction costs. Existing inventory dimensions do not establish funded work quantities.</p><p>Inventory condition labels have no assessment dates in the matched rows. DPWH Transparency document counts do not confirm physical completion. Parsed billboard prices do not establish the sign’s required specification, quality or installation.</p>{detail(details)}</section><footer class="simple-footer"><a class="simple-download" href="dpwh-simple-data.json" download>Download figures as JSON</a><p>Source scope: domestic DPWH road and bridge records in the FY2027 HGAB 3rd-reading extract and parsed Proposal/Senate HGAB POW rows. Full methods and record-level review are linked from the supporting pages.</p><div class="simple-links"><a href="cost-per-km.html">Cost per meter and lane-meter ↗</a><a href="cost-per-unit.html">Cost per Unit ↗</a><a href="cost-matching.html">Asset matching and length coverage ↗</a></div></footer></main>
</body></html>'''
    from uniform_report_menu import apply_page as apply_menu
    from report_table_presentation import apply_page_table_module
    html = apply_menu(html, PAGE)
    html, contract = apply_page_table_module(PAGE, html)
    for directory in (OUT, STATIC):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / PAGE).write_text(html, encoding='utf-8')
        (directory / 'dpwh-simple-data.json').write_text(data_text, encoding='utf-8')
    return {'page': PAGE, 'infographics': len(panels), 'bytes': len(html.encode()), 'tableContract': contract}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
