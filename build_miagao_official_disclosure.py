#!/usr/bin/env python3
"""Parse Miagao 2026 disclosure spreadsheets and official profile pages.

Outputs source-preserving JSON and a cautious APP ↔ bid-results crosswalk.
The Q1 receipts/expenditures workbook is an aggregate financial statement;
it is never treated as project-level spending evidence.
"""
from __future__ import annotations

import html
import json
import re
import shutil
import zipfile
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "data_sources/miagao_official_2026"
OUT = ROOT / "analysis_output/miagao-official-disclosure-2026.json"
PUBLIC_OUT = ROOT / "analysis_output/miagao-public-records-2026.json"
PUBLIC_DIR = ROOT / "analysis_output/miagao-disclosure-data"
BETTERMIAGAO_PUBLIC_DIR = ROOT.parent / "bettermiagao/public/data/miagao-disclosure"
NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
FILES = {
    "budget": ("Budget2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/06/Budget2026.xlsx"),
    "app": ("CONSOLIDATED-APP-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/06/CONSOLIDATED-APP-2026.xlsx"),
    "sreQ1": ("template-sre-1STQ2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/06/template-sre-1STQ2026.xlsx"),
    "bidResultsQ1": ("FDP-DILG-Compliance-1st-Quarter-2026-CivilGoods-and-Consulting-Services.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/05/FDP-DILG-Compliance-1st-Quarter-2026-CivilGoods-and-Consulting-Services.xlsx"),
    "consolidatedProgressQ1": ("1CONSOLIDATED-REPORT-1ST-QTR-2026-1.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/04/1CONSOLIDATED-REPORT-1ST-QTR-2026-1.xlsx"),
}

# Quarterly files linked from the municipality's 2026 Full Disclosure pages.
# Keep the official URL and local filename together so each published row is
# traceable to its workbook. The Q2 consolidated-progress page currently links
# the Q1 workbook; it is intentionally not registered as Q2 evidence.
QUARTERLY_FILES = {
    "q2": [
        ("20% NTA development fund utilization", "20NTAutilizationnewformat2026-Q2.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/20NTAutilizationnewformat2026.xlsx"),
        ("LDRRMF utilization", "LDRRMF-Utilization-as-of-June-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/09/LDRRMF-Utilization-as-of-June-30-2026-updated.xlsx"),
        ("Trust fund utilization", "Trust-Fund-Utilization-as-of-June-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/Trust-Fund-Utilization-as-of-June-30-2026-F.xlsx"),
        ("Statement of cash flows", "Statement-of-Cash-Flows-as-of-June-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/Statement-of-Cash-Flows-as-of-June-30-2026.xlsx"),
        ("Unliquidated cash advances", "Unliquidated-Cash-advance-as-of-June-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/Unliquidated-Cash-advance-as-of-June-302026.xlsx"),
        ("Statement of indebtedness", "template-statement-of-indebtedness2ndQUARTER2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/template-statement-of-indebtedness2ndQUARTER2026.xlsx"),
        ("SEF utilization", "SEF-utilization-as-of-June-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/SEF-utilization-as-of-June-30-2026.xlsx"),
        ("Manpower complement", "manpower-complement-2nd-quarter-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/manpower-complement-2nd-quarter-2026.xlsx"),
        ("Bid results", "FDP-DILG-Compliance-2nd-Quarter-2026-CivilGoods-and-Consulting-Services.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/FDP-DILG-Compliance-2nd-Quarter-2026-CivilGoods-and-Consulting-Services.xlsx"),
        ("Statement of receipts and expenditures", "template-sre-2ndTQ2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/07/template-sre-2ndTQ2026.xlsx"),
    ],
    "q3": [
        ("20% NTA development fund utilization", "20NTAutilizationnewformat2026-Q3.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/20NTAutilizationnewformat2026.xlsx"),
        ("LDRRMF utilization", "LDRRMF-Utilization-as-of-September-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/LDRRMF-Utilization-as-of-September-30-2026.xlsx"),
        ("Trust fund utilization", "Trust-Fund-Utilization-as-of-September-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/Trust-Fund-Utilization-as-of-September-30-2026-F.xlsx"),
        ("Statement of cash flows", "Statement-of-Cash-Flows-as-of-September-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/Statement-of-Cash-Flows-as-of-September-30-2026.xlsx"),
        ("Unliquidated advances and fund transfers", "Unliquidated-Cash-advance-Fund-transfers-as-of-September-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/Unliquidated-Cash-advance-Fund-transfers-as-of-September-30-2026.xlsx"),
        ("Statement of indebtedness", "template-statement-of-indebtedness3RDQUARTER2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/template-statement-of-indebtedness3RDQUARTER2026.xlsx"),
        ("SEF utilization", "SEF-utilization-as-of-September-30-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/SEF-utilization-as-of-September-30-2026.xlsx"),
        ("Manpower complement", "manpower-complement-3rd-quarter-2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/manpower-complement-3rd-quarter-2026.xlsx"),
        ("Bid results", "FDP-DILG-Compliance-3rd-Quarter-2026-CivilGoods-and-Consulting-Services.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/FDP-DILG-Compliance-3rd-Quarter-2026-CivilGoods-and-Consulting-Services.xlsx"),
        ("Statement of receipts and expenditures", "template-sre-3rdQ2026.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/template-sre-3rdQ2026.xlsx"),
        ("Consolidated project and program progress", "consolidated-report-3rd-qtr-2026-1.xlsx", "https://www.miagao.gov.ph/wp-content/uploads/2026/10/consolidated-report-3rd-qtr-2026-1.xlsx"),
    ],
}


