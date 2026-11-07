#!/usr/bin/env python3
"""Quick read-only title scan of Senate supporting PDFs against HGAB-only project rows."""
from __future__ import annotations
import argparse, csv, json, re, unicodedata
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = Path('/Volumes/T5 EVO/bettergov-research/nep/data_sources/OneDrive_2026-11-05/Supporting Documents (IO)')
MAPPING = ROOT / 'analysis_output/hb_nep_comparison_3rd_mapping.json'
OUT_JSON = ROOT / 'analysis_output/senate_pow_hgab_only_title_scan.json'
OUT_CSV = ROOT / 'analysis_output/senate_pow_hgab_only_title_scan.csv'
GENERIC_TITLE_WORDS = set('construction rehabilitation improvement widening reconstruction completion road roads bridge bridges multi purpose building barangay city province municipality access along of the and at in to for near project new concreting preventive maintenance repair upgrading existing drainage development works site station sta covered court multipurpose'.split())


def key(s):
    s = unicodedata.normalize('NFKC', str(s or '')).casefold()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def extract_project_title(text, by_title):
    lines = [re.sub(r'\s+', ' ', x).strip(' :\t') for x in text.splitlines()]
    # Some POW templates store text boxes in visual rather than reading order,
    # so the line after "Project Name" can be a column header. First look for
    # a complete ledger title anywhere in the first-page text.
    page_key = key(text)
    embedded = [title for title_key, rows in by_title.items() if title_key in page_key
                for title in [rows[0]['projectName']]]
    if len(embedded) == 1:
        return embedded[0]
    if len(embedded) > 1:
        return None
    labels = ('project name', 'name of project')
    for i, line in enumerate(lines):
        normalized = re.sub(r'[^a-z ]', '', line.casefold()).strip()
        if normalized in labels:
            for candidate in lines[i+1:i+5]:
                if candidate and candidate.casefold() not in {'project location', 'address', 'implementing office'}:
                    return candidate
        for label in labels:
            m = re.match(rf'^{re.escape(label)}\s*[:\-]\s*(.+)$', line, re.I)
            if m:
                return m.group(1).strip()
    return None


