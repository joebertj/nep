#!/usr/bin/env python3
"""Parse downloaded Cloudflare-indexed Senate HGAB PDFs without walking T5."""
from __future__ import annotations

import argparse
import csv
import fcntl
import json
import re
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from storage.external_storage import BASE, guard
from scan_hgab_only_pow_titles import relaxed_match_extracted_title

ROOT = Path(__file__).resolve().parent
ATTACHMENTS = BASE / 'nep/data_sources/dpwh_project_documents/attachments'
ALL_DOWNLOADS = ATTACHMENTS / 'cloudflare-file-downloads.jsonl'
POW_DOWNLOADS = ATTACHMENTS / 'downloads-hgab.jsonl'
MAPPING = ROOT / 'analysis_output/hb_nep_comparison_3rd_mapping.json'
OUT = ROOT / 'analysis_output/senate_supporting_documents_hgab_only_scan.json'
STATUS = ROOT / 'analysis_output/senate_supporting_document_scan_status.json'
CSV_OUT = ROOT / 'analysis_output/senate_supporting_documents_hgab_only_scan.csv'
CODE = re.compile(r'(?:2027[-_\s]*)?DPWH[-_\s]*HGAB[-_\s-]*(\d{5})', re.I)
SIGNATORY_PARSER_VERSION = 2
EXTENSIONS = {'.pdf'}
GENERIC = set('construction rehabilitation improvement widening reconstruction completion road roads bridge bridges multi purpose building barangay city province municipality access along of the and at in to for near project new concreting preventive maintenance repair upgrading existing drainage development works site station sta covered court multipurpose'.split())
WORKER_TITLE_INDEX = {}
WORKER_TITLES_BY_ID = {}
WORKER_TITLE_FREQUENCY = {}
WORKER_BY_TITLE = {}


def key(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9]+', ' ', value)).strip()


def classify(path: Path):
    name = path.stem.upper()
    if 'POW' in name or 'PROGRAM OF WORK' in name:
        return 'POW'
    if re.search(r'(?:^|[^A-Z0-9])BP\s*202(?:[^0-9]|$)', name):
        return 'BP 202'
    if re.search(r'GEOTAG|GEO.?TAG|PHOTO|PICTURE', name):
        return 'Geotagged photos'
    if 'IMPLEMENTABILITY' in name:
        return 'Certificate of Implementability'
    if re.search(r'(?:^|[^A-Z0-9])(?:RDC|PDC|LDC|CDC|DC)(?:[^A-Z0-9]|$)|DEVELOPMENT.?COUNCIL', name):
        return 'Development Council'
    return 'Other'


def extract_title(text, title_index, titles_by_id, title_frequency):
    lines = [re.sub(r'\s+', ' ', line).strip(' :\t') for line in text.splitlines()]
    for i, line in enumerate(lines):
        normalized = re.sub(r'[^a-z ]', '', line.casefold()).strip()
        if normalized in {'project name', 'name of project'}:
            for candidate in lines[i + 1:i + 5]:
                if candidate and candidate.casefold() not in {'project location', 'address', 'implementing office'}:
                    return candidate
        for label in ('project name', 'name of project'):
            match = re.match(rf'^{re.escape(label)}\s*[:\-]\s*(.+)$', line, re.I)
            if match:
                return match.group(1).strip()
    page_key = key(text)
    tokens = set(page_key.split()) - GENERIC
    anchors = sorted((token for token in tokens if title_frequency.get(token, 10**9) <= 400),
                     key=lambda token: title_frequency.get(token, 10**9))[:8]
    candidate_ids = set().union(*(title_index[token] for token in anchors)) if anchors else set()
    matches = [(hid, title) for hid in candidate_ids
               for title, _ in [titles_by_id[hid]] if key(title) in page_key]
    return matches[0][1] if len(matches) == 1 else None


def initialize_worker(title_index, titles_by_id, title_frequency, by_title):
    global WORKER_TITLE_INDEX, WORKER_TITLES_BY_ID, WORKER_TITLE_FREQUENCY, WORKER_BY_TITLE
    WORKER_TITLE_INDEX = title_index
    WORKER_TITLES_BY_ID = titles_by_id
    WORKER_TITLE_FREQUENCY = title_frequency
    WORKER_BY_TITLE = by_title


