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
    return SequenceMatcher(None, normalize(left), normalize(right), autojunk=False).ratio()


def closest_counterpart(variants, pool):
    """Rank NEP lines against title and bill-text variants, not title alone."""
    best = (None, 0.0, "")
    for left in variants:
        tokens = set(left.split())
        ranked = []
        for row in pool:
            right = normalize(row.get("projectName"))
            other = set(right.split())
            overlap = len(tokens & other) / max(1, len(tokens | other))
            ranked.append((overlap, row, right))
        finalists = sorted(ranked, key=lambda item: item[0], reverse=True)[:12]
        if not finalists:
            continue
        score, match, basis = max(
            ((title_similarity(left, item[2]), item[1], left) for item in finalists),
            key=lambda item: item[0],
        )
        if score > best[1]:
            best = (match, score, basis)
    return best


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
        "closest_nep_amount_pesos", "match_basis", "fiscalYear", "region", "office", "pap3",
        "projectName", "amountPesos", "sourceVolume", "sourcePage", "sourceText", "reviewStatus",
    ]
    counts = Counter()
    with args.out.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in sorted(hb, key=lambda item: int(item.get("amountPesos") or 0), reverse=True):
            # Keep the actual extracted project title as the primary matching
            # unit. sourceText can span adjacent printed rows, so it is kept
            # as evidence but never used to make a project-level match.
            variants = [normalize(row.get("projectName"))]
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
                basis = "schedule or subtotal heuristic"
            elif exact_matches:
                status = "Exact normalized title found in NEP"
                closest = max(exact_matches, key=lambda x: title_similarity(row.get("projectName"), x.get("projectName")))
                score = 1.0
                basis = "exact normalized project title"
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
                closest, score, basis = closest_counterpart(variants, pool)
                status = "Plausible NEP title counterpart; review scope" if score >= 0.83 else "No plausible NEP title counterpart; review candidate"
            counts[status] += 1
            writer.writerow({
                "comparison": status,
                "closest_nep_title": closest.get("projectName", "") if closest else "",
                "title_similarity_pct": round(score * 100),
                "closest_nep_office": closest.get("office", "") if closest else "",
                "closest_nep_amount_pesos": round(float(closest.get("amount") or 0) * 1000) if closest else "",
                "match_basis": basis,
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
        "comparisonMethod": "Exact normalized project titles are matched first. Other project titles are compared within the same office (or region when office is unavailable); only a character-similarity score of at least 83% is treated as a plausible counterpart. Extracted sourceText is retained for review but is not used to match projects because it can include adjacent printed rows. The shortlist remains a screening result, not a confirmed addition count.",
        "counts": dict(counts),
        "warning": "This text-only screen does not establish a confirmed addition count. Similarity scores cannot resolve project location, chainage, direction, tranche, scope, or extraction errors. Verify each shortlisted item against the NEP project scope and cited HGAB page.",
        "csv": str(args.out),
    }
    summary_path = args.out.with_name("hb_nep_comparison_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
