#!/usr/bin/env python3
"""Fetch private manual connectivity annotations from the ODV server."""
from __future__ import annotations

import json
import os
import re
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
    valid = {'near-produce', 'closes-loop', 'extends-road', 'road-segment', 'connects-road-segments', 'near-school', 'near-health-center', 'near-hospital'}
    valid_red = {'sizeable-private-property-connection', 'section2-visitor-venue', 'section2-subdivision-village', 'section2-large-residential-property', 'section2-restricted-access-property', 'section2-private-property-cue', 'section2-coordinate-quality', 'baywalk-shoreline-review'}
    segment_notes = {'segment of road', 'segment of a road', 'road segment', 'part of road segment', 'part of a road segment'}
    connects_notes = {'connects two segments', 'connects two road segments', 'connect two segments', 'connect two road segments', 'connects road segments'}
    normalized_notes = {'road-segment': 0, 'connects-road-segments': 0}
    empty_records_removed = 0
    for project_id, record in list(document['projects'].items()):
        if not isinstance(project_id, str) or not isinstance(record, dict):
            raise SystemExit('Server JSON contains an invalid project record; local file was not changed.')
        raw_reasons = record.get('greenReasons', record.get('reasons', []))
        if not isinstance(raw_reasons, list):
            raise SystemExit(f'Server JSON has invalid greenReasons for project {project_id}; local file was not changed.')
        reasons = {reason for reason in raw_reasons if isinstance(reason, str) and reason in valid}
        note = str(record.get('greenNote') or '').strip()
        normalized_note = re.sub(r'[^a-z0-9]+', ' ', note.casefold()).strip()
        if normalized_note in segment_notes:
            reasons.add('road-segment')
            note = ''
            normalized_notes['road-segment'] += 1
        elif normalized_note in connects_notes:
            reasons.add('connects-road-segments')
            note = ''
            normalized_notes['connects-road-segments'] += 1
        record['greenReasons'] = sorted(reasons)
        record['reasons'] = record['greenReasons']
        record['greenNote'] = note[:2000]
        raw_red_reasons = record.get('redReasons', [])
        if not isinstance(raw_red_reasons, list):
            raise SystemExit(f'Server JSON has invalid redReasons for project {project_id}; local file was not changed.')
        record['redReasons'] = sorted({reason for reason in raw_red_reasons if isinstance(reason, str) and reason in valid_red})
        record['redReason'] = str(record.get('redReason') or '')[:2000]
        if not record['greenReasons'] and not record['greenNote'] and not record['redReasons'] and not record['redReason']:
            del document['projects'][project_id]
            empty_records_removed += 1
    temporary = OUT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(OUT)
    print(f'Synced {len(document["projects"]):,} non-empty manual FMR flags; normalized notes: {normalized_notes}; removed {empty_records_removed} empty records.')
    print('Run build_connectivity_report.py to merge these private annotations into the shared connectivity dataset.')


if __name__ == '__main__':
    main()