def scan_one(task):
    import pymupdf
    result = {k: task.get(k) for k in ('file', 'documentType', 'sourceSize', 'sourceMtimeNs', 'sourceSha256', 'projectCode')}
    if task.get('roleKind'):
        result['signatoryParserVersion'] = SIGNATORY_PARSER_VERSION
    result.update({'extractedTitle': None, 'matchStatus': 'no_exact_title_match',
                   'matchedHgabIds': [], 'matchedHgabTitles': [], 'nativeText': False,
                   'pageCount': None, 'firstPageImageCount': 0, 'signatories': [], 'signatoryStatus': None})
    try:
        source = Path(task['absolutePath'])
        with pymupdf.open(source) as document:
            result['pageCount'] = len(document)
            text = document[0].get_text() if len(document) else ''
            result['firstPageImageCount'] = len(document[0].get_images(full=True)) if len(document) else 0
        result['nativeText'] = bool(text.strip())
        result['extractedTitle'] = extract_title(text, WORKER_TITLE_INDEX, WORKER_TITLES_BY_ID, WORKER_TITLE_FREQUENCY) if text.strip() else None
        title = result['extractedTitle']
        if title:
            matches = WORKER_BY_TITLE.get(key(title), [])
            if len(matches) == 1:
                result.update({'matchStatus': 'exact_title_match', 'matchedHgabIds': [matches[0]['id']], 'matchedHgabTitles': [matches[0]['projectName']]})
            elif len(matches) > 1:
                result.update({'matchStatus': 'ambiguous_exact_title_match', 'matchedHgabIds': [row['id'] for row in matches], 'matchedHgabTitles': [row['projectName'] for row in matches]})
            else:
                from scan_hgab_only_pow_titles import relaxed_match_extracted_title
                relaxed_match_extracted_title(result, WORKER_TITLES_BY_ID, WORKER_TITLE_INDEX, WORKER_TITLE_FREQUENCY)
        role_kind = task.get('roleKind')
        if role_kind:
            from project_documents.signatories import extract
            signed = extract(source, role_kind, save_pages=False)
            result['signatories'] = signed.get('people', [])
            result['signatoryStatus'] = signed.get('status')
            result['unresolvedSignatoryPages'] = len(signed.get('unresolved', []))
    except Exception as exc:
        result['matchStatus'] = 'scan_error'
        result['scanError'] = True
        result['error'] = f'{type(exc).__name__}: {str(exc)[:300]}'
    return result


def path_record(path, source):
    rel = path.relative_to(source).as_posix()
    code = None
    for candidate in (path.name, *(parent.name for parent in path.parents)):
        match = CODE.search(candidate)
        if match:
            code = f'2027DPWH-HGAB-{match.group(1)}'
            break
    stat = path.stat()
    category = classify(path)
    role_kind = None
    if category == 'POW':
        role_kind = 'pow'
    elif category == 'Development Council':
        upper = path.stem.upper()
        role_kind = next((kind for kind in ('rdc', 'pdc', 'ldc', 'cdc')
                          if re.search(rf'(?:^|[^A-Z0-9]){kind.upper()}(?:[^A-Z0-9]|$)', upper)), 'supporting')
    return {'file': rel, 'absolutePath': str(path), 'projectCode': code,
            'documentType': category, 'sourceSize': stat.st_size,
            'sourceMtimeNs': stat.st_mtime_ns, 'roleKind': role_kind}


def downloaded_pdf_tasks():
    """Return exact journaled PDF paths; do not walk T5 source folders."""
    latest = {}
    for journal in (ALL_DOWNLOADS, POW_DOWNLOADS):
        if not journal.is_file():
            continue
        with journal.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('status') != 'downloaded' or not row.get('path') or not row.get('sourcePath'):
                    continue
                if Path(row['sourcePath']).suffix.casefold() != '.pdf':
                    continue
                key = (row['sourcePath'], row.get('manifestSha256') or row.get('sha256'))
                latest[key] = row
    tasks = []
    for row in latest.values():
        rel = row['sourcePath']
        source = (ATTACHMENTS / row['path']).resolve()
        try:
            source.relative_to(ATTACHMENTS.resolve())
        except ValueError:
            continue
        if not source.is_file():
            continue
        path = Path(rel)
        category = row.get('documentType') or classify(path)
        role_kind = None
        if category == 'POW':
            role_kind = 'pow'
        elif category == 'Development Council':
            upper = path.stem.upper()
            role_kind = next((kind for kind in ('rdc', 'pdc', 'ldc', 'cdc')
                              if re.search(rf'(?:^|[^A-Z0-9]){kind.upper()}(?:[^A-Z0-9]|$)', upper)), 'supporting')
        stat = source.stat()
        tasks.append({
            'file': rel, 'absolutePath': str(source), 'projectCode': row.get('projectCode'),
            'documentType': category, 'sourceSize': stat.st_size,
            'sourceMtimeNs': stat.st_mtime_ns, 'sourceSha256': row.get('sha256'),
            'roleKind': role_kind,
        })
    return tasks


