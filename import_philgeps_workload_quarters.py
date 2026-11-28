"""Extract DPWH civil works awards from the official quarterly PhilGEPS CSV downloads."""
import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODE = re.compile(r'(?<![A-Z0-9])([0-9]{2}[A-Z]{1,3}[0-9]{4,5})(?![A-Z0-9])', re.I)


class Catalog(HTMLParser):
    def __init__(self):
        super().__init__()
        self.files = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag != 'a' or 'data-download' not in a:
            return
        system = 'legacy' if a['data-system'] == 'PhilGEPS 1.5' else 'modern'
        key = f"{a['data-year']}-{system}-Q{a['data-quarter'][-1]}"
        self.files[key] = a['href']


def iso(raw, system):
    try:
        return datetime.strptime(raw.strip(), '%d/%m/%Y' if system == 'legacy' else '%d-%b-%Y').date().isoformat()
    except (ValueError, AttributeError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path, help='Saved official PhilGEPS open-data catalog HTML')
    parser.add_argument('exports', nargs='+', type=Path, help='Local files named philgeps-YYYY-{modern,legacy}-Qn.data')
    args = parser.parse_args()
    catalog = Catalog()
    catalog.feed(args.catalog.read_text())
    sources, records = {}, set()
    for path in sorted(args.exports):
        key = path.stem.removeprefix('philgeps-')
        system = key.split('-')[1]
        counts = Counter(rows=0, dpwhCivilWorks=0, datedAwardRows=0, identifiedRows=0)
        with path.open(encoding='utf-8-sig', errors='replace', newline='') as stream:
            delimiter = '\t' if '\t' in stream.readline() else ','
            stream.seek(0)
            for row in csv.DictReader(stream, delimiter=delimiter):
                counts['rows'] += 1
                if 'PUBLIC WORKS AND HIGHWAYS' not in str(row['Procuring Entity (PE)']).upper() or 'civil works' not in str(row['Classification']).lower():
                    continue
                counts['dpwhCivilWorks'] += 1
                awarded = iso(row['Award Date'], system)
                name = (row['Awardee Organization Name'] or '').strip()
                ref = (row['Award Reference No.'] or '').strip()
                if not awarded or not ref.isdigit() or not name or name.upper() == 'NULL':
                    continue
                counts['datedAwardRows'] += 1
                codes = set(CODE.findall(' '.join(row.get(field) or '' for field in ('Solicitation No.', 'Control No.', 'Award Title', 'Notice Title')).upper()))
                if len(codes) != 1:
                    continue
                counts['identifiedRows'] += 1
                status = row.get('Award Notice Status') or row.get('Award Notice Status (Item)') or ''
                records.add((key, ref, codes.pop(), name, awarded, status, iso(row['Contract End Date'], system) or ''))
        with path.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        sources[key] = dict(url=catalog.files[key], sha256=checksum, **counts)
    fields = ('source', 'award_reference_no', 'contract_no', 'awardee_organization_name', 'award_date', 'award_notice_status', 'contract_end_date')
    doc = {'catalog': 'https://philgeps.gov.ph/CmsHomePages/open-data', 'sources': sources,
           'rows': [dict(zip(fields, row)) for row in sorted(records)]}
    (ROOT / 'data_sources/philgeps-workload-quarters.json').write_text(json.dumps(doc, ensure_ascii=False, separators=(',', ':')) + '\n')
    print(len(records), 'distinct award rows', sources.keys())


if __name__ == '__main__':
    main()
