#!/usr/bin/env python3
"""Separate printed FAP allocations from the domestic NEP/HGAB shortlist."""
import csv
import html
import json
import re
from collections import Counter
from pathlib import Path
from hgab_matching import is_fap, UNMATCHED

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def money(value):
    return f'₱{int(value):,}'


def read_rows(edition):
    suffix = '_3rd' if edition == '3rd' else ''
    with (OUT / f'hb_nep_comparison{suffix}.csv').open(newline='') as stream:
        return list(csv.DictReader(stream))


def summarize(rows):
    fap = [r for r in rows if is_fap(r)]
    domestic = [r for r in rows if not is_fap(r)]
    removed = [r for r in fap if r['comparison'] == UNMATCHED]
    paired = [r for r in fap if r.get('paired_one_to_one') == 'True']
    return {'allScheduleRows': len(rows), 'fapRows': len(fap),
            'fapAllocationPesos': sum(int(r['amountPesos']) for r in fap),
            'domesticRows': len(domestic), 'domesticCounts': dict(Counter(r['comparison'] for r in domestic)),
            'excludedFromUnmatchedShortlistRows': len(removed),
            'excludedFromUnmatchedShortlistPesos': sum(int(r['amountPesos']) for r in removed),
            'pairedFapRows': len(paired), 'unpairedFapRows': len(fap) - len(paired),
            'pairedNepAllocationPesos': sum(int(r['closest_nep_amount_pesos']) for r in paired),
            'pairedHgabAllocationPesos': sum(int(r['amountPesos']) for r in paired)}


def review_section(rows, summary):
    paired = [r for r in rows if r.get('paired_one_to_one') == 'True']
    # Compare only the same selected occurrences; an unpaired line has no zero baseline.
    totals = [summary['pairedNepAllocationPesos'], summary['pairedHgabAllocationPesos']]
    scale = max(totals + [1])
    bars = ''.join(f'<text x="0" y="{30+i*65}">{label}</text><rect x="180" y="{12+i*65}" width="{value/scale*480:.2f}" height="26" fill="{color}"/><text x="180" y="{56+i*65}">{money(value)}</text>'
                   for i, (label, value, color) in enumerate(zip(['Paired NEP FAP', 'Paired HGAB FAP'], totals, ['#637381', '#087e78'])))
    table = []
    for r in rows:
        selected = r.get('paired_one_to_one') == 'True'
        nep = int(r['closest_nep_amount_pesos']) if selected else None
        value = int(r['amountPesos'])
        title = html.escape(r['projectName'])
        source = html.escape(r['sourceVolume']) + ' · PDF p. ' + html.escape(r['sourcePage'])
        cells = [title, html.escape(r['comparison']), money(nep) if nep is not None else 'Unpaired', money(value),
                 money(value-nep) if nep is not None else 'Not calculated', source]
        table.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cells) + '</tr>')
    # Embed CSV as a JSON string, rather than interpolate titles into JavaScript or HTML handlers.
    export_rows = [['Project', 'Match status', 'NEP pesos (selected counterpart only)', 'HGAB pesos', 'Delta pesos', 'PDF', 'PDF page']]
    for r in rows:
        selected = r.get('paired_one_to_one') == 'True'
        nep = int(r['closest_nep_amount_pesos']) if selected else ''
        export_rows.append([r['projectName'], r['comparison'], nep, int(r['amountPesos']), int(r['amountPesos'])-nep if selected else '', r['sourceVolume'], r['sourcePage']])
    import io
    stream = io.StringIO(); csv.writer(stream).writerows(export_rows)
    payload = json.dumps(stream.getvalue(), ensure_ascii=False).replace('<', '\\u003c')
    return f'''<section class="card section" id="foreign-assisted-review"><h2>Foreign assisted projects · separate NEP → HGAB review</h2>
<p class="sub">The printed FAP schedule contains <strong>{len(rows)} lines, {money(summary['fapAllocationPesos'])}</strong>. All are excluded from the domestic additions shortlist. This excludes {summary['excludedFromUnmatchedShortlistRows']} unmatched FAP lines carrying {money(summary['excludedFromUnmatchedShortlistPesos'])}; it does not establish that those projects are absent from NEP. Loan identity, counterpart funding and project scope need separate verification.</p>
<p class="sub">{len(paired)} selected counterparts are compared below. Unpaired lines have no assumed zero NEP baseline. Fuzzy counterparts remain provisional. PDF page numbers use the parser’s physical-page convention.</p>
<svg viewBox="0 0 720 145" role="img" aria-label="NEP and HGAB allocations for paired foreign assisted lines" style="display:block;width:100%;max-height:190px;font:15px sans-serif">{bars}</svg>
<button type="button" class="export-btn" id="fapCsv">Export FAP review CSV</button>
<div class="tablewrap"><table><thead><tr><th>Foreign assisted project</th><th>NEP match</th><th>NEP allocation</th><th>HGAB allocation</th><th>Change</th><th>Source</th></tr></thead><tbody>{''.join(table)}</tbody></table></div></section>
<script id="fap-review-script">document.getElementById('fapCsv').onclick=()=>{{const blob=new Blob(['\\ufeff',{payload}],{{type:'text/csv;charset=utf-8'}}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='dpwh_fap_nep_hgab_3rd.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}};</script>'''


