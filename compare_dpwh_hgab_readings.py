#!/usr/bin/env python3
"""Compare DPWH project candidates between HB 10858 2nd and 3rd readings."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from chainage import compare_chainage, compare_tranche, has_directional_conflict


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(brgy)\b", "barangay", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def load_rows(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("data", {}).get("data", [])


def chain(row: dict) -> str:
    return str(row.get("projectName") or row.get("sourceText") or "")


def office_key(row: dict) -> tuple[str, str]:
    return norm(row.get("region")), norm(row.get("office"))


def value(row: dict | None) -> int:
    return int(float((row or {}).get("amountPesos") or 0))


def comparable(row: dict) -> bool:
    title = norm(row.get("projectName"))
    return not (
        "foreign assisted projects" in title
        or title.startswith("construction rehabilitation of flood mitigation facilities within major river basins and")
        or value(row) >= 5_000_000_000
    )


def match_quality(a: dict, b: dict) -> tuple[float, str, dict, dict]:
    c = compare_chainage(chain(a), chain(b))
    t = compare_tranche(chain(a), chain(b))
    score = SequenceMatcher(None, norm(a.get("projectName")), norm(b.get("projectName"))).ratio()
    if has_directional_conflict(chain(a), chain(b)):
        return 0.0, "direction conflict", c, t
    if c.get("has_current_range") and c.get("has_prior_range") and not c.get("overlaps"):
        return 0.0, "disjoint chainage", c, t
    return score, "", c, t


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--second", type=Path, required=True)
    parser.add_argument("--third", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    second = [r for r in load_rows(args.second) if comparable(r)]
    third = [r for r in load_rows(args.third) if comparable(r)]

    # Exact titles are paired first inside the same office/region. Occurrence
    # lists preserve duplicate budget rows rather than collapsing them.
    exact: dict[tuple, list[int]] = defaultdict(list)
    for index, old in enumerate(second):
        exact[(office_key(old), norm(old.get("projectName")))].append(index)
    used: set[int] = set()
    output: list[dict] = []
    unmatched_third = []
    for new in third:
        title = norm(new.get("projectName"))
        key = (office_key(new), title)
        candidates = [i for i in exact.get(key, []) if i not in used]
        if not candidates:
            # Titles can stay identical while the implementing-office label
            # changes between printings, so try the full normalized title.
            candidates = [i for i, old in enumerate(second) if i not in used and norm(old.get("projectName")) == title]
        if candidates:
            selected = max(candidates, key=lambda i: (match_quality(new, second[i])[0], -abs(value(new) - value(second[i]))))
            used.add(selected)
            old = second[selected]
            score, conflict, c, t = match_quality(new, old)
            same_amount = value(new) == value(old)
            if conflict == "disjoint chainage":
                status = "Same title · disjoint chainage"
            elif not same_amount:
                status = "Retained · amount changed"
            else:
                status = "Retained · same amount"
            output.append({
                "status": status, "score_pct": 100, "second": old, "third": new,
                "amount_delta_pesos": value(new) - value(old),
                "chainage_status": c.get("chainage_status", "not stated"),
                "chainage_overlap": c.get("chainage_overlap", ""),
                "tranche_status": t.get("tranche_status", "not stated"),
                "tranche_detail": t.get("tranche_detail", ""),
            })
        else:
            unmatched_third.append(new)

    # Fuzzy title candidates are restricted to the same region where possible
    # and require chainage compatibility and no direction conflict.
    for new in unmatched_third:
        tokens = {w for w in norm(new.get("projectName")).split() if len(w) > 2 and w not in {"construction", "rehabilitation", "project", "along", "barangay", "bridge", "road", "flood", "control"}}
        ranked = []
        for i, old in enumerate(second):
            if i in used:
                continue
            if new.get("region") and old.get("region") and norm(new.get("region")) != norm(old.get("region")):
                continue
            old_tokens = {w for w in norm(old.get("projectName")).split() if len(w) > 2 and w not in {"construction", "rehabilitation", "project", "along", "barangay", "bridge", "road", "flood", "control"}}
            if tokens and old_tokens and not (tokens & old_tokens):
                continue
            score, conflict, c, t = match_quality(new, old)
            if score >= 0.78:
                ranked.append((score, -abs(value(new) - value(old)), i, old, conflict, c, t))
        if ranked:
            score, _, index, old, conflict, c, t = max(ranked)
            used.add(index)
            output.append({
                "status": "Possible title match · review", "score_pct": round(score * 100),
                "second": old, "third": new, "amount_delta_pesos": value(new) - value(old),
                "chainage_status": c.get("chainage_status", "not stated"),
                "chainage_overlap": c.get("chainage_overlap", ""),
                "tranche_status": t.get("tranche_status", "not stated"),
                "tranche_detail": t.get("tranche_detail", ""),
            })
        else:
            output.append({
                "status": "New in 3rd reading", "score_pct": 0,
                "second": None, "third": new, "amount_delta_pesos": value(new),
                "chainage_status": "not matched", "chainage_overlap": "",
                "tranche_status": "not matched", "tranche_detail": "",
            })
    for index, old in enumerate(second):
        if index not in used:
            output.append({
                "status": "Not found in 3rd reading", "score_pct": 0,
                "second": old, "third": None, "amount_delta_pesos": -value(old),
                "chainage_status": "not matched", "chainage_overlap": "",
                "tranche_status": "not matched", "tranche_detail": "",
            })

    summary = {
        "secondCandidateCount": len(second), "thirdCandidateCount": len(third),
        "secondAllocationPesos": sum(value(r) for r in second),
        "thirdAllocationPesos": sum(value(r) for r in third),
        "statusCounts": {},
        "method": "Exact normalized titles are paired first; fuzzy candidates require at least 78% sequence similarity, exclude opposite directions and disjoint stated chainage, and are for manual review. Totals are extracted schedule allocations, not verified duplicate costs.",
    }
    for row in output:
        summary["statusCounts"][row["status"]] = summary["statusCounts"].get(row["status"], 0) + 1
    payload = {"summary": summary, "rows": output}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
