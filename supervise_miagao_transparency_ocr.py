#!/usr/bin/env python3
"""Run the Miagao OCR parser with an independent per-file stall watchdog.

The parser already times out its OCR worker. This supervisor is a second guard:
if the parser itself stops making progress while a file is current, it terminates
the parser process group, persistently skips that file, and resumes the queue.
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


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--stall-timeout-seconds", type=int, default=360)
    cli.add_argument("--poll-seconds", type=int, default=10)
    cli.add_argument("--document-timeout-seconds", type=int, default=30)
    cli.add_argument("--worker-start-timeout-seconds", type=int, default=300)
    cli.add_argument("--retry-errors", action="store_true")
    cli.add_argument("--max-documents", type=int, default=0)
    args = cli.parse_args()

    skipped_during_run: set[str] = set()
    try:
        while True:
            command = [
                sys.executable,
                str(PARSER),
                "--document-timeout-seconds",
                str(args.document_timeout_seconds),
                "--worker-start-timeout-seconds",
                str(args.worker_start_timeout_seconds),
            ]
            if args.max_documents:
                command.extend(["--max-documents", str(args.max_documents)])
            if args.retry_errors:
                command.append("--retry-errors")
            for sha in sorted(skipped_during_run):
                command.extend(["--skip-file", sha])

            record("Starting or resuming the Miagao OCR parser")
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
                    record(f"Parser exited with status {process.returncode}; stopping supervisor")
                    return process.returncode
                state = read_status()
                if state.get("status") in {"complete", "complete_with_errors"}:
                    record(f"Parser finished with status {state['status']}")
                    return 0
                record("Parser exited before completion; stopping supervisor")
                return 1
    except KeyboardInterrupt:
        record("Stop requested; terminating parser")
        child = locals().get("process")
        if child is not None:
            stop_process_group(child)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
