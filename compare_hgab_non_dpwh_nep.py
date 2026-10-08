#!/usr/bin/env python3
"""Screen FY2027 HGAB FMR, NIA, and HFEP line items against the full NEP."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from chainage import compare_chainage, compare_tranche, has_directional_conflict

ROOT = Path(__file__).resolve().parent


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize(left), normalize(right)).ratio()


def project_identity(value: str) -> str:
    """Keep the site/project name while dropping common project-type terms."""
    name = normalize(str(value or "").split(",", 1)[0])
    generic = {
        "construction", "improvement", "completion", "rehabilitation", "repair",
        "project", "irrigation", "system", "multipurpose", "purpose", "river",
        "dam", "pump", "small", "reservoir", "impounding", "extension",
        "stage", "phase", "development", "works", "national", "communal",
    }
    return " ".join(token for token in name.split() if token not in generic)


def best_nia_match(title: str, candidates: list[dict]):
    normalized = normalize(title)
    exact = [row for row in candidates if normalize(row["projectName"]) == normalized]
    if exact:
        return max(exact, key=lambda row: int(row["amountPesos"] or 0)), 1.0, True
    identity = project_identity(title)
    title_tokens = set(identity.split())
    finalists = []
    for row in candidates:
        other = project_identity(row["projectName"])
        if not title_tokens or not other:
            continue
        other_tokens = set(other.split())
        overlap = len(title_tokens & other_tokens) / max(1, len(title_tokens | other_tokens))
        if overlap >= 0.30:
            finalists.append((overlap, row, other))
    finalists.sort(key=lambda item: item[0], reverse=True)
    finalists = finalists[:20]
    if not finalists:
        return None, 0.0, False
    overlap, row, other = max(finalists, key=lambda item: SequenceMatcher(None, identity, item[2]).ratio())
    core_score = SequenceMatcher(None, identity, other).ratio()
    if core_score < 0.68:
        return None, 0.0, False
    return row, core_score, False


def run_query(cli: str, parquet: Path, output: Path) -> None:
    p = str(parquet.resolve()).replace("'", "''")
    o = str(output.resolve()).replace("'", "''")
    sql = f"""COPY (
      SELECT sourceRow, UACS_DPT_DSC AS department, UACS_AGY_DSC AS agency,
        PREXC_FPAP_ID AS prexcId, UACS_REG_DSC AS region,
        UACS_OPER_DSC AS office, DSC AS projectName,
        UACS_EXP_DSC AS expenditure, UACS_OBJ_DSC AS object,
        amount, amountPesos
      FROM read_parquet('{p}')
      WHERE PREXC_LEVEL=7 AND amount IS NOT NULL AND amount>0
        AND (UACS_AGY_DSC='National Irrigation Administration'
          OR (UACS_DPT_DSC='Department of Agriculture (DA)'
              AND regexp_matches(DSC, '(?i)farm-to-market road|farm-to-market bridge|\\bFMR\\b'))
          OR (UACS_DPT_DSC='Department of Health (DOH)'
              AND DSC ILIKE '%Health Facilities Enhancement Program%'))
      ORDER BY UACS_AGY_DSC, UACS_REG_DSC, DSC
    ) TO '{o}' (HEADER, DELIMITER ',')"""
    result = subprocess.run([cli, "-c", sql], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())


def load_json_records(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("data", {}).get("data", [])


def clean_nia_title(value: str) -> bool:
    title = normalize(value)
    if not re.search(r"\b(project|irrigation|dam|reservoir|impounding|river basin)\b", title):
        return False
    generic = (
        "operating subsidy", "quick response fund", "repair of pump irrigation systems",
        "repair of national irrigation systems", "repair of communal irrigation systems",
        "restoration of national irrigation systems", "restoration of communal irrigation systems",
        "operation and maintenance", "irrigation management transfer", "comprehensive agrarian",
        "feasibility study", "payment for right of way", "pre construction activities",
        "heavy equipment procurement", "climate change adaptation", "extension expansion",
        "improvement of service roads", "small irrigation project sip nationwide",
        "establishment of pump irrigation project epip",
    )
    return not any(title.startswith(prefix) for prefix in generic)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nep", type=Path, default=ROOT / "nep_fy2027_all.parquet")
    parser.add_argument("--fmr-hb", type=Path, default=ROOT / "hb10858_agency_projects.json")
    parser.add_argument("--nia-hb", type=Path, default=ROOT / "hb10858_nia_projects.json")
    parser.add_argument("--hfep-hb", type=Path, default=ROOT / "hb10858_hfep_projects.json")
    parser.add_argument("--out", type=Path, default=ROOT / "analysis_output" / "hgab_non_dpwh_insertion_candidates.csv")
    parser.add_argument("--duckdb", default="duckdb")
    args = parser.parse_args()
    cli = shutil.which(args.duckdb)
    if not cli:
        parser.error("DuckDB CLI required")
    for path in (args.nep, args.fmr_hb, args.nia_hb, args.hfep_hb):
        if not path.is_file():
            parser.error(f"Input not found: {path}")

    with tempfile.TemporaryDirectory(prefix="nep-hgab-match-") as tmp:
        basis_path = Path(tmp) / "nep_basis.csv"
        run_query(cli, args.nep, basis_path)
        with basis_path.open(encoding="utf-8", newline="") as stream:
            basis = list(csv.DictReader(stream))

    nia_nep = []
    fmr_envelope: dict[str, float] = defaultdict(float)
    hfep_envelope = 0.0
    for row in basis:
        row["amountPesos"] = int(float(row.get("amountPesos") or 0))
        row["amount"] = float(row.get("amount") or 0)
        title = row.get("projectName", "")
        if row.get("agency") == "National Irrigation Administration" and clean_nia_title(title):
            nia_nep.append(row)
        if row.get("department") == "Department of Agriculture (DA)" and re.search(
            r"(?i)repair/rehabilitation and construction of farm-to-market roads in designated key production areas", title
        ) and row.get("expenditure") == "Capital Outlays":
            fmr_envelope[row.get("region") or "Unspecified"] += row["amountPesos"]
        if row.get("department") == "Department of Health (DOH)" and \
           "health facilities enhancement program" in normalize(title) and row.get("expenditure") == "Capital Outlays":
            hfep_envelope += row["amountPesos"]

    fmr_hb = load_json_records(args.fmr_hb)
    nia_hb = load_json_records(args.nia_hb)
    hfep_hb = load_json_records(args.hfep_hb)
    rows: list[dict] = []
    nia_counts: Counter[str] = Counter()
    nia_amounts: Counter[str] = Counter()

    for hb in nia_hb:
        hb_name = str(hb.get("projectName", ""))
        match, score, exact = best_nia_match(hb_name, nia_nep)
        direction_conflict = bool(match and has_directional_conflict(hb_name, match["projectName"]))
        tranche = compare_tranche(hb_name, match["projectName"] if match else "")
        chainage = compare_chainage(hb_name, match["projectName"] if match else "")
        if exact:
            status = "Named in NEP; compare amount and scope"
        elif match and direction_conflict:
            status = "Potential insertion; closest NEP title has directional conflict"
        elif match and score >= 0.72 and tranche["tranche_conflict"]:
            status = "Review as possible insertion; tranche differs (50/50 signal)"
        elif match and score >= 0.72:
            status = "Possible NEP counterpart; verify scope and location"
        else:
            status = "Potential insertion; no close named NEP counterpart"
        nia_counts[status] += 1
        if status.startswith("Potential insertion"):
            nia_amounts[status] += int(hb.get("amountPesos") or 0)
        rows.append({
            "family": "NIA irrigation", "comparison": status,
            "hb_project": hb_name, "hb_amount_pesos": int(hb.get("amountPesos") or 0),
            "nep_project": match.get("projectName", "") if match else "",
            "nep_amount_pesos": match.get("amountPesos", "") if match else "",
            "nep_region": match.get("region", "") if match else "",
            "nep_office": match.get("office", "") if match else "",
            "nep_prexc_id": match.get("prexcId", "") if match else "",
            "similarity_pct": round(score * 100),
            "direction_conflict": direction_conflict,
            "tranche_status": tranche["tranche_status"],
            "tranche_detail": tranche["tranche_detail"],
            "chainage_status": chainage["chainage_status"],
            "chainage_overlap": chainage["chainage_overlap"],
            "source_page": hb.get("sourcePage", ""),
            "source_text": hb.get("sourceText", ""),
            "source_context": hb.get("sourceContext", ""),
        })

    # FMR and HFEP are line-itemized in the bill but represented by broader
    # NEP schedule entries. Keep these in separate buckets so their full HB
    # project totals are not misreported as new money on top of the NEP budget.
    for family, records, label in (
        ("FMR", fmr_hb, "NEP funds a regional FMR program envelope; this site-specific HGAB line is not individually named in NEP"),
        ("HFEP", hfep_hb, "NEP funds a shared HFEP program envelope; this facility-specific HGAB line is not individually named in NEP"),
    ):
        for hb in records:
            rows.append({
                "family": family, "comparison": label,
                "hb_project": hb.get("projectName", ""),
                "hb_amount_pesos": int(hb.get("amountPesos") or 0),
                "nep_project": "Regional FMR allocation" if family == "FMR" else "Health Facilities Enhancement Program",
                "nep_amount_pesos": "", "nep_region": "", "nep_office": "",
                "nep_prexc_id": "", "similarity_pct": "",
                "direction_conflict": "", "tranche_status": "", "tranche_detail": "",
                "chainage_status": "", "chainage_overlap": "",
                "source_page": hb.get("sourcePage", ""),
                "source_text": hb.get("sourceText", ""),
                "source_context": hb.get("sourceContext", ""),
            })

    fields = [
        "family", "comparison", "hb_project", "hb_amount_pesos", "nep_project",
        "nep_amount_pesos", "nep_region", "nep_office", "nep_prexc_id", "similarity_pct",
        "direction_conflict", "tranche_status", "tranche_detail", "chainage_status",
        "chainage_overlap", "source_page", "source_text", "source_context",
    ]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    fmr_total = sum(int(row.get("amountPesos") or 0) for row in fmr_hb)
    nia_total = sum(int(row.get("amountPesos") or 0) for row in nia_hb)
    hfep_total = sum(int(row.get("amountPesos") or 0) for row in hfep_hb)
    summary = {
        "source": {
            "nep": args.nep.name,
            "hgab": [args.fmr_hb.name, args.nia_hb.name, args.hfep_hb.name],
            "stage": "FY2027 NEP compared with HB 10858 HGAB schedules",
        },
        "NIA": {
            "hgabCandidateCount": len(nia_hb), "hgabCandidateAmountPesos": nia_total,
            "nepNamedProjectCandidateCount": len(nia_nep),
            "comparisonCounts": dict(nia_counts),
            "potentialInsertionAmountPesosByStatus": dict(nia_amounts),
            "method": "Exact normalized title first, then token-overlap shortlist and character similarity. Direction conflicts remain distinct; tranche differences are a 50/50 review signal.",
        },
        "FMR": {
            "hgabCandidateCount": len(fmr_hb), "hgabCandidateAmountPesos": fmr_total,
            "nepRegionalCapitalEnvelopePesos": int(sum(fmr_envelope.values())),
            "nepRegionalCapitalEnvelopeByRegionPesos": {k: int(v) for k, v in sorted(fmr_envelope.items())},
            "interpretation": "NEP uses regional FMR capital envelopes; HGAB names local roads. These are newly itemized lines, not automatically new spending on top of the envelope.",
        },
        "HFEP": {
            "hgabCandidateCount": len(hfep_hb), "hgabCandidateAmountPesos": hfep_total,
            "nepCapitalOutlayEnvelopePesos": int(hfep_envelope),
            "interpretation": "NEP has a shared HFEP capital-outlay envelope; HGAB names facilities. These line items may detail the shared envelope and are not automatically additional to it.",
        },
        "caution": "HB schedule extracts are candidates from layout-specific PDF parsers. Unnamed NEP envelopes cannot establish that a facility/road was absent from planning or that HGAB raised the budget; verify each source schedule and classify at the same program level.",
        "csv": str(args.out),
    }
    summary_path = args.out.with_name("hgab_non_dpwh_insertion_summary.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
