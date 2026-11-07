"""Shared wording and structure updates for the DPWH HGAB page."""
import re


def render_revision_context(html: str, data: dict) -> str:
    """Apply the reading-stage labels to one DPWH HGAB page string."""
    html = html.replace(
        '<tr><th>Project</th><th>Program / category</th><th>Office</th><th class="num">Amount*</th>',
        '<tr><th>Fiscal year</th><th>Project</th><th>Program / category</th><th>Office</th><th class="num">Amount*</th>',
    )
    html = html.replace('colspan="12" class="empty">No matching potential repeats', 'colspan="13" class="empty">No matching potential repeats')
    candidates = data['hbInsertions']
    total = sum(int(row.get('amountPesos') or 0) for row in candidates)
    html = html.replace('<title>DPWH · HGAB insertions (FY2027)</title>', '<title>DPWH · NEP to HGAB review (FY2027)</title>')
    html = re.sub(r'<meta name="description" content="[^"]*">', '<meta name="description" content="FY2027 DPWH NEP to HGAB review queue. Unmatched title records are unresolved until checked against project scope and bill pages; they are not confirmed insertions.">', html, count=1)
    html = html.replace('(HB 10858, second reading)', '(HB 10858, third reading)')
    html = html.replace('without an exact normalized project-title match in the FY2027 NEP extract. These are insertion candidates', 'that remain unmatched after exact-title, embedded-source-title, and fuzzy title screening against the FY2027 NEP')
    html = html.replace('<h1>DPWH: additions in HGAB after the NEP</h1>', '<h1>DPWH: NEP to HGAB review</h1>')
    html = re.sub(r'(<h1>DPWH: NEP to HGAB review</h1>)<p>.*?</p>', r'\1<p>Only records with no exact or plausible fuzzy project-title counterpart in the FY2027 NEP remain in this shortlist. They are title-screen candidates for additions and still need project-scope verification.</p>', html, count=1, flags=re.S)
    html = re.sub(r'<section class="impact-teaser" aria-label="(?:Key finding|NEP to HGAB review status|NEP to HGAB unmatched shortlist)">.*?</section>', f'''<section class="impact-teaser" aria-label="NEP to HGAB unmatched shortlist"><div><span class="impact-teaser-kicker">DPWH · FY2027 NEP to 3rd-reading HGAB</span><div class="impact-teaser-headline">{len(candidates):,}</div><div class="impact-teaser-title">HGAB line items without a plausible NEP title counterpart</div><p class="impact-teaser-copy">Exact titles and fuzzy title counterparts scoring at least 83% are removed from this shortlist.</p></div><div class="impact-teaser-side"><div class="impact-teaser-stat"><strong>₱{total/1e9:,.2f}B</strong><span>allocation across the unmatched shortlist</span></div><p class="impact-teaser-foot">The 83% title screen is a triage rule. Confirm project location, chainage, scope, and the cited bill page before treating a line as a true addition.</p></div></section>''', html, count=1, flags=re.S)
    html = html.replace('<h2>Potential insertions in FY2027 HGAB relative to NEP</h2>', '<h2>FY2027 HGAB line items unmatched to NEP</h2>')
    html = html.replace('<h2>FY2027 HGAB records needing NEP scope review</h2>', '<h2>FY2027 HGAB line items unmatched to NEP</h2>')
    for old, new in [
        ('All potential insertions', 'All unmatched line items'),
        ('All unresolved records', 'All unmatched line items'),
        ('No close title counterpart; review candidate', 'No plausible NEP title counterpart; review candidate'),
        ('Possible title counterpart; review scope', 'Plausible NEP title counterpart; review scope'),
        ('No close title counterpart', 'No plausible NEP title counterpart'),
        ('Possible title counterpart', 'Plausible NEP title counterpart'),
        ('HB candidates by title screen', 'Unmatched HGAB line items after NEP title screening'),
        ('Unresolved records by title-screen result', 'Unmatched HGAB line items after NEP title screening'),
        ('Candidate count and allocation for the current filters.', 'Count and extracted allocation for the unmatched line items.'),
        ('Unresolved-record count and extracted allocations for the current filters.', 'Count and extracted allocation for the unmatched line items.'),
        ('<th>HB project line</th>', '<th>HGAB project</th>'),
        ('<th class="num">HB allocation</th>', '<th class="num">Extracted amount</th>'),
        ('dpwh_hgab_insertion_candidates.csv', 'dpwh_hgab_nep_review_records.csv'),
        ('Export filtered rows to CSV', 'Export filtered review records to CSV'),
        ('The extractor is heuristic and requires checking against the original bill page;', 'The corrected native-text parser reconciles the printed program totals; still check each project against the original bill page;'),
    ]:
        html = html.replace(old, new)
    html = html.replace('<option value="all">All unresolved records</option><option value="novel">No close title counterpart</option><option value="near">Possible title counterpart</option>', '<option value="all">All unmatched line items</option><option value="novel">No plausible NEP title counterpart</option>')
    html = html.replace('<option value="near">Plausible NEP title counterpart</option>', '')
    html = re.sub(r'(<h2>FY2027 HGAB line items unmatched to NEP</h2>\s*<p class="sub">).*?(</p>)', lambda m: m.group(1) + f'After removing exact-title matches and fuzzy title counterparts scoring at least 83%, <strong>{len(candidates):,} HGAB line items</strong> remain, carrying <strong>₱{total/1e9:,.2f}B</strong>. This shortlist is screened for project-title similarity; verify project scope and cited bill page before counting confirmed additions.' + m.group(2), html, count=1, flags=re.S)
    html = re.sub(r'<details open class="card section" id="second-reading-archive">.*?</details>', '', html, count=1, flags=re.S)
    html = re.sub(r"document\.getElementById\('secondReadingCsv'\)\.onclick=.*?;(?=document\.getElementById\('insertionCsv'\)\.onclick=)", '', html, count=1)
    html = html.replace('<a href="dpwh-hgab.html">DPWH · HGAB insertions</a>', '<a href="dpwh-hgab.html">NEP → HGAB (3rd)</a><a href="dpwh-hgab-comparison.html">DPWH 2nd vs 3rd</a><a href="nia-irrigation.html">NIA irrigation</a><a href="deped.html">DepEd</a>', 1)
    return html
