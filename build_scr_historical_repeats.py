"""Compare positive FY2027 SCR allocations with enacted DPWH project lines."""
import json
from collections import defaultdict

from analyze_priority_repeats import classify, previous_rows
from analyze_within_stage_repeats import SCR_DATA, scr_occurrences
from chainage import compare_chainage, compare_tranche, has_bounded_nonoverlap, has_directional_conflict
from hgab_matching import is_fap, normalize
from location_data.location_text import geographic_title
from location_data.project_location_scope import location_conflict, qualified


def match_key(title):
    return classify(title), normalize(geographic_title(title)[0])


def build(historical=None):
    scr = json.loads(SCR_DATA.read_bytes())['rows']
    index = defaultdict(list)
    for row in scr_occurrences(scr):
        title = row['projectName']
        category, key = match_key(title)
        if not category or not key or is_fap(row):
            continue
        place = qualified(title)
        if place and place['province'] and place['municipality']:
            index[category, key].append((row, place))

    if historical is None:
        historical = previous_rows(list(range(2016, 2027)))
    pairs = []
    seen = set()
    for year, records in historical.items():
        for old in records:
            prior_title = old['name']
            if old['amount'] <= 0:
                continue
            candidates = index.get(match_key(prior_title))
            if not candidates:
                continue
            prior_place = qualified(prior_title)
            if not prior_place:
                continue
            for row, place in candidates:
                if not all(place[level] & prior_place[level] for level in ('province', 'municipality')):
                    continue
                title = row['projectName']
                if (location_conflict(title, prior_title) or has_directional_conflict(title, prior_title)
                        or has_bounded_nonoverlap(title, prior_title)
                        or compare_tranche(title, prior_title)['tranche_conflict']):
                    continue
                chainage = compare_chainage(title, prior_title)
                if chainage['chainage_status'] == 'disjoint':
                    continue
                pair_key = row['id'], year, old['source'], prior_title, old['amount']
                if pair_key in seen:
                    continue
                seen.add(pair_key)
                pairs.append({
                    'scrId': row['id'], 'projectName': title, 'program': old['category'], 'office': row['office'],
                    'amountPesos': row['amountPesos'], 'sourceVolume': row['sourceVolume'],
                    'sourcePage': row['sourcePage'], 'sourceUrl': row['sourceUrl'],
                    'sourceEvidence': row['sourceEvidence'], 'gaaYear': year, 'gaaTitle': prior_title,
                    'gaaAmountPesos': old['amount'], 'gaaSource': old['source'],
                    'changePesos': row['amountPesos'] - old['amount'],
                    'chainageStatus': chainage['chainage_status'], 'chainageOverlap': chainage['chainage_overlap'],
                })

    pairs.sort(key=lambda row: (-row['gaaYear'], -row['amountPesos'], row['scrId'], row['gaaSource']))
    return {
        'scope': 'Positive FY2027 SCR DPWH allocations in roads, bridges, multi-purpose buildings and flood control against available enacted FY2016–FY2026 DPWH project lines.',
        'method': 'Exact normalized title after stripping complete trailing station or coordinate metadata. Qualified municipality and province must agree. Direction, location, tranche and disjoint chainage conflicts are excluded.',
        'summary': {
            'comparisonPairs': len(pairs),
            'scrOccurrences': len({row['scrId'] for row in pairs}),
            'years': sorted(historical),
        },
        'rows': pairs,
    }
