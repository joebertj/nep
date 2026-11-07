#!/usr/bin/env python3
"""Hash-audit the T5 supporting-document tree against the Cloudflare file index."""
import hashlib
import json
import os
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from download_dpwh_nep_attachments import (ATTACHMENTS, ALL_JOURNAL, JOURNAL,
                                           file_sha256, manifest_rows, path_key)
from storage.external_storage import BASE, guard

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'analysis_output/Cloudflare-file-links.jsonl'
SOURCE = BASE / 'nep/data_sources/OneDrive_2026-11-05/Supporting Documents (IO)'
OUT = ROOT / 'analysis_output/t5-cloudflare-manifest-audit.json'


def path_key(value):
    return unicodedata.normalize('NFKC', unquote(str(value or ''))).replace('\\', '/').strip('/').casefold()


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    guard()
    if not SOURCE.is_dir():
        raise FileNotFoundError(f'T5 supporting-document directory not found: {SOURCE}')
    rows, rejected = manifest_rows()
    expected = {path_key(row['sourcePath']): row for row in rows}
    actual = {}
    walk_errors = []
    for directory, directories, files in os.walk(SOURCE, followlinks=False):
        directories[:] = [name for name in directories
                          if not name.startswith('_') and not name.startswith('._')
                          and name != '.DS_Store' and not (Path(directory) / name).is_symlink()]
        for name in files:
            if name.startswith('_') or name.startswith('._') or name == '.DS_Store':
                continue
            path = Path(directory) / name
            relative = path.relative_to(SOURCE).as_posix()
            try:
                if not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError as exc:
                walk_errors.append({'path': relative, 'error': f'{type(exc).__name__}: {str(exc)[:200]}'})
                continue
            actual[path_key(relative)] = {'path': path, 'relativePath': relative, 'bytes': size}

    items = []
    by_type = {}
    for index, (key, row) in enumerate(expected.items(), 1):
        local = actual.get(key)
        item = {
            'sourcePath': row['sourcePath'], 'manifestSha256': row['sha256'],
            'manifestBytes': row['bytes'], 'projectCode': row['projectCode'],
            'documentType': row['documentType'], 'isPdfByName': row['isPdf'],
            'manifestId': row['manifestId'],
        }
        if local is None:
            item['status'] = 'missing'
        else:
            item.update({'actualPath': local['relativePath'], 'actualBytes': local['bytes']})
            if local['bytes'] != row['bytes']:
                item['status'] = 'size_mismatch'
            else:
                try:
                    digest = file_sha256(local['path'])
                    item['actualSha256'] = digest
                    with local['path'].open('rb') as stream:
                        item['isPdfBySignature'] = stream.read(5) == b'%PDF-'
                    item['status'] = 'verified' if digest == row['sha256'] else 'hash_mismatch'
                except OSError as exc:
                    item.update({'status': 'unreadable', 'error': f'{type(exc).__name__}: {str(exc)[:200]}'})
        items.append(item)
        summary = by_type.setdefault(row['documentType'], Counter())
        summary[item['status']] += 1
        if index % 2000 == 0:
            print(json.dumps({'hashedOrChecked': index, 'manifestEntries': len(expected)}), flush=True)

    expected_keys = set(expected)
    extra_entries = [(key, entry) for key, entry in actual.items() if key not in expected_keys]
    extra_hashes = {}
    extras = []
    for key, entry in extra_entries:
        try:
            digest = file_sha256(entry['path'])
            extra_hashes.setdefault(digest, []).append(entry)
            extras.append({'path': entry['relativePath'], 'bytes': entry['bytes'], 'sha256': digest})
        except OSError as exc:
            extras.append({'path': entry['relativePath'], 'bytes': entry['bytes'],
                           'error': f'{type(exc).__name__}: {str(exc)[:200]}'})
    for item in items:
        if item['status'] == 'missing' and item['manifestSha256'] in extra_hashes:
            candidate = extra_hashes[item['manifestSha256']][0]
            item.update({'status': 'verified_alternate_path', 'actualPath': candidate['relativePath'],
                         'actualBytes': candidate['bytes'], 'actualSha256': item['manifestSha256']})
    # The downloader cache is also on T5. Count a manifest object as present
    # when its cached bytes verify, even if the original source-folder path is absent.
    cached = {}
    for journal in (ALL_JOURNAL, JOURNAL):
        if not journal.is_file():
            continue
        with journal.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('status') != 'downloaded' or not row.get('sourcePath') or not row.get('manifestSha256') or not row.get('path'):
                    continue
                source = (ATTACHMENTS / row['path']).resolve()
                try:
                    source.relative_to(ATTACHMENTS.resolve())
                    if not source.is_file() or source.stat().st_size != int(row.get('manifestBytes') or row.get('bytes') or -1):
                        continue
                    digest = file_sha256(source)
                except (OSError, ValueError):
                    continue
                if digest == row['manifestSha256']:
                    cached[(path_key(row['sourcePath']), row['manifestSha256'])] = row
    for item in items:
        pair = (path_key(item['sourcePath']), item['manifestSha256'])
        row = cached.get(pair)
        if row and item['status'] not in {'verified', 'verified_alternate_path'}:
            item.update({'status': 'verified_attachment_cache',
                         'actualPath': row['path'], 'actualBytes': int(row.get('bytes') or 0),
                         'actualSha256': item['manifestSha256'], 'storageRoot': 'T5 parser attachment cache'})
    by_type = {}
    for item in items:
        by_type.setdefault(item['documentType'], Counter())[item['status']] += 1
    statuses = Counter(item['status'] for item in items)
    result = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'source': 'T5 Supporting Documents (IO) tree matched by normalized relative path and SHA-256; underscore-prefixed items and macOS ._ metadata excluded.',
        'manifestPath': 'analysis_output/Cloudflare-file-links.jsonl',
        'manifestSha256': file_sha256(MANIFEST),
        'sourceTree': str(SOURCE),
        'excludedManifestRows': rejected,
        'manifestEntries': len(rows), 't5Files': len(actual),
        'verifiedAttachmentCacheEntries': len(cached),
        'statusCounts': dict(statuses),
        'statusByDocumentType': {kind: dict(counts) for kind, counts in by_type.items()},
        'extraT5Files': len(extras), 'extraT5Paths': extras,
        'walkErrors': walk_errors,
        'items': items,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUT.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temporary.replace(OUT)
    print(json.dumps({k: result[k] for k in ('generatedAtUtc', 'manifestEntries', 't5Files', 'statusCounts', 'statusByDocumentType', 'extraT5Files', 'walkErrors')}, ensure_ascii=False, indent=2))
    print(f'Audit: {OUT}')


if __name__ == '__main__':
    main()
