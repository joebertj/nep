#!/usr/bin/env python3
"""Continuously parse manually journaled HGAB POW PDFs from the T5 archive."""
import argparse
import calendar
from concurrent.futures import ProcessPoolExecutor, as_completed
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
import uuid

from storage.external_storage import BASE, guard

guard()
ROOT = BASE / 'nep/data_sources/dpwh_project_documents'
DATA_SOURCES = BASE / 'nep/data_sources'
ATTACHMENTS = ROOT / 'attachments'
JOURNAL = ATTACHMENTS / 'downloads-hgab.jsonl'
OUTPUT = ROOT / 'parsed_pow'
STATUS = ROOT / 'pow-parser-watcher-status.json'
LOCK = ROOT / 'pow-parser-loop.lock'
CODE = re.compile(r'^2027DPWH-HGAB-\d{5}$')
VERSION = hashlib.sha256(
    (Path(__file__).resolve().parent / 'project_documents/pow.py').read_bytes()
    + (Path(__file__).resolve().parent / 'project_documents/ocr_vision.swift').read_bytes()
    + Path(__file__).resolve().read_bytes()
).hexdigest()
STATE_LOCK = threading.RLock()


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {} if default is None else default


def write_json(path, value):
    guard()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def journal_rows():
    rows = {}
    if JOURNAL.is_file():
        with JOURNAL.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                code, digest = row.get('projectCode'), row.get('sha256')
                if (row.get('status') in {'downloaded', 'present_verified_on_t5'} and isinstance(code, str)
                        and CODE.fullmatch(code) and isinstance(digest, str)):
                    rows[(code, digest)] = row
    return rows


def total_downloaded_pow(hgab_rows, state):
    """Keep the shared count inclusive of the portal batch already processed by its older worker."""
    return int(state.get('portalPowBaseline', 0)) + len(hgab_rows)


def marker_for(row):
    code, digest = row['projectCode'], row['sha256']
    target = OUTPUT / code / (row['documentId'] + '-' + digest[:16])
    marker = read_json(target / 'status.json')
    if marker.get('sourceSha256') == digest and marker.get('status') in {
            'parsed', 'error', 'skipped_missing_source'}:
        return marker
    return None


def pending_items(rows, retry_after):
    pending, retries, skipped, errors, skipped_missing = [], 0, 0, 0, 0
    retry_cutoff = time.time() - retry_after
    for key, row in sorted(rows.items()):
        marker = marker_for(row)
        if marker and marker.get('status') == 'parsed':
            skipped += 1
            continue
        if marker and marker.get('status') == 'skipped_missing_source':
            source = (ATTACHMENTS / row['path']).resolve()
            if not source.is_file():
                skipped_missing += 1
                continue
        if marker and marker.get('status') == 'error':
            errors += 1
            try:
                attempted = calendar.timegm(time.strptime(marker.get('atUtc', ''), '%Y-%m-%dT%H:%M:%SZ'))
            except (ValueError, TypeError):
                attempted = 0
            parser_changed = marker.get('parserVersion') != VERSION
            if not parser_changed and attempted > retry_cutoff:
                retries += 1
                continue
        pending.append(row)
    return pending, skipped, retries, errors, skipped_missing


def output_result(row, parsed, target):
    return {
        'projectCode': row['projectCode'],
        'documentId': row['documentId'],
        'documentType': 'POW',
        'sourceFileName': row.get('fileName'),
        'sourceRelativePath': row.get('path'),
        'sourceSha256': row['sha256'],
        'sourceUrl': None,
        'downloadedAtUtc': row.get('at'),
        'parsedAtUtc': now(),
        'parserVersion': VERSION,
        'ocrEngine': 'Apple Vision and native PDF text' if sys.platform == 'darwin' else 'native PDF text',
        'allocationPesos': None,
        'allocationShareNote': 'NEP allocation not attached by this HGAB parser; item amounts and printed POW summaries remain available.',
        'status': parsed['status'],
        'pdfSha256': parsed['pdfSha256'],
        'pageCount': parsed['pageCount'],
        'pagesProcessed': parsed['pagesProcessed'],
        'pages': parsed['pages'],
        'rows': parsed['rows'],
        'costCategoryBreakdown': parsed['costCategoryBreakdown'],
        'summaryMetadata': parsed['summaryMetadata'],
        'rowObservations': parsed['rowObservations'],
        'uniqueCandidateRows': parsed['uniqueCandidateRows'],
        'sumOfUniqueCandidateAmountsPesos': parsed['sumOfUniqueCandidateAmountsPesos'],
        'reconciledPowTotal': parsed['reconciledPowTotal'],
        'itemizedDirectCostControls': parsed['itemizedDirectCostControls'],
        'amountBasis': parsed['amountBasis'],
        'limits': parsed['limits'],
    }


def parser_heartbeat(stop, state):
    while not stop.wait(30):
        with STATE_LOCK:
            state['heartbeatAtUtc'] = now()
            state['updatedAtUtc'] = state['heartbeatAtUtc']
            write_json(STATUS, state)


