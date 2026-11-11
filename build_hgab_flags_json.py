#!/usr/bin/env python3
"""Export one row per FY2027 HGAB project with existing flags and 5-type doc gaps."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
FLAG_DATA = OUT / 'flags-data.json'
LINE_ITEM_QUEUE = STATIC / 'line-item-review-queue.json'
COVERAGE_INDEX = OUT / 'hgab-document-coverage-index.json'
COVERAGE_SHARDS = OUT / 'hgab-document-coverage-shards'
NAMED_TYPES = (
    'POW',
    'BP 202',
    'Development Council',
    'Geotagged photos',
    'Certificate of Implementability',
)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def normalize_document_types(values):
    normalized = set()
    for value in values or []:
        key = str(value or '').strip().casefold()
        if key in {'pow', 'program of works', 'program of work'}:
            normalized.add('POW')
        elif key in {'bp 202', 'bp202'}:
            normalized.add('BP 202')
        elif key in {
            'development council',
            'rdc endorsement',
            'pdc endorsement',
            'ldc endorsement',
            'development council endorsement',
        }:
            normalized.add('Development Council')
        elif key in {
            'geotagged photos',
            'geotagged photo',
            'geotegged photo',
            'g.photo',
            'photo',
            'photos',
        }:
            normalized.add('Geotagged photos')
        elif key in {
            'certificate of implementability',
            'implementability certificate',
        }:
            normalized.add('Certificate of Implementability')
    return normalized


def build():
    flags_data = read(FLAG_DATA)
    line_item_queue = read(LINE_ITEM_QUEUE)
    coverage_index = read(COVERAGE_INDEX)
    shard_specs = coverage_index.get('_shardedJson', {}).get('collections', {}).get('projects', {}).get('files', [])
    if not shard_specs:
        raise ValueError('HGAB coverage index has no project shards')

    coverage_rows = []
    for shard in shard_specs:
        shard_path = COVERAGE_SHARDS / Path(shard['file']).name
        coverage_rows.extend(read(shard_path).get('rows', []))
    expected = int(coverage_index.get('denominatorProjectRows') or 0)
    if len(coverage_rows) != expected or len({row.get('hgabId') for row in coverage_rows}) != expected:
        raise ValueError(f'HGAB coverage did not reconcile to {expected:,} unique rows')

    review_flags = {
        row.get('id'): row
        for row in flags_data.get('projects', [])
        if row.get('stage') == 'HGAB 3rd-reading' and row.get('id')
    }
    queue_flags = {}
    for row in line_item_queue.get('rankedOccurrences', []):
        if row.get('recordType') not in {'DPWH HGAB 3rd-reading', 'HGAB 3rd-reading'}:
            continue
        hgab_id = row.get('hgabId')
        if not hgab_id:
            continue
        bucket = queue_flags.setdefault(hgab_id, [])
        for flag in row.get('flags') or []:
            if isinstance(flag, dict) and flag.get('label'):
                item = {
                    'label': flag['label'],
                    'evidence': flag.get('evidence') or '',
                    'source': 'Detailed line-item review queue',
                }
                if item not in bucket:
                    bucket.append(item)
    projects = []
    missing_type_counts = Counter()
    combined_flag_counts = Counter()
    rows_with_review_flags = 0
    rows_with_queue_flags = 0
    rows_with_missing_docs = 0
    rows_with_complete_docs = 0
    existing_review_flag_occurrences = 0

    for coverage in coverage_rows:
        hgab_id = coverage.get('hgabId')
        legacy = review_flags.get(hgab_id)
        existing = list(dict.fromkeys((legacy or {}).get('flagTypes') or []))
        detailed_flags = queue_flags.get(hgab_id, [])
        detailed_labels = list(dict.fromkeys(flag['label'] for flag in detailed_flags))
        existing = list(dict.fromkeys(existing + detailed_labels))
        proposal_types = normalize_document_types(coverage.get('proposalDocumentTypes'))
        senate_types = normalize_document_types(coverage.get('senateDocumentTypes'))
        present = proposal_types | senate_types
        missing = [doc_type for doc_type in NAMED_TYPES if doc_type not in present]
        document_type_details = {
            doc_type: {
                'matched': doc_type in present,
                'proposalMatched': doc_type in proposal_types,
                'senateHgabMatched': doc_type in senate_types,
            }
            for doc_type in NAMED_TYPES
        }
        missing_flags = [f'Missing {doc_type}' for doc_type in missing]
        all_flags = list(dict.fromkeys(existing + missing_flags))

        rows_with_review_flags += bool(existing)
        rows_with_queue_flags += bool(detailed_flags)
        existing_review_flag_occurrences += len(existing)
        rows_with_missing_docs += bool(missing)
        rows_with_complete_docs += len(present) >= 4
        missing_type_counts.update(missing)
        combined_flag_counts.update(all_flags)

        projects.append({
            'hgabId': hgab_id,
            'title': coverage.get('title') or '',
            'office': coverage.get('office') or '',
            'region': coverage.get('region') or '',
            'amountPesos': int(coverage.get('amountPesos') or 0),
            'flags': all_flags,
            'existingReviewFlags': existing,
            'detailedFlagEvidence': detailed_flags,
            'missingDocumentFlags': missing_flags,
            'reviewFlagMatch': legacy is not None or bool(detailed_flags),
            'flagsOverviewMatch': legacy is not None,
            'detailedQueueMatch': bool(detailed_flags),
            'documentCoverage': {
                'matchedNamedTypeCount': len(present),
                'requiredNamedTypeCount': len(NAMED_TYPES),
                'completeAtFourOfFive': len(present) >= 4,
                'missingDocumentTypes': missing,
                'types': document_type_details,
            },
        })

    projects.sort(key=lambda row: row['hgabId'])
    data = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'scope': 'One row per FY2027 HGAB 3rd-reading DPWH project row. Includes exact-ID review flags from the flags overview and detailed line-item review queue, plus missing-document flags for five named document types.',
        'method': (
            'Document presence combines linked Proposal document types (direct title matches or selected NEP counterparts) '
            'and Senate HGAB title-linked document types. Named types are POW, BP 202, Development Council, geotagged '
            'photos, and Certificate of Implementability. A document type is counted present if either source has a match; '
            'complete means at least four of five types are matched. Existing review flags combine the flags overview and '
            'the detailed line-item review queue, joined only by exact HGAB ID; 95 rows have no exact review-flag record '
            'in either source. FMR-only manual reviews are not assigned to HGAB rows because their keys identify separate '
            'FMR records and do not establish an HGAB line-item match. '
            'A missing match is not proof that a document does not exist, and file presence does not verify contents.'
        ),
        'denominatorProjectRows': expected,
        'completeDocumentThreshold': {'matchedTypes': 4, 'ofNamedTypes': len(NAMED_TYPES)},
        'sources': {
            'projectReviewFlags': 'Flags overview and detailed HGAB line-item review queue; exact HGAB ID joins only.',
            'proposalDocuments': 'Linked Proposal document coverage, including direct matches and selected NEP counterparts.',
            'senateDocuments': 'Senate-provided HGAB document title matches.',
            'reviewFlagsGeneratedAtUtc': flags_data.get('generatedAtUtc'),
            'lineItemReviewQueueGeneratedAtUtc': line_item_queue.get('generatedAtUtc'),
            'documentCoverageGeneratedAtUtc': coverage_index.get('generatedAtUtc'),
        },
        'summary': {
            'projectRows': expected,
            'rowsWithExistingReviewFlags': rows_with_review_flags,
            'rowsWithDetailedQueueFlags': rows_with_queue_flags,
            'rowsWithoutExactReviewFlagMatch': expected - sum(row['reviewFlagMatch'] for row in projects),
            'existingReviewFlagOccurrences': existing_review_flag_occurrences,
            'rowsWithAtLeastOneMissingNamedDocument': rows_with_missing_docs,
            'rowsWithAtLeastFourOfFiveNamedDocuments': rows_with_complete_docs,
            'missingDocumentFlagCounts': {name: missing_type_counts[name] for name in NAMED_TYPES},
            'combinedFlagCounts': dict(sorted(combined_flag_counts.items())),
        },
        'projects': projects,
    }
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    output_paths = (OUT / 'flags.json', STATIC / 'flags.json')
    for path in output_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding='utf-8')
    return {
        'outputs': [str(path) for path in output_paths],
        'bytes': len(serialized.encode('utf-8')),
        'sha256': hashlib.sha256(serialized.encode('utf-8')).hexdigest(),
        'summary': data['summary'],
    }


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False, indent=2))
