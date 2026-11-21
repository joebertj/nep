#!/usr/bin/env python3
"""Build a compact per-file printed-date index for COI PDFs."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "analysis_output/senate_supporting_documents_hgab_only_scan.json"
OUT = ROOT.parent / "open-data-visualization/static/nep-preview/coi-document-dates.json"


def build() -> dict:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    documents = []
    for document in source.get("documents", []):
        if document.get("documentType") != "Certificate of Implementability":
            continue
        dates = defaultdict(lambda: {"isoDate": "", "pages": set()})
        for date in document.get("printedDates") or []:
            label = str(date.get("printedDate") or "").strip()
            if not label:
                continue
            item = dates[label]
            item["isoDate"] = str(date.get("isoDate") or "")
            if date.get("sourcePage") is not None:
                item["pages"].add(int(date["sourcePage"]))
        documents.append({
            "file": str(document.get("file") or ""),
            "projectCode": str(document.get("projectCode") or ""),
            "matchStatus": str(document.get("matchStatus") or ""),
            "dates": [
                {"printedDate": label, "isoDate": info["isoDate"], "sourcePages": sorted(info["pages"])}
                for label, info in sorted(dates.items(), key=lambda pair: (pair[1]["isoDate"], pair[0]))
            ],
        })
    return {
        "source": "Printed dates parsed from the 34,317-PDF Senate supporting-document reparse.",
        "documentType": "Certificate of Implementability",
        "documents": documents,
    }


if __name__ == "__main__":
    payload = json.dumps(build(), ensure_ascii=False, separators=(",", ":"))
    OUT.write_text(payload, encoding="utf-8")
    result = json.loads(payload)
    print(json.dumps({"output": str(OUT), "coiPdfFiles": len(result["documents"]), "filesWithDates": sum(bool(row["dates"]) for row in result["documents"])}))
