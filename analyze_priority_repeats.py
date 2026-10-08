#!/usr/bin/env python3
"""Compare FY2027 DPWH NEP project lines with enacted FY2026 and FY2025 GAA.

Focuses on multi-purpose buildings, roads, bridges, and flood-control work.
The output is a review queue; title similarity is not proof of duplicate scope.
Requires the DuckDB CLI for local parquet reads.
"""

import csv
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from chainage import compare_chainage, compare_tranche, has_directional_conflict

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
REPORTS = ROOT / "analysis_output"
OUT = REPORTS / "priority_program_year_on_year_candidates.csv"

CATEGORY_PATTERNS = {
    "Multi-purpose building": re.compile(r"multi[\s-]*purpose.{0,40}building|building.{0,40}multi[\s-]*purpose", re.I),
    "Flood control": re.compile(r"flood|drainage|dike|revetment|riverbank protection", re.I),
    "Bridge": re.compile(r"\bbridge\b", re.I),
    "Road": re.compile(r"\broad\b|\broads\b", re.I),
}
STOP = {
    "THE", "OF", "AND", "TO", "IN", "AT", "FOR", "ALONG", "FROM", "WITH",
    "CONSTRUCTION", "CONSTRUCT", "CONCRETING", "IMPROVEMENT", "REHABILITATION",
    "REPAIR", "COMPLETION", "PROPOSED", "PROJECT", "PROGRAM", "BUILDING",
    "MULTI", "PURPOSE", "ROAD", "ROADS", "BRIDGE", "BRIDGES", "FLOOD",
    "CONTROL", "DRAINAGE", "SYSTEM", "FACILITY", "FACILITIES", "STRUCTURE",
    "STRUCTURES", "BARANGAY", "BRGY", "MUNICIPALITY", "CITY", "PROVINCE",
    "DISTRICT", "STA", "STATION", "PHASE", "PH", "DEVELOPMENT", "WORKS",
}


def query(sql: str) -> list[dict]:
    result = subprocess.run(["duckdb", "-json", "-c", sql], cwd=ODV,
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout or "[]")


def classify(name: str) -> str | None:
    text = str(name or "")
    if CATEGORY_PATTERNS["Multi-purpose building"].search(text):
        return "Multi-purpose building"
    if CATEGORY_PATTERNS["Flood control"].search(text):
        return "Flood control"
    if CATEGORY_PATTERNS["Bridge"].search(text):
        return "Bridge"
    if CATEGORY_PATTERNS["Road"].search(text):
        return "Road"
    return None


