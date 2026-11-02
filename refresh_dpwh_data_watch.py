#!/usr/bin/env python3
"""Refresh the public DPWH data snapshot as the private POW parser advances."""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS_ROOT = Path(os.environ.get(
    "DPWH_STATUS_ROOT", ROOT / "data_sources/dpwh_project_documents"
))
PARSER_STATUS = STATUS_ROOT / "pow-parser-watcher-status.json"
# Keep the refresh checkpoint inside the writable project workspace. It is
# operational state and is never copied to the published static directory.
REFRESH_STATUS = ROOT / ".dpwh-page-data-refresh-status.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_status(value):
    temporary = REFRESH_STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(REFRESH_STATUS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--interval", type=int, default=30)
    parser.add_argument("--retry-seconds", type=int, default=300)
    args = parser.parse_args()
    state = read_json(REFRESH_STATUS)
    last_built = state.get("lastBuiltProcessed")
    if not isinstance(last_built, int):
        # The current artifact was built before this watcher was introduced.
        last_built = int(read_json(PARSER_STATUS).get("processed", 0))
    while True:
        parser_state = read_json(PARSER_STATUS)
        processed = int(parser_state.get("processed", 0))
        now = utc_now()
        if processed - last_built >= args.batch_size:
            state.update({"status": "refreshing", "startedAtUtc": now,
                          "parserProcessed": processed,
                          "lastBuiltProcessed": last_built})
            write_status(state)
            command = [sys.executable, str(ROOT / "build_dpwh_indepth.py"), "--data-only"]
            try:
                result = subprocess.run(command, cwd=ROOT, capture_output=True,
                                        text=True, check=True)
                summary = json.loads(result.stdout)
                last_built = processed
                state.update({"status": "idle", "updatedAtUtc": utc_now(),
                              "lastBuiltProcessed": last_built,
                              "summary": summary, "lastError": None})
                write_status(state)
            except (subprocess.CalledProcessError, ValueError) as exc:
                detail = (exc.stderr if isinstance(exc, subprocess.CalledProcessError)
                          else str(exc))
                state.update({"status": "error", "updatedAtUtc": utc_now(),
                              "parserProcessed": processed,
                              "lastBuiltProcessed": last_built,
                              "lastError": detail[-4000:]})
                write_status(state)
                time.sleep(args.retry_seconds)
                continue
        else:
            state.update({"status": "idle", "updatedAtUtc": now,
                          "parserProcessed": processed,
                          "lastBuiltProcessed": last_built})
            write_status(state)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
