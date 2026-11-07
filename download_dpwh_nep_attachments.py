#!/usr/bin/env python3
"""Download missing Senate HGAB POW PDFs from the Cloudflare link index.

The manifest is the sole inventory source. This worker does not walk or scan
T5 source folders; it reads the parser download journal for SHA-256 deduplication
and writes newly fetched PDFs plus journal rows to the existing parser intake.
CAR and NIR are processed first because those folders were being redownloaded.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import unicodedata
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler
import ssl

from storage.external_storage import BASE, guard

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'analysis_output' / 'Cloudflare-file-links.jsonl'
ATTACHMENTS = BASE / 'nep/data_sources/dpwh_project_documents/attachments'
JOURNAL = ATTACHMENTS / 'downloads-hgab.jsonl'
STATUS = ATTACHMENTS / 'cloudflare-hgab-intake-status.json'
ALL_JOURNAL = ATTACHMENTS / 'cloudflare-file-downloads.jsonl'
SCAN_SNAPSHOT = ROOT / 'analysis_output' / 'senate_supporting_documents_hgab_only_scan.json'
CODE_PATTERN = re.compile(r'(?:2027[-_\s]*)?DPWH[-_\s]*HGAB[-_\s-]*(\d{5})', re.I)
ALLOWED_HOST = 'budget-assets.bettergov.ph'
ALLOWED_PATH = '/hgab/2027/dpwh/supporting-documents/'
PRIORITY_REGIONS = {'CAR', 'NIR'}
EMPTY_SHA256 = hashlib.sha256(b'').hexdigest()


def stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def write_json(path, value):
    guard()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def journaled_versions():
    """Read the append-only parser journal; never enumerate its PDF folders."""
    versions = set()
    if JOURNAL.is_file():
        with JOURNAL.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('status') == 'downloaded' and row.get('projectCode') and row.get('sha256'):
                    versions.add((row['projectCode'], row['sha256']))
    return versions


def is_pow(row):
    path = unquote(str(row.get('path') or '').rsplit('/', 1)[-1]).casefold()
    return bool(re.search(r'(?:^|[^a-z])pow(?:[^a-z]|$)|program\s+of\s+works?', path))


def classify(row):
    name = unquote(str(row.get('path') or '').rsplit('/', 1)[-1]).upper()
    if is_pow(row):
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


def path_key(value):
    value = unicodedata.normalize('NFKC', unquote(str(value or ''))).replace('\\', '/')
    return re.sub(r'/+', '/', value).strip('/').casefold()


def safe_manifest_row(row):
    path = str(row.get('path') or '')
    parts = path.replace('\\', '/').split('/')
    # Underscore-prefixed files/folders are known error artifacts and excluded.
    if any(part.startswith('_') for part in parts):
        return None
    match = CODE_PATTERN.search(path)
    digest = str(row.get('sha256') or '').lower()
    url = str(row.get('url') or '')
    parsed = urlsplit(url)
    if not re.fullmatch(r'[a-f0-9]{64}', digest):
        return None
    if parsed.scheme != 'https' or parsed.hostname != ALLOWED_HOST or not parsed.path.startswith(ALLOWED_PATH):
        return None
    try:
        size = int(row.get('bytes') or 0)
    except (TypeError, ValueError):
        return None
    malformed = size == 0 and digest == EMPTY_SHA256
    if size < 0 or (size == 0 and not malformed):
        return None
    code = f'2027DPWH-HGAB-{match.group(1)}' if match else None
    return {
        'projectCode': code,
        'documentId': match.group(1) if match else None,
        'fileName': Path(unquote(parts[-1])).name,
        'region': str(row.get('region') or (parts[0] if parts else '')).strip(),
        'sourcePath': path,
        'url': url,
        'bytes': size,
        'sha256': digest,
        'malformedManifestPdf': malformed,
        'isPdf': Path(parts[-1]).suffix.casefold() == '.pdf',
        'documentType': classify(row),
        'manifestId': str(row.get('id') or ''),
        'objectKey': str(row.get('object_key') or ''),
    }


def manifest_rows():
    if not MANIFEST.is_file():
        raise FileNotFoundError(f'Cloudflare inventory is missing: {MANIFEST}')
    rows = {}
    rejected = 0
    with MANIFEST.open(encoding='utf-8') as stream:
        for line_number, line in enumerate(stream, 1):
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Malformed JSONL row {line_number}: {exc}') from exc
            item = safe_manifest_row(raw)
            if item is None:
                rejected += 1
                continue
            rows[(item['sourcePath'], item['sha256'])] = item
    return list(rows.values()), rejected


class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.hostname != ALLOWED_HOST or not parsed.path.startswith(ALLOWED_PATH):
            raise ValueError('Cloudflare redirect left the approved HGAB asset location')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(item, destination):
    guard()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if shutil_free_bytes() < item['bytes'] + 2_000_000_000:
        raise RuntimeError('Insufficient T5 space for download plus 2 GB reserve')
    part = destination.with_name(destination.name + '.part')
    request = Request(item['url'], headers={'User-Agent': 'BetterGov-HGAB-manifest-downloader/1.0'})
    opener = build_opener(SameHostRedirect(), HTTPSHandler(context=ssl.create_default_context()))
    digest = hashlib.sha256()
    total = 0
    try:
        with opener.open(request, timeout=60) as response, part.open('wb') as out:
            first = response.read(1024)
            if item['isPdf'] and b'%PDF-' not in first:
                raise ValueError('Cloudflare object does not begin with a PDF header')
            digest.update(first)
            total += len(first)
            out.write(first)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                total += len(chunk)
            out.flush()
            os.fsync(out.fileno())
        allow_replacement = item['isPdf'] and (item['malformedManifestPdf'] or item.get('brokenCandidate'))
        if not allow_replacement and total != item['bytes']:
            raise ValueError(f'Byte count mismatch: expected {item["bytes"]}, got {total}')
        actual_sha = digest.hexdigest()
        if not allow_replacement and actual_sha != item['sha256']:
            raise ValueError('SHA-256 does not match Cloudflare inventory')
        guard()
        part.replace(destination)
        return total, actual_sha
    except Exception:
        part.unlink(missing_ok=True)
        raise


def shutil_free_bytes():
    import shutil
    return shutil.disk_usage(ATTACHMENTS).free


def append_journal(row):
    guard()
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open('a', encoding='utf-8') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def snapshot_inventory():
    """Use the last already-published T5 scan snapshot; never reread T5 folders."""
    try:
        old = json.loads(SCAN_SNAPSHOT.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    result = {}
    for row in old.get('documents', []):
        path = path_key(row.get('file'))
        if path:
            result[path] = row
    return result


def downloaded_manifest_keys():
    keys = set()
    for journal in (ALL_JOURNAL, JOURNAL):
        if not journal.is_file():
            continue
        with journal.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get('status') in {'downloaded', 'malformed_source'} and row.get('sourcePath') and row.get('manifestSha256'):
                    keys.add((path_key(row['sourcePath']), row['manifestSha256']))
    return keys


def append_download_journals(item, relative, actual_bytes, actual_sha):
    at = stamp()
    row = {
        'at': at, 'manifestId': item['manifestId'],
        'projectCode': item['projectCode'], 'documentId': item['documentId'],
        'documentType': item['documentType'], 'fileName': item['fileName'],
        'contentType': 'application/pdf' if item['isPdf'] else None,
        'path': relative.as_posix(), 'bytes': actual_bytes, 'sha256': actual_sha,
        'signature': actual_sha, 'status': 'downloaded',
        'sourceArchive': 'Cloudflare-file-links.jsonl', 'sourcePath': item['sourcePath'],
        'objectKey': item['objectKey'], 'sourceUrl': item['url'],
        'manifestSha256': item['sha256'], 'manifestBytes': item['bytes'],
        'recoveredMalformedManifestPdf': item['malformedManifestPdf'],
    }
    guard()
    ATTACHMENTS.mkdir(parents=True, exist_ok=True)
    with ALL_JOURNAL.open('a', encoding='utf-8') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    if item['documentType'] == 'POW' and item['projectCode']:
        append_journal({
            **row, 'documentType': 'POW',
            'sourceArchive': 'Cloudflare-file-links.jsonl',
        })


def index_files(dry_run=False, max_downloads=0):
    guard()
    inventory, rejected = manifest_rows()
    baseline = snapshot_inventory()
    journaled = downloaded_manifest_keys()
    missing = []
    for row in inventory:
        old = baseline.get(path_key(row['sourcePath']))
        broken = bool(row['malformedManifestPdf'] or (old and (
            old.get('scanError') or old.get('matchStatus') == 'scan_error'
            or int(old.get('sourceSize') or 0) != row['bytes'])))
        absent = old is None
        row['brokenCandidate'] = broken
        row['missingCandidate'] = absent
        if not (absent or broken):
            continue
        if (path_key(row['sourcePath']), row['sha256']) in journaled:
            continue
        missing.append(row)
    missing.sort(key=lambda row: (not row['brokenCandidate'],
                                  not row['malformedManifestPdf'],
                                  not (row['isPdf'] and row['documentType'] == 'POW'),
                                  row['region'].upper() not in PRIORITY_REGIONS,
                                  row['region'].upper(), row['projectCode'] or '', row['fileName']))
    priority_total = sum(row['region'].upper() in PRIORITY_REGIONS for row in missing)
    malformed_total = sum(row['brokenCandidate'] for row in missing)
    missing_pow = sum(row['documentType'] == 'POW' for row in missing)
    missing_pdf = sum(row['isPdf'] for row in missing)
    selected = missing[:max_downloads] if max_downloads else missing
    downloaded = failed = 0
    failures = []
    if not dry_run:
        for index, item in enumerate(selected, 1):
            safe_name = re.sub(r'[^A-Za-z0-9._ -]+', '_', item['fileName']).strip(' .') or 'document.bin'
            safe_region = re.sub(r'[^A-Za-z0-9._ -]+', '_', item['region']).strip(' .') or 'unknown-region'
            relative = Path('cloudflare-files') / safe_region / (item['projectCode'] or 'unmatched-code') / (item['sha256'][:16] + '-' + safe_name)
            target = ATTACHMENTS / relative
            try:
                actual_bytes, actual_sha = fetch(item, target)
                append_download_journals(item, relative, actual_bytes, actual_sha)
                downloaded += 1
            except (OSError, ValueError, RuntimeError, HTTPError, URLError) as exc:
                failed += 1
                failure = {'at': stamp(), 'manifestId': item['manifestId'],
                           'projectCode': item['projectCode'], 'fileName': item['fileName'],
                           'sourcePath': item['sourcePath'], 'manifestSha256': item['sha256'],
                           'brokenCandidate': item['brokenCandidate'],
                           'error': f'{type(exc).__name__}: {str(exc)[:250]}'}
                failures.append(failure)
                if item['isPdf'] and (item['malformedManifestPdf'] or item['brokenCandidate']) and isinstance(exc, ValueError):
                    failure['status'] = 'malformed_source'
                    with ALL_JOURNAL.open('a', encoding='utf-8') as stream:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                        stream.write(json.dumps(failure, ensure_ascii=False) + '\n')
                        stream.flush()
                        os.fsync(stream.fileno())
            if index % 25 == 0 or index == len(selected):
                write_json(STATUS, {
                    'status': 'downloading', 'pid': os.getpid(),
                    'processed': index, 'totalCandidates': len(selected),
                    'downloaded': downloaded, 'failed': failed,
                    'currentFile': item['sourcePath'], 'heartbeatAtUtc': stamp(),
                })
    return {
        'status': 'dry_run' if dry_run else 'downloaded',
        'inventory': str(MANIFEST), 'indexedFiles': len(inventory),
        'excludedRows': rejected, 'journaledVersions': len(journaled),
        'missingManifestVersions': len(missing),
        'missingManifestBytes': sum(row['bytes'] for row in missing),
        'missingPowFiles': missing_pow, 'missingPdfFiles': missing_pdf,
        'priorityRegions': sorted(PRIORITY_REGIONS),
        'brokenOrMalformedFiles': malformed_total,
        'priorityRegionMissing': priority_total,
        'downloadAttempted': 0 if dry_run else len(selected),
        'downloaded': downloaded, 'failed': failed, 'failureSample': failures[:10],
        'remainingAfterLimit': max(0, len(missing) - len(selected)),
        'journal': str(JOURNAL),
        'filesystemPolicy': 'No T5 folder traversal or source archive scan; Cloudflare manifest plus parser journal only.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=int, default=60, help='seconds between manifest checks (default: 60)')
    parser.add_argument('--once', action='store_true', help='check/download once and exit')
    parser.add_argument('--dry-run', action='store_true', help='compare manifest and journal without downloading')
    parser.add_argument('--max-downloads', type=int, default=0, help='cap downloads per pass; 0 means all missing POWs')
    args = parser.parse_args()
    if args.interval < 10:
        parser.error('Use an interval of at least 10 seconds')
    if args.max_downloads < 0:
        parser.error('--max-downloads cannot be negative')
    if args.dry_run:
        args.once = True
    while True:
        try:
            result = index_files(args.dry_run, args.max_downloads)
            if not args.dry_run:
                result['pid'] = os.getpid()
                result['heartbeatAtUtc'] = stamp()
                write_json(STATUS, result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            failure = {'status': 'error', 'pid': os.getpid(),
                       'error': f'{type(exc).__name__}: {str(exc)[:500]}',
                       'heartbeatAtUtc': stamp(),
                       'filesystemPolicy': 'No T5 folder traversal or source archive scan.'}
            if not args.dry_run:
                write_json(STATUS, failure)
            print(json.dumps(failure, ensure_ascii=False), flush=True)
            if args.once:
                raise
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
