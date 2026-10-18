#!/usr/bin/env python3
"""Rank current HGAB DPWH allocation occurrences by reproducible screening flags."""
import csv
import hashlib
import json
from collections import defaultdict, Counter
from pathlib import Path
from analyze_priority_repeats import previous_rows, classify
from chainage import compare_chainage, compare_tranche, has_directional_conflict
from hgab_matching import UNMATCHED, is_fap, normalize
from location_data.location_text import geographic_title
from location_data.project_location_scope import qualified, location_conflict

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'analysis_output'
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
GROUP_MIN = 10
OFFICE_MIN = 3


def historical_key(title):
    # Strip only complete trailing station/coordinate metadata; retain all
    # place names, work descriptions, directions, packages and phases.
    return normalize(geographic_title(title)[0])


def build():
    source = OUT / 'hb_nep_comparison_3rd.csv'
    with source.open() as f:
        rows = list(csv.DictReader(f))
    ids = [r['hgab_id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Repeated HGAB occurrence IDs cannot be ranked independently')
    cost_source = OUT / 'cost_per_km.json'
    cost_data = json.loads(cost_source.read_text())
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if not any(s['file'] == source.name and s['sha256'] == source_hash for s in cost_data['sources']):
        raise ValueError('Rebuild cost-per-meter data before ranking: HGAB source hash differs')
    lengths = {r['id']: r for r in cost_data['projects']}
    prior26, prior25 = previous_rows()
    history = defaultdict(list)
    for year, records in [(2026, prior26), (2025, prior25)]:
        for record in records:
            history[(classify(record['name']), historical_key(record['name']))].append({**record, 'year': year})
    groups = defaultdict(list)
    for row in rows:
        row['amountPesos'] = int(row['amountPesos'])
        if row['office'].strip():
            groups[(row['pap3'], row['amountPesos'])].append(row)
    attribution = {r['id']: r for r in json.loads((OUT / 'congress_geographic_attribution_db_3rd.json').read_text())['projects']}
    ranked = []
    for row in rows:
        if is_fap(row):
            continue  # Foreign-assisted schedules have a separate comparison.
        title = row['projectName']
        flags = []
        length = lengths.get(row['hgab_id'])
        cautions = []
        if length:
            if length['projectName'] != title or length['amountPesos'] != row['amountPesos']:
                raise ValueError('Cost-per-meter occurrence disagrees with native HGAB row')
            if length['lengthMeters'] is None:
                cautions.append('No usable extracted length; cannot calculate a defensible stated-meter rate. This is an evidence gap, not an extra ranking point.')
            elif length['lengthMeters'] < 10:
                cautions.append(f'Printed range implies {length["lengthMeters"]:g} meters; verify source notation and funded extent before interpreting a rate. No high-rate point awarded.')
            elif length['highRateCandidate']:
                flags.append({'id': 'high_meter_rate', 'label': 'High allocation per stated meter',
                              'evidence': f'₱{length["allocationPerStatedMeter"]:,.2f}/stated meter; {length["peerRateMultiple"]:g}× the ₱{length["typicalPeerRate"]:,.2f} peer median among {length["peerRecords"]} same-category, same-structure ({length.get("rateStructureGroup",length["category"])}), same-PAP, same-surface/condition-context, same-length-band records ({length["peerBand"]}). Exceeds both 2× median and Q3 + 1.5× IQR; funded scope and quantities unverified.',
                              'summaryFinding': 'cost-per-km'})
                if length['graphExtreme']:
                    cautions.append('Extreme rate excluded from rate charts; retained here for denominator and scope review. Not verified overpricing.')
            elif length['typicalPeerRate'] is None:
                cautions.append('Insufficient comparable peers; no high-rate conclusion or point.')
        if length and length.get('rehabGoodFairReview'):
            context=length['assetContextEvidence']
            flags.append({'id':'rehab_good_fair','label':'Rehabilitation on recorded Good/Fair segment',
                'evidence':f'Full matched road range was assessed {length["recordedConditionDisplay"]}; section {context["sectionId"]}. Later deterioration, structural work and scope differences require review; this is not proof the rehabilitation is unnecessary.',
                'summaryFinding':'cost-per-km'})
        if length and length.get('bridgeGoodFairContextReview'):
            cautions.append('Bridge inventory records Good/Fair condition but no assessment date. Verify the date and work scope; no dated-condition point awarded.')
        if length and length.get('recentSurfacingReview'):
            context=length['assetContextEvidence']
            flags.append({'id':'recent_surfacing','label':'Pavement work after recent recorded surfacing',
                'evidence':f'Full matched range has recorded last-surfacing year(s) {length["surfacingYearDisplay"]}, within {context["recentSurfacingWindowYears"]} budget years of FY{context["budgetYear"]}. Screening threshold, not engineering service life; verify earlier and proposed quantities.',
                'summaryFinding':'cost-per-km'})
        if row['comparison'] == UNMATCHED:
            flags.append({'id': 'insertion', 'label': 'Potential HGAB insertion',
                          'evidence': 'No plausible NEP counterpart identified by current native matching; original-page review required.'})
        group = groups[(row['pap3'], row['amountPesos'])]
        offices = sorted({r['office'] for r in group})
        if row['amountPesos'] > 0 and len(group) >= GROUP_MIN and len(offices) >= OFFICE_MIN:
            flags.append({'id': 'amount_group', 'label': 'Repeated allocation amount',
                          'evidence': f'Exact ₱{row["amountPesos"]:,} in this PAP: {len(group)} HGAB occurrences across {len(offices)} named implementing offices.',
                          'groupCount': len(group), 'officeCount': len(offices), 'pap': row['pap3']})
        matches = []
        context = qualified(title)
        if context and context['province'] and context['municipality']:
            for old in history.get((classify(title), historical_key(title)), []):
                old_context = qualified(old['name'])
                if not old_context or not old_context['province'] or not old_context['municipality']:
                    continue
                if not context['province'].intersection(old_context['province']) or not context['municipality'].intersection(old_context['municipality']):
                    continue
                chainage = compare_chainage(title, old['name'])
                if (location_conflict(title, old['name']) or has_directional_conflict(title, old['name'])
                    or compare_tranche(title, old['name'])['tranche_conflict']
                    or chainage['chainage_status'] == 'disjoint'):
                    continue
                matches.append({'year': old['year'], 'title': old['name'], 'amountPesos': old['amount'],
                                'source': old['source'], 'chainage': chainage})
        if matches:
            flags.append({'id': 'historical_title', 'label': 'Historical GAA title recurrence',
                          'evidence': 'Same normalized full title after trailing metadata removal, qualified town/province agreement; not proof of duplicate work.'})
            if any(m['chainage']['overlaps'] for m in matches):
                flags.append({'id': 'chainage_overlap', 'label': 'Explicit historical chainage overlap',
                              'evidence': 'At least one accepted historical title counterpart has positive-length overlap between stated ranges.'})
        if not flags:
            continue
        names = attribution.get(row['hgab_id'], {})
        ranked.append({'hgabId': row['hgab_id'], 'projectName': title, 'program': row['pap3'],
                       'office': row['office'], 'region': row['region'], 'amountPesos': row['amountPesos'],
                       'flagCount': len(flags), 'flags': flags, 'historicalMatches': matches,
                       'evidenceCautions': cautions,
                       'lengthReview': ({k: length.get(k) for k in ['category', 'lengthMeters', 'lengthStatus', 'lengthMethod', 'allocationPerStatedMeter', 'typicalPeerRate', 'peerRateMultiple', 'peerRecords', 'peerBand', 'highRateCandidate', 'graphExtreme', 'titleStatedLanes', 'allocationPerTitleLaneMeter', 'inventoryEffectiveLanes', 'allocationPerInventoryLaneMeterProxy', 'allocationPerInventoryAssetLaneMeter', 'laneRateStatus', 'laneInventoryEvidence', 'surfaceDisplay', 'recordedConditionDisplay', 'surfacingYearDisplay', 'surfacePeerGroup', 'rehabGoodFairReview', 'recentSurfacingReview', 'bridgeGoodFairContextReview', 'assetContextEvidence']} if length else None),
                       'sourceVolume': row['sourceVolume'], 'sourcePage': row['sourcePage'],
                       'nepStatus': row['comparison'], 'representatives': names.get('representatives', []),
                       'districts': names.get('districts', [])})
    ranked.sort(key=lambda r: (-r['flagCount'], -r['amountPesos'], r['hgabId']))
    for i, row in enumerate(ranked, 1):
        row['rank'] = i
    sources = [source, OUT / 'congress_geographic_attribution_db_3rd.json',
               cost_source,
               ROOT.parent / 'open-data-visualization/data/parquet/parsed_dpwh_2026.parquet',
               ROOT.parent / 'open-data-visualization/data/parquet/budget_2025.parquet',
               ROOT / 'location_data/philippine_locations.sqlite']
    result = {'scope': 'Domestic DPWH HGAB 3rd-reading occurrences only; not a ranking of the entire national budget.',
              'ranking': 'Flag count descending, allocation pesos descending, occurrence ID ascending for exact ties.',
              'method': {'amountGroupMinimumOccurrences': GROUP_MIN, 'amountGroupMinimumNamedOffices': OFFICE_MIN,
                         'amountGroupScope': 'Identical PAP and positive exact peso amount; counts are allocation occurrences, not certified distinct construction contracts.',
                         'historicalYears': [2025, 2026],
                         'historicalMatch': 'Identical full normalized title after complete trailing metadata removal; same qualified municipality/province; direction/location/tranche conflict and disjoint stated chainage excluded.',
                         'weights': 'One point per flag type. Multiple historical years do not add points.',
                         'highMeterRate': cost_data['highRateScreen']['method'],
                         'laneEvidence': 'Title lane rates, inventory lane estimates and existing-bridge asset estimates are separate contextual measures. None adds a ranking point or replaces a missing funded length. Lane and station evidence is retained in lengthReview.',
                         'conditionAndSurfacing': cost_data['laneCost']['assetContext'],
                         'evidenceGaps': 'Missing length, sub-10m printed ranges and insufficient peers are cautions, not points. Extreme rates require denominator/scope review and are omitted from rate charts.',
                         'summaryCoverage': 'Nine summary findings are not nine independent line-item flags. RCS equal amounts use the amount-group flag; MPB is a program scope; INSPIRE is outside this DPWH queue. Length gaps and very short printed ranges are evidence cautions. Historical recurrence and overlap support the repeat finding.',
                         'dependence': 'Historical recurrence and chainage overlap are related indicators; scores are descriptive triage, not independent evidence or probabilities.',
                         'limitations': ['Uniform packages can be legitimate. Exact appropriation amounts are not unit costs.',
                                        'Strict historical matching misses paraphrased titles and unresolved locations; no flag means insufficient evidence, not clearance.',
                                        'The prior-year search uses locally available DPWH road, bridge, building and flood records, not every agency/year.',
                                        'Matching/parser errors can produce insertion flags. Top 25 overlap other findings; do not sum them as losses.',
                                        'Current office, representative, role and party do not contribute any points.']},
              'summary': {'sourceOccurrences': len(rows), 'flaggedOccurrences': len(ranked),
                          'flagTypes': dict(Counter(f['id'] for r in ranked for f in r['flags'])),
                          'flagCountDistribution': dict(Counter(r['flagCount'] for r in ranked)),
                          'top25Occurrences': min(25, len(ranked))},
              'top25': ranked[:25], 'rankedOccurrences': ranked,
              'sources': [{'file': str(p.relative_to(ROOT.parent)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources]}
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    (OUT / 'line_item_review_queue.json').write_text(serialized)
    (STATIC / 'line-item-review-queue.json').write_text(serialized)
    return result


def render(data, table, esc):
    rows = data['top25']
    graph = '<figure><figcaption>Top 25 · flag count (teal) and allocation (orange); same ranked order in both panels</figcaption><svg class="evidence-graphic" style="max-height:620px" viewBox="0 0 1150 640" role="img" aria-label="Top 25 line items ranked by flag count then allocation"><text x="45" y="20">Rank / screening flags</text><text x="650" y="20">Allocation · billions of pesos</text>'
    max_amount = max((r['amountPesos'] for r in rows), default=1)
    max_flags = max((r['flagCount'] for r in rows), default=1)
    for i, row in enumerate(rows):
        y = 40 + i * 23
        graph += f'<text x="10" y="{y+12}" font-size="12">{row["rank"]}</text><rect x="45" y="{y}" width="{row["flagCount"]*500/max_flags}" height="15" fill="#087e78"><title>{esc(row["projectName"])}: {row["flagCount"]} flags</title></rect><text x="{55+row["flagCount"]*500/max_flags}" y="{y+12}" font-size="12">{row["flagCount"]}</text><rect x="650" y="{y}" width="{400*row["amountPesos"]/max_amount}" height="15" fill="#b65b09"><title>{esc(row["projectName"])}: ₱{row["amountPesos"]:,}</title></rect><text x="1060" y="{y+12}" font-size="11">{row["amountPesos"]/1e9:.3f}B</text>'
    graph += '</svg></figure>'
    rendered = []
    for row in rows:
        evidence = ' | '.join(f['label'] + ': ' + f['evidence'] for f in row['flags'])
        history = ' | '.join(f'GAA {m["year"]}: {m["title"]} · ₱{m["amountPesos"]:,} · {m["source"]}' + (f' · overlap {m["chainage"]["chainage_overlap"]}' if m['chainage']['overlaps'] else '') for m in row['historicalMatches'])
        rendered.append([row['rank'], row['projectName'], row['program'], row['office'], row['flagCount'],
                         row['amountPesos'], evidence, ' | '.join(row['evidenceCautions']) or 'No additional length caution from this screen; source and scope review still required', history or 'No qualifying historical title link established',
                         row['sourceVolume'] + ' · p. ' + row['sourcePage']])
    body = '<p>One row per domestic DPWH HGAB 3rd-reading allocation occurrence. Seven reproducible flag types include cost-per-meter, recorded condition and prior-surfacing screens. More qualifying flags rank first; larger allocation breaks ties. The nine summary findings are broader investigative themes, not nine points available to every project. Missing or suspect lengths are shown as evidence cautions. This is an investigation queue, not a finding of wrongdoing. Other agency schedules do not yet have equivalent combined screen coverage.</p>'
    body += graph + table(['Rank', 'HGAB project', 'Program', 'Implementing office', 'Screening flags', 'HGAB allocation pesos', 'Flag evidence', 'Evidence cautions · no extra points', 'Historical counterpart evidence', 'HGAB source'], rendered)
    body += '<h3>How the ranking is calculated</h3><ol><li><strong>Potential insertion:</strong> the current matcher identifies no plausible NEP counterpart; ambiguous links and FAPs are excluded from this flag.</li><li><strong>Repeated allocation amount:</strong> the same exact positive amount occurs in the same PAP at least 10 times across at least 3 named implementing offices. This includes amounts such as ₱5M when the group qualifies; roundness alone adds no point.</li><li><strong>Historical title recurrence:</strong> a FY2025 or FY2026 GAA title agrees after case/punctuation normalization and removal of complete trailing station/coordinate metadata. A matching qualified municipality and province is required. Work descriptions, directions, packages and phases remain. Conflicting locations/tranches and disjoint stated chainages are excluded.</li><li><strong>Historical chainage overlap:</strong> an accepted historical counterpart has explicit, positive-length overlap of stated construction ranges. This adds one scope indicator, not proof of duplicate paid work.</li></ol><p>Each type contributes one point; multiple historical years do not increase the score. Historical recurrence and chainage overlap are related signals, so the count is not a statistical probability or independent-evidence score. Exact ranking ties use the source occurrence ID. Missing historical links can reflect conservative matching, incomplete local coverage or unresolved names.</p><p>Standard packages, phased work and legitimate amendments can produce these signals. Names, roles and party affiliations add no points. Input hashes and all ranked rows are available in <a href="line-item-review-queue.json" download>the full ranking JSON</a>. The CSV exports all 25 displayed rows with their evidence. Amounts overlap the findings above; do not add them as alleged losses.</p>'
    body += '<h3>Condition and prior-surfacing flags</h3><p>One point for rehabilitation/reconstruction/major repair when the full matched road range was assessed Good/Fair in a known pre-budget year. One point for pavement work when the full matched range has a positive recorded last-surfacing year within five budget years. Widening, approaches, slope/drainage and off-carriageway scope are excluded. Unknowns and partial coverage add no point. The five-year window is a screening choice, not an engineering service-life standard. Bridge Good/Fair context without an assessment date remains a review lead and earns no dated-condition point. Later deterioration or different funded components may justify the work. Condition, recent surfacing and historical recurrence can be related; points are not independent evidence or probabilities.</p>'
    body += '<h3>New cost-per-meter flag</h3><p>One additional point when allocation per stated meter exceeds both twice the peer median and Q3 + 1.5 × IQR. Peers share the work category, structure group, matched surface/condition/assessment-year context, exact official PAP and a data-derived length band, with at least 20 records whose stated lengths are at least 10 meters. No fixed 100-meter cutoff is used. Extreme rates remain in this review table with a caution but are excluded from rate charts. Missing lengths, sub-10-meter printed ranges and insufficient peers add no point. This flag does not establish overpricing: width, terrain, structures, quantities and funded extent remain unverified. <a href="cost-per-km.html#length-density-groups">See full rate and grouping methodology</a>.</p>'
    body += '<h3>How all nine summary findings relate to this queue</h3>' + table(['Summary finding', 'Treatment in the line-item ranking'], [
        ['1 · Equal RCS packages', 'Repeated-amount flag if its existing thresholds qualify; no extra point for belonging to RCS. Needs weighting requires installation evidence.'],
        ['2 · HGAB insertion candidates', 'Potential-insertion flag; matching uncertainty remains explicit.'],
        ['3 · Multi-purpose buildings', 'MPB records qualify through the same flags as other work. Program membership earns no point.'],
        ['4 · Recurring project titles', 'Historical title recurrence and explicit chainage overlap; related indicators, not independent evidence.'],
        ['5 · Allocation clustering', 'Repeated-amount flag. The office-level road/flood association is not an additional individual-project flag.'],
        ['6 · INSPIRE', 'Outside this domestic DPWH queue; investigated on its own agency page.'],
        ['7 · Length and chainage gaps', 'Evidence caution only; no rate inferred and no ranking point for missing information.'],
        ['8 · Allocation per stated meter', 'High relative-rate flag using category, PAP and length-band peers.'],
        ['9 · Very short printed ranges', 'Evidence caution for sub-10-meter ranges; verify denominator before a high-rate conclusion. Shortness alone earns no point.']])
    return body


if __name__ == '__main__':
    print(json.dumps(build()['summary'], indent=2))
