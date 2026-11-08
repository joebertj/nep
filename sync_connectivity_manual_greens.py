#!/usr/bin/env python3
"""Fetch private manual connectivity annotations from the ODV server."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output' / 'connectivity-manual-greens.json'
REMOTE_USER = os.environ.get('NEP_DEPLOY_USER', 'joebert')
REMOTE_HOST = os.environ.get('NEP_DEPLOY_HOST', '165.245.186.194')
REMOTE_DIR = os.environ.get('NEP_DEPLOY_DIR', '/home/joebert/open-data-visualization')
IDENTITY = os.environ.get('NEP_SSH_IDENTITY', str(Path.home() / '.ssh' / 'klti'))


def main() -> None:
    command = [
        'ssh', '-i', IDENTITY, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
        '-o', 'StrictHostKeyChecking=accept-new', f'{REMOTE_USER}@{REMOTE_HOST}',
        f"if [ -f '{REMOTE_DIR}/.connectivity-manual-greens.json' ]; then cat '{REMOTE_DIR}/.connectivity-manual-greens.json'; else printf '%s\\n' '{{\"schemaVersion\":1,\"projects\":{{}}}}'; fi",
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    document = json.loads(result.stdout)
    if document.get('schemaVersion') != 1 or not isinstance(document.get('projects'), dict):
        raise SystemExit('Server returned an unexpected manual-green JSON schema; local file was not changed.')
    valid = {'near-produce', 'closes-loop', 'extends-road', 'near-school', 'near-health-center', 'near-hospital'}
    for project_id, record in document['projects'].items():
        if not isinstance(project_id, str) or not isinstance(record, dict):
            raise SystemExit('Server JSON contains an invalid project record; local file was not changed.')
        record['greenReasons'] = sorted({reason for reason in record.get('greenReasons', record.get('reasons', [])) if reason in valid})
        record['greenNote'] = str(record.get('greenNote') or '')[:2000]
        record['redReason'] = str(record.get('redReason') or '')[:2000]
    temporary = OUT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(OUT)
    print(f'Synced {len(document["projects"]):,} manually flagged FMR projects to {OUT}')
    print('Run build_connectivity_report.py to merge these private annotations into the shared connectivity dataset.')


if __name__ == '__main__':
    main()