def refresh():
    data_path = STATIC / 'dpwh-data.json'
    data = json.loads(data_path.read_text())
    audit = {}
    for edition, data_key, summary_key in [('2nd', 'hbInsertions2nd', 'hbInsertions2ndSummary'), ('3rd', 'hbInsertions', 'hbInsertions3rdSummary')]:
        rows = read_rows(edition); fap = [r for r in rows if is_fap(r)]
        summary = summarize(rows); audit[edition] = {'summary': summary, 'rows': fap}
        # Rebuild the shortlist from the comparison rather than subtracting counts on every rerun.
        allowed = {(r['projectName'], r['sourceVolume'], str(r['sourcePage'])) for r in rows if not is_fap(r) and r['comparison'] == UNMATCHED}
        data[data_key] = [r for r in data[data_key] if (r['projectName'], r['sourceVolume'], str(r['sourcePage'])) in allowed]
        screen = data[summary_key]
        screen['allScheduleCounts'] = dict(Counter(r['comparison'] for r in rows))
        screen['counts'] = summary['domesticCounts']
        screen['screenScope'] = 'Domestic schedule only; printed foreign assisted allocations reviewed separately.'
        screen['domesticScreenRecords'] = summary['domesticRows']
        screen['fapReview'] = summary
        data['fapReview' + edition] = fap
    data_path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
    audit['method'] = 'FAP classification is taken from the printed PAP or parser allocationKind. All full-schedule comparison records and totals are retained. Only the domestic unmatched shortlist excludes FAP. NEP amounts are selected one-to-one counterparts, not nearest-title suggestions.'
    (OUT / 'dpwh_fap_nep_hgab_review.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2)+'\n')
    fap = audit['3rd']['rows']; summary = audit['3rd']['summary']
    with (OUT / 'dpwh_fap_nep_hgab_review.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fap[0]) if fap else [])
        writer.writeheader(); writer.writerows(fap)
    count = len(data['hbInsertions']); cost = sum(int(r['amountPesos']) for r in data['hbInsertions'])
    section = review_section(fap, summary)
    for name in ['dpwh.html', 'dpwh-hgab.html']:
        path = STATIC / name; page = path.read_text()
        page = re.sub(r'<section class="card section" id="foreign-assisted-review">.*?</section>', '', page, flags=re.S)
        page = re.sub(r'<script id="fap-review-script">.*?</script>', '', page, flags=re.S)
        intro = (f'The domestic 3rd-reading title screen leaves <strong>{count:,} HGAB lines</strong> without a plausible NEP counterpart, carrying <strong>₱{cost/1e9:,.2f}B</strong>. Foreign assisted projects are excluded and reviewed separately below. Unmatched titles are review leads, not confirmed additions.')
        page = re.sub(r'(<section id="hgab-insertion".*?<h2>).*?(</h2>\s*<p class="sub">).*?(</p>)', lambda m:m[1]+'Potential insertions · domestic HGAB-only line items'+m[2]+intro+m[3], page, count=1, flags=re.S)
        page = page.replace('Counts across all 3rd-reading DPWH records;', 'Counts across domestic 3rd-reading DPWH records;')
        page = page.replace('DPWH line items by NEP title-screen result', 'Domestic DPWH line items by NEP title-screen result')
        # Keep this text replacement idempotent on repeat builds.
        page = page.replace('Domestic Domestic DPWH', 'Domestic DPWH')
        if name == 'dpwh-hgab.html':
            hero = re.search(r'<section class="impact-teaser".*?</section>', page, re.S)
            if hero:
                block = hero[0]
                block = re.sub(r'(<div class="impact-teaser-headline">).*?(</div>)', lambda m:m[1]+f'{count:,}'+m[2], block, count=1, flags=re.S)
                block = re.sub(r'(<div class="impact-teaser-stat"><strong>).*?(</strong>)', lambda m:m[1]+f'₱{cost/1e9:,.2f}B'+m[2], block, count=1, flags=re.S)
                block = re.sub(r'(<div class="impact-teaser-title">).*?(</div>)', lambda m:m[1]+'Potential domestic insertions · HGAB-only line items'+m[2], block, count=1, flags=re.S)
                block = re.sub(r'(<p class="impact-teaser-copy">).*?(</p>)', lambda m:m[1]+'Foreign assisted projects are reviewed separately. Exact and plausible NEP title counterparts are screened out.'+m[2], block, count=1, flags=re.S)
                page = page[:hero.start()] + block + page[hero.end():]
            # Archive count and cost also use domestic scope.
            old = data['hbInsertions2nd']; old_cost=sum(int(r['amountPesos']) for r in old)
            page = re.sub(r'The 2nd-reading edition has .*?confirmed additions\.', f'The domestic 2nd-reading shortlist has {len(old):,} unmatched records carrying ₱{old_cost/1e9:,.2f}B. FAP allocations are excluded; these are review leads, not confirmed additions.', page)
        if '</main>' not in page: raise ValueError(f'Cannot locate main container in {name}')
        page = page.replace('</main>', section+'</main>', 1)
        path.write_text(page)
    print(json.dumps({'domesticShortlistRows':count,'domesticShortlistPesos':cost,'fap':summary}, indent=2))
    from build_dpwh_subtractions import refresh as refresh_subtractions
    refresh_subtractions()
    from build_dpwh_hgab_headlines import refresh as refresh_headlines
    refresh_headlines()


if __name__ == '__main__':
    refresh()
