#!/usr/bin/env python3
"""Extract candidate named NIA irrigation projects from HB 10858 Volume I-B.

The NIA schedule interleaves PAP subtotals and named projects in two table
layouts. This parser keeps only named project-like rows from the project
schedule pages and pairs each row to the rightmost amount cell in its table.
All results require review against the printed page.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from extract_hb_agency_projects import extract_text, page_lines

ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "HB 10858 FOR 2ND READING"
OUT = ROOT / "hb10858_nia_projects.json"
PROJECT = re.compile(r"\b(?:project\b|reservoir\b|dam\b)", re.I)
MONEY = re.compile(r"^\s*(\d{1,3}(?:,\s*\d{3})+)\s*$")
SUMMARY = re.compile(r"\b(?:sub[- ]?program|sub[- ]?total|total new appropriations|new appropriations|locally[- ]?funded project|foreign[- ]assisted project|regular programs?|total\s*,?\s*project\(s\)|project\(s\))", re.I)


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def extract_page(pdf: Path, page_no: int, xml_text: str) -> list[dict]:
    lines = page_lines(xml_text)
    starts = []
    for index, line in enumerate(lines):
        is_system_title_tail = re.match(r"^Project\s*[,;]", line["text"], re.I) and any(
            abs(prev["x0"] - line["x0"]) < 70 and 0 < line["y"] - prev["y"] <= 16
            and re.search(r"irrigation system.*extension$", prev["text"], re.I) for prev in lines
        )
        if is_system_title_tail:
            continue
        if not PROJECT.search(line["text"]) or SUMMARY.search(line["text"]):
            # A named irrigation system may have its word "Project" on the
            # following printed line (e.g. "System and Extension / Project, Cagayan").
            if not re.search(r"irrigation system.*extension$", line["text"], re.I):
                continue
            following = min((x for x in lines if abs(x["x0"] - line["x0"]) < 70 and 0 < x["y"] - line["y"] <= 16 and not re.fullmatch(r"\d+", x["text"])), key=lambda x: x["y"], default={"text": ""})
            if not re.match(r"^Project\s*[,;]", following.get("text", ""), re.I):
                continue
        # A separate "Irrigation Project (SRIP), Province" line completes the
        # reservoir name immediately above it; keep it as a continuation.
        is_srip_tail = re.match(r"^Irrigation Project\s*\(SRIP\)", line["text"], re.I)
        prior_reservoir = any(
            abs(prev["x0"] - line["x0"]) < 70 and 0 < line["y"] - prev["y"] <= 16
            and re.search(r"reservoir$", prev["text"], re.I)
            for prev in lines
        )
        if is_srip_tail and prior_reservoir:
            continue
        starts.append(line)
    amounts = []
    for line in lines:
        m = MONEY.fullmatch(line["text"])
        if m:
            amounts.append({**line, "amount": int(re.sub(r"\D", "", m.group(1)))})

    records = []
    for i, start in enumerate(starts):
        next_same_column = min(
            (x["y"] for x in starts if abs(x["x0"] - start["x0"]) < 70 and x["y"] > start["y"]),
            default=start["y"] + 40,
        )
        parts = [start["text"]]
        for line in lines:
            if start["y"] < line["y"] < min(next_same_column, start["y"] + 28) and abs(line["x0"] - start["x0"]) < 70:
                if not SUMMARY.search(line["text"]) and not MONEY.fullmatch(line["text"]) and not re.fullmatch(r"\d+", line["text"]):
                    parts.append(line["text"])
        title = re.sub(r"\s+", " ", " ".join(dict.fromkeys(parts))).strip()
        if len(title) > 220 or SUMMARY.search(title):
            continue
        candidates = [
            amount for amount in amounts
            if 200 <= amount["x0"] - start["x0"] <= 550
            and -2 <= amount["y"] - start["y"] <= 27
        ]
        if not candidates:
            continue
        nearest_y = min(abs(x["y"] - start["y"]) for x in candidates)
        tied = [x for x in candidates if abs(x["y"] - start["y"]) == nearest_y]
        amount = max(tied, key=lambda x: x["x0"])
        context = [
            x["text"] for x in lines
            if abs(x["y"] - start["y"]) <= 26 and abs(x["x0"] - start["x0"]) <= 550
        ]
        row_id = f"HB10858-NIA-{page_no:04d}-{i+1:03d}"
        records.append({
            "id": row_id, "code": row_id, "fiscalYear": 2027,
            "agency": "National Irrigation Administration",
            "program": "NIA named irrigation projects",
            "region": "", "office": "", "projectName": title,
            "pap1": "Budgetary Support to Government Corporations",
            "pap2": "National Irrigation Administration", "pap3": "Irrigation project candidate",
            "rowType": "named project candidate; verify hierarchy and scope",
            "amount": amount["amount"] / 1000, "amountUnit": "thousand pesos",
            "amountPesos": amount["amount"],
            "amountField": "rightmost printed amount column; presumed total, verify against PDF",
            "sourceVolume": pdf.name, "sourcePage": page_no,
            "sourceText": f"{title} | {amount['text']}",
            "sourceContext": " | ".join(dict.fromkeys(context)),
            "screeningFlags": [], "reviewNotes": ["check project/PAP level and total amount in the NIA schedule"],
            "reviewStatus": "candidate; verify against PDF",
        })
    return records


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
    with tempfile.TemporaryDirectory(prefix="hb10858-nia-") as temp:
        for pdf in pdfs:
            folder = args.page_dir or Path(temp) / "pages"
            if not args.page_dir:
                print(f"Extracting text: {pdf.name}")
                extract_text(gs, pdf, folder)
            rows = []
            for page in (570, 571, 572):
                file = folder / f"page-{page:05}.xml"
                if file.exists():
                    rows.extend(extract_page(pdf, page, file.read_text(encoding="utf-8", errors="replace")))
            unique, seen = [], set()
            for row in rows:
                key = (norm(row["projectName"]), row["amountPesos"])
                if key not in seen:
                    seen.add(key)
                    unique.append(row)
            all_rows.extend(unique)
            stats.append({"file": pdf.name, "candidateRows": len(unique)})
    payload = {"status": 200, "code": "SUCCESS", "data": {"data": all_rows}, "metadata": {
        "source": "HB 10858 FY 2027, Volume I-B, NIA project schedule",
        "amountUnit": "thousand pesos; amountPesos preserves printed pesos",
        "extractionMethod": "Ghostscript text with table-coordinate amount pairing",
        "sourceFiles": stats, "candidateCount": len(all_rows),
        "printedProjectSubtotalPesos": 10655321000,
        "candidateAmountSumPesos": sum(row["amountPesos"] for row in all_rows),
        "reconciliationGapPesos": 10655321000 - sum(row["amountPesos"] for row in all_rows),
        "warning": "Named project candidates only. The schedule includes PAP and subtotal hierarchy; verify each row and amount against the cited PDF page before reporting totals or additions.",
    }}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_rows):,} NIA project candidates: {args.out}")
    print(f"Candidate sum: ₱{payload['metadata']['candidateAmountSumPesos']:,}; "
          f"printed project subtotal: ₱{payload['metadata']['printedProjectSubtotalPesos']:,}; "
          f"gap: ₱{payload['metadata']['reconciliationGapPesos']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
