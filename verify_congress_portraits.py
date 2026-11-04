#!/usr/bin/env python3
"""Download and validate public portrait images; retain explicit failure statuses."""
import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

STATIC = Path(__file__).resolve().parent.parent / 'open-data-visualization/static/nep-preview'
OUT = STATIC / 'congress-portrait-verification.json'


def verify(url):
    record = {'originalUrl': url, 'checkedAtUtc': datetime.now(timezone.utc).isoformat()}
    try:
        request = Request(url, headers={'User-Agent': 'BetterGov research portrait verification/1.0'})
        with urlopen(request, timeout=15) as response:
            body = response.read(10_000_001)
            content_type = response.headers.get_content_type()
        signatures = [(b'\xff\xd8\xff', 'jpg'), (b'\x89PNG\r\n\x1a\n', 'png'),
                      (b'GIF8', 'gif')]
        extension = next((ext for signature, ext in signatures if body.startswith(signature)), None)
        if body.startswith(b'RIFF') and body[8:12] == b'WEBP':
            extension = 'webp'
        if not extension or len(body) > 10_000_000:
            raise ValueError(f'Response is not a supported image ({content_type})')
        filename = hashlib.sha256(url.encode()).hexdigest()[:24] + '.' + extension
        directory = STATIC / 'congress-portraits'
        directory.mkdir(exist_ok=True)
        (directory / filename).write_bytes(body)
        record.update(status='verified_image', contentType=content_type, bytes=len(body),
                      localUrl='congress-portraits/' + filename)
    except Exception as error:
        record.update(status='fetch_failed', error=str(error))
    return url, record


def main():
    data = json.loads((STATIC / 'integrated-district-data.json').read_text())
    overrides = {row['districtId']: row['photoUrl'] for row in json.loads((STATIC / 'congress-photo-overrides.json').read_text())}
    urls = sorted({overrides.get(row['districtId']) or row.get('representativePhotoOriginalUrl') or row.get('representativePhotoUrl')
                   for row in data['districts']} - {None})
    previous = json.loads(OUT.read_text()).get('images', {}) if OUT.exists() else {}
    results = {url: row for url, row in previous.items()
               if row.get('status') == 'verified_image' and (STATIC / row.get('localUrl', '')).is_file()}
    pending = [url for url in urls if url not in results]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for index, (url, record) in enumerate(pool.map(verify, pending), 1):
            results[url] = record
            if index % 25 == 0:
                print(f'Checked {index}/{len(pending)} new images', flush=True)
    payload = {'checkedAtUtc': datetime.now(timezone.utc).isoformat(),
               'scope': 'Image transport and file signature verification; human identity is separately matched to the roster.',
               'images': results}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'mapped': len(urls), 'verified': sum(results[u]['status'] == 'verified_image' for u in urls),
                      'failed': sum(results[u]['status'] != 'verified_image' for u in urls)}))


if __name__ == '__main__':
    main()
