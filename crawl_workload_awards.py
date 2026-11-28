"""Collect published modern PhilGEPS civil works awards around the DPWH snapshot cutoff."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import urlencode, urljoin
from urllib.request import build_opener, HTTPCookieProcessor, Request
import csv
import gzip
import json
import re
import time

from crawl_philgeps_notices import fetch, pace, plain, HOST
from import_philgeps_workload_quarters import CODE, iso

ROOT = Path(__file__).resolve().parent
LIST = HOST + '/Indexes/viewMoreAward'
DETAIL = HOST + '/Indexes/viewAwardNotice/'
FIRST, LAST = date(2026, 10, 1), date(2026, 11, 3)


def retried(call):
    for attempt in range(3):
        try:
            return call()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def detail(item):
    ref, title_code, listed_name, listed_day = item
    html = retried(lambda: fetch(DETAIL + ref))
    status = re.search(r'Status\s*:\s*</label>(.*?)</div>', html, re.I | re.S)
    agency = re.search(r'<center class="verdhana_bold_twelvepx">(.*?)</center>', html, re.I | re.S)
    def field(label):
        match = re.search(re.escape(label) + r'\s*:\s*</label>\s*</?br\s*/?>\s*([^<]*)', html, re.I)
        return plain(match[1]) if match else ''
    if (not status or not agency or 'PUBLIC WORKS AND HIGHWAYS' not in plain(agency[1]).upper()
            or not re.search(r'Award Notice Number\s*:\s*' + ref + r'\b', html, re.I)
            or iso(field('Award Date'), 'modern') != listed_day):
        return None
    return dict(source='live', award_reference_no=ref, contract_no=title_code,
                awardee_organization_name=listed_name, award_date=listed_day,
                award_notice_status=plain(status[1]), contract_end_date=iso(field('Contract End Date'), 'modern'))


def main():
    archive = ROOT / 'research_downloads/hgab2027_contractors/dpwh-contracts-2016-2026.csv.gz'
    with gzip.open(archive, 'rt', encoding='utf-8-sig') as stream:
        ids = {r['contract_id'].strip().upper() for r in csv.DictReader(stream)}
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    def read(req):
        pace()
        with opener.open(req, timeout=30) as res:
            return res.read().decode('utf-8', 'replace')
    html = retried(lambda: read(LIST))
    url = LIST
    seen = set()
    candidates = {}
    pages = 0
    while True:
        fields = {'_csrfToken': re.search(r'name="_csrfToken"[^>]*value="([^"]+)', html)[1],
                  'searchClassification':'1', 'searchPublishDateFrom':FIRST.strftime('%d-%b-%Y'),
                  'searchPublishDateTo':LAST.strftime('%d-%b-%Y')}
        request = Request(url, data=urlencode(fields).encode(), headers={'Referer':LIST})
        html = retried(lambda: read(request))
        refs = set()
        for tr in re.findall(r'<tr\b[^>]*>(.*?)</tr>', html, re.I | re.S):
            cells = [plain(td) for td in re.findall(r'<td\b[^>]*>(.*?)</td>', tr, re.I | re.S)]
            if len(cells) != 5 or not cells[0].isdigit():
                continue
            ref, _, title, name, award = cells
            refs.add(ref)
            codes = set(CODE.findall(title.upper()))
            when = iso(award, 'modern')
            if len(codes) == 1 and codes <= ids and when and FIRST.isoformat() <= when <= LAST.isoformat():
                candidates[ref] = (ref, codes.pop(), name, when)
        if not refs or refs <= seen:
            raise ValueError('Empty or repeated PhilGEPS listing')
        seen.update(refs)
        pages += 1
        nxt = re.search(r'<a rel="next" href="([^"]+)"', html)
        if not nxt:
            break
        url = urljoin(LIST,nxt[1])
    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = [r for r in pool.map(detail, candidates.values()) if r]
    data = {'url':LIST, 'from':FIRST.isoformat(), 'to':LAST.isoformat(), 'listingPages':pages,
            'listedNotices':len(seen), 'archiveIdCandidates':len(candidates), 'rows':rows}
    (ROOT / 'data_sources/philgeps-workload-live.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(pages,len(seen),len(candidates),len(rows))


if __name__=='__main__':
    main()
