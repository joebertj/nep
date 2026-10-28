#!/usr/bin/env python3
"""Build the CSIIIV-sourced DPWH office-change review and annotate OOP map rows."""
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / 'data_sources/csiiiv/snapshots/34ef5d8cbbacda92f6503ffd9a428569f157f64d/analysis/data/source_comparison_2027.json'
HGAB = ROOT / 'hb10858_3rd_dpwh_projects.json'
DATA = ROOT / 'analysis_output/dpwh_deo_office_changes.json'
PAGE = ROOT.parent / 'open-data-visualization/static/nep-preview/dpwh-hgab.html'
MARKER = '<!-- dpwh-deo-office-changes -->'


def norm(value):
    return re.sub(r'[^a-z0-9]+', '', str(value).lower())


def main():
    snapshot = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
    projects = json.loads(HGAB.read_text(encoding='utf-8'))['data']['data']
    selected = []
    for pair in snapshot['projects']:
        house, nep = pair.get('house'), pair.get('nep')
        if not house or not nep or house.get('office_canonical') == nep.get('office_canonical'):
            continue
        if pair['status'] in ('exact_candidate', 'chainage_candidate'):
            selected.append(pair)
        elif pair['status'] == 'scope_amendment_candidate' and 'San Manuel' in house.get('title', ''):
            selected.append(pair)  # one Isabela scope-adjusted office change
    records = []
    for pair in selected:
        house, nep = pair['house'], pair['nep']
        matches = [row for row in projects if int(row.get('amountPesos') or 0) == int(house.get('amount_php') or 0)
                   and norm(row.get('projectName')) == norm(house.get('title'))]
        hgab_id = matches[0]['id'] if len(matches) == 1 else None
        records.append({
            'hgabProjectId': hgab_id,
            'title': house.get('title', ''),
            'nepOffice': nep.get('office', ''),
            'hgabOffice': house.get('office', ''),
            'nepPage': nep.get('pdf_page'),
            'hgabPage': house.get('pdf_page'),
            'nepAmountPesos': nep.get('amount_php'),
            'hgabAmountPesos': house.get('amount_php'),
            'status': pair.get('status'),
            'confidence': pair.get('confidence'),
            'coordinatePairPrinted': bool(hgab_id and re.search(r'\d{1,2}\.\d+\s*,\s*\d{2,3}\.\d+', house.get('title', ''))),
        })
    records.sort(key=lambda row: (row['hgabPage'] or 0, row['title']))
    mapped = [row for row in records if row['hgabProjectId'] and row['coordinatePairPrinted']]
    mapped_ids = {row['hgabProjectId'] for row in mapped}
    for row in records:
        row['mapUrl'] = f"out-of-place.html?project={row['hgabProjectId']}" if row['hgabProjectId'] in mapped_ids else None
    payload = {
        'source': 'CSIIIV retained source comparison snapshot',
        'snapshotCommit': '34ef5d8cbbacda92f6503ffd9a428569f157f64d',
        'snapshotPath': str(SNAPSHOT.relative_to(ROOT)),
        'scope': 'Exact and chainage candidates with canonical office changes, plus the San Manuel, Isabela scope-adjusted candidate. Two Camiguin operations-center title/scope candidates are excluded pending manual identity review.',
        'count': len(records), 'mappableCount': len(mapped), 'records': records,
    }
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    unmapped = [row for row in records if row['hgabProjectId'] not in mapped_ids]
    rows_html = ''.join(
        '<tr><td>' + html.escape(row['title']) + '</td><td>' + html.escape(row['nepOffice']) + '</td><td>' + html.escape(row['hgabOffice']) + '</td>'
        + f"<td>{html.escape(str(row['nepPage'] or '—'))} → {html.escape(str(row['hgabPage'] or '—'))}</td>"
        + f"<td>₱{int(row['nepAmountPesos'] or 0):,} → ₱{int(row['hgabAmountPesos'] or 0):,}</td>"
        + f"<td>{html.escape(row['status'])}</td></tr>" for row in unmapped
    )
    section = f'''{MARKER}<section class="card" id="deo-office-changes"><h2>61 implementing office changes without plotted coordinates</h2>
<p class="sub">The retained CSIIIV comparison snapshot identifies <strong>{len(records)} candidate line items</strong> where NEP and HGAB list different canonical implementing offices. <strong>{len(mapped)} have printed coordinate pairs</strong> and are available on <a href="out-of-place.html">Out of Place</a>; this section lists the remaining {len(unmapped)} records without mappable coordinates. This is a cross-source review signal, not proof that the project moved administratively or geographically. The Isabela record is scope-adjusted; two Camiguin operations-center candidates are excluded pending identity review.</p>
<p class="sub">Source snapshot: <a href="https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS/tree/34ef5d8cbbacda92f6503ffd9a428569f157f64d">CSIIIV comparison at commit 34ef5d8cbbac</a>. Pages are PDF page numbers from the NEP and HGAB source schedules.</p>
<details open><summary>Show {len(unmapped)} office-change records without plotted coordinates</summary><div class="tablewrap"><table><thead><tr><th>HGAB line item</th><th>NEP office</th><th>HGAB 3rd office</th><th>NEP → HGAB page</th><th>NEP → HGAB allocation</th><th>Comparison status</th></tr></thead><tbody>{rows_html}</tbody></table></div></details></section>'''
    page = PAGE.read_text(encoding='utf-8')
    if MARKER in page:
        start = page.index(MARKER)
        end = page.find('</section>', start) + len('</section>')
        page = page[:start] + page[end:]
    hero_end = page.find('</section>', page.find('<section id="report-hero"')) + len('</section>')
    if hero_end > len('</section>'):
        page = page[:hero_end] + '\n' + section + page[hero_end:]
    else:
        page = page.replace('</main>', section + '</main>')
    jump = '<a href="#deo-office-changes">Office changes · 61</a>'
    nav_end = page.find('</nav></header>')
    if nav_end >= 0 and jump not in page:
        page = page[:nav_end] + jump + page[nav_end:]
    PAGE.write_text(page, encoding='utf-8')
    print(f'Wrote {len(records)} office-change candidates ({len(mapped)} coordinate-mappable; {len(unmapped)} listed on DPWH page).')


if __name__ == '__main__':
    main()
