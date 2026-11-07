#!/usr/bin/env python3
"""Rebuild DPWH reports after the POW parser settles on new results."""
import argparse
import hashlib
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


def supporting_inventory_fingerprint():
    """Hash the file-presence summary that feeds undocumented-hgab.html."""
    from build_undocumented_hgab import supporting_file_presence

    presence = supporting_file_presence()
    serialized = json.dumps({
        "available": presence.get("available"),
        "files": presence.get("files"),
        "projectCodes": presence.get("projectCodes"),
        "byType": presence.get("byType"),
        "filesByCode": presence.get("filesByCode"),
        "typesByCode": presence.get("typesByCode"),
    }, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--settle-seconds", type=int, default=45)
    parser.add_argument("--retry-seconds", type=int, default=300)
    parser.add_argument("--supporting-check-seconds", type=int, default=60,
                        help="seconds between T5 supporting-file inventory checks")
    args = parser.parse_args()
    if args.supporting_check_seconds < 15:
        parser.error("--supporting-check-seconds must be at least 15 seconds")
    state = read_json(REFRESH_STATUS)
    last_built = state.get("lastBuiltProcessed")
    if not isinstance(last_built, int):
        # The current artifact was built before this watcher was introduced.
        last_built = int(read_json(PARSER_STATUS).get("processed", 0))
    last_built_downloaded = state.get("lastBuiltDownloaded")
    last_built_supporting_inventory = state.get("lastBuiltSupportingInventory")
    last_supporting_check = 0.0
    current_supporting_inventory = None
    while True:
        parser_state = read_json(PARSER_STATUS)
        processed = int(parser_state.get("processed", 0))
        downloaded = int(parser_state.get("totalDownloadedPow", 0))
        now = utc_now()
        state.update({"watcherStatus": "running", "watcherPid": os.getpid(),
                      "heartbeatAtUtc": now})
        parsed_batch_ready = processed - last_built >= args.batch_size
        intake_changed = (last_built_downloaded is not None and downloaded != last_built_downloaded)
        if time.monotonic() - last_supporting_check >= args.supporting_check_seconds:
            current_supporting_inventory = supporting_inventory_fingerprint()
            last_supporting_check = time.monotonic()
            state["supportingInventoryCheckedAtUtc"] = now
        supporting_inventory_changed = (
            current_supporting_inventory is not None
            and current_supporting_inventory != last_built_supporting_inventory
        )
        if parsed_batch_ready or intake_changed:
            state.update({"status": "refreshing", "startedAtUtc": now,
                          "parserProcessed": processed,
                          "lastBuiltProcessed": last_built})
            write_status(state)
            try:
                report = subprocess.run(
                    [sys.executable, str(ROOT / "build_dpwh_indepth.py")],
                    cwd=ROOT, capture_output=True, text=True, check=True)
                summary = json.loads(report.stdout)
                undocumented = subprocess.run(
                    [sys.executable, str(ROOT / "build_undocumented_hgab.py")],
                    cwd=ROOT, capture_output=True, text=True, check=True)
                undocumented_summary = json.loads(undocumented.stdout)
                last_built = processed
                last_built_downloaded = downloaded
                state.update({"status": "idle", "updatedAtUtc": utc_now(),
                              "lastBuiltProcessed": last_built,
                              "lastBuiltDownloaded": last_built_downloaded,
                              "lastBuiltSupportingInventory": current_supporting_inventory,
                              "summary": summary,
                              "undocumentedHgabSummary": undocumented_summary,
                              "lastError": None})
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
        elif supporting_inventory_changed:
            state.update({"status": "refreshing_file_presence", "startedAtUtc": now,
                          "supportingInventoryChanged": True})
            write_status(state)
            try:
                undocumented = subprocess.run(
                    [sys.executable, str(ROOT / "build_undocumented_hgab.py")],
                    cwd=ROOT, capture_output=True, text=True, check=True)
                undocumented_summary = json.loads(undocumented.stdout)
                last_built_supporting_inventory = current_supporting_inventory
                state.update({"status": "idle", "updatedAtUtc": utc_now(),
                              "lastBuiltSupportingInventory": last_built_supporting_inventory,
                              "undocumentedHgabSummary": undocumented_summary,
                              "lastError": None})
                write_status(state)
            except (subprocess.CalledProcessError, ValueError) as exc:
                detail = (exc.stderr if isinstance(exc, subprocess.CalledProcessError)
                          else str(exc))
                state.update({"status": "error", "updatedAtUtc": utc_now(),
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
