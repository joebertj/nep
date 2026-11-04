#!/usr/bin/env python3
"""Build an OO2 amendment sensitivity study alongside the DPWH NEP→HGAB review."""
from __future__ import annotations
import copy, json, re, unicodedata
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parent
SITE = Path('/Users/joebertj/open-data-visualization/static/nep-preview')
ANALYSIS = ROOT / 'analysis_output'
source_amendments = ROOT / 'data_sources/OO2 amendments.json'
source_data = SITE / 'dpwh-data.json'
source_page = SITE / 'dpwh-hgab.html'

amendments = json.loads(source_amendments.read_text())
hgab_data = json.loads(source_data.read_text())
hgab_only = hgab_data['hbInsertions']

def norm(value):
    value = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    value = re.sub(r'\bbrgy\.?\b', 'barangay', value)
    return set(re.sub(r'[^a-z0-9]+', ' ', value).split())

def from_amount(value):
    match = re.search(r'([\d,]+(?:\.\d+)?)\s*$', value or '')
    return float(match.group(1).replace(',', '')) if match else None

prepared = [(row, norm(row.get('projectName'))) for row in hgab_only]
records = []
for amendment in amendments['amendments']:
    title_tokens = norm(amendment.get('projectTitle'))
    to_amount = amendment.get('toAmountPesos')
    from_value = from_amount(amendment.get('fromExistingLine'))
    candidates = []
    for candidate, candidate_tokens in prepared:
        union = title_tokens | candidate_tokens
        similarity = len(title_tokens & candidate_tokens) / max(1, len(union))
        candidates.append((similarity, candidate))
    candidates.sort(key=lambda item: item[0], reverse=True)
    similarity, best = candidates[0]
    title_exact = similarity == 1.0
    amount_exact = to_amount is not None and float(best.get('amountPesos') or 0) == float(to_amount)
    change_amount = (float(to_amount) - from_value) if from_value is not None and to_amount is not None else None
    delta_match = change_amount is not None and abs(float(best.get('amountPesos') or 0) - change_amount) < 1000

    # Statuses deliberately require both distinctive title overlap and a coherent amount.
    if similarity >= .75 and (amount_exact or delta_match):
        status = 'High-confidence candidate'
        rationale = 'Distinctive title overlap and exact amount' if amount_exact else 'Distinctive title overlap; HGAB amount is within ₱1,000 of the amendment increase over the named prior line'
    elif (similarity >= .35 and (amount_exact or (to_amount is not None and abs(float(best.get('amountPesos') or 0)-float(to_amount)) <= 1000))) or (similarity >= .75 and not amount_exact):
        status = 'Review candidate'
        if similarity >= .75 and not amount_exact:
            rationale = 'Strong title overlap, but the HGAB amount differs from the amendment amount'
        else:
            rationale = 'Amount or location aligns, but title overlap is not distinctive enough to count automatically'
    else:
        status = 'Unresolved'
        rationale = 'No candidate clears the title and amount checks; not counted as an HGAB-only reduction'

    # Avoid displaying a weak nearest-name result as if it were a match.
    shown = best if status != 'Unresolved' else None
    records.append({
        'sourceRow': amendment.get('sourceRow'), 'section': amendment.get('section'),
        'projectTitle': amendment.get('projectTitle'), 'fromExistingLine': amendment.get('fromExistingLine'),
        'toAmountPesos': to_amount, 'changeAmountPesos': change_amount,
        'status': status, 'rationale': rationale, 'titleTokenJaccard': round(similarity, 4),
        'titleExactAfterNormalization': title_exact,
        'hgabCandidate': ({'id': best.get('hgab_id'), 'projectName': best.get('projectName'),
                           'amountPesos': best.get('amountPesos'), 'sourcePage': best.get('sourcePage'),
                           'sourceVolume': best.get('sourceVolume')} if shown else None),
    })