def cloudflare_inventory():
    from download_dpwh_nep_attachments import manifest_rows
    rows, _ = manifest_rows()
    files_by_code = defaultdict(list)
    types_by_code = defaultdict(Counter)
    by_type = Counter()
    for row in rows:
        kind = row['documentType']
        by_type[kind] += 1
        if row.get('projectCode'):
            files_by_code[row['projectCode']].append(row['sourcePath'])
            types_by_code[row['projectCode']][kind] += 1
    return {
        'available': True, 'source': 'Cloudflare-file-links.jsonl; no live T5 inventory scan',
        'files': len(rows), 'projectCodes': len(files_by_code), 'byType': dict(by_type),
        'filesByCode': {key: len(set(value)) for key, value in files_by_code.items()},
        'typesByCode': {key: dict(value) for key, value in types_by_code.items()},
    }


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temp.replace(path)


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def saved_title_scans():
    records = []
    for filename, doc_type in (('senate_pow_hgab_only_title_scan.json', 'POW'),
                               ('senate_bp202_hgab_only_title_scan.json', 'BP 202')):
        report = read_json(ROOT / 'analysis_output' / filename, {})
        for item in report.get('records', []):
            if item.get('matchStatus') not in {'exact_title_match', 'relaxed_title_match', 'ambiguous_exact_title_match', 'ambiguous_relaxed_title_match'}:
                continue
            records.append({**item, 'documentType': doc_type, 'pageCount': None,
                            'firstPageImageCount': 0, 'nativeText': bool(item.get('extractedTitle')),
                            'signatories': [], 'signatoryStatus': None})
    return records


