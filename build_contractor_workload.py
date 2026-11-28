#!/usr/bin/env python3
"""Join dated PhilGEPS awards to DPWH contract and contractor records."""
import csv
import gzip
import json
import re
from bisect import bisect_left
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from import_philgeps_workload_quarters import CODE

from build_general_contractors import DPWH_CONTRACTS_PARQUET, PHILGEPS_V2, parse_dpwh_contractors
from build_contractors import export_parquet, norm

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'
SNAPSHOT = date(2026, 11, 3).toordinal()


def day(value):
    try:
        return date.fromisoformat(str(value)[:10]).toordinal()
    except ValueError:
        return None


def iso(value):
    return date.fromordinal(value).isoformat() if value else None


def contract_key(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')


def main():
    contracts = defaultdict(list)
    known_names = defaultdict(Counter)
    by_contract = {}
    archive = DPWH_CONTRACTS_PARQUET.parents[2] / 'dpwh-contracts-2016-2026.csv.gz'
    with gzip.open(archive, 'rt', encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            key = contract_key(row['contract_id'])
            if not key:
                continue
            parties = {}
            for party in parse_dpwh_contractors(row['contractor']):
                license_id = party['licenseId'].lstrip('0')
                if license_id.isascii() and license_id.isdigit():
                    parties[license_id] = party['name']
                    known_names[license_id][party['name']] += 1
            if not parties:
                continue
            start, finish = day(row['start_date']), day(row['completion_date'])
            status = row['status'].strip().lower()
            completed = finish if status == 'completed' and start and finish and start <= finish <= SNAPSHOT else None
            entry = (start, completed, status, row, parties)
            if key in by_contract:
                by_contract[key] = None
            else:
                by_contract[key] = entry

    for entry in by_contract.values():
        if entry:
            for license_id in entry[4]:
                contracts[license_id].append(entry)

    raw_awards = export_parquet(
        PHILGEPS_V2,
        "award_date IS NOT NULL AND contract_no IS NOT NULL AND business_category = 'Construction Projects'",
        'DISTINCT contract_no, award_date, award_reference_no, awardee_organization_name, award_notice_status, contract_end_date',
    )
    quarter_data = json.loads((ROOT / 'data_sources/philgeps-workload-quarters.json').read_bytes())
    fallback = export_parquet(
        PHILGEPS_V2,
        "award_date IS NOT NULL AND classification ILIKE 'Civil Works%' "
        "AND procuring_entity_name ILIKE '%PUBLIC WORKS AND HIGHWAYS%'",
        'DISTINCT solicitation_no, notice_title, award_title, contract_no, award_date, '
        'award_reference_no, awardee_organization_name, award_notice_status, contract_end_date',
    )
    for row in fallback:
        if by_contract.get(contract_key(row['contract_no'])):
            continue
        codes = set(CODE.findall(' '.join(str(row.get(field) or '') for field in
                                          ('solicitation_no', 'notice_title', 'award_title')).upper()))
        if len(codes) == 1:
            row['contract_no'] = codes.pop()
            raw_awards.append(row)
    raw_awards.extend(quarter_data['rows'])
    offline = STATIC.parents[1] / 'data/parquet/philgeps_contracts.parquet'
    offline_awards = export_parquet(
        offline, 'award_date IS NOT NULL AND philgeps_contract_no IS NOT NULL AND philgeps_awardee_name IS NOT NULL',
        "DISTINCT philgeps_contract_no AS contract_no, award_date, "
        "NULL AS award_reference_no, philgeps_awardee_name AS awardee_organization_name, "
        "philgeps_award_status AS award_notice_status, 'offline' AS source",
    )
    raw_awards.extend(offline_awards)
    live_path = ROOT / 'data_sources/philgeps-workload-live.json'
    live = json.loads(live_path.read_bytes()) if live_path.exists() else {}
    raw_awards.extend(live.get('rows', []))
    coverage = Counter()
    source_keys = defaultdict(set)
    live_refs = defaultdict(set)
    end_dates = defaultdict(set)
    awards = defaultdict(lambda: defaultdict(set))
    for row in raw_awards:
        entry = by_contract.get(contract_key(row['contract_no']))
        if not entry:
            continue
        coverage['idMatchedRecords'] += 1
        status = str(row['award_notice_status'] or '').casefold()
        if any(term in status for term in ('cancel', 'revoke', 'failed')):
            continue
        awarded = day(row['award_date'])
        if not awarded or awarded > SNAPSHOT or (entry[0] and awarded > entry[0]):
            coverage['invalidDateRecords'] += 1
            continue
        awardee = norm(row['awardee_organization_name'] or '')
        for license_id in entry[4]:
            aliases = known_names[license_id]
            names = {norm(alias) for alias in aliases}
            names.update(norm(re.split(r'\s*\(FORMERLY', alias, flags=re.I)[0]) for alias in aliases)
            if awardee and awardee in names:
                reference = str(row['award_reference_no'] or '').strip()
                references = awards[(license_id, contract_key(row['contract_no']))][awarded]
                match_key = (license_id, contract_key(row['contract_no']), awarded)
                source_keys[match_key].add(row.get('source', 'v2'))
                if row.get('source') == 'live':
                    live_refs[match_key].add(reference)
                end = day(row.get('contract_end_date'))
                if end and end >= (entry[0] or awarded):
                    end_dates[match_key].add(end)
                if reference:
                    references.add(reference)

    output = STATIC / 'contractor-workload'
    output.mkdir(exist_ok=True)
    index = []
    shards = defaultdict(dict)
    workload_bands = {label: Counter(awards=0, afterLongProject=0) for label in ("0", "1", "2–4", "5 or more")}
    comparisons = defaultdict(lambda: defaultdict(Counter))
    for license_id, history in contracts.items():
        starts = sorted(start for start, end, _, _, _ in history if start and end)
        finishes = sorted(end for _, end, _, _, _ in history if end)
        ongoing = sorted(start for start, _, status, _, _ in history if start and status == 'ongoing')
        old = sorted(end for start, end, _, _, _ in history if end and end - start > 365)
        beyond_end = []
        posted_by_id = {}
        for _, completion, _, previous, _ in history:
            key = (license_id, contract_key(previous['contract_id']))
            dates = awards.get(key, ())
            if completion and len(dates) == 1:
                ends = end_dates.get((*key, next(iter(dates))), set())
                if len(ends) == 1:
                    posted_by_id[previous["contract_id"]] = iso(next(iter(ends)))
                    if completion > next(iter(ends)):
                        beyond_end.append(completion)
        beyond_end.sort()
        dated_history = sorted(start for start, _, _, _, _ in history if start)
        events = []
        for start, finish, status, row, parties in history:
            days = awards.get((license_id, contract_key(row['contract_id'])), ())
            if len(days) != 1:
                coverage['conflictingDateObservations'] += len(days) > 1
                continue
            awarded = next(iter(days))
            prior_done = bisect_left(finishes, awarded)
            overlaps = bisect_left(starts, awarded) - prior_done
            ongoing_count = bisect_left(ongoing, awarded)
            previous_unknown = bisect_left(dated_history, awarded) - prior_done - overlaps - ongoing_count
            event = {
                'id': row['contract_id'], 'title': row['description'], 'award': iso(awarded),
                'awardReferences': sorted(days[awarded]),
                'start': iso(start), 'completion': iso(finish), 'status': row['status'],
                'office': row['dpwh_office'], 'category': row['category'],
                'amount': float(row['contract_php'] or 0), 'priorCompleted': prior_done,
                'priorLong': bisect_left(old, awarded), 'priorOverlap': overlaps,
                'priorOngoing': ongoing_count, 'priorUnknown': previous_unknown,
                'jointVenture': len(parties) > 1,
            }
            source_key = (license_id, contract_key(row['contract_id']), awarded)
            sources = source_keys.get(source_key, set())
            if 'offline' in sources:
                event['offlineSource'] = True
                coverage['offlineAwardPairs'] += 1
                coverage['offlineOnlyPairs'] += sources == {'offline'}
            if 'v2' in sources:
                coverage['v2AwardPairs'] += 1
            if sources & quarter_data['sources'].keys():
                event['quarterSources'] = sorted(sources & quarter_data['sources'].keys())
                coverage['quarterAwardPairs'] += 1
            if 'live' in sources:
                event['liveReferences'] = sorted(live_refs[source_key])
                coverage['liveAwardPairs'] += 1
            event['priorBeyondEnd'] = bisect_left(beyond_end, awarded)
            coverage['afterPriorBeyondEnd'] += event['priorBeyondEnd'] > 0
            ends = end_dates.get(source_key, set())
            if len(ends) == 1:
                event['postedEnd'] = iso(next(iter(ends)))
                coverage['withPostedEnd'] += 1
                if finish:
                    coverage['withBothDates'] += 1
                    coverage['afterPostedEnd'] += event['completion'] > event['postedEnd']
            events.append(event)
            pending = overlaps + ongoing_count
            band_label = "0" if pending == 0 else "1" if pending == 1 else "2–4" if pending < 5 else "5 or more"
            workload_bands[band_label]["awards"] += 1
            workload_bands[band_label]["afterLongProject"] += event["priorLong"] > 0
            if start and start + 365 <= SNAPSHOT and len(parties) == 1 and event['office'] and event['category'] and event['amount'] > 0:
                outcome_known = finish or status in {'ongoing', 'terminated'}
                if outcome_known:
                    amount = event['amount']
                    band = sum(amount >= bound for bound in (5e6, 20e6, 100e6))
                    key = (event['office'], event['category'], event['award'][:4], band)
                    group = comparisons[key][bool(overlaps + ongoing_count)]
                    group['records'] += 1
                    group['withinYear'] += bool(finish and finish - start <= 365)
        if not events:
            continue
        events.sort(key=lambda event: (event['award'], event['id']), reverse=True)
        name = known_names[license_id].most_common(1)[0][0]
        shard = str(int(license_id) % 64)
        shards[shard][license_id] = {
            'awards': events,
            'history': [
                [row['contract_id'], iso(start), iso(end), row['status'], posted_by_id.get(row['contract_id'])]
                for start, end, _, row, _ in sorted(history, key=lambda item: item[0] or 0, reverse=True)
                if start
            ],
        }
        index.append({
            'id': license_id, 'name': name, 'shard': shard, 'awards': len(events),
            'withOverlap': sum(bool(e['priorOverlap'] + e['priorOngoing']) for e in events),
            'afterLongProject': sum(e['priorLong'] > 0 for e in events),
            'latest': events[0]['award'],
        })

    comparison = {'groups': 0, 'overlap': 0, 'noOverlap': 0}
    weighted_difference = 0
    for groups in comparisons.values():
        no, yes = groups[False], groups[True]
        if not no['records'] or not yes['records']:
            continue
        comparison['groups'] += 1
        comparison['overlap'] += yes['records']
        comparison['noOverlap'] += no['records']
        weighted_difference += yes['withinYear'] - yes['records'] * no['withinYear'] / no['records']
    comparison['differencePercentagePoints'] = (
        100 * weighted_difference / comparison['overlap'] if comparison['overlap'] else None
    )
    index.sort(key=lambda row: (-row['awards'], row['name'], row['id']))
    for shard, records in shards.items():
        write_json(output / f'{shard}.json', records)
    coverage.update({
        'archiveContracts': sum(entry is not None for entry in by_contract.values()),
        'awardObservations': sum(row['awards'] for row in index),
        'withOverlap': sum(row['withOverlap'] for row in index),
        'afterLongProject': sum(row['afterLongProject'] for row in index),
    })
    write_json(output / 'live-notices.json', live.get('rows', []))
    write_json(output / 'index.json', {
        'snapshot': iso(SNAPSHOT), 'quarterSources': quarter_data['sources'], 'live': {k: v for k, v in live.items() if k != 'rows'}, 'coverage': coverage, 'comparison': comparison, 'workloadBands': workload_bands, 'contractors': index,
    })
    print(dict(coverage), comparison, f'{len(index)} contractors')


if __name__ == '__main__':
    main()
