#!/usr/bin/env python3
"""Collect exact FY2027 budget title matches from the public PhilGEPS board."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from datetime import date, datetime
from decimal import Decimal
from html import unescape
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
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
TITLE_PREFIX = re.compile(r'^(?:convergence and special support program|asset preservation program|network development program|flood management program|organizational outcome [0-9]+|construction of concrete road)\b')
REQUEST_LOCK = Lock()
next_request = 0.0


def pace():
    global next_request
    with REQUEST_LOCK:
        time.sleep(max(0, next_request - time.monotonic()))
        next_request = time.monotonic() + .45


DATE_PATTERN = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+2026'


def plain(markup):
    return ' '.join(unescape(re.sub(r'<[^>]*>', ' ', markup)).split())


def fetch(url):
    request = Request(url, headers={'User-Agent': 'BetterGov public procurement research/1.0'})
    pace()
    with urlopen(request, timeout=20) as response:
        return response.read().decode('utf-8', errors='replace')


def search_pages(start, end, limit, all_details):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with opener.open(SEARCH, timeout=15) as response:
        form = response.read().decode('utf-8', errors='replace')
    token = re.search(r'name="_csrfToken"[^>]*value="([^"]+)', form)
    if not token:
        raise ValueError('Public search form was unavailable.')
    fields = {'_csrfToken': token[1], 'searchKeyword': '', 'searchClassification': '1', 'searchModeProc': '' if all_details else '1',
              'searchPublishDateFrom': start.strftime('%d-%b-%Y'), 'searchPublishDateTo': end.strftime('%d-%b-%Y'),
              'searchBudgetFrom': '', 'searchBudgetTo': ''}
    url = SEARCH
    visited = set()
    page_number = 0
    while limit is None or page_number < limit:
        page_number += 1
        request = Request(url, data=urlencode(fields).encode(), headers={'Referer': SEARCH})
        for attempt in range(4):
            try:
                pace()
                with opener.open(request, timeout=20) as response:
                    page = response.read().decode('utf-8', errors='replace')
                break
            except (URLError, TimeoutError) as error:
                if attempt == 3 or (isinstance(error, HTTPError) and error.code < 500):
                    raise
                time.sleep(2 ** attempt)
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
    key = title_key(title[contract.end():] if contract else title)
    if key in keys:
        return key, 'Exact normalized project title in the notice.'
    if TITLE_PREFIX.match(key):
        words = key.split()
        for start in range(1, max(1, len(words)-8)):
            suffix = ' '.join(words[start:])
            if suffix in keys and len(suffix) >= 50:
                return suffix, 'Exact project title at the end of the notice’s program heading.'
    return None


def detail_field(html, label):
    field = re.search(r'<label[^>]*>\s*' + re.escape(label) + r'\s*:?\s*</label>(.*?)</div>', html, re.I | re.S)
    if not field:
        return ''
    return plain(field[1])


def has_reference(html, reference):
    reference = re.escape(reference)
    if re.search(r'Notice Reference Number\s*:\s*' + reference + r'\b', plain(html)):
        return True
    # Revised tenders can display the original notice number in the heading.
    return bool(re.search(r'Notice Reference Number\s*:', html)
                and re.search(r"/Tenders/check_item_status/" + reference + r"\b", html, re.I))


def details(html, hint, keys, cutoff):
    if not has_reference(html, hint['reference']):
        return None
    match = re.search(r'<b>\s*Project Name:\s*</b>(.*?)</div>', html, re.I | re.S)
    if not match:
        return None
    title = plain(match[1])
    full_text = plain(html)
    contract = CONTRACT_ID.match(title)
    codes = {m.upper() for m in re.findall(r'\b27[A-Z]{1,2}\d{4,5}\b', full_text, re.I)}
    if contract:
        contract_id = contract[1].upper()
    elif len(codes) == 1:
        contract_id = next(iter(codes))
    else:
        contract_id = ''
    matched = title_match(title, keys)
    if not matched and not contract_id:
        return None
    key, basis = matched or ('', 'A corresponding title in the available budget schedules remains unverified.')
    text = title_key(full_text)
    epa = bool(re.search(r'\b(?:early procurement activit(?:y|ies)|epa)\b', text))
    funding_year = re.search(
        r'\b(?:fy|f y|fiscal year)\s*2027\b|\b2027\s+(?:nep|gaa|national expenditure program)\b',
        text,
    )
    if not funding_year:
        return None
    funding_context = text[max(0, funding_year.start() - 100):funding_year.end() + 160]
    if not re.search(r'\b(?:fund(?:ing)?|appropriat(?:ion|ed)|budget|nep|gaa|national expenditure program)\b',
                     funding_context):
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
    return {'contract': contract_id or 'Notice ' + hint['reference'], 'reference': hint['reference'], 'title': title, 'matchKey': key,
            'office': detail_field(html, 'Client Agency') or hint.get('office', ''),
            'status': status, 'abc': float(Decimal(abc[0].replace(',', ''))),
            'issued': date_found, 'dateLabel': 'Notice published' if hint.get('published') else 'Notice created',
            'opening': opened, 'epaWording': epa,
            'fy2027FundingVerified': True,
            'basis': basis + (' The notice identifies this as FY2027 early procurement.' if epa
                              else ' The notice explicitly cites FY2027 as its funding year.'),
            'url': DETAIL + hint['reference']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--published-from', type=date.fromisoformat)
    parser.add_argument('--pages', type=int, help='Optional maximum number of listing pages')
    parser.add_argument('--all-details', action='store_true', help='Review every civil-works detail page, across all procurement modes')
    parser.add_argument('--listing-file', action='append', type=Path, default=[])
    parser.add_argument('--detail-directory', type=Path, help='Store and reuse downloaded official detail pages')
    parser.add_argument('--reference', action='append', default=[], help='Public notice reference supplied for verification')
    args = parser.parse_args()
    cutoff = args.as_of.isoformat()
    if (args.pages is not None and args.pages < 1) or (args.published_from and args.published_from > args.as_of):
        parser.error('Provide a positive page limit and a publication start on or before the cutoff.')
    if any(not re.fullmatch(r'\d+', reference) for reference in args.reference):
        parser.error('A notice reference must contain digits only.')
    if args.detail_directory:
        args.detail_directory.mkdir(parents=True, exist_ok=True)

    keys = {title_key(line['title']) for line in budget_lines()}
    previous = json.loads(SNAPSHOT.read_bytes())['notices'] if SNAPSHOT.exists() else []
    retained = {row['reference']: row for row in previous if row['issued'] <= cutoff and row.get('fy2027FundingVerified')}
    seen = set()
    attempted = set()
    failures = []
    accepted = 0
    downloads = 0
    listing_pages = 0
    search_error = ''
    expected_listings = None
    blocked = Event()

    def review(hint):
        reference = hint['reference']
        cached = args.detail_directory / f'philgeps-{reference}.html' if args.detail_directory else None
        if cached and cached.exists():
            html = cached.read_text(encoding='utf-8')
            if has_reference(html, reference):
                return details(html, hint, keys, cutoff), False
        for attempt in range(3):
            if blocked.is_set():
                return ValueError('Detail request paused after a portal access error.'), False
            try:
                html = fetch(DETAIL + reference)
                if not has_reference(html, reference):
                    raise ValueError('The detail page did not contain the requested notice reference.')
                if cached:
                    cached.write_text(html, encoding='utf-8')
                return details(html, hint, keys, cutoff), True
            except (URLError, TimeoutError, ValueError) as error:
                if isinstance(error, HTTPError) and error.code in (403, 429):
                    blocked.set()
                    return error, False
                if attempt == 2 or (isinstance(error, HTTPError) and error.code == 404):
                    print(f'{reference}: {error}', flush=True)
                    return error, False
                time.sleep(2 ** attempt)

    def review_rows(rows, pool):
        nonlocal accepted, downloads
        candidates = []
        for row in rows:
            reference = row['reference']
            if reference in attempted:
                continue
            attempted.add(reference)
            candidates.append(row)
        blocked_error = None
        for row, (notice, downloaded) in zip(candidates, pool.map(review, candidates)):
            downloads += downloaded
            if isinstance(notice, Exception):
                failures.append(row['reference'])
                if isinstance(notice, HTTPError) and notice.code in (403, 429):
                    blocked_error = notice
            elif notice:
                retained[row['reference']] = notice
                accepted += 1
        if blocked_error:
            raise blocked_error

    def process(document, pool, filtered=False):
        nonlocal listing_pages, expected_listings
        if filtered:
            total = re.search(r'record\(s\) out of ([\d,]+) total', document)
            if total:
                expected_listings = max(expected_listings or 0, int(total[1].replace(',', '')))
        rows = list(listing(document))
        if filtered and rows and not all(args.published_from.isoformat() <= row['published'] <= cutoff
                                        and row['class'] == 'Civil Works - Infra Project' for row in rows):
            raise ValueError('The portal returned listings outside the requested filters.')
        listing_pages += 1
        rows = [row for row in rows if row['published'] <= cutoff]
        seen.update(row['reference'] for row in rows)
        review_rows([row for row in rows if row['class'] == 'Civil Works - Infra Project'
                     and (args.all_details or title_match(row['title'], keys))], pool)
        print(f'Page {listing_pages}: {len(seen)} listings, {len(attempted)} detail reviews, {accepted} verified', flush=True)

    def save_snapshot(in_progress=False):
        payload = {'asOf': cutoff, 'listingUrl': SEARCH if args.published_from else BOARD,
                   'listingPages': listing_pages,
                   'requestedFrom': args.published_from.isoformat() if args.published_from else None,
                   'searchError': search_error, 'allDetails': args.all_details, 'inProgress': in_progress,
                   'reportedListings': expected_listings, 'listingsScreened': len(seen),
                   'detailsRequested': len(attempted), 'detailsReviewed': len(attempted) - len(failures),
                   'detailsDownloaded': downloads, 'verifiedThisRun': accepted, 'detailFailures': failures,
                   'notices': sorted(retained.values(), key=lambda row: (row['issued'], row['reference']), reverse=True)}
        temporary = SNAPSHOT.with_suffix('.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(SNAPSHOT)
        return payload

    with ThreadPoolExecutor(max_workers=4) as pool:
        try:
            for path in args.listing_file:
                process(path.read_text(encoding='utf-8'), pool)
            if args.published_from:
                for page in search_pages(args.published_from, args.as_of, args.pages, args.all_details):
                    process(page, pool, filtered=True)
                    if listing_pages % 20 == 0:
                        save_snapshot(in_progress=True)
            elif not args.listing_file:
                process(fetch(BOARD), pool)
            review_rows([{'reference': reference} for reference in args.reference], pool)
        except (URLError, TimeoutError, ValueError) as error:
            search_error = str(error)
            print(search_error, flush=True)

    if not search_error and expected_listings and len(seen) < expected_listings:
        search_error = f'The portal reported {expected_listings:,} listings. The run reached {len(seen):,} distinct listings.'
    payload = save_snapshot()
    print({key: value for key, value in payload.items() if key != 'notices'}, flush=True)
    return 1 if search_error or failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