def consolidate(hgab_only, records, inventory, cloudflare=None):
    by_id = {row['id']: row for row in hgab_only}
    # A five-digit T5 HGAB file code groups the project's attachments. Propagate
    # a title match only when a POW/BP/other sibling file uniquely resolves that
    # code to one House row; conflicting code-to-row evidence is left unassigned.
    ids_by_code = defaultdict(set)
    evidence_by_code = defaultdict(list)
    for record in records:
        if record.get('matchStatus') in {'exact_title_match', 'relaxed_title_match'} and record.get('projectCode'):
            ids = set(record.get('matchedHgabIds', [])) & by_id.keys()
            if len(ids) == 1:
                ids_by_code[record['projectCode']].update(ids)
                evidence_by_code[record['projectCode']].append(record.get('file'))
            elif len(ids) > 1:
                ids_by_code[record['projectCode']].update(ids)
    for record in records:
        code = record.get('projectCode')
        ids = ids_by_code.get(code, set()) if code else set()
        if len(ids) == 1 and record.get('matchStatus') not in {'exact_title_match', 'relaxed_title_match'}:
            hid = next(iter(ids))
            record.update({'matchStatus': 'same_code_sibling_file_match', 'matchedHgabIds': [hid],
                           'matchedHgabTitles': [by_id[hid]['projectName']],
                           'matchedVia': 'same HGAB file code as a uniquely title-matched sibling',
                           'siblingTitleEvidenceFiles': sorted(set(evidence_by_code.get(code, [])))})
    matched = defaultdict(list)
    by_type = defaultdict(lambda: {'projectIds': set(), 'files': 0, 'exactFiles': 0, 'relaxedFiles': 0})
    signatory_types = Counter()
    signatory_types_by_document = defaultdict(Counter)
    for record in records:
        if record.get('matchStatus') not in {'exact_title_match', 'relaxed_title_match', 'same_code_sibling_file_match'}:
            continue
        kind = record['documentType']
        bucket = by_type[kind]
        bucket['files'] += 1
        bucket['exactFiles'] += record['matchStatus'] == 'exact_title_match'
        bucket['relaxedFiles'] += record['matchStatus'] == 'relaxed_title_match'
        bucket.setdefault('siblingFiles', 0)
        bucket['siblingFiles'] += record['matchStatus'] == 'same_code_sibling_file_match'
        for hid in set(record.get('matchedHgabIds', [])) & by_id.keys():
            bucket['projectIds'].add(hid)
            matched[hid].append(record)
            for person in record.get('signatories', []):
                signatory_types[person.get('kind', 'unknown')] += 1
                signatory_types_by_document[kind][person.get('kind', 'unknown')] += 1
    project_rows = []
    for row in hgab_only:
        docs = matched.get(row['id'], [])
        types = defaultdict(list)
        for doc in docs:
            types[doc['documentType']].append(doc['file'])
        signatories = {}
        for doc in docs:
            for person in doc.get('signatories', []):
                key_value = (key(person.get('name')), person.get('kind'))
                entry = signatories.setdefault(key_value, {'name': person.get('name'), 'role': person.get('kind'), 'sourceFiles': set(), 'sourcePages': set(), 'documentTypes': set(), 'verificationStatuses': set()})
                entry['sourceFiles'].add(doc['file'])
                entry['sourcePages'].add(person.get('sourcePage'))
                entry['documentTypes'].add(doc.get('documentType'))
                entry['verificationStatuses'].add(person.get('verificationStatus'))
        project_rows.append({
            'hgabId': row['id'], 'title': row.get('projectName'), 'office': row.get('office'),
            'region': row.get('region'), 'amountPesos': row.get('amountPesos'),
            'hasAtLeastOneTitleMatchedDocument': bool(docs),
            'matchedDocumentFileRecords': len({doc['file'] for doc in docs}),
            'documentTypes': {kind: {'fileRecords': len(set(types.get(kind, []))), 'present': bool(types.get(kind, []))}
                              for kind in ('POW', 'BP 202', 'Development Council', 'Geotagged photos', 'Certificate of Implementability', 'Other')},
            'signatories': [{**item, 'sourceFiles': sorted(item['sourceFiles']),
                            'sourcePages': sorted(p for p in item['sourcePages'] if p is not None),
                            'documentTypes': sorted(t for t in item['documentTypes'] if t),
                            'verificationStatuses': sorted(s for s in item['verificationStatuses'] if s)}
                           for item in signatories.values()],
        })
    matched_ids = set(matched)
    code_to_hgab = {code: next(iter(ids)) for code, ids in ids_by_code.items() if len(ids) == 1}
    inventory_types = inventory.get('typesByCode', {})
    codes_by_hgab = defaultdict(set)
    for code, hid in code_to_hgab.items():
        codes_by_hgab[hid].add(code)
    for project in project_rows:
        codes = sorted(codes_by_hgab.get(project['hgabId'], set()))
        totals = Counter()
        for code in codes:
            totals.update({kind: int(count or 0) for kind, count in inventory_types.get(code, {}).items()})
        project['t5FileCodes'] = codes
        project['t5FileCount'] = sum(totals.values())
        project['t5FilePresenceByType'] = dict(totals)
    all_types = ('POW', 'BP 202', 'Development Council', 'Geotagged photos',
                 'Certificate of Implementability', 'Other')
    scanned_by_type = Counter(record.get('documentType') for record in records)
    errors_by_type = Counter(record.get('documentType') for record in records if record.get('scanError') or record.get('matchStatus') == 'scan_error')
    no_text_by_type = Counter(record.get('documentType') for record in records if not record.get('nativeText'))
    bp_report = read_json(ROOT / 'analysis_output/senate_bp202_hgab_only_title_scan.json', {})
    type_summary = {}
    for kind in all_types:
        value = by_type.get(kind, {'projectIds': set(), 'files': 0, 'exactFiles': 0, 'relaxedFiles': 0, 'siblingFiles': 0})
        scanned = scanned_by_type.get(kind, 0)
        if kind == 'BP 202':
            scanned = int(bp_report.get('senateDocumentsScanned') or scanned)
            errors_by_type[kind] = int(bp_report.get('documentsWithScanErrors') or 0)
            no_text_by_type[kind] = int(bp_report.get('documentsWithNoNativeFirstPageText') or 0)
        type_summary[kind] = {
            'filesScanned': scanned, 'matchedProjectRows': len(value['projectIds']),
            'matchedFileRecords': value['files'], 'exactTitleMatchedFiles': value['exactFiles'],
            'relaxedTitleMatchedFiles': value['relaxedFiles'], 'uniqueCodeSiblingFileMatches': value.get('siblingFiles', 0),
            'scanErrors': errors_by_type.get(kind, 0),
            'filesWithoutNativeText': no_text_by_type.get(kind, 0),
        }
    return {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'scope': 'FY2027 HGAB project rows without a selected NEP counterpart. Rows count once even if multiple supporting files or document types match. Title match is evidence of file presence, not contents or completeness.',
        'matchingMethod': 'Native text from the first PDF page. Exact normalized full-title matches and conservative relaxed title candidates are counted. Other files inherit a match only when they share a five-digit HGAB file code with a title-matched sibling and that code resolves to one House row. Image-only documents without extracted text and without a matched sibling remain unassigned.',
        'denominatorProjectRows': len(hgab_only),
        'projectsWithAtLeastOneMatchedDocument': len(matched_ids),
        'projectsWithAtLeastOneMatchedDocumentPct': round(100 * len(matched_ids) / len(hgab_only), 2) if hgab_only else 0,
        'projectRowsWithoutMatchedDocument': len(hgab_only) - len(matched_ids),
        'matchedFileRecords': sum(v['matchedFileRecords'] for v in type_summary.values()),
        'byType': type_summary,
        'localT5Inventory': inventory.get('previousLocalT5Inventory', {}),
        'cloudflareFileInventory': {k: v for k, v in (cloudflare or {}).items()
                                    if k not in {'filesByCode', 'typesByCode'}},
        'signatoryCandidateCounts': dict(signatory_types),
        'signatoryCandidatesByDocumentType': {kind: dict(counter) for kind, counter in signatory_types_by_document.items()},
        'deduplication': 'Project counts use distinct House HGAB row IDs. File counts are distinct source paths within a project and type; byte-identical copies at different paths are not removed. T5 file-type counts inherit only from uniquely resolved HGAB file codes.',
        'projects': project_rows,
        'documents': records,
    }


