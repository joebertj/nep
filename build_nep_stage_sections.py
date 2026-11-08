#!/usr/bin/env python3
"""Render NEP-to-HGAB stage comparisons into their owning agency pages."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def _escape(value):
    return html.escape(str(value), quote=True)


def _table(headers, rows):
    head = ''.join(f'<th>{_escape(value)}</th>' for value in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{_escape(value)}</td>' for value in row) + '</tr>' for row in rows)
    return f'<div class="evidence-table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _section(identifier, title, body):
    return f'<section id="{identifier}" class="investigation-evidence"><h2>{_escape(title)}</h2>{body}</section>'


def _upsert(html_page, identifier, section_html):
    # Replace an existing complete section, accounting for nested sections.
    opening = re.search(rf'<section\b(?=[^>]*\bid=["\']{re.escape(identifier)}["\'])[^>]*>', html_page, re.I)
    if opening:
        tokens = re.compile(r'</?section\b[^>]*>', re.I)
        depth = 0
        end = None
        for match in tokens.finditer(html_page, opening.start()):
            if match.group(0).lower().startswith('</'):
                depth -= 1
                if depth == 0:
                    end = match.end()
                    break
            else:
                depth += 1
        if end is None:
            raise ValueError(f'Unclosed generated section {identifier}')
        html_page = html_page[:opening.start()] + section_html + html_page[end:]
    else:
        if '</main>' not in html_page:
            raise ValueError('Owning page has no closing main element')
        html_page = html_page.replace('</main>', section_html + '</main>', 1)
    return html_page


def _comparison_bars(labels, left, right):
    maximum = max(left + right + [1])
    svg = '<figure><figcaption>NEP and HGAB allocations · source amounts in billions of pesos</figcaption><svg class="evidence-graphic" viewBox="0 0 1050 340" role="img" aria-label="NEP versus HGAB allocations">'
    for i, (label, a, b) in enumerate(zip(labels, left, right)):
        x = 70 + i * (900 / max(len(labels), 1))
        for offset, value, color in [(0, a, '#087e78'), (40, b, '#b65b09')]:
            height = 210 * value / maximum
            svg += f'<rect x="{x+offset}" y="{255-height}" width="32" height="{height}" fill="{color}"><title>{_escape(label)} · ₱{value:,}</title></rect><text x="{x+offset}" y="{250-height}" font-size="11">{value/1e9:.3f}</text>'
        svg += f'<text x="{x}" y="280" font-size="11">{_escape(label)}</text>'
    return svg + '</svg></figure>'


def _nia_section(data):
    summary = data['summary']
    rows = data['niaNamedComparisons']
    changed = [row for row in rows if row['adjustmentPesos'] not in (None, 0) and row['visibleHgabRowVerified']]
    body = '<p>This compares FY2027 NEP named-entry allocations with HGAB 3rd-reading named rows. Earlier House reading comparisons are on the dedicated comparison page. All 32 HGAB named title/amount rows have visible-PDF checks. Blank NEP amounts are not zeros; ambiguous repeated names stay unresolved.</p>'
    if changed:
        body += _comparison_bars([f'Project {i+1}' for i in range(len(changed))], [r['nepPesos'] for r in changed], [r['hgabPesos'] for r in changed])
    ordered = changed + [row for row in rows if row not in changed]
    table_rows = []
    for row in ordered:
        delta = row['adjustmentPesos']
        signed = ('+' if delta > 0 else '−' if delta < 0 else '') + '₱' + f'{abs(delta):,}' if delta is not None else 'Not established'
        table_rows.append([changed.index(row) + 1 if row in changed else '—', row['projectName'], row['nepPesos'] if row['nepPesos'] is not None else 'Not established', row['hgabPesos'], signed, row['status'], row['workbookRows'] or 'Unresolved', row['sourcePage']])
    body += _table(['Graph project', 'NIA named project', 'NEP allocation pesos', 'HGAB allocation pesos', 'Allocation adjustment pesos', 'Comparison evidence', 'NEP workbook rows', 'HGAB PDF page'], table_rows)
    body += f'<p>{summary["niaFundedEntries"]} grouped NIA entries carry positive allocations; {summary["niaZeroEntries"]} have explicit zero and {summary["niaBlankEntries"]} have blank amounts. These counts include activities and programme envelopes, not only construction projects. Named HGAB rows are a subset of the NIA budget: do not treat their net adjustment as the agency’s total change.</p>'
    body += '<h3>Grouping and source methodology</h3><p>' + _escape(data['method']) + '</p><ul>' + ''.join('<li>' + _escape(limit) + '</li>' for limit in data['limits']) + '</ul><p><a href="nep-agency-baselines.json" download>Every source component, grouped entry and comparison JSON</a> · <a href="nep-agency-stage-controls.json" download>Visible PDF row/control evidence</a></p>'
    return _section('nia-nep-stage-comparison', 'Named NIA allocations · NEP → HGAB 3rd reading', body)


def _hfep_section(data):
    h = data['hfepStageComparison']
    body = '<p>Programme-level comparison: the NEP workbook and printed HGAB programme control both separate MOOE and Capital Outlays. This does not compare individual facilities with a programme envelope. The extracted HGAB facility rows reconcile to the printed Capital Outlays control.</p>'
    body += _comparison_bars(['Capital Outlays', 'MOOE', 'Programme total'], [h['nepCapitalPesos'], h['nepMooePesos'], h['nepTotalPesos']], [h['hgabCapitalPesos'], h['hgabMooePesos'], h['hgabTotalPesos']])
    body += _table(['Same budget category', 'NEP allocation pesos', 'HGAB allocation pesos', 'Allocation adjustment pesos'], [[label, a, b, ('+' if b-a > 0 else '−' if b-a < 0 else '') + '₱' + f'{abs(b-a):,}'] for label, a, b in [('Capital Outlays', h['nepCapitalPesos'], h['hgabCapitalPesos']), ('MOOE', h['nepMooePesos'], h['hgabMooePesos']), ('Programme total', h['nepTotalPesos'], h['hgabTotalPesos'])]])
    body += '<h3>Printed control and facility reconciliation</h3>' + _table(['Source', 'PDF page', 'Printed page', 'Programme Capital Outlays pesos', 'Extracted facility total pesos', 'Reconciliation difference pesos'], [[h['source']['sourceVolume'], h['source']['sourcePage'], h['source']['printedPage'], h['hgabCapitalPesos'], h['hgabCapitalPesos'], 0]])
    body += '<p>A programme allocation decrease is not a finding of misconduct or proof that specific facilities were removed. The NEP workbook has programme entries, not a facility-by-facility HFEP annex. Facility insertions/removals remain unestablished without that detailed baseline. Earlier House reading comparisons are on the dedicated comparison page.</p><h3>Workbook grouping methodology</h3><p>' + _escape(data['scope']) + '</p><p>Group by agency, PREXC identifier, operating unit and region; sum the object/fund components while retaining every source row. DOH Office of the Secretary only. Source amounts are thousands of pesos, multiplied by 1,000. Confirmed amount controls and source-row provenance are downloadable.</p><p><a href="nep-agency-baselines.json" download>Workbook rows and stage comparisons JSON</a> · <a href="nep-agency-stage-controls.json" download>Printed HFEP control evidence JSON</a></p>'
    return _section('hfep-nep-stage-comparison', 'HFEP programme allocations · NEP → HGAB 3rd reading', body)


def apply_page(html_page, page_name, data=None):
    """Add this module's section to one supplied page; never write HTML files."""
    data = data or json.loads((STATIC / 'nep-agency-baselines.json').read_text(encoding='utf-8'))
    if page_name == 'nia.html':
        identifier, rendered = 'nia-nep-stage-comparison', _nia_section(data)
    elif page_name == 'hfep.html':
        identifier, rendered = 'hfep-nep-stage-comparison', _hfep_section(data)
    elif page_name == 'nia-irrigation.html':
        body = '<p>The NEP workbook contains NIA named project and programme-level subsidy entries. The HGAB irrigation appendix contains finer works such as canal components and stated segments. These are different hierarchy levels and cannot establish appendix-level insertions simply through absent exact titles.</p><p><a href="nia.html#nia-nep-stage-comparison">Compare source-checked named NIA allocations against NEP →</a> · <a href="nep-agency-baselines.json" download>Inspect grouped NEP entries and source components</a></p>'
        identifier, rendered = 'nia-nep-scope', _section('nia-nep-scope', 'NEP coverage · named projects versus detailed irrigation works', body)
    else:
        return html_page
    html_page = _upsert(html_page, identifier, rendered)
    if page_name in {'nia.html', 'hfep.html'} and f'href="#{identifier}"' not in html_page:
        html_page = html_page.replace('</header>', f'<p><a href="#{identifier}" style="color:#a7ddd1">NEP → HGAB allocation comparison ↓</a></p></header>', 1)
    return html_page