def parse_one(row):
    """Parse one independent PDF in an isolated worker process."""
    from project_documents import pow as pow_parser
    guard()
    code, digest = row['projectCode'], row['sha256']
    source = (ATTACHMENTS / row['path']).resolve()
    try:
        source.relative_to(DATA_SOURCES.resolve())
    except ValueError as exc:
        raise ValueError('Journaled source path escapes the T5 data_sources tree') from exc
    if not source.is_file():
        raise FileNotFoundError(f'Journaled POW is missing: {row["path"]}')
    if source.stat().st_size != int(row.get('bytes') or 0):
        raise ValueError('Journaled PDF byte count changed')
    if sha256(source) != digest:
        raise ValueError('Journaled PDF SHA-256 changed')
    with source.open('rb') as stream:
        if b'%PDF-' not in stream.read(1024):
            raise ValueError('Journaled POW is not a PDF')
    target = OUTPUT / code / (row['documentId'] + '-' + digest[:16])
    try:
        parsed = pow_parser.parse_pdf(source, target, allocation_pesos=None)
    except Exception as exc:
        # PyMuPDF exceptions can contain SWIG objects and fail to pickle when
        # ProcessPoolExecutor sends them back to the coordinator. Return only
        # primitive values so the original parser error is preserved.
        return {'_workerErrorType': type(exc).__name__,
                '_workerErrorMessage': str(exc)[:1000]}
    if parsed.get('status') == 'parser_dependency_missing':
        raise RuntimeError(parsed.get('message', 'PyMuPDF is required'))
    return parsed


