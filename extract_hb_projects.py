#!/usr/bin/env python3
"""Extract complete visible DPWH allocations from HB 10858 Volume I-C.

Crop hidden neighbouring spread text, preserve full wrapped descriptions and
explicit printed amounts, and identify allocations through table hierarchy.
Both reading editions must reconcile with all seven printed program totals.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DEFAULT_PDF_DIR=ROOT/'HB 10858 FOR 2ND READING'
DEFAULT_OUT=ROOT/'hb10858_projects.json'

def extract_text(gs: str, pdf: Path, output: Path) -> None:
    output.mkdir(parents=True,exist_ok=True)
    result=subprocess.run([gs,'-q','-dNOPAUSE','-dBATCH','-dTextFormat=1','-sDEVICE=txtwrite',f'-sOutputFile={output}/page-%05d.xml',str(pdf)],capture_output=True,text=True)
    if result.returncode:
        raise RuntimeError(f'Could not read {pdf.name}: {result.stderr.strip() or result.stdout.strip()}')

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ghostscript", default="gs", help="Ghostscript executable (default: gs)")
    parser.add_argument("--text-cache", type=Path, help="Reuse/save page XML here; separate cache directory per edition")
    args = parser.parse_args()

    gs = shutil.which(args.ghostscript)
    if not gs:
        parser.error("Ghostscript is required. Install it with: brew install ghostscript")
    pdfs = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdfs:
        parser.error(f"No PDFs found in {args.pdf_dir}")
    pdfs = [p for p in pdfs if re.search(r"VOL\s*I[- ]?C", p.stem, re.I)]
    if not pdfs:
        parser.error("No DPWH Volume I-C PDF found")

    all_records: list[dict] = []
    source_stats = []
    with tempfile.TemporaryDirectory(prefix="hb10858-") as temp_name:
        temp = Path(temp_name)
        for pdf in pdfs:
            from hgab_native import page_boxes, extract_visible
            page_dir = (args.text_cache or temp) / re.sub(r"[^A-Za-z0-9_-]+", "_", pdf.stem)
            print(f"Extracting text: {pdf.name}", file=sys.stderr)
            boxes = page_boxes(gs, pdf)
            source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
            cache_manifest = page_dir / 'source.json'
            cached_hash = json.loads(cache_manifest.read_text()).get('sha256') if cache_manifest.exists() else None
            if cached_hash != source_hash or len(list(page_dir.glob("page-*.xml"))) != len(boxes):
                if page_dir.exists():
                    for stale in page_dir.glob('page-*.xml'):
                        stale.unlink()
                extract_text(gs, pdf, page_dir)
                cache_manifest.write_text(json.dumps({'sha256':source_hash,'file':pdf.name})+'\n')
            page_files = sorted(page_dir.glob("page-*.xml"))
            if len(page_files) != len(boxes):
                raise RuntimeError(f"Page XML/geometry count differs: {len(page_files)} vs {len(boxes)}")
            rows, audit = extract_visible(pdf, page_files, boxes)
            all_records.extend(rows)
            source_stats.append({
                "file": pdf.name,
                "pages": len(page_files),
                "sourceSHA256": source_hash,
                **audit,
            })

    payload = {
        "status": 200,
        "code": "SUCCESS",
        "data": {"data": all_records},
        "metadata": {
            "source": "House Bill No. 10858, General Appropriations Bill FY 2027",
            "amountUnit": "thousand pesos, matching 2027.json; amountPesos preserves exact bill value",
            "extractionMethod": "Visible native text cropped to PDF CropBox; visual row grouping, full wrapped descriptions, printed hierarchy leaf allocations; no title/amount deduplication or inferred amounts",
            "sourceFiles": source_stats,
            "candidateCount": len(all_records),
            "warning": "Candidate extraction only. Review each source page; omissions and misread rows are possible. Do not use as confirmed insertions until matched to NEP and checked against the bill.",
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_records):,} candidate records: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
