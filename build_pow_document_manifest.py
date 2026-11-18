#!/usr/bin/env python3
"""Publish a file-level Proposal and Senate HGAB inventory with SHA-256."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
ATTACHMENTS = ROOT / 'data_sources/dpwh_project_documents/attachments'
SITE = ROOT.parent / 'open-data-visualization/static/nep-preview'
INDEX = SITE / 'dpwh-in-depth-data.json'
HGAB_LINKS = ROOT / 'analysis_output/Cloudflare-file-links.jsonl'
PROPOSAL_DOWNLOADS = ATTACHMENTS / 'downloads.jsonl'
OUT = SITE / 'pow-document-manifest.json'
CODE_RE = re.compile(r'2027DPWH-(?:PROPOSAL|HGAB)-\d{5}', re.I)


def filename_key(value: str) -> str:
    raw = str(value or '')
    path = urlsplit(raw).path if '://' in raw else raw.split('?')[0]
    name = unquote(Path(path).name).casefold()
    name = re.sub(r'^[0-9a-f]{16}-', '', name)
    return re.sub(r'[^a-z0-9]', '', name)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def build() -> dict:
    records: list[dict] = []
    proposal_lookup: dict[tuple[str, str], list[dict]] = {}
    index = json.loads(INDEX.read_text(encoding='utf-8'))
    for shard in index.get('arrayShards', {}).get('projects', []):
        projects = json.loads((SITE / shard['path']).read_text(encoding='utf-8'))
        for project in projects:
            code = str(project.get('code') or '').upper()
            for item in project.get('documentLinks') or []:
                url = item.get('url')
                if not url:
                    continue
                row = {
                    'stage': 'Proposal', 'projectCode': code,
                    'documentType': item.get('type'),
                    'filename': unquote(Path(urlsplit(url).path).name), 'url': url,
                    'sha256': None,
                }
                proposal_lookup[(code, filename_key(url))] = row
                records.append(row)

    # Proposal download logs contain SHA-256 values computed during download.
    with PROPOSAL_DOWNLOADS.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            code = str(item.get('projectCode') or '').upper()
            url = item.get('url')
            if not url:
                continue
            row = proposal_lookup.get((code, filename_key(url)))
            if not row or not item.get('sha256'):
                continue
            digest = str(item['sha256']).lower()
            row['sha256'] = digest

    hgab_rows = {}
    with HGAB_LINKS.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            path = str(item.get('path') or '')
            code_match = next((m.group(0).upper() for part in path.split('/')
                               for m in CODE_RE.finditer(part)
                               if '-HGAB-' in m.group(0).upper()), None)
            if not code_match or not item.get('url'):
                continue
            hgab_rows[(code_match, item['url'])] = item
    for (code, url), item in hgab_rows.items():
        filename = unquote(Path(urlsplit(url).path).name)
        records.append({
            'stage': 'Senate HGAB', 'projectCode': code,
            'documentType': None, 'filename': filename, 'url': url,
            'sha256': item.get('sha256'),
        })

    records.sort(key=lambda r: (r['stage'], r['projectCode'], r['filename'], r['url']))
    proposal = [r for r in records if r['stage'] == 'Proposal']
    hgab = [r for r in records if r['stage'] == 'Senate HGAB']
    result = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'description': 'Public source-file inventory for FY2027 DPWH Proposal and Senate HGAB supporting PDFs. SHA-256 fingerprints identify exact file bytes; Proposal hashes are computed from cached PDFs, while HGAB hashes are from the BetterGovPH file-link ingestion catalog.',
        'counts': {
            'proposalFiles': len(proposal),
            'proposalFilesWithSha256': sum(bool(r.get('sha256')) for r in proposal),
            'proposalFilesWithoutCachedHash': sum(not r.get('sha256') for r in proposal),
            'hgabFiles': len(hgab),
            'hgabFilesWithSha256': sum(bool(r.get('sha256')) for r in hgab),
        },
        'files': records,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return {**result['counts'], 'output': str(OUT)}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
