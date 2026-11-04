#!/usr/bin/env python3
"""Wait for the FY2019 GAA OCR pass, then resume the cached POW retry batch."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES = ROOT / "data_sources/gaa_2019_volume_ia/pages.jsonl"
LOG = ROOT / "data_sources/gaa_2019_volume_ia/pow_retry_after_ocr.log"
EXPECTED_PAGES = 1078


def completed_page_count():
    pages = set()
    if PAGES.exists():
        with PAGES.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    pages.add(int(json.loads(line)["page"]))
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue
    return len(pages)


def main():
    while completed_page_count() < EXPECTED_PAGES:
        time.sleep(30)

    env = os.environ.copy()
    env.update({
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "FLAGS_cpu_num_threads": "1",
    })
    with LOG.open("a", encoding="utf-8") as output:
        output.write("GAA OCR reached all source pages; rebuilding line labels.\n")
        output.flush()
        subprocess.run(
            [sys.executable, str(ROOT / "parse_fy2019_gaa_volume_ia.py"), "--rebuild-fields"],
            cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=True,
        )
        output.write("Starting cached POW retry batch with one worker.\n")
        output.flush()
        subprocess.run(
            [sys.executable, str(ROOT / "reparse_failed_project_pows.py"), "--workers", "1"],
            cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, check=True,
        )
        output.write("Cached POW retry batch finished.\n")


if __name__ == "__main__":
    main()
