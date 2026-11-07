"""Summarize read-only Senate document title scans for HGAB-only project rows."""
import json
from pathlib import Path


def load_coverage(analysis_output: Path):
    """Return type-level and combined distinct-project counts from scan reports."""
    reports = {}
    matched = {}
    exact = {}
    for kind, filename in (
        ('pow', 'senate_pow_hgab_only_title_scan.json'),
        ('bp202', 'senate_bp202_hgab_only_title_scan.json'),
    ):
        path = analysis_output / filename
        if not path.is_file():
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        records = report.get('records', [])
        exact_ids = {h for r in records if r.get('matchStatus') == 'exact_title_match'
                     for h in r.get('matchedHgabIds', [])}
        accepted_ids = {h for r in records if r.get('matchStatus') in {'exact_title_match', 'relaxed_title_match'}
                        for h in r.get('matchedHgabIds', [])}
        reports[kind] = report
        matched[kind] = accepted_ids
        exact[kind] = exact_ids
    if not reports:
        return None
    denominator = max(int(r.get('hgabOnlyProjectRows') or 0) for r in reports.values())
    rows = {}
    for kind, report in reports.items():
        ids = matched.get(kind, set())
        exact_ids = exact.get(kind, set())
        rows[kind] = {
            'documentsScanned': int(report.get('senateDocumentsScanned') or 0),
            'exactMatchedDocuments': int(report.get('exactlyMatchedDocuments') or 0),
            'relaxedMatchedDocuments': int(report.get('relaxedMatchedDocuments') or 0),
            'matchedProjectRows': len(ids),
            'exactMatchedProjectRows': len(exact_ids),
            'coveragePct': round(100 * len(ids) / denominator, 2) if denominator else 0,
            'generatedAtUtc': report.get('generatedAtUtc'),
        }
    combined_ids = set().union(*matched.values()) if matched else set()
    exact_union = set().union(*exact.values()) if exact else set()
    return {
        'denominatorProjectRows': denominator,
        'byType': rows,
        'combinedMatchedProjectRows': len(combined_ids),
        'combinedExactMatchedProjectRows': len(exact_union),
        'combinedCoveragePct': round(100 * len(combined_ids) / denominator, 2) if denominator else 0,
        'combinedExactCoveragePct': round(100 * len(exact_union) / denominator, 2) if denominator else 0,
        'method': 'Read-only first-page native PDF title scan. Counts distinct HGAB-only project rows; BP 202 and POW source sets are deduplicated in the combined figure. Exact normalized title matches and conservative relaxed POW-title candidates are counted; this is a preliminary file-presence signal, not content verification.',
    }


def load_match_ids(analysis_output: Path, *, include_relaxed=False):
    """Map HGAB ledger IDs to Senate document types and file codes.

    Exact title matches are used for file-presence coverage. Relaxed matches
    can be included for supplementary, clearly labeled candidate statistics.
    """
    statuses = {'exact_title_match'}
    if include_relaxed:
        statuses.add('relaxed_title_match')
    result = {}
    for kind, filename in (
        ('pow', 'senate_pow_hgab_only_title_scan.json'),
        ('bp202', 'senate_bp202_hgab_only_title_scan.json'),
    ):
        path = analysis_output / filename
        if not path.is_file():
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        for record in report.get('records', []):
            if record.get('matchStatus') not in statuses:
                continue
            identity = (kind, record.get('projectCode'))
            for hgab_id in record.get('matchedHgabIds', []):
                result.setdefault(hgab_id, set()).add(identity)
    return result
