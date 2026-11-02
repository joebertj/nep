#!/usr/bin/env python3
"""Continuously archive newly listed FY2027 DPWH Transparency attachments."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import unquote, urlencode, urlsplit

from storage.external_storage import BASE, guard

guard()
os.environ['DPWH_EXTERNAL_VOLUME'] = '/Volumes/T5 EVO'
os.environ['DPWH_DOCUMENT_CACHE'] = str(BASE / 'nep/data_sources/dpwh_project_documents/on_demand')
from project_documents.service import API, CACHE, metadata, request

ROOT = BASE / 'nep/data_sources/dpwh_project_documents/attachments'
JOURNAL = ROOT / 'downloads.jsonl'
STATUS = ROOT / 'status.json'
MAX_BYTES = int(os.environ.get('DPWH_DOCUMENT_MAX_BYTES', str(2 * 1024**3)))
HOSTS = {'s3.infrawatch.ph', 'transparency.dpwh.gov.ph'}
API_PAGE_LIMIT = 500
STATUS_LOCK = threading.RLock()


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


def write_status(status):
    with STATUS_LOCK:
        snapshot = dict(status)
        snapshot['updatedAt'] = stamp()
        temporary = STATUS.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(STATUS)


def status_heartbeat(stop, status):
    while not stop.wait(30):
        with STATUS_LOCK:
            status['heartbeatAt'] = stamp()
        write_status(status)


def live_projects():
    """Read every page of the current Transparency project listing."""
    projects = []
    expected_count = None
    total_pages = None
    for page in range(1, 100000):
        query = urlencode({'page': page, 'limit': API_PAGE_LIMIT})
        with request(f'{API}?{query}') as response:
            payload = json.load(response)
        if payload.get('status') != 200 or not isinstance(payload.get('data'), dict):
            raise RuntimeError('Live DPWH project listing returned an unexpected response')
        body = payload['data']
        rows, pagination = body.get('data'), body.get('pagination')
        if not isinstance(rows, list) or not isinstance(pagination, dict):
            raise RuntimeError('Live DPWH project listing is missing pagination data')
        count, pages = pagination.get('totalCount'), pagination.get('totalPages')
        if not isinstance(count, int) or not isinstance(pages, int) or pages < 1:
            raise RuntimeError('Live DPWH project listing has invalid totals')
        if expected_count is None:
            expected_count, total_pages = count, pages
        elif count != expected_count or pages != total_pages:
            raise RuntimeError('Live DPWH project listing changed during pagination; retry next cycle')
        for row in rows:
            code = row.get('code')
            if not isinstance(code, str) or not re.fullmatch(r'2027DPWH-Proposal-\d{5}', code):
                raise RuntimeError('Live DPWH project listing contains an invalid project code')
            projects.append({'projectCode': code, 'projectName': row.get('projectName'),
                             'indexedDocumentCount': row.get('documentCount') or 0})
        if page >= total_pages:
            break
        if not rows:
            raise RuntimeError(f'Live DPWH project listing ended early at page {page}')
    if expected_count is None or len(projects) != expected_count:
        raise RuntimeError(f'Live DPWH project listing incomplete: got {len(projects)} of {expected_count}')
    if len({project['projectCode'] for project in projects}) != len(projects):
        raise RuntimeError('Live DPWH project listing contains duplicate project codes')
    return sorted(projects, key=lambda project: project['projectCode'])


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
        '--connect-timeout', '30', '--max-time', '1800', '--retry', '3', '--retry-delay', '3',
        '--retry-all-errors', '--max-filesize', str(MAX_BYTES),
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


def update_status(state, **values):
    with STATUS_LOCK:
        state.update(values)


def increment_status(status, key, amount=1):
    with STATUS_LOCK:
        status[key] = status.get(key, 0) + amount


def run(delay, interval_hours, once, project_codes=None):
    done = load_journal()
    status = {'status': 'starting', 'mode': 'daily_live_catalog_poll',
              'startedAt': stamp(), 'pollIntervalHours': interval_hours,
              'attachmentsDownloaded': len(done), 'errors': 0}
    heartbeat_stop = threading.Event()
    heartbeat = threading.Thread(target=status_heartbeat, args=(heartbeat_stop, status), daemon=True)
    heartbeat.start()
    cycle = 0
    try:
        while True:
            cycle += 1
            update_status(status, status='checking_catalog', cycle=cycle,
                          catalogAttemptAt=stamp(), lastCatalogError=None)
            write_status(status)
            try:
                catalog = live_projects()
            except Exception as exc:
                update_status(status, status='catalog_error', currentProject=None,
                              lastCatalogError=f'{type(exc).__name__}: {str(exc)[:300]}')
                write_status(status)
                if once:
                    raise
                retry_seconds = min(300, max(30, interval_hours * 36))
                retry_at = time.time() + retry_seconds
                update_status(status, nextCatalogRetryAt=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(retry_at)))
                write_status(status)
                while time.time() < retry_at:
                    time.sleep(min(30, retry_at - time.time()))
                continue

            source_total = len(catalog)
            projects = catalog
            if project_codes:
                wanted = set(project_codes)
                known = {project['projectCode'] for project in catalog}
                unknown = wanted - known
                if unknown:
                    raise ValueError('Unknown proposal code(s): ' + ', '.join(sorted(unknown)))
                projects = [project for project in catalog if project['projectCode'] in wanted]
            started_at = status.get('startedAt') or stamp()
            with STATUS_LOCK:
                status.clear()
                status.update({'status': 'running', 'mode': 'daily_live_catalog_poll',
                               'cycle': cycle, 'cycleStartedAt': stamp(), 'catalogCheckedAt': stamp(),
                               'source': 'live_dpwh_transparency_api', 'projectsTotal': len(projects),
                               'sourceProjectsTotal': source_total, 'projectsDone': 0,
                               'projectsWithAttachments': 0, 'attachmentsListed': 0,
                               'attachmentsDownloaded': len(done), 'errors': 0,
                               'documentCountMismatches': 0, 'pollIntervalHours': interval_hours,
                               'startedAt': started_at})
            write_status(status)

            for index, entry in enumerate(projects, 1):
                guard()
                code = entry['projectCode']
                update_status(status, currentProject=code, currentDocument=None, projectsDone=index - 1)
                try:
                    project = metadata(code, refresh=True)
                    docs = project.get('documents', [])
                    if len(docs) != entry['indexedDocumentCount']:
                        increment_status(status, 'documentCountMismatches')
                    if docs:
                        increment_status(status, 'projectsWithAttachments')
                    increment_status(status, 'attachmentsListed', len(docs))
                    for number, document in enumerate(docs, 1):
                        guard()
                        update_status(status, currentDocument=document.get('fileName') or document.get('id'),
                                      currentAttachment=number, currentProjectAttachments=len(docs))
                        write_status(status)
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
                                    target.unlink(missing_ok=True)
                                else:
                                    row = {'at': stamp(), 'projectCode': code, 'documentId': document.get('id'),
                                           'documentType': document.get('documentType'), 'fileName': document.get('fileName'),
                                           'url': url, 'signature': sig, 'path': str(relative), 'bytes': actual_size,
                                           'sha256': sha, 'status': 'downloaded', 'source': 'reused_external_cache'}
                                    append(row)
                                    done[sig] = row
                                    increment_status(status, 'attachmentsDownloaded')
                                    continue
                            size, sha = download(url, target, document.get('sizeBytes'), document.get('contentType'))
                            row = {'at': stamp(), 'projectCode': code, 'documentId': document.get('id'),
                                   'documentType': document.get('documentType'), 'fileName': document.get('fileName'),
                                   'contentType': document.get('contentType'), 'url': url, 'signature': sig,
                                   'path': str(relative), 'bytes': size, 'sha256': sha, 'status': 'downloaded'}
                            append(row)
                            done[sig] = row
                            increment_status(status, 'attachmentsDownloaded')
                            print(json.dumps({'project': code, 'attachment': number, 'total': len(docs),
                                              'file': document.get('fileName'), 'status': 'downloaded'}, ensure_ascii=False), flush=True)
                        except Exception as exc:
                            increment_status(status, 'errors')
                            append({'at': stamp(), 'projectCode': code, 'documentId': document.get('id'),
                                    'documentType': document.get('documentType'), 'fileName': document.get('fileName'),
                                    'url': document.get('url'), 'status': 'error',
                                    'error': type(exc).__name__ + ': ' + str(exc)[:300]})
                            print(json.dumps({'project': code, 'attachment': number, 'file': document.get('fileName'),
                                              'status': 'error', 'error': str(exc)[:300]}, ensure_ascii=False), flush=True)
                        write_status(status)
                        time.sleep(delay)
                except Exception as exc:
                    increment_status(status, 'errors')
                    append({'at': stamp(), 'projectCode': code, 'status': 'error',
                            'error': type(exc).__name__ + ': ' + str(exc)[:300]})
                    print(json.dumps({'project': code, 'status': 'error', 'error': str(exc)[:300]}, ensure_ascii=False), flush=True)
                update_status(status, projectsDone=index, currentProject=None, currentDocument=None)
                write_status(status)
                time.sleep(delay)

            finished = stamp()
            next_cycle = time.time() + interval_hours * 3600
            update_status(status, status='waiting', currentProject=None, currentDocument=None,
                          lastCycleFinishedAt=finished, lastCycleProjects=len(projects),
                          lastCycleAttachmentsListed=status['attachmentsListed'],
                          lastCycleErrors=status['errors'],
                          nextCycleAt=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(next_cycle)))
            if once:
                update_status(status, status='complete', complete=True, finishedAt=finished)
                write_status(status)
                print(json.dumps(status, ensure_ascii=False, indent=2), flush=True)
                return
            write_status(status)
            while time.time() < next_cycle:
                time.sleep(min(30, next_cycle - time.time()))
    finally:
        heartbeat_stop.set()
        heartbeat.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--delay', type=float, default=1.0, help='seconds between attachment downloads')
    parser.add_argument('--interval-hours', type=float, default=24.0,
                        help='hours between completed live catalog scans')
    parser.add_argument('--once', action='store_true', help='run one live catalog scan and exit')
    parser.add_argument('--project', action='append', dest='project_codes',
                        help='limit a one-time retry to these proposal codes; may be repeated')
    args = parser.parse_args()
    if args.delay < 0.2:
        parser.error('Use a delay of at least 0.2 seconds')
    if args.interval_hours < 1:
        parser.error('Use an interval of at least one hour')
    if args.project_codes and not args.once:
        parser.error('--project requires --once; continuous mode scans the complete live catalog')
    guard()
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'download.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another NEP attachment archive process is already running')
        run(args.delay, args.interval_hours, args.once, args.project_codes)


if __name__ == '__main__':
    main()