def excel_col_name(index: int) -> str:
    value = index + 1
    letters = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def quarterly_rows(path: Path, quarter: str, document_type: str, source_url: str) -> tuple[list[dict], list[dict]]:
    """Extract rows from sheets marked for the selected 2026 quarter.

    Sheet names and header cells are both checked because several municipal
    workbooks bundle prior-year forms alongside the current quarterly sheet.
    """
    quarter_number = {"q1": "1", "q2": "2", "q3": "3"}[quarter]
    quarter_word = {"q1": r"(?:1st|first)", "q2": r"(?:2nd|second)", "q3": r"(?:3rd|third)"}[quarter]
    sheets = parse_xlsx(path)
    selected = []
    for sheet_name, rows in sheets.items():
        if "license" in sheet_name.lower() or not rows:
            continue
        opening = " ".join([sheet_name] + [str(value) for row in rows[:12] for value in row["cells"].values()]).lower()
        explicit_quarter = bool(re.search(rf"\b{quarter_word}\b|\bq{quarter_number}\b|quarter\s*[:/]?\s*{quarter_number}\b", opening))
        year_2026 = "2026" in opening
        if not (explicit_quarter and year_2026):
            continue
        selected.append((sheet_name, rows))
    extracted = []
    sheet_summaries = []
    for sheet_name, rows in selected:
        sheet_summaries.append({"name": sheet_name, "sourceRows": len(rows)})
        for row in rows:
            values = {excel_col_name(index): value for index, value in row["cells"].items()}
            if not values:
                continue
            extracted.append({
                "documentType": document_type,
                "worksheet": sheet_name,
                "sourceRow": row["row"],
                "values": values,
                "searchText": " ".join(values.values()),
                "sourceUrl": source_url,
            })
    return extracted, sheet_summaries


def col_num(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref).group(0)
    value = 0
    for c in letters:
        value = value * 26 + ord(c) - 64
    return value - 1


