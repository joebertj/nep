#!/usr/bin/env python3
"""Stream the FY2027 NEP workbook into NDJSON and Parquet.

Uses only the Python standard library for XLSX parsing. The workbook's source
columns are retained, with normalized agency, hierarchy, and amount fields
added for cross-document analysis. AMT is preserved in its source unit; the
FY2027 workbook reports amounts in thousand pesos, so amountPesos multiplies
AMT by 1,000.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def col_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group(0)
    result = 0
    for letter in letters:
        result = result * 26 + ord(letter) - 64
    return result - 1


def read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    strings: list[str] = []
    with archive.open("xl/sharedStrings.xml") as source:
        for _, elem in ET.iterparse(source, events=("end",)):
            if elem.tag == f"{{{NS}}}si":
                strings.append("".join(t.text or "" for t in elem.iter(f"{{{NS}}}t")))
                elem.clear()
    return strings


def sheet_path(archive: zipfile.ZipFile, requested: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels}
    for sheet in workbook.find(f"{{{NS}}}sheets"):
        if sheet.attrib["name"] == requested:
            target = targets[sheet.attrib[f"{{{REL_NS}}}id"]]
            if target.startswith("/"):
                return target.lstrip("/")
            return str(PurePosixPath("xl") / target)
    names = [sheet.attrib["name"] for sheet in workbook.find(f"{{{NS}}}sheets")]
    raise ValueError(f"Sheet {requested!r} not found. Available sheets: {names}")


def cell_value(cell: ET.Element, shared: list[str]):
    kind = cell.attrib.get("t", "n")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{NS}}}t"))
    value = cell.find(f"{{{NS}}}v")
    if value is None or value.text is None:
        return None
    raw = value.text
    if kind == "s":
        return shared[int(raw)]
    if kind == "b":
        return raw == "1"
    if kind in ("str", "e"):
        return raw
    try:
        number = float(raw)
        if math.isfinite(number) and number.is_integer():
            return int(number)
        return number
    except ValueError:
        return raw


def amount_value(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return None


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook", nargs="?", type=Path, default=ROOT / "NEP-FY2027.xlsx")
    parser.add_argument("--sheet", default="NEP 2027")
    parser.add_argument("--out-prefix", type=Path, default=ROOT / "nep_fy2027_all")
    parser.add_argument("--duckdb", default="duckdb")
    parser.add_argument("--json-only", action="store_true", help="Skip Parquet creation")
    args = parser.parse_args()
    if not args.workbook.is_file():
        parser.error(f"Workbook not found: {args.workbook}")

    json_path = args.out_prefix.with_suffix(".json")
    parquet_path = args.out_prefix.with_suffix(".parquet")
    summary_path = args.out_prefix.with_name(args.out_prefix.name + "_summary.json")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    records = 0
    amount_records = 0
    amount_by_level: Counter[str] = Counter()
    row_by_level: Counter[str] = Counter()
    agency_rows: Counter[str] = Counter()
    amount_by_agency: Counter[str] = Counter()
    samples: dict[str, list[dict]] = {}

    with zipfile.ZipFile(args.workbook) as archive:
        shared = read_shared_strings(archive)
        path = sheet_path(archive, args.sheet)
        with archive.open(path) as source, json_path.open("w", encoding="utf-8") as output:
            output.write("[\n")
            row_iter = ET.iterparse(source, events=("start", "end"))
            headers: list[str] | None = None
            sheet_data = None
            for event, elem in row_iter:
                if event == "start" and elem.tag == f"{{{NS}}}sheetData":
                    sheet_data = elem
                    continue
                if event != "end":
                    continue
                if elem.tag != f"{{{NS}}}row":
                    continue
                row_num = int(elem.attrib.get("r", "0"))
                cells = {}
                for cell in elem.findall(f"{{{NS}}}c"):
                    value = cell_value(cell, shared)
                    if value is not None and value != "":
                        cells[col_index(cell.attrib["r"])] = value
                if row_num == 1:
                    headers = [str(cells.get(i, "")).strip() for i in range(max(cells) + 1)]
                    if sheet_data is not None:
                        sheet_data.clear()
                    continue
                if not headers:
                    raise ValueError("Header row not found")

                source_key = {
                    "AGENCY": "agencyCode",
                    "DEPARTMENT": "departmentCode",
                }
                record = {source_key.get(headers[index], headers[index]): value
                          for index, value in cells.items()
                          if index < len(headers) and headers[index]}
                level = str(record.get("PREXC_LEVEL", ""))
                agency = str(record.get("UACS_AGY_DSC", ""))
                row_by_level[level] += 1
                if agency:
                    agency_rows[agency] += 1
                amount = amount_value(record.get("AMT"))
                if amount is not None:
                    amount_records += 1
                    amount_by_level[level] += 1
                    if agency:
                        amount_by_agency[agency] += amount
                    record["amount"] = amount
                    record["amountPesos"] = amount * 1000
                    record["amountUnit"] = "thousand pesos"
                    sample = samples.setdefault(level, [])
                    if len(sample) < 4:
                        sample.append({
                            "sourceRow": row_num,
                            "agency": agency,
                            "level": level,
                            "description": record.get("DSC", ""),
                            "expenditure": record.get("UACS_EXP_DSC", ""),
                            "object": record.get("UACS_OBJ_DSC", ""),
                            "amount": amount,
                        })

                record["sourceRow"] = row_num
                record["fiscalYear"] = 2027
                if "UACS_AGY_DSC" in record:
                    record["agency"] = record["UACS_AGY_DSC"]
                if "UACS_DPT_DSC" in record:
                    record["department"] = record["UACS_DPT_DSC"]
                if "DSC" in record:
                    record["projectName"] = record["DSC"]
                if records:
                    output.write(",\n")
                output.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
                records += 1
                if sheet_data is not None:
                    sheet_data.clear()
                if row_num % 50000 == 0:
                    print(f"Parsed through source row {row_num:,}; wrote {records:,} rows", flush=True)
            output.write("\n]\n")

    summary = {
        "sourceFile": args.workbook.name,
        "sourceSheet": args.sheet,
        "records": records,
        "rowsWithAmount": amount_records,
        "amountUnit": "thousand pesos",
        "rowsByPrexcLevel": dict(row_by_level),
        "amountRowsByPrexcLevel": dict(amount_by_level),
        "rowsByAgency": dict(agency_rows),
        "amountByAgencyThousandsPesos": dict(amount_by_agency),
        "amountRowSamplesByPrexcLevel": samples,
        "json": str(json_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not args.json_only:
        cli = shutil.which(args.duckdb)
        if not cli:
            parser.error("DuckDB CLI required for Parquet output")
        sql = (
            f"COPY (SELECT * FROM read_json_auto('{sql_path(json_path)}', "
            f"format='array', sample_size=-1)) "
            f"TO '{sql_path(parquet_path)}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        result = subprocess.run([cli, "-c", sql], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(result.stderr.strip() or result.stdout.strip())
        summary["parquet"] = str(parquet_path)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({
        "records": records,
        "rowsWithAmount": amount_records,
        "json": str(json_path),
        "parquet": None if args.json_only else str(parquet_path),
        "summary": str(summary_path),
        "rowsByPrexcLevel": dict(row_by_level),
        "amountRowsByPrexcLevel": dict(amount_by_level),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
