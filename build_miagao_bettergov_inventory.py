#!/usr/bin/env python3
"""Consolidate BetterGov Miagao-related records for local research and review.

This is a discovery bundle, not a verified project register: it preserves source
rows and describes whether Miagao or a barangay name triggered each match.
"""

from __future__ import annotations

import json
import csv
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
BETTERMIAGAO = ROOT.parent / "bettermiagao"
OUT = ROOT / "analysis_output/miagao-bettergov-inventory.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def unique_title_barangays(title: str, barangays: list[str]) -> list[str]:
    haystack = f" {normalized(title)} "
    found = []
    for name in barangays:
        phrase = normalized(name)
        if phrase and f" {phrase} " in haystack:
            found.append(name)
    # Do not report a short barangay that is only embedded in a longer name.
    return [name for name in found if not any(
        len(normalized(other)) > len(normalized(name))
        and normalized(name) in normalized(other)
        and f" {normalized(other)} " in haystack
        for other in found
    )]


def match_basis(title: str, row: dict, barangays: list[str]) -> tuple[str, list[str]] | None:
    title_norm = normalized(title)
    municipality = "miagao" in title_norm.split() or "miag ao" in title_norm
    if municipality:
        return "municipality-name title match", unique_title_barangays(title, barangays)
    # A barangay name is not globally unique (e.g. San Jose). Only accept it
    # when source metadata independently places the row in Miagao. Merely
    # matching Iloilo province or the Iloilo 1st legislative district is not
    # enough to claim a municipality-level location.
    locality_values = [row.get(k) for k in ("municipality", "city", "location", "place")]
    for value in locality_values:
        value_norm = normalized(value or "")
        if "miagao" in value_norm.split() or "miag ao" in value_norm:
            return "source municipality/location field", unique_title_barangays(title, barangays)
    return None


def compact_record(source: str, kind: str, title: str, row: dict, barangays: list[str], **fields):
    basis = match_basis(title, row, barangays)
    if not basis:
        return None
    basis_label, title_barangays = basis
    record = {
        "source": source,
        "recordType": kind,
        "title": str(title).strip(),
        "matchBasis": basis_label,
        "titleBarangayMentions": title_barangays,
    }
    record.update({k: v for k, v in fields.items() if v not in (None, "", [])})
    if row.get("id") is not None:
        record["sourceRecordId"] = row["id"]
    elif row.get("hgab_id") is not None:
        record["sourceRecordId"] = row["hgab_id"]
    elif row.get("project_code") is not None:
        record["sourceRecordId"] = row["project_code"]
    return record


