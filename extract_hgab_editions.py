#!/usr/bin/env python3
"""Extract comparable FY2027 HGAB schedules from the 2nd/3rd reading folders.

This keeps the edition-specific tables together: DPWH projects, DA FMR, NIA's
named-project schedule and separate irrigation-program appendix, HFEP facilities,
and DepEd non-implementing secondary-school allocations.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

from extract_hb_projects import extract_text
from extract_hb_agency_projects import extract_page as extract_fmr_page, page_lines
from extract_hb_nia_projects import extract_page as extract_nia_page, norm
from extract_hb_hfep_projects import extract_page as extract_hfep_page


ROOT = Path(__file__).resolve().parent
IRR_ACTION = re.compile(
    r":\s*(?:construction|concreting|repair|improvement|establishment|"
    r"procurement|canalization|rehabilitation|upgrading|completion|"
    r"development|installation|replacement|restoration)\b", re.I,
)
IRR_MONEY = re.compile(r"^\s*(\d{1,3}(?:[ ,]\s*\d{3})+)\s*$")


def clean_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def irrigation_rows(pdf: Path, printed_page: int, xml: str) -> list[dict]:
    lines = page_lines(xml)
    starts = [line for line in lines if IRR_ACTION.search(line["text"])]
    amounts = []
    for line in lines:
        match = IRR_MONEY.fullmatch(line["text"])
        if match:
            amounts.append({**line, "amount": int(re.sub(r"\D", "", match.group(1)))})
    rows = []
    for index, start in enumerate(starts):
        next_start = min(
            (line["y"] for line in starts
             if abs(line["x0"] - start["x0"]) < 70 and line["y"] > start["y"]),
            default=start["y"] + 36,
        )
        pieces = [start["text"]]
        for line in lines:
            if start["y"] < line["y"] < min(next_start, start["y"] + 32) and abs(line["x0"] - start["x0"]) < 70:
                if not IRR_MONEY.fullmatch(line["text"]) and not re.fullmatch(r"\d+", line["text"]):
                    pieces.append(line["text"])
        title = re.sub(r"\s+", " ", " ".join(dict.fromkeys(pieces))).strip()
        if re.search(r"sub[- ]?program|sub[- ]?total|total new appropriations", title, re.I):
            continue
        choices = [a for a in amounts if 200 <= a["x0"] - start["x0"] <= 560 and -2 <= a["y"] - start["y"] <= 30]
        if not choices:
            continue
        nearest = min(abs(a["y"] - start["y"]) for a in choices)
        amount = max((a for a in choices if abs(a["y"] - start["y"]) == nearest), key=lambda a: a["x0"])
        context = [x["text"] for x in lines if abs(x["y"] - start["y"]) <= 30 and abs(x["x0"] - start["x0"]) <= 560]
        row_id = f"HB10858-NIA-IRR-{printed_page:04d}-{index + 1:03d}"
        rows.append({
            "id": row_id, "code": row_id, "fiscalYear": 2027,
            "edition": "", "agency": "National Irrigation Administration",
            "program": "FY 2027 Irrigation Program", "region": "", "office": "",
            "projectName": title, "pap1": "National Irrigation Administration",
            "pap2": "FY 2027 Irrigation Program", "pap3": "Irrigation project candidate",
            "rowType": "line-item candidate; verify amount and hierarchy",
            "amount": amount["amount"] / 1000, "amountUnit": "thousand pesos",
            "amountPesos": amount["amount"], "sourceVolume": pdf.name,
            "sourcePage": printed_page, "sourceText": f"{title} | {amount['text']}",
            "sourceContext": " | ".join(dict.fromkeys(context)),
            "reviewStatus": "candidate; verify against PDF",
        })
    unique, seen = [], set()
    for row in rows:
        key = (clean_key(row["projectName"]), row["amountPesos"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def deped_school_rows(page_no: int, xml: str, contexts: dict) -> list[dict]:
    """Read the two side-by-side school allocation tables by cell coordinates."""
    lines = page_lines(xml)
    output = []
    for side, x_name, x_offset in (("left", (90, 360), 0), ("right", (740, 1010), 648)):
        def on_side(line: dict) -> bool:
            x = line["x0"]
            return x_name[0] <= x <= x_name[1] or (350 <= x < 650 if side == "left" else 1000 <= x < 1300)
        side_lines = [line for line in lines if on_side(line)]
        ys = sorted({round(line["y"], 1) for line in side_lines})
        pending: list[str] = []
        for y in ys:
            same_y = [line for line in lines if abs(line["y"] - y) <= 1.5]
            labels = [x["text"].strip() for x in same_y if x_name[0] <= x["x0"] <= x_name[1]]
            usable_labels = []
            for raw_label in labels:
                label = re.sub(r"\s+", " ", raw_label).strip()
                if not label or label.isnumeric() or re.search(
                    r"DEPARTMENT OF EDUCATION|NON-IMPLEMENTING UNIT SECONDARY SCHOOLS|"
                    r"GENERAL APPROPRIATIONS BILL|REGION / SDO / SECONDARY SCHOOLS|"
                    r"JUNIOR HIGH SCHOOL|SENIOR HIGH|AMOUNT IN PESOS|^SCHOOL$|^PS$|^MOOE$|^TOTAL$",
                    label, re.I,
                ):
                    continue
                region_match = re.search(
                    r"(National Capital Region(?: \(NCR\))?|Cordillera Administrative Region(?: \(CAR\))?|"
                    r"\bRegion\s+[IVX0-9]+(?:[- ]?[A-Z]+)?(?:\s*[-–].*)?|Negros Island Region|"
                    r"\bMIMAROPA\b|\bBARMM\b|\bNCR\b|\bCAR\b)", label, re.I,
                )
                if region_match:
                    contexts[side]["region"] = region_match.group(1).strip()
                    pending.clear()
                elif re.match(r"^Division of\b", label, re.I):
                    contexts[side]["division"] = label
                    pending.clear()
                elif re.match(r"^Division Office\b", label, re.I):
                    pending.clear()
                else:
                    usable_labels.append(label)
            values: dict[str, int] = {}
            for cell in same_y:
                if not on_side(cell) or x_name[0] <= cell["x0"] <= x_name[1]:
                    continue
                normalized = cell["text"].strip().replace(" ", "")
                if normalized == "-":
                    amount = 0
                elif re.fullmatch(r"\d{1,3}(?:,\d{3})+", normalized):
                    amount = int(normalized.replace(",", ""))
                else:
                    continue
                x = cell["x0"] - x_offset
                field = "jhs_ps" if x < 420 else "jhs_mooe" if x < 485 else "jhs_total" if x < 550 else "shs_mooe"
                values[field] = amount
            if not values:
                pending.extend(usable_labels)
                continue
            pending.extend(usable_labels)
            school = re.sub(r"\s+", " ", " ".join(pending)).strip()
            pending.clear()
            if not school or re.search(r"DEPARTMENT OF EDUCATION|NON-IMPLEMENTING UNIT SECONDARY SCHOOLS", school, re.I) or re.match(r"^(?:Division of|Division Office|National Capital Region|Region\s|Cordillera Administrative Region)", school, re.I):
                continue
            if school in {"REGION / SDO / SECONDARY SCHOOLS", "AMOUNT IN PESOS"}:
                continue
            row = {
                "fiscalYear": 2027, "edition": "", "agency": "Department of Education",
                "program": "Non-Implementing Unit Secondary Schools",
                "region": contexts[side].get("region", ""),
                "division": contexts[side].get("division", ""), "schoolName": school,
                "juniorHighPersonnelServicesPesos": values.get("jhs_ps", 0),
                "juniorHighMooePesos": values.get("jhs_mooe", 0),
                "juniorHighTotalPesos": values.get("jhs_total", 0),
                "seniorHighMooePesos": values.get("shs_mooe", 0),
                "totalPesos": values.get("jhs_total", 0) + values.get("shs_mooe", 0),
                "sourcePage": page_no, "reviewStatus": "candidate; confirm school label and table row",
            }
            output.append(row)
    return output


def unique(rows: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    kept, seen = [], set()
    for row in rows:
        key = tuple(clean_key(row.get(field, "")) if isinstance(row.get(field), str) else row.get(field) for field in key_fields)
        if key not in seen:
            seen.add(key)
            kept.append(row)
    return kept


def extract_edition(pdf: Path, edition: str, gs: str, temp: Path) -> dict:
    page_dir = temp / ("pages-" + edition)
    extract_text(gs, pdf, page_dir)
    pages = sorted(page_dir.glob("page-*.xml"))
    fmr, nia, hfep, irrigation, deped = [], [], [], [], []
    contexts = {"left": {}, "right": {}}
    for file in pages:
        physical = int(file.stem.split("-")[-1])
        xml = file.read_text(encoding="utf-8", errors="replace")
        fmr.extend(extract_fmr_page(pdf, physical, xml))
        if physical in (570, 571, 572):
            nia.extend(extract_nia_page(pdf, physical, xml))
        if 876 <= physical <= 892:
            hfep.extend(extract_hfep_page(pdf, physical, xml))
        # Appendix pages 874–919 are physical PDF pages 896–941 in both editions.
        if 896 <= physical <= 941:
            irrigation.extend(irrigation_rows(pdf, physical - 22, xml))
        if 729 <= physical <= 873:
            deped.extend(deped_school_rows(physical - 18, xml, contexts))
    for rows in (fmr, nia, hfep, irrigation, deped):
        for row in rows:
            row["edition"] = edition
    return {
        "edition": edition, "source": str(pdf),
        "fmr": unique(fmr, ("projectName", "amountPesos")),
        "nia_named": unique(nia, ("projectName", "amountPesos")),
        "nia_irrigation": unique(irrigation, ("projectName", "amountPesos")),
        "hfep": unique(hfep, ("projectName", "amountPesos")),
        "deped": unique(deped, ("region", "division", "schoolName")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition-dir", type=Path, required=True)
    parser.add_argument("--edition", choices=("2nd", "3rd"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ghostscript", default="gs")
    args = parser.parse_args()
    gs = shutil.which(args.ghostscript)
    if not gs:
        parser.error("Ghostscript is required")
    pdfs = [p for p in args.edition_dir.glob("*.pdf") if re.search(r"VOL\s*I[- ]?B", p.stem, re.I)]
    if len(pdfs) != 1:
        parser.error(f"Expected one Volume I-B PDF in {args.edition_dir}; found {len(pdfs)}")
    with tempfile.TemporaryDirectory(prefix=f"hgab-{args.edition}-") as td:
        result = extract_edition(pdfs[0], args.edition, gs, Path(td))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({k: len(v) for k, v in result.items() if isinstance(v, list)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
