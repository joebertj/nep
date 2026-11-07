#!/usr/bin/env python3
"""Collect sourced historical House identities and reusable public portraits.

Run with BeautifulSoup available, using downloaded Wikipedia HTML and Commons
imageinfo responses in --cache. No historical identity is inferred from today's
member occupying the same seat. A photograph's Congress is distinct from the
Congress in which its subject represented a district.
"""
import argparse
import concurrent.futures
import json
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
STATIC = ROOT.parent / 'open-data-visualization/static/nep-preview'


def norm(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(value)) if not unicodedata.combining(c)).lower()
    return ' '.join(re.findall('[a-z0-9]+', value))


def name_tokens(value):
    return [x for x in norm(value).split() if len(x) > 1 and x not in
            {'rep', 'representative', 'hon', 'dr', 'jr', 'sr', 'ii', 'iii', 'iv'}]


def plain(value):
    if '<' not in (value or ''):
        return value or ''
    return BeautifulSoup(value or '', 'html.parser').get_text(' ', strip=True)


def expanded_rows(table):
    pending = {}
    for row in table.find_all('tr'):
        cells = {}
        for col, (cell, remaining) in list(pending.items()):
            cells[col] = cell
            if remaining == 1:
                del pending[col]
            else:
                pending[col] = (cell, remaining - 1)
        col = 0
        for cell in row.find_all(['td', 'th'], recursive=False):
            while col in cells:
                col += 1
            for offset in range(int(cell.get('colspan', 1))):
                cells[col + offset] = cell
                span = int(cell.get('rowspan', 1))
                if span > 1:
                    pending[col + offset] = (cell, span - 1)
            col += int(cell.get('colspan', 1))
        yield cells


def read_roster(cache, congress):
    soup = BeautifulSoup((cache / f'congress-{congress}.html').read_text(), 'html.parser')
    table = next(t for t in soup.find_all('table') if t.find('tr') and
                 t.find('tr').get_text(' ', strip=True) == 'Province / City District Representative Party Term Bloc')
    result = {}
    for cells in expanded_rows(table):
        if not all(i in cells for i in (0, 1, 2)):
            continue
        district = cells[1].get_text(' ', strip=True)
        if not re.fullmatch(r'Lone|\d+(?:st|nd|rd|th)', district):
            continue
        province = re.sub(r'\s*\[[^]]+\]', '', cells[0].get_text(' ', strip=True)).strip()
        cell = cells[2]
        links = [a for a in cell.select('a[href]') if '/wiki/' in a['href'] and
                 not any(x in a['href'] for x in ('#', '/wiki/File:', '/wiki/Template:'))]
        notes = []
        for a in cell.select('sup a[href]'):
            note = soup.find(id=a['href'].rsplit('#', 1)[-1])
            if note:
                notes.append(note.get_text(' ', strip=True))
        if links:
            link = links[0]
            name = link.get_text(' ', strip=True)
            article = unquote(link['href'].split('/wiki/', 1)[-1]).replace('_', ' ')
            profile_url = 'https://en.wikipedia.org/wiki/' + article.replace(' ', '_')
        else:
            name_cell = BeautifulSoup(str(cell), 'html.parser')
            for reference in name_cell.select('sup'):
                reference.decompose()
            name = name_cell.get_text(' ', strip=True)
            if not name or re.search(r'\bVacant\b|\bVacancy\b', name, re.I):
                continue
            article = 'roster-name:' + norm(name)
            profile_url = None
        item = {'congress': congress, 'province': province, 'district': district,
                'name': name, 'personKey': article, 'profileUrl': profile_url,
                'sourceUrl': f'https://en.wikipedia.org/wiki/{congress}th_Congress_of_the_Philippines',
                'termNotes': notes}
        result[(province, district, article)] = item
    return list(result.values())


