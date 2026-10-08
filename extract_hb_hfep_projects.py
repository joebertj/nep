#!/usr/bin/env python3
"""Extract reviewable facility candidates from HB 10858 Volume I-B HFEP.

HFEP has separate infrastructure, medical equipment, motor vehicle, and Total
columns, plus hierarchical program/region/province rows. This preserves only
facility-named rows and uses the printed Total column; all rows remain
candidates requiring source-PDF review.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from extract_hb_agency_projects import extract_text, page_lines

ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "HB 10858 FOR 2ND READING"
OUT = ROOT / "hb10858_hfep_projects.json"
MONEY = re.compile(r"\d{1,3}(?:,\d{3})+")
SUMMARY = re.compile(r"^(?:department of health|health facilities enhancement program|name of projects(?: and facilities)?|infrastructure|medical equipment|motor vehicle|total|primary care facilities|construction of new(?: barangay health stations \(bhs\)| primary care facility)?|completion/equipping of (?:bhs|primary care facilities)|blood facilities|laboratories|dialysis centers|rehabilitation centers|bureau of quarantine|other health care facilities|state universities|current operating expenditures|maintenance and other operating expenses|operations|general administration and support|(?:region\s+[ivx0-9]+|calabarzon|ncr|car|mimaropa|barmm|central visayas|eastern visayas|western visayas|northern mindanao|davao region|zamboanga peninsula|caraga|soccsksargen|bicol region|ilocos region|cagayan valley|central luzon))$", re.I)


def money_cells(xml_text: str) -> list[dict]:
    """Return amounts with their character-level PDF coordinates."""
    def valid_ref(m: re.Match) -> str:
        raw = m.group(1)
        cp = int(raw[1:], 16) if raw.startswith("x") else int(raw)
        return m.group(0) if cp in (9, 10, 13) or 0x20 <= cp <= 0xD7FF or 0xE000 <= cp <= 0xFFFD or 0x10000 <= cp <= 0x10FFFF else ""

    root = ET.fromstring(re.sub(r"&#(x[0-9A-Fa-f]+|[0-9]+);", valid_ref, xml_text))
    out = []
    for line in root.iter("line"):
        chars = list(line.iter("char"))
        text = "".join(c.attrib.get("c", "") for c in chars)
        for match in MONEY.finditer(text):
            boxes = [tuple(map(float, chars[i].attrib["bbox"].split())) for i in range(match.start(), match.end()) if chars[i].attrib.get("bbox")]
            if boxes:
                out.append({"y": sum((b[1]+b[3])/2 for b in boxes)/len(boxes),
                            "x0": min(b[0] for b in boxes), "x1": max(b[2] for b in boxes),
                            "text": match.group(), "amount": int(match.group().replace(",", ""))})
    return out


def extract_page(pdf: Path, page_no: int, xml_text: str) -> list[dict]:
    lines = page_lines(xml_text)
    # The schedule has two page halves. Their column positions shift slightly
    # between scanned sheets, so use the printed headers to locate each field.
    # Some PDF text lines merge a description and its amount. Extract the
    # numeric token from text lines as well as standalone amount cells.
    amounts = money_cells(xml_text)
    column_centers = {"left": {}, "right": {}}
    for header in lines:
        if header["y"] > 160:
            continue
        side = "left" if header["x0"] < 700 else "right"
        label = header["text"].strip().lower()
        key = {"infrastructure": "infrastructure", "medical": "medical",
               "motor vehicle": "motor_vehicle", "total": "total"}.get(label)
        if key and key not in column_centers[side]:
            column_centers[side][key] = (header["x0"] + header["x1"]) / 2

    rows = []
    left_threshold = 148 if any(110 <= x["x0"] <= 115 and re.match(r"^Region\b", x["text"], re.I) for x in lines) else 117
    candidates = sorted(
        ({**x, "text": MONEY.sub("", x["text"]).strip(" ,")}
         for x in lines if (left_threshold <= x["x0"] < 700 or 796 <= x["x0"] < 1200)
         and not re.fullmatch(r"[\d.]+", MONEY.sub("", x["text"]).strip())
         and len(MONEY.sub("", x["text"]).strip()) >= 12
         and not re.match(r"^\s*(?:with|and|of|in|at|for|to)\b", MONEY.sub("", x["text"]).strip(), re.I)
         and not re.match(r"^\s*\d+(?:\.[a-z])?\.", MONEY.sub("", x["text"]).strip(), re.I)
         and not SUMMARY.fullmatch(MONEY.sub("", x["text"]).strip())),
        key=lambda x: (x["x0"], x["y"]),
    )
    for i, line in enumerate(candidates):
        text = line["text"].strip()
        is_left = line["x0"] < 700
        side = "left" if is_left else "right"
        centers = column_centers[side]
        prior_same_column = [x for x in lines if x["x0"] < (700 if is_left else 1200)
                             and abs(x["x0"] - line["x0"]) <= 25
                             and 0 < line["y"] - x["y"] <= 12
                             and not MONEY.search(x["text"])]
        prior_fragment_context = any(
            p["text"].rstrip().endswith(("-", ","))
            or p["text"].count("(") > p["text"].count(")")
            or (p["x1"] - p["x0"] >= 175 and re.match(
                r"^(?:station\b|valenzuela\b|district\s+hospital\b|hospital\))", text, re.I))
            for p in prior_same_column
        )
        if prior_fragment_context:
            continue
        # Join a wrapped facility title when punctuation/prepositions show a
        # continuation, or when the prior line reaches the printed column edge.
        # The latter catches wraps such as "... Memorial / District Hospital".
        parts = [text]
        row_ys = [line["y"]]
        previous = text
        next_lines = sorted((x for x in lines if x["x0"] < (700 if is_left else 1200)
                             and abs(x["x0"] - line["x0"]) <= 25
                             and 0 < x["y"] - line["y"] <= 12
                             and not MONEY.search(x["text"])), key=lambda x: x["y"])
        for following in next_lines:
            is_continuation = re.match(r"^\s*(?:with|and|of|in|at|for|to|the|station\b|district\s+hospital\b|hospital\))|^\s*[,)]", following["text"], re.I)
            ends_incomplete = (previous.rstrip().endswith(("-", ","))
                               or re.search(r"\b(?:of|and|with|at|for|to|the|in)$", previous.rstrip(), re.I)
                               or previous.count("(") > previous.count(")"))
            reaches_column_edge = line["x1"] - line["x0"] >= 175
            if ends_incomplete or (is_continuation and reaches_column_edge):
                if SUMMARY.search(following["text"]):
                    break
                parts.append(following["text"].strip())
                row_ys.append(following["y"])
                previous = following["text"].strip()
            else:
                break
        title = re.sub(r"\s+", " ", " ".join(dict.fromkeys(parts)))
        title = MONEY.sub("", title).strip(" ,")
        if len(title) < 12 or len(title) > 240:
            continue
        row_amounts = [a for a in amounts if ((a["x0"] < 700) == is_left)
                       and min(abs(a["y"] - y) for y in row_ys) <= 5.5]
        nearby = row_amounts
        if not nearby:
            continue
        # Choose the rightmost amount cell in this page half (Total), ignoring
        # component columns. If a merged text line hides cell coordinates, its
        # value is still eligible only when it is the sole amount on that row.
        total_center = centers.get("total", 570 if is_left else 1249)
        standalone_total = [a for a in nearby if abs((a["x0"] + a["x1"]) / 2 - total_center) <= 60]
        if standalone_total:
            amount = min(standalone_total, key=lambda a: min(abs(a["y"] - y) for y in row_ys))
        else:
            fallback = [a for a in amounts if min(abs(a["y"] - y) for y in row_ys) <= 2.5]
            if len(fallback) != 1:
                continue
            amount = fallback[0]
        component_keys = ("infrastructure", "medical", "motor_vehicle")
        component_values = []
        for key in component_keys:
            center = centers.get(key)
            cells = [a for a in nearby if center is not None
                     and abs((a["x0"] + a["x1"]) / 2 - center) <= 40]
            component_values.append(min(cells, key=lambda a: abs((a["x0"] + a["x1"]) / 2 - center))["amount"] if cells else None)
        context = [x["text"] for x in lines if abs(x["y"] - line["y"]) <= 16 and abs(x["x0"] - line["x0"]) <= 500]
        row_id = f"HB10858-HFEP-{page_no:04d}-{i+1:03d}"
        rows.append({
            "id": row_id, "code": row_id, "fiscalYear": 2027,
            "agency": "Department of Health", "program": "Health Facilities Enhancement Program",
            "region": "", "office": "", "projectName": title,
            "pap1": "Department of Health", "pap2": "Health Facilities Enhancement Program",
            "pap3": "Facility candidate", "rowType": "named facility candidate; verify hierarchy and scope",
            "amount": amount["amount"] / 1000, "amountUnit": "thousand pesos",
            "amountPesos": amount["amount"], "amountField": "printed Total column",
            "amountInfrastructurePesos": component_values[0],
            "amountMedicalEquipmentPesos": component_values[1],
            "amountMotorVehiclePesos": component_values[2],
            "sourceVolume": pdf.name, "sourcePage": page_no,
            "sourceText": f"{title} | Total: {amount['text']}",
            "sourceContext": " | ".join(dict.fromkeys(context)),
            "screeningFlags": [],
            "reviewNotes": ["verify facility row, hierarchy, and printed Total column against the HFEP schedule"],
            "reviewStatus": "candidate; verify against PDF",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=PDF_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--ghostscript", default="gs")
    parser.add_argument("--page-dir", type=Path, help="Reuse extracted page XML")
    args = parser.parse_args()
    gs = shutil.which(args.ghostscript)
    if not gs and not args.page_dir:
        parser.error("Ghostscript is required: brew install ghostscript")
    pdfs = sorted(args.pdf_dir.glob("*VOL*IB*.pdf"))
    if not pdfs:
        parser.error(f"No Volume I-B PDF found in {args.pdf_dir}")
    all_rows, stats = [], []
    with tempfile.TemporaryDirectory(prefix="hb10858-hfep-") as temp:
        for pdf in pdfs:
            folder = args.page_dir or Path(temp) / "pages"
            if not args.page_dir:
                extract_text(gs, pdf, folder)
            rows = []
            # Volume I-B HFEP detail schedule occupies PDF pages 876–892.
            for page in range(876, 893):
                file = folder / f"page-{page:05}.xml"
                if file.exists():
                    rows.extend(extract_page(pdf, page, file.read_text(encoding="utf-8", errors="replace")))
            unique, seen = [], set()
            for row in rows:
                key = (" ".join(row["projectName"].lower().split()), row["amountPesos"])
                if key not in seen:
                    seen.add(key)
                    unique.append(row)
            all_rows.extend(unique)
            stats.append({"file": pdf.name, "candidateRows": len(unique)})
    payload = {"status": 200, "code": "SUCCESS", "data": {"data": all_rows}, "metadata": {
        "source": "HB 10858 FY 2027, Volume I-B, HFEP schedule",
        "amountUnit": "pesos; amountPesos preserves printed pesos",
        "extractionMethod": "Ghostscript text with facility-name screening and printed Total-column pairing",
        "sourceFiles": stats, "candidateCount": len(all_rows),
        "printedGrandTotalPesos": 10021659000,
        "candidateAmountSumPesos": sum(row["amountPesos"] for row in all_rows),
        "warning": "Facility candidates only. The HFEP schedule has hierarchical program, regional, and provincial summaries and separate component columns. Verify each row and Total amount against the cited PDF page before reporting totals or additions.",
    }}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_rows):,} HFEP facility candidates: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
