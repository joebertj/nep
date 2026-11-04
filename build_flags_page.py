#!/usr/bin/env python3
"""Build the off-menu summary of the project records and flags in congress.html."""
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
CONGRESS = STATIC / 'congress-district-review-data.json'
CONGRESS_ALLOCATION = STATIC / 'congress-data.json'

FLAG_GROUPS = {
    'NEP / stage comparison': re.compile(r'potential nep|nep counterpart(?! repeat)|allocation (?:decrease|increase)|implementing office changed|nep → hgab allocation changes', re.I),
    'Documents': re.compile(r'no listed|transparency match not verified', re.I),
    'Cost / allocation': re.compile(r'cost per|high allocation|short printed project range', re.I),
    'Repeats / recurrence': re.compile(r'repeat|repeated allocation|recurrence|doppelgänger|chainage overlap|same-site coordinate candidate', re.I),
    'Location / program / condition': re.compile(r'coordinate falls|out of place|district labels|boundary|same-barangay|good/fair|rcs|road rehabilitation', re.I),
}


def build():
    congress = json.loads(CONGRESS.read_text())
    allocation = json.loads(CONGRESS_ALLOCATION.read_text())
    catalog = congress.get('flagCatalog', [])
    source_projects = congress.get('projects', [])
    projects = []
    group_projects = {name: {} for name in FLAG_GROUPS}
    group_occurrences = Counter()
    label_occurrences = Counter(congress.get('summary', {}).get('flagCounts', {}))
    stage_totals = defaultdict(lambda: {'projectRows': 0, 'allocationPesos': 0})
    for row in source_projects:
        stage_name = 'NEP-only removal candidate' if row.get('recordStage') == 'NEP' else 'HGAB 3rd-reading'
        amount = int((row.get('nepAmountPesos') if stage_name.startswith('NEP') else row.get('amountPesos')) or 0)
        labels = [catalog[i].get('label', '') for i in row.get('flagIds', []) if isinstance(i, int) and i < len(catalog)]
        item = {
            'id': row.get('id', ''),
            'title': row.get('projectName') or '',
            'amountPesos': amount,
            'stage': stage_name,
            'flagCount': len(labels),
            'flagTypes': labels,
        }
        projects.append(item)
        stage_totals[stage_name]['projectRows'] += 1
        stage_totals[stage_name]['allocationPesos'] += amount
        for label in labels:
            matched_group = next((name for name, pattern in FLAG_GROUPS.items() if pattern.search(label)), None)
            if matched_group:
                group_projects[matched_group][item['id']] = item
                group_occurrences[matched_group] += 1
    flag_groups = [
        {
            'name': name,
            'flaggedProjectRows': len(group_projects[name]),
            'recordAllocationPesos': sum(row['amountPesos'] for row in group_projects[name].values()),
            'flagOccurrences': group_occurrences[name],
        }
        for name in FLAG_GROUPS
    ]
    summary = congress.get('summary', {})
    schedule = allocation.get('summary', {})
    # External comparison is a distinct, broader PBC basket; never sum it with
    # the local DPWH project-row cloud because its infrastructure lines overlap.
    pbc_house = {
        'title': 'People’s Budget Coalition (PBC) · FY2027 House bill',
        'url': 'https://ajamontesa.github.io/ph-budget-analysis/hgab-2027-assessment.html',
        'basis': 'House bill as printed for third reading; October 2026. PBC risk-basket taxonomy, not a list of individually flagged project rows.',
        'totalExcludingUnprogrammedPesos': 947_700_000_000,
        'unprogrammedPesos': 112_000_000_000,
        'totalIncludingUnprogrammedPesos': 1_059_700_000_000,
        'dpwhProgramPesos': 587_100_000_000,
        'groups': [
            {'name': 'Programs at high risk of political patronage', 'housePesos': 209_600_000_000, 'nepPesos': 140_100_000_000},
            {'name': 'Political offices', 'housePesos': 42_900_000_000, 'nepPesos': 37_900_000_000},
            {'name': 'Infrastructure requiring project-level disclosure', 'housePesos': 695_200_000_000, 'nepPesos': 686_000_000_000},
        ],
        'lineItems': [
            {'group': 'Programs at high risk of political patronage', 'name': 'DSWD Protective Services (AICS)', 'nepPesos': 33_300_000_000, 'housePesos': 58_100_000_000, 'changePesos': 24_800_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'DOLE TUPAD', 'nepPesos': 14_200_000_000, 'housePesos': 19_000_000_000, 'changePesos': 4_700_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'DOH Medical Assistance Program (MAP, formerly MAIFIP)', 'nepPesos': 24_200_000_000, 'housePesos': 48_200_000_000, 'changePesos': 24_000_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'CHED Tulong Dunong', 'nepPesos': 0, 'housePesos': 1_800_000_000, 'changePesos': 1_800_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'DA Presidential Assistance to Farmers and Fisherfolk', 'nepPesos': 0, 'housePesos': 10_000_000_000, 'changePesos': 10_000_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'Confidential and intelligence funds · all agencies', 'nepPesos': 10_800_000_000, 'housePesos': 10_900_000_000, 'changePesos': 100_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'Financial Assistance to LGUs', 'nepPesos': 37_500_000_000, 'housePesos': 41_600_000_000, 'changePesos': 4_100_000_000},
            {'group': 'Programs at high risk of political patronage', 'name': 'NTF-ELCAC support to barangays', 'nepPesos': 9_700_000_000, 'housePesos': 9_700_000_000, 'changePesos': 0},
            {'group': 'Programs at high risk of political patronage', 'name': 'Growth Equity Fund', 'nepPesos': 10_300_000_000, 'housePesos': 10_300_000_000, 'changePesos': 0},
            {'group': 'Political offices', 'name': 'Office of the President', 'nepPesos': 10_100_000_000, 'housePesos': 10_100_000_000, 'changePesos': 0},
            {'group': 'Political offices', 'name': 'Office of the Vice President', 'nepPesos': 800_000_000, 'housePesos': 800_000_000, 'changePesos': 0},
            {'group': 'Political offices', 'name': 'Congress', 'nepPesos': 27_000_000_000, 'housePesos': 32_000_000_000, 'changePesos': 5_000_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DA farm-to-market roads', 'nepPesos': 16_000_000_000, 'housePesos': 19_600_000_000, 'changePesos': 3_600_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DA and BFAR equipment, postharvest facilities, and cold storage', 'nepPesos': 5_700_000_000, 'housePesos': 5_800_000_000, 'changePesos': 100_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'National Irrigation Administration', 'nepPesos': 46_400_000_000, 'housePesos': 45_200_000_000, 'changePesos': -1_200_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DOH Health Facilities Enhancement Program', 'nepPesos': 14_500_000_000, 'housePesos': 10_100_000_000, 'changePesos': -4_500_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DepEd Basic Education Facilities', 'nepPesos': 30_600_000_000, 'housePesos': 27_500_000_000, 'changePesos': -3_100_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DPWH Asset Preservation Program', 'nepPesos': 76_500_000_000, 'housePesos': 82_600_000_000, 'changePesos': 6_100_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DPWH Network Development Program', 'nepPesos': 176_600_000_000, 'housePesos': 122_000_000_000, 'changePesos': -54_600_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DPWH Bridge Program', 'nepPesos': 44_400_000_000, 'housePesos': 40_900_000_000, 'changePesos': -3_500_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DPWH Flood Management Program', 'nepPesos': 103_500_000_000, 'housePesos': 96_100_000_000, 'changePesos': -7_300_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DPWH Convergence and Special Support Program', 'nepPesos': 157_300_000_000, 'housePesos': 231_400_000_000, 'changePesos': 74_100_000_000},
            {'group': 'Infrastructure requiring project-level disclosure', 'name': 'DPWH Local Program', 'nepPesos': 14_600_000_000, 'housePesos': 14_100_000_000, 'changePesos': -600_000_000},
        ],
        'assistance': [
            {'name': 'DSWD Protective Services (AICS)', 'housePesos': 58_100_000_000, 'nepPesos': 33_300_000_000, 'changePesos': 24_800_000_000},
            {'name': 'DOH Medical Assistance Program (MAP, formerly MAIFIP)', 'housePesos': 48_200_000_000, 'nepPesos': 24_200_000_000, 'changePesos': 24_000_000_000},
        ],
        'institutionalAlternative': {
            'name': 'PhilHealth budgetary support',
            'housePesos': 74_450_000_000,
            'note': 'PBC reports PhilHealth support at ₱74.45B, unchanged from the NEP in the House bill. It recommends shifting MAP/MAIFIP to PhilHealth benefit expansion and DOH hospitals’ zero-balance billing; for AICS, it points to rules-based alternatives such as 4Ps, social pension and the food-stamp program. This is a policy proposal, not a traced transfer.'
        },
        'reallocationContext': 'PBC says the two DPWH Basic Infrastructure Program lump lines, AICS and MAP/MAIFIP together took about 61% of House additions. Separately, about ₱90B moved within the infrastructure basket from network development, bridges, flood management, health facilities and classrooms toward the two DPWH lump lines. These are budget-level comparisons; the report does not trace each peso from a specific cut to a specific addition.',
        'overlapNote': 'The reported ₱1.0597T basket already includes ₱587.1B in DPWH program lines. Our ₱434.745B in HGAB flagged rows sits inside that DPWH subtotal, so it adds project-level evidence, not new appropriations. Adding the two totals would double-count. PBC also notes an internal confidential-funds overlap; see the exact qualification below.',
    }
    pbc_outside_dpwh = pbc_house['totalIncludingUnprogrammedPesos'] - pbc_house['dpwhProgramPesos']
    hgab_flagged_pesos = stage_totals['HGAB 3rd-reading']['allocationPesos']
    schedule_pesos = int(schedule.get('candidateTotalPesos') or 0)
    pbc_house['overlapCheck'] = {
        'pbcOutsideDpwhIncludingUAPesos': pbc_outside_dpwh,
        'pbcOutsideDpwhExcludingUAPesos': pbc_outside_dpwh - pbc_house['unprogrammedPesos'],
        'hgabFlaggedProjectPesos': hgab_flagged_pesos,
        'flaggedBlendIncludingUAPesos': pbc_outside_dpwh + hgab_flagged_pesos,
        'shortOfTrillionPesos': max(0, 1_000_000_000_000 - (pbc_outside_dpwh + hgab_flagged_pesos)),
        'flaggedBlendExcludingUAPesos': pbc_outside_dpwh - pbc_house['unprogrammedPesos'] + hgab_flagged_pesos,
        'shortOfTrillionExcludingUAPesos': max(0, 1_000_000_000_000 - (pbc_outside_dpwh - pbc_house['unprogrammedPesos'] + hgab_flagged_pesos)),
        'fullDpwhSchedulePesos': schedule_pesos,
        'unflaggedDpwhScheduleRows': max(0, int(schedule.get('candidateLineItems') or 0) - int(summary.get('flaggedHgabProjectRows') or 0)),
        'unflaggedDpwhSchedulePesos': max(0, schedule_pesos - hgab_flagged_pesos),
        'fullScheduleReplacementIncludingUAPesos': pbc_outside_dpwh + schedule_pesos,
        'fullScheduleReplacementExcludingUAPesos': pbc_outside_dpwh - pbc_house['unprogrammedPesos'] + schedule_pesos,
        'pbcVsLocalDpwhRoundingDeltaPesos': schedule_pesos - pbc_house['dpwhProgramPesos'],
        'nepOnlyCandidatePesos': stage_totals['NEP-only removal candidate']['allocationPesos'],
        'note': 'For a like-stage blend, remove PBC’s complete rounded DPWH subtotal, then add only HGAB-stage rows flagged by congress.html. NEP-only removal candidates are excluded because they belong to the NEP stage. A second replacement uses the full DPWH candidate schedule to show that the PBC DPWH subtotal matches that schedule within rounding; this recreates PBC’s broad basket and is not a flags-only total.',
        'pbcInternalOverlapNote': 'PBC notes that the Office of the President confidential and intelligence funds are also counted in the all-agency CIF line; it cites a historical overlap of about ₱4.5B but does not give an exact FY2027 overlap amount.',
    }
    pbc_house['nepTotalExcludingUnprogrammedPesos'] = sum(group['nepPesos'] for group in pbc_house['groups'])
    pbc_house['nepTotalIncludingUnprogrammedPesos'] = pbc_house['nepTotalExcludingUnprogrammedPesos'] + pbc_house['unprogrammedPesos']
    data = {
        'generatedAtUtc': datetime.now(timezone.utc).isoformat(),
        'scope': 'All project records and review signals used by static/nep-preview/congress.html: HGAB 3rd-reading rows plus NEP-only removal candidates.',
        'summary': {
            'flaggedProjectRows': int(summary.get('flaggedProjectRows') or len(projects)),
            'flaggedHgabProjectRows': int(summary.get('flaggedHgabProjectRows') or 0),
            'nepOnlyRemovalCandidates': int(summary.get('nepOnlyRemovalCandidates') or 0),
            'recordAllocationPesos': sum(row['amountPesos'] for row in projects),
            'stageTotals': dict(stage_totals),
            'congressScheduleLineItems': int(schedule.get('candidateLineItems') or 0),
            'congressScheduleAllocationPesos': int(schedule.get('candidateTotalPesos') or 0),
            'districtAssignedRows': int(schedule.get('uniquelyAssignedLines') or 0),
            'districtAssignedPesos': int(schedule.get('assignedSourceAmountPesos') or 0),
            'sharedAssignedRows': int(schedule.get('sharedAssignedLines') or 0),
            'unassignedRows': int(schedule.get('unassignedLines') or 0),
            'unassignedPesos': int(schedule.get('unassignedAmountPesos') or 0),
            'flagTypeCounts': dict(sorted(label_occurrences.items(), key=lambda item: (-item[1], item[0]))),
            'flagGroups': flag_groups,
            'reviewFlagCount': sum(row['flagCount'] for row in projects),
        },
        'source': {
            'congressReviewData': 'static/nep-preview/congress-district-review-data.json',
            'congressSchedule': 'static/nep-preview/congress-data.json',
            'method': 'Uses the congress.html reviewed project records and flag catalog directly. Includes both HGAB 3rd-reading rows and NEP-only removal candidates; geographic totals reflect the page’s current assignment summary. Stage-mixed allocation sums are row sums, not a single-stage enacted budget total.'
        },
        'externalBenchmark': pbc_house,
        'projects': projects,
    }
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n'
    html = (ROOT / 'project_documents/flags.html').read_text()
    from uniform_report_menu import apply_page
    html = apply_page(html, 'flags.html')
    for directory in (OUT, STATIC):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'flags-data.json').write_text(serialized)
        (directory / 'flags.html').write_text(html)
    return data['summary']


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