high = [r for r in records if r['status'] == 'High-confidence candidate']
review = [r for r in records if r['status'] == 'Review candidate']
unresolved = [r for r in records if r['status'] == 'Unresolved']
high_ids = {r['hgabCandidate']['id'] for r in high if r['hgabCandidate']}
review_ids = {r['hgabCandidate']['id'] for r in review if r['hgabCandidate']}
adjusted_rows = [r for r in hgab_only if r.get('hgab_id') not in high_ids]
adjusted_pesos = sum(int(r.get('amountPesos') or 0) for r in adjusted_rows)
summary = {
    'created': date.today().isoformat(), 'baselineDomesticHgabOnlyCandidates': len(hgab_only),
    'amendmentRows': len(records), 'highConfidenceRows': len(high), 'highConfidenceUniqueHgabCandidates': len(high_ids),
    'reviewRows': len(review), 'reviewUniqueHgabCandidatesNotAlreadyHighConfidence': len(review_ids-high_ids),
    'unresolvedRows': len(unresolved), 'conservativeAdjustedBaseline': len(adjusted_rows),
    'preOO2DomesticAllocationPesos': sum(int(r.get('amountPesos') or 0) for r in hgab_only),
    'OO2AdjustedDomesticAllocationPesos': adjusted_pesos,
    'reviewInclusiveLowerBound': len(hgab_only)-len(high_ids)-len(review_ids-high_ids),
    'sourceWorkbookReportedTotalPesos': amendments['summary']['workbookReportedTotal']['cachedAmountPesos'],
    'parsedAmendmentRowsToAmountTotalPesos': amendments['summary']['sumOfParsedToAmountsPesos'],
    'workbookRowSumMismatch': not amendments['summary']['workbookTotalMatchesParsedRowSum'],
    'method': 'One amendment row is considered a high-confidence candidate only when normalized title token Jaccard similarity is at least 0.75 and the HGAB-only candidate amount exactly equals the amendment amount, or (for a title change) the amount equals the amendment increase over the named prior line within ₱1,000. Review candidates do not reduce the conservative count. Candidate links are investigative correspondences, not official NEP determinations.'
}
output = {'summary': summary, 'records': records}
for path in [ANALYSIS/'dpwh_oo2_hgab_impact.json', SITE/'dpwh-OO2-hgab-data.json', ANALYSIS/'dpwh-OO2-hgab-data.json']:
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n')

base = source_page.read_text()
base = base.replace(
    '<tr><th>Project</th><th>Program / category</th><th>Office</th><th class="num">Amount*</th>',
    '<tr><th>Fiscal year</th><th>Project</th><th>Program / category</th><th>Office</th><th class="num">Amount*</th>',
)
base = base.replace('colspan="12" class="empty">No matching potential repeats', 'colspan="13" class="empty">No matching potential repeats')
base = re.sub(r'<aside\b[^>]*class="[^"]*archived-page-alert[^"]*"[^>]*>.*?</aside>', '', base, flags=re.S)
base = base.replace(':not(#deo-office-changes){display:none!important}', ':not(#deo-office-changes):not(#oo2-impact){display:none!important}')
base = re.sub(r'<title>.*?</title>', '<title>DPWH · OO2-adjusted HGAB-only projects</title>', base, count=1, flags=re.S)
base = base.replace('FY2027 DPWH NEP to HGAB review queue. Unmatched title records are unresolved until checked against project scope and bill pages; they are not confirmed insertions.', 'Study of FY2027 OO2 amendments and possible overlap with domestic HGAB-only candidates. Candidate matches require review and do not establish official NEP status.')
base = re.sub(r'<h1\b[^>]*>.*?</h1>', '<h1>DPWH: OO2-adjusted HGAB-only projects</h1>', base, count=1, flags=re.S)
base = base.replace('<p class="report-header-teaser">How many House budget lines lack a plausible NEP counterpart?</p>', '<p class="report-header-teaser">A sensitivity study of how the OO2 amendments could change the domestic HGAB-only count.</p>')
base = base.replace('</style><script id="ph-location-table-script"', '''
.oo2-study{display:block!important;margin:20px 0 28px;padding:24px;background:#fff;border:1px solid #dce3e1;border-radius:14px;box-shadow:0 10px 30px #213d4b0b}.oo2-study h2{margin-top:0}.oo2-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.oo2-metric{border:1px solid #dce3e1;border-radius:10px;padding:15px}.oo2-metric strong{display:block;font-size:26px;line-height:1.2}.oo2-subtle{color:#637381;font-size:13px}.oo2-controls{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.oo2-controls input,.oo2-controls select{padding:9px 11px;border:1px solid #bbc5c3;border-radius:8px;font:inherit}.oo2-controls input{flex:1;min-width:220px}.oo2-table-wrap{overflow:auto}.oo2-table{width:100%;border-collapse:collapse;min-width:950px;font-size:13px}.oo2-table th,.oo2-table td{padding:10px;border-bottom:1px solid #dce3e1;text-align:left;vertical-align:top}.oo2-table th{background:#eaf0ff;position:sticky;top:0}.oo2-pill{display:inline-block;padding:3px 8px;border-radius:999px;font-weight:700;font-size:11px;background:#e6f5ef;color:#175c41}.oo2-pill.review{background:#fff0d4;color:#805000}.oo2-pill.unresolved{background:#edf0f2;color:#4e5a61}.oo2-study tr[hidden]{display:none}@media(max-width:760px){.oo2-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.oo2-study{padding:16px}}
</style><script id="ph-location-table-script"''')
section = '''<section class="oo2-study" id="oo2-impact"><h2>HGAB-only after OO2 adjustment</h2><p>The current domestic HGAB-only count is <strong id="oo2-m-adjusted">—</strong>. This starts from <strong id="oo2-base">—</strong> unmatched domestic HGAB records and excludes <strong id="oo2-m-high">—</strong> unique records with high-confidence OO2 amendment matches. Nine further amendment rows remain under review and are not excluded from this count; three have no credible match in this screen. The adjustment is a working comparison, not a finding that every amended title has identical scope or that the workbook was formally incorporated into the NEP.</p><div class="oo2-metrics"><div class="oo2-metric"><span class="oo2-subtle">Before OO2 adjustment</span><strong id="oo2-m-base-card">—</strong></div><div class="oo2-metric"><span class="oo2-subtle">OO2 matched records excluded</span><strong id="oo2-m-high-card">—</strong></div><div class="oo2-metric"><span class="oo2-subtle">HGAB-only after adjustment</span><strong id="oo2-m-adjusted-card">—</strong></div><div class="oo2-metric"><span class="oo2-subtle">Amendment rows needing review</span><strong id="oo2-m-review">—</strong></div></div><p id="oo2-range" class="oo2-subtle"></p><p class="report-disclaimer"><strong>Data caveat.</strong> The amendment workbook’s reported total (₱8.277B) does not equal the parsed sum of its 70 “to” amounts (₱10.284B). This page compares records and does not use either total to estimate a budget-wide adjustment. High-confidence rows are excluded only under the stated title-and-amount rule; review rows remain in the HGAB-only count unless their match is verified.</p><h3>Record-by-record OO2 comparison</h3><div class="oo2-controls"><input id="oo2-search" type="search" placeholder="Filter titles, HGAB projects, or source row"><select id="oo2-status"><option value="">All statuses</option><option>High-confidence candidate</option><option>Review candidate</option><option>Unresolved</option></select></div><div class="oo2-table-wrap"><table class="oo2-table"><thead><tr><th>OO2 row / type</th><th>OO2 amendment title</th><th>HGAB record before adjustment</th><th>OO2 amount / increase</th><th>HGAB amount</th><th>Assessment</th></tr></thead><tbody id="oo2-rows"><tr><td colspan="6">Loading amendment comparisons…</td></tr></tbody></table></div><p class="oo2-subtle">The project list and headline breakdowns below use the OO2-adjusted count. The pre-OO2 comparison is preserved on the Archive page.</p></section>'''
main_at = base.index('<main class="wrap">')
disclaimer_end = base.index('</aside>', main_at) + len('</aside>')
hero_match = re.search(r'<section\b[^>]*id="report-hero"[^>]*>.*?</section>', base, flags=re.S)
if not hero_match:
    raise RuntimeError('Could not find the report hero to place below the disclaimer')