def parse_xlsx(path: Path) -> dict[str, list[dict]]:
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        shared: list[str] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in root.findall("m:si", NS)]
        out = {}
        for sh in wb.findall("m:sheets/m:sheet", NS):
            target = targets[sh.attrib[f"{{{NS['r']}}}id"]].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            root = ET.fromstring(z.read(target))
            rows = []
            for row in root.findall(".//m:sheetData/m:row", NS):
                cells = {}
                for cell in row.findall("m:c", NS):
                    value = cell.find("m:v", NS)
                    text = value.text if value is not None else ""
                    if cell.attrib.get("t") == "s" and text:
                        text = shared[int(text)]
                    elif cell.attrib.get("t") == "inlineStr":
                        text = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
                    if str(text).strip():
                        cells[col_num(cell.attrib["r"])] = str(text).strip()
                if cells:
                    rows.append({"row": int(row.attrib["r"]), "cells": cells})
            out[sh.attrib["name"]] = rows
        return out


def clean_text(markup: str) -> str:
    class Text(HTMLParser):
        def __init__(self):
            super().__init__(); self.parts = []
        def handle_data(self, data):
            if data.strip(): self.parts.append(data.strip())
    parser = Text(); parser.feed(markup)
    return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()


def parse_profile_tables(markup: str) -> list[list[list[str]]]:
    class Tables(HTMLParser):
        def __init__(self):
            super().__init__(); self.tables = []; self.table = None; self.row = None; self.cell = None
        def handle_starttag(self, tag, attrs):
            if tag == "table": self.table = []
            elif self.table is not None and tag == "tr": self.row = []
            elif self.row is not None and tag in {"td", "th"}: self.cell = []
        def handle_data(self, data):
            if self.cell is not None: self.cell.append(data)
        def handle_endtag(self, tag):
            if tag in {"td", "th"} and self.cell is not None:
                self.row.append(re.sub(r"\s+", " ", " ".join(self.cell)).strip()); self.cell = None
            elif tag == "tr" and self.row is not None:
                if any(self.row): self.table.append(self.row)
                self.row = None
            elif tag == "table" and self.table is not None:
                self.tables.append(self.table); self.table = None
    parser = Tables(); parser.feed(markup); return parser.tables


