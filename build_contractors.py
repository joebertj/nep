#!/usr/bin/env python3
"""Build an auditable GAA MPB contractor study from ODV DIME/PhilGEPS caches."""
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
OUT = ROOT / 'analysis_output'


def norm(value):
    text = unicodedata.normalize('NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def export_parquet(path: Path, where: str, fields: str):
    """Read the local ODV parquet cache through the DuckDB CLI."""
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
           and 2016 <= int(row.get('year') or 0) <= 2026]
    dime = export_parquet(
        PARQUET / 'dime_projects.parquet',
        "lower(coalesce(project_name,'')) LIKE '%multi-purpose%'",
        'project_name, project_year, contract_year, amount, contract_amount, dime_cost, '
        'project_code, global_id, contractor_name, organization_name, contractor_status, '
        'contractor_role, province, city, barangay, source')
    philgeps = export_parquet(
        PARQUET / 'philgeps_contracts.parquet',
        "lower(coalesce(project_name,'') || ' ' || coalesce(philgeps_award_title,'') || ' ' || coalesce(project_description,'')) LIKE '%multi-purpose%'",
        'project_name, project_year, contract_year, amount, contract_amount, '
        'philgeps_contract_no, contract_id, project_id, global_id, contractor_name, '
        'philgeps_awardee_name, contractor_status, philgeps_award_status, contractor_role, '
        'province, municipality, city, barangay, award_date, source')
    amo = json.loads(AMO_CACHE.read_text(encoding='utf-8'))
    merchants = export_parquet(
        MERCHANT_PARQUET,
        "status = 'success' AND name IS NOT NULL",
        'contractor_name, normalized_name, name, reg_status, reg_philgeps_number, '
        'reg_approved_date, reg_philgeps_expiry, scraped_at, status')
    with PCAB_CSV.open(encoding='utf-8-sig', newline='') as stream:
        pcab = list(csv.DictReader(stream))
    return gaa, dime, philgeps, amo, merchants, pcab


