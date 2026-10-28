#!/usr/bin/env python3
"""Reparse one cached POW with the current parser and republish Indepth."""
import argparse
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'data_sources/dpwh_project_documents/on_demand'
CODE = re.compile(r'^2027DPWH-Proposal-\d{5}$')


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def reparse(code):
    from storage.external_storage import guard
    from project_documents.cache_lock import project_lock
    from project_documents import pow as pow_parser
    from project_documents.service import kinds
    from project_documents.signatories import extract

    folder = CACHE / code
    guard()
    metadata_path = folder / 'metadata.json'
    result_path = folder / 'result.json'
    if not metadata_path.is_file() or not result_path.is_file():
        raise FileNotFoundError(f'{code} has no cached metadata/result; this command does not download documents')

    with project_lock(folder, blocking=False):
        metadata = json.loads(metadata_path.read_text())
        result = json.loads(result_path.read_text())
        project_documents = [(document, kinds(document)) for document in metadata.get('documents', [])]
        pow_document = next((d for d, kind in project_documents if kind == 'pow'), None)
        if pow_document is None:
            raise ValueError(f'{code} has no POW listed in cached metadata')
        version = hashlib.sha256(json.dumps(pow_document, sort_keys=True).encode()).hexdigest()[:16]
        old = next((d for d in result.get('documents', [])
                    if d.get('kind') == 'pow' and d.get('metadata', {}).get('url') == pow_document.get('url')), {})
        pdf = folder / 'assets' / version / 'pow.pdf'
        # API metadata can change IDs/upload timestamps while the same source
        # URL remains cached under its earlier ID. Reuse the exact-URL asset
        # and compute a fresh checksum instead of downloading a second copy.
        if not pdf.is_file() and old.get('version'):
            cached_pdf = folder / 'assets' / old['version'] / 'pow.pdf'
            if cached_pdf.is_file():
                pdf = cached_pdf
                version = old['version']
        if not pdf.is_file():
            raise FileNotFoundError(f'Cached POW PDF is missing: {pdf}')
        with pdf.open('rb') as stream:
            if b'%PDF-' not in stream.read(1024):
                raise ValueError('Cached POW file does not have a PDF header')

        allocation = round(float(metadata['amount']) * 1000)
        row = {**old, 'kind': 'pow', 'metadata': pow_document, 'version': version,
               'pdfAsset': version + '/pow.pdf',
               'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
               'parsedBy': 'on_demand_reparse', 'parserVersion': hashlib.sha256(
                   (ROOT / 'project_documents/pow.py').read_bytes() +
                   (ROOT / 'project_documents/ocr_vision.swift').read_bytes()).hexdigest()}
        row['pow'] = pow_parser.parse_pdf(pdf, pdf.parent, allocation)
        row['signatories'] = old.get('signatories') or extract(pdf, 'pow', pdf.parent)
        row['status'] = 'available'
        row.pop('error', None)
        result['documents'] = [d for d in result.get('documents', [])
                               if not (d.get('kind') == 'pow' and d.get('metadata', {}).get('url') == pow_document.get('url'))]
        result['documents'].append(row)
        result['updatedByOnDemandReparseAtUtc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        atomic_json(result_path, result)
        parsed = row['pow']

    guard()
    import build_dpwh_indepth
    summary = build_dpwh_indepth.build()
    return {'projectCode': code, 'status': parsed.get('status'),
            'pages': parsed.get('pagesProcessed'), 'itemRows': len(parsed.get('rows', [])),
            'categoryRows': len(parsed.get('costCategoryBreakdown', [])),
            'publishedPowProjects': summary.get('projectsWithParsedPow')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project_code', help='Cached proposal code, e.g. 2027DPWH-Proposal-22663')
    args = parser.parse_args()
    if not CODE.fullmatch(args.project_code):
        parser.error('project code must look like 2027DPWH-Proposal-22663')
    try:
        print(json.dumps(reparse(args.project_code), ensure_ascii=False))
    except BlockingIOError:
        parser.exit(2, 'Project cache is busy with a download or parser; retry after it finishes.\n')


if __name__ == '__main__':
    main()
