#!/usr/bin/env python3
"""Build a detailed, source-preserving Butuan NEP vs HGAB comparison JSON."""
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEP_PATH = ROOT / "2027.json"
HGAB_PATH = ROOT / "hb10858_3rd_dpwh_projects.json"
COMPARISON_PATH = ROOT / "analysis_output" / "hb_nep_comparison_3rd.csv"
OUTPUT_PATH = ROOT / "analysis_output" / "butuan_nep_hgab_mapping.json"


def text(value: object) -> str:
    return str(value or "").strip()


def has_butuan_city(value: object) -> bool:
    return bool(re.search(r"\bbutuan\s+city\b", text(value), re.I))


def is_butuan_deo(value: object) -> bool:
    value = text(value).lower()
    return "butuan city district engineering office" in value or bool(re.match(r"butuan city deo\b", value))


def raw_amount_pesos(row: dict, nep: bool = False) -> int | None:
    if nep:
        # The NEP API's amount is reported in thousands of pesos.
        amount = row.get("amount")
        return int(round(float(amount) * 1000)) if amount not in (None, "") else None
    amount = row.get("amountPesos")
    return int(round(float(amount))) if amount not in (None, "") else None


def load_comparison() -> dict[tuple[str, str, str], dict]:
    result = {}
    with COMPARISON_PATH.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (text(row.get("sourcePage")), text(row.get("projectName")), text(row.get("amountPesos")))
            result[key] = {
                "classification": row.get("comparison"),
                "closestNepTitle": row.get("closest_nep_title") or None,
                "closestNepOffice": row.get("closest_nep_office") or None,
                "closestNepAmountPesos": int(row["closest_nep_amount_pesos"]) if row.get("closest_nep_amount_pesos") else None,
                "titleSimilarityPercent": float(row["title_similarity_pct"] or 0),
                "matchBasis": row.get("match_basis"),
            }
    return result


def add_comparison(hgab_row: dict, lookup: dict) -> dict:
    key = (text(hgab_row.get("sourcePage")), text(hgab_row.get("projectName")), text(hgab_row.get("amountPesos")))
    assessment = lookup.get(key)
    return {**hgab_row, "comparisonAssessment": assessment}