def build():
    gaa, dime, philgeps, amo, merchants, pcab = load_sources()
    by_title_year = defaultdict(list)
    for row in dime:
        year = int(row.get('project_year') or row.get('contract_year') or 0)
        title = norm(row.get('project_name'))
        if title and year:
            by_title_year[(year, title)].append(row)

    amo_by_company = defaultdict(list)
    for category in ('top_direct', 'top_indirect'):
        for row in amo.get(category, []):
            for company in row.get('contractors') or []:
                key = norm(company)
                if key:
                    amo_by_company[key].append({
                        'amoName': row.get('pcab_amo') or row.get('full_name'),
                        'role': 'AMO is listed as an elected official in the source cache' if category == 'top_direct' else 'Indirect AMO relationship record',
                        'position': row.get('position'),
                        'year': row.get('year'),
                        'province': row.get('province'),
                        'municipality': row.get('municipality_city'),
                        'relationship': row.get('relationship_type'),
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

    matched, ambiguous = [], []
    for project in gaa:
        key = (int(project.get('year') or 0), norm(project.get('name')))
        candidates = by_title_year.get(key, [])
        if len(candidates) != 1:
            if candidates:
                ambiguous.append({'year': key[0], 'project': project.get('name'), 'candidateCount': len(candidates)})
            continue
        source = candidates[0]
        contractor = str(source.get('contractor_name') or '').strip()
        if not contractor or norm(contractor) in {'no data available', 'unknown', 'n a'}:
            continue
        matched.append({
            'year': key[0], 'project': project.get('name'),
            'gaaAllocationPesos': int(project.get('amountPesos') or 0),
            'gaaSource': project.get('source'), 'contractor': contractor,
            'contractAmountPesos': float(source.get('contract_amount') or source.get('amount') or 0),
            'dimeProjectId': source.get('global_id') or source.get('project_code') or '',
            'dimeProjectName': source.get('project_name'),
            'contractYear': int(source.get('contract_year') or source.get('project_year') or key[0]),
            'contractStatus': source.get('contractor_status') or source.get('status') or '',
            'province': source.get('province') or '', 'municipality': source.get('city') or '',
            'barangay': source.get('barangay') or '',
            'amoMatches': amo_by_company.get(norm(contractor), []),
            'philgepsMembership': merchant_by_name.get(norm(contractor), []),
            'pcabLicenses': pcab_by_name.get(norm(contractor), []),
        })

    groups = defaultdict(list)
    for row in matched:
        groups[norm(row['contractor'])].append(row)
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
        contractor_rows.append({
            'contractor': names[0], 'aliases': names[1:],
            'projectCount': len(projects),
            'contractAmountPesos': round(sum(p['contractAmountPesos'] for p in projects), 2),
            'gaaAllocationPesos': sum(p['gaaAllocationPesos'] for p in projects),
            'years': sorted({p['year'] for p in projects}),
            'amoMatches': amo_matches,
            'philgepsMembership': membership_rows,
            'pcabLicenses': pcab_rows,
            'projects': sorted(projects, key=lambda p: (p['year'], p['project'].casefold())),
        })
    contractor_rows.sort(key=lambda r: (-r['projectCount'], -r['contractAmountPesos'], r['contractor'].casefold()))

    # PhilGEPS keyword rows remain visible as a separate pool unless an exact,
    # same-year title match establishes a GAA project link. Never merge them into
    # the DIME ranking on a loose title similarity alone.
    gaa_keys = {(int(p.get('year') or 0), norm(p.get('name'))) for p in gaa}
    philgeps_exact = []
    for row in philgeps:
        year = int(row.get('project_year') or row.get('contract_year') or 0)
        title = norm(row.get('project_name'))
        awardee = str(row.get('philgeps_awardee_name') or row.get('contractor_name') or '').strip()
        if (year, title) in gaa_keys and awardee:
            philgeps_exact.append({'year': year, 'project': row.get('project_name'), 'contractor': awardee,
                                   'contractAmountPesos': float(row.get('contract_amount') or row.get('amount') or 0),
                                   'contractId': row.get('philgeps_contract_no') or row.get('contract_id') or ''})

    data = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'scope': {'gaaYears': '2016–2018 and 2020–2026', 'gaaMpbRows': len(gaa),
                  'gaaSource': 'ODV integrated-project-data.json · GAA rows classified Multi-purpose building'},
        'summary': {'matchedProjects': len(matched), 'namedContractors': len(contractor_rows),
                    'gaaAllocationPesos': sum(p['gaaAllocationPesos'] for p in matched),
                    'contractAmountPesos': round(sum(p['contractAmountPesos'] for p in matched), 2),
                    'contractAmountsAboveGaaLine': sum(p['contractAmountPesos'] > p['gaaAllocationPesos'] for p in matched),
                    'ambiguousTitleMatches': len(ambiguous), 'philgepsKeywordRecords': len(philgeps),
                    'philgepsExactGaaTitleMatches': len(philgeps_exact)},
        'matching': 'A GAA MPB row is linked only where normalized project title and fiscal year exactly match one DIME row. Ambiguous or approximate matches are excluded.',
        'sourceNotes': {
            'DIME': 'ODV cached DIME project records; contractor and contract amount fields are attributed to the DIME project record.',
            'PhilGEPS': 'ODV PhilGEPS award records. MPB keyword results are not assigned to GAA project rows unless the title and year exactly match.',
            'AMO': 'ODV PhilGEPS/AMO relationship cache. A name match is a lead for review, not proof of ownership, control, benefit, influence, or wrongdoing.',
            'PhilGEPS registration': 'ODV merchant-info cache. Status is Red or Platinum as captured by the source, not a live validity check. The cached merchant records were scraped in November 2025.',
            'PCAB': 'ODV PCAB regular-license CSV. Category, license number, government-infrastructure registration flag, and valid-through date are retained from the source. Exact normalized company-name match only.',
        },
        'contractors': contractor_rows,
        'ambiguousMatches': ambiguous,
        'philgepsExactMatches': philgeps_exact,
        'philgepsUnlinked': [{
            'project': row.get('project_name') or row.get('philgeps_award_title') or '',
            'contractor': row.get('philgeps_awardee_name') or row.get('contractor_name') or '',
            'contractAmountPesos': float(row.get('contract_amount') or row.get('amount') or 0),
            'contractYear': int(row.get('contract_year') or row.get('project_year') or 0),
            'province': row.get('province') or '',
            'contractId': row.get('philgeps_contract_no') or row.get('contract_id') or '',
        } for row in philgeps if (int(row.get('project_year') or row.get('contract_year') or 0), norm(row.get('project_name'))) not in gaa_keys],
    }
    data['summary']['contractorsWithPhilGEPSMembershipRecord'] = sum(bool(c['philgepsMembership']) for c in contractor_rows)
    data['summary']['contractorsWithPCABLicenseRecord'] = sum(bool(c['pcabLicenses']) for c in contractor_rows)
    data['summary']['philgepsUnlinkedRecords'] = len(data['philgepsUnlinked'])
    return data


PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>GAA MPB contractors · BetterGov</title>
<style>
:root{--navy:#00246a;--blue:#0038a8;--gold:#fcd116;--ink:#17212b;--muted:#566575;--line:#d8e1e7;--paper:#f3f6f8;--teal:#087e78}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}header{background:linear-gradient(120deg,var(--navy),var(--blue));color:white;border-bottom:6px solid var(--gold);padding:24px clamp(16px,3vw,40px)}header .brand{display:inline-block;color:#fff;text-decoration:none;font-weight:800;letter-spacing:.02em}header .eyebrow{margin:20px 0 4px;color:var(--gold);text-transform:uppercase;letter-spacing:.12em;font-size:12px;font-weight:800}h1{margin:0;font-size:clamp(28px,4vw,42px);line-height:1.1;color:white}header p{max-width:900px;color:#eef4ff;margin:10px 0 0}main{width:100%;padding:20px clamp(14px,2vw,32px) 42px}.notice{border-left:5px solid var(--gold);background:#fffdf1;border-radius:9px;padding:14px 18px;margin:0 0 18px;color:#36424e}.hero-stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:16px 0}.stat,.card{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 3px 12px #102f3e0b}.stat{padding:16px}.stat strong{display:block;color:var(--navy);font-size:clamp(22px,3vw,30px);font-variant-numeric:tabular-nums}.stat span{display:block;color:var(--muted);font-size:13px}.card{padding:clamp(16px,2vw,24px);margin:18px 0}.card h2{margin:0 0 6px;color:var(--navy);font-size:22px}.lede,.muted{color:var(--muted)}.viz-grid{display:grid;grid-template-columns:1fr;gap:18px;align-items:start}.controls{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.controls input,.controls select,button{font:inherit;padding:9px 11px;border:1px solid #aebdca;border-radius:8px;background:white;color:var(--ink)}.controls input{min-width:220px;flex:1}button{cursor:pointer;color:var(--blue);font-weight:700}.chart{min-height:270px}.bar-row{display:grid;grid-template-columns:minmax(120px,1.2fr) minmax(50px,2fr) auto;gap:9px;align-items:center;margin:9px 0;font-size:13px}.bar-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.track{height:15px;border-radius:20px;background:#e7edf2;overflow:hidden}.fill{height:100%;background:linear-gradient(90deg,#0038a8,#168c86);border-radius:20px}.bar-value{font-weight:750;white-space:nowrap;font-variant-numeric:tabular-nums}table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:14px}th,td{padding:10px 9px;text-align:left;vertical-align:top;border-bottom:1px solid #dce3e8;overflow-wrap:anywhere;word-break:break-word}th{background:#edf3f8;color:#233f5b;position:sticky;top:0;z-index:1}td.num{text-align:right;white-space:normal;font-variant-numeric:tabular-nums}.table-wrap{overflow-x:hidden;overflow-y:auto;max-height:70vh;border:1px solid var(--line);border-radius:9px}.rank{width:48px;color:var(--muted)}.contractor{font-weight:750;color:var(--navy)}.tag{display:inline-block;background:#eef4ff;color:#20477b;border-radius:999px;padding:2px 8px;font-size:12px}.detail{margin-top:18px}.hidden{display:none!important}.source-list li{margin:6px 0}.small{font-size:13px}.foot{border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:13px}.pagination{display:flex;gap:12px;align-items:center;justify-content:flex-end;padding-top:10px}.research-status{max-width:none;margin:18px 0;padding:12px 16px;border-left:4px solid var(--gold);background:#fff;color:var(--muted);font-size:13px}.share-build-meta{box-sizing:border-box;display:flex;justify-content:flex-end;width:100%;margin:22px 0 0;padding:10px 0 0;border-top:1px solid var(--line);color:#616161;font-size:12px}.share-build-meta a{color:var(--blue)}
@media(max-width:900px){.hero-stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.hero-stats{grid-template-columns:1fr 1fr}.bar-row{grid-template-columns:minmax(95px,1.1fr) minmax(35px,1fr) auto;font-size:12px}.table-wrap{max-height:none}#ranking-table thead{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}#ranking-table,#ranking-table tbody,#ranking-table tr,#ranking-table td{display:block;width:100%}#ranking-table tbody{display:grid;gap:10px;padding:8px}#ranking-table tr{border:1px solid var(--line);border-radius:9px;overflow:hidden}#ranking-table td{display:grid;grid-template-columns:minmax(95px,.7fr) minmax(0,1.3fr);gap:8px;border-bottom:1px solid #e8edf1;padding:8px}#ranking-table td:before{content:attr(data-label);font-weight:750;color:#233f5b}#ranking-table td.rank{display:none}}
</style></head><body>
<header><a class="brand" href="https://bettergov.ph/">BetterGov · Budget research</a><div class="eyebrow">Procurement evidence · GAA MPB</div><h1>Who received MPB contracts?</h1><p>Named contractors connected to GAA multi-purpose building projects, with contract values and AMO leads where the records support a link.</p></header>
<main>
<aside class="notice"><strong>Disclaimer.</strong> These are public-record matches, not findings of wrongdoing. The contractor ranking includes only exact normalized project-title and same-year matches between an enacted GAA MPB line and a DIME project record. Contract award records do not establish completion, payment, quality, or who ultimately benefited. AMO name matches are research leads only.</aside>
<div id="stats" class="hero-stats"></div>
<section class="card"><h2>Top contractors</h2><p class="lede">Ranked by number of GAA MPB project lines with an exact DIME title and year match. Switch the chart to contract value; the table retains both measures.</p><div class="controls"><label>Chart metric <select id="metric"><option value="projectCount">Matched MPB projects</option><option value="contractAmountPesos">DIME contract value</option></select></label><label>Filter period <select id="year"><option value="">All GAA years</option></select></label><input id="search" type="search" placeholder="Find a contractor"></div><div class="viz-grid"><div><div id="chart" class="chart" aria-label="Top contractors chart"></div></div><div class="table-wrap"><table id="ranking-table"><thead><tr><th>Rank</th><th>Contractor</th><th>MPB projects</th><th>DIME contract value</th><th>PhilGEPS membership</th><th>PCAB category / license</th><th>AMO leads</th></tr></thead><tbody id="ranking"></tbody></table></div></div><p id="ranking-note" class="muted small"></p><p class="small muted">DIME contract values and GAA allocation amounts come from different records and may cover different scopes or funding periods. ${__OVER__} matched rows have a DIME contract value above the associated GAA line allocation; review those records individually.</p></section>
<section id="details" class="card detail"><h2>Matched MPB project records</h2><p class="lede">Select a contractor in the ranking to inspect its linked GAA lines and DIME records.</p><div id="project-table" class="table-wrap"></div></section>
<section class="card"><h2>PhilGEPS records that still need a GAA link</h2><p id="philgeps-note" class="lede"></p><p class="small">These are MPB keyword results in the ODV PhilGEPS cache. Their project title and fiscal year do not exactly match a GAA MPB line in this snapshot, so they are excluded from the contractor ranking. A title similarity alone is not treated as proof of a match.</p><details><summary>Show unlinked records</summary><div class="table-wrap" style="margin-top:12px"><table><thead><tr><th>Year</th><th>Procurement title</th><th>Awardee</th><th>Contract amount</th><th>Contract ID</th></tr></thead><tbody id="philgeps-rows"></tbody></table></div></details></section>
<section class="card"><h2>How to read this study</h2><ul class="source-list"><li><strong>Project match:</strong> punctuation, spacing, and case are normalized; title and year must then match exactly, and only a single DIME candidate is accepted.</li><li><strong>PhilGEPS membership:</strong> the merchant snapshot records Red or Platinum membership. The PhilGEPS supplier FAQ distinguishes Red and Platinum; Platinum can expire and downgrade. These cache records were scraped in November 2025 and are not current verification. No “Gold” tier appears in this source.</li><li><strong>PCAB license:</strong> the separate PCAB register provides license number, category, government-infrastructure registration, and valid-through date. PCAB categories (such as A, B, AAA) are not PhilGEPS membership tiers. Company matching is exact after name normalization.</li><li><strong>Top contractor:</strong> count is matched GAA project lines. Contract value is summed from DIME contract amounts for those lines; it is not the GAA allocation total.</li><li><strong>AMO leads:</strong> company names are matched exactly after normalization against the ODV PhilGEPS/AMO cache. The cache links companies to an Authorized Managing Officer and may carry public-official or relationship fields. This does not prove ownership or control.</li><li><strong>Coverage:</strong> GAA source rows currently include FY2016–FY2018 and FY2020–FY2026. The project universe and contractor records are incomplete and can change as ODV data is updated.</li></ul><p id="source-notes" class="foot">PhilGEPS membership types: <a href="https://notices.philgeps.gov.ph/help1_5.html">PhilGEPS supplier FAQ</a> · <a href="https://open.philgeps.gov.ph/analytics/load/merchantInfo">PhilGEPS merchant search</a> · PhilGEPS open data: <a href="https://philgeps.ebizolution.net/open-data">official Open Data portal</a> · PCAB license records: ODV cached copy of its regular-license register.</p></section>
<script id="study-data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('study-data').textContent),S=D.summary;
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),n=v=>Number(v||0).toLocaleString('en-PH'),peso=v=>'₱'+n(Math.round(Number(v||0)));
const statItems=[[S.matchedProjects,'GAA MPB lines with exact DIME contractor match'],[D.contractors.length,'named contractors in matched rows'],[peso(S.contractAmountPesos),'DIME contract value across matched rows'],[S.philgepsUnlinkedRecords,'PhilGEPS keyword records not exactly linked to GAA']];
document.getElementById('stats').innerHTML=statItems.map(([v,l])=>`<div class="stat"><strong>${esc(v)}</strong><span>${esc(l)}</span></div>`).join('');
document.getElementById('philgeps-note').textContent=`${n(S.philgepsKeywordRecords)} PhilGEPS records were found by MPB keywords; ${n(S.philgepsExactGaaTitleMatches)} have an exact same-year GAA title link in this snapshot.`;
document.getElementById('philgeps-rows').innerHTML=(D.philgepsUnlinked||[]).slice(0,500).map(r=>`<tr><td>${esc(r.contractYear||'—')}</td><td>${esc(r.project)}</td><td>${esc(r.contractor||'—')}</td><td class="num">${peso(r.contractAmountPesos)}</td><td>${esc(r.contractId||'—')}</td></tr>`).join('');
document.getElementById('source-notes').insertAdjacentText('beforeend',' Sources: BetterGov ODV integrated GAA project records; ODV DIME project parquet cache; ODV PhilGEPS contract parquet cache; ODV PhilGEPS merchant-info cache; ODV PCAB regular-license CSV; ODV PhilGEPS/AMO cache. Values reflect the local cached source snapshot used to build this page.');
const yearSel=document.getElementById('year');[...new Set(D.contractors.flatMap(c=>c.projects.map(p=>p.year)))].sort((a,b)=>a-b).forEach(y=>yearSel.insertAdjacentHTML('beforeend',`<option value="${y}">${y}</option>`));
let selected=null;function list(){const y=yearSel.value,q=document.getElementById('search').value.toLowerCase().trim();return D.contractors.map(c=>{const ps=c.projects.filter(p=>(!y||String(p.year)===y));return {...c,projects:ps,projectCount:ps.length,contractAmountPesos:ps.reduce((a,p)=>a+Number(p.contractAmountPesos||0),0),gaaAllocationPesos:ps.reduce((a,p)=>a+Number(p.gaaAllocationPesos||0),0)}}).filter(c=>c.projectCount&&(!q||c.contractor.toLowerCase().includes(q))).sort((a,b)=>Number(b[document.getElementById('metric').value])-Number(a[document.getElementById('metric').value])||a.contractor.localeCompare(b.contractor));}
function render(){const rows=list(),metric=document.getElementById('metric').value,top=rows.slice(0,12),max=Math.max(1,...top.map(r=>Number(r[metric]||0)));document.getElementById('chart').innerHTML=top.length?top.map((r,i)=>`<div class="bar-row"><span class="bar-label" title="${esc(r.contractor)}">${i+1}. ${esc(r.contractor)}</span><span class="track"><span class="fill" style="display:block;width:${100*Number(r[metric]||0)/max}%"></span></span><span class="bar-value">${metric==='projectCount'?n(r[metric]):peso(r[metric])}</span></div>`).join(''):'<p>No matching contractors.</p>';
document.getElementById('ranking').innerHTML=rows.map((r,i)=>{const membership=r.philgepsMembership.length?r.philgepsMembership.map(m=>`${esc(m.membership)}${m.expiryDate?` · exp ${esc(m.expiryDate)}`:''}${m.scrapedAt?`<div class="small muted">scraped ${esc(m.scrapedAt.slice(0,10))}</div>`:''}`).join('<br>'):'No exact-name record';const pcab=r.pcabLicenses.length?r.pcabLicenses.map(p=>`${esc(p.category||'Category not listed')} · ${esc(p.licenseNumber||'no license no.')}${p.validToDate?`<div class="small muted">valid through ${esc(p.validToDate)} · Gov infra: ${esc(p.governmentInfrastructure||'not listed')}</div>`:''}`).join('<br>'):'No exact-name record';return `<tr data-contractor="${esc(r.contractor)}"><td class="rank" data-label="Rank">${i+1}</td><td data-label="Contractor"><button class="contractor pick" type="button">${esc(r.contractor)}</button>${r.aliases.length?`<div class="small muted">Also recorded as ${esc(r.aliases.join('; '))}</div>`:''}</td><td class="num" data-label="MPB projects">${n(r.projectCount)}</td><td class="num" data-label="DIME contract value">${peso(r.contractAmountPesos)}</td><td data-label="PhilGEPS membership">${membership}</td><td data-label="PCAB category / license">${pcab}</td><td data-label="AMO leads">${r.amoMatches.length?`<span class="tag">${r.amoMatches.length} AMO lead${r.amoMatches.length===1?'':'s'}</span>`:'—'}</td></tr>`}).join('');document.querySelectorAll('.pick').forEach(b=>b.onclick=()=>{selected=b.textContent;renderProjects()});document.getElementById('ranking-note').textContent=`${n(rows.length)} contractors shown · chart displays the top ${Math.min(12,rows.length)} by selected metric. Registration data is shown only where the company name matches exactly. Select a contractor to see project details.`;if(selected)renderProjects();}
function renderProjects(){const c=D.contractors.find(x=>x.contractor===selected);const box=document.getElementById('project-table');if(!c){box.innerHTML='<p>Select a contractor in the ranking to inspect projects.</p>';return}const ps=c.projects.filter(p=>!yearSel.value||String(p.year)===yearSel.value);box.innerHTML=`<table><thead><tr><th>GAA year</th><th>Project</th><th>Province / municipality</th><th>GAA allocation</th><th>DIME contract amount</th><th>DIME status</th><th>AMO lead details</th></tr></thead><tbody>${ps.map(p=>`<tr><td>${p.year}</td><td>${esc(p.project)}<div class="small muted">DIME: ${esc(p.dimeProjectName)}</div></td><td>${esc([p.province,p.municipality,p.barangay].filter(Boolean).join(' · ')||'—')}</td><td class="num">${peso(p.gaaAllocationPesos)}</td><td class="num">${peso(p.contractAmountPesos)}</td><td>${esc(p.contractStatus||'—')}</td><td>${p.amoMatches.length?p.amoMatches.map(m=>`${esc(m.amoName)} · ${esc(m.role)}${m.position?` · ${esc(m.position)}`:''}${m.year?` · ${esc(m.year)}`:''}${m.province?` · ${esc(m.province)}`:''}`).join('<br>'):'No exact AMO-cache company-name match'}</td></tr>`).join('')}</tbody></table>`;document.querySelector('#details h2').textContent=`${selected} · matched MPB projects`;}
document.getElementById('metric').onchange=render;yearSel.onchange=render;document.getElementById('search').oninput=render;render();
</script></main></body></html>'''


def main():
    data = build()
    OUT.mkdir(exist_ok=True)
    (OUT / 'contractors-data.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    html = PAGE.replace('${__OVER__}', str(data['summary']['contractAmountsAboveGaaLine']))
    html = html.replace('__DATA__', json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    html = apply_share_build_meta(html)
    (OUT / 'contractors.html').write_text(html, encoding='utf-8')
    (STATIC / 'contractors-data.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    (STATIC / 'contractors.html').write_text(html, encoding='utf-8')
    print(json.dumps(data['summary'], indent=2))


if __name__ == '__main__':
    main()
