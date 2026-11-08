#!/usr/bin/env python3
"""Build an all-project contractor directory from ODV infrastructure sources."""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from build_contractors import (
    AMO_CACHE, MERCHANT_PARQUET, PCAB_CSV, SEC_DATABASE, TRANSPARENCY_PARQUET,
    export_parquet, mask_name_with_letter_hints, norm, transparency_contractor_entries,
    write_contractors_payload,
)
from uniform_report_menu import apply_share_build_meta, apply_page as apply_uniform_menu_page

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static/nep-preview'
PARQUET = ODV / 'data/parquet'
INTEGRATED = STATIC / 'integrated-project-data.json'
DPWH_CONTRACTS_PARQUET = (ROOT / 'research_downloads/hgab2027_contractors/extracted/'
                          'dpwh-contractors-gaa-2020-2026/dpwh-contracts-2016-2026.parquet')
OUT = ROOT / 'analysis_output'
PROJECT_TYPES = ('Flood Control', 'MPB', 'Roads', 'Bridges')


def year_value(value):
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def philgeps_year(row):
    """Use a plausible source year, falling back to a clear DPWH FY contract ID."""
    for field in ('project_year', 'contract_year'):
        candidate = year_value(row.get(field))
        if 2000 <= candidate <= 2035:
            return candidate
    identifier = str(
        row.get('philgeps_contract_no') or row.get('contract_id') or
        row.get('philgeps_reference_id') or row.get('project_id') or ''
    ).strip()
    match = re.match(r'^(\d{2})[A-Z]{1,4}\d', identifier, re.I)
    if match:
        yy = int(match.group(1))
        if 12 <= yy <= 35:
            return 2000 + yy
    return 0


def amount_value(*values):
    for value in values:
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            continue
        if amount:
            return round(amount, 2)
    return 0.0


def parse_dpwh_contractors(value):
    """Parse DPWH's `COMPANY (license) / JV COMPANY (license)` field."""
    entries = []
    for part in str(value or '').split(' / '):
        text = part.strip()
        match = re.match(r'^(.*?)\s+\(([^()]*)\)\s*$', text)
        if match:
            name = match.group(1).strip()
            license_id = re.sub(r'^\[REVOKED\]\s*', '', match.group(2).strip(), flags=re.I)
        else:
            name, license_id = text, ''
        if name and norm(name) not in {'n a', 'na', 'none', 'unknown'}:
            entries.append({'name': name, 'licenseId': license_id})
    return entries

def project_type(record):
    """Use the exact linked GAA category when available, then clear title cues."""
    category_map = {
        'flood control': 'Flood Control',
        'multi-purpose building': 'MPB',
        'multipurpose building': 'MPB',
        'road': 'Roads',
        'bridge': 'Bridges',
    }
    gaa_types = {category_map[str(row.get('category') or '').strip().casefold()]
                 for row in record.get('gaaMatches', [])
                 if str(row.get('category') or '').strip().casefold() in category_map}
    for row in record.get('dpwhContracts', []):
        source_category = str(row.get('category') or '').casefold()
        if 'flood control' in source_category or 'hydraulics' in source_category or 'drainage' in source_category:
            gaa_types.add('Flood Control')
        elif 'bridge' in source_category:
            gaa_types.add('Bridges')
        elif 'road' in source_category or 'pccp' in source_category:
            gaa_types.add('Roads')
    if len(gaa_types) == 1:
        return next(iter(gaa_types))
    if len(gaa_types) > 1:
        return 'Other'
    title = str(record.get('project') or '')
    if re.search(r'multi[ -]?purpose building|multipurpose building|covered court', title, re.I):
        return 'MPB'
    if re.search(r'\bbridge\b', title, re.I):
        return 'Bridges'
    if re.search(r'flood control|flood mitigation|flood management|river control|drainage structure', title, re.I):
        return 'Flood Control'
    if re.search(r'\broad\b|\bstreet\b|\bhighway\b|farm.to.market', title, re.I):
        return 'Roads'
    return 'Other'


