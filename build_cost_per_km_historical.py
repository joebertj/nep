#!/usr/bin/env python3
"""Own the all-available-GAA stated-meter history page."""
import json
import math
from pathlib import Path

from build_cost_per_km import OUT, STATIC
from build_mpb_report import PAGE as TEMPLATE
from compare_meter_rates_2026 import build as build_comparison, render as render_comparison
from build_cost_per_km_history_data import build as build_all_year_data

PAGE = 'cost-per-km-historical.html'


def _annual_history_section(data):
    rows = [r for r in data['annual'] if r['usableRecords']]
    chart_rows = [r for r in rows if r['usableRecords'] >= 20]
    years = sorted({r['year'] for r in chart_rows})
    series = [('Roads', '#0038A8'), ('Bridges', '#CE1126'), ('Mixed roads / bridges', '#b65b09')]
    vals = [r['medianPesosPerMeter'] for r in chart_rows if r['medianPesosPerMeter'] and r['medianPesosPerMeter'] > 0]
    if vals:
        lo, hi = math.log10(min(vals)), math.log10(max(vals))
        if hi == lo:
            hi = lo + 1
        left, right, top, bottom = 74, 1084, 30, 300
        x = lambda year: left + (year - min(years)) * (right-left) / max(1, max(years)-min(years))
        y = lambda value: bottom - (math.log10(value)-lo) * (bottom-top) / (hi-lo)
        ticks = []
        for exp in range(math.floor(lo), math.ceil(hi)+1):
            value = 10**exp
            if lo <= exp <= hi:
                yy = y(value)
                ticks.append(f'<line x1="{left}" y1="{yy:.1f}" x2="{right}" y2="{yy:.1f}" stroke="#dce5e3"/><text x="{left-9}" y="{yy+4:.1f}" text-anchor="end" font-size="11">₱{value:,.0f}</text>')
        for year in years:
            ticks.append(f'<text x="{x(year):.1f}" y="{bottom+24}" text-anchor="middle" font-size="11">{year}</text>')
        paths = []
        for kind, color in series:
            points = [r for r in chart_rows if r['category'] == kind]
            if not points:
                continue
            coords = ' '.join(f'{x(r["year"]):.1f},{y(r["medianPesosPerMeter"]):.1f}' for r in points)
            paths.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="3"/>')
            for r in points:
                cx, cy = x(r['year']), y(r['medianPesosPerMeter'])
                paths.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{color}"><title>{r["year"]} {kind}: ₱{r["medianPesosPerMeter"]:,.0f}/m · n={r["usableRecords"]}</title></circle>')
        plotted_categories = {r['category'] for r in chart_rows}
        legend = ''.join(f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:16px"><i style="width:12px;height:12px;border-radius:50%;background:{color}"></i>{kind}</span>' for kind, color in series if kind in plotted_categories)
        svg = f'<svg viewBox="0 0 1120 365" role="img" aria-label="Annual median allocations per stated meter from available DPWH GAA years 2016 to 2026 and FY2027 HGAB comparator"><text x="74" y="17" font-size="12">Median allocation per stated meter · logarithmic scale · at least 20 records and 10 stated meters</text>{"".join(ticks)}{"".join(paths)}<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#617781"/></svg>'
        chart = f'<div style="overflow-x:auto">{svg}</div><p>{legend}</p>'
    else:
        chart = '<p>No qualifying stated-length rates are available in the local annual sources.</p>'
    from build_investigation_summary import table, esc
    by_year = table(['Year · stage','Work category','Usable rate records ≥10 m','Median pesos/meter','25th percentile','75th percentile'],[[f'{r["year"]} · {"HGAB proposal" if r["year"]==2027 else "enacted GAA"}',r['category'],r['usableRecords'],round(r['medianPesosPerMeter'],2),round(r['p25PesosPerMeter'],2),round(r['p75PesosPerMeter'],2)] for r in rows])
    sources = table(['Source years','Source','Rows with a stated-length rate','Source limits'],[[', '.join(map(str,r['years'])),r.get('source') or '—',r.get('rateRows','—'),r.get('limit','Source detail unavailable')] for r in data['sourceNotes']])
    return ('<section id="all-gaa-years" class="card"><h2>All available GAA years · stated-meter rate history</h2>'
            '<p>Annual distributions use locally available project-level DPWH GAA sources for FY2016–FY2026. FY2027 HGAB 3rd reading is shown separately as a proposal comparator. Each point is a year/category median, not a matched-project price trend. The chart requires at least 20 usable records per year/category; the table retains smaller cohorts with their sample sizes shown. Lengths below 10 meters and rows without recoverable stated lengths are excluded from rates.</p>'
            + chart + by_year + '<h3>Source coverage and limits</h3><p>' + esc(data['method']) + '</p>' + sources
            + '<ul>' + ''.join('<li>'+esc(v)+'</li>' for v in data['limits']) + '</ul>'
            + '<p><a href="meter-rates-all-years.json" download>Download annual rates, underlying project rows and source notes</a></p></section>')


def build_page(current=None):
    if current is None:
        current = json.loads((OUT / 'cost_per_km.json').read_text(encoding='utf-8'))
    data = build_comparison(current)
    all_year_data = build_all_year_data(current)
    head = TEMPLATE.split('</head>')[0].replace(
        'MPB · Multi-purpose building allocations',
        'Cost per meter · FY2026 historical comparison',
    ) + '</head>'
    hero = (
        '<section class="repeat-hero"><div class="repeat-hero-primary">'
        '<span class="repeat-hero-kicker">DPWH · available FY2016–FY2026 enacted GAA sources</span>'
        '<h2>Stated-meter allocation history across GAA years</h2>'
        '<p>FY2027 HGAB 3rd reading appears separately as a proposal comparator.</p>'
        '</div><div class="repeat-hero-detail"><p>These are allocation-per-meter screening proxies for different project records, not paired contracts, verified construction prices, or evidence of inflation.</p>'
        '<p>Annual summaries use only rows with recoverable stated lengths of at least 10 meters. Different source coverage and project mix prevent interpreting this as a constant-scope price index.</p>'
        '<p><a href="cost-per-km.html">Return to current stated-meter rates ↗</a></p></div></section>'
    )
    limits = (
        '<aside id="report-evidence-notice" class="report-disclaimer" role="note">'
        '<strong>Evidence limits.</strong> Lengths are parsed from titles and source context. '
        'FMR is excluded. The FY2026/FY2027 detailed comparison needs at least 20 usable records per stage and length band. '
        'Different project mix, dimensions, locations, and funded scope remain uncontrolled.</aside>'
    )
    all_year_section = _annual_history_section(all_year_data)
    comparison = render_comparison(data).replace(
        '2. Historical comparison · are stated-meter allocations higher than FY2026 GAA?',
        'Detailed comparison · FY2026 enacted GAA vs FY2027 HGAB', 1
    )
    page = (
        head + '<body class="bettergov-research"><header><div class="eyebrow">BetterGov · Budget research</div>'
        '<h1>Cost per meter · Historical comparison</h1>'
        '<p>Historical DPWH GAA distributions and a separate FY2027 proposed-budget comparator</p></header>'
        '<main>' + limits + hero + all_year_section + comparison + '</main></body></html>'
    )
    from report_hero_module import STYLE
    page = page.replace('__HERO_STYLE__', STYLE)
    from uniform_report_menu import apply_page as apply_uniform_menu_page
    page = apply_uniform_menu_page(page, PAGE)
    from report_table_presentation import apply_page_table_module
    page, contract = apply_page_table_module(PAGE, page)
    for destination in (STATIC / PAGE, OUT / PAGE):
        destination.write_text(page, encoding='utf-8')
    return {
        'page': PAGE,
        'programComparisons': len(data['programComparisons']),
        'lengthBands': len(data['lengthBandComparisons']),
        'historicalRateRows': len(all_year_data['records']),
        'historicalYears': sorted({r['year'] for r in all_year_data['records']}),
        'tableContract': contract,
    }


def main():
    print(json.dumps(build_page(), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
