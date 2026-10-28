#!/usr/bin/env python3
"""Build both congressional JSON datasets from their shared attribution source.

Run this entry point instead of the individual builders so the allocation
ranking is refreshed before the flag-review dataset consumes its district
allocation totals.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ALLOCATION_BUILDER = (
    ROOT.parent
    / 'open-data-visualization'
    / 'analysis'
    / 'build_congress_allocation_data.py'
)


def main() -> None:
    if not ALLOCATION_BUILDER.is_file():
        raise FileNotFoundError(f'Allocation builder not found: {ALLOCATION_BUILDER}')

    subprocess.run(
        [sys.executable, str(ALLOCATION_BUILDER), '--write'],
        cwd=ALLOCATION_BUILDER.parent,
        check=True,
    )

    sys.path.insert(0, str(ROOT))
    import build_congress_district_review

    review_summary = build_congress_district_review.build()
    print(json.dumps({
        'allocationData': str(
            ROOT.parent / 'open-data-visualization/static/nep-preview/congress-data.json'
        ),
        'reviewData': str(
            ROOT.parent
            / 'open-data-visualization/static/nep-preview/congress-district-review-data.json'
        ),
        'reviewSummary': review_summary,
    }, indent=2))


if __name__ == '__main__':
    main()
