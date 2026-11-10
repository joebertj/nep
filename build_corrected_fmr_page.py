#!/usr/bin/env python3
"""Build the focused manual-review FMR page."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from build_fmr_dataset import ROOT, OUT, STATIC
from build_mpb_report import PAGE
from sync_connectivity_manual_greens import sync_from_server

MANUAL_RED_LABELS = {
    'section2-visitor-venue': 'Near a mapped visitor venue',
    'section2-subdivision-village': 'Near a subdivision or village',
    'section2-large-residential-property': 'Near a large residential property',
    'section2-restricted-access-property': 'Near a restricted-access property',
    'section2-private-property-cue': 'Near another mapped private-property cue',
    'section2-coordinate-quality': 'Coordinate quality needs review',
    'baywalk-shoreline-review': 'Baywalk / shoreline ecological review',
}


def map_links(row: dict) -> str:
    try:
        start = (float(row['startLatitude']), float(row['startLongitude']))
        end = (float(row['endLatitude']), float(row['endLongitude']))
        if not all(map(lambda v: -90 <= v <= 90, (start[0], end[0]))) or not all(map(lambda v: -180 <= v <= 180, (start[1], end[1]))):
            raise ValueError('coordinates out of range')
    except (KeyError, TypeError, ValueError):
        return 'Map links unavailable · source coordinates missing'
    satellite_start = f'https://www.google.com/maps/@{start[0]:.6f},{start[1]:.6f},17z/data=!3m1!1e3'
    satellite_end = f'https://www.google.com/maps/@{end[0]:.6f},{end[1]:.6f},17z/data=!3m1!1e3'
    route = ('https://www.google.com/maps/dir/?api=1&origin='
             + f'{start[0]:.6f}%2C{start[1]:.6f}&destination={end[0]:.6f}%2C{end[1]:.6f}&travelmode=driving')
    return (
        f'<a href="{html.escape(satellite_start, quote=True)}" target="_blank" rel="noopener noreferrer" title="Google Maps satellite view at the printed start coordinate">Google Maps satellite · start ↗</a>'
        f'<br><a href="{html.escape(satellite_end, quote=True)}" target="_blank" rel="noopener noreferrer" title="Google Maps satellite view at the printed end coordinate">Google Maps satellite · end ↗</a>'
        f'<br><a href="{html.escape(route, quote=True)}" target="_blank" rel="noopener noreferrer" title="Google Maps suggested driving route and distance between printed endpoints; not the project alignment or straight-line measurement">Route + distance ↗</a>'
    )


def generate() -> dict:
    from report_hero_module import STYLE
    from uniform_report_menu import apply_page as apply_uniform_menu
    from build_investigation_summary import CSS as EVIDENCE_CSS
    from report_table_presentation import apply_page_table_module

    manual_snapshot, _ = sync_from_server()
    manual_projects = manual_snapshot['projects']
    source = json.loads((STATIC / 'connectivity-data.json').read_text(encoding='utf-8'))
    # FMR can be rebuilt on its own, so apply the authoritative server review
    # over the shared connectivity snapshot before selecting flagged rows.
    for row in source.get('projects', []):
        record = manual_projects.get(row.get('id'), {})
        row['manualGreenReasons'] = record.get('greenReasons', record.get('reasons', []))
        row['manualGreenNote'] = str(record.get('greenNote') or '')[:2000]
        row['manualRedReasons'] = record.get('redReasons', [])
        row['manualRedReason'] = str(record.get('redReason') or '')[:2000]
    coordinate_rows = [
        row for row in source.get('projects', [])
        if row.get('coordinateQualityFlag') or str(row.get('connectivityClass') or row.get('result') or '').startswith('Coordinate review')
    ]
    coordinate_rows.sort(key=lambda row: (-(float(row.get('coordinateGapMeters') or 0)), row.get('region', ''), row.get('title', '')))
    rows = []
    for row in source.get('projects', []):
        categories = [MANUAL_RED_LABELS[k] for k in row.get('manualRedReasons', []) if k in MANUAL_RED_LABELS]
        note = str(row.get('manualRedReason') or '').strip()
        if not categories and not note:
            continue
        rows.append({
            'id': row.get('id'), 'title': row.get('title', ''), 'region': row.get('region', ''),
            'amountPesos': int(row.get('amountPesos') or 0), 'sourcePage': row.get('sourcePage'),
            'startLatitude': row.get('startLatitude'), 'startLongitude': row.get('startLongitude'),
            'endLatitude': row.get('endLatitude'), 'endLongitude': row.get('endLongitude'),
            'manualFlags': categories, 'manualNote': note,
            'flagCount': len(categories) + bool(note),
        })
    rows.sort(key=lambda r: (-r['amountPesos'], -r['flagCount'], r['region'], r['title']))
    counts = {label: sum(label in row['manualFlags'] for row in rows) for label in MANUAL_RED_LABELS.values()}
    counts = {k: v for k, v in counts.items() if v}
    note_count = sum(bool(row['manualNote']) for row in rows)
    if note_count:
        counts['Free-form manual review note'] = note_count
    payload = {
        'scope': 'FY2027 HGAB FMR projects with a human-assigned red review category or note.',
        'method': 'Rows are included only when a reviewer saved a manual red flag. The list is not an automated risk finding; mapped cues and free-form notes require source and location review.',
        'builtAtUtc': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'projects': rows, 'categoryCounts': counts,
    }
    (OUT / 'fmr-manual-red-flags.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (STATIC / 'fmr-manual-red-flags.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')

    maximum = max(counts.values(), default=1)
    chart = ''.join(
        f'<div class="fmr-manual-red-bar"><span>{html.escape(label)}</span><div><i style="width:{count / maximum * 100:.1f}%"></i></div><strong>{count:,}</strong></div>'
        for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ) or '<p>No manual red flags are currently recorded.</p>'
    table_rows = ''.join(
        '<tr>'
        f'<td>{html.escape(row["title"])}<small>{html.escape(row["id"] or "")}</small></td>'
        f'<td>{"<br>".join(html.escape(x) for x in row["manualFlags"])}'
        f'{"<br>" if row["manualFlags"] and row["manualNote"] else ""}'
        f'{("<strong>Reviewer note:</strong> " + html.escape(row["manualNote"])) if row["manualNote"] else ""}</td>'
        f'<td>{html.escape(row["region"])}</td><td class="amount">₱{row["amountPesos"]:,}</td>'
        f'<td>{map_links(row)}</td><td>PDF p. {html.escape(str(row["sourcePage"] or "—"))}</td></tr>'
        for row in rows
    ) or '<tr><td colspan="6">No projects with manual red flags yet.</td></tr>'

    coordinate_table_rows = ''.join(
        '<tr>'
        f'<td>{html.escape(row.get("title", ""))}<small>{html.escape(str(row.get("id") or ""))} · PDF p. {html.escape(str(row.get("sourcePage") or "—"))}</small></td>'
        f'<td>{html.escape(str(row.get("region") or "—"))}</td>'
        f'<td>{float(row.get("coordinateGapMeters") or 0) / 1000:,.2f} km</td>'
        f'<td class="amount">₱{int(row.get("amountPesos") or 0):,}</td>'
        f'<td>{map_links(row)}</td></tr>'
        for row in coordinate_rows
    ) or '<tr><td colspan="5">No endpoint pairs currently require coordinate review.</td></tr>'
    coordinate_section = (
        '<section class="card fmr-coordinate-review" id="coordinate-review">'
        '<h2>1 · Coordinate review · endpoints over 20 km apart</h2>'
        f'<p>{len(coordinate_rows):,} FMR project rows have printed endpoint coordinates more than 20 km apart. Connectivity spatial matching is suppressed for these rows because of the coordinate gap. This is a data-quality review signal; it does not identify which printed coordinate is wrong or establish the actual route alignment.</p>'
        f'<div class="fmr-manual-red-stats"><div><strong>{len(coordinate_rows):,}</strong><span>projects needing coordinate review</span></div>'
        f'<div><strong>₱{sum(int(row.get("amountPesos") or 0) for row in coordinate_rows):,}</strong><span>listed HGAB allocation</span></div></div>'
        '<p>Open satellite views at both printed endpoints and the suggested driving route to inspect the source locations. Google directions are not the project alignment or a straight-line measurement.</p>'
        '<div class="table-wrap"><table data-report-table-exempt="true"><thead><tr><th>FMR project · source</th><th>Region</th><th>Endpoint gap</th><th class="amount">HGAB allocation</th><th>Map / route</th></tr></thead>'
        f'<tbody>{coordinate_table_rows}</tbody></table></div></section>'
    )

    section = (
        '<main><section class="card fmr-manual-red" id="manual-red-flags">'
        '<h2>2 · Top FMR red flags · manual review</h2>'
        '<p>This section lists only projects with a red category or note saved through manual review. It does not apply distance thresholds, automated connectivity classes, title keyword screens, or other flag logic. HGAB allocation is used only to sort the list, highest first. Mapped venue, subdivision, and property cues do not establish access, ownership, or wrongdoing.</p>'
        f'<div class="fmr-manual-red-stats"><div><strong>{len(rows):,}</strong><span>projects with manual red flags</span></div>'
        f'<div><strong>{sum(int(row["flagCount"]) for row in rows):,}</strong><span>manual flag categories and notes</span></div>'
        f'<div><strong>₱{sum(row["amountPesos"] for row in rows):,}</strong><span>listed HGAB allocation</span></div></div>'
        f'<h3>Manual red-flag categories</h3><div class="fmr-manual-red-chart">{chart}</div>'
        '<p><a href="fmr-manual-red-flags.json" download>Download manually flagged FMR projects as JSON ↗</a>. Satellite links show the printed start and end coordinates. Route + distance opens Google Maps suggested driving directions between those endpoints; it is not the project alignment or a straight-line measurement. '
        '<a href="fmr-archive.html">FMR schedule and analysis archive ↗</a></p>'
        '<div class="table-wrap"><table data-report-table-exempt="true"><thead><tr><th>FMR project</th><th>Manual review flags</th><th>Region</th><th class="amount">HGAB allocation</th><th>Map / route</th><th>Source page</th></tr></thead>'
        f'<tbody>{table_rows}</tbody></table></div></section></main>'
    )
    css = '<style id="fmr-manual-review-style">.fmr-manual-red-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0}.fmr-manual-red-stats>div{display:flex;flex-direction:column;gap:4px;padding:14px;border:1px solid #e3c9c9;border-radius:10px;background:#fff8f7}.fmr-manual-red-stats strong{font-size:clamp(18px,2vw,24px);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.fmr-manual-red-stats span{font-size:13px;color:#52636d}.fmr-manual-red-chart{display:grid;gap:8px;margin:14px 0}.fmr-manual-red-bar{display:grid;grid-template-columns:minmax(180px,1fr) minmax(100px,2fr) auto;align-items:center;gap:10px}.fmr-manual-red-bar>div{height:12px;background:#f2e6e6;border-radius:99px;overflow:hidden}.fmr-manual-red-bar i{display:block;height:100%;background:#b4232e;border-radius:99px}.fmr-manual-red td small{display:block;color:#52636d}@media(max-width:760px){.fmr-manual-red-bar{grid-template-columns:minmax(120px,1fr) minmax(60px,1fr) auto}}@media(max-width:520px){.fmr-manual-red-stats{grid-template-columns:1fr}}</style>'
    head = PAGE.split('</head>', 1)[0].replace('MPB · Multi-purpose building allocations', 'FMR · Manual red-flag review') + '</head>'
    page = head + '<body><header><h1>FMR · Coordinate and manual review</h1><p>Endpoint coordinate quality and human-reviewed red flags.</p></header>' + '<main>' + coordinate_section + section[6:] + '</body></html>'
    page = page.replace('__HERO_STYLE__', STYLE).replace('</head>', css + '</head>', 1)
    page = apply_uniform_menu(page, 'fmr.html')
    page = page.replace('</head>', EVIDENCE_CSS + '</head>', 1)
    page, _ = apply_page_table_module('fmr.html', page)
    (OUT / 'fmr.html').write_text(page, encoding='utf-8')
    (STATIC / 'fmr.html').write_text(page, encoding='utf-8')
    return {'coordinateReviewProjects': len(coordinate_rows), 'manualRedProjects': len(rows), 'manualRedCategories': counts}


if __name__ == '__main__':
    print(json.dumps(generate(), ensure_ascii=False, indent=2))
