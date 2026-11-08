#!/usr/bin/env python3
"""Build an auditable GAA MPB contractor study from DIME and PhilGEPS project records."""
from __future__ import annotations

import hashlib
import csv
import json
import re
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from uniform_report_menu import apply_share_build_meta

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / 'open-data-visualization'
STATIC = ODV / 'static' / 'nep-preview'
PARQUET = ODV / 'data' / 'parquet'
INTEGRATED = STATIC / 'integrated-project-data.json'
AMO_CACHE = ODV / 'static' / 'data' / 'philgeps_amo_cache.json'
MERCHANT_PARQUET = ODV / 'database' / 'philgeps_merchant_info.parquet'
PCAB_CSV = ODV / 'database' / 'PCAB_REGULAR_LICENSE_COMBINED.csv'
SEC_DATABASE = ODV / 'static' / 'data' / 'sec_contractors_database.json'
FY2019_MPB_GAA = ROOT / 'data_sources' / 'mpb-historical-2019.json'
FY2015_MPB_GAA = ROOT / 'data_sources' / 'mpb-historical-2015.json'
TRANSPARENCY_PARQUET = PARQUET / 'transparency_projects.parquet'
OUT = ROOT / 'analysis_output'


def norm(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def mask_name_with_letter_hints(value):
    """Keep first and last letters of each name token while masking its middle."""
    def mask_token(match):
        token = match.group(0)
        if len(token) <= 2:
            return token
        return token[0] + '*' * (len(token) - 2) + token[-1]
    return re.sub(r"[^\W\d_]+", mask_token, str(value or ''), flags=re.UNICODE)


MPB_OBJECT = re.compile(r'(?:building|bldg\b|bld\b|buildin\b|buil\b|hall|covered court|gym|facility|cent(?:er|re)|warehouse)', re.I)


def philgeps_mpb_title(row):
    title = ' '.join(str(row.get(k) or '') for k in ('project_name', 'philgeps_award_title', 'project_description'))
    return bool(re.search(r'multi[\s-]?purpose', title, re.I) and MPB_OBJECT.search(title))


def philgeps_award_projects(rows):
    """Deduplicate repeated PhilGEPS joins to one awarded project/title record."""
    groups = defaultdict(list)
    for row in rows:
        awardee = str(row.get('philgeps_awardee_name') or row.get('contractor_name') or '').strip()
        title = str(row.get('project_name') or row.get('philgeps_award_title') or row.get('project_description') or '').strip()
        year = int(row.get('project_year') or row.get('contract_year') or 0)
        # An awardee and award date distinguish an award from an open tender or keyword-only hit.
        if not awardee or not row.get('award_date') or not title or not philgeps_mpb_title(row):
            continue
        award_id = (row.get('philgeps_contract_no') or row.get('contract_id') or
                    row.get('philgeps_reference_id') or row.get('project_id') or '')
        identity = (str(award_id), year, norm(title), norm(awardee))
        if not award_id:
            identity = ('', year, norm(title), norm(awardee), round(float(row.get('contract_amount') or row.get('amount') or 0), 2))
        groups[identity].append(row)

    projects = []
    for identity, records in groups.items():
        # Keep the most complete title and the largest reported award value when
        # repeated source rows disagree; the conflict remains explicit for review.
        records = sorted(records, key=lambda r: len(str(r.get('project_name') or r.get('philgeps_award_title') or '')), reverse=True)
        row = records[0]
        amounts = sorted({round(float(r.get('contract_amount') or r.get('amount') or 0), 2) for r in records})
        awardee = str(row.get('philgeps_awardee_name') or row.get('contractor_name') or '').strip()
        title = str(row.get('project_name') or row.get('philgeps_award_title') or row.get('project_description') or '').strip()
        projects.append({
            'year': int(row.get('project_year') or row.get('contract_year') or 0),
            'project': title,
            'contractor': awardee,
            'contractAmountPesos': max(amounts, default=0),
            'contractId': row.get('philgeps_contract_no') or row.get('contract_id') or row.get('philgeps_reference_id') or row.get('project_id') or '',
            'awardDate': str(row.get('award_date') or ''),
            'awardStatus': row.get('philgeps_award_status') or '',
            'province': row.get('province') or '',
            'areaOfDelivery': row.get('philgeps_area_of_delivery') or '',
            'awardeeKey': norm(awardee),
            'titleKey': norm(title),
            'awardValueConflict': len(amounts) > 1,
            'reportedAwardAmountsPesos': amounts,
            'duplicateSourceRows': len(records),
            'source': 'PhilGEPS award record',
        })
    return sorted(projects, key=lambda r: (r['year'], r['project'].casefold(), r['contractId']))


TRANSPARENCY_MPB_TITLE = re.compile(
    r'\bmulti purpose(?:d)? (?:building|bldg|hall|covered court|gym|facility)\b', re.I)


def transparency_contractor_entries(row):
    entries = []
    for index in range(1, 5):
        suffix = '' if index == 1 else f'_{index}'
        name = str(row.get(f'contractor_name{suffix}') or '').strip()
        if not name or norm(name) in {'n a', 'na', 'none', 'unknown'}:
            continue
        contractor_id = row.get(f'contractor_id{suffix}')
        contractor_id = str(contractor_id).strip() if contractor_id not in (None, '') else ''
        if contractor_id.endswith('.0'):
            contractor_id = contractor_id[:-2]
        entries.append({'name': name, 'id': contractor_id})
    return entries


def transparency_mpb_contracts(rows, gaa_keys):
    """Deduplicate DPWH Transparency contract rows and retain contractor/JV evidence."""
    groups = defaultdict(list)
    for row in rows:
        year = int(row.get('year') or 0)
        title = str(row.get('project_name') or '').strip()
        title_key = norm(title)
        if not title or not year or not title_key:
            continue
        if (year, title_key) not in gaa_keys and not TRANSPARENCY_MPB_TITLE.search(title_key):
            continue
        contract_id = str(row.get('contract_id') or '').strip()
        contractor_entries = transparency_contractor_entries(row)
        identity = (year, contract_id, title_key) if contract_id else (
            year, '', title_key, tuple(sorted((norm(c['name']), c['id']) for c in contractor_entries)))
        groups[identity].append(row)

    projects = []
    for identity, records in groups.items():
        records.sort(key=lambda r: sum(bool(r.get(k)) for k in (
            'contractor_name', 'contractor_name_2', 'contractor_id', 'contractor_id_2',
            'contract_amount', 'Contract Amount', 'Contract Price', 'status')), reverse=True)
        row = records[0]
        names = {}
        amounts = set()
        for item in records:
            for contractor in transparency_contractor_entries(item):
                marker = (contractor['id'], norm(contractor['name']))
                names[marker] = contractor
            for field in ('contract_amount', 'Contract Amount', 'Contract Price', 'amount', 'cost_php'):
                try:
                    value = float(item.get(field) or 0)
                except (TypeError, ValueError):
                    value = 0
                if value > 0:
                    amounts.add(round(value, 2))
        contractors = sorted(names.values(), key=lambda c: (c['name'].casefold(), c['id']))
        amount = max(amounts, default=0)
        projects.append({
            'year': int(row.get('year') or 0), 'project': str(row.get('project_name') or '').strip(),
            'titleKey': norm(row.get('project_name')), 'contractId': row.get('contract_id') or '',
            'contractAmountPesos': amount, 'reportedAmountsPesos': sorted(amounts),
            'amountConflict': len(amounts) > 1, 'duplicateSourceRows': len(records),
            'contractors': contractors, 'jointVenture': len(contractors) > 1,
            'contractStatus': row.get('status') or row.get('Contract Status') or '',
            'region': row.get('region') or '', 'office': row.get('implementing_office') or '',
            'province': row.get('province') or '', 'municipality': row.get('city') or '',
            'source': 'DPWH Transparency contract record',
        })
    return sorted(projects, key=lambda r: (r['year'], r['project'].casefold(), str(r['contractId'])))


def export_parquet(path: Path, where: str, fields: str):
    """Read the local parquet source files through the DuckDB CLI."""
    cli = '/opt/homebrew/bin/duckdb'
    sql_path = str(path).replace("'", "''")
    sql = (f"COPY (SELECT {fields} FROM read_parquet('{sql_path}') WHERE {where}) "
           "TO '{output}' (FORMAT JSON);\n")
    with tempfile.NamedTemporaryFile('w', suffix='.sql', encoding='utf-8', delete=False) as script:
        script_path = Path(script.name)
    try:
        with tempfile.NamedTemporaryFile('w', suffix='.json', encoding='utf-8', delete=False) as output:
            output_path = Path(output.name)
        script_path.write_text(sql.replace('{output}', str(output_path)), encoding='utf-8')
        subprocess.run([cli, '-no-stdin', '-f', str(script_path)], check=True, capture_output=True, text=True)
        return [json.loads(line) for line in output_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    finally:
        script_path.unlink(missing_ok=True)
        if 'output_path' in locals():
            output_path.unlink(missing_ok=True)


def load_sources():
    gaa_payload = json.loads(INTEGRATED.read_text(encoding='utf-8'))
    gaa = [row for row in gaa_payload.get('projects', [])
           if row.get('stage') == 'GAA' and row.get('category') == 'Multi-purpose building'
           and 2016 <= int(row.get('year') or 0) <= 2026
           and int(row.get('year') or 0) != 2019]
    # Preserve FY2015 PAP candidates from the DBM CSV, including unresolved
    # locations; the district snapshot contains only uniquely assigned rows.
    gaa.extend(json.loads(FY2015_MPB_GAA.read_text(encoding='utf-8')).get('records', []))
    # The district project snapshot omits unresolved locations. Keep every
    # FY2019 technical-GAA MPB line in the contractor baseline regardless of
    # whether its title can be assigned to a current legislative district.
    gaa.extend(json.loads(FY2019_MPB_GAA.read_text(encoding='utf-8')).get('records', []))
    dime = export_parquet(
        PARQUET / 'dime_projects.parquet',
        "lower(coalesce(project_name,'')) LIKE '%multi-purpose%'",
        'project_name, project_year, contract_year, amount, contract_amount, dime_cost, '
        'project_code, global_id, contractor_name, organization_name, contractor_status, '
        'contractor_role, province, city, barangay, source')
    philgeps = export_parquet(
        PARQUET / 'philgeps_contracts.parquet',
        "lower(coalesce(project_name,'') || ' ' || coalesce(philgeps_award_title,'') || ' ' || coalesce(project_description,'')) LIKE '%multi-purpose%' OR lower(coalesce(project_name,'') || ' ' || coalesce(philgeps_award_title,'') || ' ' || coalesce(project_description,'')) LIKE '%multi purpose%' OR lower(coalesce(project_name,'') || ' ' || coalesce(philgeps_award_title,'') || ' ' || coalesce(project_description,'')) LIKE '%multipurpose%'",
        'project_name, project_year, contract_year, amount, contract_amount, '
        'philgeps_contract_no, philgeps_reference_id, contract_id, project_id, global_id, contractor_name, '
        'philgeps_awardee_name, contractor_status, philgeps_award_status, contractor_role, '
        'province, philgeps_area_of_delivery, municipality, city, barangay, award_date, source')
    transparency = export_parquet(
        TRANSPARENCY_PARQUET,
        "lower(coalesce(project_name,'')) LIKE '%multi-purpose%' OR "
        "lower(coalesce(project_name,'')) LIKE '%multi purpose%' OR "
        "lower(coalesce(project_name,'')) LIKE '%multipurpose%'",
        'contract_id, project_name, contractor_name, contractor_id, '
        'contractor_name_2, contractor_id_2, contractor_name_3, contractor_id_3, '
        'contractor_name_4, contractor_id_4, year, contract_amount, "Contract Amount", '
        '"Contract Price", amount, cost_php, status, "Contract Status", region, '
        'implementing_office, province, city, source, file_source')
    amo = json.loads(AMO_CACHE.read_text(encoding='utf-8'))
    merchants = export_parquet(
        MERCHANT_PARQUET,
        "status = 'success' AND name IS NOT NULL",
        'contractor_name, normalized_name, name, reg_status, reg_philgeps_number, '
        'reg_approved_date, reg_philgeps_expiry, scraped_at, status')
    with PCAB_CSV.open(encoding='utf-8-sig', newline='') as stream:
        pcab = list(csv.DictReader(stream))
    return gaa, dime, philgeps, transparency, amo, merchants, pcab


def build():
    gaa, dime, philgeps, transparency, amo, merchants, pcab = load_sources()
    sec_payload = json.loads(SEC_DATABASE.read_text(encoding='utf-8'))
    awarded_philgeps = philgeps_award_projects(philgeps)
    by_title_year = defaultdict(list)
    for row in dime:
        year = int(row.get('project_year') or row.get('contract_year') or 0)
        title = norm(row.get('project_name'))
        if title and year:
            by_title_year[(year, title)].append(row)

    philgeps_by_title_year = defaultdict(list)
    for row in philgeps:
        year = int(row.get('project_year') or row.get('contract_year') or 0)
        title = norm(row.get('project_name') or row.get('philgeps_award_title') or row.get('project_description'))
        if title and year:
            philgeps_by_title_year[(year, title)].append(row)

    gaa_keys = {(int(p.get('year') or 0), norm(p.get('name'))) for p in gaa}
    transparency_contracts = transparency_mpb_contracts(transparency, gaa_keys)
    transparency_by_title_year = defaultdict(list)
    for contract in transparency_contracts:
        transparency_by_title_year[(contract['year'], contract['titleKey'])].append(contract)
    transparency_alias_ids = defaultdict(set)
    for contract in transparency_contracts:
        for contractor in contract['contractors']:
            if contractor['id']:
                transparency_alias_ids[norm(contractor['name'])].add(contractor['id'])
    transparency_entity_id = {
        name_key: next(iter(ids)) for name_key, ids in transparency_alias_ids.items() if len(ids) == 1
    }

    def contractor_key(name):
        normalized = norm(name)
        return f"dpwh:{transparency_entity_id[normalized]}" if normalized in transparency_entity_id else normalized

    amo_by_company = defaultdict(list)
    sec_amo_by_company = defaultdict(list)
    for category in ('top_direct', 'top_indirect'):
        for row in amo.get(category, []):
            for company in row.get('contractors') or []:
                key = norm(company)
                if key:
                    amo_by_company[key].append({
                        'amoName': (row.get('pcab_amo') or row.get('full_name')) if category == 'top_direct'
                            else mask_name_with_letter_hints(row.get('pcab_amo') or row.get('full_name')),
                        'role': 'AMO is listed as an elected official in the source cache' if category == 'top_direct' else 'Indirect AMO relationship record',
                        'position': row.get('position'),
                        'year': row.get('year'),
                        'province': row.get('province'),
                        'municipality': row.get('municipality_city'),
                        'relationship': row.get('relationship_type'),
                    })
            for company in row.get('sec_companies') or []:
                key = norm(company.get('contractor_name') or company.get('company_name'))
                if key:
                    sec_amo_by_company[key].append({
                        'company_name': company.get('company_name') or company.get('contractor_name') or '',
                        'sec_number': company.get('sec_number') or '',
                        'status': company.get('status') or '',
                        'date_registered': company.get('date_registered') or '',
                        'source': company.get('source') or 'SEC and AMO relationship records',
                        'officers': company.get('officers') or [],
                    })

    # Keep only exact normalized registered organization names. A JV or a
    # similarly named merchant is not silently treated as the same company.
    merchant_by_name = defaultdict(list)
    for row in merchants:
        key = norm(row.get('name'))
        membership = str(row.get('reg_status') or '').strip().title()
        if key and membership in {'Red', 'Platinum'}:
            item = {
                'membership': membership,
                'certificateNumber': row.get('reg_philgeps_number') or '',
                'approvedDate': row.get('reg_approved_date') or '',
                'expiryDate': row.get('reg_philgeps_expiry') or '',
                'scrapedAt': row.get('scraped_at') or '',
                'registeredName': row.get('name') or '',
            }
            marker = (item['membership'], item['certificateNumber'], item['expiryDate'], item['registeredName'])
            if all((m['membership'], m['certificateNumber'], m['expiryDate'], m['registeredName']) != marker
                   for m in merchant_by_name[key]):
                merchant_by_name[key].append(item)

    pcab_by_name = defaultdict(list)
    for row in pcab:
        key = norm(row.get('nameOfFirm'))
        if not key:
            continue
        item = {
            'registeredName': row.get('nameOfFirm') or '',
            'licenseNumber': row.get('licenseNumber') or '',
            'category': row.get('Category') or '',
            'amo': row.get('AMO') or '',
            'validToDate': row.get('validToDate') or '',
            'governmentInfrastructure': row.get('regForGovInfraProjects') or '',
        }
        marker = (item['licenseNumber'], item['category'], item['validToDate'], item['governmentInfrastructure'])
        if all((m['licenseNumber'], m['category'], m['validToDate'], m['governmentInfrastructure']) != marker
               for m in pcab_by_name[key]):
            pcab_by_name[key].append(item)

    sec_by_name = defaultdict(list)
    for row in sec_payload.get('contractors', []):
        key = norm(row.get('company_name') or row.get('original_contractor_name'))
        if not key:
            continue
        item = {field: row.get(field) or '' for field in (
            'company_name', 'sec_number', 'status', 'date_registered', 'registered_address', 'source')}
        if not any(item[field] for field in ('sec_number', 'status', 'date_registered', 'registered_address')):
            continue
        marker = (item['sec_number'], item['status'], item['date_registered'])
        if all((r['sec_number'], r['status'], r['date_registered']) != marker for r in sec_by_name[key]):
            sec_by_name[key].append(item)

    matched, ambiguous, gaa_inventory = [], [], []
    gaa_by_title_year = defaultdict(list)
    for project in gaa:
        year = int(project.get('year') or 0)
        title = str(project.get('name') or '')
        key = (year, norm(title))
        gaa_by_title_year[key].append(project)
        dime_rows = by_title_year.get(key, [])
        philgeps_rows = philgeps_by_title_year.get(key, [])
        gaa_inventory.append({
            'year': year,
            'stage': project.get('stage') or 'GAA',
            'project': title,
            'allocationPesos': int(project.get('amountPesos') or 0),
            'districtId': project.get('districtId') or '',
            'gaaSource': project.get('source') or '',
            'dimeMatchCount': len(dime_rows),
            'dimeContractors': ' | '.join(sorted({str(r.get('contractor_name') or '').strip() for r in dime_rows if r.get('contractor_name')})),
            'dimeIds': ' | '.join(sorted({str(r.get('global_id') or r.get('project_code') or '') for r in dime_rows if r.get('global_id') or r.get('project_code')})),
            'dimeContractAmountsPesos': ' | '.join(str(r.get('contract_amount') or r.get('amount') or '') for r in dime_rows),
            'philgepsMatchCount': len(philgeps_rows),
            'philgepsAwardees': ' | '.join(sorted({str(r.get('philgeps_awardee_name') or r.get('contractor_name') or '').strip() for r in philgeps_rows if r.get('philgeps_awardee_name') or r.get('contractor_name')})),
            'philgepsContractIds': ' | '.join(sorted({str(r.get('philgeps_contract_no') or r.get('contract_id') or '') for r in philgeps_rows if r.get('philgeps_contract_no') or r.get('contract_id')})),
            'transparencyMatchCount': len(transparency_by_title_year.get(key, [])),
            'transparencyContractors': ' | '.join(sorted({c['name'] for t in transparency_by_title_year.get(key, []) for c in t['contractors']})),
            'transparencyContractIds': ' | '.join(sorted({str(t['contractId']) for t in transparency_by_title_year.get(key, []) if t['contractId']})),
            'transparencyContractAmountsPesos': ' | '.join(str(t['contractAmountPesos']) for t in transparency_by_title_year.get(key, [])),
        })

    matched, ambiguous = [], []
    matched_dime_source_ids = set()
    for project in gaa:
        key = (int(project.get('year') or 0), norm(project.get('name')))
        candidates = by_title_year.get(key, [])
        if len(candidates) != 1:
            if candidates:
                ambiguous.append({'year': key[0], 'project': project.get('name'), 'candidateCount': len(candidates)})
            continue
        source = candidates[0]
        matched_dime_source_ids.add(id(source))
        contractor = str(source.get('contractor_name') or '').strip()
        if not contractor or norm(contractor) in {'no data available', 'unknown', 'n a'}:
            continue
        matched.append({
            'year': key[0], 'project': project.get('name'),
            'recordType': 'GAA + DIME', 'gaaMatchStatus': 'Exact normalized title and year match',
            'gaaAllocationPesos': int(project.get('amountPesos') or 0),
            'gaaSource': project.get('source'), 'contractor': contractor,
            'contractAmountPesos': float(source.get('contract_amount') or source.get('amount') or 0),
            'dimeContractAmountPesos': float(source.get('contract_amount') or source.get('amount') or 0),
            'philgepsAwardValuePesos': 0,
            'dimeProjectId': source.get('global_id') or source.get('project_code') or '',
            'dimeProjectName': source.get('project_name'),
            'contractYear': int(source.get('contract_year') or source.get('project_year') or key[0]),
            'contractStatus': source.get('contractor_status') or source.get('status') or '',
            'province': source.get('province') or '', 'municipality': source.get('city') or '',
            'barangay': source.get('barangay') or '',
            'philgepsMatches': [{
                'awardee': r.get('philgeps_awardee_name') or r.get('contractor_name') or '',
                'contractAmountPesos': float(r.get('contract_amount') or r.get('amount') or 0),
                'contractId': r.get('philgeps_contract_no') or r.get('contract_id') or '',
                'status': r.get('philgeps_award_status') or '',
            } for r in philgeps_by_title_year.get(key, [])],
            'transparencyMatches': [], 'transparencyContractAmountPesos': 0,
            'amoMatches': amo_by_company.get(norm(contractor), []),
            'philgepsMembership': merchant_by_name.get(norm(contractor), []),
            'pcabLicenses': pcab_by_name.get(norm(contractor), []),
        })

    dime_matched_project_count = len(matched)
    dime_matched_projects = list(matched)
    dime_only_projects = []
    for source in dime:
        if id(source) in matched_dime_source_ids:
            continue
        year = int(source.get('project_year') or source.get('contract_year') or 0)
        title = str(source.get('project_name') or '').strip()
        contractor = str(source.get('contractor_name') or '').strip()
        if not title or not contractor or norm(contractor) in {'no data available', 'unknown', 'n a'}:
            continue
        gaa_candidates = gaa_by_title_year.get((year, norm(title)), [])
        if len(gaa_candidates) == 1:
            # A unique GAA match should already have been represented above;
            # retain this guard in case source-key normalization changes.
            continue
        status = ('FLAG · multiple GAA lines share normalized title/year'
                  if len(gaa_candidates) > 1 else
                  'FLAG · no exact normalized GAA title/year match')
        amount = float(source.get('contract_amount') or source.get('amount') or 0)
        row = {
            'year': year, 'project': title, 'recordType': 'DIME-only MPB',
            'gaaMatchStatus': status, 'gaaAllocationPesos': 0, 'gaaSource': '',
            'contractor': contractor, 'contractAmountPesos': amount,
            'dimeContractAmountPesos': amount, 'philgepsAwardValuePesos': 0,
            'dimeProjectId': source.get('global_id') or source.get('project_code') or '',
            'dimeProjectName': title,
            'contractYear': int(source.get('contract_year') or source.get('project_year') or year),
            'contractStatus': source.get('contractor_status') or source.get('status') or '',
            'province': source.get('province') or '', 'municipality': source.get('city') or '',
            'barangay': source.get('barangay') or '', 'philgepsMatches': [],
            'transparencyMatches': [], 'transparencyContractAmountPesos': 0,
            'amoMatches': amo_by_company.get(norm(contractor), []),
            'philgepsMembership': merchant_by_name.get(norm(contractor), []),
            'pcabLicenses': pcab_by_name.get(norm(contractor), []),
        }
        dime_only_projects.append(row)
        matched.append(row)

    philgeps_only_projects, philgeps_linked_awards, philgeps_ambiguous_awards = [], [], []
    for award in awarded_philgeps:
        key = (award['year'], award['titleKey'])
        gaa_rows = gaa_by_title_year.get(key, [])
        award_record = {k: award.get(k) for k in ('contractId', 'awardDate', 'awardStatus', 'contractor', 'project', 'year', 'contractAmountPesos', 'awardValueConflict', 'reportedAwardAmountsPesos')}
        if gaa_rows:
            linked = {**award_record, 'matchStatus': 'Exact normalized title and year match to GAA'}
            philgeps_linked_awards.append(linked)
            if len(gaa_rows) != 1:
                philgeps_ambiguous_awards.append({**linked, 'matchStatus': f'{len(gaa_rows)} GAA lines share this normalized title and year'})
            existing = next((p for p in matched if p['year'] == award['year'] and norm(p['project']) == award['titleKey'] and norm(p['contractor']) == award['awardeeKey']), None)
            if existing:
                existing.setdefault('philgepsMatches', []).append(linked)
                existing['philgepsAwardValuePesos'] = round(float(existing.get('philgepsAwardValuePesos') or 0) + award['contractAmountPesos'], 2)
                existing['contractAmountPesos'] = max(float(existing.get('contractAmountPesos') or 0), float(existing['philgepsAwardValuePesos']))
                continue  # DIME already contributes the project and contract value.
            gaa_project = gaa_rows[0]
            matched.append({
                'year': award['year'], 'project': award['project'],
                'recordType': 'GAA + PhilGEPS', 'gaaMatchStatus': 'Exact normalized title and year match',
                'gaaAllocationPesos': int(gaa_project.get('amountPesos') or 0),
                'gaaSource': gaa_project.get('source') or '', 'contractor': award['contractor'],
                'contractAmountPesos': award['contractAmountPesos'], 'dimeContractAmountPesos': 0,
                'philgepsAwardValuePesos': award['contractAmountPesos'],
                'dimeProjectId': '', 'dimeProjectName': '', 'contractYear': award['year'],
                'contractStatus': f"PhilGEPS award · {award['awardStatus'] or 'award date recorded'}",
                'province': award['province'], 'municipality': '', 'barangay': '',
                'philgepsMatches': [linked],
                'transparencyMatches': [], 'transparencyContractAmountPesos': 0,
                'amoMatches': amo_by_company.get(award['awardeeKey'], []),
                'philgepsMembership': merchant_by_name.get(award['awardeeKey'], []),
                'pcabLicenses': pcab_by_name.get(award['awardeeKey'], []),
            })
            continue

        project_row = {
            'year': award['year'], 'project': award['project'],
            'recordType': 'PhilGEPS-only awarded MPB',
            'gaaMatchStatus': 'FLAG · no exact normalized GAA title/year match',
            'gaaAllocationPesos': 0, 'gaaSource': '', 'contractor': award['contractor'],
            'contractAmountPesos': award['contractAmountPesos'], 'dimeContractAmountPesos': 0,
            'philgepsAwardValuePesos': award['contractAmountPesos'],
            'dimeProjectId': '', 'dimeProjectName': '', 'contractYear': award['year'],
            'contractStatus': f"PhilGEPS award · {award['awardStatus'] or 'award date recorded'}",
            'province': award['province'], 'municipality': award['areaOfDelivery'], 'barangay': '',
            'philgepsMatches': [{**award_record, 'matchStatus': 'FLAG · no exact normalized GAA title/year match'}],
            'transparencyMatches': [], 'transparencyContractAmountPesos': 0,
            'philgepsAwardId': award['contractId'], 'awardDate': award['awardDate'],
            'contractId': award['contractId'], 'contractYear': award['year'],
            'awardValueConflict': award['awardValueConflict'],
            'reportedAwardAmountsPesos': award['reportedAwardAmountsPesos'],
            'amoMatches': amo_by_company.get(award['awardeeKey'], []),
            'philgepsMembership': merchant_by_name.get(award['awardeeKey'], []),
            'pcabLicenses': pcab_by_name.get(award['awardeeKey'], []),
        }
        philgeps_only_projects.append(project_row)
        matched.append(project_row)

    existing_title_keys = {(p['year'], norm(p['project'])) for p in matched}
    base_source_title_keys = set(existing_title_keys)
    transparency_match_stats = {
        'records': len(transparency_contracts), 'contractorAssociations': 0,
        'exactContractorLinks': 0, 'titleYearLinks': 0,
        'contractorNameMismatches': 0, 'newContractorRows': 0,
        'jointVentureRecords': sum(bool(c['jointVenture']) for c in transparency_contracts),
        'amountConflictRecords': sum(bool(c['amountConflict']) for c in transparency_contracts),
    }
    matched_transparency_ids = set()
    transparency_only_projects = []
    transparency_new_project_keys = set()
    transparency_gaa_link_ids = set()
    transparency_titleyear_matched_ids = set()
    source_rows_by_title_year = defaultdict(list)
    for source_row in matched:
        source_rows_by_title_year[(source_row['year'], norm(source_row['project']))].append(source_row)
    for contract in transparency_contracts:
        key = (contract['year'], contract['titleKey'])
        if key in gaa_by_title_year or key in existing_title_keys:
            transparency_match_stats['titleYearLinks'] += 1
            transparency_titleyear_matched_ids.add(contract['contractId'])
        contract['exactGaaTitleYearMatch'] = bool(gaa_by_title_year.get(key))
        contract['otherSourceTitleYearMatch'] = key in base_source_title_keys
        contract['exactContractorLinks'] = 0
        if key in gaa_by_title_year:
            transparency_gaa_link_ids.add(contract['contractId'])
        if key not in gaa_by_title_year and key not in base_source_title_keys:
            transparency_new_project_keys.add(key)
        source_rows_same_project = source_rows_by_title_year.get(key, [])
        if source_rows_same_project and not any(contractor_key(p['contractor']) == contractor_key(t['name'])
                                                for p in source_rows_same_project for t in contract['contractors']):
            transparency_match_stats['contractorNameMismatches'] += 1
        for trans_contractor in contract['contractors']:
            transparency_match_stats['contractorAssociations'] += 1
            candidate = next((p for p in source_rows_same_project
                              if contractor_key(p['contractor']) == contractor_key(trans_contractor['name'])), None)
            transparency_match = {
                'contractId': contract['contractId'], 'contractAmountPesos': contract['contractAmountPesos'],
                'contractStatus': contract['contractStatus'], 'contractorName': trans_contractor['name'],
                'contractorId': trans_contractor['id'], 'jointVenture': contract['jointVenture'],
                'amountConflict': contract['amountConflict'], 'reportedAmountsPesos': contract['reportedAmountsPesos'],
                'duplicateSourceRows': contract['duplicateSourceRows'],
                'matchStatus': 'Exact normalized contractor + title/year match' if candidate else
                    ('Title/year match; contractor name differs' if source_rows_same_project else
                     ('Exact title/year GAA match' if gaa_by_title_year.get(key) else
                      'FLAG · no exact GAA/DIME/PhilGEPS title/year match')),
            }
            if candidate:
                candidate.setdefault('transparencyMatches', []).append(transparency_match)
                candidate['transparencyContractAmountPesos'] = round(
                    sum(float(x.get('contractAmountPesos') or 0) for x in candidate['transparencyMatches']), 2)
                source_amounts = [float(candidate.get(k) or 0) for k in
                                  ('dimeContractAmountPesos', 'philgepsAwardValuePesos', 'transparencyContractAmountPesos')]
                candidate['contractAmountPesos'] = max(source_amounts, default=0)
                matched_transparency_ids.add(contract['contractId'])
                contract['exactContractorLinks'] += 1
                transparency_match_stats['exactContractorLinks'] += 1
                continue

            gaa_rows = gaa_by_title_year.get(key, [])
            gaa_project = gaa_rows[0] if len(gaa_rows) == 1 else None
            if gaa_project:
                record_type = 'GAA + DPWH Transparency'
                gaa_status = 'Exact normalized title and year match'
            elif len(gaa_rows) > 1:
                record_type = 'DPWH Transparency-only MPB'
                gaa_status = 'FLAG · multiple GAA lines share normalized title/year'
            elif source_rows_same_project:
                record_type = 'DPWH Transparency-only MPB'
                gaa_status = 'FLAG · title/year matches contractor records with a different contractor name'
            else:
                record_type = 'DPWH Transparency-only MPB'
                gaa_status = 'FLAG · no exact normalized GAA title/year match'
            row = {
                'year': contract['year'], 'project': contract['project'], 'recordType': record_type,
                'gaaMatchStatus': gaa_status,
                'gaaAllocationPesos': int(gaa_project.get('amountPesos') or 0) if gaa_project else 0,
                'gaaSource': gaa_project.get('source') or '' if gaa_project else '',
                'gaaLineId': gaa_project.get('id') or '' if gaa_project else '',
                'contractor': trans_contractor['name'],
                'contractAmountPesos': contract['contractAmountPesos'],
                'dimeContractAmountPesos': 0, 'philgepsAwardValuePesos': 0,
                'transparencyContractAmountPesos': contract['contractAmountPesos'],
                'dimeProjectId': '', 'dimeProjectName': '', 'contractYear': contract['year'],
                'contractStatus': f"DPWH Transparency · {contract['contractStatus'] or 'contract record'}",
                'province': contract['province'], 'municipality': contract['municipality'], 'barangay': '',
                'philgepsMatches': [], 'transparencyMatches': [transparency_match],
                'transparencyContractId': contract['contractId'],
                'transparencyJointVenture': contract['jointVenture'],
                'transparencyAwardValueConflict': contract['amountConflict'],
                'reportedTransparencyAmountsPesos': contract['reportedAmountsPesos'],
                'amoMatches': amo_by_company.get(norm(trans_contractor['name']), []),
                'philgepsMembership': merchant_by_name.get(norm(trans_contractor['name']), []),
                'pcabLicenses': pcab_by_name.get(norm(trans_contractor['name']), []),
            }
            transparency_only_projects.append(row)
            matched.append(row)
            source_rows_by_title_year[key].append(row)
            existing_title_keys.add(key)
            transparency_match_stats['newContractorRows'] += 1

    for project in matched:
        amounts = [float(project.get(k) or 0) for k in (
            'dimeContractAmountPesos', 'philgepsAwardValuePesos', 'transparencyContractAmountPesos')]
        project['contractAmountPesos'] = max(amounts, default=0)

    groups = defaultdict(list)
    for row in matched:
        groups[contractor_key(row['contractor'])].append(row)
    contractor_rows = []
    for key, projects in groups.items():
        names = sorted({p['contractor'] for p in projects}, key=str.casefold)
        amo_matches = []
        seen_amo = set()
        for project in projects:
            for match in project['amoMatches']:
                marker = (norm(match['amoName']), match['role'], match['year'], norm(match.get('province')))
                if marker not in seen_amo:
                    seen_amo.add(marker)
                    amo_matches.append(match)
        membership_rows, seen_membership = [], set()
        pcab_rows, seen_pcab = [], set()
        sec_rows, seen_sec = [], set()
        for project in projects:
            for record in project['philgepsMembership']:
                marker = (record['membership'], record['certificateNumber'], record['expiryDate'], record['registeredName'])
                if marker not in seen_membership:
                    seen_membership.add(marker)
                    membership_rows.append(record)
            for record in project['pcabLicenses']:
                marker = (record['licenseNumber'], record['category'], record['validToDate'], record['governmentInfrastructure'])
                if marker not in seen_pcab:
                    seen_pcab.add(marker)
                    pcab_rows.append(record)
            for name in [project['contractor'], *project.get('contractorAliases', [])]:
                for record in sec_by_name.get(norm(name), []):
                    marker = (record['sec_number'], record['status'], record['date_registered'])
                    if marker not in seen_sec:
                        seen_sec.add(marker)
                        sec_rows.append(record)
        for name in names:
            for record in sec_by_name.get(norm(name), []):
                marker = (record['sec_number'], record['status'], record['date_registered'])
                if marker not in seen_sec:
                    seen_sec.add(marker)
                    sec_rows.append(record)
            for record in sec_amo_by_company.get(norm(name), []):
                marker = (record['company_name'], record['sec_number'], record['status'], record['date_registered'])
                if all((r.get('company_name'), r.get('sec_number'), r.get('status'), r.get('date_registered')) != marker
                       for r in sec_rows):
                    sec_rows.append(record)
        gaa_projects = [p for p in projects if p['recordType'].startswith('GAA')]
        dime_only = [p for p in projects if p['recordType'] == 'DIME-only MPB']
        philgeps_only = [p for p in projects if p['recordType'] == 'PhilGEPS-only awarded MPB']
        transparency_only = [p for p in projects if p['recordType'] == 'DPWH Transparency-only MPB']
        transparency_links = [p for p in projects if p.get('transparencyMatches')]
        dime_amount = round(sum(float(p.get('dimeContractAmountPesos') or 0) for p in projects), 2)
        philgeps_amount = round(sum(float(p.get('philgepsAwardValuePesos') or 0) for p in projects), 2)
        transparency_amount = round(sum(float(p.get('transparencyContractAmountPesos') or 0) for p in projects), 2)
        year_stats = []
        for year in sorted({int(p.get('year') or p.get('contractYear') or 0) for p in projects}):
            year_projects = [p for p in projects if int(p.get('year') or p.get('contractYear') or 0) == year]
            year_stats.append({
                'year': year,
                'projectCount': len(year_projects),
                'gaaProjectCount': sum(p['recordType'].startswith('GAA') for p in year_projects),
                'dimeOnlyProjectCount': sum(p['recordType'] == 'DIME-only MPB' for p in year_projects),
                'philgepsOnlyProjectCount': sum(p['recordType'] == 'PhilGEPS-only awarded MPB' for p in year_projects),
                'dimeContractAmountPesos': round(sum(float(p.get('dimeContractAmountPesos') or 0) for p in year_projects), 2),
                'philgepsAwardValuePesos': round(sum(float(p.get('philgepsAwardValuePesos') or 0) for p in year_projects), 2),
                'contractAmountPesos': round(sum(float(p.get('contractAmountPesos') or 0) for p in year_projects), 2),
            })
        contractor_rows.append({
            'contractor': names[0], 'aliases': names[1:],
            'projectCount': len(projects),
            'gaaProjectCount': len(gaa_projects),
            'dimeOnlyProjectCount': len(dime_only),
            'philgepsOnlyProjectCount': len(philgeps_only),
            'transparencyProjectCount': len(transparency_links),
            'transparencyOnlyProjectCount': len(transparency_only),
            'dimeContractAmountPesos': dime_amount,
            'philgepsAwardValuePesos': philgeps_amount,
            'transparencyContractAmountPesos': transparency_amount,
            'contractAmountPesos': round(sum(float(p.get('contractAmountPesos') or 0) for p in projects), 2),
            'gaaAllocationPesos': sum(p['gaaAllocationPesos'] for p in projects),
            'years': sorted({p['year'] for p in projects}),
            'yearStats': year_stats,
            'amoMatches': amo_matches,
            'philgepsMembership': membership_rows,
            'pcabLicenses': pcab_rows,
            'secRecords': sec_rows,
            'projects': sorted(projects, key=lambda p: (p['year'], p['project'].casefold())),
        })
    contractor_rows.sort(key=lambda r: (-r['projectCount'], -r['contractAmountPesos'], r['contractor'].casefold()))

    gaa_keys = {(int(p.get('year') or 0), norm(p.get('name'))) for p in gaa}
    philgeps_exact = philgeps_linked_awards
    dime_contract_total = round(sum(float(p.get('dimeContractAmountPesos') or 0) for p in matched), 2)
    philgeps_award_total = round(sum(float(p.get('philgepsAwardValuePesos') or 0) for p in matched), 2)
    transparency_value_total = round(sum(float(c['contractAmountPesos']) for c in transparency_contracts), 2)
    transparency_count_by_id = {str(c['contractId']) for c in transparency_contracts if c['contractId']}
    transparency_base_ids = {
        str(m.get('contractId')) for p in matched for m in p.get('transparencyMatches', [])
        if m.get('contractId')
    }

    data = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'scope': {'gaaYears': '2015–2019 and 2020–2026', 'gaaMpbRows': len(gaa),
                  'gaaSource': 'FY2019 DBM technical DPWH GAA UACS PAP lines plus other GAA MPB rows classified by title'},
        'summary': {'gaaMpbLines': len(gaa),
                    'gaaUniqueTitleYearLines': len(gaa_keys),
                    'gaaRepeatedTitleYearRows': len(gaa) - len(gaa_keys),
                    'dimeExactGaaLines': sum(bool(by_title_year.get((int(p.get('year') or 0), norm(p.get('name'))))) for p in gaa),
                    'philgepsExactGaaLines': sum(bool(philgeps_by_title_year.get((int(p.get('year') or 0), norm(p.get('name'))))) for p in gaa),
                    'dimeMatchedGaaProjects': dime_matched_project_count,
                    'dimeKeywordRecords': len(dime),
                    'dimeNamedContractorRecords': sum(bool(str(r.get('contractor_name') or '').strip()) for r in dime),
                    'dimeOnlyProjects': len(dime_only_projects),
                    'dimeOnlyContractAmountPesos': round(sum(p['dimeContractAmountPesos'] for p in dime_only_projects), 2),
                    'philgepsAwardedProjects': len(awarded_philgeps),
                    'philgepsOnlyProjects': len(philgeps_only_projects),
                    'philgepsOnlyAwardValuePesos': round(sum(p['contractAmountPesos'] for p in philgeps_only_projects), 2),
                    'unionProjectCount': len(gaa) + len(dime_only_projects) + len(philgeps_only_projects) + len(transparency_new_project_keys),
                    'transparencyKeywordRecords': len(transparency),
                    'transparencyMpbContractRecords': len(transparency_contracts),
                    'transparencyGaaTitleYearLinks': len(transparency_gaa_link_ids),
                    'transparencyTitleYearLinks': transparency_match_stats['titleYearLinks'],
                    'transparencyContractorNameExactLinks': transparency_match_stats['exactContractorLinks'],
                    'transparencyContractorNameMismatches': transparency_match_stats['contractorNameMismatches'],
                    'transparencyOnlyTitleYearProjects': len(transparency_new_project_keys),
                    'transparencyContractorRowsAdded': transparency_match_stats['newContractorRows'],
                    'transparencyJointVentureRecords': transparency_match_stats['jointVentureRecords'],
                    'transparencyAmountConflictRecords': transparency_match_stats['amountConflictRecords'],
                    'transparencyUniqueContractValuePesos': transparency_value_total,
                    'transparencyUnlinkedContractRecords': len(transparency_count_by_id - transparency_titleyear_matched_ids),
                    'matchedProjects': len(matched), 'namedContractors': len(contractor_rows),
                    'gaaAllocationPesos': sum(p['gaaAllocationPesos'] for p in matched if p['recordType'].startswith('GAA')),
                    'dimeContractAmountPesos': dime_contract_total,
                    'philgepsAwardValuePesos': philgeps_award_total,
                    'contractAmountPesos': round(sum(float(p.get('contractAmountPesos') or 0) for p in matched), 2),
                    'contractAmountsAboveGaaLine': sum(p['contractAmountPesos'] > p['gaaAllocationPesos'] for p in dime_matched_projects),
                    'philgepsAwardValueConflicts': sum(bool(p['awardValueConflict']) for p in philgeps_only_projects),
                    'ambiguousTitleMatches': len(ambiguous), 'philgepsKeywordRecords': len(philgeps),
                    'philgepsExactGaaTitleMatches': len(philgeps_exact)},
        'matching': 'GAA is the historical MPB line baseline. DIME and PhilGEPS rows are retained as previously described. DPWH Transparency MPB contract records are matched by exact normalized title/year and exact contractor name, with DPWH Transparency contractor IDs used to consolidate name variants when unique. Exact title/year matches with differing contractor names are retained as separate associations and flagged. Unmatched Transparency records remain as Transparency-only rows. No fuzzy project identity is inferred; joint-venture amounts are not split among partners.',
        'sourceNotes': {
            'DIME': 'Named DIME project records; all keyword-filtered MPB contractor records with named contractors are included, including those without a unique exact GAA title/year match.',
            'DPWH Transparency': 'DPWH Transparency contract records; rows qualify through explicit multi-purpose building/facility wording or an exact title/year match to a classified GAA MPB line. Contract IDs deduplicate repeated source rows. Exact contractor ID aliases consolidate only when a source ID maps unambiguously to one contractor.',
            'PhilGEPS': 'PhilGEPS award records. Deduplicated awarded MPB rows are included as independent contractor projects when no exact GAA title/year match exists; exact matches enrich the GAA-linked project.',
            'AMO': 'PhilGEPS and AMO relationship records. A name match is a lead for review, not proof of ownership, control, benefit, influence, or wrongdoing.',
            'PhilGEPS registration': 'PhilGEPS registration records. Status is Red or Platinum as captured by the source, not a live validity check. The source snapshot is from November 2025.',
            'PCAB': 'PCAB regular-license records. Category, license number, government-infrastructure registration flag, and valid-through date are retained from the source. Exact normalized company-name match only.',
        },
        'contractors': contractor_rows,
        'philgepsOnlyProjects': philgeps_only_projects,
        'transparencyOnlyProjects': transparency_only_projects,
        'transparencyContractRecords': transparency_contracts,
        'transparencyMatching': transparency_match_stats,
        'philgepsLinkedAwards': philgeps_linked_awards,
        'philgepsAmbiguousGaaAwards': philgeps_ambiguous_awards,
        'gaaInventory': gaa_inventory,
        'ambiguousMatches': ambiguous,
        'philgepsExactMatches': philgeps_exact,
        'philgepsUnlinked': philgeps_only_projects,
    }
    data['summary']['contractorsWithPhilGEPSMembershipRecord'] = sum(bool(c['philgepsMembership']) for c in contractor_rows)
    data['summary']['contractorsWithPCABLicenseRecord'] = sum(bool(c['pcabLicenses']) for c in contractor_rows)
    data['summary']['philgepsUnlinkedRecords'] = len(data['philgepsUnlinked'])
    return data


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GAA + DIME + PhilGEPS MPB records · BetterGov</title>
<style>
:root{--navy:#00246a;--blue:#0038a8;--gold:#fcd116;--ink:#17212b;--muted:#566575;--line:#d8e1e7;--paper:#f3f6f8;--teal:#087e78}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}header{background:linear-gradient(120deg,var(--navy),var(--blue));color:white;border-bottom:6px solid var(--gold);padding:24px clamp(16px,3vw,40px)}header .brand{display:inline-block;color:#fff;text-decoration:none;font-weight:800;letter-spacing:.02em}header .eyebrow{margin:20px 0 4px;color:var(--gold);text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:800}h1{margin:0;font-size:clamp(28px,4vw,42px);line-height:1.1;color:white}header p{max-width:900px;color:#eef4ff;margin:10px 0 0}main{width:100%;padding:20px clamp(14px,2vw,32px) 42px}.notice{border-left:5px solid var(--gold);background:#fffdf1;border-radius:9px;padding:14px 18px;margin:0 0 18px;color:#36424e}.hero-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.stat,.card{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 3px 12px #102f3e0b}.stat{padding:16px}.stat strong{display:block;color:var(--navy);font-size:clamp(22px,3vw,30px);font-variant-numeric:tabular-nums}.stat span{display:block;color:var(--muted);font-size:13px}.card{padding:clamp(16px,2vw,24px);margin:18px 0}.card h2{margin:0 0 6px;color:var(--navy);font-size:22px}.lede,.muted{color:var(--muted)}.viz-grid{display:grid;grid-template-columns:1fr;gap:18px;align-items:start}.controls{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.controls input,.controls select,button{font:inherit;padding:9px 11px;border:1px solid #aebdca;border-radius:8px;background:white;color:var(--ink)}.controls input{min-width:220px;flex:1}button{cursor:pointer;color:var(--blue);font-weight:700}.chart{min-height:270px}.bar-row{display:grid;grid-template-columns:minmax(120px,1.2fr) minmax(50px,2fr) auto;gap:9px;align-items:center;margin:9px 0;font-size:13px}.bar-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.track{height:15px;border-radius:20px;background:#e7edf2;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#0038a8,#168c86);border-radius:20px}.bar-value{font-weight:750;white-space:nowrap;font-variant-numeric:tabular-nums}table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:14px}th,td{padding:10px 9px;text-align:left;vertical-align:top;border-bottom:1px solid #dce3e8;overflow-wrap:anywhere;word-break:break-word}th{background:#edf3f8;color:#233f5b;position:sticky;top:0;z-index:1}td.num{text-align:right;white-space:normal;font-variant-numeric:tabular-nums}.table-wrap{overflow-x:auto;overflow-y:auto;max-height:70vh;border:1px solid var(--line);border-radius:9px}.rank{width:48px;color:var(--muted)}.contractor{font-weight:750;color:var(--navy)}.tag{display:inline-block;background:#eef4ff;color:#20477b;border-radius:999px;padding:2px 8px;font-size:12px}.detail{margin-top:18px}.hidden{display:none!important}.source-list li{margin:6px 0}.small{font-size:13px}.foot{border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:13px}.pagination{display:flex;gap:12px;align-items:center;justify-content:flex-end;padding-top:10px}.research-status{max-width:none;margin:18px 0;padding:12px 16px;border-left:4px solid var(--gold);background:#fff;color:var(--muted);font-size:13px}.share-build-meta{box-sizing:border-box;display:flex;justify-content:flex-end;width:100%;margin:22px 0 0;padding:10px 0 0;border-top:1px solid var(--line);color:#616161;font-size:12px}.share-build-meta a{color:var(--blue)}
@media(max-width:900px){.hero-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.hero-stats{grid-template-columns:1fr 1fr}.bar-row{grid-template-columns:minmax(95px,1.1fr) minmax(35px,1fr) auto;font-size:12px}.table-wrap{max-height:none}#ranking-table thead{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}#ranking-table,#ranking-table tbody,#ranking-table tr,#ranking-table td{display:block;width:100%}#ranking-table tbody{display:grid;gap:10px;padding:8px}#ranking-table tr{border:1px solid var(--line);border-radius:9px;overflow:hidden}#ranking-table td{display:grid;grid-template-columns:minmax(95px,.7fr) minmax(0,1.3fr);gap:8px;border-bottom:1px solid #e8edf1;padding:8px}#ranking-table td:before{content:attr(data-label);font-weight:750;color:#233f5b}#ranking-table td.rank{display:none}}
</style></head><body>
<header><a class="brand" href="https://bettergov.ph/">BetterGov · Budget research</a><div class="eyebrow">Procurement evidence · GAA MPB</div><h1>GAA + DIME + PhilGEPS MPB records</h1><p>GAA lines are the historical MPB baseline. All named DIME MPB contractor records and deduplicated awarded PhilGEPS MPB records are included in the contractor union, even when no exact GAA title/year match exists.</p></header>
<main>
<aside class="notice"><strong>Disclaimer.</strong> These are public-record matches, not findings of wrongdoing. The GAA line count is the historical inventory baseline. Awarded PhilGEPS MPB projects without an exact GAA title/year match are added to the contractor analysis and flagged. A missing exact match is a review question, not proof that funds were omitted. DIME and PhilGEPS values remain source-labelled. Contract award records do not establish completion, payment, quality, or who ultimately benefited. AMO name matches are research leads only.</aside>
<div id="stats" class="hero-stats"></div>
<section class="card"><h2>GAA MPB source inventory</h2><p id="inventory-note" class="lede"></p><p><a href="contractors-gaa-mpb-inventory.csv" download>Download all GAA MPB lines with DIME and PhilGEPS left-join fields (CSV)</a></p></section>
<section class="card"><h2>Top contractors</h2><p class="lede">Contractor records are consolidated across exact normalized company names. Project totals include GAA-linked DIME records, DIME-only MPB records, and awarded PhilGEPS MPB records. Source counts and amounts stay visible separately.</p><div class="controls"><label>Rank contractors by <select id="metric"><option value="projectCount">Number of projects · all sources</option><option value="contractAmountPesos">Total recorded value · DIME + PhilGEPS</option></select></label><label>Filter period <select id="year"><option value="">All project years</option></select></label><input id="search" type="search" placeholder="Find a contractor"></div><div class="viz-grid"><div><div id="chart" class="chart" aria-label="Top contractors chart"></div></div><div class="table-wrap"><table id="ranking-table"><thead><tr><th>Rank</th><th>Contractor</th><th>Projects by source</th><th>DIME contract amount</th><th>PhilGEPS award value</th><th>Recorded value · DIME + PhilGEPS</th><th>SEC company / officers &amp; incorporators</th><th>PhilGEPS membership</th><th>PCAB category / license</th><th>AMO leads</th></tr></thead><tbody id="ranking"></tbody></table></div></div><p id="ranking-note" class="muted small"></p><p class="small muted">GAA allocation, DIME contract values and PhilGEPS award values are distinct source fields. A title/year match is not proof that source scopes are identical. In the current snapshot, no exact title/year projects overlap between DIME and PhilGEPS; if future source rows match, they are consolidated as one project and source amounts remain separately reported.</p></section>
<section id="details" class="card detail"><h2>Contractor MPB records across sources</h2><p class="lede">Select a contractor to inspect every included GAA-linked, DIME-only and PhilGEPS award record. DIME-only and PhilGEPS-only rows carry explicit GAA-match review flags.</p><div id="project-table" class="table-wrap"></div></section>
<section class="card"><h2>Awarded PhilGEPS MPB projects not found in GAA</h2><p id="philgeps-note" class="lede"></p><p class="small">These records have an awardee and award date, and a title that identifies a multi-purpose building or similar facility. They are included in contractor project counts and PhilGEPS award-value totals. The “not found” flag means no exact normalized title/year GAA match; review title variants and source records before concluding the project is absent from the budget.</p><details><summary>Show flagged PhilGEPS awards</summary><div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>Year</th><th>Procurement title</th><th>Awardee</th><th>Award amount</th><th>GAA-link status</th><th>Contract ID</th></tr></thead><tbody id="philgeps-rows"></tbody></table></div></details></section>
<section class="card"><h2>How to read this study</h2><ul class="source-list"><li><strong>Project match:</strong> punctuation, spacing, and case are normalized; title and year must then match exactly. A single DIME candidate is linked to a GAA line. DIME records without a unique exact GAA match are kept as DIME-only contractor projects and flagged. Awarded PhilGEPS MPB projects are also retained when no exact GAA match exists.</li><li><strong>Cross-source contractor consolidation:</strong> contractor rows group named projects from all three sources by exact normalized company name. The same title/year project is counted once when matched across sources; its source-specific evidence remains attached. Similar company names are not fuzzily merged.</li><li><strong>Amounts:</strong> GAA allocation, DIME contract amount and PhilGEPS award value remain separate. DIME and PhilGEPS amounts are not added to GAA allocations. Repeated PhilGEPS source rows use the maximum reported amount once and are flagged when values disagree.</li><li><strong>PhilGEPS membership:</strong> the merchant snapshot records Red or Platinum membership. The PhilGEPS supplier FAQ distinguishes Red and Platinum; Platinum can expire and downgrade. These cache records were scraped in November 2025 and are not current verification. No “Gold” tier appears in this source.</li><li><strong>PCAB license:</strong> the separate PCAB register provides license number, category, government-infrastructure registration, and valid-through date. PCAB categories (such as A, B, AAA) are not PhilGEPS membership tiers. Company matching is exact after name normalization.</li><li><strong>AMO leads:</strong> company names are matched exactly after normalization against the PhilGEPS and AMO relationship records. The cache links companies to an Authorized Managing Officer and may carry public-official or relationship fields. Unconfirmed indirect AMO names are masked with first/last-letter hints; names listed as elected officials in the cache remain readable. This does not prove ownership or control.</li><li><strong>Coverage:</strong> the GAA baseline includes classified MPB source lines for FY2015–FY2019 and FY2020–FY2026. FY2015 uses DBM DPWH capital-outlay PAP titles; its PAP codes are not unique project IDs. <a href="gaa-2015-dpwh-technical.html">Search the parsed FY2015 lines</a>. FY2019 uses the <a href="gaa-2019-dpwh-technical.html">DBM technical DPWH GAA schedule</a>; FY2015 and FY2019 appropriations do not identify contractors, so DIME and PhilGEPS matches remain title/year-based and are not implied by GAA source inclusion. Every GAA line is retained in the downloadable inventory, including lines with no DIME or PhilGEPS match. The contractor ranking includes all named DIME records and deduplicated awarded PhilGEPS MPB records identified in the local caches.</li></ul><p id="source-notes" class="foot">PhilGEPS membership types: <a href="https://notices.philgeps.gov.ph/help1_5.html">PhilGEPS supplier FAQ</a> · <a href="https://open.philgeps.gov.ph/analytics/load/merchantInfo">PhilGEPS merchant search</a> · PhilGEPS open data: <a href="https://philgeps.ebizolution.net/open-data">official Open Data portal</a> · PCAB license records: archived copy of its regular-license register.</p></section>
<script>
let D,S;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),n=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+n(Math.round(Number(v||0)));
fetch('contractors-data/index.json').then(response=>{if(!response.ok)throw new Error('Index unavailable');return response.json()}).then(data=>{D=data;S=D.summary;
const statItems=[[S.unionProjectCount,'GAA lines + unmatched DIME + awarded PhilGEPS MPB records'],[S.gaaMpbLines,'GAA historical MPB source lines'],[S.dimeOnlyProjects,'named DIME MPB records without unique GAA match'],[S.philgepsOnlyProjects,'awarded PhilGEPS MPB records without exact GAA match']];
document.getElementById('stats').innerHTML=statItems.map(([v,l])=>`<div class="stat"><strong>${esc(v)}</strong><span>${esc(l)}</span></div>`).join('');
document.getElementById('inventory-note').textContent=`Union baseline: ${n(S.gaaMpbLines)} GAA MPB lines for FY${D.scope.gaaYears}, plus all ${n(S.dimeNamedContractorRecords)} named DIME MPB contractor records (${n(S.dimeMatchedGaaProjects)} exact GAA title/year matches and ${n(S.dimeOnlyProjects)} without a unique GAA match) and ${n(S.philgepsOnlyProjects)} awarded PhilGEPS MPB records without an exact GAA title/year match = ${n(S.unionProjectCount)} source records. The GAA inventory has ${n(S.gaaUniqueTitleYearLines)} distinct normalized title-year keys; repeated source lines are retained. PhilGEPS exact-title/year links: ${n(S.philgepsExactGaaLines)} GAA lines. Missing joins remain in the source union and are flagged.`;
document.getElementById('philgeps-note').textContent=`${n(S.philgepsKeywordRecords)} raw PhilGEPS keyword rows were deduplicated to ${n(S.philgepsAwardedProjects)} awarded MPB project/title records. ${n(S.philgepsOnlyProjects)} have no exact title/year GAA match and are included in the contractor totals; ${n(S.philgepsExactGaaTitleMatches)} exact PhilGEPS awards joined to GAA lines.`;
document.getElementById('philgeps-rows').innerHTML=(D.philgepsUnlinked||[]).slice(0,500).map(r=>`<tr><td>${esc(r.contractYear||r.year||'—')}</td><td>${esc(r.project)}</td><td>${esc(r.contractor||'—')}</td><td class="num">${peso(r.contractAmountPesos)}</td><td>${esc(r.gaaMatchStatus)}</td><td>${esc(r.contractId||r.philgepsAwardId||'—')}${r.awardValueConflict?'<div class="small muted">Conflicting source values: '+esc((r.reportedAwardAmountsPesos||[]).map(peso).join(' / '))+'</div>':''}</td></tr>`).join('');
document.getElementById('source-notes').insertAdjacentText('beforeend',' Sources: BetterGov integrated GAA project records; DIME project records; PhilGEPS contract records; PhilGEPS registration records; PCAB regular-license records; PhilGEPS and AMO relationship records; SEC contractor registration records and privacy-filtered SEC officer/incorporator entries from the PhilGEPS and AMO relationship records. Values reflect the local cached source snapshot used to build this page.');
const yearSel=document.getElementById('year');
let selected=null,selectedDetail=null;const detailCache=new Map();
function list(){const y=yearSel.value,q=document.getElementById('search').value.toLowerCase().trim();return D.contractors.map(c=>{const ys=y?c.yearStats.find(x=>String(x.year)===y):null,st=ys||c;return {...c,projectCount:st.projectCount,gaaProjectCount:st.gaaProjectCount,dimeOnlyProjectCount:st.dimeOnlyProjectCount,philgepsOnlyProjectCount:st.philgepsOnlyProjectCount,dimeContractAmountPesos:st.dimeContractAmountPesos,philgepsAwardValuePesos:st.philgepsAwardValuePesos,contractAmountPesos:st.contractAmountPesos}}).filter(c=>c.projectCount&&(!q||c.contractor.toLowerCase().includes(q)||c.aliases.some(a=>a.toLowerCase().includes(q)))).sort((a,b)=>Number(b[document.getElementById('metric').value])-Number(a[document.getElementById('metric').value])||a.contractor.localeCompare(b.contractor));}
function render(){const rows=list(),metric=document.getElementById('metric').value,top=rows.slice(0,12),max=Math.max(1,...top.map(r=>Number(r[metric]||0)));document.getElementById('chart').innerHTML=top.length?top.map((r,i)=>`<div class="bar-row"><span class="bar-label" title="${esc(r.contractor)}">${i+1}. ${esc(r.contractor)}</span><span class="track"><span class="fill" style="display:block;width:${100*Number(r[metric]||0)/max}%"></span></span><span class="bar-value">${metric==='projectCount'?n(r[metric]):peso(r[metric])}</span></div>`).join(''):'<p>No matching contractors.</p>';
document.getElementById('ranking').innerHTML=rows.map((r,i)=>{const membership=r.philgepsMembership.length?r.philgepsMembership.map(m=>`${esc(m.membership)}${m.expiryDate?` · exp ${esc(m.expiryDate)}`:''}${m.scrapedAt?`<div class="small muted">scraped ${esc(m.scrapedAt.slice(0,10))}</div>`:''}`).join('<br>'):'No exact-name record';const sec=r.secRecords.length?r.secRecords.map(s=>`${esc(s.company_name||'SEC record')}${s.status?` · ${esc(s.status)}`:''}${s.sec_number?` · ${esc(s.sec_number)}`:''}${s.date_registered?`<div class="small muted">registered ${esc(s.date_registered)}</div>`:''}${s.officers&&s.officers.length?`<div class="small muted">${s.officers.map(o=>`SEC ${esc(o.role||'officer/incorporator')}: ${esc(o.name_display||o.name||'name unavailable')}`).join('<br>')}</div>`:''}`).join('<br>'):'No exact-name SEC record';const pcab=r.pcabLicenses.length?r.pcabLicenses.map(p=>`${esc(p.category||'Category not listed')} · ${esc(p.licenseNumber||'no license no.')}${p.validToDate?`<div class="small muted">valid through ${esc(p.validToDate)} · Gov infra: ${esc(p.governmentInfrastructure||'not listed')}</div>`:''}`).join('<br>'):'No exact-name record';return `<tr data-contractor="${esc(r.contractor)}"><td class="rank" data-label="Rank">${i+1}</td><td data-label="Contractor"><button class="contractor pick" type="button" data-contractor-id="${esc(r.id)}">${esc(r.contractor)}</button>${r.aliases.length?`<div class="small muted">Also recorded as ${esc(r.aliases.join('; '))}</div>`:''}</td><td data-label="Projects by source"><strong>${n(r.projectCount)} total</strong><div class="small muted">GAA-linked ${n(r.gaaProjectCount)} · DIME-only ${n(r.dimeOnlyProjectCount)} · PhilGEPS-only ${n(r.philgepsOnlyProjectCount)}</div></td><td class="num" data-label="DIME contract amount">${peso(r.dimeContractAmountPesos)}</td><td class="num" data-label="PhilGEPS award value">${peso(r.philgepsAwardValuePesos)}</td><td class="num" data-label="Total recorded value">${peso(r.contractAmountPesos)}</td><td data-label="SEC registration">${sec}</td><td data-label="PhilGEPS membership">${membership}</td><td data-label="PCAB category / license">${pcab}</td><td data-label="AMO leads">${r.amoMatches.length?`${r.amoMatches.slice(0,3).map(m=>esc(m.amoName)).join('<br>')}${r.amoMatches.length>3?`<div class="small muted">+${r.amoMatches.length-3} more AMO leads</div>`:''}`:'—'}</td></tr>`}).join('');document.querySelectorAll('.pick').forEach(b=>b.onclick=()=>{selected=b.dataset.contractorId;selectedDetail=null;renderProjects()});document.getElementById('ranking-note').textContent=`${n(rows.length)} contractors shown · ranking and chart are sorted by ${metric==='projectCount'?'number of projects across all sources':'total recorded DIME + PhilGEPS value'}; chart displays the top ${Math.min(12,rows.length)}. Project counts combine source records; exact title/year matches link to GAA where available. Select a contractor for source-level details.`;if(selected)renderProjects();}
async function renderProjects(){const c=D.contractors.find(x=>x.id===selected);const box=document.getElementById('project-table');if(!c){box.innerHTML='<p>Select a contractor in the ranking to inspect MPB records.</p>';return}if(!selectedDetail){box.innerHTML='<p>Loading this contractor’s project records…</p>';try{let projects=detailCache.get(c.id);if(!projects){projects=[];for(const shard of c.detailShards||[]){let payload=detailCache.get(shard);if(!payload){const response=await fetch(`contractors-data/${shard}`);if(!response.ok)throw new Error(`Failed to load ${shard}`);payload=await response.json();detailCache.set(shard,payload)}const entry=payload.entries.find(x=>x.id===c.id);if(entry)projects.push(...entry.projects)}detailCache.set(c.id,projects)}selectedDetail={...c,projects};}catch(error){box.innerHTML='<p>Could not load project details. Please refresh and try again.</p>';return}}const ps=selectedDetail.projects.filter(p=>!yearSel.value||String(p.year||p.contractYear)===yearSel.value);box.innerHTML=`<table><thead><tr><th>Year</th><th>Project · source / GAA status</th><th>Province / municipality</th><th>GAA allocation</th><th>DIME amount</th><th>PhilGEPS award amount and ID</th><th>AMO lead details</th></tr></thead><tbody>${ps.map(p=>`<tr><td>${p.year||p.contractYear||'—'}</td><td>${esc(p.project)}<div class="small muted">${esc(p.recordType)} · ${esc(p.gaaMatchStatus||'')}</div>${p.gaaSource?`<div class="small muted">GAA source: ${esc(p.gaaSource)}</div>`:''}${p.dimeProjectName?`<div class="small muted">DIME title: ${esc(p.dimeProjectName)}</div>`:''}</td><td>${esc([p.province,p.municipality,p.barangay].filter(Boolean).join(' · ')||'—')}</td><td class="num">${p.gaaAllocationPesos?peso(p.gaaAllocationPesos):'—'}</td><td class="num">${p.dimeContractAmountPesos?peso(p.dimeContractAmountPesos):'—'}</td><td>${p.philgepsMatches.length?p.philgepsMatches.map(m=>`${esc(m.awardee||'Awardee unavailable')} · ${peso(m.contractAmountPesos)} · ${esc(m.contractId||'no ID')} · ${esc(m.matchStatus||m.status||'')}`).join('<br>'):'—'}</td><td>${p.amoMatches.length?p.amoMatches.map(m=>`${esc(m.amoName)} · ${esc(m.role)}${m.position?` · ${esc(m.position)}`:''}${m.year?` · ${esc(m.year)}`:''}${m.province?` · ${esc(m.province)}`:''}`).join('<br>'):'No exact AMO-cache company-name match'}</td></tr>`).join('')}</tbody></table>`;document.querySelector('#details h2').textContent=`${c.contractor} · MPB records across sources`;}
document.getElementById('metric').onchange=render;yearSel.onchange=()=>{render();if(selected)renderProjects()};document.getElementById('search').oninput=render;
[...new Set(D.contractors.flatMap(c=>c.years||[]))].sort((a,b)=>a-b).forEach(y=>yearSel.insertAdjacentHTML('beforeend',`<option value="${y}">${y}</option>`));render();
}).catch(error=>{document.getElementById('ranking-note').textContent='Could not load contractor data index.';});
</script></main></body></html>'''


SHARD_LIMIT_BYTES = 8 * 1024 * 1024


def write_contractors_payload(directory: Path, index_data: dict, contractors: list[dict],
                              deferred_stats_fields: tuple[str, ...] = ()):
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob('shard-*.json'):
        old.unlink()
    for old in directory.glob('filter-stats-*.json'):
        old.unlink()

    summaries = []
    entries = []
    entry_bytes = 0
    shard_number = 0

    def flush_shard():
        nonlocal entries, entry_bytes, shard_number
        if not entries:
            return
        shard_number += 1
        name = f'shard-{shard_number:03d}.json'
        (directory / name).write_text(
            json.dumps({'entries': entries}, ensure_ascii=False, separators=(',', ':')),
            encoding='utf-8',
        )
        for entry in entries:
            if name not in summary_by_id[entry['id']]['detailShards']:
                summary_by_id[entry['id']]['detailShards'].append(name)
        entries = []
        entry_bytes = 0

    summary_by_id = {}
    deferred_stats = {field: [] for field in deferred_stats_fields}
    for index, contractor in enumerate(contractors, start=1):
        contractor_id = f'c{index:05d}'
        summary = {key: value for key, value in contractor.items()
                   if key != 'projects' and key not in deferred_stats}
        summary['id'] = contractor_id
        summary['detailShards'] = []
        summaries.append(summary)
        summary_by_id[contractor_id] = summary
        for field in deferred_stats_fields:
            if field in contractor:
                deferred_stats[field].append({'id': contractor_id, field: contractor[field]})

        project_chunks = []
        chunk = []
        chunk_bytes = 128
        for project in contractor.get('projects', []):
            project_bytes = len(json.dumps(project, ensure_ascii=False, separators=(',', ':')).encode('utf-8')) + 1
            if project_bytes + 128 > SHARD_LIMIT_BYTES:
                raise ValueError(f"Single project record exceeds shard limit: {contractor['contractor']}")
            if chunk and chunk_bytes + project_bytes > SHARD_LIMIT_BYTES:
                project_chunks.append(chunk)
                chunk = []
                chunk_bytes = 128
            chunk.append(project)
            chunk_bytes += project_bytes
        if chunk:
            project_chunks.append(chunk)

        for project_chunk in project_chunks:
            entry = {'id': contractor_id, 'projects': project_chunk}
            size = len(json.dumps(entry, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            if entries and entry_bytes + size + 16 > SHARD_LIMIT_BYTES:
                flush_shard()
            entries.append(entry)
            entry_bytes += size + 16
    flush_shard()

    filter_stats_manifest = {}
    for field, records in deferred_stats.items():
        prefix = {'categoryStats': 'category', 'yearStats': 'year',
                  'secRecords': 'sec', 'philgepsMembership': 'philgeps-membership',
                  'pcabLicenses': 'pcab', 'amoMatches': 'amo'}.get(field, field)
        field_shards = []
        chunk = []
        chunk_bytes = len(b'{"entries":[]}')

        def flush_filter_stats():
            nonlocal chunk, chunk_bytes
            if not chunk:
                return
            name = f'filter-stats-{prefix}-{len(field_shards) + 1:03d}.json'
            payload = json.dumps({'entries': chunk}, ensure_ascii=False, separators=(',', ':'))
            size_bytes = len(payload.encode('utf-8'))
            if size_bytes > SHARD_LIMIT_BYTES:
                raise ValueError(f'Filter-stat shard exceeds limit: {name} ({size_bytes} bytes)')
            (directory / name).write_text(payload, encoding='utf-8')
            field_shards.append({'path': name, 'itemCount': len(chunk), 'sizeBytes': size_bytes})
            chunk = []
            chunk_bytes = len(b'{"entries":[]}')

        for record in records:
            record_bytes = len(json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            if record_bytes + len(b'{"entries":[]}') > SHARD_LIMIT_BYTES:
                raise ValueError(f'Single filter-stat record exceeds shard limit: {record["id"]} · {field}')
            if chunk and chunk_bytes + record_bytes + 1 > SHARD_LIMIT_BYTES:
                flush_filter_stats()
            chunk.append(record)
            chunk_bytes += record_bytes + (1 if len(chunk) > 1 else 0)
        flush_filter_stats()
        filter_stats_manifest[field] = field_shards

    index_data['contractors'] = summaries
    if filter_stats_manifest:
        index_data['deferredDataShards'] = filter_stats_manifest
    directory.joinpath('index.json').write_text(
        json.dumps(index_data, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8',
    )
    return {'shardCount': shard_number, 'filterStatsShardCount': sum(map(len, filter_stats_manifest.values())),
            'contractorCount': len(summaries)}


def main():
    data = build()
    OUT.mkdir(exist_ok=True)
    inventory = data.pop('gaaInventory', [])
    inventory_fields = ['year', 'stage', 'project', 'allocationPesos', 'districtId', 'gaaSource',
                        'dimeMatchCount', 'dimeContractors', 'dimeIds', 'dimeContractAmountsPesos',
                        'philgepsMatchCount', 'philgepsAwardees', 'philgepsContractIds']
    for destination in (OUT / 'mpb-historical-contractors-gaa-mpb-inventory.csv', STATIC / 'mpb-historical-contractors-gaa-mpb-inventory.csv'):
        with destination.open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=inventory_fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(inventory)
    contractors = data.pop('contractors', [])
    # Only the web UI's small index and PhilGEPS flagged-award list belong in
    # its index file. Full project details are placed in separate JSON shards.
    index_data = {key: data[key] for key in (
        'generatedAtUtc', 'scope', 'summary', 'matching', 'sourceNotes', 'philgepsUnlinked')
        if key in data}
    index_data['inventoryCsv'] = 'mpb-historical-contractors-gaa-mpb-inventory.csv'
    for key in (
        'philgepsOnlyProjects', 'transparencyOnlyProjects', 'transparencyContractRecords',
        'philgepsLinkedAwards', 'philgepsAmbiguousGaaAwards', 'ambiguousMatches', 'philgepsExactMatches',
        'philgepsUnlinked', 'gaaInventory',
    ):
        data.pop(key, None)
    index_data['dataShardFormat'] = 'mpb-historical-contractors-data/shard-NNN.json; load a contractor detail shard on selection'
    shard_stats = {}
    for destination in (OUT / 'mpb-historical-contractors-data', STATIC / 'mpb-historical-contractors-data'):
        shard_stats = write_contractors_payload(destination, index_data.copy(), contractors)
    html = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MPB contractors moved</title><meta http-equiv="refresh" content="0;url=contractors.html?type=MPB"><link rel="canonical" href="contractors.html?type=MPB"></head><body><main><h1>MPB contractor records moved</h1><p>The consolidated Contractors directory includes an MPB project-type filter.</p><p><a href="contractors.html?type=MPB">Open MPB contractors →</a></p></main><script>location.replace('contractors.html?type=MPB'+location.hash)</script></body></html>'''
    (OUT / 'mpb-historical-contractors.html').write_text(html, encoding='utf-8')
    (STATIC / 'mpb-historical-contractors.html').write_text(html, encoding='utf-8')
    print(json.dumps({**data['summary'], **shard_stats}, indent=2))


if __name__ == '__main__':
    main()
