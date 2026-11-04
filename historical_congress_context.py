"""Attach researched historical House identities without changing budget geography."""
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / 'open-data-visualization/static/nep-preview'


def key(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value)) if not unicodedata.combining(c)).lower()
    value = ' '.join(re.findall('[a-z0-9]+', value))
    return 'davao de oro' if value == 'compostela valley' else value


def congress_for_year(year):
    """Election-cohort context, rather than the Congress which enacted the GAA."""
    return 16 if year == 2015 else 17 if year <= 2018 else 18 if year <= 2021 else 19 if year <= 2024 else 20


def attach(seats):
    path = STATIC / 'congress-historical-rosters.json'
    if not path.exists():
        raise FileNotFoundError('Research historical Congress identities before building the historical chart')
    source = json.loads(path.read_text())
    roster = defaultdict(list)
    historical_labels = defaultdict(set)
    current_labels = defaultdict(set)
    photos = defaultdict(list)
    for row in source['members']:
        province = key(row['province'])
        roster[(row['congress'], province, key(row['district']))].append(row)
        historical_labels[(row['congress'], province)].add(key(row['district']))
    for seat in seats:
        current_labels[key(seat['province'])].add(key(seat['districtLabel'].replace(' District', '')))
    for photo in source['portraits']:
        if photo.get('status') == 'verified_image' and (STATIC / photo.get('localUrl', '')).is_file():
            photos[photo['personKey']].append(photo)
    # Detached cities alter the remaining province district even when the
    # province's number of seats stays constant. Hold these earlier geometries.
    detached_city_holds = {('laguna', '1st'): 19, ('laguna', '2nd'): 18, ('cebu', '6th'): 19}
    for seat in seats:
        seat['representativeRosterSourcesByPeriod'] = {}
        seat['representativePortraitSubjectsByPeriod'] = {}
        for year in range(2015, 2028):
            stage = 'HGAB 3rd' if year == 2027 else 'GAA'
            period = f'{year}|{stage}'
            congress = congress_for_year(year)
            seat['representativePhotoCongressByPeriod'][period] = congress
            seat['representativeCongressByPeriod'][period] = congress
            if congress == 20:
                active = seat.get('memberStatus') == 'active'
                seat['representativesByPeriod'][period] = seat['representative'] if active else None
                seat['representativeStatusByPeriod'][period] = 'Current 20th Congress roster snapshot' if active else 'No active member listed in current House roster'
                portrait = None
                if active and seat.get('representativePhotoStatus') == 'verified_image':
                    photo_term = re.search(r'(1[6789]|20)th[ _]Congress', seat.get('representativePhotoOriginalUrl') or '', re.I)
                    portrait = {'url': seat['representativePhotoUrl'], 'originalUrl': seat['representativePhotoOriginalUrl'],
                                'sourceUrl': seat['representativePhotoSourceUrl'], 'status': 'verified_image',
                                'name': seat['representative'], 'photoCongress': int(photo_term[1]) if photo_term else 20,
                                'identityMatch': seat['representativePhotoIdentityStatus'],
                                'checkedAtUtc': seat['representativePhotoVerifiedAtUtc']}
                seat['representativePhotoSourcesByPeriod'][period] = portrait
                seat['representativePhotosByPeriod'][period] = portrait['url'] if portrait else None
                seat['representativePortraitSubjectsByPeriod'][period] = portrait['name'] if portrait else None
                seat['representativeRosterSourcesByPeriod'][period] = [{'name': seat['representative'], 'sourceUrl': seat.get('representativeProfileUrl')}]
                continue
            province = key(seat['province'])
            district = key(seat['districtLabel'].replace(' District', ''))
            historical_province, historical_district = province, district
            # Historical tables separate Taguig's second district from the
            # Taguig–Pateros first district; the current geography groups both.
            alias = province == 'taguig pateros'
            if alias:
                historical_province = 'taguig' if district == '2nd' else 'taguig pateros'
                historical_district = district
            candidates = roster.get((congress, historical_province, historical_district), [])
            changed = not alias and historical_labels.get((congress, province), set()) != current_labels[province]
            changed = changed or congress < detached_city_holds.get((province, district), 0)
            seat['representativeRosterSourcesByPeriod'][period] = candidates
            members = {r['personKey']: r for r in candidates}
            portrait = None
            if changed or not members:
                name = None
                status = ('Historical seat boundaries or numbering differ; member attribution withheld' if changed else
                          'No historical seat with this current district label')
            else:
                name = ' / '.join(row['name'] for row in members.values())
                status = f'{congress}th Congress district roster context'
                if len(members) > 1:
                    status += '; multiple members within this term; no single portrait assigned'
                else:
                    person = next(iter(members.values()))
                    choices = sorted(photos.get(person['personKey'], []), key=lambda p: (
                        p.get('photoCongress') != congress,
                        abs((p.get('photoCongress') or 0) - congress),
                        'cropped' in p.get('fileTitle', '').lower(), p.get('sourceUrl') or ''))
                    if choices:
                        photo = choices[0]
                        portrait = {'url': photo['localUrl'], 'originalUrl': photo['originalUrl'],
                                    'sourceUrl': photo['sourceUrl'], 'status': 'verified_image',
                                    'name': person['name'], 'personKey': person['personKey'],
                                    'photoCongress': photo.get('photoCongress'),
                                    'creator': photo.get('creator'), 'license': photo.get('license'),
                                    'identityMatch': photo['identityMatch'], 'checkedAtUtc': photo.get('checkedAtUtc')}
            seat['representativesByPeriod'][period] = name
            seat['representativeStatusByPeriod'][period] = status
            seat['representativePhotoSourcesByPeriod'][period] = portrait
            seat['representativePhotosByPeriod'][period] = portrait['url'] if portrait else None
            seat['representativePortraitSubjectsByPeriod'][period] = portrait['name'] if portrait else None

    coverage = {}
    audit_rows = []
    for year in range(2015, 2028):
        stage = 'HGAB 3rd' if year == 2027 else 'GAA'
        period = f'{year}|{stage}'
        coverage[period] = {'congress': congress_for_year(year),
            'resolvedDistricts': sum(bool(s['representativesByPeriod'][period]) for s in seats),
            'unresolvedDistricts': sum(not s['representativesByPeriod'][period] for s in seats),
            'portraitDistricts': sum(bool(s['representativePhotosByPeriod'][period]) for s in seats),
            'mappedPortraitDistricts': sum(bool(s['representativePhotosByPeriod'][period]) for s in seats),
            'missingPortraitDistricts': sum(bool(s['representativesByPeriod'][period]) and not s['representativePhotosByPeriod'][period] for s in seats),
            'contextLabel': f'{congress_for_year(year)}th Congress roster context; current allocation geography'}
        for seat in seats:
            photo = seat['representativePhotoSourcesByPeriod'][period] or {}
            audit_rows.append([year, stage, congress_for_year(year), seat['districtId'], seat['district'],
                seat['representativesByPeriod'][period], seat['representativeStatusByPeriod'][period],
                photo.get('name'), photo.get('photoCongress'), photo.get('url'), photo.get('originalUrl'),
                photo.get('sourceUrl'), photo.get('creator'), photo.get('license'), photo.get('identityMatch'),
                photo.get('checkedAtUtc'), ' | '.join(sorted({r['sourceUrl'] for r in seat['representativeRosterSourcesByPeriod'][period] if r.get('sourceUrl')}))])
    with (STATIC / 'integrated-historical-photo-audit.csv').open('w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle)
        writer.writerow(['Fiscal year', 'Stage', 'Roster Congress', 'Current district ID', 'Current district label',
                         'Historical roster member', 'Roster matching status', 'Portrait subject', 'Photograph Congress',
                         'Local image', 'Original image', 'Photograph source', 'Creator', 'License', 'Identity evidence',
                         'Image checked at UTC', 'Roster source'])
        writer.writerows(audit_rows)
    return coverage
