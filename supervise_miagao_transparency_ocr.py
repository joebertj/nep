#!/usr/bin/env python3
"""Run the Miagao parser with a per-file watchdog and historical publisher.

The parser times out individual Tesseract calls. This supervisor also detects a
stalled document, skips it, resumes the queue, and runs the /historical index
publisher while new parsed records are being written.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARSER = ROOT / "parse_miagao_transparency_ocr.py"
HISTORICAL_PUBLISHER = ROOT / "publish_miagao_historical_index.py"
STATUS = ROOT / "analysis_output/miagao-transparency-ocr/status.json"
LOG = ROOT / "analysis_output/miagao-transparency-ocr/supervisor.log"


def read_status():
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def record(message):
    entry = {"atUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "message": message}
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(f"[{entry['atUtc']}] {message}", flush=True)


def stop_process_group(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)


def start_historical_watcher(interval_seconds):
    record(f"Starting /historical index watcher (every {interval_seconds}s)")
    return subprocess.Popen(
        [sys.executable, str(HISTORICAL_PUBLISHER), "--watch-seconds", str(interval_seconds)],
        cwd=ROOT,
        start_new_session=True,
    )


def publish_historical_once():
    subprocess.run([sys.executable, str(HISTORICAL_PUBLISHER)], cwd=ROOT, check=True)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--stall-timeout-seconds", type=int, default=360)
    cli.add_argument("--poll-seconds", type=int, default=10)
    cli.add_argument("--document-timeout-seconds", type=int, default=30)
    cli.add_argument("--historical-update-interval-seconds", type=int, default=15)
    cli.add_argument("--retry-errors", action="store_true")
    cli.add_argument("--retry-error-records", action="store_true")
    cli.add_argument("--max-documents", type=int, default=0)
    args = cli.parse_args()

    skipped_during_run: set[str] = set()
    historical_watcher = None
    try:
        while True:
            command = [
                sys.executable,
                str(PARSER),
                "--document-timeout-seconds",
                str(args.document_timeout_seconds),
            ]
            if args.max_documents:
                command.extend(["--max-documents", str(args.max_documents)])
            if args.retry_errors:
                command.append("--retry-errors")
            if args.retry_error_records:
                command.append("--retry-error-records")
            for sha in sorted(skipped_during_run):
                command.extend(["--skip-file", sha])

            record("Starting or resuming the Miagao parser with single-threaded Tesseract OCR")
            child_started_ns = time.time_ns()
            process = subprocess.Popen(command, cwd=ROOT, start_new_session=True)
            watched_sha = None
            watched_since = None

            while process.poll() is None:
                state = read_status()
                current = state.get("current") or {}
                sha = current.get("sha256")
                try:
                    status_is_current = STATUS.stat().st_mtime_ns > child_started_ns
                except OSError:
                    status_is_current = False
                if not status_is_current:
                    time.sleep(max(args.poll_seconds, 1))
                    continue
                if historical_watcher is None:
                    historical_watcher = start_historical_watcher(
                        max(args.historical_update_interval_seconds, 5)
                    )
                elif historical_watcher.poll() is not None:
                    watcher_code = historical_watcher.returncode
                    if state.get("status") not in {"complete", "complete_with_errors"} or watcher_code != 0:
                        record(f"Historical index watcher exited with status {watcher_code}; restarting")
                        historical_watcher = start_historical_watcher(
                            max(args.historical_update_interval_seconds, 5)
                        )
                if sha and sha not in skipped_during_run:
                    if sha != watched_sha:
                        watched_sha = sha
                        watched_since = time.monotonic()
                    elif watched_since is not None and time.monotonic() - watched_since >= args.stall_timeout_seconds:
                        record(
                            f"File stalled for {args.stall_timeout_seconds}s; terminating parser and skipping {sha}"
                        )
                        stop_process_group(process)
                        skipped_during_run.add(sha)
                        break
                else:
                    watched_sha = None
                    watched_since = None
                time.sleep(max(args.poll_seconds, 1))

            if process.poll() is not None:
                if process.returncode != 0:
                    if historical_watcher is not None:
                        stop_process_group(historical_watcher)
                    try:
                        publish_historical_once()
                    except Exception as exc:
                        record(f"Final /historical publish failed: {exc}")
                    record(f"Parser exited with status {process.returncode}; stopping supervisor")
                    return process.returncode
                state = read_status()
                if state.get("status") in {"complete", "complete_with_errors"}:
                    if historical_watcher is not None:
                        try:
                            historical_watcher.wait(timeout=max(args.historical_update_interval_seconds, 5) + 20)
                        except subprocess.TimeoutExpired:
                            stop_process_group(historical_watcher)
                            publish_historical_once()
                        historical_watcher = None
                    else:
                        publish_historical_once()
                    record(f"Parser finished with status {state['status']}")
                    return 0
                if historical_watcher is not None:
                    stop_process_group(historical_watcher)
                try:
                    publish_historical_once()
                except Exception as exc:
                    record(f"Final /historical publish failed: {exc}")
                record("Parser exited before completion; stopping supervisor")
                return 1
    except KeyboardInterrupt:
        record("Stop requested; terminating parser")
        child = locals().get("process")
        if child is not None:
            stop_process_group(child)
        if historical_watcher is not None:
            stop_process_group(historical_watcher)
        try:
            publish_historical_once()
        except Exception as exc:
            record(f"Partial /historical publish failed: {exc}")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