def main() -> None:
    barangay_source = BETTERMIAGAO / "src/data/miagao-barangays.ts"
    names = re.findall(r"^\s*'([^']+)',\s*$", barangay_source.read_text(encoding="utf-8"), re.M)
    if len(names) != 119:
        raise RuntimeError(f"Expected Miagao's 119 barangays; found {len(names)}")

    records: list[dict] = []
    source_counts: dict[str, dict] = {}

    def add(source: str, kind: str, title: str, row: dict, **fields):
        record = compact_record(source, kind, title, row, names, **fields)
        if record:
            records.append(record)
            source_counts.setdefault(source, {"matchedRows": 0, "matchBasisCounts": defaultdict(int)})
            source_counts[source]["matchedRows"] += 1
            source_counts[source]["matchBasisCounts"][record["matchBasis"]] += 1

    # The existing broad historical/annual project series used on Better Miagao.
    integrated_path = ODV / "static/nep-preview/integrated-project-data.json"
    integrated = read_json(integrated_path)
    for row in integrated.get("projects", []):
        add("ODV integrated project series", "National DPWH budget/project row", row.get("name", ""), row,
            year=row.get("year"), stage=row.get("stage"), category=row.get("category"),
            amountPesos=row.get("amountPesos"), office=row.get("office"), sourceReference=row.get("source"),
            districtId=row.get("districtId"))

    # DIME/SSP/PhilGEPS cross-source contracts for Iloilo.
    province_path = ODV / "static/data/province-projects-iloilo/all-projects-cache.json"
    province = read_json(province_path)
    for row in province.get("projects", []):
        title = row.get("project_name") or row.get("project_name_1") or ""
        add("ODV Iloilo province project cache", "Contract/procurement project record", title, row,
            year=row.get("year"), stage="contract / procurement record", category=row.get("project_type"),
            amountPesos=row.get("amount"), status=row.get("status"), contractor=row.get("contractor"),
            office=row.get("office"), location=row.get("location"), sourceSystems=row.get("sources_list") or row.get("sources"),
            sourceKind=row.get("source"))

    # The Iloilo 1st District representative's portal records, including some
    # rows whose locality is expressed only through the project title.
    district_path = ODV / "static/data/congressman-projects-janette-garin/all-projects-cache.json"
    district = read_json(district_path)
    for row in district.get("projects", []):
        title = row.get("project_name") or row.get("project_name_1") or ""
        add("ODV Iloilo 1st District project cache", "District portal project record", title, row,
            year=row.get("project_year") or row.get("contract_year"), stage=row.get("source_of_funds"),
            category=row.get("program"), amountPesos=row.get("amount") or row.get("contract_amount"),
            status=row.get("status"), barangay=row.get("barangay"), office=row.get("organization_name"),
            contractor=row.get("contractor_name"), projectCode=row.get("project_code"),
            latitude=row.get("latitude"), longitude=row.get("longitude"))

    # 2027 House 3rd-reading DPWH insertions: catch both municipality-level
    # titles and rows named only for Miagao barangays.
    dpwh_data = read_json(ODV / "static/nep-preview/dpwh-data.json")
    for row in dpwh_data.get("hbInsertions", []):
        title = row.get("projectName", "")
        add("ODV DPWH FY2027 HGAB 3rd-reading data", "Proposed DPWH insertion", title, row,
            year=2027, stage="HGAB 3rd reading · proposal", amountPesos=row.get("amountPesos"),
            category=row.get("program"), office=row.get("office"), region=row.get("region"),
            hgabId=row.get("hgab_id"), sourceVolume=row.get("sourceVolume"), sourcePage=row.get("sourcePage"),
            proposalCounterpart=row.get("closest_nep_title"), comparison=row.get("comparison"))

    # FY2026 amendment table is a separate budget stage and kept distinct from
    # annual GAA/contract values.
    amendments = read_json(ODV / "static/data/budget_amendments_2026.json")
    for row in amendments.get("projects", []):
        title = row.get("display_name") or row.get("revised_name") or row.get("name", "")
        add("ODV DPWH FY2026 budget amendments", "Budget amendment row", title, row,
            year=2026, stage="FY2026 budget amendment", amountPesos=row.get("final_amount"),
            originalAmountPesos=row.get("original_amount"), increasePesos=row.get("increase"),
            description=row.get("description"), pageReference=row.get("page_reference"),
            sourceSheet=row.get("source_sheet"), amendmentId=row.get("id"))

    # FMR rows are a specialized current proposal subset; preserve the source
    # page and coordinates as locational leads, without treating them as as-built.
    fmr_data = read_json(ODV / "static/nep-preview/fmr-data.json")
    for row in fmr_data.get("stageMatches", []):
        title = row.get("title", "")
        add("ODV FY2027 FMR dataset", "Proposed FMR row", title, row,
            year=2027, stage="HGAB 3rd reading · proposal", amountPesos=row.get("amount_php"),
            region=row.get("region"), hgabId=row.get("project_id"), sourcePage=row.get("source", {}).get("pdf_page"),
            coordinates=row.get("coordinates"), coordinateReviewFlags=row.get("original_review_flags"))

    # Historical MPB inventory with title-level barangay allocation.
    mpb = read_json(ODV / "static/nep-preview/mpb-barangay-base-data.json")
    for barangay in mpb.get("barangays", []):
        if normalized(barangay.get("municipality", "")) != "miagao":
            continue
        for building in barangay.get("buildings", []):
            for level in building.get("levelHistory", []):
                mpb_row = {**building, "municipality": barangay.get("municipality"), "province": barangay.get("province"),
                           "barangay": barangay.get("barangay"), "psgc": barangay.get("id")}
                add("ODV historical MPB barangay inventory", "Historical MPB budget row", building.get("name", ""), mpb_row,
                    year=level.get("year"), stage="GAA / budget dataset", category="Multi-purpose building",
                    amountPesos=level.get("amountPesos"), barangay=barangay.get("barangay"),
                    psgc=barangay.get("id"), mpbLevel=level.get("level"))

    # Document extracted signatory candidates tied to the same 2027 title rows.
    dc = read_json(ODV / "static/nep-preview/development-council-data.json")
    miagao_hgab_ids = {
        row.get("hgabId") for row in records
        if row.get("recordType") == "Proposed DPWH insertion" and row.get("hgabId")
    }
    for row in dc.get("candidates", []):
        if row.get("hgabId") not in miagao_hgab_ids:
            continue
        add("ODV parsed Senate HGAB POW / Development Council candidates", "Extracted signatory role candidate",
            row.get("title", ""), row, year=2027, stage="HGAB 3rd reading · parsed document evidence",
            amountPesos=row.get("amountPesos"), name=row.get("name"), role=row.get("role"),
            office=row.get("office"), region=row.get("region"), hgabId=row.get("hgabId"),
            documentSources=row.get("sources"), sameProjectSignatories=row.get("sameProjectSignatories"))

    # Contextual spatial source records. They are mapped features, not proof of
    # ownership, access, operation, or any project's connection to the place.
    for fname, label, kind in [
        ("connectivity-venues-data.json", "ODV mapped public venues / services", "Mapped venue or facility cue"),
        ("connectivity-property-indicators-data.json", "ODV mapped property indicators", "Mapped property cue"),
        ("connectivity-public-services-data.json", "ODV mapped public services", "Mapped public service"),
    ]:
        path = ODV / "static/nep-preview" / fname
        if not path.exists():
            continue
        data = read_json(path)
        for row in data.get("rows", []):
            if normalized(row.get("municipality", "")) != "miagao" or normalized(row.get("province", "")) != "iloilo":
                continue
            record = {
                "source": label, "recordType": kind,
                "title": row.get("name") or row.get("type") or kind,
                "matchBasis": "municipality field within archived DPWH boundary / OSM source snapshot",
                "sourceId": row.get("id"), "latitude": row.get("latitude"), "longitude": row.get("longitude"),
                "sourceUrl": row.get("sourceUrl"), "sourceTags": row.get("evidence") or row.get("buildingTag"),
                "ownershipStatus": row.get("ownershipStatus"), "operatingStatus": row.get("operatingStatus"),
                "snapshotBasis": row.get("placeEvidence"),
            }
            records.append(record)
            source_counts.setdefault(label, {"matchedRows": 0, "matchBasisCounts": defaultdict(int)})
            source_counts[label]["matchedRows"] += 1
            source_counts[label]["matchBasisCounts"][record["matchBasis"]] += 1

    public_services_path = ODV / "static/nep-preview/connectivity-public-services-data.csv"
    if public_services_path.exists():
        with public_services_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if normalized(row.get("municipality", "")) != "miagao" or normalized(row.get("province", "")) != "iloilo":
                    continue
                records.append({
                    "source": "ODV mapped public services", "recordType": "Mapped public service",
                    "title": row.get("name") or row.get("type") or "Mapped public service",
                    "matchBasis": "municipality field within archived DPWH boundary / OSM source snapshot",
                    "sourceId": row.get("id"), "latitude": row.get("latitude"), "longitude": row.get("longitude"),
                    "sourceUrl": row.get("sourceUrl"), "sourceTags": row.get("evidence"),
                    "snapshotBasis": row.get("placeEvidence"),
                })
                source_counts.setdefault("ODV mapped public services", {"matchedRows": 0, "matchBasisCounts": defaultdict(int)})
                source_counts["ODV mapped public services"]["matchedRows"] += 1
                source_counts["ODV mapped public services"]["matchBasisCounts"]["municipality field within archived DPWH boundary / OSM source snapshot"] += 1

    # Deduplicate repeated identical source rows, retaining distinct amounts,
    # years, codes, and status snapshots as separate evidence.
    seen = set()
    deduped = []
    for row in records:
        stable = (
            row.get("source"), row.get("recordType"), row.get("sourceRecordId") or row.get("hgabId") or row.get("sourceId"),
            normalized(row.get("title", "")), row.get("year"), row.get("amountPesos"), row.get("name"), row.get("role"),
        )
        if stable in seen:
            continue
        seen.add(stable)
        deduped.append(row)

    # Cross-source exact-name groups are convenience links only; all underlying
    # rows remain available, and differing amounts/stages are not collapsed.
    groups = defaultdict(list)
    for idx, row in enumerate(deduped):
        title_key = normalized(row.get("title", ""))
        if not title_key:
            continue
        groups[(title_key, row.get("year"), row.get("amountPesos"))].append(idx)
    cross_source_groups = []
    for (title_key, year, amount), indexes in groups.items():
        sources = sorted({deduped[i].get("source", "") for i in indexes})
        if len(sources) < 2:
            continue
        cross_source_groups.append({
            "title": deduped[indexes[0]]["title"], "year": year, "amountPesos": amount,
            "sourceRows": [{"index": i, "source": deduped[i]["source"], "recordType": deduped[i]["recordType"]} for i in indexes],
            "note": "Exact normalized title/year/amount cross-source grouping; not an adjudicated identity merge.",
        })

    # Counts for each source class include raw matches and matched rows retained.
    sources = []
    for source, info in sorted(source_counts.items()):
        sources.append({"source": source, "matchedRowsBeforeExactDedup": info["matchedRows"],
                        "matchBasisCounts": dict(info["matchBasisCounts"])})

    result = {
        "title": "Miagao-related BetterGov source inventory",
        "generatedAt": date.today().isoformat(),
        "scope": "Local search of BetterGov ODV public datasets and report data for Miagao / Miag-ao and exact Miagao barangay-title mentions. It is a research inventory, not a verified as-built, spending, property-ownership, or current-official register.",
        "locationMatching": "Punctuation-normalized Miagao/Miag-ao title mention or source municipality/location field naming Miagao. Generic barangay-name matches alone are excluded because barangay names repeat across the country. Shared/corridor projects still require manual location review.",
        "stageNote": "FY2027 rows are proposals; budget amendment, historical GAA, contract, district portal, mapped facility, and extracted document-candidate records are separate evidence types. Never sum them as if they were one appropriation.",
        "sourceInventory": sources,
        "matchedSourceRecordCount": len(deduped),
        "exactTitleYearAmountCrossSourceGroups": len(cross_source_groups),
        "records": deduped,
        "crossSourceGroups": cross_source_groups,
        "limitations": [
            "Title mentions are not geocoded project boundaries or proof that the work lies wholly within the named barangay.",
            "Contract, budget, district portal, and GAA sources can represent different funding or reporting stages for the same work.",
            "Source status fields can disagree or be stale; no one source has been chosen as ground truth.",
            "Parsed POW and Development Council names are candidates, not verified current officials or project sponsors.",
            "OpenStreetMap venue, property, and service points are mapped cues; ownership, operation, access, and current conditions are unverified.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(deduped)} source rows to {OUT}")
    for row in sources:
        print(f"{row['source']}: {row['matchedRowsBeforeExactDedup']} rows")
    print(f"Exact normalized title/year/amount groups across sources: {len(cross_source_groups)}")


if __name__ == "__main__":
    main()
