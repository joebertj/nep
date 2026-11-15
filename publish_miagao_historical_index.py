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
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
OCR_DIR = ROOT / "analysis_output/miagao-transparency-ocr"
INVENTORY = ROOT / "analysis_output/miagao-transparency-source-inventory.json"
DEFAULT_OUTPUT = ROOT.parent / "bettermiagao/public/data/miagao-historical-index.json"
DEFAULT_PREVIEW_OUTPUT = ROOT.parent / "bettermiagao/dist/data/miagao-historical-index.json"


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
    source_hashes = set()
    parser_candidate_hashes = set()
    pdf_candidate_hashes = set()
    jpeg_candidate_hashes = set()

    for source in inventory.get("linkedUrls", []):
        archive = source.get("archive") or {}
        sha = archive.get("sha256")
        if not sha:
            continue
        source_hashes.add(sha)
        extension = Path(urlparse(source.get("url", "")).path).suffix.lower()
        if extension == ".pdf":
            pdf_candidate_hashes.add(sha)
            parser_candidate_hashes.add(sha)
        elif extension in {".jpg", ".jpeg"}:
            jpeg_candidate_hashes.add(sha)
            parser_candidate_hashes.add(sha)

    for source in inventory.get("linkedUrls", []):
        archive = source.get("archive") or {}
        sha = archive.get("sha256")
        local_path = archive.get("localPath")
        if not sha or not local_path:
            continue
        if sha not in parser_candidate_hashes:
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
        # A URL may be attached to a new official post after its bytes were
        # archived and parsed. Keep the parser's stable document references,
        # while refreshing the latest post/page references from each crawl.
        refs_by_key = {}
        for ref in [*(result.get("sourceDocumentUrls") or []), *(source.get("sources") or [])]:
            normalized = dict(ref)
            normalized["documentUrl"] = ref.get("documentUrl") or source.get("url")
            normalized["sourcePageUrl"] = ref.get("sourcePageUrl") or ref.get("sourceUrl")
            key = (normalized["documentUrl"], normalized["sourcePageUrl"])
            refs_by_key.setdefault(key, {}).update(normalized)
        refs = list(refs_by_key.values())
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
    error_hashes = {
        path.name.removesuffix(".error.json")
        for path in (OCR_DIR / "documents").glob("*.error.json")
    } & parser_candidate_hashes
    skipped_candidate_hashes = skipped_hashes & parser_candidate_hashes
    error_documents = len(error_hashes)
    source_documents = len(source_hashes)
    completed_documents = len(seen_hashes)
    summary = {
        "sourceDocuments": source_documents,
        "parserCandidateDocuments": len(parser_candidate_hashes),
        "completedDocuments": completed_documents,
        "pdfCandidateDocuments": len(pdf_candidate_hashes),
        "pdfCompletedDocuments": len(seen_hashes & pdf_candidate_hashes),
        "jpegCandidateDocuments": len(jpeg_candidate_hashes),
        "jpegCompletedDocuments": len(seen_hashes & jpeg_candidate_hashes),
        "unsupportedDocuments": max(0, source_documents - len(parser_candidate_hashes)),
        "ocrPageRows": ocr_pages,
        "nativeTextDocuments": native_text_documents,
        "errorDocuments": error_documents,
        "intentionallySkippedDocuments": len(skipped_candidate_hashes),
        "pendingDocuments": max(
            0,
            len(parser_candidate_hashes)
            - completed_documents
            - error_documents
            - len(skipped_candidate_hashes),
        ),
    }
    payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "parserStatus": status.get("status", "unknown"),
        "parserUpdatedAtUtc": status.get("updatedAtUtc"),
        "summary": summary,
        "rows": sorted(rows, key=lambda row: (row.get("publishedAt") or "", row["sourceTitle"].lower()), reverse=True),
    }
    outputs = [args.output]
    if args.output.resolve() == DEFAULT_OUTPUT.resolve() and DEFAULT_PREVIEW_OUTPUT.parent.is_dir():
        outputs.append(DEFAULT_PREVIEW_OUTPUT)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(output)
    print(json.dumps({"outputs": [str(output) for output in outputs], **summary}, indent=2))


if __name__ == "__main__":
    main()
