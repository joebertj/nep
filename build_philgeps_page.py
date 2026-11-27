#!/usr/bin/env python3
"""Match published procurement titles to named FY2027 budget schedules."""
import csv
import hashlib
import json
import re
import subprocess
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
V2 = ODV / 'data/philgeps-v2'
PDF = 'https://budget-assets.bettergov.ph/hgab/2027/pdf/'
DATA = 'philgeps-data.json'
LIVE_SNAPSHOT = ROOT / 'data_sources/philgeps-fy2027-notices.json'

# Primary documents checked individually. The date is the issue date printed
# in the invitation. The scheduled opening is kept separate from proof it occurred.
VERIFIED_INVITATIONS = [{
    'contract': '27OF0046',
    'title': 'Construction of Multi-Purpose Building (Completion) at Sitio Pajo, Barangay Baesa, Quezon City, 14.66249, 121.01425',
    'office': 'DPWH Quezon City 1st District Engineering Office',
    'reference': '165446',
    'issued': '2026-11-25',
    'dateLabel': 'Notice created',
    'opening': '2026-12-16',
    'abc': 147_509_891.12,
    'status': 'Published',
    'basis': 'The project title and coordinates match the NEP, HGAB and SCR lines. The notice cites the FY2027 NEP as its funding basis and identifies the tender as Early Procurement Activity.',
    'url': 'https://philgeps.gov.ph/Indexes/viewLiveTenderDetails/165446',
}, {
    'contract': '27LD0053',
    'title': 'Concreting of Road Connecting Purok 1 and Purok 7, Barangay Asbang, Matanao, Davao del Sur',
    'office': 'DPWH Davao del Sur District Engineering Office',
    'reference': '124873',
    'issued': '2026-11-06',
    'opening': '2026-11-26',
    'abc': 59_400_000,
    'basis': 'Exact normalized title and Davao del Sur procuring office. The invitation identifies this as early procurement and makes award conditional on the FY2027 GAA taking effect.',
    'url': 'https://philgeps.gov.ph/portal_documents/bid_notice_documents/bid_notice_124873/bid_notice_document/1793883574_27LD0053_IB_final.pdf',
    'bulletin': 'https://philgeps.gov.ph/portal_documents/bid_notice_documents/bid_notice_124873/bid_notice_corrigendum_document/1794921548_bf9248ac_SB_No._2026_095_27LD0053.pdf',
}]
ORIENTAL_NOTICE = 'https://philgeps.gov.ph/portal_documents/bid_notice_documents/bid_notice_112820/bid_notice_document/1793005296_27LG0008___Invitation_to_Bid__Bidding_Documents_and_Plans.pdf'
ORIENTAL_CONTRACTS = [
    ('27LG0001', 'Bitaogan Br. (B01127MN) along Jct Manikling-Gov Generoso Rd', 71_893_000, 'bridge'),
    ('27LG0002', 'Camogna Br. 2 (B01691MN) along Tibanban-Lavigan Rd', 31_470_000, 'bridge'),
    ('27LG0003', 'La Union Br. (B01129MN) along Jct Manikling-Gov Generoso Rd', 49_698_000, 'bridge'),
    ('27LG0004', 'Luzon Br. (B01898MN) along Tibanban-Lavigan Rd', 66_585_000, 'bridge'),
    ('27LG0008', 'Sumlog River flood mitigation, Barangay Ilangay, Lupon · Sta. 1+680 to 2+430', 144_750_000, 'different_segment'),
    ('27LG0009', 'Construction of Road, Barangay Langka, Municipality of Lupon - Barangay Poblacion, Municipality of Banaybanay, Davao Oriental - (Sta. 0 + 500.000 - Sta. 2 + 882.000)', 67_550_000, 'title'),
]


def read(path):
    return json.loads(path.read_bytes())