hero = hero_match.group(0)
base = base[:hero_match.start()] + base[hero_match.end():]
main_at = base.index('<main class="wrap">')
disclaimer_end = base.index('</aside>', main_at) + len('</aside>')
base = base[:disclaimer_end] + hero + section + base[disclaimer_end:]
# Apply the OO2 subtraction to the existing HGAB-only table and its data response.
adjusted_data = copy.deepcopy(hgab_data)
adjusted_data['hbInsertions'] = adjusted_rows
adjusted_headline = adjusted_data.get('hgabHeadline', {})
for row in high:
    candidate = row.get('hgabCandidate') or {}
    original = next((x for x in hgab_only if x.get('hgab_id') == candidate.get('id')), None)
    if not original:
        continue
    for dimension, value in [('officeBreakdown', original.get('officeType')), ('programBreakdown', original.get('program'))]:
        group = next((x for x in adjusted_headline.get(dimension, []) if x.get('label') == value), None)
        if group:
            group['insertionCount'] = max(0, int(group.get('insertionCount') or 0) - 1)
            group['insertionPesos'] = int(group.get('insertionPesos') or 0) - int(original.get('amountPesos') or 0)
adjusted_headline['insertionCount'] = int(adjusted_headline.get('insertionCount') or 0) - len(high_ids)
adjusted_headline['method'] = 'OO2-adjusted domestic HGAB-only records (58 high-confidence OO2 matches excluded), plus unpaired FAP review records; removal candidates remain on the original NEP basis.'