def read_photos(cache):
    pages = {}
    for path in sorted(cache.glob('commons-*.json')):
        pages.update(json.loads(path.read_text()).get('query', {}).get('pages', {}))
    photos = []
    for page in pages.values():
        info = page.get('imageinfo', [{}])[0]
        meta = info.get('extmetadata', {})
        text = lambda key: plain(meta.get(key, {}).get('value', ''))
        title, desc, artist = page['title'], text('ImageDescription'), text('Artist')
        term = re.search(r'\b(1[6789]|20)th Congress\b', title + ' ' + desc, re.I)
        if not term or not re.search('House of Representatives|Congress of the Philippines', artist, re.I):
            continue
        if not ('portrait' in (title + ' ' + desc).lower() or title.startswith('File:Rep.')):
            continue
        if not info.get('url', '').lower().split('?')[0].endswith(('.jpg', '.jpeg', '.png', '.webp')):
            continue
        credit = meta.get('Credit', {}).get('value', '')
        sources = [a['href'] for a in BeautifulSoup(credit, 'html.parser').select('a[href]')]
        if not sources or not text('LicenseShortName'):
            continue
        name = re.sub(r'^File:|\.[^.]+$', '', title)
        name = re.sub(r'\([^)]*\)|\b(?:Rep\.|Representative|Official Portrait|Portrait of|during the|Congress|1[6789]th|20th)\b', ' ', name, flags=re.I)
        name = re.sub(r'^Rep\.\s*', '', name).strip(' -')
        url = urlsplit(info['url'])
        photos.append({'photoCongress': int(term[1]), 'fileTitle': title,
                       'nameFromFile': name, 'description': desc, 'creator': artist,
                       'license': text('LicenseShortName'), 'licenseUrl': text('LicenseUrl'),
                       'originalSources': sources,
                       'sourceUrl': info.get('descriptionurl') or 'https://commons.wikimedia.org/wiki/' + title.replace(' ', '_'),
                       'originalUrl': urlunsplit((url.scheme, url.netloc, url.path, '', ''))})
    return photos


def score_name(aliases, photo):
    candidate = name_tokens(photo['nameFromFile'])
    suffixes = {'jr', 'sr', 'ii', 'iii', 'iv', 'v'}
    def suffix(value):
        return next((word for word in norm(value).split() if word in suffixes), None)
    candidate_suffix = suffix(photo['nameFromFile'])
    scores = []
    for alias in aliases:
        alias_suffix = suffix(alias)
        if candidate_suffix and alias_suffix and candidate_suffix != alias_suffix:
            continue
        tokens = name_tokens(alias)
        if len(tokens) < 2 or len(candidate) < 2:
            continue
        a, b = set(tokens), set(candidate)
        if a == b:
            scores.append(100)
        elif a <= b or b <= a:
            scores.append(95)
        elif tokens[-1] == candidate[-1] and min(len(tokens[0]), len(candidate[0])) >= 5 and (
                tokens[0].startswith(candidate[0]) or candidate[0].startswith(tokens[0])):
            scores.append(90)
        elif re.search(r'\b' + re.escape(norm(alias)) + r'\b', norm(photo.get('description', ''))):
            scores.append(98)
    return max(scores, default=0)


