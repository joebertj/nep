#!/usr/bin/env python3
"""Periodically discover and download new documents from Miagao's official site."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CRAWLER = ROOT / "crawl_miagao_transparency.py"
SUPERVISOR = ROOT / "supervise_miagao_transparency_ocr.py"
PUBLISHER = ROOT / "publish_miagao_historical_index.py"
INVENTORY = ROOT / "analysis_output/miagao-transparency-source-inventory.json"
OCR_DIR = ROOT / "analysis_output/miagao-transparency-ocr/documents"
ELIGIBLE = {".pdf", ".jpg", ".jpeg"}


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {message}", flush=True)


def pending_documents() -> list[str]:
    try:
        inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read refreshed source inventory: {exc}") from exc

    pending: set[str] = set()
    for item in inventory.get("linkedUrls", []):
        archive = item.get("archive") or {}
        sha = archive.get("sha256")
        local_path = archive.get("localPath")
        ext = Path(item.get("url", "").split("?", 1)[0]).suffix.lower()
        if not sha or not local_path or ext not in ELIGIBLE:
            continue
        result = OCR_DIR / f"{sha}.json"
        error = OCR_DIR / f"{sha}.error.json"
        if not result.exists() and not error.exists():
            pending.add(sha)
    return sorted(pending)


def run_cycle() -> None:
    log("Checking the official Miagao transparency catalog and downloading linked uploads")
    subprocess.run([sys.executable, str(CRAWLER)], cwd=ROOT, check=True)
    pending = pending_documents()
    if pending:
        log(f"Found {len(pending)} new PDF/JPEG document(s); starting the Miagao parser")
        subprocess.run([sys.executable, str(SUPERVISOR)], cwd=ROOT, check=True)
    else:
        log("No new parser-supported documents found")
    subprocess.run([sys.executable, str(PUBLISHER)], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interval-seconds", type=int, default=6 * 60 * 60,
                        help="time between checks (default: six hours)")
    parser.add_argument("--once", action="store_true", help="check, download, parse and publish once, then exit")
    args = parser.parse_args()
    if args.interval_seconds < 60:
        parser.error("--interval-seconds must be at least 60")

    while True:
        started = time.monotonic()
        try:
            run_cycle()
        except subprocess.CalledProcessError as exc:
            log(f"Cycle failed (command exit {exc.returncode}); will retry next cycle")
            if args.once:
                return exc.returncode or 1
        except Exception as exc:
            log(f"Cycle failed ({type(exc).__name__}: {exc}); will retry next cycle")
            if args.once:
                return 1
        if args.once:
            return 0
        delay = max(0, args.interval_seconds - (time.monotonic() - started))
        log(f"Next official-site check in {int(delay)} seconds")
        try:
            time.sleep(delay)
        except KeyboardInterrupt:
            log("Stop requested")
            return 130


if __name__ == "__main__":
    raise SystemExit(main())
