#!/usr/bin/env python3
"""Create the title-classified FY2019 DPWH MPB slice from the technical GAA."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data_sources/gaa_2019_dpwh_technical/lines.json"
OUT = ROOT / "data_sources/mpb-historical-2019.json"
MULTI = re.compile(r"multi[- ]?purpose", re.I)
FACILITY = re.compile(r"building|bldg|facility", re.I)


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    records = []
    for row in source["rows"]:
        code = row["uacs"]
        title = row.get("title", "")
        # Specific PAP codes have twelve significant digits. Shorter UACS rows
        # are program/group controls and overlap the detailed project lines.
        if not code.startswith(("30", "31", "32")) or len(code.rstrip("0")) < 12:
            continue
        if not MULTI.search(title) or not FACILITY.search(title):
            continue
        pdf_page = (row.get("sourcePages") or [None])[0]
        records.append({
            "year": 2019,
            "stage": "GAA",
            "category": "Multi-purpose building",
            "name": title,
            "amountPesos": row.get("amountPesos"),
            "sourceId": code,
            "sourcePage": pdf_page + 1465 if pdf_page else None,
            "pdfPage": pdf_page,
            "source": (f"FY2019 DPWH Technical GAA · UACS {code} · "
                       f"printed p. {pdf_page + 1465 if pdf_page else 'not resolved'} · PDF p. {pdf_page or 'not resolved'}"),
            "sourceUrl": source["sourceUrl"] + (f"#page={pdf_page}" if pdf_page else ""),
        })
    payload = {
        "title": "FY2019 DPWH GAA MPB title candidates",
        "source": source["source"],
        "sourceSha256": source["sourceSha256"],
        "classification": "Title contains multi-purpose (including spelling variants) and building/bldg/facility; restricted to 12-significant-digit UACS PAP codes to exclude program/group controls.",
        "caveat": "Title-classified appropriation lines; OCR is not used. Confirm the source page before treating a line as a distinct building. Amounts are not expenditures.",
        "records": records,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {len(records):,} FY2019 MPB title candidates; "
          f"{sum(r['amountPesos'] or 0 for r in records):,} pesos with nulls excluded")


if __name__ == "__main__":
    main()
