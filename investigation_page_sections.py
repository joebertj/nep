"""Investigation sections rendered by their owning report page builders."""
import csv
import html
import json
from collections import Counter
from pathlib import Path
from hgab_matching import UNMATCHED, is_fap

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def _esc(value):
    return html.escape(str(value), quote=True)


def _section(identifier, title, body):
    return f'<section id="{identifier}" class="investigation-evidence"><h2>{_esc(title)}</h2>{body}</section>'


def _table(headers, rows):
    head = ''.join(f'<th>{_esc(value)}</th>' for value in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{_esc(value)}</td>' for value in row) + '</tr>' for row in rows)
    return f'<div class="evidence-table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _replace_section(page, identifier, replacement):
    import re
    pattern = rf'<section\b(?=[^>]*\bid=["\']{identifier}["\'])[^>]*>.*?</section>'
    if re.search(pattern, page, re.S):
        return re.sub(pattern, lambda _m: replacement, page, count=1, flags=re.S)
    if '</main>' not in page:
        raise ValueError(f'Cannot attach {identifier}: page has no </main> anchor')
    return page.replace('</main>', replacement + '</main>', 1)


def rcs_sections():
    data = json.loads((STATIC / 'rcs-data.json').read_text())
    trace_path = STATIC / 'rcs-stage-trace.json'
    if trace_path.is_file():
        trace = json.loads(trace_path.read_text()).get('summary', {})
    else:
        from build_rcs_stage_trace import build
        trace = build()['summary']
    rows = data['districts']
    n = len(rows)
    current = [int(row.get('currentUnits', 1)) for row in rows]
    province = [int(row['recommendedUnits']) for row in rows]
    rain = [float(row['averageAnnualMm']) for row in rows]
    moved = sum(abs(a - b) for a, b in zip(current, province)) / 2
    district_total = sum(int(row['currentPesos']) for row in rows)
    variation = max(rain) / min(rain)
    first = _section('rcs-statistical-evidence', 'Uniform allocations · formula sensitivity',
        f'<p>All {n} district-office lines receive one ₱4.2M budget unit, while their province or regional rainfall proxies span {min(rain):,.0f}–{max(rain):,.0f} mm/year ({variation:.2f}×). Identical allocation amounts do not establish that planners ignored other factors.</p>'
        + _table(['Scenario check', 'Value'], [['District offices', n], ['Allocation per office', '₱4,200,000'], ['Total district-office allocation', f'₱{district_total:,}'], ['Units moved under existing province-first scenario', f'{moved:,.0f}']])
        + '<p class="caution">A standard package or minimum-coverage policy could explain equal amounts. Rainfall alone does not measure demand; verify sites, catchments, design capacity, water demand, access and existing assets before making a needs claim.</p>')
    second = _section('rcs-stage-evidence', 'Even distribution · did any RCS allocation disappear in HGAB?',
        '<p><strong>The observed pattern is 199 DEO lines at ₱4.2M each.</strong> Whether planners considered need outside the schedule requires policy or design records.</p>'
        + _table(['Stage check', 'DEO RCS lines'], [['Retained unchanged in HGAB', trace.get('unchangedInHGAB', 'Not available')], ['No selected HGAB counterpart', trace.get('withoutSelectedCounterpart', 'Not available')], ['Allocation decreases in HGAB', trace.get('allocationDecreases', 'Not available')]])
        + '<p><a href="rcs-stage-trace.csv" download>Export RCS stage/scenario lines CSV</a> · <a href="rcs-stage-trace.json">Source and LEG reference evidence JSON</a></p><p class="caution">A named LEG cannot be declared a recipient or loser without installation locations, applicable boundaries and evidence of the funded service area.</p>')
    return first, second


def dpwh_oo2_section():
    path = ROOT / 'analysis_output/hb_nep_comparison_3rd.csv'
    oo2_path = ROOT / 'analysis_output/dpwh_oo2_hgab_impact.json'
    if not path.is_file() or not oo2_path.is_file():
        raise FileNotFoundError('DPWH investigation section needs the current comparison CSV and OO2 impact JSON')
    with path.open(newline='') as stream:
        comparisons = list(csv.DictReader(stream))
    oo2 = json.loads(oo2_path.read_text())
    excluded = {row['hgabCandidate']['id'] for row in oo2['records'] if row.get('status') == 'High-confidence candidate' and row.get('hgabCandidate')}
    domestic = [row for row in comparisons if row.get('comparison') == UNMATCHED and not is_fap(row) and row.get('hgab_id') not in excluded]
    fap = [row for row in comparisons if row.get('comparison') == UNMATCHED and is_fap(row)]
    counts = Counter(row.get('comparison', 'Unclassified') for row in comparisons)
    body = '<p>These statuses partition native HGAB rows; they are not certified outcomes. Schedule totals can reconcile while individual titles, offices or occurrence links remain wrong.</p>'
    body += _table(['NEP counterpart screen', 'Native HGAB allocation records'], sorted(counts.items()))
    domestic_pesos = sum(int(row['amountPesos']) for row in domestic)
    fap_pesos = sum(int(row['amountPesos']) for row in fap)
    body += f'<p>{len(domestic):,} domestic candidate lines carry ₱{domestic_pesos:,}. The {len(fap):,} unpaired FAP lines carrying ₱{fap_pesos:,} remain a separate review. High-confidence OO2 matches are excluded from the domestic count. Neither bucket is proof of insertion; new wording, combined occurrences or parser fragments can hide existing NEP projects.</p><p class="caution">Manually audit a stratified sample by program, office class and amount band, oversampling high-value candidates. The comparison export is not a count of certified added projects.</p>'
    return _section('hgab-investigation-evidence', 'Insertion candidates · what the matching can establish', body)


def congress_section():
    data = json.loads((STATIC / 'congress-data.json').read_text())
    summary = data['summary']
    total = int(summary['sourceTotalPesos'])
    coverage = summary['strictAssignedPesos'] / total if total else 0
    body = f'<p>Strict attribution covers {summary["uniquelyAssignedLines"]:,}/{summary["sourceLineItems"]:,} source lines ({summary["uniquelyAssignedLines"]/summary["sourceLineItems"]:.1%}) and {coverage:.1%} of extracted allocation value. The remaining money is excluded from strict LEG rankings, not missing from the budget.</p>'
    body += _table(['Attribution outcome', 'HGAB lines', 'Allocation pesos'], [['Strict single LEG', summary['uniquelyAssignedLines'], summary['strictAssignedPesos']], ['Shared or unresolved', summary['strictExcludedLines'], summary['strictExcludedAmountPesos']]])
    body += '<p class="caution">District totals are evidence-supported lower-coverage totals, not complete receipts or amounts sponsored by representatives. Offices are not legislative seats. Homonymous places require geographic context; multi-place routes cannot be assigned to one LEG without segment evidence.</p><p>Measure unresolved coverage using project locations and dated boundaries before comparing districts. Province splits, historical names, shared DEOs and school names can change attribution.</p>'
    return _section('congress-investigation-evidence', 'Ranking coverage and location exclusions', body)


def innovations_section():
    data = json.loads((STATIC / 'budget-innovations-data.json').read_text())
    inspire = next(row for row in data['candidates'] if row['id'] == 'inspire')
    historical = [row for row in inspire['historical'] if row.get('n')]
    body = '<p>INSPIRE is a returning named project, not a keyword appearing for the first time. Separate history of wording from history of funded scope.</p>'
    body += _table(['Stage/year', 'Observed allocation pesos'], [[f'GAA {row["year"]}', int(row['pesos'])] for row in historical] + [['NEP 2027', int(inspire['fy2027Pesos'])]])
    body += '<p class="caution">Past enacted allocations plus a new proposal do not establish duplicate spending, actual release or disbursement. Ask for approved total project cost, component scope, procurement phases, progress, obligations and remaining balance.</p>'
    return _section('innovation-investigation-evidence', 'Returning labels · INSPIRE funding history', body)


def apply_owned_sections(page, owner):
    """Render sections for one page owner only; never reads or writes HTML files."""
    renderers = {
        'rcs.html': rcs_sections,
        'dpwh-OO2-hgab.html': lambda: (dpwh_oo2_section(),),
        'congress.html': lambda: (congress_section(),),
        'budget-innovations.html': lambda: (innovations_section(),),
    }
    if owner not in renderers:
        raise KeyError(f'No investigation section renderer registered for {owner}')
    for block in renderers[owner]():
        match = __import__('re').search(r'<section\b[^>]*\bid="([^"]+)"', block)
        page = _replace_section(page, match.group(1), block)
    return page
