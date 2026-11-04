#!/usr/bin/env python3
"""Extract UACS-coded FY2019 DPWH technical GAA lines from DBM's text PDF.

Summary/control lines and named-project candidates remain separate fields;
the PDF contains repeated summary tables, so rows must not all be summed.
"""

import collections
import hashlib
import json
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
PDF = ROOT / "research_downloads/philgeps_dime_2019gaa/fy2019-gaa-dpwh-technical.pdf"
OUT = ROOT / "data_sources/gaa_2019_dpwh_technical"
JSON = OUT / "lines.json"
CODE = re.compile(r"^\d{15}$")
AMOUNT = re.compile(r"^(?:\d{1,3}(?:,\d{3})+|\d+)$")
PROJECT_WORDS = re.compile(
    r"\b(?:construction|rehabilitation|rehab|concreting|improvement|widening|"
    r"repair|completion|reconstruction|replacement|installation|opening|"
    r"upgrading|slope protection|flood control|bridge|road|building|"
    r"multipurpose|multi-purpose|evacuation center|river control)\b",
    re.IGNORECASE,
)


def extract():
    doc = pymupdf.open(PDF)
    occurrences = collections.defaultdict(list)
    for page_index, page in enumerate(doc):
        grouped = collections.defaultdict(list)
        for word in page.get_text("words", sort=True):
            grouped[(word[5], word[6])].append(word)
        lines = sorted(
            ((min(w[1] for w in words), words) for words in grouped.values()),
            key=lambda item: item[0],
        )
        current = None
        for _, words in lines:
            code_word = next((w for w in words if CODE.fullmatch(w[4])), None)
            if code_word:
                if current:
                    occurrences[current["uacs"]].append(current)
                current = {"uacs": code_word[4], "text_parts": [], "amount": None,
                           "pdf_page": page_index + 1}
            if not current:
                continue
            current["text_parts"].extend(
                w[4] for w in words
                if 125 <= w[0] < 430 and not CODE.fullmatch(w[4])
            )
            amount_words = [
                w for w in words
                if w[0] >= 570 and AMOUNT.fullmatch(w[4].replace(",", ""))
            ]
            if amount_words and current["amount"] is None:
                current["amount"] = int(amount_words[-1][4].replace(",", ""))
                occurrences[current["uacs"]].append(current)
                current = None
        if current:
            occurrences[current["uacs"]].append(current)

    rows = []
    for uacs, copies in occurrences.items():
        amount_counts = collections.Counter(
            row["amount"] for row in copies if row["amount"] is not None
        )
        preferred = max(copies, key=lambda row: len(" ".join(row["text_parts"])))
        title = " ".join(preferred["text_parts"]).strip()
        rows.append({
            "uacs": uacs,
            "title": title,
            "amountPesos": amount_counts.most_common(1)[0][0] if amount_counts else None,
            "amountCandidatesPesos": sorted(amount_counts),
            "occurrences": len(copies),
            "sourcePages": sorted({row["pdf_page"] for row in copies}),
            "rowType": "project_title_candidate" if uacs.startswith(("30", "31", "32")) and PROJECT_WORDS.search(title) else "program_or_control_line",
        })

    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "title": "FY2019 DPWH Technical GAA",
        "fiscalYear": 2019,
        "source": "DBM Technical GAA FY2019, DPWH, Office of the Secretary",
        "sourceUrl": "https://www.dbm.gov.ph/wp-content/uploads/GAA/GAA2019/TechGAA2019/DPWH/A.pdf",
        "sourceSha256": digest,
        "sourcePdfPages": len(doc),
        "appropriationTotalPesos": 454016273000,
        "rowGrain": "Unique UACS-coded appropriation lines; repeated appearances of the same code are reconciled to the most frequent amount",
        "amountMethod": "Extracted from the rightmost total column using PDF text positions; summary/control rows are retained and must not be added to detailed rows",
        "projectCandidateRule": "Capital-program UACS lines with infrastructure/project terms in the extracted title; candidate classification only",
        "rows": sorted(rows, key=lambda row: row["uacs"]),
    }
    JSON.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"PDF pages: {len(doc):,}; unique UACS rows: {len(rows):,}; output: {JSON}")
    print(f"SHA-256: {digest}")
    candidates = [r for r in rows if r["rowType"] == "project_title_candidate"]
    print(f"Project-title candidates: {len(candidates):,}; their amounts are not a non-overlapping total")
    for prefix in ("20", "30", "31", "32"):
        subset = [r for r in rows if r["uacs"].startswith(prefix)]
        print(f"{prefix}: rows={len(subset):,}, "
              f"title candidates={sum(r['rowType'] == 'project_title_candidate' for r in subset):,}")
    print("Rows with multiple observed amounts:", sum(len(r["amountCandidatesPesos"]) > 1 for r in rows))


if __name__ == "__main__":
    extract()
