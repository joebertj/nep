#!/usr/bin/env python3
"""Create a review list of HB project candidates absent by exact title from NEP."""

import argparse
import csv
import json
import re
import unicodedata
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def title_similarity(left, right):
    """Character similarity after normalization; used only to suggest a review counterpart."""
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def closest_counterpart(title, pool):
    """Narrow with cheap token overlap before calculating character similarity."""
    left = normalize(title)
    tokens = set(left.split())
    ranked = []
    for row in pool:
        right = normalize(row.get("projectName"))
        other = set(right.split())
        overlap = len(tokens & other) / max(1, len(tokens | other))
        ranked.append((overlap, row, right))
    finalists = sorted(ranked, key=lambda item: item[0], reverse=True)[:12]
    if not finalists:
        return None, 0.0
    score, row, _ = max(finalists, key=lambda item: SequenceMatcher(None, left, item[2]).ratio())
    return row, title_similarity(left, row.get("projectName"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nep", type=Path, default=ROOT / "2027.json")
    parser.add_argument("--hb", type=Path, default=ROOT / "hb10858_projects.json")
    parser.add_argument("--out", type=Path, default=ROOT / "analysis_output" / "hb_nep_comparison.csv")
    args = parser.parse_args()

    nep = json.loads(args.nep.read_text(encoding="utf-8"))["data"]["data"]
    hb_payload = json.loads(args.hb.read_text(encoding="utf-8"))
    hb = hb_payload["data"]["data"]
    nep_by_name = defaultdict(list)
    nep_by_office = defaultdict(list)
    nep_by_region = defaultdict(list)
    for row in nep:
        name = normalize(row.get("projectName"))
        nep_by_name[name].append(row)
        nep_by_office[normalize(row.get("office"))].append(row)
        nep_by_region[normalize(row.get("region"))].append(row)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "comparison", "closest_nep_title", "title_similarity_pct", "closest_nep_office",
        "closest_nep_amount_pesos", "fiscalYear", "region", "office", "pap3",
        "projectName", "amountPesos", "sourceVolume", "sourcePage", "sourceText", "reviewStatus",
    ]
    counts = Counter()
    with args.out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(hb, key=lambda item: int(item.get("amountPesos") or 0), reverse=True):
            exact_matches = nep_by_name.get(normalize(row.get("projectName")), [])
            title = normalize(row.get("projectName"))
            # These are extracted schedule headings/totals that passed the
            # heuristic project detector, not individual line items.
            extraction_issue = (
                "foreign assisted projects" in title
                or title.startswith("construction rehabilitation of flood mitigation facilities within major river basins and")
                or int(row.get("amountPesos") or 0) >= 5_000_000_000
            )
            if extraction_issue:
                status = "Likely schedule heading/total; exclude from insertion count"
                closest, score = None, 0.0
            elif exact_matches:
                status = "Exact normalized title found in NEP"
                closest = max(exact_matches, key=lambda x: title_similarity(row.get("projectName"), x.get("projectName")))
                score = 1.0
            else:
                # Keep likely comparisons local to the implementing office. For
                # candidates with no office, narrow by region where possible.
                office = normalize(row.get("office"))
                region = normalize(row.get("region"))
                pool = nep_by_office.get(office, []) if office else []
                if not pool and region:
                    pool = nep_by_region.get(region, [])
                if not pool:
                    pool = nep
                closest, score = closest_counterpart(row.get("projectName"), pool)
                status = "Possible title counterpart; review scope" if score >= 0.72 else "No close title counterpart; review candidate"
            counts[status] += 1
            writer.writerow({
                "comparison": status,
                "closest_nep_title": closest.get("projectName", "") if closest else "",
                "title_similarity_pct": round(score * 100),
                "closest_nep_office": closest.get("office", "") if closest else "",
                "closest_nep_amount_pesos": round(float(closest.get("amount") or 0) * 1000) if closest else "",
                "fiscalYear": row.get("fiscalYear", ""),
                "region": row.get("region", ""),
                "office": row.get("office", ""),
                "pap3": row.get("pap3", ""),
                "projectName": row.get("projectName", ""),
                "amountPesos": row.get("amountPesos", ""),
                "sourceVolume": row.get("sourceVolume", ""),
                "sourcePage": row.get("sourcePage", ""),
                "sourceText": row.get("sourceText", ""),
                "reviewStatus": row.get("reviewStatus", ""),
            })

    summary = {
        "billSource": hb_payload.get("metadata", {}).get("sourceFiles", []),
        "nepRecords": len(nep),
        "hbCandidateRecords": len(hb),
        "comparisonMethod": "Exact normalized title exclusion; for unmatched titles, a closest counterpart is suggested within the same office (or region when office is unavailable), using token overlap to narrow candidates and character similarity to rank them. Similarity is only a review lead; location, chainage, direction, tranche, scope, and extraction accuracy are not resolved automatically.",
        "counts": dict(counts),
        "warning": "Rows without an exact title match are potential insertions for review, not confirmed additions. Likely schedule headings/totals are excluded. Fuzzy counterparts do not establish overlap. Different naming, grouping, chainage, and extraction errors can all affect this screen.",
        "csv": str(args.out),
    }
    summary_path = args.out.with_name("hb_nep_comparison_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
