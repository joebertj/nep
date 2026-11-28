"""Join dated public blacklisting entries to 2026 onward procurement activity."""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data_sources'
OUT = ROOT.parent / 'open-data-visualization/static/nep-preview/contractor-workload'
FIRST = '2026-01-01'


def name_key(value):
    return re.sub(r'[^A-Z0-9]', '', re.sub(r'\bGEN\b', 'GENERAL', value.upper()).replace('&', ' AND '))


def date(value):
    return value if isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) else None


def in_window(day, record):
    return record['start'] <= day and (record['end'] is None or day <= record['end'])


def main():
    snapshot = json.loads((DATA / 'gppb-blacklisting-2026-11-28.json').read_bytes())
    windows, temporary, registrations = defaultdict(list), defaultdict(list), defaultdict(set)
    for row in snapshot['rows']:
        key = name_key(row['blacklisted_entity'])
        if not key or key.isdigit():
            continue
        registration = (row['philgeps_reg_no'] or '').strip()
        if registration not in {'', '-'}:
            registrations[key].add(registration)
        start, end = date(row['start_date']), date(row['end_date'])
        permanent = row['category'] == 'PERMANENT_BLACKLISTED_ENTITIES'
        if row['category'] == 'TEMPORARY_REMOVED_BLACKLISTED_ENTITIES':
            temporary[key].append((date(row['temp_start_date']), date(row['temp_end_date'])))
            continue
        if not start or (not permanent and (not end or end < FIRST or end < start)) or row['is_removed_by_system']:
            continue
        window = {'name': row['blacklisted_entity'], 'start': start, 'end': None if permanent else end,
                  'agency': row['procuring_entity'], 'order': row['blacklisting_order_no'],
                  'portalCreated': date(row.get('portal_record_created_date')),
                  'type': 'Permanent blacklisting' if permanent else 'Blacklisting'}
        if window not in windows[key]:
            windows[key].append(window)

    index = json.loads((OUT / 'index.json').read_bytes())
    directory = defaultdict(list)
    for row in index['contractors']:
        directory[name_key(row['name'])].append(row['id'])

    activities = json.loads((DATA / 'workload-procurement-activity.json').read_bytes())
    ffjj_review = json.loads((DATA / 'workload-ffjj-date-review.json').read_bytes())
    for case in ffjj_review:
        activities.append({
            'name': 'FFJJ Construction', 'date': case['bidOpening'], 'type': 'Bid opening',
            'title': case['title'], 'reference': case['reference'],
            'agency': 'DA Philippine Rural Development Project Scale-up',
            'source': 'World Bank procurement plan and bidder list',
            'url': case['bidSource'], 'bidderSource': case['awardSource'],
        })
    for dataset in ('quarters', 'live'):
        path = DATA / f'philgeps-workload-{dataset}.json'
        payload = json.loads(path.read_bytes())
        for record in payload['rows']:
            if record['award_date'] < FIRST or re.search(r'cancel|revoke|fail|withdraw', record['award_notice_status'], re.I):
                continue
            source = record['source']
            reference = record['award_reference_no']
            url = (f'https://philgeps.gov.ph/Indexes/viewAwardNotice/{reference}' if source == 'live'
                   else payload['sources'][source]['url'])
            activities.append({'name': record['awardee_organization_name'], 'date': record['award_date'],
                               'type': 'Award', 'title': record['contract_no'], 'reference': record['contract_no'],
                               'agency': 'DPWH', 'source': f'PhilGEPS award {reference}', 'url': url})

    contractors = {}
    for key, periods in windows.items():
        if len(registrations[key]) > 1 or len(directory[key]) != 1:
            continue
        relevant = [a for a in activities if name_key(a['name']) == key and
                    a['type'] in {'Award', 'Bid', 'Bid opening'} and date(a['date']) and FIRST <= a['date'] <= snapshot['snapshot']]
        activity = {}
        for event in sorted(relevant, key=lambda item: item['source']):
            day = event['date']
            may_be_lifted = any((not start or start <= day) and (not end or day <= end)
                                for start, end in temporary[key])
            matching = [] if may_be_lifted else [i for i, period in enumerate(periods) if in_window(day, period)]
            activity[(event['reference'], day, event['type'])] = {
                **event, 'windows': matching, 'temporaryRemoval': may_be_lifted,
            }
        contractors[directory[key][0]] = {
            'periods': periods, 'activity': sorted(activity.values(), key=lambda e: e['date'], reverse=True),
        }

    payload = {'snapshot': snapshot['snapshot'], 'source': snapshot['source'],
               'reportRows': len(snapshot['rows']), 'contractors': contractors, 'ffjjReview': ffjj_review}
    (OUT / 'sanctions.json').write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    flagged = [event for row in contractors.values() for event in row['activity'] if event['windows']]
    print(len(contractors), 'directory licenses matched to periods;', len(flagged), 'dated overlaps')
    for event in flagged:
        print(event['name'], event['date'], event['reference'])


if __name__ == '__main__':
    main()