def relaxed_match_extracted_title(record, titles_by_id, title_index, title_frequency):
    """Conservative fuzzy match for the project-title line already extracted."""
    if record.get('matchStatus') != 'no_exact_title_match' or not record.get('extractedTitle'):
        return None
    source_tokens = set(key(record['extractedTitle']).split())
    if len(source_tokens) < 4:
        return None
    anchors = sorted((t for t in source_tokens - GENERIC_TITLE_WORDS
                      if title_frequency.get(t, 10**9) <= 400),
                     key=lambda t: title_frequency.get(t, 10**9))[:5]
    candidate_ids = set().union(*(title_index[t] for t in anchors)) if anchors else set()
    scored = []
    source_numbers = {t for t in source_tokens if any(c.isdigit() for c in t)}
    for hgab_id in candidate_ids:
        title, title_tokens = titles_by_id[hgab_id]
        common = len(source_tokens & title_tokens)
        if not common or not ((source_tokens - GENERIC_TITLE_WORDS) & (title_tokens - GENERIC_TITLE_WORDS)):
            continue
        recall = common / len(title_tokens)
        precision = common / len(source_tokens)
        dice = 2 * common / (len(source_tokens) + len(title_tokens))
        title_numbers = {t for t in title_tokens if any(c.isdigit() for c in t)}
        if source_numbers and title_numbers and source_numbers != title_numbers:
            continue
        if recall >= 0.72 and precision >= 0.78 and dice >= 0.74:
            scored.append((dice, recall, precision, hgab_id, title))
    scored.sort(reverse=True)
    if not scored:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        record['matchStatus'] = 'ambiguous_relaxed_title_match'
        record['matchScore'] = round(scored[0][0], 4)
        return 'ambiguous'
    best = scored[0]
    record.update({'matchStatus': 'relaxed_title_match', 'matchScore': round(best[0], 4),
                   'titleTokenCoverage': round(best[1], 4), 'matchCount': 1,
                   'matchedHgabIds': [best[3]], 'matchedHgabTitles': [best[4]]})
    return 'matched'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    ap.add_argument('--kind', choices=('pow', 'bp202'), default='pow', help='Senate supporting-document type to scan')
    ap.add_argument('--output-json', type=Path)
    ap.add_argument('--output-csv', type=Path)
    ap.add_argument('--reuse-existing', action='store_true', help='reuse the existing PDF scan records and only redo relaxed matching')
    args = ap.parse_args()
    if args.output_json is None:
        args.output_json = OUT_JSON if args.kind == 'pow' else ROOT / f'analysis_output/senate_{args.kind}_hgab_only_title_scan.json'
    if args.output_csv is None:
        args.output_csv = OUT_CSV if args.kind == 'pow' else ROOT / f'analysis_output/senate_{args.kind}_hgab_only_title_scan.csv'
    if not args.source.is_dir():
        raise SystemExit(f'Source directory not found: {args.source}')
    if not args.reuse_existing:
        try:
            import pymupdf
        except ImportError as e:
            raise SystemExit('PyMuPDF is required; use .venv-documents/bin/python') from e

    mapping = json.loads(MAPPING.read_text(encoding='utf-8'))
    hgab_only = [r for r in mapping.get('hgabWithoutSelectedCounterpart', [])
                 if r.get('allocationKind') == 'project' and r.get('projectName')]
    by_title = defaultdict(list)
    for row in hgab_only:
        by_title[key(row['projectName'])].append(row)
    titles_by_id = {}
    title_index = defaultdict(set)
    title_frequency = Counter()
    for row in hgab_only:
        hgab_id = row['id']; title = row['projectName']; tokens = set(key(title).split())
        titles_by_id[hgab_id] = (title, tokens)
        title_frequency.update(tokens)
        for token in tokens:
            title_index[token].add(hgab_id)

    if args.reuse_existing:
        previous = json.loads(args.output_json.read_text(encoding='utf-8'))
        records = previous['records']
        errors = previous.get('powFilesWithScanErrors', 0)
        no_text = previous.get('powFilesWithNoNativeFirstPageText', 0)
        no_title = previous.get('powFilesWithoutExtractedProjectTitle', 0)
    else:
        files = sorted(p for p in args.source.rglob('*.pdf')
                       if p.is_file() and not p.name.startswith('_') and not p.name.startswith('._')
                       and not any(part.startswith('_') for part in p.relative_to(args.source).parts)
                       and ((args.kind == 'pow' and 'pow' in p.stem.casefold() and 'dupa' not in p.stem.casefold())
                            or (args.kind == 'bp202' and re.search(r'(?i)(?:^|[^a-z0-9])bp\s*202(?:[^0-9]|$)', p.stem))))
        records = []; errors = no_text = no_title = 0
        for path in files:
            try:
                with pymupdf.open(path) as doc:
                    text = doc[0].get_text() if len(doc) else ''
                if not text.strip(): no_text += 1
                title = extract_project_title(text, by_title)
                if not title: no_title += 1
                matches = by_title.get(key(title), []) if title else []
                rel = str(path.relative_to(args.source))
                records.append({'file': rel,
                    'projectCode': re.search(r'2027DPWH-HGAB-\d{5}', path.as_posix()).group(0) if re.search(r'2027DPWH-HGAB-\d{5}', path.as_posix()) else None,
                    'extractedTitle': title, 'matchCount': len(matches),
                    'matchStatus': 'exact_title_match' if len(matches) == 1 else 'ambiguous_exact_title_match' if matches else 'no_exact_title_match',
                    'matchedHgabIds': [r.get('id') for r in matches], 'matchedHgabTitles': [r.get('projectName') for r in matches]})
            except Exception as e:
                errors += 1
                records.append({'file': str(path.relative_to(args.source)), 'projectCode': None,
                                'extractedTitle': None, 'matchCount': 0, 'matchStatus': 'scan_error',
                                'matchedHgabIds': [], 'matchedHgabTitles': [], 'error': f'{type(e).__name__}: {e}'})

    for record in records:
        relaxed_match_extracted_title(record, titles_by_id, title_index, title_frequency)

    exact = [r for r in records if r['matchStatus'] == 'exact_title_match']
    relaxed_matches = [r for r in records if r['matchStatus'] == 'relaxed_title_match']
    ambiguous = [r for r in records if r['matchStatus'] in {'ambiguous_exact_title_match','ambiguous_relaxed_title_match'}]
    matched_project_ids = {hid for r in records if r['matchStatus'] in {'exact_title_match','relaxed_title_match'}
                           for hid in r['matchedHgabIds']}
    report = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'documentType': 'Program of Works (POW)' if args.kind == 'pow' else 'BP 202',
        'method': f"Read-only extraction of first-page native PDF text from Senate {args.kind.upper()} PDFs. Exact normalized title occurrence is counted separately. Relaxed candidate matching on extracted project-title text requires token recall >= 0.72, precision >= 0.78 and Dice overlap >= 0.74; it also requires a shared specific token, matching numeric tokens when present, and a 0.05 score margin over the runner-up. This is a rough estimate; it is not manually verified. Matching is against HGAB project rows without a selected NEP counterpart.",
        'sourceDirectory': str(args.source),
        'senateDocumentsScanned': len(records),
        'exactlyMatchedDocuments': len(exact),
        'relaxedMatchedDocuments': len(relaxed_matches),
        'combinedMatchedDocuments': len(exact) + len(relaxed_matches),
        'ambiguousDocuments': len(ambiguous),
        'documentsWithNoExactTitleMatch': sum(r['matchStatus'] != 'exact_title_match' for r in records),
        'documentsWithNoAcceptedExactOrRelaxedMatch': sum(r['matchStatus'] not in {'exact_title_match', 'relaxed_title_match'} for r in records),
        'documentsWithScanErrors': errors,
        'documentsWithNoNativeFirstPageText': no_text,
        'documentsWithoutExtractedProjectTitle': no_title,
        'hgabOnlyProjectRows': len(hgab_only),
        'hgabOnlyProjectRowsWithAtLeastOneExactOrRelaxedDocumentMatch': len(matched_project_ids),
        'hgabOnlyProjectCoveragePct': round(100 * len(matched_project_ids) / len(hgab_only), 2) if hgab_only else 0,
        'matchedDocumentSharePct': round(100 * (len(exact) + len(relaxed_matches)) / len(records), 2) if records else 0,
        'records': records,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with args.output_csv.open('w', encoding='utf-8-sig', newline='') as f:
        fields = ['file', 'projectCode', 'extractedTitle', 'matchStatus', 'matchScore', 'titleTokenCoverage', 'matchedHgabIds', 'matchedHgabTitles', 'error']
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); writer.writeheader()
        for r in records:
            writer.writerow({**r, 'matchedHgabIds': ' | '.join(r.get('matchedHgabIds', [])),
                             'matchedHgabTitles': ' | '.join(r.get('matchedHgabTitles', []))})
    print(json.dumps({k:v for k,v in report.items() if k != 'records'}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
