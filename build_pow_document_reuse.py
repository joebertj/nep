#!/usr/bin/env python3
"""Find byte-identical cached Proposal and Senate HGAB PDFs across projects."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
ATTACHMENTS = ROOT / 'data_sources/dpwh_project_documents/attachments'
OUT = ROOT.parent / 'open-data-visualization/static/nep-preview/pow-document-reuse.json'
INDEPTH_ROOT = ROOT.parent / 'open-data-visualization/static/nep-preview'
INDEPTH_INDEX = INDEPTH_ROOT / 'dpwh-in-depth-data.json'
HGAB_COVERAGE = ROOT / 'analysis_output/hgab-document-coverage.json'
CLOUDFLARE_LINKS = ROOT / 'analysis_output/Cloudflare-file-links.jsonl'
CODE_RE = re.compile(r'2027DPWH-(?:PROPOSAL|HGAB)-\d{5}', re.I)


def document_type(filename: str) -> str:
    name = filename.casefold()
    if any(term in name for term in ('geotag', 'photo', 'photograph')):
        return 'Photos'
    if 'pow' in name or 'program of work' in name:
        return 'POW'
    if 'bp202' in name or 'bp 202' in name:
        return 'BP 202'
    if 'implementability' in name:
        return 'Certificate of Implementability'
    if any(term in name for term in ('development council', 'rdc', 'pdc', 'ldc', 'endorsement', 'resolution')):
        return 'Development Council'
    return 'Other'


def project_code_from_path(path: Path) -> str | None:
    # Use the project directory. A wrongly filed document can name a different
    # project in its filename, and that mismatch is useful evidence in itself.
    matches = [match.group(0).upper() for part in path.parts[:-1]
               for match in CODE_RE.finditer(part)]
    return matches[-1] if matches else None


def project_metadata() -> dict[str, dict]:
    index = json.loads(INDEPTH_INDEX.read_text(encoding='utf-8'))
    metadata = {}
    for shard in index.get('arrayShards', {}).get('projects', []):
        records = json.loads((INDEPTH_ROOT / shard['path']).read_text(encoding='utf-8'))
        for project in records:
            code = str(project.get('code') or '').upper()
            if code:
                metadata[code] = {
                    'projectCode': code, 'source': 'Proposal',
                    'title': project.get('name') or code,
                    'region': project.get('region'), 'office': project.get('office'),
                    'documentLinks': project.get('documentLinks') or [],
                }

    coverage = json.loads(HGAB_COVERAGE.read_text(encoding='utf-8'))
    for row in coverage.get('projects', []):
        info = {
            'projectCode': None, 'source': 'Senate HGAB',
            'title': None, 'region': None, 'office': None, 'linkedRows': {},
        }
        for document in row.get('senateDocuments') or []:
            for match in CODE_RE.finditer(str(document.get('path') or '')):
                if 'HGAB-' not in match.group(0).upper():
                    continue
                code = match.group(0).upper()
                existing = metadata.setdefault(code, {**info, 'projectCode': code})
                existing['linkedRows'][row.get('hgabId')] = {
                    'hgabId': row.get('hgabId'), 'title': row.get('title') or row.get('hgabId'),
                    'region': row.get('region'), 'office': row.get('office'),
                }
    return metadata


def filename_key(value: str) -> str:
    raw = str(value or '')
    parsed = urlsplit(raw)
    name = unquote(Path(parsed.path if parsed.scheme else raw.split('?')[0]).name).casefold()
    name = re.sub(r'^[0-9a-f]{16}-', '', name)
    return re.sub(r'[^a-z0-9]', '', name)


def cloudflare_links_by_sha_and_code() -> dict[tuple[str, str], list[dict]]:
    links: dict[tuple[str, str], list[dict]] = defaultdict(list)
    if not CLOUDFLARE_LINKS.exists():
        return links
    for line in CLOUDFLARE_LINKS.open(encoding='utf-8'):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        digest = str(record.get('sha256') or '').casefold()
        path = str(record.get('path') or '')
        codes = {match.group(0).upper() for part in path.split('/')[:-1]
                 for match in CODE_RE.finditer(part)}
        if digest and record.get('url'):
            for code in codes:
                links[(digest, code)].append(record)
    return links


def file_hash(candidate: tuple[Path, int, str, str]):
    path, size, code, kind = candidate
    digest = hashlib.sha256()
    try:
        with path.open('rb') as source:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
        return digest.hexdigest(), size, code, kind, path, None
    except OSError as error:
        return None, size, code, kind, path, str(error)


def build() -> dict:
    by_size: dict[int, list[tuple[Path, str, str]]] = defaultdict(list)
    scanned = 0
    for directory, subdirs, filenames in os.walk(ATTACHMENTS):
        subdirs[:] = [name for name in subdirs if name != '__MACOSX']
        for filename in filenames:
            if not filename.casefold().endswith('.pdf') or filename.startswith('._'):
                continue
            path = Path(directory) / filename
            code = project_code_from_path(path)
            if not code:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            by_size[size].append((path, code, document_type(filename)))
            scanned += 1

    candidates = []
    for size, records in by_size.items():
        if len({record[1] for record in records}) > 1:
            candidates.extend((path, size, code, kind) for path, code, kind in records)
    print(f'Found {scanned:,} PDFs; hashing {len(candidates):,} cross-project same-size candidates.', flush=True)

    digests: dict[str, list[dict]] = defaultdict(list)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for number, (digest, size, code, kind, path, error) in enumerate(pool.map(file_hash, candidates), 1):
            if digest:
                digests[digest].append({
                    'projectCode': code, 'documentType': kind,
                    'filename': path.name, 'sizeBytes': size,
                    'sourcePath': str(path),
                })
            if number % 2000 == 0:
                print(f'Hashed {number:,} candidates.', flush=True)

    metadata = project_metadata()
    cloud_links = cloudflare_links_by_sha_and_code()
    groups = []
    for digest, files in digests.items():
        by_project: dict[str, list[dict]] = defaultdict(list)
        for record in files:
            by_project[record['projectCode']].append(record)
        if len(by_project) < 2:
            continue
        projects = []
        for code, project_files in sorted(by_project.items()):
            info = metadata.get(code, {
                'projectCode': code, 'source': 'Proposal' if '-PROPOSAL-' in code else 'Senate HGAB',
                'title': code, 'region': None, 'office': None,
            })
            linked_rows = info.get('linkedRows')
            def linked_files():
                output = []
                for file in project_files:
                    urls = []
                    if info.get('source') == 'Proposal':
                        urls = [link for link in info.get('documentLinks', [])
                                if link.get('url') and filename_key(link['url']) == filename_key(file['filename'])]
                    else:
                        urls = cloud_links.get((digest, code), [])
                    if urls:
                        for link in urls:
                            output.append({
                                'documentType': file['documentType'],
                                'filename': file['filename'],
                                'sourceUrl': link.get('url'),
                                'linkLabel': 'Open source PDF',
                                'sourcePath': file['sourcePath'],
                            })
                    else:
                        output.append({
                            'documentType': file['documentType'],
                            'filename': file['filename'],
                            'sourceUrl': None,
                            'linkLabel': None,
                            'sourcePath': file['sourcePath'],
                        })
                return output
            if linked_rows:
                rows = list(linked_rows.values())
                projects.append({
                    'projectCode': code, 'source': 'Senate HGAB',
                    'title': rows[0]['title'] if len(rows) == 1 else None,
                    'linkedRows': rows,
                    'files': linked_files(),
                })
            else:
                projects.append({
                    **{key: value for key, value in info.items() if key != 'linkedRows'},
                    'files': linked_files(),
                })
        online_copies = [
            (file.get('sourceUrl'), project.get('projectCode'))
            for project in projects for file in project['files'] if file.get('sourceUrl')
        ]
        if online_copies:
            shared_url, shared_code = online_copies[0]
            for project in projects:
                for file in project['files']:
                    if not file.get('sourceUrl'):
                        file['sourceUrl'] = shared_url
                        file['linkLabel'] = 'Open byte-identical PDF'
                        file['linkProjectCode'] = shared_code
                    file.pop('sourcePath', None)
        else:
            source_path = next((file.get('sourcePath') for project in projects
                                for file in project['files'] if file.get('sourcePath')), None)
            shared_url = None
            if source_path:
                target_dir = OUT.parent / 'reused-document-files'
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f'{digest}.pdf'
                if not target.exists():
                    shutil.copyfile(source_path, target)
                shared_url = f'reused-document-files/{digest}.pdf'
            for project in projects:
                for file in project['files']:
                    file.pop('sourcePath', None)
                    file['sourceUrl'] = shared_url
                    file['linkLabel'] = 'Open shared T5 copy' if shared_url else None
        groups.append({
            'sha256': digest,
            'sizeBytes': files[0]['sizeBytes'],
            'documentTypes': sorted({file['documentType'] for file in files}),
            'projects': projects,
        })

    groups.sort(key=lambda group: (
        0 if 'Photos' in group['documentTypes'] else 1,
        group['documentTypes'][0], -len(group['projects']), group['sha256'],
    ))
    by_type = {}
    for kind in sorted({kind for group in groups for kind in group['documentTypes']}):
        matching = [group for group in groups if kind in group['documentTypes']]
        by_type[kind] = {
            'duplicateContentGroups': len(matching),
            'projectAssignments': sum(len(group['projects']) for group in matching),
        }
    by_source = {'Proposal-only groups': 0, 'Senate-HGAB-only groups': 0, 'Cross-stage groups': 0}
    for group in groups:
        sources = {project.get('source') for project in group['projects']}
        if sources == {'Proposal'}:
            by_source['Proposal-only groups'] += 1
        elif sources == {'Senate HGAB'}:
            by_source['Senate-HGAB-only groups'] += 1
        elif {'Proposal', 'Senate HGAB'} <= sources:
            by_source['Cross-stage groups'] += 1
    result = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'method': ('Exact SHA-256 equality of cached PDF bytes. A group is shown only when the same bytes occur under at least two distinct project-code directories. '
                   'macOS AppleDouble sidecars are excluded. A match establishes identical cached file content, not that the same scope was funded or built.'),
        'scannedPdfFiles': scanned,
        'hashedCrossProjectSizeCandidates': len(candidates),
        'duplicateContentGroups': len(groups),
        'byDocumentType': by_type,
        'bySourceStage': by_source,
        'groups': groups,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return {key: value for key, value in result.items() if key != 'groups'}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
