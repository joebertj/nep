#!/usr/bin/env python3
"""OCR Miagao transparency scans and image-only PDF pages.

Rows are saved per source file so an interrupted run can resume without
re-OCRing completed files. Every output row carries the original document URL,
the post/page that linked it, the local archive path and file SHA-256, and the
exact image/PDF page number. XLS/XLSX files and text-readable PDF pages are
left to their structured/native-text parsers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT / "analysis_output/miagao-transparency-source-inventory.json"
OUT_DIR = ROOT / "analysis_output/miagao-transparency-ocr"
DOC_DIR = OUT_DIR / "documents"
STATUS_PATH = OUT_DIR / "status.json"
ROWS_PATH = OUT_DIR / "ocr-rows.jsonl"
ERRORS_PATH = OUT_DIR / "errors.jsonl"
SKIP_LIST_PATH = OUT_DIR / "skip-list.json"
MIN_NATIVE_TEXT_CHARS = 200
IMAGE_COVERAGE_TEXT_CEILING = 1200
USER_AGENT = "BetterMiagao transparency OCR"
TESSERACT = shutil.which("tesseract")
if not TESSERACT:
    homebrew_tesseract = Path("/opt/homebrew/opt/tesseract/bin/tesseract")
    TESSERACT = str(homebrew_tesseract) if homebrew_tesseract.is_file() else None


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def append_error(payload):
    ERRORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ERRORS_PATH.open("a", encoding="utf-8") as out:
        out.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def inventory_documents():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    groups = {}
    for item in inventory.get("linkedUrls", []):
        archive = item.get("archive") or {}
        local_path = archive.get("localPath")
        sha = archive.get("sha256")
        if not local_path or not sha:
            continue
        ext = Path(urlparse(item["url"]).path).suffix.lower()
        if ext not in {".pdf", ".jpg", ".jpeg"}:
            continue
        group = groups.setdefault(sha, {
            "sha256": sha,
            "localPath": local_path,
            "bytes": archive.get("bytes"),
            "extension": ext,
            "urls": [],
        })
        for source in item.get("sources", []):
            ref = {
                "documentUrl": item["url"],
                "sourcePageUrl": source.get("sourceUrl"),
                "sourceTitle": source.get("sourceTitle"),
                "publishedAt": source.get("sourceDate"),
                "sourceElement": source.get("element"),
                "sourceAttribute": source.get("attribute"),
                "fileName": Path(unquote(urlparse(item["url"]).path)).name,
            }
            key = (ref["documentUrl"], ref["sourcePageUrl"])
            if all((old["documentUrl"], old["sourcePageUrl"]) != key for old in group["urls"]):
                group["urls"].append(ref)
    return inventory, list(groups.values())


def document_identifiers(item):
    identifiers = {item["sha256"].lower(), item["localPath"].lower()}
    identifiers.add(Path(item["localPath"]).name.lower())
    for ref in item["urls"]:
        identifiers.add(ref["fileName"].lower())
        identifiers.add(ref["documentUrl"].lower())
    return identifiers


def update_skip_list(documents, add_values, remove_values):
    entries = json.loads(SKIP_LIST_PATH.read_text(encoding="utf-8")) if SKIP_LIST_PATH.exists() else []
    by_sha = {entry["sha256"]: entry for entry in entries}

    def resolve(value):
        query = value.strip().lower()
        matches = [item for item in documents if query in document_identifiers(item)]
        if not matches:
            raise SystemExit(f"Skip-list identifier did not match an inventory document: {value}")
        if len(matches) > 1:
            raise SystemExit(f"Skip-list identifier is ambiguous; use a SHA-256 or archive path: {value}")
        return matches[0]

    for value in remove_values:
        item = resolve(value)
        by_sha.pop(item["sha256"], None)
    for value in add_values:
        item = resolve(value)
        by_sha[item["sha256"]] = {
            "sha256": item["sha256"],
            "localPath": item["localPath"],
            "fileName": item["urls"][0]["fileName"] if item["urls"] else Path(item["localPath"]).name,
            "addedAtUtc": now(),
        }

    entries = sorted(by_sha.values(), key=lambda entry: entry["sha256"])
    if entries or SKIP_LIST_PATH.exists() or add_values or remove_values:
        write_json(SKIP_LIST_PATH, entries)
    return by_sha


def alpha_count(text: str) -> int:
    return sum(char.isalpha() for char in text)


def pdf_ocr_pages(path: Path, fitz):
    doc = fitz.open(path)
    pages = []
    for index, page in enumerate(doc):
        native = page.get_text("text") or ""
        text_chars = alpha_count(native)
        page_area = max(float(page.rect.width * page.rect.height), 1.0)
        image_area = 0.0
        try:
            for info in page.get_image_info(xrefs=True):
                bbox = info.get("bbox")
                if bbox and len(bbox) == 4:
                    x0, y0, x1, y1 = map(float, bbox)
                    image_area += max(0.0, x1 - x0) * max(0.0, y1 - y0)
        except Exception:
            pass
        coverage = min(1.0, image_area / page_area)
        needs_ocr = text_chars < MIN_NATIVE_TEXT_CHARS or (
            coverage >= 0.30 and text_chars < IMAGE_COVERAGE_TEXT_CEILING
        )
        if needs_ocr:
            pages.append({
                "pageNumber": index + 1,
                "nativeText": clean_text(native),
                "nativeTextCharacters": text_chars,
                "imageCoverageRatio": round(coverage, 4),
            })
    return doc, pages


def run_tesseract_ocr(image_path: Path, timeout: int):
    if not TESSERACT:
        raise RuntimeError("Tesseract is required for scan OCR; install it before resuming this queue")
    result = subprocess.run(
        [TESSERACT, str(image_path), "stdout", "--psm", "3", "tsv"],
        capture_output=True, text=True, timeout=timeout, check=True,
        env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
    )
    tokens = []
    lines: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
        text = clean_text(row.get("text", ""))
        if not text:
            continue
        try:
            left, top = float(row["left"]), float(row["top"])
            width, height = float(row["width"]), float(row["height"])
            confidence = float(row["conf"])
        except (KeyError, TypeError, ValueError):
            continue
        if confidence < 0:
            confidence = None
        else:
            confidence = round(confidence / 100, 4)
        tokens.append({"text": text, "confidence": confidence,
                       "boxPx": [left, top, left + width, top + height]})
        key = (row.get("block_num", ""), row.get("par_num", ""), row.get("line_num", ""))
        lines[key].append(text)
    return {"ocrText": "\n".join(" ".join(words) for words in lines.values()), "tokens": tokens}


def summarize_ocr(extracted):
    confidences = [float(token["confidence"]) for token in extracted["tokens"] if token.get("confidence") is not None]
    return {
        "ocrText": extracted["ocrText"],
        "tokens": extracted["tokens"],
        "tokenCount": len(extracted["tokens"]),
        "meanConfidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
    }


def parse_document(item, fitz, timeout):
    path = ROOT / item["localPath"]
    if not path.is_file():
        raise FileNotFoundError(f"Archived file not found: {item['localPath']}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["sha256"]:
        raise ValueError("Archived file SHA-256 does not match the inventory")
    output_rows = []
    ext = item["extension"]
    if ext == ".pdf":
        doc, pages = pdf_ocr_pages(path, fitz)
        try:
            with tempfile.TemporaryDirectory(prefix="miagao-tesseract-") as temp_dir:
                for page_item in pages:
                    page_number = page_item["pageNumber"]
                    image_path = Path(temp_dir) / f"page-{page_number}.png"
                    doc[page_number - 1].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False).save(image_path)
                    extracted = summarize_ocr(run_tesseract_ocr(image_path, timeout))
                    output_rows.append({
                        "sourceFileSha256": item["sha256"],
                        "sourceFileBytes": item.get("bytes"),
                        "sourceArchivePath": item["localPath"],
                        "sourceDocumentUrls": item["urls"],
                        "sourceFileName": item["urls"][0]["fileName"] if item["urls"] else path.name,
                        "pageNumber": page_number,
                        "worksheetName": None,
                        "sourceRowNumber": None,
                        "nativeText": page_item["nativeText"],
                        "extractedText": "\n".join(v for v in [page_item["nativeText"], extracted["ocrText"]] if v),
                        "ocrText": extracted["ocrText"],
                        "ocrTokenCount": extracted["tokenCount"],
                        "ocrMeanConfidence": extracted["meanConfidence"],
                        "ocrTokens": extracted["tokens"],
                        "nativeTextCharacters": page_item["nativeTextCharacters"],
                        "imageCoverageRatio": page_item["imageCoverageRatio"],
                        "extractionMethod": "PyMuPDF native text + Tesseract OCR" if page_item["nativeText"] else "Tesseract OCR",
                        "parseStatus": "ocr_text_found" if extracted["tokenCount"] else "no_text_detected",
                    })
        finally:
            doc.close()
    else:
        extracted = summarize_ocr(run_tesseract_ocr(path, timeout))
        output_rows.append({
            "sourceFileSha256": item["sha256"],
            "sourceFileBytes": item.get("bytes"),
            "sourceArchivePath": item["localPath"],
            "sourceDocumentUrls": item["urls"],
            "sourceFileName": item["urls"][0]["fileName"] if item["urls"] else path.name,
            "pageNumber": 1,
            "worksheetName": None,
            "sourceRowNumber": None,
            "nativeText": "",
            "extractedText": extracted["ocrText"],
            "ocrText": extracted["ocrText"],
            "ocrTokenCount": extracted["tokenCount"],
            "ocrMeanConfidence": extracted["meanConfidence"],
            "ocrTokens": extracted["tokens"],
            "nativeTextCharacters": 0,
            "imageCoverageRatio": 1.0,
            "extractionMethod": "Tesseract image OCR",
            "parseStatus": "ocr_text_found" if extracted["tokenCount"] else "no_text_detected",
        })
    return output_rows


def refresh_rows(completed):
    temp = ROWS_PATH.with_suffix(".jsonl.tmp")
    total = 0
    with temp.open("w", encoding="utf-8") as out:
        for item in completed:
            doc_path = DOC_DIR / f"{item['sha256']}.json"
            if not doc_path.exists():
                continue
            payload = json.loads(doc_path.read_text(encoding="utf-8"))
            for row in payload.get("rows", []):
                out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                total += 1
    temp.replace(ROWS_PATH)
    return total


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-documents", type=int, default=0, help="optional cap for a partial run; zero processes all OCR candidates")
    parser.add_argument("--rebuild-rows", action="store_true", help="rebuild the unified OCR JSONL from completed per-document results")
    parser.add_argument("--retry-errors", action="store_true", help="retry files with a saved .error.json record; skipped by default")
    parser.add_argument("--retry-error-records", action="store_true", help="after the main queue, retry unique files recorded in errors.jsonl and current error markers, including files with older saved results")
    parser.add_argument("--skip-file", action="append", default=[], metavar="SHA256|PATH|NAME", help="persistently skip a file (repeatable; accepts SHA-256, archive path, or unique filename)")
    parser.add_argument("--unskip-file", action="append", default=[], metavar="SHA256|PATH|NAME", help="remove a file from the persistent skip list (repeatable)")
    parser.add_argument("--document-timeout-seconds", type=int, default=30, help="skip and log a file if OCR exceeds this time")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    inventory, documents = inventory_documents()
    skipped_files = update_skip_list(documents, args.skip_file, args.unskip_file)
    retry_error_hashes: set[str] = set()
    if args.retry_error_records:
        if ERRORS_PATH.exists():
            with ERRORS_PATH.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        digest = json.loads(line).get("sourceFileSha256")
                    except (json.JSONDecodeError, AttributeError):
                        continue
                    if digest:
                        retry_error_hashes.add(digest)
        retry_error_hashes.update(path.name.removesuffix(".error.json") for path in DOC_DIR.glob("*.error.json"))
    completed = []
    pending = []
    prior_errors = []
    intentionally_skipped = []
    for item in documents:
        if item["sha256"] in skipped_files:
            intentionally_skipped.append(item)
            continue
        if args.retry_error_records:
            if item["sha256"] in retry_error_hashes:
                pending.append(item)
            elif (DOC_DIR / f"{item['sha256']}.json").exists():
                completed.append(item)
            continue
        result_path = DOC_DIR / f"{item['sha256']}.json"
        if result_path.exists():
            completed.append(item)
            continue
        error_path = DOC_DIR / f"{item['sha256']}.error.json"
        if error_path.exists() and not args.retry_errors:
            prior_errors.append(json.loads(error_path.read_text(encoding="utf-8")))
            continue
        pending.append(item)
    if args.rebuild_rows:
        count = refresh_rows(completed)
        if STATUS_PATH.exists():
            status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
            status.update({
                "updatedAtUtc": now(),
                "intentionallySkippedDocuments": len(intentionally_skipped),
                "skipListPath": str(SKIP_LIST_PATH.relative_to(ROOT)),
                "skippedFiles": [
                    {"sha256": item["sha256"], "localPath": item["localPath"],
                     "fileName": item["urls"][0]["fileName"] if item["urls"] else Path(item["localPath"]).name}
                    for item in intentionally_skipped
                ],
            })
            current = status.get("current") or {}
            if current.get("sha256") in skipped_files:
                status.update({
                    "status": "paused",
                    "current": None,
                    "resumeNote": "Run the parser to continue; intentionally skipped files are excluded from the queue.",
                })
            write_json(STATUS_PATH, status)
        print(f"Rebuilt {ROWS_PATH} with {count} page/image rows; {len(intentionally_skipped)} files are on the persistent skip list", flush=True)
        return

    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise SystemExit(f"PDF text/rendering dependency unavailable in this environment: {exc}") from exc
    if not TESSERACT:
        raise SystemExit("Tesseract is required for scan OCR; install it before resuming this queue.")
    if args.max_documents:
        pending = pending[: args.max_documents]

    # Source-text checks keep selectable PDF pages out of the OCR queue.
    candidates = []
    discovery_errors = []
    for item in pending:
        if item["extension"] in {".jpg", ".jpeg"}:
            item["ocrPages"] = [1]
            candidates.append(item)
            continue
        try:
            doc, page_items = pdf_ocr_pages(ROOT / item["localPath"], fitz)
            doc.close()
            if page_items:
                item["ocrPages"] = [page["pageNumber"] for page in page_items]
                candidates.append(item)
            else:
                item["ocrPages"] = []
                # Record a source-document-level skip so it is accounted for.
                write_json(DOC_DIR / f"{item['sha256']}.json", {
                    "sourceFileSha256": item["sha256"], "sourceArchivePath": item["localPath"],
                    "sourceDocumentUrls": item["urls"], "rows": [], "parseStatus": "native_text_sufficient",
                })
                completed.append(item)
        except Exception as exc:
            error = {"sourceFileSha256": item["sha256"], "sourceArchivePath": item["localPath"], "sourceDocumentUrls": item["urls"], "stage": "discovery", "error": f"{type(exc).__name__}: {exc}"}
            discovery_errors.append(error)
            write_json(DOC_DIR / f"{item['sha256']}.error.json", error)
            append_error(error)

    state = {
        "title": "Miagao transparency parser",
        "ocrEngine": "Tesseract OCR, single-threaded",
        "existingCompletedResultsReused": len(completed),
        "updatedAtUtc": now(),
        "status": "starting",
        "inventoryGeneratedAt": inventory.get("generatedAt"),
        "sourceDocuments": len(documents),
        "uniqueOcrCandidateFiles": len(candidates),
        "pendingOcrDocuments": len(candidates),
        "completedDocuments": len(completed),
        "skippedPriorErrors": len(prior_errors),
        "retryErrorRecordFiles": len([item for item in pending if item["sha256"] in retry_error_hashes]),
        "intentionallySkippedDocuments": len(intentionally_skipped),
        "skipListPath": str(SKIP_LIST_PATH.relative_to(ROOT)),
        "discoveryErrors": discovery_errors,
        "current": None,
        "rowsPath": str(ROWS_PATH.relative_to(ROOT)),
    }
    write_json(STATUS_PATH, state)
    queue_label = "error-record retry queue" if args.retry_error_records else "OCR queue"
    print(f"{queue_label}: {len(candidates)} unique image/scan files; {len(completed)} completed; {len(intentionally_skipped)} intentionally skipped; {len(prior_errors)} prior failures skipped.", flush=True)
    successful = []
    failed = list(prior_errors) + list(discovery_errors)
    total_pages = 0
    for index, item in enumerate(candidates, 1):
        state.update({"status": "processing", "updatedAtUtc": now(), "current": {"index": index, "total": len(candidates), "sha256": item["sha256"], "file": item["urls"][0]["fileName"] if item["urls"] else item["localPath"], "ocrPages": item["ocrPages"]}})
        write_json(STATUS_PATH, state)
        try:
            rows = parse_document(item, fitz, args.document_timeout_seconds)
            write_json(DOC_DIR / f"{item['sha256']}.json", {
                "sourceFileSha256": item["sha256"],
                "sourceArchivePath": item["localPath"],
                "sourceDocumentUrls": item["urls"],
                "ocrPageNumbers": item["ocrPages"],
                "rows": rows,
            })
            (DOC_DIR / f"{item['sha256']}.error.json").unlink(missing_ok=True)
            successful.append(item)
            total_pages += len(rows)
            print(f"[{index}/{len(candidates)}] {len(rows)} OCR pages · {item['urls'][0]['fileName'] if item['urls'] else item['localPath']}", flush=True)
            state.update({"completedOcrDocuments": index, "completedOcrPages": total_pages, "lastCompletedAtUtc": now(), "current": None})
        except Exception as exc:
            error = {"sourceFileSha256": item["sha256"], "sourceArchivePath": item["localPath"], "sourceDocumentUrls": item["urls"], "stage": "ocr", "error": f"{type(exc).__name__}: {exc}"}
            failed.append(error)
            print(f"[{index}/{len(candidates)}] ERROR {item['localPath']}: {error['error']}", flush=True)
            # Save a per-file skip marker and a durable audit log; later passes skip it by default.
            write_json(DOC_DIR / f"{item['sha256']}.error.json", error)
            append_error(error)
            state["current"] = None
        state["failedDocuments"] = len(failed)
        state["completedDocuments"] = len(completed) + len(successful)
        state["skippedDocuments"] = len(failed)
        state["updatedAtUtc"] = now()
        write_json(STATUS_PATH, state)

    all_completed = []
    for item in documents:
        if (DOC_DIR / f"{item['sha256']}.json").exists():
            all_completed.append(item)
    row_count = refresh_rows(all_completed)
    state.update({
        "status": "complete" if not failed else "complete_with_errors",
        "updatedAtUtc": now(),
        "current": None,
        "completedDocuments": len(all_completed),
        "completedOcrDocuments": len(successful),
        "ocrPageRows": row_count,
        "failedDocuments": len(failed),
        "intentionallySkippedDocuments": len(intentionally_skipped),
        "skipListPath": str(SKIP_LIST_PATH.relative_to(ROOT)),
        "errors": failed,
    })
    write_json(STATUS_PATH, state)
    print(json.dumps({key: state[key] for key in ("status", "sourceDocuments", "uniqueOcrCandidateFiles", "completedDocuments", "completedOcrDocuments", "ocrPageRows", "failedDocuments", "rowsPath")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
