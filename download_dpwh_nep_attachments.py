#!/usr/bin/env python3
"""Resumably archive every attachment listed for the FY2027 DPWH NEP projects."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import unquote, urlsplit

from storage.external_storage import BASE, guard

guard()
os.environ['DPWH_EXTERNAL_VOLUME'] = '/Volumes/T5 EVO'
os.environ['DPWH_DOCUMENT_CACHE'] = str(BASE / 'nep/data_sources/dpwh_project_documents/on_demand')
from project_documents.service import CACHE, metadata

REPO = Path(__file__).resolve().parent
TREE = REPO / 'data_sources/csiiiv/snapshots/34ef5d8cbbacda92f6503ffd9a428569f157f64d/analysis/data/dpwh_transparency_nep_tree.json'
ROOT = BASE / 'nep/data_sources/dpwh_project_documents/attachments'
JOURNAL = ROOT / 'downloads.jsonl'
STATUS = ROOT / 'status.json'
MAX_BYTES = int(os.environ.get('DPWH_DOCUMENT_MAX_BYTES', str(2 * 1024**3)))
HOSTS = {'s3.infrawatch.ph', 'transparency.dpwh.gov.ph'}


def stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def signature(document):
    identity = {k: document.get(k) for k in ('id', 'fileName', 'url', 'sizeBytes', 'contentType', 'uploadedAt')}
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def filename(document):
    name = unquote(str(document.get('fileName') or Path(urlsplit(document['url']).path).name))
    name = name.replace('\\', '_').replace('/', '_')
    name = ''.join(c if c.isprintable() and c not in '<>:"|?*' else '_' for c in name).strip(' .')
    return name[:240] or 'attachment.bin'


def load_journal():
    found = {}
    if JOURNAL.exists():
        with JOURNAL.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                    if row.get('status') == 'downloaded':
                        found[row['signature']] = row
                except (json.JSONDecodeError, KeyError):
                    continue
    return found


def append(row):
    ROOT.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def cached_asset(code, document):
    result_path = CACHE / code / 'result.json'
    if not result_path.exists():
        return None
    try:
        result = json.loads(result_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    for row in result.get('documents', []):
        if row.get('metadata') != document:
            continue
        rel = row.get('pdfAsset') or row.get('cachedAsset')
        if rel:
            path = CACHE / code / 'assets' / rel
            if path.is_file():
                return path
    return None


def download(url, target, expected_size, content_type):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in HOSTS:
        raise ValueError('Attachment URL is outside the approved HTTPS source hosts')
    if expected_size is not None and expected_size > MAX_BYTES:
        raise ValueError(f'Attachment exceeds configured {MAX_BYTES}-byte limit')
    guard()
    if shutil.disk_usage(ROOT).free < (expected_size or 0) + 2 * 1024**3:
        raise OSError('External drive has less than expected attachment size plus 2 GiB free')
    part = target.with_name(target.name + '.part')
    part.parent.mkdir(parents=True, exist_ok=True)
    if part.exists():
        part.unlink()
    command = [
        'curl', '--silent', '--show-error', '--fail', '--proto', '=https',
        '--connect-timeout', '20', '--max-time', '300', '--max-filesize', str(MAX_BYTES),
        '--output', str(part), '--write-out', '%{http_code}', url,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode or result.stdout.strip() != '200':
        part.unlink(missing_ok=True)
        raise RuntimeError(f'curl HTTP {result.stdout.strip() or "?"} exit {result.returncode}: {result.stderr.strip()[:240]}')
    size = part.stat().st_size
    if expected_size is not None and size != expected_size:
        part.unlink(missing_ok=True)
        raise ValueError(f'Downloaded {size} bytes; metadata lists {expected_size}')
    if (content_type or '').lower().split(';')[0] == 'application/pdf':
        with part.open('rb') as stream:
            if b'%PDF-' not in stream.read(1024):
                part.unlink(missing_ok=True)
                raise ValueError('Metadata says PDF but file signature is missing')
    part.replace(target)
    return size, digest(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=1.0, help='seconds between attachment downloads')
    args = parser.parse_args()
    if args.delay < 0.2:
        parser.error('Use a delay of at least 0.2 seconds')
    guard()
    tree = json.loads(TREE.read_text())
    projects = [
        {'projectCode': node.get('source', {}).get('project_code') or node['id'],
         'projectName': node.get('label'),
         'indexedDocumentCount': node.get('source', {}).get('document_count') or 0}
        for node in tree.get('nodes', []) if node.get('kind') == 'project'
    ]
    if len(projects) != 11372 or len({p['projectCode'] for p in projects}) != len(projects):
        raise ValueError('Pinned transparency index has an unexpected or duplicate project set')
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'download.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another NEP attachment archive process is already running')
        run(projects, args.delay)


def run(projects, delay):
    done = load_journal()
    status = {'startedAt': stamp(), 'sourceIndexCommit': '34ef5d8cbbacda92f6503ffd9a428569f157f64d',
              'projectsTotal': len(projects), 'projectsDone': 0, 'projectsWithAttachments': 0,
              'attachmentsListed': 0, 'attachmentsDownloaded': len(done), 'errors': 0}
    for index, entry in enumerate(projects, 1):
        guard()
        code = entry['projectCode']
        status.update(currentProject=code, projectsDone=index - 1)
        try:
            project = metadata(code, refresh=True)
            docs = project.get('documents', [])
            if docs:
                status['projectsWithAttachments'] += 1
            status['attachmentsListed'] += len(docs)
            for number, document in enumerate(docs, 1):
                guard()
                try:
                    url = document.get('url')
                    if not url:
                        raise ValueError(f'Attachment {document.get("id", number)} has no source URL')
                    sig = signature(document)
                    prior = done.get(sig)
                    relative = Path(code) / f'{document.get("id", number)}-{sig[:16]}' / filename(document)
                    target = ROOT / relative
                if prior and target.is_file() and target.stat().st_size == prior.get('bytes'):
                    if digest(target) == prior.get('sha256'):
                        continue
                    source = cached_asset(code, document)
                    if source and not target.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            os.link(source, target)
                        except OSError:
                            shutil.copy2(source, target)
                        actual_size = target.stat().st_size
                        sha = digest(target)
                        if document.get('sizeBytes') is not None and actual_size != document['sizeBytes']:
                            target.unlink()
                        else:
                            row = {'at': stamp(), 'projectCode': code, 'documentId': document.get('id'),
                                   'documentType': document.get('documentType'), 'fileName': document.get('fileName'),
                                   'url': url, 'signature': sig, 'path': str(relative), 'bytes': actual_size,
                                   'sha256': sha, 'status': 'downloaded', 'source': 'reused_external_cache'}
                            append(row); done[sig] = row; status['attachmentsDownloaded'] += 1
                            continue
                    size, sha = download(url, target, document.get('sizeBytes'), document.get('contentType'))
                    row = {'at': stamp(), 'projectCode': code, 'documentId': document.get('id'),
                           'documentType': document.get('documentType'), 'fileName': document.get('fileName'),
                           'contentType': document.get('contentType'), 'url': url, 'signature': sig,
                           'path': str(relative), 'bytes': size, 'sha256': sha, 'status': 'downloaded'}
                    append(row); done[sig] = row; status['attachmentsDownloaded'] += 1
                    print(json.dumps({'project': code, 'attachment': number, 'total': len(docs), 'file': document.get('fileName'), 'status': 'downloaded'}, ensure_ascii=False), flush=True)
                except Exception as exc:
                    status['errors'] += 1
                    append({'at': stamp(), 'projectCode': code, 'documentId': document.get('id'),
                            'fileName': document.get('fileName'), 'url': document.get('url'),
                            'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)[:300]})
                    print(json.dumps({'project': code, 'attachment': number, 'file': document.get('fileName'), 'status': 'error', 'error': str(exc)[:300]}, ensure_ascii=False), flush=True)
                status['updatedAt'] = stamp()
                STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
                time.sleep(delay)
        except Exception as exc:
            status['errors'] += 1
            append({'at': stamp(), 'projectCode': code, 'status': 'error', 'error': type(exc).__name__ + ': ' + str(exc)[:300]})
            print(json.dumps({'project': code, 'status': 'error', 'error': str(exc)[:300]}), flush=True)
        status['projectsDone'] = index
        status['updatedAt'] = stamp()
        STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
        time.sleep(delay)
    status.update(currentProject=None, finishedAt=stamp(), attachmentsDownloaded=len(done))
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    main()
