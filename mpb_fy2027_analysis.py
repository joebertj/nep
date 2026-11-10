"""Shared FY2027 MPB summaries used by the MPB page builders."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def build_fy2027_document_coverage(project_details=None):
    """Join MPB HGAB rows to reconciled Proposal and Senate document types."""
    mpb = json.loads((OUT / 'mpb_analysis.json').read_text(encoding='utf-8')) if project_details is None else None
    if project_details is None:
        project_details = mpb.get('coordinateProximity', {}).get('projectDetails', {})
    coverage = json.loads((STATIC / 'hgab-document-coverage.json').read_text(encoding='utf-8'))
    coverage_rows = coverage.get('projects', [])
    by_id = {str(row.get('hgabId') or ''): row for row in coverage_rows if row.get('hgabId')}
    if len(by_id) != len(coverage_rows):
        raise ValueError('HGAB document coverage contains missing or duplicate project IDs')
    if not project_details:
        raise ValueError('MPB analysis has no FY2027 HGAB project IDs')
    missing = sorted(set(project_details) - set(by_id))
    if missing:
        raise ValueError(f'{len(missing)} FY2027 MPB projects are absent from HGAB document coverage; refusing partial result')

    named_types = {
        'POW', 'BP 202', 'Development Council', 'Geotagged photos',
        'Certificate of Implementability',
    }

    def normalize_types(values):
        normalized = set()
        for value in values or []:
            key = str(value or '').strip().casefold()
            if key in {'pow', 'program of works', 'program of work'}:
                normalized.add('POW')
            elif key in {'bp 202', 'bp202'}:
                normalized.add('BP 202')
            elif key in {'development council', 'rdc endorsement', 'pdc endorsement',
                         'ldc endorsement', 'development council endorsement'}:
                normalized.add('Development Council')
            elif key in {'geotagged photos', 'geotagged photo', 'geotegged photo',
                         'g.photo', 'photo', 'photos'}:
                normalized.add('Geotagged photos')
            elif key in {'certificate of implementability', 'implementability certificate'}:
                normalized.add('Certificate of Implementability')
        return normalized

    counts = {count: 0 for count in range(len(named_types) + 1)}
    complete = proposal_complete = senate_complete = 0
    for hgab_id in project_details:
        row = by_id[hgab_id]
        proposal = normalize_types(row.get('proposalDocumentTypes')) & named_types
        senate = normalize_types(row.get('senateDocumentTypes')) & named_types
        combined = proposal | senate
        count = len(combined)
        counts[count] += 1
        complete += count >= 4
        proposal_complete += len(proposal) >= 4
        senate_complete += len(senate) >= 4

    total = len(project_details)
    return {
        'fiscalYear': 2027,
        'stage': 'HGAB 3rd reading',
        'source': 'MPB HGAB project IDs reconciled to all-HGAB Proposal and Senate document coverage by House ledger ID',
        'documentCoverageGeneratedAtUtc': coverage.get('generatedAtUtc'),
        'denominatorProjectRows': total,
        'completeDocumentProjectRows': complete,
        'completeDocumentProjectRowsPct': round(100 * complete / max(1, total), 2),
        'incompleteDocumentProjectRows': total - complete,
        'proposalCompleteDocumentProjectRows': proposal_complete,
        'senateCompleteDocumentProjectRows': senate_complete,
        'completeDocumentTypeThreshold': 4,
        'completeDocumentTypeNames': sorted(named_types),
        'countsByMatchedTypeCount': [
            {'matchedTypeCount': count, 'projectRows': counts[count],
             'projectRowsPct': round(100 * counts[count] / max(1, total), 2)}
            for count in range(len(named_types) + 1)
        ],
        'method': 'Each FY2027 MPB HGAB ledger row is joined by its House project ID. Proposal and Senate HGAB document types are combined and deduplicated. Complete means at least four of five named types: POW, BP 202, Development Council, geotagged photos, and Certificate of Implementability. Other document types are excluded. A title match or file presence does not verify document contents.',
    }


def build_fy2027_historical_distribution():
    """Return FY2027 title-history totals from the mapped barangay history."""
    base = json.loads((OUT / 'mpb-barangay-base-data.json').read_text(encoding='utf-8'))
    index = json.loads((OUT / 'mpb-barangay-index.json').read_text(encoding='utf-8'))
    new_title_matches = repeat_title_matches = 0
    new_title_allocation = repeat_title_allocation = 0
    current_barangays = first_time_barangays = 0
    for place in base.get('barangays', []):
        groups = place.get('buildings', [])
        place_years = [int(entry['year']) for group in groups for entry in group.get('levelHistory', [])]
        current_groups = []
        for group in groups:
            history = group.get('levelHistory', [])
            current_entries = [entry for entry in history if int(entry.get('year') or 0) == 2027]
            if not current_entries:
                continue
            current_groups.append(group)
            amount = sum(int(entry.get('amountPesos') or 0) for entry in current_entries)
            if any(int(entry.get('year') or 0) < 2027 for entry in history):
                repeat_title_matches += 1
                repeat_title_allocation += amount
            else:
                new_title_matches += 1
                new_title_allocation += amount
        if current_groups:
            current_barangays += 1
            if not any(year < 2027 for year in place_years):
                first_time_barangays += 1

    periods = index.get('periods', [])
    total_matches = new_title_matches + repeat_title_matches
    return {
        'fiscalYear': 2027,
        'stage': 'HGAB 3rd',
        'mappedProjectRows': int(next((p.get('linkedRows', 0) for p in periods if int(p.get('year', 0)) == 2027), 0)),
        'coveredBarangays': current_barangays,
        'historicalTitleMatches': total_matches,
        'newTitleMatches': new_title_matches,
        'repeatedTitleMatches': repeat_title_matches,
        'newTitleMatchSharePct': 100 * new_title_matches / max(1, total_matches),
        'repeatedTitleMatchSharePct': 100 * repeat_title_matches / max(1, total_matches),
        'newTitleAllocationPesos': new_title_allocation,
        'repeatedTitleAllocationPesos': repeat_title_allocation,
        'totalAllocationPesos': new_title_allocation + repeat_title_allocation,
        'firstTimeBarangays': first_time_barangays,
        'previouslyMappedBarangays': current_barangays - first_time_barangays,
        'firstTimeBarangaySharePct': 100 * first_time_barangays / max(1, current_barangays),
    }
