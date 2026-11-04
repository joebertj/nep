#!/usr/bin/env python3
"""Create a FY2015 MPB slice from DBM DPWH capital-outlay PAP rows."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data_sources/gaa_2015_dpwh_technical/lines.json'
OUT = ROOT / 'data_sources/mpb-historical-2015.json'
MULTI = re.compile(r'multi[\s-]*purpose', re.I)
FACILITY = re.compile(r'building|bldg|facility', re.I)


def main():
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    records = []
    for index, row in enumerate(source['rows'], 1):
        title = row.get('title', '')
        if not MULTI.search(title) or not FACILITY.search(title):
            continue
        records.append({
            'year': 2015, 'stage': 'GAA', 'category': 'Multi-purpose building',
            'name': title, 'amountPesos': row.get('amountPesos'),
            'sourceId': f"PAP {row['papCode']} · {row['implementingUnitCode']} · row {index}",
            'sourcePage': None,
            'source': f"FY2015 DBM DPWH GAA · PAP {row['papCode']} · {row['implementingOffice']}",
            'sourceUrl': source['sourceArchiveUrl'],
            'implementingOffice': row.get('implementingOffice'),
        })
    payload = {
        'title': 'FY2015 DPWH GAA MPB title candidates',
        'source': source['source'], 'sourceCsvSha256': source['sourceCsvSha256'],
        'classification': 'Capital-outlay PAP group title contains multi-purpose (spelling variants) and building/bldg/facility. PAP codes are not unique project identifiers.',
        'caveat': 'These are candidate appropriation lines derived from account-level capital-outlay entries, not verified unique physical buildings or spending. DBM amounts were converted from thousand pesos.',
        'records': records,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print(f"Wrote {len(records):,} FY2015 MPB candidates; ₱{sum(r['amountPesos'] or 0 for r in records):,}")


if __name__ == '__main__':
    main()
