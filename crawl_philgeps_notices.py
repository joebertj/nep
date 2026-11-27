#!/usr/bin/env python3
"""Collect exact FY2027 budget title matches from the public PhilGEPS board."""
import argparse
from datetime import date, datetime
from decimal import Decimal
from html import unescape
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import time
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from build_philgeps_page import ROOT, budget_lines, title_key

HOST = 'https://philgeps.gov.ph'
BOARD = HOST + '/Indexes/index'
SEARCH = HOST + '/Indexes/viewMoreOpenTenders'
DETAIL = HOST + '/Indexes/viewLiveTenderDetails/'
SNAPSHOT = ROOT / 'data_sources/philgeps-fy2027-notices.json'
NOTICE_ID = re.compile(r'/Indexes/viewLiveTenderDetails/(\d+)', re.I)
CONTRACT_ID = re.compile(r'^\s*(?:contract\s*(?:id|no\.?)\s*[:.]?\s*)?(27[A-Z]{1,2}\d{4,5})\b\s*[-:.–—]*\s*', re.I)
TITLE_PREFIX = re.compile(r'^(?:convergence and special support program|asset preservation program|network development program|flood management program)\b')
DATE_PATTERN = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+2026'


def plain(markup):
    return ' '.join(unescape(re.sub(r'<[^>]*>', ' ', markup)).split())


def fetch(url):
    request = Request(url, headers={'User-Agent': 'BetterGov public procurement research/1.0'})
    with urlopen(request, timeout=15) as response:
        return response.read().decode('utf-8', errors='replace')


def search_pages(start, end, limit):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with opener.open(SEARCH, timeout=15) as response:
        form = response.read().decode('utf-8', errors='replace')
    token = re.search(r'name="_csrfToken"[^>]*value="([^"]+)', form)
    if not token:
        raise ValueError('Public search form was unavailable.')
    fields = {'_csrfToken': token[1], 'searchKeyword': '', 'searchClassification': '1', 'searchModeProc': '1',
              'searchPublishDateFrom': start.strftime('%d-%b-%Y'), 'searchPublishDateTo': end.strftime('%d-%b-%Y'),
              'searchBudgetFrom': '', 'searchBudgetTo': ''}
    url = SEARCH
    visited = set()
    for _ in range(limit):
        request = Request(url, data=urlencode(fields).encode(), headers={'Referer': SEARCH})
        with opener.open(request, timeout=15) as response:
            page = response.read().decode('utf-8', errors='replace')
        references = tuple(row['reference'] for row in listing(page))
        if references in visited:
            raise ValueError('The portal repeated a listing page after pagination.')
        visited.add(references)
        yield page
        next_link = re.search(r'<a[^>]*rel="next"[^>]*href="([^"]+)"', page, re.I)
        if not next_link:
            break
        url = urljoin(SEARCH, unescape(next_link[1]))
        if urlsplit(url).netloc != urlsplit(HOST).netloc:
            break
        token = re.search(r'name="_csrfToken"[^>]*value="([^"]+)', page)
        if token:
            fields['_csrfToken'] = token[1]
        time.sleep(.45)


def listing(html):
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.I | re.S):
        reference = NOTICE_ID.search(row)
        fields = re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.I | re.S)
        if reference and len(fields) == 7:
            _, title, _, cls, office, posted, _ = map(plain, fields)
            yield {'reference': reference[1], 'title': title, 'office': office, 'class': cls,
                   'published': datetime.strptime(posted, '%d-%b-%Y').date().isoformat()}


def title_match(title, keys):
    contract = CONTRACT_ID.match(title)
    if not contract:
        return None
    key = title_key(title[contract.end():])
    if key in keys:
        return contract[1], key, 'Exact normalized project title after the contract ID.'
    if TITLE_PREFIX.match(key):
        words = key.split()
        for start in range(1, max(1, len(words)-8)):
            suffix = ' '.join(words[start:])
            if suffix in keys and len(suffix) >= 50:
                return contract[1], suffix, 'Exact project title at the end of the notice’s program heading.'
    return None


def detail_field(html, label):
    field = re.search(r'<label[^>]*>\s*' + re.escape(label) + r'\s*:?\s*</label>(.*?)</div>', html, re.I | re.S)
    if not field:
        return ''
    return plain(field[1])