from build_dpwh_hgab_headlines import count_chart, stats_table
def build_adjusted_headline_section():
    source = hgab_data['hgabHeadline']
    offices, programs = adjusted_headline['officeBreakdown'], adjusted_headline['programBreakdown']
    domestic_removed = sum(int(x.get('removalCount') or 0) for x in offices)
    fap_count = next((int(x['insertionCount']) for x in programs if x['label'] == 'FAPs'), 0)
    total = len(adjusted_rows) + fap_count
    out = (f'<section class="card section" id="hgab-headline-breakdowns"><h2>OO2-adjusted HGAB-only records and NEP removals</h2>'
           f'<p class="sub">After excluding {len(high_ids):,} high-confidence OO2 matches, {len(adjusted_rows):,} domestic HGAB-only candidates remain. Another {fap_count:,} unpaired FAP records remain in a separate review bucket; together these make {total:,} HGAB-only review records. The {domestic_removed:,} domestic removal candidates are unchanged. These are provisional line-item screens, not confirmed legislative changes.</p>'
           '<p class="sub">Nine amendment rows still need title, amount or scope review and remain in the domestic count. Three rows have no credible candidate match. OO2 candidate correspondence does not prove identical scope or formal NEP adoption.</p>'
           '<p class="sub">Implementing offices and programs come from each source schedule. Insertion amounts are HGAB allocations; removal amounts are original NEP allocations, not certified savings.</p>'
           '<button class="export-btn" id="hgabBreakdownCsv" type="button">Export headline breakdowns to CSV</button>')
    for rows, title, dimension in [(offices,'Central Office versus DEOs and other implementing offices','Implementing office category'),(programs,'OO2-adjusted HGAB-only candidates by source program','Program')]:
        chart = count_chart(rows, title).replace('insertion candidates','OO2-adjusted HGAB-only candidates').replace('insertion candidate','OO2-adjusted HGAB-only candidate')
        table = stats_table(rows, dimension).replace('Insertion candidate lines','OO2-adjusted HGAB-only lines')
        out += chart + table
    out += '</section>'
    export = [dict(r,dimension=dimension) for dimension,rows in [('Office',offices),('Program',programs)] for r in rows]
    out += '<script type="application/json" id="hgab-headline-data">'+json.dumps(export,ensure_ascii=False).replace('</','<\\/')+'</script>'
    return out

old_breakdown = re.compile(r'<section class="card section" id="hgab-headline-breakdowns">.*?</section>\s*<script type="application/json" id="hgab-headline-data">.*?</script>', re.S)
base, replaced = old_breakdown.subn(build_adjusted_headline_section(), base, count=1)
if not replaced:
    raise RuntimeError('Could not find the original HGAB headline breakdown to adjust')
base = base.replace('<strong>5,549</strong>', f'<strong>{len(adjusted_rows):,}</strong>')
base = base.replace('5,549', f'{len(adjusted_rows):,}').replace('5,553', f'{adjusted_headline["insertionCount"]:,}')
base = base.replace('₱158.36B', f'₱{adjusted_pesos/1e9:.2f}B').replace('₱158.363B', f'₱{adjusted_pesos/1e9:.3f}B')
base = base.replace('Potential insertions · domestic HGAB-only line items', 'HGAB-only candidates after OO2 adjustment')
base = base.replace('The base review identifies', 'After the OO2 adjustment,')
base = base.replace('The base NEP → HGAB review below remains the original comparison. Its counts exclude this OO2 sensitivity overlay.', 'This table uses the OO2-adjusted domestic HGAB-only count; review and unresolved amendment rows remain included until verified.')
base = base.replace('potential domestic insertion lines', 'OO2-adjusted domestic HGAB-only lines')
base = base.replace('Potential insertions · domestic HGAB-only line items', 'HGAB-only candidates after OO2 adjustment')
base = base.replace('Largest allocations in the selected domestic insertion candidates', 'Largest allocations in the OO2-adjusted domestic HGAB-only candidates')
base = base.replace('Top ten filtered insertion allocations', 'Top ten filtered OO2-adjusted HGAB-only allocations')
base = base.replace('Export filtered insertions to CSV', 'Export filtered HGAB-only records to CSV')
base = base.replace('dpwh_hgab_3rd_domestic_insertions_filtered.csv', 'dpwh_oo2_adjusted_hgab_only_filtered.csv')
base = base.replace('fetch("dpwh-data.json")', 'fetch("dpwh-data.json")')

