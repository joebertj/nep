#!/usr/bin/env python3
"""Reparse cached POWs with no recovered rows or outstanding review pages.

The progress file makes the batch resumable. This reads only already cached
PDFs and takes each project's normal lock before replacing its parse result.
"""
import hashlib
import json
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


def main():
    from storage.external_storage import guard
    from project_documents.cache_lock import project_lock
    from project_documents import pow as pow_parser
    from project_documents.signatories import extract

    guard()
    snapshot = json.loads(SNAPSHOT.read_text())
    progress = json.loads(PROGRESS.read_text()) if PROGRESS.is_file() else {}
    if progress.get('completed'):
        print(json.dumps(progress, ensure_ascii=False), flush=True)
        return
    if not progress.get('codes'):
        codes = []
        for project in snapshot.get('projects', []):
            document = next((doc for doc in project.get('documents', []) if doc.get('kind') == 'pow'), None)
            if document and (not document.get('rows') or document.get('reviewPages')):
                codes.append(project['code'])
        progress = {'startedAtUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                    'codes': codes, 'processed': {}, 'skippedBusy': [], 'missing': [], 'errors': {}}
        atomic_json(PROGRESS, progress)

    for index, code in enumerate(progress['codes'], 1):
        if code in progress['processed'] or code in progress['missing'] or code in progress['errors']:
            continue
        guard()
        folder = CACHE / code
        try:
            with project_lock(folder, blocking=False):
                metadata_path, result_path = folder / 'metadata.json', folder / 'result.json'
                if not metadata_path.is_file() or not result_path.is_file():
                    progress['missing'].append(code)
                    atomic_json(PROGRESS, progress)
                    continue
                metadata = json.loads(metadata_path.read_text())
                result = json.loads(result_path.read_text())
                source, pdf = pow_asset(folder, metadata)
                if source is None or not pdf.is_file():
                    progress['missing'].append(code)
                    atomic_json(PROGRESS, progress)
                    continue
                version = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:16]
                previous = next((doc for doc in result.get('documents', [])
                                 if doc.get('kind') == 'pow' and
                                 doc.get('metadata', {}).get('id') == source.get('id')), {})
                parsed_doc = {**previous, 'kind': 'pow', 'metadata': source, 'version': version,
                              'pdfAsset': version + '/pow.pdf',
                              'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                              'parsedBy': 'failed_pow_batch_reparse',
                              'parserVersion': hashlib.sha256(
                                  (ROOT / 'project_documents/pow.py').read_bytes() +
                                  (ROOT / 'project_documents/ocr_vision.swift').read_bytes()).hexdigest()}
                allocation = round(float(metadata['amount']) * 1000)
                parsed_doc['pow'] = pow_parser.parse_pdf(pdf, pdf.parent, allocation)
                parsed_doc['signatories'] = previous.get('signatories') or extract(pdf, 'pow', pdf.parent)
                parsed_doc['status'] = 'available'
                parsed_doc.pop('error', None)
                result['documents'] = [doc for doc in result.get('documents', [])
                                       if not (doc.get('kind') == 'pow' and
                                               doc.get('metadata', {}).get('id') == source.get('id'))]
                result['documents'].append(parsed_doc)
                result['updatedByFailedPowBatchAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                atomic_json(result_path, result)
                parsed = parsed_doc['pow']
                progress['processed'][code] = {'status': parsed.get('status'),
                                               'rows': len(parsed.get('rows', [])),
                                               'reviewPages': sum(p.get('status') == 'needs_manual_review'
                                                                  for p in parsed.get('pages', [])),
                                               'pages': parsed.get('pagesProcessed')}
                progress['skippedBusy'] = [x for x in progress['skippedBusy'] if x != code]
        except BlockingIOError:
            if code not in progress['skippedBusy']:
                progress['skippedBusy'].append(code)
        except Exception as error:
            progress['errors'][code] = f'{type(error).__name__}: {error}'
        atomic_json(PROGRESS, progress)
        print(json.dumps({'current': index, 'total': len(progress['codes']), 'code': code,
                          'result': progress['processed'].get(code, 'busy' if code in progress['skippedBusy']
                                                               else progress['errors'].get(code, 'missing'))},
                         ensure_ascii=False), flush=True)

    progress['completedAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    progress['completed'] = not progress['skippedBusy']
    atomic_json(PROGRESS, progress)
    guard()
    import build_dpwh_indepth
    summary = build_dpwh_indepth.build()
    print(json.dumps({'complete': progress['completed'], 'processed': len(progress['processed']),
                      'remainingBusy': len(progress['skippedBusy']), 'missing': len(progress['missing']),
                      'errors': len(progress['errors']), 'publishedPowProjects': summary.get('projectsWithParsedPow'),
                      'progressFile': str(PROGRESS)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