def main_data():
    integrated = json.loads(INTEGRATED.read_text(encoding='utf-8'))
    gaa_by_key = defaultdict(list)
    for row in integrated.get('projects', []):
        year = year_value(row.get('year'))
        title = str(row.get('name') or '').strip()
        if row.get('stage') == 'GAA' and year and title:
            gaa_by_key[(year, norm(title))].append({
                'year': year, 'title': title, 'amountPesos': int(row.get('amountPesos') or 0),
                'source': row.get('source') or '', 'category': row.get('category') or '',
            })

    dime = export_parquet(
        PARQUET / 'dime_projects.parquet', 'TRUE',
        'project_name, project_year, contract_year, amount, contract_amount, dime_cost, '
        'project_code, global_id, contractor_name, organization_name, contractor_status, '
        'contractor_role, province, city, barangay, source')
    philgeps = export_parquet(
        PARQUET / 'philgeps_contracts.parquet', 'TRUE',
        'project_name, project_description, philgeps_award_title, project_year, contract_year, '
        'amount, contract_amount, philgeps_contract_no, philgeps_reference_id, contract_id, '
        'project_id, global_id, contractor_name, philgeps_awardee_name, contractor_status, '
        'philgeps_award_status, contractor_role, province, philgeps_area_of_delivery, municipality, '
        'city, barangay, award_date, source')
    transparency = export_parquet(
        TRANSPARENCY_PARQUET, 'TRUE',
        'contract_id, project_name, contractor_name, contractor_id, contractor_name_2, contractor_id_2, '
        'contractor_name_3, contractor_id_3, contractor_name_4, contractor_id_4, year, contract_amount, '
        '"Contract Amount", "Contract Price", amount, cost_php, status, "Contract Status", region, '
        'implementing_office, province, city, source, file_source')
    dpwh_contracts = export_parquet(
        DPWH_CONTRACTS_PARQUET, 'contractor IS NOT NULL AND infra_year BETWEEN 2016 AND 2026',
        'contract_id, dpwh_url, description, category, component_categories, status, contract_php, '
        'amount_paid_php, progress_percent, dpwh_office, region, contractor, start_date, completion_date, '
        'infra_year, program_name, source_of_funds, gaa_year, report_count, has_satellite_image, is_live, livestream_url')
    dpwh_names_by_license = defaultdict(Counter)
    for row in dpwh_contracts:
        for contractor in parse_dpwh_contractors(row.get('contractor')):
            if contractor['licenseId']:
                dpwh_names_by_license[contractor['licenseId']][contractor['name']] += 1
    dpwh_canonical_name = {license_id: counts.most_common(1)[0][0]
                           for license_id, counts in dpwh_names_by_license.items() if counts}

    entities = {}

    def add_record(source, year, title, company, detail, unique_hint='', gaa_year=None):
        title = str(title or '').strip()
        company = str(company or '').strip()
        company_key, title_key = norm(company), norm(title)
        if not company_key or not title_key:
            return None
        identity = (year, title_key, company_key) if year else (year, title_key, company_key, unique_hint)
        record = entities.get(identity)
        if record is None:
            record = {
                'year': year, 'project': title, 'titleKey': title_key, 'contractor': company,
                'gaaMatches': gaa_by_key.get((gaa_year or year, title_key), []) if (gaa_year or year) else [],
                'dimeRecords': [], 'philgepsAwards': [], 'transparencyContracts': [], 'dpwhContracts': [],
                'province': detail.get('province') or '', 'municipality': detail.get('municipality') or '',
                'barangay': detail.get('barangay') or '',
            }
            entities[identity] = record
        record[source].append(detail)
        for key in ('province', 'municipality', 'barangay'):
            if not record[key] and detail.get(key):
                record[key] = detail[key]
        return record

    dime_seen = set()
    for i, row in enumerate(dime):
        year = year_value(row.get('project_year') or row.get('contract_year'))
        title = str(row.get('project_name') or row.get('project_description') or '').strip()
        company = str(row.get('contractor_name') or row.get('organization_name') or '').strip()
        identifier = str(row.get('global_id') or row.get('project_code') or '').strip()
        if not company or not title or norm(company) in {'no data available', 'unknown', 'n a'}:
            continue
        marker = (year, norm(title), norm(company), identifier or i)
        if marker in dime_seen:
            continue
        dime_seen.add(marker)
        add_record('dimeRecords', year, title, company, {
            'id': identifier, 'amountPesos': amount_value(row.get('contract_amount'), row.get('amount'), row.get('dime_cost')),
            'status': row.get('contractor_status') or row.get('status') or '', 'role': row.get('contractor_role') or '',
            'source': row.get('source') or 'ODV DIME project cache',
            'province': row.get('province') or '', 'municipality': row.get('city') or '', 'barangay': row.get('barangay') or '',
        }, unique_hint=identifier or str(i))

    # Keep awarded procurement rows only, and collapse repeated joins by award ID/title/year/company.
    award_groups = defaultdict(list)
    for i, row in enumerate(philgeps):
        company = str(row.get('philgeps_awardee_name') or row.get('contractor_name') or '').strip()
        title = str(row.get('project_name') or row.get('philgeps_award_title') or row.get('project_description') or '').strip()
        if not company or not title or not row.get('award_date'):
            continue
        year = philgeps_year(row)
        award_id = str(row.get('philgeps_contract_no') or row.get('contract_id') or row.get('philgeps_reference_id') or row.get('project_id') or '').strip()
        marker = (year, award_id, norm(title), norm(company)) if award_id else (year, '', norm(title), norm(company), amount_value(row.get('contract_amount'), row.get('amount')))
        award_groups[marker].append(row)
    for i, rows in enumerate(award_groups.values()):
        rows.sort(key=lambda r: len(str(r.get('project_name') or r.get('philgeps_award_title') or '')), reverse=True)
        row = rows[0]
        title = str(row.get('project_name') or row.get('philgeps_award_title') or row.get('project_description') or '').strip()
        company = str(row.get('philgeps_awardee_name') or row.get('contractor_name') or '').strip()
        year = philgeps_year(row)
        amounts = sorted({amount_value(r.get('contract_amount'), r.get('amount')) for r in rows})
        add_record('philgepsAwards', year, title, company, {
            'id': str(row.get('philgeps_contract_no') or row.get('contract_id') or row.get('philgeps_reference_id') or row.get('project_id') or ''),
            'amountPesos': max(amounts, default=0), 'reportedAmountsPesos': amounts,
            'amountConflict': len(amounts) > 1, 'duplicateSourceRows': len(rows),
            'awardDate': str(row.get('award_date') or ''), 'status': row.get('philgeps_award_status') or '',
            'yearBasis': 'PhilGEPS source year' if any(2000 <= year_value(row.get(k)) <= 2035 for k in ('project_year', 'contract_year')) else 'Fiscal-year prefix in procurement identifier',
            'source': row.get('source') or 'PhilGEPS awarded procurement',
            'province': row.get('province') or '', 'municipality': row.get('municipality') or row.get('city') or '',
            'barangay': row.get('barangay') or '',
        }, unique_hint=str(i))

    transparency_groups = defaultdict(list)
    for i, row in enumerate(transparency):
        year = year_value(row.get('year'))
        title = str(row.get('project_name') or '').strip()
        if not title or not year:
            continue
        names = transparency_contractor_entries(row)
        if not names:
            continue
        contract_id = str(row.get('contract_id') or '').strip()
        amount = amount_value(row.get('contract_amount'), row.get('Contract Amount'), row.get('Contract Price'), row.get('amount'), row.get('cost_php'))
        for contractor in names:
            marker = (year, contract_id, norm(title), norm(contractor['name'])) if contract_id else (year, '', norm(title), norm(contractor['name']), amount)
            transparency_groups[marker].append((row, contractor))
    for i, group in enumerate(transparency_groups.values()):
        row, contractor = group[0]
        title = str(row.get('project_name') or '').strip()
        year = year_value(row.get('year'))
        amounts = sorted({amount_value(x.get('contract_amount'), x.get('Contract Amount'), x.get('Contract Price'), x.get('amount'), x.get('cost_php')) for x, _ in group})
        add_record('transparencyContracts', year, title, contractor['name'], {
            'id': str(row.get('contract_id') or ''), 'contractorId': contractor.get('id') or '',
            'amountPesos': max(amounts, default=0), 'reportedAmountsPesos': amounts,
            'amountConflict': len(amounts) > 1, 'duplicateSourceRows': len(group),
            'status': row.get('status') or row.get('Contract Status') or '',
            'office': row.get('implementing_office') or '', 'region': row.get('region') or '',
            'source': row.get('source') or row.get('file_source') or 'DPWH Transparency',
            'province': row.get('province') or '', 'municipality': row.get('city') or '', 'barangay': '',
        }, unique_hint=str(i))

    # The BetterGov Parquet is the line-level DPWH Transparency snapshot. Preserve
    # every named contractor/contract association and keep its figures separate
    # from the existing Transparency parquet and the DIME/PhilGEPS sources.
    for i, row in enumerate(dpwh_contracts):
        title = str(row.get('description') or '').strip()
        contract_id = str(row.get('contract_id') or '').strip()
        year = year_value(row.get('infra_year'))
        if not title or not contract_id or not year:
            continue
        contractors_in_row = parse_dpwh_contractors(row.get('contractor'))
        for contractor in contractors_in_row:
            listed_name = contractor['name']
            contractor_name = dpwh_canonical_name.get(contractor['licenseId'], listed_name)
            add_record('dpwhContracts', year, title, contractor_name, {
                'id': contract_id, 'url': row.get('dpwh_url') or '',
                'licenseId': contractor['licenseId'],
                'listedContractorName': listed_name,
                'amountPesos': amount_value(row.get('contract_php')),
                'amountPaidPesos': amount_value(row.get('amount_paid_php')),
                'progressPercent': row.get('progress_percent'),
                'status': row.get('status') or '', 'category': row.get('category') or '',
                'componentCategories': row.get('component_categories') or '',
                'office': row.get('dpwh_office') or '', 'region': row.get('region') or '',
                'program': row.get('program_name') or '', 'sourceOfFunds': row.get('source_of_funds') or '',
                'gaaYear': year_value(row.get('gaa_year')),
                'startDate': row.get('start_date') or '', 'completionDate': row.get('completion_date') or '',
                'reportCount': year_value(row.get('report_count')),
                'hasSatelliteImage': bool(row.get('has_satellite_image')),
                'hasLivestream': bool(row.get('is_live')),
            }, unique_hint=contract_id, gaa_year=year_value(row.get('gaa_year')) or year)

    amo = json.loads(AMO_CACHE.read_text(encoding='utf-8'))
    direct_names = set()
    amo_by_company = defaultdict(list)
    sec_amo_by_company = defaultdict(list)
    for category in ('top_direct', 'top_indirect'):
        for row in amo.get(category, []):
            official = str(row.get('pcab_amo') or row.get('full_name') or '').strip()
            if category == 'top_direct' and norm(official):
                direct_names.add(norm(official))
            for company in row.get('contractors') or []:
                key = norm(company)
                if key:
                    amo_by_company[key].append({
                        'amoName': official if category == 'top_direct' else mask_name_with_letter_hints(official),
                        'role': 'Listed elected official in source cache' if category == 'top_direct' else 'Indirect AMO relationship record',
                        'position': row.get('position'), 'year': row.get('year'), 'province': row.get('province'),
                        'relationship': row.get('relationship_type'),
                    })
            for company in row.get('sec_companies') or []:
                key = norm(company.get('contractor_name') or company.get('company_name'))
                if key:
                    sec_amo_by_company[key].append(company)

    merchants = export_parquet(MERCHANT_PARQUET, "status = 'success' AND name IS NOT NULL",
        'contractor_name, normalized_name, name, reg_status, reg_philgeps_number, reg_approved_date, reg_philgeps_expiry, scraped_at, status')
    merchant_by_name = defaultdict(list)
    for row in merchants:
        name = str(row.get('name') or '').strip()
        key, membership = norm(name), str(row.get('reg_status') or '').strip().title()
        if key and membership in {'Red', 'Platinum'}:
            entry = {'membership': membership, 'certificateNumber': row.get('reg_philgeps_number') or '',
                     'expiryDate': row.get('reg_philgeps_expiry') or '', 'scrapedAt': row.get('scraped_at') or '',
                     'registeredName': name}
            if entry not in merchant_by_name[key]:
                merchant_by_name[key].append(entry)
    pcab_by_name = defaultdict(list)
    with PCAB_CSV.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            key = norm(row.get('nameOfFirm'))
            if key:
                item = {'registeredName': row.get('nameOfFirm') or '', 'licenseNumber': row.get('licenseNumber') or '',
                        'category': row.get('Category') or '', 'validToDate': row.get('validToDate') or '',
                        'governmentInfrastructure': row.get('regForGovInfraProjects') or ''}
                if item not in pcab_by_name[key]:
                    pcab_by_name[key].append(item)
    sec = json.loads(SEC_DATABASE.read_text(encoding='utf-8'))
    sec_by_name = defaultdict(list)
    for row in sec.get('contractors', []):
        key = norm(row.get('company_name') or row.get('original_contractor_name'))
        if not key:
            continue
        item = {field: row.get(field) or '' for field in ('company_name','sec_number','status','date_registered','registered_address','source')}
        officers = []
        for officer in row.get('officers') or []:
            name = str(officer.get('name_display') or officer.get('name') or '').strip()
            if name:
                officers.append({**officer, 'name_display': name if norm(name) in direct_names else mask_name_with_letter_hints(name)})
        item['officers'] = officers
        if any(item.get(k) for k in ('sec_number','status','date_registered','registered_address')) and item not in sec_by_name[key]:
            sec_by_name[key].append(item)

    by_contractor = defaultdict(list)
    for record in entities.values():
        record['dimeRecords'] = _unique(record['dimeRecords'], 'id')
        record['philgepsAwards'] = _unique(record['philgepsAwards'], 'id')
        record['transparencyContracts'] = _unique(record['transparencyContracts'], 'id')
        record['dpwhContracts'] = _unique(record['dpwhContracts'], 'id')
        if not any(record[k] for k in ('dimeRecords','philgepsAwards','transparencyContracts','dpwhContracts')):
            continue
        by_contractor[norm(record['contractor'])].append(record)

    contractors = []
    for key, projects in by_contractor.items():
        names = sorted({p['contractor'] for p in projects}, key=str.casefold)
        for project in projects:
            project['projectType'] = project_type(project)
        dime_count = sum(len(p['dimeRecords']) for p in projects)
        award_count = sum(len(p['philgepsAwards']) for p in projects)
        transparency_count = sum(len(p['transparencyContracts']) for p in projects)
        dpwh_count = sum(len(p['dpwhContracts']) for p in projects)
        dime_amount = round(sum(r['amountPesos'] for p in projects for r in p['dimeRecords']), 2)
        philgeps_amount = round(sum(r['amountPesos'] for p in projects for r in p['philgepsAwards']), 2)
        transparency_amount = round(sum(r['amountPesos'] for p in projects for r in p['transparencyContracts']), 2)
        dpwh_amount = round(sum(r['amountPesos'] for p in projects for r in p['dpwhContracts']), 2)
        years = sorted({p['year'] for p in projects if p['year']})
        year_stats = []
        for year in years:
            rows = [p for p in projects if p['year'] == year]
            year_stats.append({'year': year, 'projectCount': len(rows),
                'gaaLinkedProjectCount': sum(bool(p['gaaMatches']) for p in rows),
                'dimeProjectCount': sum(len(p['dimeRecords']) for p in rows),
                'philgepsAwardCount': sum(len(p['philgepsAwards']) for p in rows),
                'transparencyContractCount': sum(len(p['transparencyContracts']) for p in rows),
                'dpwhContractCount': sum(len(p['dpwhContracts']) for p in rows),
                'dimeContractAmountPesos': round(sum(r['amountPesos'] for p in rows for r in p['dimeRecords']),2),
                'philgepsAwardValuePesos': round(sum(r['amountPesos'] for p in rows for r in p['philgepsAwards']),2),
                'transparencyContractAmountPesos': round(sum(r['amountPesos'] for p in rows for r in p['transparencyContracts']),2),
                'dpwhContractAmountPesos': round(sum(r['amountPesos'] for p in rows for r in p['dpwhContracts']),2)})
        category_stats = []
        for category in PROJECT_TYPES:
            category_projects = [p for p in projects if p['projectType'] == category]
            for year in sorted({p['year'] for p in category_projects if p['year']}):
                rows = [p for p in category_projects if p['year'] == year]
                category_stats.append({'projectType': category, 'year': year,
                    'projectCount': len(rows),
                    'dimeProjectCount': sum(len(p['dimeRecords']) for p in rows),
                    'philgepsAwardCount': sum(len(p['philgepsAwards']) for p in rows),
                    'transparencyContractCount': sum(len(p['transparencyContracts']) for p in rows),
                    'dpwhContractCount': sum(len(p['dpwhContracts']) for p in rows),
                    'gaaLinkedProjectCount': sum(bool(p['gaaMatches']) for p in rows),
                    'dimeContractAmountPesos': round(sum(r['amountPesos'] for p in rows for r in p['dimeRecords']), 2),
                    'philgepsAwardValuePesos': round(sum(r['amountPesos'] for p in rows for r in p['philgepsAwards']), 2),
                    'transparencyContractAmountPesos': round(sum(r['amountPesos'] for p in rows for r in p['transparencyContracts']), 2),
                    'dpwhContractAmountPesos': round(sum(r['amountPesos'] for p in rows for r in p['dpwhContracts']), 2)})
        sec_records = list(sec_by_name.get(key, []))
        for item in sec_amo_by_company.get(key, []):
            if item not in sec_records:
                sec_records.append(item)
        contractors.append({'contractor': names[0], 'aliases': names[1:], 'projectCount': len(projects),
            'dimeProjectCount': dime_count, 'philgepsAwardCount': award_count,
            'transparencyContractCount': transparency_count, 'dpwhContractCount': dpwh_count,
            'gaaLinkedProjectCount': sum(bool(p['gaaMatches']) for p in projects),
            'dimeContractAmountPesos': dime_amount, 'philgepsAwardValuePesos': philgeps_amount,
            'transparencyContractAmountPesos': transparency_amount, 'dpwhContractAmountPesos': dpwh_amount,
            'years': years, 'yearStats': year_stats,
            'categoryStats': category_stats,
            'secRecords': sec_records, 'philgepsMembership': merchant_by_name.get(key, []),
            'pcabLicenses': pcab_by_name.get(key, []), 'amoMatches': amo_by_company.get(key, []), 'projects': projects})
    contractors.sort(key=lambda x: (-x['projectCount'], x['contractor'].casefold()))
    source_totals = {'dimeProjectRecords': sum(c['dimeProjectCount'] for c in contractors),
        'philgepsAwardRecords': sum(c['philgepsAwardCount'] for c in contractors),
        'transparencyContractAssociations': sum(c['transparencyContractCount'] for c in contractors),
        'dpwhContractAssociations': sum(c['dpwhContractCount'] for c in contractors),
        'gaaLinkedProjectAssociations': sum(c['gaaLinkedProjectCount'] for c in contractors)}
    return {'generatedAtUtc': datetime.now(timezone.utc).isoformat(), 'scope': {
            'description': 'Named contractor associations from DIME projects, awarded PhilGEPS records, DPWH Transparency contract records and the BetterGov DPWH contract-list snapshot. Exact normalized title/year GAA matches are attached where the integrated DPWH GAA source contains a classified line. The integrated GAA baseline covers classified DPWH roads, bridges, flood-control and multi-purpose-building rows.',
            'gaaYears': sorted({year for year, _ in gaa_by_key}), 'gaaLinkedTitleYearKeys': len(gaa_by_key)},
        'summary': {'contractorCount': len(contractors), 'projectAssociations': sum(c['projectCount'] for c in contractors), **source_totals},
        'sourceNotes': {'DIME':'All named contractor project rows in the local ODV DIME cache.',
            'PhilGEPS':'Award-dated rows with a named awardee in the local ODV PhilGEPS cache; repeated source joins are deduplicated by award identity.',
            'DPWH Transparency':'All named contractor associations in the local DPWH Transparency cache; repeated rows are deduplicated by contract/title/year/name.',
            'DPWH contract list':'BetterGov DPWH contracts Parquet, snapshot 2026-11-03, FY2016–FY2026. Individual contract descriptions, amounts, statuses, offices and DPWH source-page links are attached by exact contractor name and license parsed from the source field. Joint-venture contract rows appear under every named party, so contractor-level associations overlap and must not be summed as distinct contracts. Contract amounts are not payments; amount-paid values are displayed as reported. This source overlaps the separate DPWH Transparency parquet and is retained as its own evidence column.',
            'GAA':'Exact normalized title/year links use classified project rows from integrated-project-data.json. An absent link means no exact classified row was found in that dataset, not proof that the project was unbudgeted.',
            'AMO':'ODV AMO cache associations are research leads. Indirect names and SEC officers without a known direct elected-official association are masked with first/last-letter hints.'},
        'contractors': contractors}