adjustment_hook = '<script id="oo2-adjusted-data-hook">(()=>{const ids=new Set('+json.dumps(sorted(high_ids))+'),originalFetch=window.fetch.bind(window);window.fetch=(input,init)=>originalFetch(input,init).then(response=>{let url;try{url=new URL(typeof input==="string"?input:input.url,location.href)}catch(e){return response}if(!url.pathname.endsWith("/dpwh-data.json"))return response;return response.clone().json().then(data=>{data.hbInsertions=(data.hbInsertions||[]).filter(r=>!ids.has(r.hgab_id));data.hgabHeadline='+json.dumps(adjusted_headline,separators=(',',':'))+';if(data.hbInsertions3rdSummary?.counts){data.hbInsertions3rdSummary.counts["No plausible NEP title counterpart; review candidate"]=data.hbInsertions.length}if(data.hbInsertions3rdSummary?.allScheduleCounts)data.hbInsertions3rdSummary.allScheduleCounts["No plausible NEP title counterpart; review candidate"]=(data.hbInsertions3rdSummary.allScheduleCounts["No plausible NEP title counterpart; review candidate"]||0)-ids.size;const headers=new Headers(response.headers);headers.delete("content-length");headers.delete("content-encoding");return new Response(JSON.stringify(data),{status:response.status,statusText:response.statusText,headers})})})})();</script>'
base = base.replace('</head>', adjustment_hook+'</head>', 1)
js = '''<script>
(()=>{const fmt=n=>Number(n).toLocaleString('en-PH');const peso=n=>n==null?'—':'₱'+Number(n).toLocaleString('en-PH',{maximumFractionDigits:2});fetch('dpwh-OO2-hgab-data.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(D=>{const s=D.summary;document.getElementById('oo2-base').textContent=fmt(s.baselineDomesticHgabOnlyCandidates);document.getElementById('oo2-m-base-card').textContent=fmt(s.baselineDomesticHgabOnlyCandidates);document.getElementById('oo2-m-high-card').textContent=fmt(s.highConfidenceUniqueHgabCandidates);document.getElementById('oo2-m-adjusted').textContent=fmt(s.conservativeAdjustedBaseline);document.getElementById('oo2-m-adjusted-card').textContent=fmt(s.conservativeAdjustedBaseline);document.getElementById('oo2-m-review').textContent=fmt(s.reviewRows);document.getElementById('oo2-range').textContent=`If every distinct review candidate also maps after manual scope checks, the count could fall to ${fmt(s.reviewInclusiveLowerBound)}. That is an outer sensitivity bound, not the reported result.`;const tbody=document.getElementById('oo2-rows');const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));tbody.innerHTML=D.records.map(r=>{const h=r.hgabCandidate;const cls=r.status==='Review candidate'?'review':r.status==='Unresolved'?'unresolved':'';const candidate=h?`${esc(h.projectName)}<div class="oo2-subtle">HB ${esc(h.sourcePage||'')} · ${esc(h.id)}</div>`:'No credible candidate';return `<tr data-status="${esc(r.status)}" data-search="${esc([r.projectTitle,h?.projectName,r.sourceRow,r.section].join(' ').toLowerCase())}"><td>${esc(r.sourceRow)} · ${esc(r.section)}</td><td>${esc(r.projectTitle)}<div class="oo2-subtle">${esc(r.fromExistingLine||'')}</div></td><td>${candidate}</td><td>${peso(r.toAmountPesos)}${r.changeAmountPesos!=null?`<div class=\"oo2-subtle\">Change from named prior line: ${peso(r.changeAmountPesos)}</div>`:''}</td><td>${h?peso(h.amountPesos):'—'}</td><td><span class="oo2-pill ${cls}">${esc(r.status)}</span><div class="oo2-subtle">${esc(r.rationale)}</div></td></tr>`}).join('');const apply=()=>{const q=document.getElementById('oo2-search').value.toLowerCase(),st=document.getElementById('oo2-status').value;for(const tr of tbody.rows)tr.hidden=!(tr.dataset.search.includes(q)&&(!st||tr.dataset.status===st))};document.getElementById('oo2-search').oninput=apply;document.getElementById('oo2-status').onchange=apply}).catch(e=>{document.getElementById('oo2-rows').innerHTML=`<tr><td colspan="6">OO2 comparison data unavailable: ${String(e.message)}</td></tr>`})})();
</script>
'''
base = base.replace('</body>', js+'</body>', 1)
base = re.sub(r'href=(["\'])dpwh-hgab\.html(#[^"\']*)?\1', lambda m:'href='+m[1]+'dpwh-OO2-hgab.html'+(m[2] or '')+m[1], base)
from uniform_report_menu import NAV
base = re.sub(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>', lambda _:NAV, base, flags=re.S)
(SITE/'dpwh-OO2-hgab.html').write_text(base)
(ANALYSIS/'dpwh-OO2-hgab.html').write_text(base)
print(json.dumps(summary, indent=2))