def normalize(value: str) -> str:
    value = value.lower().replace("&amp;", "and")
    value = re.sub(r"\b(brgy|barangay)\.?\s*", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def contains_infra(text: str) -> bool:
    return bool(re.search(r"\b(road|bridge|building|irrigation|drainage|water system|water supply|flood|seawall|shoreline|market|facility|center|hall|terminal|port|school|health center|rehabilitation|construction|improvement)\b", text, re.I))


def excel_date(serial: str) -> str:
    try:
        return (datetime(1899, 12, 30) + timedelta(days=float(serial))).date().isoformat()
    except Exception:
        return serial


def main():
    workbooks = {}
    for key, (filename, url) in FILES.items():
        workbooks[key] = {"sourceUrl": url, "sheets": parse_xlsx(SOURCE / filename)}

    quarterly_disclosure = {}
    for quarter, documents in QUARTERLY_FILES.items():
        quarter_records = []
        quarter_sources = []
        for document_type, filename, url in documents:
            path = SOURCE / filename
            if not path.exists():
                quarter_sources.append({"documentType": document_type, "localFile": filename, "sourceUrl": url, "status": "source workbook not downloaded"})
                continue
            rows, sheets = quarterly_rows(path, quarter, document_type, url)
            quarter_records.extend(rows)
            quarter_sources.append({"documentType": document_type, "localFile": filename, "sourceUrl": url, "status": "parsed" if rows else "no worksheet clearly marked for this quarter", "rowCount": len(rows), "worksheets": sheets})
        quarterly_disclosure[quarter] = {
            "quarter": quarter.upper(),
            "calendarYear": 2026,
            "sourcePage": "https://www.miagao.gov.ph/transparency/2026-full-disclosure/",
            "generatedAt": date.today().isoformat(),
            "sources": quarter_sources,
            "rows": quarter_records,
            "rowCount": len(quarter_records),
            "notes": [
                "Rows are extracted from the worksheets explicitly marked for 2026 and this quarter; worksheet names, source row numbers, and cell coordinates are retained.",
                "Where a workbook's tab label conflicts with the quarter stated inside its form, the original worksheet name is preserved as published.",
                "These workbooks contain different disclosure forms and are not all project-level spending records. Aggregate fund statements are kept distinct from project/procurement rows.",
                "The municipality's Q2 consolidated project-progress page currently links the Q1 workbook; no Q2 project-progress rows are attributed from that mislabeled link.",
            ],
        }

    # The current SRE sheet is aggregate by source/fund and functional
    # expenditure category. Preserve its labeled rows and original row numbers.
    sre_sheet = workbooks["sreQ1"]["sheets"].get("Form 3 - SRE", [])
    sre_rows = []
    for row in sre_sheet:
        if row["row"] < 8:
            continue
        c = row["cells"]
        label = c.get(0) or c.get(1)
        if not label:
            continue
        sre_rows.append({
            "row": row["row"],
            "particulars": label,
            "budgetOrIncomeTarget": c.get(2),
            "generalFund": c.get(3),
            "sef": c.get(4),
            "total": c.get(5),
            "sourceUrl": FILES["sreQ1"][1],
            "sourceSheet": "Form 3 - SRE",
        })

    app_sheet = workbooks["app"]["sheets"].get("Consolidated FINAL APP 2026", [])
    app_lines = []
    current_section = current_office = current_fund = ""
    for row in app_sheet:
        c = row["cells"]
        if 2 in c and 3 in c and not 4 in c:
            current_section, current_office = c[2], c[3]
        elif 2 in c and 3 not in c and 4 not in c and len(c) <= 2:
            current_section = c[2]
        if 3 in c and 2 in c and ("office" in c[3].lower() or "mayor" in c[3].lower() or "municipal" in c[3].lower()):
            current_office = c[3]
        if 11 in c:
            current_fund = c[11]
        title = c.get(4) or c.get(2) or c.get(5)
        if title and row["row"] >= 17:
            line = {
                "row": row["row"], "sectionOrProject": current_section,
                "office": current_office, "description": title,
                "procurementDescription": c.get(5), "mode": c.get(6), "earlyProcurement": c.get(7),
                "procurementStart": c.get(9), "procurementEnd": c.get(10),
                "fund": current_fund, "budgetPesos": c.get(12), "procurementStrategy": c.get(13),
                "remarks": c.get(14), "rawCells": c,
                "sourceUrl": FILES["app"][1], "sourceSheet": "Consolidated FINAL APP 2026",
            }
            app_lines.append(line)

    bid_records = []
    bid_sheet_names = ["FORM 10a - CW", "FORM 10b - GS", "FORM 10c - CS"]
    for sheet_name in bid_sheet_names:
        rows = workbooks["bidResultsQ1"]["sheets"].get(sheet_name, [])
        if not rows: continue
        header_row = next((r["row"] for r in rows if any("Reference" in v for v in r["cells"].values())), None)
        headers = {}
        for row in rows:
            if row["row"] == header_row:
                headers = row["cells"]; break
        for row in rows:
            c = row["cells"]
            if row["row"] <= (header_row or 0): continue
            if not any(v.strip() for v in c.values()): continue
            title = c.get(2) if sheet_name != "FORM 10b - GS" else c.get(1)
            # Only numbered/identified project rows; omit attestations and blanks.
            reference = c.get(1) if sheet_name != "FORM 10b - GS" else c.get(0)
            if not title or not reference or not re.search(r"\d", reference): continue
            bid_records.append({
                "form": sheet_name, "reference": reference, "title": title,
                "approvedBudgetPesos": c.get(3) if sheet_name == "FORM 10a - CW" else (c.get(2) if sheet_name == "FORM 10b - GS" else c.get(4)),
                "location": c.get(4) if sheet_name == "FORM 10a - CW" else ("Miagao, Iloilo" if sheet_name == "FORM 10b - GS" else c.get(3)),
                "winningBidder": c.get(5) if sheet_name == "FORM 10a - CW" else (c.get(3) if sheet_name == "FORM 10b - GS" else c.get(5)),
                "bidAmountPesos": c.get(7) if sheet_name == "FORM 10a - CW" else (c.get(5) if sheet_name == "FORM 10b - GS" else c.get(7)),
                "bidDateExcelSerial": c.get(8) if sheet_name == "FORM 10a - CW" else (c.get(6) if sheet_name == "FORM 10b - GS" else c.get(8)),
                "duration": c.get(9) if sheet_name == "FORM 10a - CW" else c.get(9),
                "row": row["row"], "rawCells": c, "sourceUrl": FILES["bidResultsQ1"][1],
            })

    crosswalk = []
    for bid in bid_records:
        bt = normalize(bid["title"])
        b_words = set(bt.split())
        candidates = []
        for app in app_lines:
            at = normalize(app["description"])
            if not at or not contains_infra(app["description"]): continue
            a_words = set(at.split())
            overlap = len(b_words & a_words) / max(1, len(b_words | a_words))
            # Preserve only meaningful candidates. Name similarity is a lead,
            # never a final identity decision.
            if overlap >= 0.22:
                candidates.append((overlap, app))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        crosswalk.append({
            "bidReference": bid["reference"], "bidTitle": bid["title"],
            "appCandidates": [{"score": round(score, 3), "row": app["row"], "title": app["description"], "budgetPesos": app["budgetPesos"], "office": app["office"], "sourceUrl": app["sourceUrl"]} for score, app in candidates[:5]],
            "matchStatus": "review candidates" if candidates else "no current APP title candidate",
            "note": "Normalized name similarity; human confirmation required. Barangay/location and reference IDs should be checked before merging.",
        })

    # Department-level COA Annex B progress reports. Their layout is mostly
    # consistent but headers and office labels vary, so preserve each source
    # row alongside extracted columns. Old-year duplicate tabs are excluded.
    progress_rows = []
    for sheet_name, rows in workbooks["consolidatedProgressQ1"]["sheets"].items():
        top = " ".join(str(v) for r in rows[:7] for v in r["cells"].values()).lower()
        if "2026" not in top:
            continue
        header = next((r for r in rows if any("PROJECT" in v.upper() and ("PROGRAM" in v.upper() or "ACTIVIT" in v.upper()) for v in r["cells"].values()) and any("TOTAL COST" in v.upper() for v in r["cells"].values())), None)
        if not header: continue
        cols = header["cells"]
        name_col = next((i for i, v in cols.items() if "PROJECT/PROGRAM" in v.upper()), None)
        office_col = next((i for i, v in cols.items() if "IMPLEMENTING OFFICE" in v.upper()), None)
        location_col = next((i for i, v in cols.items() if v.strip().upper() == "LOCATION"), None)
        cost_col = next((i for i, v in cols.items() if v.strip().upper() == "TOTAL COST"), None)
        if name_col is None or cost_col is None: continue
        percent_col = next((i for r in rows if r["row"] in (header["row"], header["row"] + 1) for i, v in r["cells"].items() if "% COMPLETION" in v.upper()), None)
        incurred_col = next((i for r in rows if r["row"] in (header["row"], header["row"] + 1) for i, v in r["cells"].items() if "COST INCUR" in v.upper()), None)
        target_col = next((i for i, v in cols.items() if "TARGET COMPLETION" in v.upper()), None)
        remarks_col = next((i for i, v in cols.items() if v.strip().upper() == "REMARKS"), None)
        date_col = next((i for i, v in cols.items() if v.strip().upper() == "DATE STARTED"), None)
        office = ""
        for row in rows:
            if row["row"] <= header["row"] + 1: continue
            c = row["cells"]
            if office_col in c and c[office_col] and c[office_col].strip().upper() not in {"TOTAL", "PREPARED BY", "APPROVED"}:
                office = c[office_col]
            title = c.get(name_col, "").strip()
            if not title or title.upper() == "TOTAL" or "PREPARED BY" in title.upper() or "APPROVED" in title.upper(): continue
            if cost_col not in c and location_col not in c: continue
            progress_rows.append({
                "departmentSheet": sheet_name, "row": row["row"], "office": office,
                "title": title, "location": c.get(location_col), "totalCostRaw": c.get(cost_col),
                "dateStarted": c.get(date_col), "targetCompletion": c.get(target_col),
                "percentCompleteRaw": c.get(percent_col), "costIncurredToDateRaw": c.get(incurred_col),
                "remarks": c.get(remarks_col), "rawCells": c,
                "sourceUrl": FILES["consolidatedProgressQ1"][1],
                "evidenceType": "Quarterly project/program implementation report",
            })

    profiles_file = SOURCE / "barangay-profiles-api.json"
    profile_records = []
    if profiles_file.exists():
        for p in json.loads(profiles_file.read_text()):
            markup = p.get("content", {}).get("rendered", "")
            profile_records.append({
                "title": clean_text(p.get("title", {}).get("rendered", "")),
                "publishedAt": p.get("date"), "sourceUrl": p.get("link"),
                "contentText": clean_text(markup), "tables": parse_profile_tables(markup),
                "historicalNote": "Municipal profile page published in 2018; officeholders and population/facility details are historical, not current.",
            })

    # The 2024 post announces the elected roster but its eight linked images
    # are event photographs, not legible/name-labelled roster sheets.
    roster = {
        "sourceUrl": "https://www.miagao.gov.ph/about-miagao/news/know-your-barangay-officials/",
        "publishedAt": "2024-01-02", "announcedBarangays": 119,
        "parseStatus": "Images inspected; they show the oath-taking event and do not provide a text-readable 119-barangay name roster.",
        "individualNamesExtracted": 0,
        "imageUrls": [
            f"https://www.miagao.gov.ph/wp-content/uploads/2024/01/{name}"
            for name in [
                "410294150_796055329233230_6944362724581073532_n.jpg",
                "411640546_796055082566588_1373370632836083770_n.jpg",
                "410293030_795965665908863_8808091344534073811_n-1.jpg",
                "411716337_795966225908807_6614339599203439162_n-1.jpg",
                "410270427_796055089233254_817081197316830370_n.jpg",
                "411640546_796055082566588_1373370632836083770_n-1.jpg",
                "411666316_796054982566598_807070936692741607_n.jpg",
                "410294646_796000672572029_6632849601322675071_n.jpg",
            ]
        ],
        "councilRosterStatus": "Historical image/event evidence only; no claim that these are present-day barangay captains.",
    }

    summary = {
        "budgetSheets": {s: len(rows) for s, rows in workbooks["budget"]["sheets"].items()},
        "appRows": len(app_lines),
        "infrastructureAppRows": sum(contains_infra(x["description"]) for x in app_lines),
        "bidResultsQ1Rows": len(bid_records),
        "sreQ1Rows": len(sre_rows),
        "bidResultsByForm": {s: sum(x["form"] == s for x in bid_records) for s in bid_sheet_names},
        "sreQ1Sheets": {s: len(rows) for s, rows in workbooks["sreQ1"]["sheets"].items()},
        "consolidatedProgressQ1Sheets": sorted({x["departmentSheet"] for x in progress_rows}),
        "consolidatedProgressQ1Rows": len(progress_rows),
        "officialBarangayProfilePages": len(profile_records),
        "2024RosterImageCount": len(roster["imageUrls"]),
        "budgetIsProjectLevel": False,
        "sreIsProjectLevel": False,
        "fullDisclosureQ2FilesParsed": sum(source["status"] == "parsed" for source in quarterly_disclosure["q2"]["sources"]),
        "fullDisclosureQ2Rows": quarterly_disclosure["q2"]["rowCount"],
        "fullDisclosureQ3FilesParsed": sum(source["status"] == "parsed" for source in quarterly_disclosure["q3"]["sources"]),
        "fullDisclosureQ3Rows": quarterly_disclosure["q3"]["rowCount"],
    }
    budget_summary_rows = workbooks["budget"]["sheets"].get("Summary2026", [])
    budget_totals = next((r["cells"] for r in budget_summary_rows if r["cells"].get(0, "").strip().upper() == "TOTAL APPROPRIATIONS"), {})
    office_budget_rows = []
    for row in budget_summary_rows:
        c = row["cells"]
        if 0 in c and 8 in c and row["row"] >= 10 and not c[0].upper().startswith("TOTAL"):
            office_budget_rows.append({"officeOrGroup": c[0], "personalServices": c.get(5), "mooe": c.get(6), "capitalOutlay": c.get(7), "totalPesos": c.get(8), "sourceRow": row["row"]})

    # Lean UI asset: raw sheet content remains in the full archive above, while
    # this one is suitable for a client-side search/export interface.
    tracking_cases = []
    for bid in bid_records:
        title_words = set(normalize(bid["title"]).split())
        candidates = []
        for kind, source_rows in (("APP", app_lines), ("Q1 progress", progress_rows)):
            ranked = []
            for item in source_rows:
                text = item.get("description", "") if kind == "APP" else item.get("title", "")
                words = set(normalize(text).split())
                if not words or not title_words: continue
                score = len(words & title_words) / len(words | title_words)
                if len(words & title_words) >= 3 and score >= 0.25:
                    ranked.append((score, item))
            ranked.sort(key=lambda pair: pair[0], reverse=True)
            for score, item in ranked[:3]:
                candidates.append({"sourceType": kind, "score": round(score, 3), "row": item.get("row"), "title": item.get("description") or item.get("title"), "office": item.get("office") or item.get("departmentSheet"), "location": item.get("location"), "sourceUrl": item.get("sourceUrl")})
        tracking_cases.append({
            "projectTitle": bid["title"], "location": bid.get("location"), "barangay": None,
            "budgetEntry": "No project-level 2026 budget schedule available in the published annual budget workbook; it is account/office-level.",
            "procurementPlan": "candidate only" if any(c["sourceType"] == "APP" for c in candidates) else "no title candidate in APP rows",
            "bidResult": bid,
            "reportedQ1ProgressOrCostIncurred": "candidate only" if any(c["sourceType"] == "Q1 progress" for c in candidates) else "no title candidate in Q1 report rows",
            "reviewCandidates": candidates,
            "matchCaution": "Title similarity is a lead, not a confirmed record identity. Confirm barangay, reference number and scope before linking.",
        })

    compact_app = [{k: v for k, v in item.items() if k != "rawCells"} for item in app_lines]
    compact_progress = [{k: v for k, v in item.items() if k != "rawCells"} for item in progress_rows]
    public_asset = {
        "title": "Miagao FY2026 budget and project tracking records",
        "generatedAt": date.today().isoformat(),
        "sourceLinks": {k: url for k, (_, url) in FILES.items()},
        "annualBudget": {
            "totalAppropriationsPesos": budget_totals.get(8),
            "officeAndGroupAppropriations": office_budget_rows,
            "scopeNote": "Office/account-level appropriation totals; the workbook does not identify a 2026 amount for every project title.",
        },
        "appRows": compact_app,
        "appRowCount": len(compact_app),
        "bidResultsQ1": bid_records,
        "sreQ1Rows": sre_rows,
        "q1ProgressRows": compact_progress,
        "q1ProgressRowCount": len(compact_progress),
        "projectTrackingCases": tracking_cases,
        "financialStatementNote": "Q1 Statement of Receipts and Expenditures is aggregated by fund/account and cannot be linked to individual project titles. The separate COA progress report contains department-level program rows with reported cost incurred to date, but it is not a complete transaction-level expenditure ledger.",
        "barangayProfiles2018": [{"title": p["title"], "publishedAt": p["publishedAt"], "sourceUrl": p["sourceUrl"], "contentText": p["contentText"], "tables": p["tables"], "historicalNote": p["historicalNote"]} for p in profile_records],
        "barangayRoster2024": roster,
        "fullDisclosureQ2": quarterly_disclosure["q2"],
        "fullDisclosureQ3": quarterly_disclosure["q3"],
    }
    result = {
        "title": "Miagao official budget, procurement, bid and expenditure records · FY2026",
        "generatedAt": date.today().isoformat(),
        "summary": summary,
        "scopeAndCautions": [
            "The 2026 annual budget workbook is an approved budget by account/office, not a per-project infrastructure schedule.",
            "The Q1 Statement of Receipts and Expenditures is aggregate by fund and account. It does not identify individual project spending; no project-level expenditure matches are inferred.",
            "APP ↔ bid result links are normalized-title review candidates, not confirmed procurement matches. The complete source row and location should be checked.",
            "The 2024 municipal post says it covers 119 barangays, but its linked media are event photos, not an individually named roster. Do not infer captain identities from these photos.",
            "The eleven municipal barangay profile pages currently exposed by the official site are dated 2018. Names, population, facilities and proposed priorities from those profiles are historical, not current.",
        ],
        "sources": {k: {"url": url, "localFile": filename} for k, (filename, url) in FILES.items()},
        "rawWorkbooks": workbooks,
        "appLines": app_lines,
        "bidResultsQ1": bid_records,
        "appBidCrosswalkCandidates": crosswalk,
        "projectProgressQ1": progress_rows,
        "barangayProfiles2018": profile_records,
        "barangayRoster2024": roster,
        "fullDisclosureQ2": quarterly_disclosure["q2"],
        "fullDisclosureQ3": quarterly_disclosure["q3"],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    PUBLIC_OUT.write_text(json.dumps(public_asset, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    APP_SHARD_DIR = PUBLIC_DIR / "budget-app"
    APP_SHARD_DIR.mkdir(parents=True, exist_ok=True)
    shards = {
        "q1-execution.json": {"bidResultsQ1": bid_records, "sreQ1Rows": sre_rows, "q1ProgressRows": compact_progress, "q1ProgressRowCount": len(compact_progress), "projectTrackingCases": tracking_cases, "financialStatementNote": public_asset["financialStatementNote"]},
        "barangay-history.json": {"barangayProfiles2018": public_asset["barangayProfiles2018"], "barangayRoster2024": roster},
        "full-disclosure-q2.json": quarterly_disclosure["q2"],
        "full-disclosure-q3.json": quarterly_disclosure["q3"],
    }
    app_shards = []
    for start in range(0, len(compact_app), 500):
        name = f"rows-{start // 500 + 1:03d}.json"
        (APP_SHARD_DIR / name).write_text(json.dumps({"rows": compact_app[start:start + 500]}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        app_shards.append({"url": f"/data/miagao-disclosure/budget-app/{name}", "rows": min(500, len(compact_app) - start)})
    app_manifest = {"annualBudget": public_asset["annualBudget"], "appRowCount": len(compact_app), "appRowShards": app_shards, "sourceUrl": FILES["app"][1]}
    (APP_SHARD_DIR / "manifest.json").write_text(json.dumps(app_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {"title": public_asset["title"], "generatedAt": public_asset["generatedAt"], "sourceLinks": public_asset["sourceLinks"], "summary": summary, "files": {name: {"url": f"/data/miagao-disclosure/{name}", "rows": len(value.get("rows", value.get("q1ProgressRows", value.get("bidResultsQ1", value.get("barangayProfiles2018", [])))))} for name, value in shards.items()}, "appRows": {"manifestUrl": "/data/miagao-disclosure/budget-app/manifest.json", "rows": len(compact_app), "shards": len(app_shards)}}
    for name, payload in shards.items():
        (PUBLIC_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    if BETTERMIAGAO_PUBLIC_DIR.parent.exists():
        BETTERMIAGAO_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
        for name in ("full-disclosure-q2.json", "full-disclosure-q3.json"):
            shutil.copy2(PUBLIC_DIR / name, BETTERMIAGAO_PUBLIC_DIR / name)
    (PUBLIC_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT}")
    print(f"Wrote public dataset {PUBLIC_OUT}")
    print(f"Wrote lazy-loaded disclosure assets under {PUBLIC_DIR}")
    if BETTERMIAGAO_PUBLIC_DIR.exists():
        print(f"Copied Q2/Q3 public assets to {BETTERMIAGAO_PUBLIC_DIR}")


if __name__ == "__main__":
    main()
