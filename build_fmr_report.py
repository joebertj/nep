#!/usr/bin/env python3
"""Build FMR using the validated analyst annex ledgers when available."""
from pathlib import Path
import json,runpy
if __name__ == '__main__':
    if (Path(__file__).resolve().parent/'data_sources/fmr_analyst/hgab_fmr_coordinates_normalized.json').exists():
        from build_corrected_fmr_page import generate
        print(json.dumps(generate(),indent=2))
    else:
        runpy.run_path(str(Path(__file__).with_name('build_fmr_report_legacy.py')),run_name='__main__')
