#!/usr/bin/env python3
"""Orchestrate HGAB revision data and its page-owned renderers.

This script coordinates the build but does not write HTML itself. Each
one-page builder owns its matching static page and analysis mirror.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Data inputs must be refreshed before the page owners consume them.
DATA_BUILDERS = [
    'build_nep_agency_baselines.py',
    'build_hgab_revision_pages.py',
]

# These are page owners; they run after the shared revision and baseline JSON
# inputs have been prepared above.
PAGE_BUILDERS = [
    'build_dpwh_hgab_comparison_page.py',
    'build_dpwh_hgab_page.py',
    'build_fmr_reading_page.py',
    'build_nia_reading_page.py',
    'build_hfep_reading_page.py',
    'build_nia_irrigation_page.py',
    'build_deped_page.py',
]


def main():
    from build_reviewed_annex_sections import build_baseline_asset
    build_baseline_asset()
    results = {}
    for script in DATA_BUILDERS + PAGE_BUILDERS:
        result = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT,
                                text=True, capture_output=True, check=True)
        try:
            results[script] = json.loads(result.stdout)
        except (ValueError, TypeError):
            results[script] = {'output': result.stdout.strip()}
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