def details(html, hint, keys, cutoff):
    if not re.search(r'Notice Reference Number\s*:\s*' + re.escape(hint['reference']) + r'\b', plain(html)):
        return None
    match = re.search(r'<b>\s*Project Name:\s*</b>(.*?)</div>', html, re.I | re.S)
    if not match:
        return None
    title = plain(match[1])
    full_text = plain(html)
    if not CONTRACT_ID.match(title):
        contracts = {m.upper() for m in re.findall(r'\b27[A-Z]{1,2}\d{4,5}\b', full_text, re.I)}
        if len(contracts) != 1:
            return None
        title = next(iter(contracts)) + ' - ' + title
    matched = title_match(title, keys)
    if not matched or (hint.get('matchKey') and matched[1] != hint['matchKey']):
        return None
    contract, key, basis = matched
    text = title_key(full_text)
    epa = bool(re.search(r'\b(?:early procurement activit(?:y|ies)|epa)\b', text))
    if not re.search(r'\b(?:f y|fy|fiscal year) 2027\b|\b2027 (?:nep|gaa)\b', text):
        return None
    if not epa and not re.search(r'\b(?:nep|national expenditure program|gaa)\b', text):
        return None
    abc = re.match(r'[\d,]+(?:\.\d+)?', detail_field(html, 'Approved Budget of the Contract'))
    created = re.search(r'\b\d{1,2}-[A-Za-z]{3}-2026\b', detail_field(html, 'Date created'))
    status = detail_field(html, 'Status')
    if not abc or not created or not status:
        return None
    created_date = datetime.strptime(created[0], '%d-%b-%Y').date().isoformat()
    date_found = hint.get('published') or created_date
    if date_found > cutoff or created_date > cutoff:
        return None
    opening = re.search(r'(?:bid opening|opening of bids)\s+(?:shall be|will be)\s+on\s+(' + DATE_PATTERN + ')',
                        full_text, re.I)
    opened = datetime.strptime(opening[1], '%B %d, %Y').date().isoformat() if opening else ''
    return {'contract': contract, 'reference': hint['reference'], 'title': title, 'matchKey': key,
            'office': detail_field(html, 'Client Agency') or hint.get('office', ''),
            'status': status, 'abc': float(Decimal(abc[0].replace(',', ''))),
            'issued': date_found, 'dateLabel': 'Notice published' if hint.get('published') else 'Notice created',
            'opening': opened, 'epaWording': epa,
            'basis': basis + (' The notice identifies this as FY2027 early procurement.' if epa
                              else ' The notice cites FY2027 funding.'),
            'url': DETAIL + hint['reference']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--published-from', type=date.fromisoformat)
    parser.add_argument('--pages', type=int, default=12)
    parser.add_argument('--listing-file', action='append', type=Path, default=[])
    parser.add_argument('--detail-directory', type=Path, help='Reuse official detail pages previously downloaded here')
    parser.add_argument('--reference', action='append', default=[], help='Public notice reference supplied for verification')
    args = parser.parse_args()
    cutoff = args.as_of.isoformat()
    if args.pages < 1 or (args.published_from and args.published_from > args.as_of):
        parser.error('Provide a positive page limit and a publication start on or before the cutoff.')
    keys = {title_key(line['title']) for line in budget_lines()}
    listings = [path.read_text(encoding='utf-8') for path in args.listing_file]
    search_error = ''
    if args.published_from:
        try:
            for page in search_pages(args.published_from, args.as_of, args.pages):
                rows = list(listing(page))
                if rows and not all(args.published_from.isoformat() <= row['published'] <= cutoff
                                    and row['class'] == 'Civil Works - Infra Project' for row in rows):
                    raise ValueError('The portal returned listings outside the requested filters.')
                listings.append(page)
        except (URLError, TimeoutError, ValueError) as error:
            search_error = str(error)
            print(search_error, flush=True)
    if not listings:
        listings.append(fetch(BOARD))
    notices = {row['reference']: row for document in listings for row in listing(document) if row['published'] <= cutoff}
    candidates = {}
    for reference, row in notices.items():
        if row['class'] == 'Civil Works - Infra Project' and (matched := title_match(row['title'], keys)):
            candidates[reference] = {**row, 'matchKey': matched[1]}
    for reference in args.reference:
        if not re.fullmatch(r'\d+', reference):
            parser.error('A notice reference must contain digits only.')
        candidates.setdefault(reference, {'reference': reference})
    previous = json.loads(SNAPSHOT.read_bytes())['notices'] if SNAPSHOT.exists() else []
    retained = {row['reference']: row for row in previous if row['issued'] <= cutoff}
    failures = []
    accepted = 0
    for reference, hint in candidates.items():
        try:
            cached = args.detail_directory / f'philgeps-{reference}.html' if args.detail_directory else None
            if cached and cached.exists():
                html = cached.read_text(encoding='utf-8')
            else:
                html = fetch(DETAIL + reference)
                time.sleep(.45)
                if cached:
                    cached.write_text(html, encoding='utf-8')
            notice = details(html, hint, keys, cutoff)
            if notice:
                retained[reference] = notice
                accepted += 1
        except (URLError, TimeoutError) as error:
            failures.append(reference)
            print(f'{reference}: {error}', flush=True)
    payload = {'asOf': cutoff, 'listingUrl': SEARCH if args.published_from else BOARD, 'listingPages': len(listings),
               'requestedFrom': args.published_from.isoformat() if args.published_from else None,
               'searchError': search_error,
               'listingsScreened': len(notices), 'detailsRequested': len(candidates),
               'verifiedThisRun': accepted, 'detailFailures': failures,
               'notices': sorted(retained.values(), key=lambda r: (r['issued'], r['reference']), reverse=True)}
    temporary = SNAPSHOT.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(SNAPSHOT)
    print({k: v for k, v in payload.items() if k != 'notices'}, flush=True)


if __name__ == '__main__':
    main()
