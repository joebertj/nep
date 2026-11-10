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
import hashlib
import json
import os
import re
import sys
import time
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
MIN_NATIVE_TEXT_CHARS = 200
IMAGE_COVERAGE_TEXT_CEILING = 1200
USER_AGENT = "BetterMiagao transparency OCR"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


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


def image_for_pdf_page(page, fitz, Image):
    pix = page.get_pixmap(matrix=fitz.Matrix(2.25, 2.25), alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def ocr_result(ocr, image, np):
    result = ocr.predict(np.asarray(image))[0]
    texts = result.get("rec_texts")
    scores = result.get("rec_scores")
    boxes = result.get("rec_boxes")
    texts = [] if texts is None else list(texts)
    scores = [] if scores is None else list(scores)
    boxes = [] if boxes is None else list(boxes)
    tokens = []
    for index, text in enumerate(texts):
        text = clean_text(text)
        if not text:
            continue
        confidence = None
        if index < len(scores):
            try:
                confidence = round(float(scores[index]), 4)
            except (TypeError, ValueError):
                pass
        box = None
        if index < len(boxes):
            try:
                box = [round(float(v), 1) for v in boxes[index]]
            except (TypeError, ValueError):
                pass
        tokens.append({"text": text, "confidence": confidence, "boxPx": box})
    text = "\n".join(token["text"] for token in tokens)
    confidence_values = [token["confidence"] for token in tokens if token["confidence"] is not None]
    return {
        "ocrText": text,
        "tokens": tokens,
        "tokenCount": len(tokens),
        "meanConfidence": round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None,
    }


def parse_document(item, ocr, fitz, Image, ImageOps, np):
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
            for page_item in pages:
                page = doc[page_item["pageNumber"] - 1]
                image = image_for_pdf_page(page, fitz, Image)
                extracted = ocr_result(ocr, image, np)
                output_rows.append({
                    "sourceFileSha256": item["sha256"],
                    "sourceFileBytes": item.get("bytes"),
                    "sourceArchivePath": item["localPath"],
                    "sourceDocumentUrls": item["urls"],
                    "sourceFileName": item["urls"][0]["fileName"] if item["urls"] else path.name,
                    "pageNumber": page_item["pageNumber"],
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
                    "extractionMethod": "PyMuPDF native text + PaddleOCR PP-OCRv5 scan-page OCR" if page_item["nativeText"] else "PaddleOCR PP-OCRv5 scan-page OCR",
                    "parseStatus": "ocr_text_found" if extracted["tokenCount"] else "no_text_detected",
                })
        finally:
            doc.close()
    else:
        with Image.open(path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            extracted = ocr_result(ocr, image, np)
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
            "extractionMethod": "PaddleOCR PP-OCRv5 image OCR",
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
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DOC_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import pymupdf as fitz
        import numpy as np
        from PIL import Image, ImageOps
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise SystemExit(f"OCR dependencies unavailable in this environment: {exc}") from exc

    inventory, documents = inventory_documents()
    completed = []
    pending = []
    for item in documents:
        result_path = DOC_DIR / f"{item['sha256']}.json"
        if result_path.exists():
            completed.append(item)
            continue
        pending.append(item)
    if args.rebuild_rows:
        count = refresh_rows(completed)
        print(f"Rebuilt {ROWS_PATH} with {count} page/image rows", flush=True)
        return
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
            discovery_errors.append({"sourceFileSha256": item["sha256"], "sourceArchivePath": item["localPath"], "error": f"{type(exc).__name__}: {exc}"})

    state = {
        "title": "Miagao transparency OCR parser",
        "updatedAtUtc": now(),
        "status": "starting",
        "inventoryGeneratedAt": inventory.get("generatedAt"),
        "sourceDocuments": len(documents),
        "uniqueOcrCandidateFiles": len(candidates),
        "pendingOcrDocuments": len(candidates),
        "completedDocuments": len(completed),
        "discoveryErrors": discovery_errors,
        "current": None,
        "rowsPath": str(ROWS_PATH.relative_to(ROOT)),
    }
    write_json(STATUS_PATH, state)
    print(f"OCR queue: {len(candidates)} unique image/scan files; {len(completed)} source PDFs already have sufficient native text or prior results.", flush=True)
    print(f"Initializing PaddleOCR from cached local models; results retain source URL, post, SHA-256, and page.", flush=True)
    ocr = PaddleOCR(lang="en", ocr_version="PP-OCRv5", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)

    successful = []
    failed = list(discovery_errors)
    total_pages = 0
    for index, item in enumerate(candidates, 1):
        state.update({"status": "processing", "updatedAtUtc": now(), "current": {"index": index, "total": len(candidates), "sha256": item["sha256"], "file": item["urls"][0]["fileName"] if item["urls"] else item["localPath"], "ocrPages": item["ocrPages"]}})
        write_json(STATUS_PATH, state)
        try:
            rows = parse_document(item, ocr, fitz, Image, ImageOps, np)
            write_json(DOC_DIR / f"{item['sha256']}.json", {
                "sourceFileSha256": item["sha256"],
                "sourceArchivePath": item["localPath"],
                "sourceDocumentUrls": item["urls"],
                "ocrPageNumbers": item["ocrPages"],
                "rows": rows,
            })
            successful.append(item)
            total_pages += len(rows)
            print(f"[{index}/{len(candidates)}] {len(rows)} OCR pages · {item['urls'][0]['fileName'] if item['urls'] else item['localPath']}", flush=True)
            state.update({"completedOcrDocuments": index, "completedOcrPages": total_pages, "lastCompletedAtUtc": now(), "current": None})
        except Exception as exc:
            error = {"sourceFileSha256": item["sha256"], "sourceArchivePath": item["localPath"], "sourceDocumentUrls": item["urls"], "error": f"{type(exc).__name__}: {exc}"}
            failed.append(error)
            print(f"[{index}/{len(candidates)}] ERROR {item['localPath']}: {error['error']}", flush=True)
            # Persist failures separately; the next run can retry them.
            write_json(DOC_DIR / f"{item['sha256']}.error.json", error)
            state["current"] = None
        state["failedDocuments"] = len(failed)
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
        "errors": failed,
    })
    write_json(STATUS_PATH, state)
    print(json.dumps({key: state[key] for key in ("status", "sourceDocuments", "uniqueOcrCandidateFiles", "completedDocuments", "completedOcrDocuments", "ocrPageRows", "failedDocuments", "rowsPath")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