def clean_title(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    value = re.sub(r"\b(?:STA\.?|STATION)\s*[0-9+().-]+(?:\s*[-–]\s*(?:STA\.?|STATION)?\s*[0-9+().-]+)?", " ", value, flags=re.I)
    value = re.sub(r"\(?\s*-?\d{1,3}\.\d+\s*[,°]\s*-?\d{1,3}\.\d+\s*°?\s*\)?", " ", value)
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", value.upper()).split())


def informative(value: str) -> str:
    return " ".join(token for token in clean_title(value).split() if token not in STOP)


def rank_matches(targets: list[dict], prior: list[dict], year: int) -> list[dict]:
    indexed = []
    token_index: dict[str, list[int]] = defaultdict(list)
    for i, row in enumerate(prior):
        text = informative(row["name"])
        tokens = set(text.split())
        indexed.append((text, tokens))
        for token in tokens:
            token_index[token].append(i)

    results = []
    for current in targets:
        current_text = informative(current["name"])
        current_tokens = set(current_text.split())
        counts = Counter(
            i for token in current_tokens for i in token_index.get(token, ())
            if not has_directional_conflict(current["name"], prior[i]["name"])
        )
        shortlist = sorted(
            counts,
            key=lambda i: counts[i],
            reverse=True,
        )[:50]
        scored = []
        for i in shortlist:
            old_text, old_tokens = indexed[i]
            old = prior[i]
            chainage = compare_chainage(current["name"], old["name"])
            if current["category"] == "Bridge":
                # Bridge titles alone are not enough: require an explicit
                # positive-length chainage overlap.
                if not chainage["overlaps"]:
                    continue
            elif current["category"] == "Road":
                # Exclude a road match when both ranges are stated but disjoint.
                # Missing or point-only chainage remains visible as unverified.
                if chainage["has_current_range"] and chainage["has_prior_range"] and not chainage["overlaps"]:
                    continue
            else:
                chainage = {
                    "current_chainage": "", "prior_chainage": "",
                    "chainage_overlap": "", "chainage_status": "not applicable",
                }
            union = current_tokens | old_tokens
            jac = len(current_tokens & old_tokens) / len(union) if union else 0
            seq = SequenceMatcher(None, current_text, old_text, autojunk=False).ratio()
            tranche = compare_tranche(current["name"], old["name"])
            score = max(jac, seq * 0.92)
            scored.append((score, old, chainage, tranche))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        for rank, (score, old, chainage, tranche) in enumerate(scored[:3], 1):
            results.append({
                **current,
                "prior_year": year,
                "prior_name": old["name"],
                "prior_amount": old["amount"],
                "prior_source": old["source"],
                "similarity": round(score, 3),
                "rank": rank,
                "amount_difference": current["amount"] - old["amount"],
                **chainage,
                **tranche,
            })
    return results


def normalize_2027() -> list[dict]:
    rows = json.loads((ROOT / "2027.json").read_text(encoding="utf-8"))["data"]["data"]
    result = []
    for row in rows:
        name = row.get("projectName", "")
        category = classify(name)
        if not category:
            continue
        result.append({
            "category": category, "name": name,
            "amount": round(float(row.get("amount") or 0) * 1000),
            "office": row.get("office", ""), "region": row.get("region", ""),
            "source": row.get("code", "FY2027 NEP"),
        })
    return result


def previous_rows() -> tuple[list[dict], list[dict]]:
    path26 = "data/parquet/parsed_dpwh_2026.parquet"
    path25 = "data/parquet/budget_2025.parquet"
    terms = "MULTI.?PURPOSE|ROAD|BRIDGE|FLOOD|DRAINAGE|DIKE|REVETMENT"
    rows26 = query(f"""select _excel_row, col_J as name, amount from read_parquet('{path26}')
        where col_J is not null and trim(col_J) <> ''
        and regexp_matches(upper(col_J), '{terms}')""")
    rows25 = query(f"""select id, description as name, amount, department_desc, agency_desc
        from read_parquet('{path25}') where department_desc ilike '%Public Works%'
        and regexp_matches(upper(coalesce(description,'')), '{terms}')""")

    def convert(rows: list[dict], year: int) -> list[dict]:
        result = []
        for row in rows:
            category = classify(row.get("name", ""))
            if not category:
                continue
            amount = float(row.get("amount") or 0)
            if year == 2025:
                amount *= 1000  # GAA parquet amounts are in thousands of pesos.
            result.append({
                "category": category, "name": row.get("name", ""),
                "amount": round(amount),
                "source": (f"FY2026 DPWH GAA Details Enrolled Copy, row {row.get('_excel_row', '')}"
                           if year == 2026 else f"GAA 2025 row {row.get('id', '')}"),
            })
        return result

    return convert(rows26, 2026), convert(rows25, 2025)


def main() -> None:
    targets = normalize_2027()
    prior26, prior25 = previous_rows()
    matches = []
    for category in CATEGORY_PATTERNS:
        current = [row for row in targets if row["category"] == category]
        old26 = [row for row in prior26 if row["category"] == category]
        old25 = [row for row in prior25 if row["category"] == category]
        found = rank_matches(current, old26, 2026) + rank_matches(current, old25, 2025)
        matches.extend(found)
        for year, prior in ((2026, old26), (2025, old25)):
            best = [r for r in found if r["prior_year"] == year and r["rank"] == 1]
            threshold = [r for r in best if r["similarity"] >= 0.78]
            print(f"{category}: FY2027 NEP {len(current)}; FY{year} GAA source {len(prior)}; "
                  f"top matches >=78%: {len(threshold)}")

    columns = ["category", "name", "amount", "office", "region", "source",
               "prior_year", "prior_name", "prior_amount", "prior_source",
               "similarity", "rank", "amount_difference", "current_chainage", "prior_chainage",
               "chainage_overlap", "chainage_status", "tranche_status", "tranche_detail",
               "tranche_conflict", "has_current_range",
               "has_prior_range", "overlaps"]
    REPORTS.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(matches)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
