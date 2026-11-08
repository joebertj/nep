#!/usr/bin/env python3
"""Audit PDF/document statistics against the Cloudflare manifest and T5 hash reconciliation."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'

PAGE_BUILDERS = {
    'dpwh.html': 'build_dpwh_indepth.py',
    'dpwh-transparency.html': 'build_dpwh_transparency_page.py',
    'cost-per-unit.html': 'build_cost_per_unit_page.py',
    'pccp-cost-per-unit.html': 'build_pccp_cost_per_unit_page.py',
    'expectation-vs-reality.html': 'build_expectation_vs_reality.py',
    'development-council.html': 'build_development_council.py',
    'undocumented-hgab.html': 'build_undocumented_hgab.py',
    'pow.html': 'build_pow_page.py',
    'summary.html': 'build_investigation_summary.py',
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def fail(errors, code, detail):
    errors.append({'code': code, 'detail': detail})


def audit():
    errors, warnings, checks, pages = [], [], {}, {}
    scan_path = OUT / 'senate_supporting_documents_hgab_only_scan.json'
    scan = read_json(scan_path)
    stats = read_json(OUT / 'senate-hgab-only-document-stats.json')
    projects = scan.get('projects') or []
    ids = [p.get('hgabId') for p in projects]
    matched_ids = {p.get('hgabId') for p in projects if p.get('hasAtLeastOneTitleMatchedDocument')}
    denominator = len(projects)
    matched = len(matched_ids)
    counts = {
        'denominatorProjectRows': denominator,
        'projectsWithAtLeastOneMatchedDocument': matched,
        'projectRowsWithoutMatchedDocument': denominator - matched,
        'matchedFileRecords': sum(int(p.get('matchedDocumentFileRecords') or 0) for p in projects),
    }
    duplicate_ids = len(ids) - len(set(ids))
    if duplicate_ids:
        fail(errors, 'duplicate-scan-project-ids', f'{duplicate_ids} duplicate project IDs')
    for key, value in counts.items():
        if scan.get(key) != value or stats.get(key) != value:
            fail(errors, 'scan-summary-mismatch', f'{key}: recomputed={value}, scan={scan.get(key)}, stats-copy={stats.get(key)}')
    stats_by_id = {p.get('hgabId'): p for p in stats.get('projects', [])}
    scan_by_id = {p.get('hgabId'): p for p in projects}
    if stats.get('byType') != scan.get('byType') or set(stats_by_id) != set(scan_by_id):
        fail(errors, 'scan-copy-diverged', 'the published stats copy has a different cohort or per-type totals')
    else:
        def signatory_facts(row):
            return sorted((str(p.get('name') or ''), str(p.get('role') or ''),
                           tuple(p.get('sourcePages') or []), tuple(p.get('documentTypes') or []))
                          for p in row.get('signatories', []))
        for project_id, source_row in scan_by_id.items():
            copy_row = stats_by_id[project_id]
            for key in ('hasAtLeastOneTitleMatchedDocument', 'matchedDocumentFileRecords', 'documentTypes'):
                if copy_row.get(key) != source_row.get(key):
                    fail(errors, 'scan-project-copy-diverged', f'{project_id}: {key}')
                    break
            if signatory_facts(copy_row) != signatory_facts(source_row):
                fail(errors, 'scan-project-signatories-diverged', project_id)
    checks['senateScan'] = {**counts, 'generatedAtUtc': scan.get('generatedAtUtc'), 'uniqueProjectIds': len(set(ids))}

    t5_audit = read_json(OUT / 't5-cloudflare-manifest-audit.json')
    t5_status = t5_audit.get('statusCounts') or {}
    t5_present = sum(int(t5_status.get(key, 0)) for key in
                     ('verified', 'verified_alternate_path', 'verified_attachment_cache'))
    t5_reconciliation = scan.get('t5CloudflareReconciliation') or {}
    if t5_reconciliation.get('manifestEntries') != t5_audit.get('manifestEntries'):
        fail(errors, 't5-manifest-count-mismatch',
             f"scan={t5_reconciliation.get('manifestEntries')}, audit={t5_audit.get('manifestEntries')}")
    if t5_reconciliation.get('manifestFilesPresentOnT5') != t5_present:
        fail(errors, 't5-present-count-mismatch',
             f"scan={t5_reconciliation.get('manifestFilesPresentOnT5')}, hash-audit={t5_present}")
    scanned_pdfs = sum(int(item.get('filesScanned') or 0) for item in scan.get('byType', {}).values())
    available_pdfs = int(t5_reconciliation.get('pdfFilesAvailable') or 0)
    if scanned_pdfs != available_pdfs:
        fail(errors, 'manifest-pdf-parse-count-mismatch',
             f'parsed={scanned_pdfs}, present-on-T5={available_pdfs}')
    checks['t5CloudflareManifest'] = {
        'manifestEntries': t5_audit.get('manifestEntries'),
        'presentAndHashVerified': t5_present,
        'missingFromT5': t5_status.get('missing', 0),
        'attachmentCacheCopies': t5_status.get('verified_attachment_cache', 0),
        'pdfFilesPresentOnT5': available_pdfs,
        'pdfFilesScanned': scanned_pdfs,
    }

    status_path = OUT / 'senate_supporting_document_scan_status.json'
    status = read_json(status_path) if status_path.exists() else {}
    live_count = status.get('projectsWithAtLeastOneMatchedDocument')
    if status.get('status') == 'error':
        warnings.append({'code': 'scanner-or-refresh-error',
                         'detail': status.get('lastError') or status.get('pageRefreshStatus') or 'scanner reports an error'})
    if status.get('status') == 'idle' and live_count != matched:
        warnings.append({'code': 'scanner-status-stale',
                         'detail': f'idle status says {live_count}; consolidated report says {matched}. The consolidated JSON is the page source of truth.'})
    checks['scannerStatus'] = {'status': status.get('status'), 'matchedProjectRows': live_count,
                               'matchesConsolidatedOutput': live_count == matched}

    only = read_json(OUT / 'hgab-only-document-coverage.json')
    only_rows = only.get('projects') or []
    only_ids = {p.get('hgabId') for p in only_rows}
    if only.get('denominatorProjectRows') != denominator or only_ids != set(ids):
        fail(errors, 'hgab-only-coverage-cohort-mismatch',
             f'scan has {denominator} rows; coverage has {len(only_rows)} rows / {len(only_ids)} IDs')
    scan_by_id = {p.get('hgabId'): p for p in projects}
    for row in only_rows:
        scanned = scan_by_id.get(row.get('hgabId'))
        if scanned and bool(row.get('senateHgabDocumentsMatched')) != bool(scanned.get('hasAtLeastOneTitleMatchedDocument')):
            fail(errors, 'hgab-only-row-match-mismatch', row.get('hgabId'))

    all_hgab = read_json(OUT / 'hgab-document-coverage.json')
    all_rows = all_hgab.get('projects') or []
    all_ids = [p.get('hgabId') for p in all_rows]
    all_match = sum(bool(p.get('proposalDocumentsMatched') or p.get('senateHgabDocumentsMatched')) for p in all_rows)
    all_proposal = sum(bool(p.get('proposalDocumentsMatched')) for p in all_rows)
    all_senate = sum(bool(p.get('senateHgabDocumentsMatched')) for p in all_rows)
    if len(all_rows) != all_hgab.get('denominatorProjectRows') or len(all_ids) != len(set(all_ids)):
        fail(errors, 'all-hgab-coverage-shape', 'all-HGAB export denominator or unique-row contract failed')
    all_by_id = {p.get('hgabId'): p for p in all_rows}
    for project_id in matched_ids:
        row = all_by_id.get(project_id)
        if row is None or not row.get('senateHgabDocumentsMatched'):
            fail(errors, 'all-hgab-senate-match-missing', project_id)
    checks['allHgabCoverage'] = {'rows': len(all_rows), 'withProposal': all_proposal,
                                 'withSenate': all_senate, 'union': all_match,
                                 'generatedAtUtc': all_hgab.get('generatedAtUtc')}

    indepth = read_json(OUT / 'dpwh-in-depth-data.json')
    support = indepth.get('senateSupportingDocumentCoverage') or {}
    for key in ('denominatorProjectRows', 'projectsWithAtLeastOneMatchedDocument',
                'projectRowsWithoutMatchedDocument', 'matchedFileRecords', 'byType'):
        if support.get(key) != scan.get(key):
            fail(errors, 'dpwh-support-summary-mismatch', f'{key}: DPWH={support.get(key)!r}, scan={scan.get(key)!r}')
    title_stats = indepth.get('senateDocumentTitleCoverage') or {}
    pow_summary = indepth.get('hgabPowSummary') or {}
    if pow_summary.get('titleMatchAssessedFiles') != pow_summary.get('titleScanDocuments'):
        fail(errors, 'pow-title-assessment-count-mismatch',
             f"assessed={pow_summary.get('titleMatchAssessedFiles')}, scanned={pow_summary.get('titleScanDocuments')}")
    checks['parsedPow'] = {'parsedDocuments': pow_summary.get('parsedDocuments'),
                           'titleScanDocuments': pow_summary.get('titleScanDocuments'),
                           'titleMatchAssessedFiles': pow_summary.get('titleMatchAssessedFiles'),
                           'titleMatchesHGABOnly': title_stats.get('combinedMatchedProjectRows'),
                           'titleMatchDenominator': title_stats.get('denominatorProjectRows')}

    undoc = read_json(STATIC / 'undocumented-hgab-data.json')
    ud_projects = []
    for name in undoc.get('projectShards', []):
        ud_projects.extend(read_json(STATIC / name))
    ud_ids = [p.get('id') for p in ud_projects]
    hgab_only_set = set(ids)
    outside = set(ud_ids) - hgab_only_set
    if outside:
        fail(errors, 'undocumented-cohort-leak', f'{len(outside)} queue rows have selected NEP counterparts')
    if len(ud_projects) != undoc.get('summary', {}).get('noDocumentProjects'):
        fail(errors, 'undocumented-project-count-mismatch',
             f"shards={len(ud_projects)}, summary={undoc.get('summary', {}).get('noDocumentProjects')}")
    checks['undocumented'] = {'queueRows': len(ud_projects), 'uniqueRows': len(set(ud_ids)),
                              'allRowsHgabOnly': not outside,
                              'coverageExportRows': len(only_rows)}

    expected_columns = ['HGAB code', 'Project', 'Office · region', 'HGAB allocation',
                        'Proposal docs', 'Senate HGAB docs', 'Signatories in related documents']
    shared_renderer = (ROOT / 'project_documents/hgab-document-coverage.js').read_text(encoding='utf-8')
    shared_renderer_path = STATIC / 'hgab-document-coverage.js'
    if not shared_renderer_path.exists() or shared_renderer_path.read_text(encoding='utf-8') != shared_renderer:
        fail(errors, 'coverage-renderer-not-shared', 'Published page renderer differs from the shared coverage module')
    for page_name in ('dpwh.html', 'undocumented-hgab.html'):
        html = (STATIC / page_name).read_text(encoding='utf-8')
        marker = 'id="all-hgab-document-coverage"'
        start = html.find(marker)
        end = html.find('</section>', start)
        section = html[start:end] if start >= 0 and end >= 0 else ''
        header = re.search(r'<thead>(.*?)</thead>', section, re.S)
        columns = [re.sub(r'<[^>]+>', '', x).strip() for x in re.findall(r'<th\b[^>]*>(.*?)</th>', header.group(1), re.S)] if header else []
        if columns != expected_columns:
            fail(errors, 'coverage-table-columns', f'{page_name}: {columns!r}')
        if 'data-report-table-exempt="true"' not in section:
            fail(errors, 'coverage-table-column-compaction',
                 f'{page_name}: shared table script is not instructed to preserve all seven columns')
        if 'hgab-only-document-coverage.json' not in html and page_name == 'undocumented-hgab.html':
            fail(errors, 'undocumented-export-link-missing', page_name)
        source = ('hgab-document-coverage.json' if page_name == 'dpwh.html'
                  else 'hgab-only-document-coverage.json')
        if 'hgab-document-coverage.js?v=' not in html or f'data-hgab-coverage-source="{source}' not in html:
            fail(errors, 'coverage-renderer-config', f'{page_name}: shared renderer or expected dataset source missing')
        pages[page_name] = {'coverageColumns': len(columns),
                            'loadsCoverageRenderer': 'hgab-document-coverage.js?v=' in html,
                            'coverageSource': source}

    builder_violations = []
    for page_name, builder_name in PAGE_BUILDERS.items():
        builder_path = ROOT / builder_name
        page_path = STATIC / page_name
        if not builder_path.exists() or not page_path.exists():
            builder_violations.append(f'{page_name}: missing page or builder {builder_name}')
            continue
        source = builder_path.read_text(encoding='utf-8')
        if page_name not in source:
            builder_violations.append(f'{builder_name}: no explicit owner reference for {page_name}')
        pages.setdefault(page_name, {})['builder'] = builder_name
        pages[page_name]['builtAtUtc'] = datetime.fromtimestamp(page_path.stat().st_mtime).astimezone().isoformat()
    if builder_violations:
        fail(errors, 'page-builder-ownership', '; '.join(builder_violations))
    summary_builder = (ROOT / 'build_investigation_summary.py').read_text(encoding='utf-8')
    summary_html_targets = re.findall(
        r"\bSTATIC\s*/\s*['\"]([^'\"]+\.html)['\"]", summary_builder)
    foreign_targets = sorted({name for name in summary_html_targets if name != 'summary.html'})
    if foreign_targets:
        fail(errors, 'summary-builder-cross-page-write',
             'summary builder writes non-owned HTML pages: ' + ', '.join(foreign_targets))
    module_source = (ROOT / 'report_page_modules.py').read_text(encoding='utf-8')
    if 'def apply_page_modules(html, page):' not in module_source:
        fail(errors, 'page-module-interface-missing', 'owner builders cannot apply shared sections in memory')
    checks['encapsulation'] = {
        'summaryWritesOnlyOwnPage': 'summary-builder-cross-page-write' not in {e['code'] for e in errors},
        'summaryHtmlTargets': sorted(set(summary_html_targets)),
    }
    checks['pageOwnership'] = PAGE_BUILDERS

    pow_page = (STATIC / 'pow.html').read_text(encoding='utf-8')
    pow_data = read_json(STATIC / 'pow-hgab-parsed-documents.json')
    pow_summary = pow_data.get('summary', {})
    if 'id="senate-hgab-parsed-pows"' not in pow_page or 'pow-hgab-parsed-documents.js?v=' not in pow_page:
        fail(errors, 'senate-pow-page-section', 'POW page is missing its Senate HGAB parsed-results table or loader')
    if len(pow_data.get('documents', [])) != pow_summary.get('parsedDocuments'):
        fail(errors, 'senate-pow-export-count', 'POW page export row count does not match parsed-document count')
    checks['senatePowPage'] = {
        'parsedDocuments': pow_summary.get('parsedDocuments'),
        'billRows': pow_summary.get('billRows'),
        'uniqueMatchedHgabProjectRows': pow_summary.get('uniqueMatchedHgabProjectRows'),
        'loadsParsedResults': 'pow-hgab-parsed-documents.js?v=' in pow_page,
    }

    scan_mtime = scan_path.stat().st_mtime
    relevant_pages = ['dpwh.html', 'undocumented-hgab.html', 'summary.html', 'cost-per-unit.html',
                      'pccp-cost-per-unit.html', 'expectation-vs-reality.html', 'development-council.html',
                      'pow.html']
    stale_pages = [name for name in relevant_pages if (STATIC / name).stat().st_mtime < scan_mtime]
    if stale_pages:
        fail(errors, 'pages-older-than-scan', ', '.join(stale_pages))
    checks['pageFreshness'] = {'sourceScanGeneratedAtUtc': scan.get('generatedAtUtc'),
                               'pagesAtOrAfterScan': len(relevant_pages) - len(stale_pages),
                               'pagesExpected': len(relevant_pages), 'stalePages': stale_pages}

    result = {'status': 'failed' if errors else 'ok_with_warnings' if warnings else 'ok', 'checkedAtUtc': datetime.now().astimezone().isoformat(),
              'source': 'Cloudflare manifest SHA-256 reconciliation across the T5 source folder and parser attachment cache, plus page outputs.',
              'checks': checks, 'pages': pages, 'warnings': warnings, 'errors': errors}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'document-page-stats-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--strict', action='store_true', help='exit nonzero if any check fails')
    args = parser.parse_args()
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.strict and result['errors']:
        raise SystemExit(1)
