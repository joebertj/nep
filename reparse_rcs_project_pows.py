#!/usr/bin/env python3
"""Rerun the current POW parser for cached FY2027 RCS project documents."""
import hashlib
import json
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'data_sources/dpwh_project_documents/on_demand'
SNAPSHOT = ROOT / 'analysis_output/dpwh-in-depth-data.json'
PROGRESS = CACHE.parent / '.reparse-rcs-pow-progress.json'


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def main():
    from storage.external_storage import guard
    from project_documents.cache_lock import project_lock
    from project_documents import pow as pow_parser
    from project_documents.service import kinds
    from project_documents.signatories import extract

    guard()
    snapshot = json.loads(SNAPSHOT.read_text())
    parser_version = hashlib.sha256(
        (ROOT / 'project_documents/pow.py').read_bytes() +
        (ROOT / 'project_documents/ocr_vision.swift').read_bytes()).hexdigest()
    projects = [p for p in snapshot.get('projects', [])
                if 'rainwater collector system' in p.get('name', '').lower()
                and round(float(p.get('allocationPesos') or 0)) == 4_200_000]
    codes, missing, current = [], [], []
    for project in projects:
        folder = CACHE / project['code']
        metadata_path, result_path = folder / 'metadata.json', folder / 'result.json'
        if not metadata_path.is_file() or not result_path.is_file():
            missing.append(project['code'])
            continue
        metadata, result = json.loads(metadata_path.read_text()), json.loads(result_path.read_text())
        source = next((doc for doc in metadata.get('documents', []) if kinds(doc) == 'pow'), None)
        if source is None:
            missing.append(project['code'])
            continue
        old = next((doc for doc in result.get('documents', [])
                    if doc.get('kind') == 'pow' and
                    doc.get('metadata', {}).get('url') == source.get('url')), {})
        version = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:16]
        pdf = folder / 'assets' / version / 'pow.pdf'
        if not pdf.is_file() and old.get('version'):
            pdf = folder / 'assets' / old['version'] / 'pow.pdf'
            version = old['version']
        if not pdf.is_file():
            missing.append(project['code'])
        elif old.get('parserVersion') == parser_version:
            current.append(project['code'])
        else:
            codes.append(project['code'])

    progress = {'startedAtUtc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'scope': 'Cached ₱4.2M Rainwater Collector System POWs',
                'codes': codes, 'processed': {}, 'skippedBusy': [],
                'missing': missing, 'alreadyCurrent': current, 'errors': {}}
    atomic_json(PROGRESS, progress)
    for index, code in enumerate(codes, 1):
        guard()
        folder = CACHE / code
        try:
            with project_lock(folder, blocking=False):
                metadata = json.loads((folder / 'metadata.json').read_text())
                result = json.loads((folder / 'result.json').read_text())
                source = next((doc for doc in metadata.get('documents', []) if kinds(doc) == 'pow'), None)
                if source is None:
                    progress['missing'].append(code)
                    continue
                old = next((doc for doc in result.get('documents', [])
                            if doc.get('kind') == 'pow' and
                            doc.get('metadata', {}).get('url') == source.get('url')), {})
                version = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()[:16]
                pdf = folder / 'assets' / version / 'pow.pdf'
                if not pdf.is_file() and old.get('version'):
                    pdf = folder / 'assets' / old['version'] / 'pow.pdf'
                    version = old['version']
                if not pdf.is_file():
                    progress['missing'].append(code)
                    continue
                parsed_doc = {**old, 'kind': 'pow', 'metadata': source, 'version': version,
                              'pdfAsset': version + '/pow.pdf',
                              'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
                              'parsedBy': 'rcs_batch_reparse', 'parserVersion': parser_version}
                parsed_doc['pow'] = pow_parser.parse_pdf(
                    pdf, pdf.parent, round(float(metadata['amount']) * 1000))
                parsed_doc['signatories'] = old.get('signatories') or extract(pdf, 'pow', pdf.parent)
                parsed_doc['status'] = 'available'
                parsed_doc.pop('error', None)
                result['documents'] = [doc for doc in result.get('documents', [])
                                       if not (doc.get('kind') == 'pow' and
                                               doc.get('metadata', {}).get('url') == source.get('url'))]
                result['documents'].append(parsed_doc)
                result['updatedByRcsBatchReparseAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                atomic_json(folder / 'result.json', result)
                parsed = parsed_doc['pow']
                progress['processed'][code] = {'status': parsed.get('status'),
                                               'rows': len(parsed.get('rows', [])),
                                               'categories': len(parsed.get('costCategoryBreakdown', [])),
                                               'reviewPages': sum(p.get('status') == 'needs_manual_review'
                                                                  for p in parsed.get('pages', [])),
                                               'pages': parsed.get('pagesProcessed')}
        except BlockingIOError:
            progress['skippedBusy'].append(code)
        except Exception as error:
            progress['errors'][code] = f'{type(error).__name__}: {error}'
        atomic_json(PROGRESS, progress)
        print(json.dumps({'current': index, 'total': len(codes), 'code': code,
                          'result': progress['processed'].get(code,
                                      'busy' if code in progress['skippedBusy'] else
                                      progress['errors'].get(code, 'missing'))},
                         ensure_ascii=False), flush=True)

    progress['completedAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    progress['completed'] = not progress['skippedBusy']
    atomic_json(PROGRESS, progress)
    guard()
    import build_dpwh_indepth
    summary = build_dpwh_indepth.build()
    print(json.dumps({'complete': progress['completed'],
                      'rcsProjects': len(projects), 'reparsed': len(progress['processed']),
                      'alreadyCurrent': len(current), 'missingPowAssets': len(missing),
                      'remainingBusy': len(progress['skippedBusy']), 'errors': progress['errors'],
                      'publishedPowProjects': summary.get('projectsWithParsedPow'),
                      'progressFile': str(PROGRESS)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