def _run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--interval', type=int, default=60)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--max-documents', type=int, default=0, help='optional cap for a bounded scan pass')
    args = parser.parse_args()
    if not 1 <= args.workers <= 8 or args.interval < 10:
        parser.error('Use 1-8 workers and an interval of at least 10 seconds')
    guard()
    mapping = json.loads(MAPPING.read_text(encoding='utf-8'))
    hgab_only = [row for row in mapping.get('hgabWithoutSelectedCounterpart', [])
                 if row.get('allocationKind') == 'project' and row.get('projectName')]
    title_index = defaultdict(set)
    titles_by_id = {}
    title_frequency = Counter()
    for row in hgab_only:
        tokens = set(key(row['projectName']).split())
        titles_by_id[row['id']] = (row['projectName'], tokens)
        title_frequency.update(tokens)
        for token in tokens:
            title_index[token].add(row['id'])
    by_title = defaultdict(list)
    for row in hgab_only:
        by_title[key(row['projectName'])].append(row)
    old = read_json(OUT, {})
    old_records = {record.get('file'): record for record in old.get('documents', []) if record.get('file')}
    historical = saved_title_scans()
    historical_by_file = {record.get('file'): record for record in historical if record.get('file')}
    for file, record in historical_by_file.items():
        old_records.setdefault(file, record)

    while True:
        paths = []
        for task in downloaded_pdf_tasks():
            previous = old_records.get(task['file'])
            if (previous and previous.get('sourceSha256') == task.get('sourceSha256')
                    and (not task.get('roleKind') or previous.get('signatoryParserVersion') == SIGNATORY_PARSER_VERSION)):
                continue
            paths.append(task)
        if args.max_documents:
            paths = paths[:args.max_documents]
        status = {'status': 'scanning_downloaded_manifest_files', 'source': 'Cloudflare-file-downloads.jsonl', 'totalProjectRows': len(hgab_only),
                  'candidateFiles': len(paths), 'completedThisPass': 0, 'workers': args.workers,
                  'heartbeatAtUtc': datetime.now(timezone.utc).isoformat()}
        atomic_json(STATUS, status)
        if paths:
            with ProcessPoolExecutor(max_workers=args.workers, initializer=initialize_worker,
                                     initargs=(dict(title_index), titles_by_id, dict(title_frequency), by_title)) as pool:
                futures = {pool.submit(scan_one, task): task for task in paths}
                done = 0
                for future in as_completed(futures):
                    result = future.result()
                    previous = old_records.get(result['file'])
                    if previous and previous.get('matchStatus') in {'exact_title_match', 'relaxed_title_match'} and result.get('matchStatus') not in {'exact_title_match', 'relaxed_title_match'}:
                        for field in ('matchStatus', 'matchedHgabIds', 'matchedHgabTitles', 'extractedTitle'):
                            result[field] = previous.get(field)
                        result['matchedVia'] = previous.get('matchedVia') or 'retained from the earlier dedicated title scan'
                    old_records[result['file']] = result
                    done += 1
                    if done % 100 == 0 or done == len(paths):
                        status.update({'completedThisPass': done, 'heartbeatAtUtc': datetime.now(timezone.utc).isoformat()})
                        atomic_json(STATUS, status)
                        if done % 500 == 0 or done == len(paths):
                            print(json.dumps({'completed': done, 'total': len(paths), 'file': result['file'], 'matchStatus': result.get('matchStatus')}), flush=True)
        if paths or args.once:
            cloudflare = cloudflare_inventory()
            previous_t5_types = {}
            for project in old.get('projects', []):
                for code in project.get('t5FileCodes', []):
                    previous_t5_types[code] = project.get('t5FilePresenceByType', {})
            inventory = {'typesByCode': previous_t5_types,
                         'previousLocalT5Inventory': old.get('localT5Inventory', {})}
            report = consolidate(hgab_only, list(old_records.values()), inventory, cloudflare)
            atomic_json(OUT, report)
            with CSV_OUT.open('w', encoding='utf-8-sig', newline='') as stream:
                fields = ['hgabId', 'title', 'office', 'region', 'amountPesos', 'hasAtLeastOneTitleMatchedDocument', 'matchedDocumentFileRecords', 'documentTypes', 't5FileCodes', 't5FileCount', 't5FilePresenceByType', 'signatories']
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
                for row in report['projects']:
                    writer.writerow({**row, 'documentTypes': json.dumps(row['documentTypes'], ensure_ascii=False), 't5FileCodes': json.dumps(row['t5FileCodes'], ensure_ascii=False), 't5FilePresenceByType': json.dumps(row['t5FilePresenceByType'], ensure_ascii=False), 'signatories': json.dumps(row['signatories'], ensure_ascii=False)})
            status.update({'status': 'complete', 'completedThisPass': len(paths),
                           'projectsWithAtLeastOneMatchedDocument': report['projectsWithAtLeastOneMatchedDocument'],
                           'matchedDocuments': report['matchedFileRecords'],
                           'pageRefreshStatus': 'running',
                           'heartbeatAtUtc': datetime.now(timezone.utc).isoformat()})
            atomic_json(STATUS, status)
            if paths or args.once:
                # Publish completed scan totals before refreshing pages so
                # concurrent status readers and the audit see the same snapshot.
                try:
                    subprocess.run([sys.executable, str(ROOT / 'refresh_parsed_document_pages.py'),
                                    'senate-supporting-document-scan'], cwd=ROOT, check=True)
                except Exception as exc:
                    status.update({'status': 'error', 'pageRefreshStatus': 'error',
                                   'lastError': f'{type(exc).__name__}: {str(exc)[:500]}',
                                   'heartbeatAtUtc': datetime.now(timezone.utc).isoformat()})
                    atomic_json(STATUS, status)
                    raise
                status.update({'pageRefreshStatus': 'complete',
                               'heartbeatAtUtc': datetime.now(timezone.utc).isoformat()})
                atomic_json(STATUS, status)
        else:
            # A one-shot scan or another worker may have refreshed the report
            # since this loop started. Read the published report for status so
            # a long-running process cannot keep advertising stale totals.
            latest = json.loads(OUT.read_text()) if OUT.is_file() else old
            status.update({'status': 'idle', 'projectsWithAtLeastOneMatchedDocument': latest.get('projectsWithAtLeastOneMatchedDocument', 0),
                           'heartbeatAtUtc': datetime.now(timezone.utc).isoformat()})
            atomic_json(STATUS, status)
        if args.once:
            break
        time.sleep(args.interval)


def main():
    lock_path = STATUS.with_suffix('.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit('Another supporting-document scanner is already running') from exc
        _run()


if __name__ == '__main__':
    main()
