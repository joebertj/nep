#!/usr/bin/env python3
"""Sequential, resumable OCR extraction for the FY2019 GAA Volume IA PDF.

The raw page text is retained as evidence. This source is a scanned volume,
so the output is an OCR transcription and must not be treated as a complete
FY2019 GAA dataset or a DPWH project list.
"""

import argparse
import json
import os
import re
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("FLAGS_cpu_num_threads", "1")

import pymupdf
from paddleocr import PaddleOCR

ROOT = Path(__file__).resolve().parent
PDF = ROOT / "research_downloads/philgeps_dime_2019gaa/fy2019-gaa-volume-ia.pdf"
OUT = ROOT / "data_sources/gaa_2019_volume_ia"
JSONL = OUT / "pages.jsonl"
AMOUNT_CANDIDATE = re.compile(
    r"(?<![A-Z0-9])(?:₱\s*)?(\d{1,3}(?:,\d{3})+(?:\.\d{2})?|\d{6,}(?:\.\d{2})?)(?![A-Z0-9])",
    re.IGNORECASE,
)
SUBTOTAL_LABEL = re.compile(r"\bSUB[\s-]*TOTAL\b|\bTOTAL\s+OF\s+(?:ITEMS|SUBPROGRAMS)\b", re.IGNORECASE)
TOTAL_LABEL = re.compile(r"^\s*(?:GRAND\s+)?TOTAL\b|\bTOTAL\s+APPROPRIATION\b", re.IGNORECASE)


def classify_line(line):
    """Classify OCR rows without dropping subtotals or other table lines."""
    text = line.get("text", "")
    if SUBTOTAL_LABEL.search(text):
        return "subtotal"
    if TOTAL_LABEL.search(text):
        return "total"
    if line.get("amount_candidates"):
        return "line_item"
    return "text"


def result_text(result):
    """Normalize PaddleOCR 3.x result object to plain recognized text."""
    if hasattr(result, "json"):
        value = result.json
        if callable(value):
            value = value()
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            value = value.get("res", value)
        if isinstance(value, dict):
            texts = value.get("rec_texts", [])
            scores = value.get("rec_scores", [])
            return [{"text": str(t), "confidence": float(scores[i]) if i < len(scores) else None}
                    for i, t in enumerate(texts)]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--end-page", type=int)
    parser.add_argument("--limit", type=int, help="Process at most this many unprocessed pages")
    parser.add_argument("--rebuild-fields", action="store_true",
                        help="Recompute line numbers, amount candidates, and subtotal/total labels")
    args = parser.parse_args()
    if args.rebuild_fields:
        if not JSONL.exists():
            raise SystemExit(f"No OCR output to rebuild: {JSONL}")
        temp_path = JSONL.with_suffix(".jsonl.tmp")
        with JSONL.open(encoding="utf-8") as source, temp_path.open("w", encoding="utf-8") as target:
            for raw in source:
                page = json.loads(raw)
                lines = page.get("lines", [])
                for line_no, line in enumerate(lines, start=1):
                    line["line_no"] = line_no
                    line["amount_candidates"] = AMOUNT_CANDIDATE.findall(line.get("text", ""))
                    line["row_type"] = classify_line(line)
                page["text"] = "\n".join(line.get("text", "") for line in lines)
                target.write(json.dumps(page, ensure_ascii=False) + "\n")
        temp_path.replace(JSONL)
        print(f"Updated searchable line fields in {JSONL}")
        return
    if not PDF.exists():
        raise SystemExit(f"Missing source PDF: {PDF}")
    OUT.mkdir(parents=True, exist_ok=True)
    done = set()
    if JSONL.exists():
        with JSONL.open(encoding="utf-8") as existing:
            for line in existing:
                try:
                    done.add(int(json.loads(line)["page"]))
                except (ValueError, KeyError, json.JSONDecodeError):
                    continue

    pdf = pymupdf.open(PDF)
    first = max(1, args.start_page)
    last = min(args.end_page or len(pdf), len(pdf))
    todo = [p for p in range(first, last + 1) if p not in done]
    if args.limit:
        todo = todo[:args.limit]
    ocr = PaddleOCR(lang="en", ocr_version="PP-OCRv5",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False)
    scale = args.dpi / 72
    matrix = pymupdf.Matrix(scale, scale)
    with JSONL.open("a", encoding="utf-8") as out:
        for page_no in todo:
            pix = pdf[page_no - 1].get_pixmap(matrix=matrix, alpha=False)
            image_path = OUT / f".page-{page_no:04d}.png"
            pix.save(image_path)
            try:
                result = ocr.predict(str(image_path))
                lines = result_text(result[0]) if result else []
            finally:
                image_path.unlink(missing_ok=True)
            for line_no, line in enumerate(lines, start=1):
                line["line_no"] = line_no
                # Candidates are preserved as OCR strings; they are not
                # silently promoted to verified appropriation amounts.
                line["amount_candidates"] = AMOUNT_CANDIDATE.findall(line["text"])
                line["row_type"] = classify_line(line)
            text = "\n".join(x["text"] for x in lines)
            row = {
                "page": page_no,
                "source": "fy2019-gaa-volume-ia.pdf",
                "coverage": "FY2019 GAA Volume IA only; OCR transcription",
                "dpi": args.dpi,
                "lines": lines,
                "text": text,
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            print(f"page {page_no}/{last}: {len(lines)} OCR lines", flush=True)


if __name__ == "__main__":
    main()