def title_key(title):
    text = ''.join(c for c in unicodedata.normalize('NFD', title) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def budget_lines():
    rows = {}
    def add(stage, program, title, source_id, amount, url, office=''):
        title = ' '.join(str(title or '').split())
        if not title:
            return
        value = int(amount) if amount not in (None, '') else None
        key = (stage, program, title_key(title), value, url)
        rows.setdefault(key, {'stage': stage, 'program': program, 'title': title,
                              'id': source_id, 'amount': value, 'url': url, 'office': office or ''})

    def pdf(name, page):
        return PDF + name + (f'#page={page}' if page else '')

    for r in read(OUT / 'nep_dpwh_baseline.json')['data']['data']:
        add('NEP', 'DPWH', r.get('officialNepTitle') or r['projectName'], r['id'], r['amountPesos'],
            pdf('nep2027-vol-iib.pdf', r['sourcePage']), r['office'])

    with (OUT / 'hb_nep_comparison_3rd.csv').open(newline='', encoding='utf-8-sig') as stream:
        for r in csv.DictReader(stream):
            volume = 'ib' if re.search(r'\bVOL\s+I-B\b', r['sourceVolume'], re.I) else 'ic'
            add('HGAB', 'DPWH', r['projectName'], r['hgab_id'], r['amountPesos'],
                pdf(f'hb10858-3r-vol-{volume}.pdf', r['sourcePage']), r['office'])

    with (ROOT / 'data_sources/fmr_analyst/nep_fmr_projects_normalized.csv').open(newline='', encoding='utf-8-sig') as stream:
        for r in csv.DictReader(stream):
            add('NEP', 'FMR', r['title'], r['project_id'], r['amount_php'], pdf('nep2027-fmr.pdf', r['pdf_page']))

    annex = read(OUT / 'reviewed_annex_baselines.json')
    for stage, source in [('NEP', 'nep'), ('HGAB', 'house')]:
        for r in annex['hfep'][source]['items']:
            file = 'nep2027-hfep.pdf' if stage == 'NEP' else 'hb10858-3r-vol-ib.pdf'
            add(stage, 'HFEP', r['label'], r['id'], r['amounts_php'].get('total'), pdf(file, r['source']['pdf_page']))
    for r in annex['nia']['nep']['projects']:
        add('NEP', 'NIA', r['label'], r['id'], r['amount_php'], pdf('nep2027-nia.pdf', r['provenance']['page']))
    for r in annex['nia']['house']['nodes']:
        if r['kind'] == 'project':
            add('HGAB', 'NIA', r['label'], r['id'], r['printed_amount_php'], pdf('hb10858-3r-vol-ib.pdf', r['source']['pdf_page']))

    for r in read(STATIC / 'scr-data.json')['rows']:
        program = r['program'].upper()
        if r['status'] == 'nep_only':
            add('NEP', program, r['title'], r['id'], r['nep_php'], r['nep_pdf_url'], r['office'])
        if r['house_php'] not in ('', None):
            add('HGAB', program, r['house_title'], r['house_id'] or r['id'], r['house_php'], r['house_pdf_url'], r['office'])
        if r['senate_php'] and int(r['senate_php']) > 0:
            url = r['senate_pdf_url'] if r['senate_page'] else r['house_pdf_url']
            add('SCR', program, r['title'], r['id'], r['senate_php'], url, r['office'])
    return list(rows.values())


def sql_path(path):
    return "'" + str(path).replace("'", "''") + "'"


def match_archive(keys):
    """Scan the typed v2 title fields and retain one source row per title/reference pair."""
    parquet = V2 / 'philgeps-2000-2025-typed.parquet'
    with tempfile.TemporaryDirectory(prefix='philgeps-title-') as tmp:
        path = Path(tmp) / 'titles.json'
        path.write_text(json.dumps([{'key': key} for key in sorted(keys)]))
        query = f"""
            WITH hits AS (
                SELECT k.key, fields.title AS matched_title, fields.field,
                       p.bid_reference_no AS reference, p.notice_title AS title,
                       p.solicitation_no AS solicitation, p.procuring_entity_name AS office,
                       CAST(CAST(p.bid_published_date AS DATE) AS VARCHAR) AS published,
                       p.bid_notice_status AS notice_status, p.approved_budget AS abc,
                       p.award_reference_no AS award_reference, p.award_notice_status AS award_status,
                       CAST(CAST(p.award_date AS DATE) AS VARCHAR) AS award_date,
                       p._source_file_id AS source, p._source_sheet AS sheet, p._source_row_number AS source_row
                FROM read_parquet({sql_path(parquet)}) p,
                LATERAL (VALUES
                    ('Notice title', p.notice_title), ('Award title', p.award_title), ('Line item', p.item_name)
                ) fields(field, title)
                JOIN read_json_auto({sql_path(path)}) k
                  ON k.key = trim(regexp_replace(lower(strip_accents(fields.title)), '[^a-z0-9]+', ' ', 'g'))
                WHERE p.bid_reference_no IS NOT NULL
            )
            SELECT hits.*, s.file_name AS source_file FROM hits
            LEFT JOIN read_parquet({sql_path(V2 / 'sources.parquet')}) s ON hits.source = s.source_file_id
            QUALIFY row_number() OVER (
                PARTITION BY key, reference ORDER BY
                CASE field WHEN 'Notice title' THEN 1 WHEN 'Award title' THEN 2 ELSE 3 END,
                (award_reference IS NOT NULL) DESC, published DESC NULLS LAST, source, sheet, source_row
            )=1
            ORDER BY published DESC NULLS LAST, reference, key
        """
        result = subprocess.run(['duckdb', '-json', '-c', query], check=True, capture_output=True, text=True)
        return json.loads(result.stdout or '[]')


def build_data():
    lines = budget_lines()
    by_title = defaultdict(list)
    for r in lines:
        key = title_key(r['title'])
        if key:
            by_title[key].append(r)
    archive = match_archive(by_title)
    current = []
    for invitation in VERIFIED_INVITATIONS:
        budget = by_title[title_key(invitation['title'])]
        if not any(line['stage'] == 'NEP' for line in budget):
            raise ValueError(f"Missing FY2027 NEP title for {invitation['contract']}")
        current.append({**invitation, 'budget': budget})
    for contract, title, abc, basis in ORIENTAL_CONTRACTS:
        related = []
        if basis == 'different_segment':
            budget = []
            related = [line for line in lines if line['stage'] == 'NEP'
                       and 'sumlog river barangay ilangay' in title_key(line['title'])]
            if len(related) != 1:
                raise ValueError(f'Unresolved comparison source for {contract}')
            evidence = ('The nearby NEP line lists Sta. 0+000 to 0+750. The invitation lists '
                        'Sta. 1+680 to 2+430 and cites the NEP with errata or corrections. '
                        'The ranges do not overlap. Linking funding to this contract requires the corrected schedule.')
        else:
            budget = by_title[title_key(title)]
            if not any(line['stage'] == 'NEP' and 'Davao Oriental 2nd' in line['office'] for line in budget):
                raise ValueError(f'Missing FY2027 NEP title or office for {contract}')
            evidence = ('The bridge ID, route and NEP office agree. The NEP lists the work under permanent bridge widening.'
                        if basis == 'bridge' else 'Exact normalized project title including the same road limits and NEP office.')
        current.append({'contract': contract, 'title': title, 'office': 'DPWH Davao Oriental 2nd District Engineering Office',
                        'reference': '112820', 'issued': '2026-10-26', 'opening': '2026-11-24',
                        'abc': abc, 'url': ORIENTAL_NOTICE, 'basis': evidence, 'budget': budget, 'related': related})
    crawl = read(LIVE_SNAPSHOT) if LIVE_SNAPSHOT.exists() else {'notices': []}
    by_notice = {(row['reference'], row['contract']): row for row in current}
    for notice in crawl['notices']:
        key = notice['matchKey']
        budget = by_title.get(key, [])
        if key and not budget:
            raise ValueError(f"Budget title no longer matches PhilGEPS notice {notice['reference']}")
        identity = notice['reference'], notice['contract']
        if identity not in by_notice:
            by_notice[identity] = {**notice, 'budget': budget}
    current = sorted(by_notice.values(), key=lambda row: (row['issued'], row['reference'], row['contract']), reverse=True)
    from philgeps_review_flags import attach_flags
    attach_flags(current, read(STATIC / 'scr-data.json')['rows'], read(OUT / 'flags.json')['projects'], title_key)
    matched = {row['key']: by_title[row['key']] for row in archive}
    manifest = read(V2 / 'manifest.json')['facts']
    return {
        'coverage': {'budgetLines': len(lines), 'byStage': dict(Counter(r['stage'] for r in lines)),
                     'titleKeys': len(by_title), 'archiveRows': manifest['rows'],
                     'archiveThrough': manifest['bid_published'][1]},
        'archive': archive, 'budgetMatches': matched, 'invitations': current,
        'crawl': {key: value for key, value in crawl.items() if key != 'notices'},
    }


if __name__ == '__main__':
    data = build_data()
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    from render_philgeps_page import render
    html = render(data, DATA + '?v=' + hashlib.sha256(serialized.encode()).hexdigest()[:12])
    for folder in (OUT, STATIC):
        (folder / DATA).write_text(serialized, encoding='utf-8')
        (folder / 'philgeps.html').write_text(html, encoding='utf-8')
    print(data['coverage'], len(data['archive']), 'archive title/reference pairs')
