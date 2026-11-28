"""Extract named awardees from a saved World Bank procurement-notices response."""
import argparse
from html import unescape
import json
from pathlib import Path
import re

DATA = Path(__file__).resolve().parent / 'data_sources'
AWARDEES = re.compile(
    r'Awarded Bidder\(s\):(.*?)(?:(?:Evaluated|Rejected|Unsuccessful|Nonresponsive|Other) Bidder\(s\):|$)',
    re.I | re.S,
)
AWARD_DATE = re.compile(r'Date Notification of Award Issued.{0,100}?(20\d\d/\d\d/\d\d)', re.I | re.S)


def extract(notices):
    for notice in notices:
        if notice.get('notice_type') != 'Contract Award':
            continue
        text = notice.get('notice_text', '')
        awarded, issued = AWARDEES.search(text), AWARD_DATE.search(text)
        if not awarded or not issued or issued[1] < '2026/01/01':
            continue
        for name in re.findall(r'<b>([^<>]+?)\s*\(\d+\)</b>', awarded[1], re.I):
            yield {
                'name': unescape(name), 'date': issued[1].replace('/', '-'), 'type': 'Award',
                'title': notice['bid_description'].replace('Famr-to', 'Farm-to'),
                'reference': notice['bid_reference_no'], 'agency': 'DA Philippine Rural Development Project Scale-up',
                'url': 'https://search.worldbank.org/api/v2/procnotices?format=json&id=' + notice['id'],
                'source': 'World Bank procurement notice ' + notice['id'],
            }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('notices', type=Path, help='Saved World Bank procurement-notices API JSON')
    args = parser.parse_args()
    items = list(extract(json.loads(args.notices.read_bytes())['procnotices']))
    (DATA / 'workload-procurement-activity.json').write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