def run_once(state, retry_after, workers):
    rows = journal_rows()
    pending, skipped, retries, prior_errors, skipped_missing = pending_items(rows, retry_after)
    with STATE_LOCK:
        state.update({
            'parserVersion': VERSION,
            'totalDownloadedPow': total_downloaded_pow(rows, state),
            'skippedCurrent': skipped,
            'skippedMissingSource': skipped_missing,
            'pending': len(pending) + retries,
            'pendingNewDownloads': len(pending),
            'pendingWithoutParseResult': len(pending),
            'pendingRetry': retries,
            'totalPendingIncludingActive': len(pending) + retries,
            'activeCount': 0,
            'active': [],
            'current': None,
            'workers': workers,
            'coordinatorWorkers': 1,
            'heartbeatAtUtc': now(),
            'parserPid': os.getpid(),
            'status': 'processing' if pending else 'waiting_retry' if retries else 'idle',
            'lastError': state.get('lastError'),
        })
        write_json(STATUS, state)

    completed = 0
    if pending:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(parse_one, row): row for row in pending}
            with STATE_LOCK:
                state.update({'activeCount': min(workers, len(pending)),
                              'active': [row['projectCode'] for row in pending[:workers]],
                              'current': pending[0]['projectCode'],
                              'heartbeatAtUtc': now()})
                write_json(STATUS, state)
            for future in as_completed(futures):
                row = futures[future]
                code, digest = row['projectCode'], row['sha256']
                target = OUTPUT / code / (row['documentId'] + '-' + digest[:16])
                marker_path = target / 'status.json'
                try:
                    parsed = future.result()
                    if parsed.get('_workerErrorType'):
                        raise RuntimeError(
                            f"{parsed['_workerErrorType']}: {parsed.get('_workerErrorMessage', '')}"
                        )
                    result = output_result(row, parsed, target)
                    write_json(target / 'result.json', result)
                    marker = {
                        'parserVersion': VERSION, 'sourceSha256': digest, 'status': 'parsed',
                        'parsedAtUtc': now(), 'rows': len(result['rows']),
                        'categories': len(result['costCategoryBreakdown']),
                        'parseStatus': result['status'],
                        'paddleFallbackNeeded': False, 'paddleFallbackPages': [],
                    }
                    write_json(marker_path, marker)
                    with STATE_LOCK:
                        state['processed'] = int(state.get('processed', 0)) + 1
                        state['rows'] = int(state.get('rows', 0)) + len(result['rows'])
                        state['categories'] = int(state.get('categories', 0)) + len(result['costCategoryBreakdown'])
                        state['lastError'] = None
                        state['lastParsedCode'] = code
                        state['lastParsedStatus'] = result['status']
                    print(json.dumps({'code': code, 'status': result['status'],
                                      'rows': len(result['rows']), 'categories': len(result['costCategoryBreakdown'])}), flush=True)
                except Exception as exc:
                    target.mkdir(parents=True, exist_ok=True)
                    message = f'{type(exc).__name__}: {str(exc)[:500]}'
                    missing_source = (isinstance(exc, FileNotFoundError)
                                      and message.startswith('FileNotFoundError: Journaled POW is missing:'))
                    write_json(marker_path, {
                        'parserVersion': VERSION, 'sourceSha256': digest,
                        'status': 'skipped_missing_source' if missing_source else 'error',
                        'atUtc': now(), 'error': message,
                    })
                    with STATE_LOCK:
                        if missing_source:
                            state['skippedMissingSource'] = int(state.get('skippedMissingSource', 0)) + 1
                            state['lastError'] = None
                        else:
                            state['errors'] = int(state.get('errors', 0)) + 1
                            state['lastError'] = f'{code}: {message[:300]}'
                    print(json.dumps({'code': code,
                                      'status': 'skipped_missing_source' if missing_source else 'error',
                                      'error': message}), flush=True)
                completed += 1
                with STATE_LOCK:
                    remaining = len(pending) - completed
                    state.update({'status': 'processing' if remaining else 'waiting_retry' if retries else 'idle',
                                  'current': None if remaining == 0 else state.get('current'),
                                  'pendingNewDownloads': remaining,
                                  'pendingWithoutParseResult': remaining,
                                  'pending': remaining + retries,
                                  'totalPendingIncludingActive': remaining + retries,
                                  'activeCount': min(workers, remaining),
                                  'heartbeatAtUtc': now()})
                    write_json(STATUS, state)

    pending, skipped, retries, errors, skipped_missing = pending_items(journal_rows(), retry_after)
    final_rows = journal_rows()
    with STATE_LOCK:
        state.update({'totalDownloadedPow': total_downloaded_pow(final_rows, state), 'skippedCurrent': skipped,
                      'skippedMissingSource': skipped_missing,
                      'pending': len(pending) + retries, 'pendingNewDownloads': len(pending),
                      'pendingWithoutParseResult': len(pending), 'pendingRetry': retries,
                      'totalPendingIncludingActive': len(pending) + retries,
                      'activeCount': 0, 'active': [], 'current': None,
                      'status': 'waiting_retry' if retries else 'idle',
                      'heartbeatAtUtc': now(), 'updatedAtUtc': now()})
        write_json(STATUS, state)
    return len(pending), retries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=int, default=30, help='seconds between parser queue scans')
    parser.add_argument('--retry-seconds', type=int, default=900,
                        help='minimum delay before retrying a failed PDF')
    parser.add_argument('--workers', type=int, default=5,
                        help='isolated parser worker processes (1-5; default 5)')
    parser.add_argument('--once', action='store_true', help='process one queue pass and exit')
    args = parser.parse_args()
    if args.interval < 5 or args.retry_seconds < 60 or not 1 <= args.workers <= 5:
        parser.error('Use interval >= 5 seconds, retry delay >= 60 seconds, and 1-5 workers')
    try:
        import pymupdf  # noqa: F401
    except ImportError as exc:
        raise SystemExit('PyMuPDF is required. Install project_documents/requirements.txt in the parser environment.') from exc
    import importlib.util
    paddle_available = importlib.util.find_spec('paddleocr') is not None
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open('a+') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SystemExit('Another HGAB POW parser loop is already running.') from exc
        previous = read_json(STATUS)
        if not isinstance(previous.get('portalPowBaseline'), int):
            existing_hgab_statuses = 0
            for marker_path in OUTPUT.glob('2027DPWH-HGAB-*/*/status.json'):
                marker = read_json(marker_path)
                if marker.get('status') in {'parsed', 'error', 'skipped_missing_source'}:
                    existing_hgab_statuses += 1
            previous['portalPowBaseline'] = max(
                0, int(previous.get('totalDownloadedPow', 0)) - existing_hgab_statuses)
        state = {
            **previous,
            'parserVersion': VERSION,
            'startedAtUtc': previous.get('startedAtUtc') or now(),
            'workers': args.workers, 'coordinatorWorkers': 1,
            'primaryOcrEngine': ('Apple Vision and native PDF text with PaddleOCR PP-OCRv5 scanned-page fallback'
                                 if sys.platform == 'darwin' and paddle_available else
                                 'native PDF text with PaddleOCR PP-OCRv5 scanned-page fallback'
                                 if paddle_available else
                                 'Apple Vision and native PDF text' if sys.platform == 'darwin' else 'native PDF text'),
            'paddleFallbackWorkers': args.workers if paddle_available else 0,
            'queuePolicy': 'Process available POW files; terminally skip missing journaled source PDFs, and requeue if the source later appears.',
            'status': 'starting', 'active': [], 'activeCount': 0, 'current': None,
            'skippedMissingSource': int(previous.get('skippedMissingSource', 0)),
            'heartbeatAtUtc': now(), 'parserPid': os.getpid(),
        }
        stop = threading.Event()
        heartbeat = threading.Thread(target=parser_heartbeat, args=(stop, state), daemon=True)
        heartbeat.start()
        try:
            while True:
                run_once(state, args.retry_seconds, args.workers)
                if args.once:
                    break
                time.sleep(args.interval)
        finally:
            stop.set()
            heartbeat.join(timeout=2)
            with STATE_LOCK:
                state.update({'status': 'stopped', 'active': [], 'activeCount': 0,
                              'current': None, 'parserPid': None,
                              'heartbeatAtUtc': now(), 'updatedAtUtc': now()})
                write_json(STATUS, state)


if __name__ == '__main__':
    main()
