#!/usr/bin/env python3
"""Publish completed Miagao transparency parser records for the Better Miagao site."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OCR_DIR = ROOT / "analysis_output/miagao-transparency-ocr"
INVENTORY = ROOT / "analysis_output/miagao-transparency-source-inventory.json"
DEFAULT_OUTPUT = ROOT.parent / "bettermiagao/public/data/miagao-historical-index.json"


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("BETTERMIAGAO_HISTORICAL_INDEX", DEFAULT_OUTPUT)),
        help="destination JSON file (defaults to the sibling Better Miagao public data folder)",
    )
    parser.add_argument(
        "--watch-seconds",
        type=int,
        default=0,
        help="republish periodically until the OCR parser finishes; zero publishes once",
    )
    args = parser.parse_args()

    if args.watch_seconds > 0:
        command = [sys.executable, str(Path(__file__).resolve()), "--output", str(args.output)]
        while True:
            subprocess.run(command, cwd=ROOT, check=True)
            status = read_json(OCR_DIR / "status.json", {})
            if status.get("status") in {"complete", "complete_with_errors"}:
                return
            time.sleep(max(args.watch_seconds, 5))

    inventory = read_json(INVENTORY, {})
    status = read_json(OCR_DIR / "status.json", {})
    skipped = read_json(OCR_DIR / "skip-list.json", [])
    skipped_hashes = {item.get("sha256") for item in skipped}
    completed_documents = 0
    ocr_pages = 0
    native_text_documents = 0
    rows = []
    seen_hashes = set()

    for source in inventory.get("linkedUrls", []):
        archive = source.get("archive") or {}
        sha = archive.get("sha256")
        local_path = archive.get("localPath")
        if not sha or not local_path:
            continue
        if sha in seen_hashes:
            continue
        seen_hashes.add(sha)
        result_path = OCR_DIR / "documents" / f"{sha}.json"
        result = read_json(result_path, None)
        if result is None:
            continue
        completed_documents += 1
        result_rows = result.get("rows") or []
        if result.get("parseStatus") == "native_text_sufficient" and not result_rows:
            native_text_documents += 1

        # Keep all source page references; a single archived file can be linked
        # from multiple official posts.
        refs = result.get("sourceDocumentUrls") or source.get("sources") or []
        if not refs:
            refs = [{"documentUrl": source.get("url")}]
        for page_index, page in enumerate(result_rows, start=1):
            page_refs = page.get("sourceDocumentUrls") or refs
            first_ref = page_refs[0] if page_refs else {}
            text = page.get("extractedText") or page.get("ocrText") or page.get("nativeText") or ""
            rows.append({
                "id": f"{sha}:{page.get('pageNumber') or page_index}",
                "documentSha256": sha,
                "sourceFileName": page.get("sourceFileName") or Path(local_path).name,
                "sourceArchivePath": local_path,
                "sourceFileBytes": page.get("sourceFileBytes") or archive.get("bytes"),
                "sourceTitle": first_ref.get("sourceTitle") or source.get("title") or Path(local_path).name,
                "publishedAt": first_ref.get("publishedAt") or first_ref.get("sourceDate"),
                "documentUrl": first_ref.get("documentUrl") or source.get("url"),
                "sourcePageUrl": first_ref.get("sourcePageUrl") or first_ref.get("sourceUrl"),
                "sourceReferences": page_refs,
                "pageNumber": page.get("pageNumber"),
                "extractionMethod": page.get("extractionMethod") or "Unknown",
                "parseStatus": page.get("parseStatus") or "parsed",
                "ocrMeanConfidence": page.get("ocrMeanConfidence"),
                "ocrTokenCount": page.get("ocrTokenCount"),
                "extractedText": text,
            })
        if not result_rows and result.get("parseStatus") == "native_text_sufficient":
            first_ref = refs[0] if refs else {}
            rows.append({
                "id": f"{sha}:native-text",
                "documentSha256": sha,
                "sourceFileName": Path(local_path).name,
                "sourceArchivePath": local_path,
                "sourceFileBytes": archive.get("bytes"),
                "sourceTitle": first_ref.get("sourceTitle") or source.get("title") or Path(local_path).name,
                "publishedAt": first_ref.get("publishedAt") or first_ref.get("sourceDate"),
                "documentUrl": first_ref.get("documentUrl") or source.get("url"),
                "sourcePageUrl": first_ref.get("sourcePageUrl") or first_ref.get("sourceUrl"),
                "sourceReferences": refs,
                "pageNumber": None,
                "extractionMethod": "Native text; no OCR required",
                "parseStatus": "native_text_sufficient",
                "ocrMeanConfidence": None,
                "ocrTokenCount": None,
                "extractedText": "",
            })

    ocr_pages = sum(row["pageNumber"] is not None for row in rows)
    error_documents = len(list((OCR_DIR / "documents").glob("*.error.json")))
    source_documents = len({
        (item.get("archive") or {}).get("sha256")
        for item in inventory.get("linkedUrls", [])
        if (item.get("archive") or {}).get("sha256")
    })
    summary = {
        "sourceDocuments": source_documents,
        "completedDocuments": completed_documents,
        "ocrPageRows": ocr_pages,
        "nativeTextDocuments": native_text_documents,
        "errorDocuments": error_documents,
        "intentionallySkippedDocuments": len(skipped_hashes),
        "pendingDocuments": max(
            0,
            source_documents - completed_documents - error_documents - len(skipped_hashes),
        ),
    }
    payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parserStatus": status.get("status", "unknown"),
        "parserUpdatedAtUtc": status.get("updatedAtUtc"),
        "summary": summary,
        "rows": sorted(rows, key=lambda row: (row.get("publishedAt") or "", row["sourceTitle"].lower()), reverse=True),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"output": str(args.output), **summary}, indent=2))


if __name__ == "__main__":
    main()
