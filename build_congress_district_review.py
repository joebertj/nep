#!/usr/bin/env python3
"""Build the searchable set of HGAB 3rd-reading projects with review flags."""
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from analyze_mpb_proximity import coordinates as parse_coordinates
from build_rcs_pow_review import read_evidence as read_rcs_pow_evidence

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def add_flag(project, label, detail):
    flags = project.setdefault('analysisFlags', [])
    if not any(flag.get('label') == label and flag.get('detail') == detail for flag in flags):
        flags.append({'label': label, 'detail': detail})


def distance_meters(left, right):
    lat1, lon1 = math.radians(left['latitude']), math.radians(left['longitude'])
    lat2, lon2 = math.radians(right['latitude']), math.radians(right['longitude'])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6_371_008.8 * 2 * math.asin(math.sqrt(a))


def caloocan_district_from_title(title):
    """Resolve explicit numbered Caloocan barangays to their legal district."""
    if 'caloocan' not in str(title or '').lower():
        return None
    match = re.search(r'\b(?:barangay|brgy\.?|bgy\.?)\s*(?:no\.?\s*)?(\d{1,3})\b', str(title), flags=re.IGNORECASE)
    if not match:
        return None
    barangay = int(match.group(1))
    if 178 <= barangay <= 188:
        return 'Caloocan City · 3rd District'
    if barangay in {1, 2, 3, 4} or 77 <= barangay <= 85 or 132 <= barangay <= 177:
        return 'Caloocan City · 1st District'
    if 5 <= barangay <= 76 or 86 <= barangay <= 131:
        return 'Caloocan City · 2nd District'
    return None


def quezon_city_district_from_geo(title, geo_row):
    """Preserve Quezon City polygon matches separately from Quezon Province."""
    if 'quezon city' not in str(title or '').lower():
        return None
    ordinal = {
        'first': '1st', 'second': '2nd', 'third': '3rd',
        'fourth': '4th', 'fifth': '5th', 'sixth': '6th',
    }
    for evidence in geo_row.get('geographicEvidence') or []:
        if evidence.get('level') != 'printed-coordinate boundary match':
            continue
        localities = evidence.get('localities') or []
        district = str(evidence.get('district') or '')
        if not any('quezon city' in str(locality).lower() for locality in localities):
            continue
        match = re.search(r'\b(first|second|third|fourth|fifth|sixth)\s+district\b', district, flags=re.IGNORECASE)
        if match:
            return f"Quezon City · {ordinal[match.group(1).lower()]} District"
    return None


