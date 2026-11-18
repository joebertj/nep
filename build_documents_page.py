#!/usr/bin/env python3
"""Build the all-stage FY2027 DPWH document inventory and coverage page."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
TEMPLATE = ROOT / 'report_assets/documents_page_template.html'
TYPES = [
    'POW', 'BP 202', 'Development Council', 'Geotagged photos',
    'Certificate of Implementability', 'Other / unclassified',
]


def normalize(value: str) -> str:
    key = str(value or '').strip().casefold()
    if key in {'pow', 'program of works', 'program of work'}:
        return 'POW'
    if key in {'bp 202', 'bp202'}:
        return 'BP 202'
    if key in {'development council', 'rdc', 'pdc', 'ldc', 'rdc endorsement',
                'pdc endorsement', 'ldc endorsement', 'development council endorsement'}:
        return 'Development Council'
    if key in {'photos', 'photo', 'geotagged photos', 'geotagged photo',
                'geotegged photo', 'g.photo'}:
        return 'Geotagged photos'
    if key in {'certificate', 'certificate of implementability',
                'implementability certificate', 'cert of implementability'}:
        return 'Certificate of Implementability'
    return 'Other / unclassified'


def build_data() -> dict:
    coverage = json.loads((OUT / 'hgab-document-coverage.json').read_text(encoding='utf-8'))
    proposal_index = json.loads((STATIC / 'dpwh-in-depth-data.json').read_text(encoding='utf-8'))
    stage_counts = {
        stage: {kind: {'matchedFiles': 0} for kind in TYPES}
        for stage in ('Proposal', 'Senate HGAB')
    }
    proposal_project_ids = defaultdict(set)
    matched_house_ids = {stage: defaultdict(set) for stage in stage_counts}
    stage_file_ids = {stage: defaultdict(set) for stage in stage_counts}

    for shard in proposal_index.get('arrayShards', {}).get('projects', []):
        projects = json.loads((STATIC / shard['path']).read_text(encoding='utf-8'))
        for project in projects:
            seen = set()
            # documentLinks is the full published Proposal archive inventory.
            # `documents` is the smaller parser snapshot and misses linked types
            # such as BP 202 and Certificate of Implementability.
            for document in project.get('documentLinks') or []:
                kind = normalize(document.get('type'))
                url = document.get('url')
                if not url:
                    continue
                key = (project.get('code'), kind, url)
                stage_file_ids['Proposal'][kind].add(key)
                seen.add(kind)
            for kind in seen:
                proposal_project_ids[kind].add(project.get('code'))

    matched_counts = {
        stage: {kind: {'houseRows': 0} for kind in TYPES}
        for stage in ('Proposal', 'Senate HGAB')
    }
    complete_histogram = [0] * 6
    proposal_complete = senate_complete = both_complete = 0
    for row in coverage.get('projects', []):
        hgab_id = str(row.get('hgabId') or '')
        per_stage = {}
        for stage, source_key in (('Proposal', 'proposalDocumentTypes'),
                                  ('Senate HGAB', 'senateDocumentTypes')):
            kinds = {normalize(value) for value in row.get(source_key) or []}
            per_stage[stage] = kinds
            for kind in kinds:
                matched_counts[stage][kind]['houseRows'] += 1
                matched_house_ids[stage][kind].add(hgab_id)
            if stage == 'Senate HGAB':
                for document in row.get('senateDocuments') or []:
                    kind = normalize(document.get('documentType'))
                    identity = document.get('fileLinkId')
                    if identity is None:
                        identity = document.get('documentId') or document.get('url')
                    if identity is not None:
                        stage_file_ids[stage][kind].add(str(identity))
        union = per_stage['Proposal'] | per_stage['Senate HGAB']
        named = {'POW', 'BP 202', 'Development Council', 'Geotagged photos', 'Certificate of Implementability'}
        count = len(union & named)
        complete_histogram[count] += 1
        proposal_complete += len(per_stage['Proposal'] & named) >= 4
        senate_complete += len(per_stage['Senate HGAB'] & named) >= 4
        both_complete += len(union & named) >= 4

    for stage in stage_counts:
        for kind in TYPES:
            stage_counts[stage][kind]['matchedFiles'] = len(stage_file_ids[stage][kind])
            stage_counts[stage][kind]['projectFolders'] = len(proposal_project_ids[kind]) if stage == 'Proposal' else None
            matched_counts[stage][kind]['houseRows'] = len(matched_house_ids[stage][kind])

    expected = int(coverage.get('denominatorProjectRows') or 0)
    if len(coverage.get('projects', [])) != expected:
        raise ValueError('HGAB coverage rows do not match the stated denominator')
    data = {
        'generatedAtUtc': coverage.get('generatedAtUtc'),
        'proposalGeneratedAtUtc': proposal_index.get('generatedAtUtc'),
        'scope': coverage.get('scope'),
        'denominatorProjectRows': expected,
        'stageCounts': stage_counts,
        'houseRowTypeCounts': matched_counts,
        'complete': {
            'threshold': 'At least 4 of 5 named types',
            'unionCompleteRows': both_complete,
            'unionCompletePct': round(100 * both_complete / max(1, expected), 2),
            'proposalCompleteRows': proposal_complete,
            'senateCompleteRows': senate_complete,
            'typeCountHistogram': complete_histogram,
            'namedTypes': ['POW', 'BP 202', 'Development Council', 'Geotagged photos',
                           'Certificate of Implementability'],
        },
        'method': coverage.get('method'),
        'proposalScope': proposal_index.get('scope'),
        'proposalProjectCount': proposal_index.get('projectCount'),
        'senateFileIndex': coverage.get('senateDocumentFileLinkIndex'),
    }
    return data


def build() -> dict:
    data = build_data()
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    (STATIC / 'documents-data.json').write_text(payload, encoding='utf-8')
    (OUT / 'documents-data.json').write_text(payload, encoding='utf-8')
    page = TEMPLATE.read_text(encoding='utf-8')
    version = hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]
    page = page.replace('documents-data.json', f'documents-data.json?v={version}')
    from uniform_report_menu import apply_page as uniform_menu
    page = uniform_menu(page, 'documents.html')
    (STATIC / 'documents.html').write_text(page, encoding='utf-8')
    (OUT / 'documents.html').write_text(page, encoding='utf-8')
    return {'page': 'documents.html', 'denominatorProjectRows': data['denominatorProjectRows'],
            'completeRows': data['complete']['unionCompleteRows'],
            'completePct': data['complete']['unionCompletePct'],
            'proposalProjects': data['proposalProjectCount']}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
