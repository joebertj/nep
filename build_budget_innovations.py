#!/usr/bin/env python3
"""Build the local Budget Innovations report from the FY2027 NEP and local history."""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
OUT = ODV / "static" / "nep-preview"
NEP_2027 = ROOT / "2027.parquet"
DPWH_2026 = ODV / "data" / "parquet" / "dpwh_2026_leaf_nodes.parquet"
HISTORY = ODV / "static" / "data" / "parquet" / "budget_202[0-5].parquet"

CATEGORIES = [
    {
        "id": "mpb-social-services",
        "title": "Multi-purpose buildings for social services",
        "fy2027": "BIP - Multi-Purpose Buildings/ Facilities to support Social Services",
        "fy2026": "SIPAG - Multi-Purpose Buildings/ Facilities to support Social Services",
        "historyTerm": "multi-purpose building",
        "status": "New label; related category existed",
        "interpretation": "The FY2027 NEP places this work under BIP. FY2026 used a SIPAG label for related multi-purpose building projects. The changed label does not establish that every line is new or that scopes match.",
    },
    {
        "id": "flood-mitigation",
        "title": "Flood mitigation and drainage",
        "fy2027": "Construction/ Maintenance of Flood Mitigation Structures and Drainage Systems",
        "fy2026": "Construction/ Maintenance of Flood Mitigation Structures and Drainage Systems",
        "historyTerm": "flood mitigation",
        "status": "Existing FY2026 category",
        "interpretation": "This category name is already present in FY2026 under Flood Management Program. The FY2027 NEP has a much larger parsed set of proposed lines, but schedule hierarchy and record granularity differ; this is not a like-for-like growth estimate.",
    },
    {
        "id": "major-river-flood",
        "title": "Flood facilities in major river basins",
        "fy2027": "Construction/ Rehabilitation of Flood Mitigation Facilities within Major River Basins and Principal Rivers",
        "fy2026": "Construction/ Rehabilitation of Flood Mitigation Facilities within Major River Basins and Principal Rivers",
        "historyTerm": "flood mitigation facilities",
        "status": "Existing FY2026 category",
        "interpretation": "This exact category label appears in the FY2026 schedule under Flood Management Program. The FY2027 NEP has more proposed records and a larger amount, but differing schedule granularity means scope-by-scope comparison is still needed.",
    },
    {
        "id": "rcs",
        "title": "Rainwater Collector System (RCS)",
        "fy2027": "Rainwater Collector System",
        "fy2026": "Rainwater Collector System",
        "historyTerm": "rainwater collector system",
        "status": "Returning program; present in FY2026",
        "interpretation": "RCS is not a first-use term: it appears in the FY2023 GAA and FY2026 DPWH schedule. The FY2027 proposal continues the named program at a different scale.",
    },
    {
        "id": "inspire",
        "title": "INSPIRE Building",
        "fy2027": "INSPIRE Building",
        "fy2026": None,
        "historyTerm": "inspire building",
        "status": "Returning named project",
        "interpretation": "The named Laoag City building appears in FY2023 and FY2025 GAA records, then returns in the FY2027 NEP. FY2027 is not its first appearance; this should be reviewed as a continuing or phased project.",
    },
]

# Keep technical hierarchy, office, and location shorthand out of the keyword lead list.
KEYWORD_STOPLIST = {
    "DPWH", "BRGY", "STA", "NRJ", "JCT", "PHASE", "NCR", "GOP", "GAA", "NEP",
    "MOOE", "PS", "ICT", "LGU", "DEO", "FY", "PAP", "UACS", "NGA", "SUCS", "HEI",
    "LZ", "MN", "PW", "CB", "TC", "SM", "MT", "NR", "PN", "TL", "MR", "CG", "LT",
    "BN", "BH", "GR", "SY", "DG", "SG", "LP", "MQ", "TW", "AB", "CR", "EO", "RA",
}


def duckdb(sql: str) -> list[dict]:
    result = subprocess.run(["duckdb", "-json", "-c", sql], check=True, text=True, capture_output=True)
    return json.loads(result.stdout or "[]")


def q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def one(rows: list[dict]) -> dict:
    return rows[0] if rows else {"n": 0, "pesos": 0}


def allocation_profile(row: dict) -> str:
    count = int(row.get("allocationRecords") or 0)
    recipients = int(row.get("recipientCount") or 0)
    share = float(row.get("modalShare") or 0)
    top_share = float(row.get("topAllocationShare") or 0)
    if count == 1:
        return "Unique line item"
    if recipients >= 10 and share >= 0.7:
        return "Broad, standardized distribution"
    if top_share >= 0.5:
        return "Concentrated in largest line"
    return "Multiple, variable allocations"


