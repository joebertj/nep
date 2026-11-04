#!/usr/bin/env python3
"""Parse DBM's official FY2015 DPWH GAA CSV into project-level PAP rows.

The source is an account-level CSV. Capital outlay object rows are grouped by
PAP code/title/implementing office and their amounts (reported in thousand
pesos) are summed to a single candidate project allocation.
"""

import collections
import csv
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data_sources/gaa_2015_dpwh_technical/dpwh.csv"
OUT = ROOT / "data_sources/gaa_2015_dpwh_technical/lines.json"
PROJECT_WORDS = re.compile(
    r"multi[\s-]*purpose.{0,40}building|building.{0,40}multi[\s-]*purpose|"
    r"flood|drainage|dike|revetment|riverbank protection|\bbridge\b|\broads?\b",
    re.IGNORECASE,
)


def main():
    grouped = {}
    with SOURCE.open(encoding="cp1252", newline="") as handle:
        for row_number, row in enumerate(csv.reader(handle), 1):
            if len(row) != 16:
                raise ValueError(f"Unexpected CSV width on row {row_number}: {len(row)}")
            # DBM's CSV is an account-detail extract. Class 6 is Capital
            # Outlays; lower classes would duplicate non-project costs.
            if row[11] != "6":
                continue
            amount_thousands = int(row[15] or 0)
            key = (row[4], row[5], row[6], row[7], row[8], row[9], row[10])
            item = grouped.setdefault(key, {
                "papCode": row[4], "title": row[5], "implementingUnitCode": row[6],
                "implementingOffice": row[7], "regionCode": row[8],
                "fundCode": row[9], "fundDescription": row[10],
                "amountThousandsPesos": 0, "sourceRows": 0, "objectAccounts": {},
            })
            item["amountThousandsPesos"] += amount_thousands
            item["sourceRows"] += 1
            object_key = (row[13], row[14])
            item["objectAccounts"][object_key] = item["objectAccounts"].get(object_key, 0) + amount_thousands

    rows = []
    for item in grouped.values():
        item["amountPesos"] = item.pop("amountThousandsPesos") * 1000
        item["categoryCandidate"] = bool(PROJECT_WORDS.search(item["title"]))
        item["objectAccounts"] = [
            {"code": code, "description": description, "amountPesos": amount * 1000}
            for (code, description), amount in sorted(item["objectAccounts"].items())
        ]
        item["source"] = (
            f"FY2015 DPWH GAA · PAP {item['papCode']} · {item['implementingOffice']}"
        )
        rows.append(item)

    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    total_capital_outlay_pesos = sum(row["amountPesos"] for row in rows)
    payload = {
        "title": "FY2015 DPWH GAA account detail and project candidates",
        "fiscalYear": 2015,
        "source": "DBM Budget Documents Archives, GAA FY2015, DPWH.csv",
        "sourceArchiveUrl": "https://www.dbm.gov.ph/wp-content/uploads/GAA/Archived/GAA2015.zip",
        "sourceArchiveMember": "GAA2015/DPWH.csv",
        "sourceCsvSha256": digest,
        "sourceCsvRows": 29091,
        "sourceEncoding": "Windows-1252",
        "rowGrain": "Capital-outlay rows grouped by PAP code, full PAP description, implementing office, region and fund source; multiple object accounts are summed per group",
        "amountMethod": "DBM CSV amounts are in thousand pesos and converted to pesos; only allotment class 6 (Capital Outlays) is included in lines.json",
        "capitalOutlayTotalPesos": total_capital_outlay_pesos,
        "projectCandidateRule": "Description contains a road, bridge, flood/drainage, or multipurpose-building term; this is a title filter, not proof that every row is a distinct physical project",
        "rows": sorted(rows, key=lambda row: (row["papCode"], row["title"], row["implementingOffice"])),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    candidates = [row for row in rows if row["categoryCandidate"]]
    print(f"Source rows: {payload['sourceCsvRows']:,}; capital-outlay PAP groups: {len(rows):,}")
    print(f"Capital outlays: ₱{total_capital_outlay_pesos:,}; title candidates: {len(candidates):,}")
    print(f"Title candidate allocations are overlapping/unclassified and must not be summed as a separate GAA total.")
    print(f"SHA-256: {digest}; output: {OUT}")


if __name__ == "__main__":
    main()
