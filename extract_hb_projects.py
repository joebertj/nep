#!/usr/bin/env python3
"""Extract reviewable DPWH project candidates from the HB 10858 PDF schedules.

Uses Ghostscript's text device, so no OCR or Python PDF package is required.
The output follows the broad 2027.json shape, with source page and raw text
preserved because bill table extraction needs human validation before matching.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
DEFAULT_PDF_DIR = ROOT / "HB 10858 FOR 2ND READING"
DEFAULT_NEP = ROOT / "2027.json"
DEFAULT_OUT = ROOT / "hb10858_projects.json"

AMOUNT_RE = re.compile(r"(?<![\w.])(?P<amount>\d{1,3}(?:,\s*\d{3})+)(?!\d)\s*$")
OFFICE_RE = re.compile(r"\b(?:District Engineering Office|DEO)\b", re.I)
NON_DISTRICT_OFFICE_RE = re.compile(r"\b(?:Regional Office(?:\s+[IVX]+)?|NCR Regional Office|CAR Regional Office|Central Office)\b", re.I)
REGION_RE = re.compile(r"^(?:National Capital Region|Cordillera Administrative Region|Region\s+[IVX]+|Negros Island Region|MIMAROPA|BARMM|CAR)$", re.I)
PROJECT_RE = re.compile(
    r"\b(?:construction|contruction|rehabilitation|improvement|concreting|widening|paving|"
    r"completion|replacement|repair|upgrading|retrofitting|reconstruction|"
    r"reblocking|maintenance|installation|establishment|development|"
    r"flood control|flood mitigation|drainage|water system|water supply|"
    r"rainwater|rain water|multi[- ]purpose|bridge|road|slope protection|"
    r"river wall|revetment|pumping station|evacuation center)\b", re.I
)
PROJECT_START_RE = re.compile(
    r"^(?:construction|contruction|rehabilitation|improvement|concreting|widening|paving|"
    r"completion|replacement|repair|upgrading|retrofitting|reconstruction|"
    r"reblocking|maintenance|installation|establishment|development|"
    r"flood control|flood mitigation|drainage|water system|water supply|"
    r"rainwater|rain water|multi[- ]purpose|bridge|road|slope protection|"
    r"river wall|revetment|pumping station|evacuation center)\b", re.I
)
SKIP_RE = re.compile(r"^(?:total|sub-total|grand total|for the|amount\b|programs?\b|activities\b)$", re.I)
GENERIC_HEADING_RE = re.compile(
    r"^(?:maintenance and other operating expenses|maintenance, repair and rehabilitation of infrastructure facilities(?: and other related activities)?|"
    r"maintenance services for automated traffic data collection program|"
    r"construction of by-pass and diversion roads|"
    r"construction/ rehabilitation of water supply/ septage and sewerage/ rain water collectors)$", re.I
)
SITE_RE = re.compile(
    r"\b(?:barangay|brgy\.?|sitio|purok|city|municipality|province|river|creek|"
    r"km\s*\d|sta\.?\s*\d|chainage\s*\d|k\d{3,4}\s*\+|"
    r"\d{1,3}\.\d{4,})\b", re.I
)


def extract_text(gs: str, pdf: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    # A %d output pattern is essential: Ghostscript does not add form-feed
    # separators to txtwrite output, so make one text file per physical page.
    command = [gs, "-q", "-dNOPAUSE", "-dBATCH", "-dTextFormat=1", "-sDEVICE=txtwrite", f"-sOutputFile={output}/page-%05d.xml", str(pdf)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or f"Ghostscript exited {result.returncode}"
        raise RuntimeError(f"Could not read {pdf.name}: {message}")


def column_lines(page_xml: str) -> list[tuple[int, str]]:
    """Rebuild visual rows and assign them to the two schedule columns by x position."""
    def keep_xml_reference(match: re.Match) -> str:
        value = match.group(1)
        codepoint = int(value[1:], 16) if value.startswith("x") else int(value)
        valid = codepoint in (9, 10, 13) or 0x20 <= codepoint <= 0xD7FF or 0xE000 <= codepoint <= 0xFFFD or 0x10000 <= codepoint <= 0x10FFFF
        return match.group(0) if valid else ""

    page_xml = re.sub(r"&#(x[0-9A-Fa-f]+|[0-9]+);", keep_xml_reference, page_xml)
    root = ET.fromstring(page_xml)
    raw_lines = []
    header_x = []
    for line in root.iter("line"):
        chars = list(line.iter("char"))
        if not chars:
            continue
        text = "".join(char.attrib.get("c", "") for char in chars).strip()
        if not text:
            continue
        boxes = [tuple(map(float, char.attrib["bbox"].split())) for char in chars]
        x0, x1 = min(b[0] for b in boxes), max(b[2] for b in boxes)
        y = sum((b[1] + b[3]) / 2 for b in boxes) / len(boxes)
        if text.upper() == "PROGRAMS / ACTIVITIES / PROJECTS":
            header_x.append((x0, x1))
        raw_lines.append((y, chars, boxes))

    header_x = sorted(set(header_x))
    boundary = (header_x[0][1] + header_x[1][0]) / 2 if len(header_x) >= 2 else None
    if boundary is None:
        # Fallback for continuation pages with a single repeated header: infer
        # the gap between the two strongest line-start clusters.
        starts = Counter(round(min(b[0] for b in boxes) / 20) * 20 for _y, _chars, boxes in raw_lines)
        peaks = [x for x, n in starts.most_common(2) if n >= 4]
        if len(peaks) == 2 and abs(peaks[0] - peaks[1]) >= 120:
            boundary = (min(peaks) + max(peaks)) / 2

    if boundary is None:
        boundary = float("inf")
    rows: dict[tuple[int, int], list[tuple[float, str]]] = {}
    for y, chars, boxes in raw_lines:
        for col in (0, 1):
            selected = []
            for char, box in zip(chars, boxes):
                center = (box[0] + box[2]) / 2
                if (col == 0 and center < boundary) or (col == 1 and center >= boundary):
                    selected.append((box[0], box[2], char.attrib.get("c", "")))
            if selected:
                segments = []
                current = []
                last_x1 = None
                for x0, x1, value in sorted(selected):
                    if last_x1 is not None and x0 - last_x1 > 20:
                        segments.append(current)
                        current = []
                    current.append((x0, value))
                    last_x1 = x1
                if current:
                    segments.append(current)
                for segment in segments:
                    text = "".join(value for _x, value in segment).strip()
                    if text:
                        amount_column = re.search(r"\s{5,}(\d[\d,\s]*)$", text)
                        if amount_column:
                            split_at = amount_column.start(1)
                            left = segment[:split_at]
                            right = segment[split_at:]
                            rows.setdefault((col, round(y)), []).append((min(x for x, _value in left), "".join(value for _x, value in left).strip()))
                            rows.setdefault((col, round(y)), []).append((min(x for x, _value in right), "".join(value for _x, value in right).strip()))
                        else:
                            rows.setdefault((col, round(y)), []).append((min(x for x, _value in segment), text))
    result = []
    for col in (0, 1):
        for (row_col, _y), pieces in sorted(rows.items(), key=lambda item: (item[0][0], item[0][1])):
            if row_col != col:
                continue
            ordered = sorted(pieces)
            # Keep a right-column amount separate from the description. Without
            # this boundary, a station number at the end of a title can merge
            # with the amount (e.g. "Sta. 17 + 737, 250,000,000").
            amount_piece = ordered[-1][1].strip() if len(ordered) > 1 else ""
            if amount_piece and re.fullmatch(r"\d[\d,\s]*", amount_piece) and "," in amount_piece:
                description = " ".join(text for _x, text in ordered[:-1])
                description = re.sub(r"\s+", " ", description).strip()
                amount_piece = re.sub(r"\s+", "", amount_piece)
                value = f"{description}\t{amount_piece}"
            else:
                value = re.sub(r"\s+", " ", " ".join(text for _x, text in ordered)).strip()
            if value and value.upper() not in {"PROGRAMS / ACTIVITIES / PROJECTS", "AMOUNT (PHP)"}:
                result.append((col, value))
    return result


def amount_tail(text: str) -> tuple[str, int] | None:
    if "\t" in text:
        description, amount_text = text.rsplit("\t", 1)
        if re.fullmatch(r"\d[\d,\s]*", amount_text.strip()) and "," in amount_text:
            digits = re.sub(r"[ ,\s]", "", amount_text)
            return description.strip(), int(digits)
    match = AMOUNT_RE.search(text)
    if not match:
        return None
    return text[:match.start()].strip(" .\t"), int(re.sub(r"[,\s]", "", match.group("amount")))


def region_label(text: str) -> str | None:
    if re.match(r"^Bangsamoro Autonomous Region in Muslim Mindanao\b", text, re.I):
        return "BARMM"
    match = REGION_RE.search(text)
    if not match:
        return None
    value = match.group(0).strip()
    return "CAR" if value.upper() == "CAR" else value


def extract_candidates(pdf: Path, pages: list[str]) -> tuple[list[dict], int, int]:
    candidates: list[dict] = []
    duplicate_pages_skipped = 0
    duplicate_rows_skipped = 0
    rainwater_seen: set[str] = set()
    category_labels = {
        "rainwater collector system": "Rainwater Collector System",
        "water supply system": "Water Supply System",
        "septage and sewerage": "Septage and Sewerage",
        "construction/ maintenance of flood mitigation structures and drainage systems": "Construction/ Maintenance of Flood Mitigation Structures and Drainage Systems",
        "construction/ rehabilitation of flood mitigation facilities within major river basins and principal rivers": "Construction/ Rehabilitation of Flood Mitigation Facilities within Major River Basins and Principal Rivers",
        "bip - multi-purpose buildings/ facilities to support social services": "BIP - Multi-Purpose Buildings/ Facilities to support Social Services",
        "bip - access roads and/or bridges from the national roads leading to major/ strategic public buildings/ facilities": "BIP - Access Roads and/or Bridges from the National Roads leading to Major/ Strategic Public Buildings/ Facilities",
    }
    # Each physical PDF sheet contains two consecutive printed pages. Process
    # left then right and carry the budget hierarchy forward in that order.
    context = {"office": "", "region": "", "category": "", "pending": [], "pending_office": "", "last_candidate": None}
    contexts = {0: context, 1: context}

    def add_rainwater_record(office: str, region: str, amount_pesos: int, page_no: int, source_text: str) -> None:
        if not office or amount_pesos not in {4_200_000, 9_000_000, 38_400_000}:
            return
        office_key = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", office.lower()).encode("ascii", "ignore").decode())
        if office_key in rainwater_seen:
            return
        rainwater_seen.add(office_key)
        record_id = f"HB10858-{pdf.stem[:1]}-{page_no:04d}-{len(candidates)+1:06d}"
        candidates.append({
            "id": record_id,
            "code": record_id,
            "fiscalYear": 2027,
            "region": region,
            "office": office,
            "projectName": f"Rainwater Collector System - {office}",
            "pap1": "",
            "pap2": "",
            "pap3": "Rainwater Collector System",
            "amount": amount_pesos / 1000,
            "documentCount": 1,
            "amountPesos": amount_pesos,
            "sourceVolume": pdf.name,
            "sourcePage": page_no,
            "sourceText": source_text,
            "reviewStatus": "candidate; verify against PDF",
        })

    previous_signature = None
    previous_page_candidates = {}
    for page_no, page in enumerate(pages, start=1):
        lines = column_lines(page)
        signature = tuple(lines)
        if signature == previous_signature:
            duplicate_pages_skipped += 1
            continue
        previous_signature = signature
        page_candidates = {}
        for col, line in lines:
            state = contexts[col]
            parsed = amount_tail(line)
            text = parsed[0] if parsed else line
            amount_pesos = parsed[1] if parsed else None
            cleaned = re.sub(r"^\s*[a-zA-Z0-9]+[.)]\s*", "", text).strip()
            if not cleaned:
                if amount_pesos and state["category"] == "Rainwater Collector System" and state["pending_office"]:
                    add_rainwater_record(state["pending_office"], state["region"], amount_pesos, page_no, line)
                    state["pending_office"] = ""
                continue

            reg = region_label(cleaned)
            if reg:
                state["region"] = reg
                # A new regional heading starts a new allocation branch. Do not
                # let an office from the preceding branch leak into this one.
                state["office"] = ""
                state["pending"].clear()
                state["pending_office"] = ""
                state["last_candidate"] = None
                continue

            office_match = OFFICE_RE.search(cleaned) or NON_DISTRICT_OFFICE_RE.search(cleaned)
            if office_match and not PROJECT_RE.search(cleaned):
                state["office"] = cleaned
                # The Rainwater office allocation schedule spans printed pages
                # 392–399 inside this volume. Rows are plain office/amount lines.
                if 400 <= page_no <= 410:
                    inferred_amount = amount_pesos
                    if inferred_amount not in {4_200_000, 9_000_000, 38_400_000}:
                        inferred_amount = 9_000_000 if NON_DISTRICT_OFFICE_RE.search(cleaned) else 4_200_000
                    add_rainwater_record(cleaned, state["region"], inferred_amount, page_no, line)
                    state["pending_office"] = ""
                else:
                    state["pending_office"] = cleaned
                state["pending"].clear()
                state["last_candidate"] = None
                continue

            category_heading = re.sub(r"\s+", " ", cleaned).strip(" .").lower()
            if category_heading in category_labels:
                for column_state in contexts.values():
                    column_state["category"] = category_labels[category_heading]
                    column_state["last_candidate"] = None
                state["pending"].clear()
                continue
            if category_heading.startswith("construction/ rehabilitation of water supply/"):
                state["category"] = ""
                state["pending"].clear()
                continue
            if (category_heading.startswith("construction/") or category_heading.startswith("bip -")) and not SITE_RE.search(cleaned):
                state["category"] = ""

            if not parsed:
                # The bill often wraps the location onto a following line after
                # the amount. Attach that continuation to the preceding row in
                # this printed column, rather than losing the identifying site.
                previous = state["last_candidate"]
                if (previous is not None and not PROJECT_START_RE.match(cleaned)
                        and SITE_RE.search(cleaned) and len(cleaned) < 180):
                    row = candidates[previous]
                    row["projectName"] = re.sub(r"\s+", " ", f"{row['projectName']} {cleaned}").strip(" .")
                    row["sourceText"] = re.sub(r"\s+", " ", f"{row['sourceText']} {line}").strip()
                    continue
                # Keep wrapped title fragments only while they resemble a project.
                if PROJECT_RE.search(cleaned) and len(cleaned) > 8:
                    state["pending"].append(cleaned)
                    state["pending"] = state["pending"][-4:]
                    if PROJECT_START_RE.match(cleaned):
                        state["last_candidate"] = None
                continue

            if amount_pesos is None or amount_pesos <= 0:
                continue
            title_parts = [*state["pending"], cleaned]
            title = re.sub(r"\s+", " ", " ".join(title_parts)).strip(" .")
            state["pending"].clear()
            if not title or SKIP_RE.match(title) or GENERIC_HEADING_RE.match(title) or not PROJECT_RE.search(title):
                continue
            # A project row should begin with an action word. Rows containing an
            # office name after a project prefix remain valid project descriptions.
            if not PROJECT_START_RE.match(title):
                continue
            # Schedule headings and regional subtotals often look like project
            # names and carry large amounts. A location/chainage is required
            # for a candidate row, so those program-level totals are excluded.
            if not SITE_RE.search(title):
                continue

            record_id = f"HB10858-{pdf.stem[:1]}-{page_no:04d}-{len(candidates)+1:06d}"
            candidate = {
                "id": record_id,
                "code": record_id,
                "fiscalYear": 2027,
                "region": state["region"],
                "office": state["office"],
                "projectName": title,
                "pap1": "",
                "pap2": "",
                "pap3": (
                    "Rainwater Collector System" if re.search(r"rain\s*water|water collector|cistern|catchment", title, re.I)
                    else "Water Supply System" if re.search(r"water supply|water system|watersystem", title, re.I)
                    else state["category"]
                ),
                "amount": amount_pesos / 1000,
                "documentCount": 1,
                "amountPesos": amount_pesos,
                "sourceVolume": pdf.name,
                "sourcePage": page_no,
                "sourceText": line,
                "reviewStatus": "candidate; verify against PDF",
            }
            dedupe_key = (
                candidate["region"], candidate["office"],
                re.sub(r"[^a-z0-9]+", " ", candidate["projectName"].lower()).strip(),
                candidate["amountPesos"], candidate["pap3"],
            )
            if dedupe_key in previous_page_candidates:
                candidate_index = previous_page_candidates[dedupe_key]
                duplicate_rows_skipped += 1
            else:
                candidates.append(candidate)
                candidate_index = len(candidates) - 1
            page_candidates[dedupe_key] = candidate_index
            state["last_candidate"] = candidate_index
        previous_page_candidates = page_candidates
    return candidates, duplicate_pages_skipped, duplicate_rows_skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--ghostscript", default="gs", help="Ghostscript executable (default: gs)")
    parser.add_argument("--include-all", action="store_true", help="Parse every supplied volume, not only Volume I-C")
    args = parser.parse_args()

    gs = shutil.which(args.ghostscript)
    if not gs:
        parser.error("Ghostscript is required. Install it with: brew install ghostscript")
    pdfs = sorted(args.pdf_dir.glob("*.pdf"))
    if not pdfs:
        parser.error(f"No PDFs found in {args.pdf_dir}")
    if not args.include_all:
        pdfs = [p for p in pdfs if re.search(r"VOL\s*I[- ]?C", p.stem, re.I)]
    if not pdfs:
        parser.error("No Volume I-C PDF found; use --include-all to parse other volumes")

    all_records: list[dict] = []
    source_stats = []
    with tempfile.TemporaryDirectory(prefix="hb10858-") as temp_name:
        temp = Path(temp_name)
        for pdf in pdfs:
            page_dir = temp / re.sub(r"[^A-Za-z0-9_-]+", "_", pdf.stem)
            print(f"Extracting text: {pdf.name}", file=sys.stderr)
            extract_text(gs, pdf, page_dir)
            page_files = sorted(page_dir.glob("page-*.xml"))
            pages = [p.read_text(encoding="utf-8", errors="replace") for p in page_files]
            rows, duplicate_pages_skipped, duplicate_rows_skipped = extract_candidates(pdf, pages)
            all_records.extend(rows)
            source_stats.append({
                "file": pdf.name,
                "pages": len(page_files),
                "duplicatePagesSkipped": duplicate_pages_skipped,
                "duplicateRowsSkipped": duplicate_rows_skipped,
                "candidateRows": len(rows),
            })

    payload = {
        "status": 200,
        "code": "SUCCESS",
        "data": {"data": all_records},
        "metadata": {
            "source": "House Bill No. 10858, General Appropriations Bill FY 2027",
            "amountUnit": "thousand pesos, matching 2027.json; amountPesos preserves exact bill value",
            "extractionMethod": "Ghostscript text extraction; heuristic candidate detection, no OCR",
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