def main() -> None:
    nep_source = json.loads(NEP_PATH.read_text(encoding="utf-8"))
    hgab_source = json.loads(HGAB_PATH.read_text(encoding="utf-8"))
    nep_rows = nep_source["data"]["data"]
    hgab_rows = hgab_source["data"]["data"]
    comparison = load_comparison()

    # "Butuan allocation" is limited to the Butuan City DEO in NEP.
    nep_local = [r for r in nep_rows if is_butuan_deo(r.get("office"))]
    # Butuan text in a regional road title can refer to a distant chainage.
    # Preserve those cross-office references separately instead of assigning
    # them to the Butuan City DEO on the basis of the place name alone.
    nep_route_refs = [r for r in nep_rows if has_butuan_city(r.get("projectName")) and not is_butuan_deo(r.get("office"))]

    # Include all extracted rows assigned to Butuan City DEO and all rows whose
    # title names Butuan City. The latter are retained with their actual office
    # so office/title conflicts and cross-office routes stay visible.
    hgab_local_or_named = [r for r in hgab_rows if is_butuan_deo(r.get("office")) or has_butuan_city(r.get("projectName"))]
    hgab_butuanon = [r for r in hgab_rows if re.search(r"\bbutuanon\b", text(r.get("projectName")), re.I)]
    hgab_local_or_named = [add_comparison(r, comparison) for r in hgab_local_or_named]

    nep_by_code = {text(r.get("code")): r for r in nep_rows}
    hgab_by_code = {text(r.get("code")): r for r in hgab_rows}

    def nep_ref(code: str) -> dict:
        r = nep_by_code[code]
        return {"code": code, "fiscalYear": r.get("fiscalYear"), "region": r.get("region"),
                "office": r.get("office"), "projectName": r.get("projectName"),
                "pap1": r.get("pap1"), "pap2": r.get("pap2"), "pap3": r.get("pap3"),
                "sourceAmount": r.get("amount"), "sourceAmountUnit": "thousand pesos",
                "amountPesos": raw_amount_pesos(r, nep=True)}

    def hgab_ref(code: str) -> dict:
        r = hgab_by_code[code]
        assessment = comparison.get((text(r.get("sourcePage")), text(r.get("projectName")), text(r.get("amountPesos"))), {})
        return {"code": code, "fiscalYear": r.get("fiscalYear"), "region": r.get("region"),
                "office": r.get("office"), "projectName": r.get("projectName"),
                "sourceAmount": r.get("amount"), "amountPesos": raw_amount_pesos(r),
                "sourcePage": r.get("sourcePage"), "sourceVolume": r.get("sourceVolume"),
                "sourceText": r.get("sourceText"), "reviewStatus": r.get("reviewStatus"),
                "assessment": assessment}

    butuan_cases = [
        {
            "caseId": "water-system-mahay-villa-kanangga",
            "status": "plausible_same_scope_candidate_review_extraction",
            "nep": [nep_ref("2027DPWH-Proposal-38923")],
            "hgab": [hgab_ref("HB10858-3-0374-001423")],
            "reason": "Same named water-system section and same ₱250M amount. HGAB extraction repeats the end of the title; its comparison row is classified plausible and needs scope review.",
        },
        {
            "caseId": "water-system-relief-pipe",
            "status": "exact_title_amount_candidate_with_duplicate_page_extraction",
            "nep": [nep_ref("2027DPWH-Proposal-38925")],
            "hgab": [hgab_ref("HB10858-3-0377-001460"), hgab_ref("HB10858-3-0376-001424")],
            "reason": "The complete page 377 title matches the NEP title and amount (₱300M). Page 376 has the same amount but a merged/truncated title. Both rows may represent a page-break/duplicate extraction of one bill entry; do not count both without checking the PDF. The page 377 row's office is unexpectedly Pangasinan 3rd DEO, while page 376 has a blank office.",
        },
        {
            "caseId": "water-system-villa-kanangga-bancasi",
            "status": "nep_item_no_butuan_hgab_candidate_found",
            "nep": [nep_ref("2027DPWH-Proposal-38924")],
            "hgab": [],
            "reason": "The NEP has a separate ₱300M Villa Kanangga–Bancasi section. No extracted HGAB row naming this section was found in the Butuan City title/office records. This means not found in the local extraction, not confirmed removed from the bill.",
        },
        {
            "caseId": "multi-purpose-building-butuan",
            "status": "plausible_same_item_but_title_coordinates_contaminated",
            "nep": [nep_ref("2027DPWH-Proposal-38931")],
            "hgab": [hgab_ref("HB10858-3-0654-007119")],
            "reason": "Both are ₱400M and the HGAB title begins with the NEP title. The extracted HGAB title appends a second coordinate pair (126.21547, 9.03855), different from NEP's Butuan coordinates (125.508396, 8.942260), so the amount/title prefix alone do not establish a clean one-to-one match.",
        },
        {
            "caseId": "scout-ranger-quarters-heading-contamination",
            "status": "false_candidate_schedule_heading_amount_not_project_amount",
            "nep": [nep_ref("2027DPWH-Proposal-04590")],
            "hgab": [hgab_ref("HB10858-3-0938-012731")],
            "reason": "NEP lists Scout Ranger Quarters at ₱16M. The HGAB extraction attaches the words to a ₱44.749011B amount, but its sourceText is only the FOREIGN-ASSISTED PROJECTS schedule heading and that row is explicitly excluded by the comparison as a heading/total. It is not a valid project match; the underlying HGAB project line was not recovered by this extraction.",
        },
    ]
    mapping_cases = [{
        "caseId": "butuan-local-allocation",
        "priority": 1,
        "scope": "Butuan City DEO and Butuan City project titles",
        "finding": "The Butuan NEP contains separate water-system sections and building projects; HGAB extraction preserves some titles and amounts, but other rows are merged, duplicated across page boundaries, assigned to an inconsistent office, or contaminated by a schedule heading.",
        "cases": butuan_cases,
    }, {
        "caseId": "same-project-amount-changed",
        "scope": "Quezon City flood control",
        "finding": "The location and project title align, but the amount changes from ₱330M in NEP to ₱300M in HGAB. It is a likely same-project revision, not evidence of a wholly new project.",
        "nep": [nep_ref("2027DPWH-Proposal-33737")],
        "hgab": [hgab_ref("HB10858-3-0298-000059")],
    }, {
        "caseId": "same-road-distinct-chainage-segments",
        "scope": "Bukidnon road segments",
        "finding": "Four NEP line items each cover a distinct 4 km STA interval and each cost ₱250M. HGAB has four candidate rows for the same route and amount, but three titles are truncated before the end chainage. Matching on road name alone would collapse distinct segments; the segment endpoints are needed.",
        "nep": [nep_ref(f"2027DPWH-Proposal-{n}") for n in ("39579", "39580", "39581", "39582")],
        "hgab": [hgab_ref(f"HB10858-3-0440-{n}") for n in ("002645", "002646", "002647", "002648")],
    }, {
        "caseId": "merged-multiple-roads-in-one-title",
        "scope": "Pandi By-pass and unrelated road locations",
        "finding": "The ₱140M HGAB extraction starts with Pandi By-pass in Bulacan but continues with chainages and route names from several other provinces. The nearest NEP title is only 14% similar and is an Aliaga–Guimba road in Nueva Ecija. The extracted row cannot be assigned as one clean Pandi match.",
        "nep": [nep_ref("2027DPWH-Proposal-20581")],
        "hgab": [hgab_ref("HB10858-3-0216-000008")],
    }, {
        "caseId": "two-flood-projects-merged-and-truncated",
        "scope": "Davao del Sur flood control",
        "finding": "The two NEP Padada–Mainit River projects are each ₱500M but cover different station ranges/locations. One HGAB row is truncated after its starting chainage; another extraction combines a Talomo River title with the Padada–Mainit project. The title matcher classifies both as no plausible match despite finding the corresponding NEP titles at 82% and 70% similarity.",
        "nep": [nep_ref("2027DPWH-Proposal-21401"), nep_ref("2027DPWH-Proposal-21402")],
        "hgab": [hgab_ref("HB10858-3-0370-001344"), hgab_ref("HB10858-3-0370-001346")],
    }, {
        "caseId": "route-segments-duplicate-across-pages",
        "scope": "NRJ Tagum–Panabo Circumferential Road",
        "finding": "NEP has two route items, ₱230M and ₱600M, with different segment descriptions. The extracted HGAB repeats both amounts on pages 444 and 445. This could be page-boundary duplication in extraction; the copies must not be added as four distinct appropriations without checking the source pages.",
        "nep": [nep_ref("2027DPWH-Proposal-38549"), nep_ref("2027DPWH-Proposal-38550")],
        "hgab": [hgab_ref(f"HB10858-3-0444-{n}") for n in ("002707", "002708")] + [hgab_ref(f"HB10858-3-0445-{n}") for n in ("002725", "002726")],
    }, {
        "caseId": "truncated-bridge-location",
        "scope": "Tandu Bato–Tulayan Bridge, Sulu",
        "finding": "The ₱750M HGAB candidate title ends at “Municipality of” and loses the municipality/location needed to identify the project. The nearest NEP title is an unrelated Zamboanga City revetment at 59% similarity, so it is not a credible match.",
        "nep": [],
        "hgab": [hgab_ref("HB10858-3-0436-002595")],
    }]

    local_total = sum(raw_amount_pesos(r, nep=True) or 0 for r in nep_local)
    hgab_office_rows = [r for r in hgab_local_or_named if is_butuan_deo(r.get("office"))]
    hgab_office_total = sum(raw_amount_pesos(r) or 0 for r in hgab_office_rows)
    classifications = {}
    for r in hgab_local_or_named:
        label = (r.get("comparisonAssessment") or {}).get("classification") or "No comparison row"
        classifications[label] = classifications.get(label, 0) + 1

    output = {
        "title": "FY2027 DPWH Butuan NEP to HGAB 3rd Reading mapping detail",
        "unit": "pesos",
        "method": {
            "nepAmountConversion": "2027.json amount is in thousands of pesos; amountPesos is derived by multiplying by 1,000.",
            "hgabAmounts": "hb10858_3rd_dpwh_projects.json amountPesos is used as extracted.",
            "scope": "NEP allocation records assigned to Butuan City District Engineering Office; all HGAB extracted records assigned to Butuan City DEO or whose title names Butuan City. Cross-office route references are included separately and are not assigned to Butuan City just because the route name contains Butuan.",
            "matching": "The existing hb_nep_comparison_3rd.csv assessment is retained per HGAB row. It is a title/amount candidate assessment, not a confirmed insertion/removal determination.",
            "extractionWarning": hgab_source.get("metadata", {}).get("warning"),
        },
        "sources": {
            "nep": {"file": "2027.json", "fiscalYear": 2027, "recordCount": len(nep_rows)},
            "hgab": {"file": "hb10858_3rd_dpwh_projects.json", "bill": "HB 10858, HGAB 3rd Reading", "fiscalYear": 2027, "recordCount": len(hgab_rows)},
            "comparison": {"file": "analysis_output/hb_nep_comparison_3rd.csv"},
        },
        "summary": {
            "nepButuanDeoRecords": len(nep_local), "nepButuanDeoTotalPesos": local_total,
            "nepButuanTitleReferencesUnderOtherOffices": len(nep_route_refs),
            "hgabRowsWithButuanCityDeoOfficeLabel": len(hgab_office_rows), "hgabOfficeLabelRawExtractedTotalPesos": hgab_office_total,
            "hgabRowsNamedButuanCityOrAssignedButuanDeo": len(hgab_local_or_named),
            "hgabButuanNameRowsByComparisonCategory": classifications,
            "hgabButuanonRiverNameHitsExcludedFromButuanCityScope": len(hgab_butuanon),
            "pdfCrossCheck": {
                "sourceFile": "DPWH per district.pdf",
                "deo": "Butuan City DEO",
                "legislativeDistrict": "Butuan City (Lone District)",
                "amountThousandsPesos": 8834267,
                "amountPesos": 8834267000,
                "nepLineItemSumPesos": local_total,
                "differenceNepMinusPdfPesos": local_total - 8834267000,
                "note": "The gap is ₱4.2M, matching one RCS unit in the NEP records. The scan does not show a fiscal year; treat this as a cross-check, not proof of version identity.",
            },
        },
        "mappingCases": mapping_cases,
        "nepButuanDeoRecords": [
            {**r, "amountPesos": raw_amount_pesos(r, nep=True), "amountUnitInSource": "thousand pesos"}
            for r in nep_local
        ],
        "nepButuanCityRouteReferencesOtherOffices": [
            {**r, "amountPesos": raw_amount_pesos(r, nep=True), "amountUnitInSource": "thousand pesos"}
            for r in nep_route_refs
        ],
        "hgabButuanCityOrOfficeRecords": hgab_local_or_named,
        "hgabButuanonNameHitsExcluded": hgab_butuanon,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    print(json.dumps(output["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
