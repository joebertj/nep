#!/usr/bin/env python3
"""Reparse cached POWs with no recovered rows or outstanding review pages.

The progress file makes the batch resumable. This reads only already cached
PDFs and takes each project's normal lock before replacing its parse result.
"""
import hashlib
import json
import argparse
import concurrent.futures
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'data_sources/dpwh_project_documents/on_demand'
SNAPSHOT = ROOT / 'analysis_output/dpwh-in-depth-data.json'
PROGRESS = CACHE.parent / '.reparse-failed-pow-progress.json'


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def pow_asset(folder, metadata):
    from project_documents.service import kinds
    document = next((doc for doc in metadata.get('documents', []) if kinds(doc) == 'pow'), None)
    if document is None:
        return None, None
    version = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()[:16]
    pdf = folder / 'assets' / version / 'pow.pdf'
    return document, pdf


def reparse_one(code):
    """Parse one zero-row POW in its own process (and PaddleOCR instance)."""
    from storage.external_storage import guard
    from project_documents.cache_lock import project_lock
    from project_documents import pow as pow_parser
    from project_documents.parse_preservation import retain_prior_pow_rows
    from project_documents.signatories import extract

    guard()
    folder = CACHE / code
    try:
        with project_lock(folder, blocking=False):
            metadata_path, result_path = folder / 'metadata.json', folder / 'result.json'
            if not metadata_path.is_file() or not result_path.is_file():
                return code, 'missing', None
            metadata = json.loads(metadata_path.read_text())
            result = json.loads(result_path.read_text())
            source, pdf = pow_asset(folder, metadata)
            if source is None or not pdf.is_file():
                return code, 'missing', None
            version = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:16]
            previous = next((doc for doc in result.get('documents', [])
                             if doc.get('kind') == 'pow' and
                             doc.get('metadata', {}).get('id') == source.get('id')), {})
            parsed_doc = {**previous, 'kind': 'pow', 'metadata': source, 'version': version,
                          'pdfAsset': version + '/pow.pdf',
                          'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                          'parsedBy': 'zero_row_pow_paddle_retry',
                          'parserVersion': hashlib.sha256(
                              (ROOT / 'project_documents/pow.py').read_bytes() +
                              (ROOT / 'project_documents/ocr_vision.swift').read_bytes()).hexdigest()}
            allocation = round(float(metadata['amount']) * 1000)
            parsed_doc['pow'] = pow_parser.parse_pdf(pdf, pdf.parent, allocation)
            parsed_doc['signatories'] = previous.get('signatories') or extract(pdf, 'pow', pdf.parent)
            parsed_doc['status'] = 'available'
            parsed_doc.pop('error', None)
            parsed_doc = retain_prior_pow_rows(previous, parsed_doc)
            result['documents'] = [doc for doc in result.get('documents', [])
                                   if not (doc.get('kind') == 'pow' and
                                           doc.get('metadata', {}).get('id') == source.get('id'))]
            result['documents'].append(parsed_doc)
            result['updatedByFailedPowBatchAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            atomic_json(result_path, result)
            parsed = parsed_doc['pow']
            return code, 'processed', {'status': parsed.get('status'),
                                        'rows': len(parsed.get('rows', [])),
                                        'reviewPages': sum(p.get('status') == 'needs_manual_review'
                                                           for p in parsed.get('pages', [])),
                                        'pages': parsed.get('pagesProcessed')}
    except BlockingIOError:
        return code, 'busy', None
    except Exception as error:
        return code, 'error', f'{type(error).__name__}: {error}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=1,
                        help='parallel PaddleOCR retry processes (default: 1)')
    parser.add_argument('--retry-errors', action='store_true',
                        help='retry only projects recorded as errors in the resumable progress file')
    parser.add_argument('--no-publish', action='store_true',
                        help='leave static publication to the already-running watcher')
    args = parser.parse_args()
    if args.workers < 1:
        parser.error('--workers must be at least 1')

    from storage.external_storage import guard
    guard()
    snapshot = json.loads(SNAPSHOT.read_text())
    progress = json.loads(PROGRESS.read_text()) if PROGRESS.is_file() else {}
    if progress.get('completed') and not args.retry_errors:
        print(json.dumps(progress, ensure_ascii=False), flush=True)
        return
    if args.retry_errors:
        progress['previousErrors'] = progress.get('errors', {})
        progress['errors'] = {}
        progress['completed'] = False
        progress['retryStartedAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    if not progress.get('codes') or progress.get('mode') != 'zero_rows_cached_only':
        codes = []
        for project in snapshot.get('projects', []):
            document = next((doc for doc in project.get('documents', []) if doc.get('kind') == 'pow'), None)
            if document and not document.get('rows'):
                code = project['code']
                folder = CACHE / code
                metadata_path, result_path = folder / 'metadata.json', folder / 'result.json'
                if not metadata_path.is_file() or not result_path.is_file():
                    continue
                try:
                    metadata = json.loads(metadata_path.read_text())
                    source, pdf = pow_asset(folder, metadata)
                    if source and pdf.is_file():
                        codes.append(code)
                except (OSError, ValueError, TypeError):
                    continue
        progress = {'mode': 'zero_rows_cached_only', 'workers': args.workers,
                    'startedAtUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'codes': codes, 'processed': {}, 'skippedBusy': [], 'missing': [], 'errors': {}}
    progress['workers'] = args.workers
    atomic_json(PROGRESS, progress)

    pending = [code for code in progress['codes']
               if code not in progress['processed'] and code not in progress['missing']
               and code not in progress['errors']]
    def record(index, code, outcome):
        try:
            _, status, detail = outcome
            if status == 'processed':
                progress['processed'][code] = detail
                progress['skippedBusy'] = [x for x in progress['skippedBusy'] if x != code]
            elif status == 'missing':
                if code not in progress['missing']: progress['missing'].append(code)
            elif status == 'busy':
                if code not in progress['skippedBusy']: progress['skippedBusy'].append(code)
            else:
                progress['errors'][code] = detail
        except Exception as error:
            progress['errors'][code] = f'{type(error).__name__}: {error}'
        atomic_json(PROGRESS, progress)
        print(json.dumps({'current': index, 'total': len(pending), 'code': code,
                          'result': progress['processed'].get(code, 'busy' if code in progress['skippedBusy']
                                                               else progress['errors'].get(code, 'missing'))},
                         ensure_ascii=False), flush=True)

    if args.workers == 1:
        # Avoid an unnecessary child process for the low-CPU single-worker mode.
        # This also avoids losing an entire batch if a spawned OCR worker exits.
        for index, code in enumerate(pending, 1):
            try:
                outcome = reparse_one(code)
            except Exception as error:
                outcome = (code, 'error', f'{type(error).__name__}: {error}')
            record(index, code, outcome)
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(reparse_one, code): code for code in pending}
            for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
                code = futures[future]
                try:
                    outcome = future.result()
                except Exception as error:
                    outcome = (code, 'error', f'{type(error).__name__}: {error}')
                record(index, code, outcome)

    progress['completedAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    progress['completed'] = not progress['skippedBusy']
    atomic_json(PROGRESS, progress)
    summary = None
    if not args.no_publish:
        guard()
        import build_dpwh_indepth
        summary = build_dpwh_indepth.build()
    print(json.dumps({'complete': progress['completed'], 'processed': len(progress['processed']),
                      'remainingBusy': len(progress['skippedBusy']), 'missing': len(progress['missing']),
                      'errors': len(progress['errors']),
                      'publishedPowProjects': summary.get('projectsWithParsedPow') if summary else None,
                      'publicationDeferredToWatcher': args.no_publish,
                      'progressFile': str(PROGRESS)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