def caption_identity(photo, members):
    """Use an explicit province AND district in the official portrait caption."""
    desc = norm(photo.get('description', ''))
    for word, ordinal in [('first', '1st'), ('second', '2nd'), ('third', '3rd'), ('fourth', '4th'),
                          ('fifth', '5th'), ('sixth', '6th'), ('seventh', '7th'), ('eighth', '8th')]:
        desc = re.sub(r'\b' + word + r'\b', ordinal, desc)
    possible = []
    for row in members:
        if row['congress'] != photo['photoCongress']:
            continue
        province = norm(row['province'])
        district = norm(row['district'])
        if not re.search(r'\b' + re.escape(province) + r'\b', desc):
            continue
        if not re.search(r'\b' + district + r'\b', desc):
            continue
        possible.append((len(province), row['personKey']))
    if not possible:
        return None
    longest = max(length for length, _ in possible)
    people = {person for length, person in possible if length == longest}
    return next(iter(people)) if len(people) == 1 else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, default=ROOT / 'data_sources/congress-online-cache')
    parser.add_argument('--download', action='store_true', help='Cache and verify identified images locally')
    parser.add_argument('--missing-people-only', action='store_true', help='Download one portrait per still-unpictured person')
    parser.add_argument('--delay', type=float, default=1.1, help='Seconds between image requests')
    args = parser.parse_args()
    members = [r for congress in (16, 17, 18, 19) for r in read_roster(args.cache, congress)]
    alias_path = ROOT / 'data_sources/historical-congress-identity-aliases.json'
    if alias_path.exists():
        for identity in json.loads(alias_path.read_text()):
            aliases = {norm(a) for a in identity['aliases']}
            for row in members:
                if norm(row['name']) in aliases:
                    row.update(personKey=identity['personKey'], identitySourceUrl=identity['sourceUrl'])
    named_articles = defaultdict(set)
    for row in members:
        if row['profileUrl']:
            named_articles[norm(row['name'])].add(row['personKey'])
    for row in members:
        choices = named_articles[norm(row['name'])]
        if row['personKey'].startswith('roster-name:') and len(choices) == 1:
            row['personKey'] = next(iter(choices))
    people = defaultdict(set)
    term_people = defaultdict(set)
    for row in members:
        people[row['personKey']].add(row['name'])
        if not row['personKey'].startswith('roster-name:'):
            people[row['personKey']].add(row['personKey'])
        term_people[row['congress']].add(row['personKey'])
    photos = read_photos(args.cache)
    unmatched = []
    by_person = defaultdict(list)
    for photo in photos:
        scored = [(score_name(people[person], photo), person) for person in term_people[photo['photoCongress']]]
        matches = [(score, person) for score, person in scored if score >= 90]
        if len(matches) != 1:
            person = caption_identity(photo, members)
            if not person:
                unmatched.append({**photo, 'possiblePeople': matches})
                continue
            score = 100
            photo['identityMatch'] = 'official_portrait_caption_and_historical_seat'
        else:
            score, person = matches[0]
        photo['personKey'] = person
        photo.setdefault('identityMatch', 'unique_historical_roster_name_match')
        photo['identityScore'] = score
        by_person[person].append(photo)
        people[person].add(photo['nameFromFile'])

    still_unmatched = []
    for photo in unmatched:
        matches = [person for person in term_people[photo['photoCongress']] if score_name(people[person], photo) >= 90]
        if len(matches) == 1:
            person = matches[0]
            photo.update(personKey=person, identityMatch='portrait_alias_confirmed_by_other_official_caption')
            by_person[person].append(photo)
        else:
            still_unmatched.append(photo)
    unmatched = still_unmatched

    # Current verified portraits can illustrate the same individual in earlier
    # terms. Their photo Congress stays separate from the historical office term.
    current = json.loads((STATIC / 'congress-district-roster.json').read_text())
    verified = json.loads((STATIC / 'congress-portrait-verification.json').read_text())['images']
    for row in current['districts']:
        candidate = {'nameFromFile': row.get('name', ''), 'description': row.get('sourceName', '')}
        matches = [person for person, aliases in people.items() if score_name(aliases, candidate) >= 90]
        image = verified.get(row.get('photoUrl'), {})
        if len(matches) != 1 or image.get('status') != 'verified_image':
            continue
        person = matches[0]
        term = re.search(r'(1[6789]|20)th[ _]Congress', unquote(row['photoUrl']), re.I)
        by_person[person].append({'personKey': person, 'photoCongress': int(term[1]) if term else 20,
            'nameFromFile': row['name'], 'originalUrl': row['photoUrl'],
            'sourceUrl': row.get('portraitSourceUrl') or row.get('profileUrl'),
            'originalSources': [row.get('profileUrl')], 'localUrl': image['localUrl'],
            'status': 'verified_image', 'identityMatch': 'unique_historical_roster_name_match',
            'creator': 'House of Representatives of the Philippines',
            'license': 'Official House portrait; original source retained'})

    biography_path = args.cache / 'biography-portraits.json'
    linked_people = {r['personKey'] for r in members if r['profileUrl']}
    if biography_path.exists():
        for row in json.loads(biography_path.read_text()):
            person = row['requestedPersonKey']
            info = row.get('commonsPage', {}).get('imageinfo', [{}])[0]
            meta = info.get('extmetadata', {})
            field = lambda key: plain(meta.get(key, {}).get('value', ''))
            width, height = row['original'].get('width', 0), row['original'].get('height', 1)
            title = row['fileTitle']
            if not info.get('url') or not field('LicenseShortName') or not .4 <= width / height <= 1.4:
                continue
            if re.search('coat.of.arms|flag.of|logo|seal.of', title, re.I):
                continue
            if person not in linked_people and not re.search(
                    r'House of Representatives|Congress of the Philippines', field('Artist'), re.I):
                continue
            term = re.search(r'(1[6789]|20)th[ _]Congress', title + ' ' + field('ImageDescription'), re.I)
            raw_url = urlsplit(info['url'])
            original_url = urlunsplit((raw_url.scheme, raw_url.netloc, raw_url.path, '', ''))
            by_person[person].append({'personKey': person, 'photoCongress': int(term[1]) if term else None,
                'fileTitle': title, 'nameFromFile': row['pageTitle'],
                'description': field('ImageDescription'), 'originalUrl': original_url,
                'sourceUrl': info['descriptionurl'], 'creator': field('Artist'),
                'originalSources': [a['href'] for a in BeautifulSoup(meta.get('Credit', {}).get('value', ''), 'html.parser').select('a[href]')],
                'license': field('LicenseShortName'), 'licenseUrl': field('LicenseUrl'),
                'identityMatch': 'linked_wikipedia_biography_portrait' if person in linked_people else 'official_house_portrait_exact_roster_name',
                'identitySourceUrl': 'https://en.wikipedia.org/wiki/' + row['pageTitle'].replace(' ', '_')})

    for search_path in args.cache.glob('supplemental-*-search.json'):
        for search in json.loads(search_path.read_text()):
            person = search['personKey']
            if person not in people:
                continue
            for page in search.get('response', {}).get('query', {}).get('pages', {}).values():
                info = page.get('imageinfo', [{}])[0]
                meta = info.get('extmetadata', {})
                field = lambda name: plain(meta.get(name, {}).get('value', ''))
                title = page.get('title', '')
                if not re.search(r'portrait|cropped|File:Rep\.', title, re.I):
                    continue
                if not info.get('url') or not field('LicenseShortName') or not .4 <= info.get('width', 0) / max(1, info.get('height', 0)) <= 1.4:
                    continue
                role = field('Artist') + ' ' + field('ImageDescription') + ' ' + field('Categories')
                if not re.search(r'House of Representatives|Congress of the Philippines|Filipino politician|Philippines.*(?:Governor|politician)|League of Provinces', role, re.I):
                    continue
                candidate = {'nameFromFile': title, 'description': field('ImageDescription')}
                if score_name(people[person], candidate) < 90:
                    continue
                raw_url = urlsplit(info['url'])
                image_url = urlunsplit((raw_url.scheme, raw_url.netloc, raw_url.path, '', ''))
                if any(p['originalUrl'] == image_url for p in by_person[person]):
                    continue
                term = re.search(r'(\d+)(?:th|rd|nd|st)[ _]Congress', title + ' ' + field('ImageDescription'), re.I)
                by_person[person].append({'personKey': person, 'photoCongress': int(term[1]) if term else None,
                    'fileTitle': title, 'nameFromFile': search['name'], 'description': field('ImageDescription'),
                    'originalUrl': image_url, 'sourceUrl': info['descriptionurl'],
                    'originalSources': [a['href'] for a in BeautifulSoup(meta.get('Credit', {}).get('value', ''), 'html.parser').select('a[href]')],
                    'creator': field('Artist'), 'license': field('LicenseShortName'), 'licenseUrl': field('LicenseUrl'),
                    'identityMatch': 'exact_roster_name_and_official_politician_portrait'})

    all_photos = [p for group in by_person.values() for p in group]
    if args.download:
        from verify_congress_portraits import verify
        urls = sorted({p['originalUrl'] for p in all_photos})
        if args.missing_people_only:
            urls = []
            for group in by_person.values():
                if any(verified.get(p['originalUrl'], {}).get('status') == 'verified_image' for p in group):
                    continue
                choice = min(group, key=lambda p: (p.get('photoCongress') not in (17, 18), p.get('photoCongress') != 19, p['originalUrl']))
                urls.append(choice['originalUrl'])
            urls = sorted(set(urls))
        pending = [u for u in urls if verified.get(u, {}).get('status') != 'verified_image']
        def download(url):
            endpoint = url
            if url.startswith('https://upload.wikimedia.org/wikipedia/commons/'):
                tail = url.split('/wikipedia/commons/', 1)[1]
                endpoint = 'https://thumb.wikimedia.org/wikipedia/commons/thumb/' + tail + '/250px-' + tail.rsplit('/', 1)[1]
            _, record = verify(endpoint)
            record.update(originalUrl=url, downloadUrl=endpoint)
            time.sleep(args.delay)
            return url, record
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            for index, (url, record) in enumerate(pool.map(download, pending), 1):
                verified[url] = record
                if index % 25 == 0:
                    print(f'Checked {index}/{len(pending)} historical portrait files', flush=True)
        verification_path = STATIC / 'congress-portrait-verification.json'
        previous = json.loads(verification_path.read_text())
        previous.update(checkedAtUtc=datetime.now(timezone.utc).isoformat(), images=verified)
        verification_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
    for photo in all_photos:
        checked = verified.get(photo['originalUrl'], {})
        if checked.get('status') == 'verified_image' and (STATIC / checked.get('localUrl', '')).is_file():
            photo.update(status='verified_image', localUrl=checked['localUrl'], checkedAtUtc=checked.get('checkedAtUtc'))
        else:
            photo.update(status=checked.get('status', 'not_downloaded'))

    payload = {'researchedAtUtc': datetime.now(timezone.utc).isoformat(),
               'scope': 'Historical House district members and attributed portraits. Term roster identity and photograph Congress are separate fields.',
               'members': members, 'portraits': all_photos}
    out = STATIC / 'congress-historical-rosters.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    research = ROOT / 'data_sources/historical-congress-unmatched-portraits.json'
    research.write_text(json.dumps(unmatched, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'members': {n: sum(r['congress'] == n for r in members) for n in (16, 17, 18, 19)},
                      'identifiedPortraits': len(payload['portraits']), 'unmatchedPortraits': len(unmatched),
                      'rosterMembersWithAnIdentifiedPortrait': {n: sum(bool(by_person[r['personKey']]) for r in members if r['congress'] == n) for n in (16, 17, 18, 19)}}, indent=2))


if __name__ == '__main__':
    main()