def main() -> None:
    candidates = []
    for item in CATEGORIES:
        fy27 = one(duckdb(
            "SELECT count(*) AS n, round(sum(amount) * 1000) AS pesos "
            f"FROM read_parquet({q(str(NEP_2027))}) WHERE pap3={q(item['fy2027'])} "
            f"OR lower(projectName) LIKE {q('%' + item['fy2027'].lower() + '%')}"
        ))
        if item["fy2026"]:
            fy26 = one(duckdb(
                "SELECT count(*) AS n, round(sum(amount)) AS pesos "
                f"FROM read_parquet({q(str(DPWH_2026))}) WHERE level_5={q(item['fy2026'])} "
                f"OR level_6={q(item['fy2026'])} OR level_7={q(item['fy2026'])}"
            ))
        else:
            fy26 = {"n": 0, "pesos": 0}
        term = item["historyTerm"]
        hist = duckdb(
            "SELECT year, count(*) AS n, round(sum(amount) * 1000) AS pesos "
            f"FROM read_parquet({q(str(HISTORY))}) WHERE lower(description) LIKE {q('%' + term + '%')} "
            "GROUP BY year ORDER BY year"
        )
        candidates.append({**item, "fy2027Count": int(fy27["n"] or 0), "fy2027Pesos": int(fy27["pesos"] or 0),
                           "fy2026Count": int(fy26["n"] or 0), "fy2026Pesos": int(fy26["pesos"] or 0), "historical": hist})

    keyword_rows = duckdb(
        "WITH named AS ("
        "SELECT agency, projectName, round(sum(amountPesos)) AS pesos "
        f"FROM read_parquet({q(str(ROOT / 'nep_fy2027_all.parquet'))}) "
        "WHERE projectName IS NOT NULL GROUP BY agency, projectName HAVING sum(amountPesos)>0), "
        "tokens AS (SELECT DISTINCT agency, projectName, pesos, "
        "unnest(regexp_extract_all(projectName, '\\b[A-Z]{3,10}(?:-[A-Z]{1,5})?\\b')) AS keyword FROM named), "
        "hits AS (SELECT keyword, count(DISTINCT projectName) AS projectCount, "
        "round(sum(pesos)) AS pesos, string_agg(DISTINCT agency, ' | ') AS agencies, "
        "string_agg(DISTINCT projectName, ' || ') AS examples FROM tokens GROUP BY keyword) "
        "SELECT * FROM hits WHERE pesos > 0 ORDER BY pesos DESC"
    )
    prior_keyword_years = {
        row["keyword"]: [int(year) for year in (row.get("gaa_years") or "").split(",") if year]
        for row in duckdb(
            "WITH tokens AS (SELECT year, unnest(regexp_extract_all(upper(description), "
            "'\\b[A-Z]{3,10}(?:-[A-Z]{1,5})?\\b')) AS keyword "
            f"FROM read_parquet({q(str(HISTORY))}) WHERE description IS NOT NULL) "
            "SELECT keyword, string_agg(DISTINCT cast(year AS VARCHAR), ',' ORDER BY cast(year AS VARCHAR)) AS gaa_years "
            "FROM tokens GROUP BY keyword"
        )
    }
    new_keywords = []
    for row in keyword_rows:
        keyword = row["keyword"]
        if keyword in KEYWORD_STOPLIST:
            continue
        years = prior_keyword_years.get(keyword, [])
        if years and max(years) >= 2023:
            continue
        examples = (row.get("examples") or "").split(" || ")[:4]
        agencies = (row.get("agencies") or "").split(" | ")[:8]
        new_keywords.append({
            "keyword": keyword,
            "keywordStatus": "Revived" if years else "Potential first appearance",
            "priorGaaYears": years,
            "projectCount": int(row["projectCount"] or 0),
            "pesos": int(row["pesos"] or 0),
            "agencies": agencies,
            "examples": examples,
            "priorGaaMatches": 0,
        })

    phrase_rows = duckdb(
        "WITH named AS (SELECT agency, projectName, round(sum(amountPesos)) AS pesos "
        f"FROM read_parquet({q(str(ROOT / 'nep_fy2027_all.parquet'))}) "
        "WHERE projectName IS NOT NULL GROUP BY agency, projectName HAVING sum(amountPesos)>0), "
        "phrases AS (SELECT agency, projectName, pesos, trim(split_part(projectName, ':', 1)) AS phrase "
        "FROM named WHERE strpos(projectName, ':') > 0) "
        "SELECT phrase AS keyword, count(DISTINCT projectName) AS projectCount, "
        "round(sum(pesos)) AS pesos, string_agg(DISTINCT agency, ' | ') AS agencies, "
        "string_agg(DISTINCT projectName, ' || ') AS examples FROM phrases "
        "WHERE length(phrase) >= 8 AND length(phrase) <= 65 AND lower(phrase) <> 'philippines' "
        "AND NOT regexp_matches(lower(phrase), '^(construction|completion|establishment|rehabilitation|improvement|installation|development of|acquisition|purchase|repair|maintenance|concreting|upgrading|provision|supply|procurement|continuation of|payment of|support to|conduct of|reconstruction|replacement|conversion of|fabrication|fabricate|furnishing|refurbishment|expansion of|land development|newly constructed)') "
        "GROUP BY phrase HAVING sum(pesos) > 0 ORDER BY pesos DESC"
    )
    if phrase_rows:
        checks = ", ".join(
            f"string_agg(DISTINCT CASE WHEN lower(coalesce(description,'')) LIKE {q('%' + row['keyword'].lower() + '%')} "
            f"THEN cast(year AS VARCHAR) END, ',' ORDER BY CASE WHEN lower(coalesce(description,'')) LIKE {q('%' + row['keyword'].lower() + '%')} "
            f"THEN cast(year AS VARCHAR) END) AS m{i}"
            for i, row in enumerate(phrase_rows)
        )
        match_row = one(duckdb(
            f"SELECT {checks} FROM read_parquet({q(str(HISTORY))})"
        ))
        phrase_years = {
            row["keyword"]: [int(year) for year in (match_row.get(f"m{i}") or "").split(",") if year]
            for i, row in enumerate(phrase_rows)
        }
        acronym_terms = {row["keyword"] for row in new_keywords}
        for row in phrase_rows:
            phrase = row["keyword"]
            years = phrase_years.get(phrase, [])
            if (years and max(years) >= 2023) or phrase in acronym_terms:
                continue
            new_keywords.append({
                "keyword": phrase,
                "keywordType": "Named phrase",
                "keywordStatus": "Revived" if years else "Potential first appearance",
                "priorGaaYears": years,
                "projectCount": int(row["projectCount"] or 0),
                "pesos": int(row["pesos"] or 0),
                "agencies": (row.get("agencies") or "").split(" | ")[:8],
                "examples": (row.get("examples") or "").split(" || ")[:4],
                "priorGaaMatches": 0,
            })
    for row in new_keywords:
        row.setdefault("keywordType", "Uppercase keyword")
    new_keywords.sort(key=lambda row: row["pesos"], reverse=True)

    if new_keywords:
        value_rows = ",".join(f"({q(row['keyword'])}, {q(row['keywordType'])})" for row in new_keywords)
        allocation_rows = duckdb(
            "WITH keywords(keyword, kind) AS (VALUES " + value_rows + "), "
            "line_allocations AS (SELECT agency, projectName, OPERUNIT, round(sum(amountPesos)) AS amount "
            f"FROM read_parquet({q(str(ROOT / 'nep_fy2027_all.parquet'))}) "
            "WHERE projectName IS NOT NULL GROUP BY agency, projectName, OPERUNIT HAVING sum(amountPesos) > 0), "
            "matched AS (SELECT k.keyword, l.OPERUNIT, l.amount FROM keywords k JOIN line_allocations l ON "
            "((k.kind='Uppercase keyword' AND regexp_matches(l.projectName, '(^|[^A-Za-z0-9])' || regexp_escape(k.keyword) || '([^A-Za-z0-9]|$)')) "
            "OR (k.kind='Named phrase' AND contains(lower(l.projectName), lower(k.keyword))))), "
            "freq AS (SELECT keyword, amount, count(*) AS n FROM matched GROUP BY keyword, amount), "
            "modal AS (SELECT *, row_number() OVER(PARTITION BY keyword ORDER BY n DESC, amount DESC) AS rn FROM freq), "
            "stats AS (SELECT keyword, count(*) AS allocationRecords, count(DISTINCT OPERUNIT) AS recipientCount, "
            "round(sum(amount)) AS distributedPesos, min(amount) AS minAllocation, max(amount) AS maxAllocation, "
            "max(amount)/sum(amount) AS topAllocationShare FROM matched GROUP BY keyword) "
            "SELECT s.*, m.amount AS modalAllocation, m.n AS modalCount, m.n/s.allocationRecords AS modalShare "
            "FROM stats s JOIN modal m ON s.keyword=m.keyword AND m.rn=1"
        )
        stats_by_keyword = {row["keyword"]: row for row in allocation_rows}
        for row in new_keywords:
            stats = stats_by_keyword.get(row["keyword"], {})
            row.update({
                "allocationRecords": int(stats.get("allocationRecords") or 0),
                "recipientCount": int(stats.get("recipientCount") or 0),
                "distributedPesos": int(stats.get("distributedPesos") or 0),
                "modalAllocation": int(stats.get("modalAllocation") or 0),
                "modalCount": int(stats.get("modalCount") or 0),
                "modalShare": float(stats.get("modalShare") or 0),
                "minAllocation": int(stats.get("minAllocation") or 0),
                "maxAllocation": int(stats.get("maxAllocation") or 0),
                "topAllocationShare": float(stats.get("topAllocationShare") or 0),
            })
            row["allocationProfile"] = allocation_profile(row)

    # The DPWH proposal schedule resolves RCS and INSPIRE to actual district/project lines,
    # which are more informative than the consolidated project-name rows in the full NEP file.
    for row in candidates:
        if row["id"] == "rcs":
            condition = "pap3='Rainwater Collector System'"
        elif row["id"] == "inspire":
            condition = "projectName ILIKE '%INSPIRE Building%'"
        else:
            condition = f"pap3={q(row['fy2027'])}"
        lines = duckdb(
            "WITH allocations AS (SELECT office, projectName, sum(amount) AS amount "
            f"FROM read_parquet({q(str(NEP_2027))}) WHERE {condition} "
            "GROUP BY office, projectName HAVING sum(amount) > 0), "
            "freq AS (SELECT amount,count(*) AS n FROM allocations GROUP BY amount), "
            "mode AS (SELECT amount,n,row_number() OVER(ORDER BY n DESC,amount DESC) rn FROM freq), "
            "stats AS (SELECT count(*) AS allocationRecords,count(DISTINCT office) AS recipientCount, "
            "round(sum(amount)*1000) AS distributedPesos,min(amount)*1000 AS minAllocation, "
            "max(amount)*1000 AS maxAllocation,max(amount)/sum(amount) AS topAllocationShare FROM allocations) "
            "SELECT s.*,m.amount*1000 AS modalAllocation,m.n AS modalCount,m.n/s.allocationRecords AS modalShare "
            "FROM stats s LEFT JOIN mode m ON m.rn=1"
        )
        stats = one(lines)
        row.update({
            "allocationRecords": int(stats.get("allocationRecords") or 0),
            "recipientCount": int(stats.get("recipientCount") or 0),
            "distributedPesos": int(stats.get("distributedPesos") or 0),
            "modalAllocation": int(stats.get("modalAllocation") or 0),
            "modalCount": int(stats.get("modalCount") or 0),
            "modalShare": float(stats.get("modalShare") or 0),
            "minAllocation": int(stats.get("minAllocation") or 0),
            "maxAllocation": int(stats.get("maxAllocation") or 0),
            "topAllocationShare": float(stats.get("topAllocationShare") or 0),
        })
        row["allocationProfile"] = allocation_profile(row)

    candidates.sort(key=lambda row: row["fy2027Pesos"], reverse=True)

    data = {
        "title": "Budget Innovations",
        "scope": "Uppercase keywords in FY2027 NEP project names across agencies compared with FY2020–FY2025 enacted budget descriptions; selected DPWH categories are also compared with the local FY2026 DPWH schedule.",
        "method": "Keywords absent from FY2020–FY2025 GAA descriptions are labeled Potential first appearance. Keywords found only in FY2020–FY2022, with no exact match in FY2023–FY2025, are labeled Revived after a three-year gap. This classification uses the local archive only; it does not cover years before 2020 and is not proof that the underlying project, idea, or scope is new. Category names can change while project scope continues; counts and totals may be at different hierarchy levels.",
        "candidates": candidates,
        "potentialKeywords": new_keywords,
        "keywordScan": {
            "source": "FY2027 NEP project names across agencies",
            "comparison": "Exact uppercase keyword match in FY2020–FY2025 enacted budget descriptions",
            "coverageYears": [2020, 2021, 2022, 2023, 2024, 2025],
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "budget-innovations-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
