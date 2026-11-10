#!/usr/bin/env python3
"""Build the Miagao 119-barangay inventory from local BetterGov source data."""

from __future__ import annotations

import json
import re
from zipfile import ZipFile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
ODV = ROOT / "analysis_output"
MIAGAO = Path("/Users/joebertj/bettermiagao/src/data")
OUT = ODV / "miagao-barangay-inventory.json"
DILG_BIS_ROSTER = ROOT / "data_sources/dilg_bis_2025/official-list_06_2025-09-14.xlsx"
DILG_BIS_URL = "https://archive.org/download/20250914.dilg.barangay/official-list_06_2025-09-14.xlsx"
DILG_BIS_DATE = "2025-09-14"
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

# PSA's 2024 POPCEN / PSGC municipality page, captured 2026-11-10.
# Kept as a code-to-value map so source name spelling is not the join key.
POPULATION_2024 = {
    "0603030001": 368, "0603030002": 1010, "0603030003": 608,
    "0603030004": 282, "0603030005": 263, "0603030006": 561,
    "0603030007": 487, "0603030008": 1122, "0603030009": 505,
    "0603030010": 208, "0603030011": 489, "0603030012": 910,
    "0603030013": 420, "0603030014": 142, "0603030015": 3024,
    "0603030016": 944, "0603030017": 197, "0603030018": 480,
    "0603030019": 181, "0603030020": 450, "0603030021": 352,
    "0603030022": 349, "0603030023": 184, "0603030024": 181,
    "0603030025": 123, "0603030026": 165, "0603030027": 92,
    "0603030028": 286, "0603030029": 656, "0603030030": 275,
    "0603030031": 803, "0603030032": 168, "0603030033": 346,
    "0603030034": 287, "0603030035": 138, "0603030036": 1539,
    "0603030037": 1226, "0603030038": 886, "0603030039": 683,
    "0603030040": 387, "0603030041": 987, "0603030042": 179,
    "0603030043": 287, "0603030044": 799, "0603030045": 1130,
    "0603030046": 375, "0603030047": 432, "0603030048": 330,
    "0603030050": 426, "0603030051": 265, "0603030052": 158,
    "0603030053": 541, "0603030054": 321, "0603030055": 439,
    "0603030056": 541, "0603030057": 367, "0603030058": 436,
    "0603030059": 1523, "0603030060": 200, "0603030061": 499,
    "0603030062": 1826, "0603030063": 1388, "0603030064": 1254,
    "0603030065": 520, "0603030066": 725, "0603030067": 522,
    "0603030068": 965, "0603030069": 227, "0603030070": 160,
    "0603030071": 1699, "0603030072": 937, "0603030073": 1129,
    "0603030074": 337, "0603030075": 508, "0603030076": 2617,
    "0603030077": 152, "0603030078": 602, "0603030079": 232,
    "0603030080": 279, "0603030082": 749, "0603030083": 227,
    "0603030084": 928, "0603030085": 266, "0603030086": 201,
    "0603030087": 271, "0603030088": 1553, "0603030089": 2078,
    "0603030090": 132, "0603030091": 410, "0603030092": 533,
    "0603030093": 352, "0603030094": 148, "0603030095": 408,
    "0603030096": 447, "0603030097": 422, "0603030098": 1260,
    "0603030099": 830, "0603030100": 408, "0603030101": 364,
    "0603030102": 193, "0603030103": 459, "0603030104": 712,
    "0603030105": 201, "0603030106": 516, "0603030107": 697,
    "0603030108": 284, "0603030109": 241, "0603030110": 340,
    "0603030111": 223, "0603030112": 131, "0603030113": 452,
    "0603030114": 475, "0603030115": 127, "0603030116": 252,
    "0603030117": 444, "0603030118": 802, "0603030119": 866,
    "0603030120": 432, "0603030121": 238,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def mention_matches(title: str, barangay: str) -> bool:
    """Whole-name match after punctuation normalization, avoiding substring hits."""
    title_tokens = f" {normalize(title)} "
    name_tokens = f" {normalize(barangay)} "
    return name_tokens in title_tokens


def xlsx_inline_rows(path: Path) -> list[dict[str, str]]:
    """Read a simple DILG XLSX sheet using only the Python standard library."""
    with ZipFile(path) as workbook:
        root = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
    rows: list[dict[str, str]] = []
    for row in root.findall(".//m:sheetData/m:row", XLSX_NS):
        values: dict[str, str] = {}
        for cell in row.findall("m:c", XLSX_NS):
            match = re.match(r"([A-Z]+)", cell.attrib.get("r", ""))
            if not match:
                continue
            text = cell.find("m:is/m:t", XLSX_NS)
            value = cell.find("m:v", XLSX_NS)
            values[match.group(1)] = (text.text if text is not None else value.text if value is not None else "") or ""
        rows.append(values)
    if not rows:
        raise RuntimeError(f"No spreadsheet rows found in {path}")
    headers = {value.strip().upper(): key for key, value in rows[0].items()}
    required = {"TERM", "PROVINCE", "CITY/MUNICIPALITY", "BARANGAY", "POSITION", "LASTNAME", "FIRSTNAME"}
    if not required.issubset(headers):
        raise RuntimeError(f"Unexpected DILG workbook headers: {sorted(headers)}")
    output = []
    for row in rows[1:]:
        output.append({header: row.get(column, "").strip() for header, column in headers.items()})
    return output


def parse_dilg_miagao_roster() -> tuple[dict[str, dict[str, str]], dict]:
    if not DILG_BIS_ROSTER.exists():
        raise RuntimeError(f"Missing DILG source workbook: {DILG_BIS_ROSTER}")
    rows = xlsx_inline_rows(DILG_BIS_ROSTER)
    miagao_rows = [
        row for row in rows
        if normalize(row.get("PROVINCE", "")) == "iloilo"
        and normalize(row.get("CITY/MUNICIPALITY", "")) == "miagao"
    ]
    if not miagao_rows:
        raise RuntimeError("DILG workbook has no Miagao rows")

    role_counts: dict[str, int] = {}
    for row in miagao_rows:
        role = row.get("POSITION", "").strip()
        role_counts[role] = role_counts.get(role, 0) + 1

    captains: dict[str, dict[str, str]] = {}
    for row in miagao_rows:
        if normalize(row.get("POSITION", "")) != "punong barangay":
            continue
        name_parts = [
            row.get("FIRSTNAME", ""), row.get("MIDDLENAME", ""),
            row.get("LASTNAME", ""), row.get("SUFFIX", ""),
        ]
        name = " ".join(part.title() for part in name_parts if part.strip())
        barangay = row.get("BARANGAY", "").strip()
        key = normalize(barangay)
        if not key or key in captains:
            raise RuntimeError(f"Duplicate or blank Miagao captain barangay: {barangay!r}")
        captains[key] = {
            "name": name,
            "role": "Punong Barangay",
            "asOf": DILG_BIS_DATE,
            "sourceLabel": "DILG Barangay Information System · Region VI roster snapshot",
            "status": "Listed for the 2023–2025 term in the DILG roster snapshot dated 14 September 2025. Later vacancies or successions are not independently verified here.",
            "source": DILG_BIS_URL,
            "rosterTerm": row.get("TERM", ""),
        }
    if len(captains) != 119:
        raise RuntimeError(f"Expected 119 DILG Miagao captain rows; found {len(captains)}")
    summary = {
        "snapshotDate": DILG_BIS_DATE,
        "sourceUrl": DILG_BIS_URL,
        "barangayRows": len({normalize(row.get("BARANGAY", "")) for row in miagao_rows}),
        "captainRows": len(captains),
        "officialPositionRows": len(miagao_rows),
        "roleCounts": [{"role": role, "count": count} for role, count in sorted(role_counts.items(), key=lambda item: (-item[1], item[0]))],
        "termNote": "The workbook lists the 2023–2025 term. Republic Act 12326 extended the term of the incumbent barangay officials and moved the next BSKE to November 2028. The workbook is not a live succession register.",
    }
    return captains, summary


def main() -> None:
    # PSGC source is JSONL, not a JSON array.
    locations = [
        json.loads(line)
        for line in (ROOT / "data_sources/bettergov-psgc-locations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    barangays = [
        row for row in locations
        if row.get("level") == "barangay" and row.get("parent_code") == "0603030000"
    ]
    if len(barangays) != 119:
        # The source schema varies by vintage. Fall back to the PSGC code prefix.
        barangays = [
            row for row in locations
            if row.get("level") == "barangay" and row.get("parent_code") == "0603030000"
        ]
    if len(barangays) != 119:
        # Use the site's audited full list, preserving its existing display names.
        ts = (MIAGAO / "miagao-barangays.ts").read_text(encoding="utf-8")
        names = re.findall(r"^\s*'([^']+)',\s*$", ts, flags=re.M)
        if len(names) != 119:
            raise RuntimeError(f"Expected 119 barangays; found {len(names)}")
        # PSGC codes are ordinal in Miagao except reserved codes; rely on source row matching.
        code_by_name = {
            normalize(row.get("name", "")): str(row.get("code", row.get("psgc", "")))
            for row in locations
            if row.get("level") == "barangay" and row.get("parent_code") == "0603030000"
        }
        barangays = [{"name": name, "code": code_by_name.get(normalize(name), "")} for name in names]

    mpb_data = load_json(ODV / "mpb-barangay-data.json")
    mpb_by_code = {
        row.get("psgc"): row
        for row in mpb_data.get("barangays", [])
        if row.get("municipality", "").upper() == "MIAGAO"
    }
    project_data = load_json(MIAGAO / "miagao-projects.json")
    projects = project_data["projects"]

    verified_captain_evidence = {
        "Baraclayan": {
            "name": "Marlou R. Niones", "role": "Punong Barangay",
            "asOf": "2024-12-02", "sourceLabel": "DOST Region VI",
            "status": "Identified as Barangay Captain of Baraclayan in 2024 reporting.",
            "source": "https://region6.dost.gov.ph/2024/12/02/western-visayas-participants-triumph-during-dosts-2024-cest-and-setup-awards/",
        },
        "Lanutan": {
            "name": "Arvin Faculin", "role": "Punong Barangay",
            "asOf": "2024-10-03", "sourceLabel": "Municipality of Miagao",
            "status": "Named as newly elected Punong Barangay in the municipality’s 2024 oath-taking report.",
            "source": "https://www.miagao.gov.ph/about-miagao/news/barangay-lanutan-gets-new-pb/",
        },
        "Tiglawa": {
            "name": "Jose Nacita", "role": "Punong Barangay",
            "asOf": "2024-01-25", "sourceLabel": "Municipality of Miagao",
            "status": "Identified as Tiglawa Punong Barangay during a 2024 project conference.",
            "source": "https://www.miagao.gov.ph/about-miagao/news/miagao-to-igbaras-opening-of-road-soon/",
        },
        "San Rafael": {
            "name": "Diofe Fatla-onag", "role": "Punong Barangay",
            "asOf": "2024-06-26", "sourceLabel": "Iloilo Provincial Government",
            "status": "Identified as San Rafael Punong Barangay in a 2024 provincial government report.",
            "source": "https://www.iloilo.gov.ph/en/donations-and-grants-news/financial-aid-child-development-center-san-rafael-miagao",
        },
        "Tacas": {
            "name": "Nestor Faicol", "role": "Punong Barangay",
            "asOf": "2023-11-13", "sourceLabel": "Iloilo Provincial Government",
            "status": "Identified as Tacas Punong Barangay during the November 2023 hall-annex inauguration.",
            "source": "https://www.iloilo.gov.ph/en/node/4991",
        },
        "Igpandan": {
            "name": "Lucia Coronia", "role": "Punong Barangay",
            "asOf": "2025-01-23", "sourceLabel": "Municipality of Miagao",
            "status": "Identified as Igpandan Punong Barangay in a 2025 municipal report.",
            "source": "https://www.miagao.gov.ph/about-miagao/news/for-barangay-igpandan-p40000-assistance-for-the-rehabilitation-of-basketball-court/",
        },
        "Potrido": {
            "name": "Diana Legaspi", "role": "Punong Barangay",
            "asOf": "2026-10-26", "sourceLabel": "Municipality of Miagao",
            "status": "Identified as Potrido Punong Barangay in a municipal report dated October 2026.",
            "source": "https://www.miagao.gov.ph/about-miagao/news/barangay-potrido-through-punong-barangay-diana-legaspi-received-a-cheque-amounting-to-p50000-the-funds-will-be-allocated-for-the-rehabilitation-and-improvement-of-the-alternative-learning-system/",
        },
        "Kirayan Sur": {
            "name": "Rachel Narte", "role": "Punong Barangay",
            "asOf": "2025-02-28", "sourceLabel": "Iloilo Provincial Government",
            "status": "Identified as Kirayan Sur Punong Barangay during a 2025 provincial medical mission.",
            "source": "https://iloilo.gov.ph/en/district-hospital-news/project-buligay-brings-free-medical-services-miag-ao-residents",
        },
        "Cawayanan": {
            "name": "Elmer Nonaillada", "role": "Punong Barangay",
            "asOf": "2025-07-22", "sourceLabel": "Iloilo Provincial Government",
            "status": "Identified as Cawayanan Punong Barangay at the 2025 water-system opening.",
            "source": "https://iloilo.gov.ph/en/infrastructure-news/new-stream-progress-water-system-projects-completed-miagao",
        },
    }

    dilg_captains, roster_summary = parse_dilg_miagao_roster()

    output_rows = []
    for source_row in barangays:
        name = source_row.get("name") or source_row.get("barangay") or ""
        code = str(source_row.get("code") or source_row.get("psgc") or "")
        mpb = mpb_by_code.get(code, {})
        linked_projects = [
            {
                "year": row.get("year"),
                "stage": row.get("stage"),
                "category": row.get("category"),
                "title": row.get("name"),
                "amountPesos": row.get("amountPesos"),
                "source": row.get("source"),
                "locationBasis": "Barangay name appears in project title; not a verified site boundary.",
            }
            for row in projects
            if mention_matches(row.get("name", ""), name)
        ]
        captain = dilg_captains.get(normalize(name))
        later_evidence = verified_captain_evidence.get(name)
        if later_evidence and later_evidence.get("asOf", "") > DILG_BIS_DATE:
            # Preserve genuinely newer official confirmation while keeping the DILG roster date explicit.
            captain = {**captain, **later_evidence, "dilgRosterAsOf": DILG_BIS_DATE}
        output_rows.append({
            "psgc": code,
            "name": name,
            "population2024": POPULATION_2024.get(code),
            "urbanRural2024": source_row.get("urbanRural"),
            "mpb": {
                "projectRowsAllYears": mpb.get("projectRows", 0),
                "buildingCountAllYears": mpb.get("buildingCount", 0),
                "allocationPesosAllYears": mpb.get("allocationPesos", 0),
                "records": [
                    {
                        "year": item.get("year"),
                        "stage": item.get("stage"),
                        "category": item.get("category"),
                        "title": item.get("name"),
                        "amountPesos": item.get("amountPesos"),
                        "source": item.get("source"),
                        "locationBasis": item.get("locationBasis"),
                        "identityConfidence": item.get("identityConfidence"),
                    }
                    for item in mpb.get("projects", [])
                ],
            },
            "titleMatchedProjects": linked_projects,
            "captain": captain,
        })

    if len(output_rows) != 119:
        raise RuntimeError(f"Expected 119 output rows; found {len(output_rows)}")
    missing_population = [row["name"] for row in output_rows if row["population2024"] is None]
    if missing_population:
        raise RuntimeError(f"Population values missing for: {', '.join(missing_population)}")

    result = {
        "title": "Miagao barangay directory and linked public records",
        "generatedAt": "2026-11-10",
        "barangayCount": len(output_rows),
        "sources": {
            "psgcAndPopulation": "https://psa.gov.ph/classification/psgc/barangays/0603030000",
            "historicalAndFy2027DpwhProjects": project_data.get("sourceUrl"),
            "mpbProjectRecords": mpb_data.get("source"),
            "barangayOfficialsRoster": "https://www.miagao.gov.ph/about-miagao/news/know-your-barangay-officials/",
            "dilgBarangayInformationSystemRoster": DILG_BIS_URL,
            "dilgBarangayInformationSystemRosterNote": "DILG Barangay Information System Region VI workbook snapshot dated 2025-09-14. It lists 119 Miagao Punong Barangays for the 2023–2025 term and matches all 119 barangay names in the 2026 PSA list. It is a dated roster, not a live register of later vacancies or successions.",
            "barangayOfficialsRosterNote": "The municipal 2024 post announces the elected roster but its linked media are event photos, not a searchable name list. The DILG workbook provides a machine-readable list; it remains dated evidence rather than live verification.",
            "barangayProfiles": "https://www.miagao.gov.ph/about-miagao/barangay-map-information/",
            "barangayProfilesNote": "The municipal barangay profiles are older background records (profile entries dated 2018); service, infrastructure, and official details may be outdated.",
        },
        "captainRoster": roster_summary,
        "matchingNote": "Project title mentions are leads to public records, not geocoded site boundaries. Shared/corridor projects can be listed for multiple barangays; do not sum per-barangay amounts as a municipality total.",
        "barangays": output_rows,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    app_inventory = MIAGAO / "miagao-barangay-inventory.json"
    app_inventory.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} and {app_inventory} with {len(output_rows)} barangays")
    print("PSA population rows:", len([row for row in output_rows if row["population2024"] is not None]))
    print("MPB barangays with any linked record:", sum(bool(row["mpb"]["records"]) for row in output_rows))
    print("Project-title matched barangays:", sum(bool(row["titleMatchedProjects"]) for row in output_rows))
    print("DILG roster captain rows:", roster_summary["captainRows"])


if __name__ == "__main__":
    main()