def _unique(rows, field):
    seen, out = set(), []
    for row in rows:
        key = str(row.get(field) or '')
        marker = key if key else json.dumps(row, sort_keys=True, ensure_ascii=False)
        if marker not in seen:
            seen.add(marker); out.append(row)
    return out


PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Contractors · BetterGov</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f3f6f8;color:#17212b;font:15px/1.5 system-ui,sans-serif}header{background:linear-gradient(120deg,#00246a,#0038a8);color:white;padding:24px clamp(16px,3vw,40px);border-bottom:6px solid #fcd116}h1{margin:0;font-size:clamp(28px,4vw,42px)}header p{max-width:950px;color:#eef4ff}main{width:100%;padding:22px clamp(14px,2vw,32px)}section{margin:18px 0;padding:20px;background:white;border:1px solid #d8e1e7;border-radius:14px}.stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}.stat{padding:14px;background:#f3f6f8;border-radius:10px}.stat strong{display:block;color:#00246a;font-size:24px}.controls{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.controls input,.controls select,button{font:inherit;padding:8px 10px;border:1px solid #aebdca;border-radius:8px;background:white}.controls input{flex:1;min-width:220px}button{color:#0038a8;cursor:pointer}.table-wrap{overflow:auto;max-height:72vh}table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px}th,td{padding:8px;border-bottom:1px solid #dce3e8;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{position:sticky;top:0;background:#edf3f8;z-index:1}.num{text-align:right;white-space:nowrap}.muted{color:#566575;font-size:13px}.bar-row{display:grid;grid-template-columns:minmax(130px,1fr) minmax(80px,2fr) auto;gap:8px;align-items:center;margin:7px}.track{height:13px;background:#e7edf2;border-radius:20px;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#0038a8,#168c86)}.details{margin-top:16px}.project{padding:10px 0;border-bottom:1px solid #dce3e8}.notice{border-left:5px solid #fcd116;background:#fffdf1;padding:13px 16px}.hidden{display:none}@media(max-width:900px){.stats{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:720px){.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.table-wrap{max-height:none}.bar-row{grid-template-columns:minmax(90px,1fr) minmax(50px,1fr) auto}}</style></head><body>
<header><div class="eyebrow">Procurement evidence · cross-source contractor analysis</div><h1>Contractors</h1><p>Named contractor records from DIME, awarded PhilGEPS procurement and DPWH Transparency, with exact-title/year GAA links where classified project lines are available.</p></header><main>
<section class="notice"><strong>How to read this directory.</strong> Contractor names are consolidated by exact normalized name; similar names are not automatically merged. A project association is deduplicated by title, year and contractor, while source records remain separately visible. GAA allocations and source contract values are distinct; cross-source values can overlap and should not be added together. An absent exact GAA link is not proof that a project was unbudgeted.</section>
<section><div id="stats" class="stats"></div></section><section><h2>Ranked contractors</h2><p class="muted">Choose a project type, year, search or source-specific ranking. DIME, PhilGEPS and Transparency amounts can describe the same contract, so they remain separate.</p><div class="controls"><label>Project type <select id="project-type"><option value="">All projects</option><option>Flood Control</option><option>MPB</option><option>Roads</option><option>Bridges</option></select></label><label>Rank by <select id="metric"><option value="projectCount">Distinct project associations</option><option value="dimeContractAmountPesos">DIME recorded value</option><option value="philgepsAwardValuePesos">PhilGEPS award value</option><option value="transparencyContractAmountPesos">DPWH Transparency value</option><option value="dpwhContractAmountPesos">DPWH contract-list value</option></select></label><label>Year <select id="year"><option value="">All available years</option></select></label><input id="search" type="search" placeholder="Search contractor"></div><div id="chart"></div><div class="table-wrap"><table><thead><tr><th>Rank</th><th>Contractor</th><th>Projects</th><th>DIME records / value</th><th>PhilGEPS awards / value</th><th>Transparency contracts / value</th><th>GAA-linked projects</th><th>DPWH contract records / value</th><th>SEC company / officers</th><th>Membership / PCAB</th><th>AMO leads</th></tr></thead><tbody id="ranking"></tbody></table></div><p id="status" class="muted"></p><button id="export" type="button">Export filtered contractors CSV</button></section>
<section id="details" class="details"><h2>Project records</h2><div id="project-table" class="muted">Select a contractor to inspect project records and source-specific values.</div></section>
<section><h2>Sources and matching</h2><p id="source-notes" class="muted"></p><p class="muted">Project-type filters use exact classified GAA title/year categories where available; otherwise, clear title wording is used. Unclear records are excluded from the type-specific filters. Exact GAA links use normalized title and year and cover classified DPWH road, bridge, flood-control and multi-purpose-building rows in the integrated project dataset. The DPWH FY2016–FY2026 contract list is added as a separate project-record source, with contract links and named parties parsed from the source field. Joint-venture contracts are associated with each named contractor; these associations overlap and must not be summed as unique contracts. DIME, PhilGEPS, DPWH Transparency and the DPWH contract list remain separately reported. <a href="https://budget-assets.bettergov.ph/hgab/2027/contractors/downloads/dpwh-contracts-2016-2026.parquet?v=cf5b390712ba">Download the 267,292-row DPWH contract Parquet</a>. SEC, PCAB, PhilGEPS registration and AMO fields are exact-name leads from cached ODV datasets, not current certifications or proof of ownership, control or benefit.</p></section>
<script>
let D;const $=id=>document.getElementById(id),n=x=>Number(x||0).toLocaleString('en-PH'),peso=x=>'₱'+n(Math.round(Number(x||0))),esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));let selected=null,detailsCache=new Map();
fetch('contractors-data/index.json').then(r=>{if(!r.ok)throw Error(r.status);return r.json()}).then(d=>{D=d;const S=D.summary;const stats=[[S.contractorCount,'Contractors'],[S.projectAssociations,'Distinct contractor/project associations'],[S.dimeProjectRecords,'DIME records'],[S.philgepsAwardRecords+S.transparencyContractAssociations,'PhilGEPS awards + Transparency associations'],[S.dpwhContractAssociations,'DPWH contract associations']];$('stats').innerHTML=stats.map(([v,l])=>'<div class="stat"><strong>'+n(v)+'</strong><span>'+esc(l)+'</span></div>').join('');$('source-notes').textContent=Object.entries(D.sourceNotes).map(([k,v])=>k+': '+v).join(' ');const requestedType=new URLSearchParams(location.search).get('type');if(['Flood Control','MPB','Roads','Bridges'].includes(requestedType))$('project-type').value=requestedType;const ys=[...new Set(D.contractors.flatMap(c=>c.years||[]))].sort((a,b)=>a-b);for(const y of ys){const o=document.createElement('option');o.value=y;o.textContent='FY'+y;$('year').append(o)}
function rows(){const q=$('search').value.toLowerCase().trim(),y=$('year').value,type=$('project-type').value,metric=$('metric').value;return D.contractors.map(c=>{let s;if(type){const parts=(c.categoryStats||[]).filter(x=>x.projectType===type&&(!y||String(x.year)===y));s=parts.reduce((a,x)=>{for(const k of ['projectCount','dimeProjectCount','philgepsAwardCount','transparencyContractCount','dpwhContractCount','gaaLinkedProjectCount','dimeContractAmountPesos','philgepsAwardValuePesos','transparencyContractAmountPesos','dpwhContractAmountPesos'])a[k]=(a[k]||0)+Number(x[k]||0);return a},{})}else s=y?c.yearStats.find(x=>String(x.year)===y):c;return {...c,...s,projectType:type||''}}).filter(c=>c.projectCount&&(!q||[c.contractor,...c.aliases].join(' ').toLowerCase().includes(q))).sort((a,b)=>b[metric]-a[metric]||a.contractor.localeCompare(b.contractor))}
function render(){const list=rows(),metric=$('metric').value,top=list.slice(0,12),max=Math.max(1,...top.map(x=>Number(x[metric]||0)));$('chart').innerHTML=top.map((c,i)=>'<div class="bar-row"><span>'+n(i+1)+'. '+esc(c.contractor)+'</span><span class="track"><span class="fill" style="display:block;width:'+100*Number(c[metric]||0)/max+'%"></span></span><strong>'+ (metric==='projectCount'?n(c[metric]):peso(c[metric]))+'</strong></div>').join('');$('ranking').innerHTML=list.map((c,i)=>{const dpwh=n(c.dpwhContractCount)+' · '+peso(c.dpwhContractAmountPesos),sec=c.secRecords.length?c.secRecords.map(s=>esc(s.company_name||'SEC record')+(s.sec_number?' · '+esc(s.sec_number):'')+(s.officers?.length?'<div class="muted">'+s.officers.map(o=>esc(o.role||'officer')+': '+esc(o.name_display||o.name||'')).join('<br>')+'</div>':'')).join('<br>'):'—',pcab=[...c.philgepsMembership.map(x=>x.membership+' PhilGEPS'),...c.pcabLicenses.map(x=>(x.category||'PCAB')+' · '+(x.licenseNumber||''))].join('<br>')||'—',amo=c.amoMatches.slice(0,4).map(x=>esc(x.amoName)+' · '+esc(x.role)).join('<br>')||'—';return '<tr><td>'+n(i+1)+'</td><td><button data-id="'+esc(c.id)+'">'+esc(c.contractor)+'</button>'+(c.aliases.length?'<div class="muted">Also: '+esc(c.aliases.join('; '))+'</div>':'')+'</td><td>'+n(c.projectCount)+'</td><td>'+n(c.dimeProjectCount)+' · '+peso(c.dimeContractAmountPesos)+'</td><td>'+n(c.philgepsAwardCount)+' · '+peso(c.philgepsAwardValuePesos)+'</td><td>'+n(c.transparencyContractCount)+' · '+peso(c.transparencyContractAmountPesos)+'</td><td>'+n(c.gaaLinkedProjectCount)+'</td><td>'+dpwh+'</td><td>'+sec+'</td><td>'+pcab+'</td><td>'+amo+'</td></tr>'}).join('');$('status').textContent=n(list.length)+' contractors shown'+($('project-type').value?' · '+$('project-type').value:'')+($('year').value?' · FY'+$('year').value:'')+' · ranked by '+$('metric').selectedOptions[0].textContent+'. Source values remain separate.';document.querySelectorAll('#ranking button[data-id]').forEach(b=>b.onclick=()=>{selected=b.dataset.id;renderDetails()})}
async function renderDetails(){const c=D.contractors.find(x=>x.id===selected);if(!c)return;let projects=detailsCache.get(c.id);if(!projects){projects=[];for(const shard of c.detailShards||[]){let payload=detailsCache.get(shard);if(!payload){payload=await fetch('contractors-data/'+shard).then(r=>{if(!r.ok)throw Error(r.status);return r.json()});detailsCache.set(shard,payload)}const entry=payload.entries.find(x=>x.id===c.id);if(entry)projects.push(...entry.projects)}detailsCache.set(c.id,projects)}const year=$('year').value,type=$('project-type').value,shown=projects.filter(p=>(!year||String(p.year)===year)&&(!type||p.projectType===type));$('details').querySelector('h2').textContent=c.contractor+' · source-level projects';$('project-table').innerHTML=shown.map(p=>'<article class="project"><strong>'+esc(p.project)+' · FY'+(p.year||'year unavailable')+'</strong><div class="muted">'+esc([p.province,p.municipality,p.barangay].filter(Boolean).join(' · '))+' · '+esc(p.projectType||'Other')+'</div>'+(p.gaaMatches.length?'<div>GAA: '+p.gaaMatches.map(g=>esc(g.category)+' · '+peso(g.amountPesos)+' · '+esc(g.source)).join('<br>')+'</div>':'<div>GAA: no exact title/year link in the classified source layer</div>')+p.dimeRecords.map(x=>'<div>DIME: '+peso(x.amountPesos)+' · '+esc(x.id||'ID unavailable')+' · '+esc(x.status||'status unavailable')+'</div>').join('')+p.philgepsAwards.map(x=>'<div>PhilGEPS awarded: '+peso(x.amountPesos)+' · '+esc(x.id||'ID unavailable')+' · '+esc(x.status||'')+(x.amountConflict?' · conflicting source amounts':'')+'</div>').join('')+p.transparencyContracts.map(x=>'<div>DPWH Transparency: '+peso(x.amountPesos)+' · '+esc(x.id||'ID unavailable')+' · '+esc(x.status||'')+'</div>').join('')+p.dpwhContracts.map(x=>'<div>DPWH contract list: '+(x.url?'<a href="'+esc(x.url)+'" target="_blank" rel="noreferrer">'+esc(x.id||'open contract')+'</a>':esc(x.id||'ID unavailable'))+' · '+peso(x.amountPesos)+' · DPWH listed name: '+esc(x.listedContractorName||'')+' · '+esc(x.status||'status unavailable')+' · '+esc(x.office||'office unavailable')+' · paid reported '+peso(x.amountPaidPesos)+(x.gaaYear?' · source GAA FY'+esc(x.gaaYear):'')+(x.progressPercent!==null&&x.progressPercent!==undefined?' · '+esc(x.progressPercent)+'% physical progress':'')+'</div>').join('')+'</article>').join('')||'<p>No projects for this selection.</p>'}
function csv(){const data=rows(),fields=['contractor','projectType','projectCount','dimeProjectCount','philgepsAwardCount','transparencyContractCount','dpwhContractCount','dimeContractAmountPesos','philgepsAwardValuePesos','transparencyContractAmountPesos','dpwhContractAmountPesos','gaaLinkedProjectCount'];const content=[fields,...data.map(c=>fields.map(k=>c[k]))].map(r=>r.map(x=>'"'+String(x??'').replaceAll('"','""')+'"').join(',')).join('\r\n'),a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff'+content],{type:'text/csv;charset=utf-8'}));a.download='contractors-cross-source.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
for(const id of ['metric','year','project-type'])$(id).onchange=()=>{render();if(selected)renderDetails()};$('search').oninput=render;$('export').onclick=csv;render()}).catch(e=>{$('status').textContent='Could not load cross-source contractor data: '+e.message});
</script></main></body></html>'''


def build():
    data = main_data()
    contractors = data.pop('contractors')
    index = {k:v for k,v in data.items()}
    index['dataShardFormat'] = 'contractors-data/shard-NNN.json; project details load on selection'
    OUT.mkdir(exist_ok=True)
    stats = {}
    for folder in (OUT/'contractors-data', STATIC/'contractors-data'):
        stats = write_contractors_payload(folder,index.copy(),contractors)
    html = apply_uniform_menu_page(apply_share_build_meta(PAGE), 'contractors.html')
    from report_table_presentation import apply_page_table_module
    html,_=apply_page_table_module('contractors.html',html)
    for path in (OUT/'contractors.html',STATIC/'contractors.html'):
        path.write_text(html,encoding='utf-8')
    print(json.dumps({**data['summary'],**stats},indent=2))


if __name__ == '__main__':
    build()