def build():
    native = read_json(ROOT / 'hb10858_3rd_dpwh_projects.json')['data']['data']
    coordinate_points = []
    for row in native:
        point = parse_coordinates(row.get('projectName') or '')
        if point.get('status') == 'Usable printed point':
            coordinate_points.append((row, point))
    with (ROOT / 'analysis_output/hb_nep_comparison_3rd.csv').open(encoding='utf-8-sig', newline='') as f:
        comparisons = list(csv.DictReader(f))
    comparison_by_id = {r['hgab_id']: r for r in comparisons if r.get('hgab_id')}
    geo = {r['id']: r for r in read_json(ROOT / 'analysis_output/congress_geographic_attribution_db_3rd.json')['projects']}
    office_changes = {r['hgabProjectId']: r for r in read_json(ROOT / 'analysis_output/dpwh_deo_office_changes.json')['records']}
    mapped = {r['id']: r for r in read_json(ROOT / 'analysis_output/out_of_place_projects.json')['projects']}
    dpwh_data = read_json(STATIC / 'dpwh-data.json')
    assignment = read_json(ROOT / 'analysis_output/congress_leg_insertions.json')
    repeat_data = read_json(ROOT / 'analysis_output/within_stage_repeats.json')
    line_item_queue = read_json(ROOT / 'analysis_output/line_item_review_queue.json')
    nep_only_removals = read_json(ROOT / 'analysis_output/dpwh_removals_3rd.json').get('domestic', {}).get('rows', [])
    cost_data = read_json(ROOT / 'analysis_output/cost_per_km.json')
    historical_repeat_data = read_json(ROOT / 'analysis_output/repeat_nep_hgab_survival.json')
    mpb_analysis = read_json(ROOT / 'analysis_output/mpb_analysis.json')
    rcs_scope_by_code = {row['code']: row for row in read_rcs_pow_evidence() if row.get('code')}

    insertion_rows = {r['hgab_id']: r for r in dpwh_data.get('hbInsertions', []) if r.get('hgab_id')}
    queue_by_id = {r['hgabId']: r for r in line_item_queue.get('rankedOccurrences', []) if r.get('hgabId')}
    assigned_insertions = {}
    for group in assignment.get('districts', []):
        for row in group.get('rows', []):
            if row['id'] in assigned_insertions:
                raise ValueError(f"Insertion {row['id']} assigned to multiple districts")
            assigned_insertions[row['id']] = group

    # Use the strict allocation dataset as the single source for district totals.
    # Congress.html still carries its separate flag-level project records, but
    # its full-district allocation statistic must match the archived ranking.
    allocation_data = read_json(STATIC / 'congress-data.json')
    attribution = str(allocation_data.get('attributionMethod') or '')
    allocation_summary = allocation_data.get('summary') or {}
    required_rules = ('city-jurisdiction-preserved-v1', 'caloocan-numbered-barangay-crosswalk-v1')
    native_total = sum(int(row.get('amountPesos') or 0) for row in native)
    if not all(rule in attribution for rule in required_rules):
        raise ValueError(
            'congress-data.json is missing the current city and Caloocan attribution rules; '
            'regenerate it with analysis/build_congress_allocation_data.py --write first.'
        )
    if (
        int(allocation_summary.get('sourceLineItems') or -1) != len(native)
        or int(allocation_summary.get('sourceTotalPesos') or -1) != native_total
    ):
        raise ValueError(
            'congress-data.json is stale for the current HGAB source rows; '
            'regenerate it with analysis/build_congress_allocation_data.py --write first.'
        )
    district_allocation_totals = {
        row['district']: {
            'amountPesos': int(row.get('totalPesos') or 0),
            'projectCount': int(row.get('lineItems') or 0),
        }
        for row in allocation_data.get('strict', [])
    }

    outlier_rows = defaultdict(list)
    for row in dpwh_data.get('outliers', []):
        if str(row.get('fiscal_year')) != '2027':
            continue
        try:
            key = (row.get('project_name', ''), int(float(row.get('amount') or 0)), row.get('location', ''))
            z = float(row.get('robust_z') or 0)
        except (TypeError, ValueError):
            continue
        outlier_rows[key].append(z)

    repeat_flags = defaultdict(list)
    nep_repeat_flags = defaultdict(list)
    hgab_by_nep_id = defaultdict(list)
    for comparison_row in comparisons:
        if comparison_row.get('nep_id') and comparison_row.get('hgab_id'):
            hgab_by_nep_id[comparison_row['nep_id']].append(comparison_row['hgab_id'])
    for pair in repeat_data.get('pairs', []):
        chainage = pair.get('chainage') or {}
        detail = pair.get('kind', 'Within-stage repeat candidate')
        if pair.get('contextEvidence'):
            detail += ' · ' + pair['contextEvidence']
        if chainage.get('chainage_status'):
            detail += ' · chainage: ' + str(chainage['chainage_status'])
        stage = pair.get('stage')
        for side in ('left', 'right'):
            row = pair.get(side) or {}
            if stage == 'FY2027 HGAB 3rd' and row.get('id'):
                repeat_flags[row['id']].append(detail)
            elif stage == 'FY2027 NEP' and row.get('id'):
                for hgab_id in hgab_by_nep_id.get(row['id'], []):
                    nep_repeat_flags[hgab_id].append(detail + ' · NEP counterpart occurrence is in a within-stage repeat pair.')

    cost_by_id = {row['id']: row for row in cost_data.get('projects', []) if row.get('id')}
    historical_repeats = defaultdict(list)
    for pair in historical_repeat_data.get('comparisonPairs', []):
        retained = pair.get('hgabRetention') or {}
        project_id = retained.get('hgabId')
        if project_id:
            historical_repeats[project_id].append(pair)
    proposal_by_code = {row.get('sourceCode'): row for row in historical_repeat_data.get('proposals', []) if row.get('sourceCode') and row.get('hgabId')}
    mpb_historical_repeats = defaultdict(list)
    for pair in mpb_analysis.get('repeats', []):
        proposal = proposal_by_code.get(pair.get('source_code'))
        if proposal:
            mpb_historical_repeats[proposal['hgabId']].append(pair)
    mpb_coordinate_data = mpb_analysis.get('coordinateProximity', {})
    mpb_project_details = mpb_coordinate_data.get('projectDetails', {})
    mpb_location_pairs = defaultdict(list)
    mpb_close_pairs = set()
    mpb_historical_close = defaultdict(list)
    for pair in mpb_coordinate_data.get('historical', []):
        try:
            distance = float(pair.get('distanceMeters'))
        except (TypeError, ValueError):
            continue
        if distance >= 50:
            continue
        proposal = proposal_by_code.get(pair.get('source_code'))
        if not proposal:
            continue
        detail = (
            f'{pair.get("comparison_year") or "Prior GAA"}: {pair.get("prior_project") or "prior project title unavailable"} '
            f'(₱{int(pair.get("prior_amount") or 0):,}) has a printed point {distance:,.1f} m from this MPB project. '
            f'{pair.get("siteInterpretation") or "Verify the building/site identity and funded scope."} '
            'Nearby printed points do not establish duplicate construction or funding.'
        )
        mpb_historical_close[proposal['hgabId']].append(detail)
    for pair in mpb_coordinate_data.get('current', []):
        left_id = re.search(r'HB10858-\d+-\d+-\d+', pair.get('sourceLabel') or '')
        right_id = re.search(r'HB10858-\d+-\d+-\d+', pair.get('otherSource') or '')
        if not left_id or not right_id:
            continue
        distance = pair.get('distanceMeters')
        if isinstance(distance, (int, float)) and distance < 50:
            mpb_close_pairs.add(tuple(sorted((left_id.group(0), right_id.group(0)))))
        try:
            distance_text = f'{float(distance):,.1f} m apart'
        except (TypeError, ValueError):
            distance_text = 'distance unavailable'
        for project_id, other_id, other_name in (
            (left_id.group(0), right_id.group(0), pair.get('otherProject') or 'paired MPB project'),
            (right_id.group(0), left_id.group(0), pair.get('projectName') or 'paired MPB project'),
        ):
            label = 'MPB same-site coordinate candidate · under 50 m' if isinstance(distance, (int, float)) and distance < 50 else 'MPB same-barangay coordinate pair'
            detail = f'Paired with {other_name} ({distance_text}). {pair.get("siteInterpretation") or "Compare the printed sites and funded scopes."}. {pair.get("proximityReview") or "Site identity and scope remain unverified."} Printed points are not verified building footprints.'
            mpb_location_pairs[project_id].append((label, detail))
    general_close_pairs = defaultdict(list)
    for index, (left_row, left_point) in enumerate(coordinate_points):
        for right_row, right_point in coordinate_points[index + 1:]:
            left_id, right_id = left_row['id'], right_row['id']
            pair_key = tuple(sorted((left_id, right_id)))
            if pair_key in mpb_close_pairs:
                continue
            distance = distance_meters(left_point, right_point)
            if distance > 50:
                continue
            for project_id, other in ((left_id, right_row), (right_id, left_row)):
                general_close_pairs[project_id].append(
                    f'Printed point is {distance:,.1f} m from {other.get("projectName") or "another project"} '
                    f'(₱{int(other.get("amountPesos") or 0):,}). Verify whether these are distinct sites and scopes. '
                    'Close coordinates can reflect a shared site, adjacent facilities, or a reused reference point; '
                    'this is not proof of duplicate funding.'
                )
    rcs_amount_groups = defaultdict(lambda: {'ids': set(), 'offices': set()})
    for row in native:
        title = str(row.get('pap3') or row.get('pap2') or '')
        if 'rainwater collector system' not in title.lower():
            continue
        amount = int(row.get('amountPesos') or 0)
        group = rcs_amount_groups[amount]
        group['ids'].add(row.get('id'))
        if row.get('office'):
            group['offices'].add(row['office'])

    projects = []
    for source in native:
        project_id = source['id']
        compare = comparison_by_id.get(project_id)
        queue_row = queue_by_id.get(project_id)
        if not compare and not queue_row:
            continue
        project = {
            'id': project_id,
            'projectName': source.get('projectName') or '',
            'office': source.get('office') or '',
            'amountPesos': int(source.get('amountPesos') or 0),
            'sourceVolume': source.get('sourceVolume') or '',
            'sourcePage': source.get('sourcePage') or '',
            'pap': source.get('pap3') or source.get('pap2') or source.get('pap1') or '',
            'districts': [],
            'representativeCards': [],
            'analysisFlags': [],
        }

        comparison = (compare or {}).get('comparison') or (queue_row or {}).get('nepStatus', '')
        closest = (compare or {}).get('closest_nep_title') or ''
        similarity = float((compare or {}).get('title_similarity_pct') or 0)
        try:
            delta = int(float((compare or {}).get('amount_delta_pesos') or 0))
            nep_amount = int(float((compare or {}).get('closest_nep_amount_pesos') or 0))
        except (TypeError, ValueError):
            delta, nep_amount = 0, 0
        project['nepComparison'] = {
            'status': comparison,
            'title': closest or None,
            'amountPesos': nep_amount or None,
            'allocationDeltaPesos': delta if compare and compare.get('amount_delta_pesos') else None,
        }
        if comparison == 'No plausible NEP title counterpart; review candidate':
            detail = 'HGAB line has no plausible selected NEP title counterpart; this is a candidate, not a confirmed insertion.'
            if closest:
                detail += f' Closest title: {closest} ({similarity:g}% text similarity).'
            add_flag(project, 'Potential NEP insertion', detail)
            project['insertionCandidate'] = True
        elif comparison == 'Plausible NEP title counterpart; review scope':
            add_flag(project, 'NEP counterpart needs scope review', f'Possible counterpart: {closest or "not identified"} ({similarity:g}% title similarity); verify scope and location.')
        elif comparison == 'Multiple or already paired NEP counterparts; review scope':
            add_flag(project, 'NEP counterpart pairing is ambiguous', f'Multiple or already-paired candidates require one-to-one scope review. Closest title: {closest or "not identified"} ({similarity:g}% title similarity).')
        if delta:
            direction = 'increase' if delta > 0 else 'decrease'
            add_flag(project, f'Allocation {direction}: {abs(delta):,} pesos', f'HGAB allocation changed by ₱{delta:,} from the selected NEP counterpart (NEP ₱{nep_amount:,}; HGAB ₱{project["amountPesos"]:,}).')

        cost = cost_by_id.get(project_id)
        if cost:
            if cost.get('highRateCandidate'):
                add_flag(project, 'High cost per stated meter vs peers', f'₱{cost.get("allocationPerStatedMeter", 0):,.2f}/m; {cost.get("peerRateMultiple", 0):.2f}× peer median across {cost.get("peerRecords", 0)} comparable records ({cost.get("peerBand") or "peer length band"}). This is whole-line allocation divided by stated length; scope, funded extent, width, and work quantities are unverified.')
            if cost.get('graphExtreme'):
                add_flag(project, 'Extreme cost per stated meter vs peers', f'The stated-length rate exceeds the peer-screen upper fence (₱{cost.get("graphUpperFence", 0):,.2f}/m; {cost.get("peerRecords", 0)} peer records). This is a review lead, not evidence of overpricing; verify scope and quantities.')
            if cost.get('costDensityReviewFlag'):
                add_flag(project, 'Cost per meter unavailable · length review', cost.get('costDensityReviewReason') or 'No usable stated length was available for the cost-density screen.')
            if cost.get('rehabGoodFairReview'):
                context = cost.get('assetContextEvidence') or {}
                caution = context.get('caution') or 'Recorded inventory condition is historical and may not reflect present conditions.'
                add_flag(project, 'Road rehabilitation · recorded segment rated Good/Fair', f'{cost.get("recordedConditionDisplay") or "Good/Fair inventory rating"}; {cost.get("surfacingYearDisplay") or "surfacing year unknown"}. Verify current condition and funded work scope. {caution}')
            if cost.get('bridgeGoodFairContextReview'):
                context = cost.get('assetContextEvidence') or {}
                add_flag(project, 'Bridge rated Good/Fair in inventory · assessment date needed', f'{cost.get("recordedConditionDisplay") or "Good/Fair rating"}. The inventory match is an asset-context lead; its assessment date is unavailable, and this does not establish that rehabilitation is unnecessary.')

        # The cross-page review queue is the canonical source for project-level
        # disclosure, POW, photo, RDC, recurrence, and rate flags.
        if queue_row:
            existing_labels = {flag['label'] for flag in project['analysisFlags']}
            for queued_flag in queue_row.get('flags', []):
                flag_id = queued_flag.get('id')
                label = queued_flag.get('label') or flag_id or 'Review flag'
                evidence = queued_flag.get('evidence') or 'See the source report for the flag basis.'
                if flag_id == 'missing_documents':
                    add_flag(project, label, evidence)
                elif flag_id == 'missing_photos' or flag_id == 'missing_rdc' or flag_id == 'missing_pow' or flag_id == 'chainage_overlap' or flag_id == 'historical_title':
                    add_flag(project, label, evidence)
                elif flag_id == 'insertion':
                    if not any(x in existing_labels for x in ('Potential NEP insertion', 'NEP counterpart needs scope review', 'NEP counterpart pairing is ambiguous')):
                        add_flag(project, label, evidence)
                elif flag_id == 'amount_group':
                    if not any(x.startswith('Repeated allocation amount') for x in existing_labels):
                        add_flag(project, label, evidence)
                elif flag_id == 'high_meter_rate':
                    if not any(x == 'High cost per stated meter vs peers' for x in existing_labels):
                        add_flag(project, label, evidence)
                elif flag_id == 'very_short_range':
                    if not any(x.startswith('Cost per meter · verify short printed range') for x in existing_labels):
                        add_flag(project, label, evidence)
                elif flag_id == 'rehab_good_fair':
                    if not any(x.startswith('Road rehabilitation · recorded segment rated Good/Fair') for x in existing_labels):
                        add_flag(project, label, evidence)

        rcs_group = rcs_amount_groups.get(project['amountPesos'])
        if 'rainwater collector system' in project['pap'].lower() and rcs_group and len(rcs_group['offices']) >= 3:
            add_flag(project, 'Uniform RCS allocation amount', f'₱{project["amountPesos"]:,} appears for Rainwater Collector System projects in {len(rcs_group["offices"])} distinct offices ({len(rcs_group["ids"])} project lines). This identifies a repeated allocation tier; site scope, capacity, and local conditions are not validated.')
        rcs_scope = rcs_scope_by_code.get((compare or {}).get('nep_api_id') or '')
        if rcs_scope:
            contexts = rcs_scope.get('contexts') or []
            declared_sites = rcs_scope.get('declaredSiteCount')
            if rcs_scope.get('rowCount'):
                item = rcs_scope.get('item') or 'item description unavailable'
                pct = (float(rcs_scope.get('amount') or 0) / float(rcs_scope.get('allocation') or 1)) * 100
                parsed = f'Parsed leading item: {item} (₱{float(rcs_scope.get("amount") or 0):,.2f}, {pct:.1f}% of the ₱4.2M allocation).'
            else:
                parsed = 'No submitted POW cost rows were extracted for this project in the current scope review.'
            scope_text = f'{len(contexts)} named facility/component contexts' if contexts else 'no named facility/component context extracted'
            if declared_sites is not None:
                scope_text += f'; POW declares {declared_sites} site(s)'
            add_flag(project, 'RCS POW scope evidence · ₱4.2M tier', f'The RCS review screen reports {scope_text}. {parsed} Identical allocation amounts and incomplete extraction do not establish comparable needs, cost, or padding; check the cited POW and site quantities.')
            if rcs_scope.get('powUrl'):
                project['rcsPowUrl'] = rcs_scope['powUrl']

        prior_pairs = historical_repeats.get(project_id, [])
        if prior_pairs:
            examples = []
            for pair in prior_pairs[:3]:
                prior = pair.get('prior_project') or 'prior project title unavailable'
                year = pair.get('comparison_year') or 'prior year'
                status = pair.get('chainage_status') or pair.get('tranche_status') or 'scope not resolved'
                examples.append(f'{year}: {prior} ({status})')
            extra = len(prior_pairs) - len(examples)
            suffix = f'; plus {extra} additional historical comparison(s)' if extra else ''
            add_flag(project, 'Historical project repeat candidate', f'{len(prior_pairs)} historical comparison(s): ' + '; '.join(examples) + suffix + '. Similarity/chainage is a review lead and does not establish duplicate funding.')

        mpb_pairs = mpb_historical_repeats.get(project_id, [])
        if mpb_pairs:
            examples = []
            for pair in mpb_pairs[:3]:
                prior = pair.get('prior_project') or 'prior site/project unavailable'
                year = pair.get('comparison_year') or 'prior year'
                site = pair.get('siteInterpretation') or pair.get('chainage_status') or 'site identity unresolved'
                examples.append(f'{year}: {prior} ({site})')
            extra = len(mpb_pairs) - len(examples)
            suffix = f'; plus {extra} additional comparison(s)' if extra else ''
            add_flag(project, 'MPB historical site or scope repeat candidate', f'{len(mpb_pairs)} historical MPB comparison(s): ' + '; '.join(examples) + suffix + '. Site identity and scope require verification; this is not proof of duplicate funding.')
        for detail in sorted(set(mpb_historical_close.get(project_id, []))):
            add_flag(project, 'Historical GAA coordinate doppelgänger · under 50 m', detail)

        for label, detail in mpb_location_pairs.get(project_id, []):
            add_flag(project, label, detail)
        for detail in sorted(set(general_close_pairs.get(project_id, []))):
            add_flag(project, 'Possible project doppelgänger · coordinates under 50 m apart', detail)
        for mpb_flag in mpb_project_details.get(project_id, {}).get('reviewFlags', []):
            label = mpb_flag.get('label') or ''
            if label in {'Location boundary match unresolved', 'Location boundary review'}:
                add_flag(project, 'MPB ' + label.lower(), mpb_flag.get('detail') or 'The printed coordinate needs boundary review.')

        office_change = office_changes.get(project_id)
        if office_change:
            project['officeAssignmentChange'] = office_change
            add_flag(project, 'Implementing office changed between NEP and HGAB', f'NEP: {office_change["nepOffice"]} → HGAB 3rd: {office_change["hgabOffice"]}. Match status: {office_change["status"]}.')

        outlier_key = (project['projectName'], project['amountPesos'], project['office'])
        for z in outlier_rows.get(outlier_key, []):
            add_flag(project, 'High allocation vs same-category peers', f'FY2027 robust peer screen: robust z-score {z:g}. Allocation amount is not a unit price; verify scope and quantity before comparing.')

        for detail in sorted(set(repeat_flags.get(project_id, []))):
            add_flag(project, 'Within-HGAB repeat candidate', detail + '. Similar title or chainage is a review signal, not proof of duplicate funding.')
        for detail in sorted(set(nep_repeat_flags.get(project_id, []))):
            add_flag(project, 'Within-NEP counterpart repeat candidate', detail + '. Similar title or chainage is a review signal, not proof of duplicate funding.')

        geo_row = geo.get(project_id, {})
        if not compare and queue_row and not geo_row.get('districts') and len(queue_row.get('districts') or []) == 1:
            geo_row = {'status': 'unique', 'districts': queue_row['districts'], 'representatives': queue_row.get('representatives') or []}
        if geo_row.get('status') == 'unique' and len(geo_row.get('districts') or []) == 1:
            project['districts'] = geo_row['districts']
            project['reportDistrict'] = geo_row['districts'][0]
            names = geo_row.get('representatives') or []
            project['representativeCards'] = [{'district': project['reportDistrict'], 'name': name} for name in names]
        elif geo_row.get('status') == 'shared':
            project['geographicAssignmentStatus'] = 'shared'
        else:
            project['geographicAssignmentStatus'] = 'unresolved'

        insertion = insertion_rows.get(project_id)
        assigned_group = assigned_insertions.get(project_id)
        if insertion:
            project['insertionCandidate'] = True
            project['closestNepTitle'] = insertion.get('closest_nep_title') or ''
            project['titleSimilarityPct'] = float(insertion.get('title_similarity_pct') or 0)
            project['insertionDistrictAssigned'] = bool(assigned_group)
            if assigned_group:
                project['reportDistrict'] = assigned_group['district']
                project['districts'] = [assigned_group['district']]
                representative = assigned_group.get('representative') or ''
                project['representativeCards'] = [{'district': assigned_group['district'], 'name': representative}]
            else:
                # Keep insertion candidates out of member reports unless the
                # specific insertion-location review accepted their district.
                project.pop('reportDistrict', None)
                project['districts'] = []
                project['representativeCards'] = []

        # Geographic polygons do not split Antipolo City by barangay. Reapply
        # the manually documented RA 9232 crosswalk for projects explicitly
        # naming an Antipolo 1st District barangay. Keep 2nd-L.D. lines out.
        title = project['projectName']
        first_district_barangay = re.search(
            r'\b(?:barangay|brgy\.? )\s*(bagong nayon|beverly hills|dela paz|mambugan|mayamot|muntindilaw|munting dilao|san isidro|sta\.?\s*cruz|santa cruz)\b',
            title,
            flags=re.IGNORECASE,
        )
        if (
            'antipolo city' in title.lower()
            and first_district_barangay
            and not re.search(r'\b2nd\s*(?:l\.?\s*d\.?|district|legislative district)\b', title, flags=re.IGNORECASE)
        ):
            project['districts'] = ['Antipolo City · 1st District']
            project['reportDistrict'] = 'Antipolo City · 1st District'
            project['representativeCards'] = [{'district': project['reportDistrict'], 'name': 'Puno, Ronaldo V.'}]
            project['geographicAssignmentStatus'] = 'manual statutory barangay crosswalk'

        caloocan_district = caloocan_district_from_title(title)
        if caloocan_district:
            representatives = {
                'Caloocan City · 1st District': 'Malapitan, Oscar G.',
                'Caloocan City · 2nd District': 'Erice, Edgar R.',
                'Caloocan City · 3rd District': 'Asistio, Dean',
            }
            project['districts'] = [caloocan_district]
            project['reportDistrict'] = caloocan_district
            project['representativeCards'] = [{'district': caloocan_district, 'name': representatives[caloocan_district]}]
            project['geographicAssignmentStatus'] = 'manual statutory barangay-number crosswalk'

        quezon_city_district = quezon_city_district_from_geo(title, geo_row)
        if quezon_city_district:
            representatives = {
                'Quezon City · 1st District': 'Atayde, Juan Carlos "Arjo" C.',
                'Quezon City · 2nd District': 'Tulfo, Ralph Wendel P.',
                'Quezon City · 3rd District': 'Pumaren, Franz S.',
                'Quezon City · 4th District': 'Suntay, Jesus "Bong" C.',
                'Quezon City · 5th District': 'Vargas, Patrick Michael D.',
                'Quezon City · 6th District': 'Co-Pilar, Ma. Victoria',
            }
            project['districts'] = [quezon_city_district]
            project['reportDistrict'] = quezon_city_district
            project['representativeCards'] = [{'district': quezon_city_district, 'name': representatives[quezon_city_district]}]
            project['geographicAssignmentStatus'] = 'printed-coordinate Quezon City district boundary match'

        map_row = mapped.get(project_id)
        if map_row:
            project['mapReviewRecord'] = True
            if map_row.get('sharePage'):
                project['sharePage'] = map_row['sharePage']
            if map_row.get('latitude') is not None:
                project['latitude'] = map_row['latitude']
            if map_row.get('longitude') is not None:
                project['longitude'] = map_row['longitude']
            add_flag(project, 'Out of Place map review · printed coordinate', 'This record appears in the Out of Place map screen. Check the project title, printed locality, coordinate, and office context; inclusion in the map is a review lead.')
            if not map_row.get('officeAssignmentChange'):
                add_flag(project, 'Coordinate falls outside its named locality · map review', 'The project coordinate was included in the out-of-place map review. Open the map and verify the printed locality and boundary.')

        if project['analysisFlags']:
            projects.append(project)

    # NEP-only candidates are also part of the DPWH comparison flags, but have
    # no selected HGAB row. Keep them in the unassigned review bucket rather
    # than infer a legislative district from the DEO office.
    for row in nep_only_removals:
        nep_id = str(row.get('nepId') or '')
        if not nep_id:
            continue
        nep_amount = int(row.get('nepPesos') or 0)
        detail = (
            f'No selected HGAB 3rd counterpart for the NEP line (NEP allocation ₱{nep_amount:,}; '
            f'NEP PDF p. {row.get("nepPage") or "unknown"}). This is a removal review candidate, '
            'not a confirmed deletion or budget reduction; renaming, segmentation, or unresolved matching may explain the missing link.'
        )
        projects.append({
            'id': 'NEP-only-removal:' + nep_id,
            'recordStage': 'NEP',
            'projectName': row.get('nepTitle') or '',
            'office': row.get('office') or '',
            'amountPesos': 0,
            'nepAmountPesos': nep_amount,
            'sourceVolume': 'NEP DPWH schedule',
            'sourcePage': row.get('nepPage') or '',
            'pap': '',
            'districts': [],
            'representativeCards': [],
            'nepOnlyRemovalCandidate': True,
            'nepComparison': {'status': 'No selected HGAB counterpart; removal review', 'title': None, 'amountPesos': nep_amount, 'allocationDeltaPesos': None},
            'analysisFlags': [{'label': 'Potential NEP-only removal', 'detail': detail}],
        })

    if len(insertion_rows) != int(assignment.get('domesticCandidateLines', len(insertion_rows))):
        raise ValueError('Domestic insertion count does not reconcile with the assignment source')
    if len(assigned_insertions) != int(assignment.get('assignedCandidateLines', len(assigned_insertions))):
        raise ValueError('District-assigned insertion count does not reconcile with the assignment source')

    projects.sort(key=lambda row: (-int(row.get('amountPesos') or row.get('nepAmountPesos') or 0), str(row.get('projectName') or '')))
    def flag_type(label):
        if label.startswith('Allocation increase:') or label.startswith('Allocation decrease:'):
            return 'NEP → HGAB allocation changes'
        if label.startswith('Repeated allocation amount'):
            return 'Repeated allocation amounts'
        if label.startswith('Out of Place map review'):
            return 'Out of Place map records'
        if label.startswith('Within-HGAB repeat candidate'):
            return 'Within-HGAB repeat candidates'
        return label.split(' · ')[0]

    flag_counts = Counter(flag_type(flag['label']) for row in projects for flag in row['analysisFlags'])
    flag_catalog = []
    flag_ids = {}
    for row in projects:
        ids = []
        for flag in row.pop('analysisFlags'):
            key = (flag['label'], flag.get('detail', ''))
            if key not in flag_ids:
                flag_ids[key] = len(flag_catalog)
                flag_catalog.append({'label': key[0], 'detail': key[1]})
            ids.append(flag_ids[key])
        row['flagIds'] = ids
    assigned_insertion_count = sum(bool(row.get('insertionCandidate') and row.get('insertionDistrictAssigned')) for row in projects)
    domestic_count = len(insertion_rows)
    unassigned_insertion_count = domestic_count - assigned_insertion_count
    payload = {
            'source': 'HGAB 3rd vs NEP comparison, the project-level line-item review queue (DPWH transparency documents, POW, photos, RDC, historical/rate/chainage screens), geographic attribution, DPWH office changes, cost-per-meter and asset-condition screens, peer allocation screens, repeated GAA comparisons, close-coordinate project pairs, MPB location review, and out-of-place map review',
            'method': 'Every listed row has at least one review flag. Close-coordinate doppelgänger candidates are pairs of distinct HGAB 3rd project titles with one unambiguous, sufficiently precise printed point less than 50 metres apart; proximity does not establish a shared site or duplicate work. A district is assigned only from a unique geographic attribution, the accepted LEG insertion-location review, documented statutory barangay crosswalks for Antipolo and explicitly numbered Caloocan barangays, or printed-coordinate matches to Quezon City district polygons. Quezon City is kept separate from Quezon Province. Unresolved/shared rows remain in the unassigned review bucket. Flags are evidence leads, not findings of wrongdoing or confirmed insertions.',
        'summary': {
            'flaggedProjectRows': len(projects),
            'flaggedHgabProjectRows': sum(row.get('recordStage') != 'NEP' for row in projects),
            'nepOnlyRemovalCandidates': len(nep_only_removals),
            'districtAssignedFlaggedProjectRows': sum(bool(row.get('reportDistrict')) for row in projects),
            'unassignedFlaggedProjectRows': sum(not bool(row.get('reportDistrict')) for row in projects),
            'domesticInsertionCandidates': domestic_count,
            'districtAssignedInsertionCandidates': assigned_insertion_count,
            'unassignedInsertionCandidates': unassigned_insertion_count,
            'allPotentialInsertionRecords': sum(r.get('comparison') == 'No plausible NEP title counterpart; review candidate' for r in comparisons),
            'mappedFlagRows': len(mapped),
            'officeChangeRows': len(office_changes),
            'flagCounts': dict(sorted(flag_counts.items())),
        },
        'flagCatalog': flag_catalog,
        'districtAllocationTotals': [
            {'district': district, **totals}
            for district, totals in sorted(district_allocation_totals.items())
        ],
        'projects': projects,
    }
    out = STATIC / 'congress-district-review-data.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    roster_path = STATIC / 'congress-district-roster.json'
    report_page = STATIC / 'congress.html'
    if roster_path.is_file() and report_page.is_file():
        version = hashlib.sha256(out.read_bytes() + roster_path.read_bytes()).hexdigest()[:12]
        page = report_page.read_text(encoding='utf-8')
        for filename in ('congress-district-review-data.json', 'congress-district-roster.json'):
            page = re.sub(
                rf"fetch\('{re.escape(filename)}(?:\?v=[^']*)?'\)",
                f"fetch('{filename}?v={version}')",
                page,
                count=1,
            )
        report_page.write_text(page, encoding='utf-8')
    return payload['summary']


if __name__ == '__main__':
    print(json.dumps(build(), indent=2))
