#!/usr/bin/env python3
"""Wait for the queued POW retry batch, then parse the PCCP price-list PDF."""
import csv
import argparse
import hashlib
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PDF = ROOT / "data_sources/pdf-p-classtruncatedtext-module-lineclamped-85ulhh-style-max-lines5dpwh-estimated-pricelist-for-pccp-per-meter-p_compress.pdf"
POW_LOG = ROOT / "data_sources/gaa_2019_volume_ia/pow_retry_after_ocr.log"
STATUS = ROOT / "data_sources/pccp_price_list_parse_status.json"
OUT = ROOT / "analysis_output/pccp_price_list_parse.json"
CSV = ROOT / "analysis_output/pccp_price_list_rows.csv"
DONE_MARKER = "Cached POW retry batch finished."


def save_status(**values):
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    temp = STATUS.with_suffix(".json.tmp")
    temp.write_text(json.dumps(values, ensure_ascii=False, indent=2) + "\n")
    temp.replace(STATUS)


def source_sha256():
    digest = hashlib.sha256()
    with PDF.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parser_version():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def extract_native_price_tables():
    """Extract the 18 region-split tables from the tall native-text PDF page."""
    import pymupdf

    section_by_table = {
        **{i: "A. Preventive Maintenance" for i in range(0, 3)},
        **{i: "B. Rehabilitation/Reconstruction" for i in range(3, 6)},
        **{i: "C. Road Upgrading" for i in range(6, 9)},
        **{i: "D. Flooded Sections (Raising of Grade and Drainage)" for i in range(9, 12)},
        **{i: "E. Drainage and Slope Protection" for i in range(12, 15)},
        **{i: "New Road Construction" for i in range(15, 18)},
    }
    document = pymupdf.open(PDF)
    records = {}
    table_count = 0
    for page_number, page in enumerate(document, start=1):
        tables = page.find_tables().tables
        table_count += len(tables)
        for table_index, table in enumerate(tables):
            grid = table.extract()
            region_header = None
            region_header_index = None
            for index, row in enumerate(grid):
                labels = [str(value or "").strip() for value in row]
                if sum(bool(re.fullmatch(r"(?:NCR|CAR|AVERAGE|REGION\s+[IVX]+(?:-[A-Z])?)", x, re.I)) for x in labels) >= 3:
                    region_header, region_header_index = labels, index
                    break
            if region_header is None:
                continue
            regions = region_header[2:]
            unit_header = " ".join(str(value or "") for value in grid[0]).upper()
            cost_unit = "linear_meter" if re.search(r"COST\s*/\s*L\.?\s*M\.?", unit_header) else "kilometer"
            surface_type = ""
            assumption = ""
            for row in grid[region_header_index + 1:]:
                surface = re.sub(r"\s+", " ", str(row[0] or "")).strip()
                scope = re.sub(r"\s+", " ", str(row[1] or "")).strip()
                prices = []
                for value in row[2:2 + len(regions)]:
                    text = str(value or "").strip().replace(",", "")
                    try:
                        prices.append(float(text) if text else None)
                    except ValueError:
                        prices.append(None)
                if not scope or not any(value is not None for value in prices):
                    continue
                if surface.startswith("("):
                    assumption = surface.strip("() ")
                elif surface:
                    surface_type = surface
                    assumption = ""
                key = (section_by_table.get(table_index, "Unclassified table"),
                       surface_type, scope, assumption, cost_unit)
                record = records.setdefault(key, {
                    "section": key[0], "surfaceType": surface_type, "scope": scope,
                    "assumption": assumption or None, "unit": cost_unit,
                    "regionalUnitCostsPesos": {}, "sourcePage": page_number,
                    "sourceTables": [],
                    "extractionMethod": "PyMuPDF native table extraction",
                    "verificationStatus": "Machine-extracted candidate; verify the printed table and row assumptions",
                })
                if table_index not in record["sourceTables"]:
                    record["sourceTables"].append(table_index)
                for region, value in zip(regions, prices):
                    region = re.sub(r"\s+", " ", str(region or "")).strip()
                    if value is not None:
                        record["regionalUnitCostsPesos"][region] = value
    document.close()
    rows = list(records.values())
    rows.sort(key=lambda row: (row["section"], row["surfaceType"], row["scope"]))
    return {"status": "native_table_rows_recovered" if rows else "no_bill_rows_recovered",
            "pagesProcessed": 1, "tableCount": table_count, "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--now", action="store_true",
                        help="start the queued price-list parse immediately")
    parser.add_argument("--force", action="store_true",
                        help="reparse even when a result for this PDF hash already exists")
    args = parser.parse_args()
    if not PDF.is_file():
        raise SystemExit(f"Source PDF missing: {PDF}")
    sha = source_sha256()
    version = parser_version()
    if OUT.is_file() and not args.force:
        try:
            prior = json.loads(OUT.read_text())
            if prior.get("sourceSha256") == sha and prior.get("parserVersion") == version:
                save_status(status="complete", sourceSha256=sha, parserVersion=version,
                            result=str(OUT), skipped="same source and parser version already parsed")
                return
        except (OSError, ValueError):
            pass

    save_status(status="waiting_for_pow_retry_batch", sourceSha256=sha, queuedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    if not args.now:
        while not POW_LOG.is_file() or DONE_MARKER not in POW_LOG.read_text(errors="replace"):
            time.sleep(30)

    save_status(status="parsing", sourceSha256=sha, startedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    result = extract_native_price_tables()
    result["sourceFile"] = str(PDF.relative_to(ROOT))
    result["sourceSha256"] = sha
    result["parserVersion"] = version
    result["parsePurpose"] = "Regional DPWH infrastructure cost estimates; source uses unit cost per kilometer or linear meter, as labeled. Rows and assumptions require source-page review."
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix(".json.tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    temp.replace(OUT)

    columns = ("section", "surfaceType", "scope", "assumption", "unit", "region",
               "unitCostPesos", "sourcePage", "extractionMethod", "verificationStatus")
    with CSV.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in result.get("rows", []):
            for region, value in row.get("regionalUnitCostsPesos", {}).items():
                writer.writerow({**row, "region": region, "unitCostPesos": value})
    save_status(status="complete", sourceSha256=sha, parserVersion=version,
                result=str(OUT), rows=len(result.get("rows", [])),
                parserStatus=result.get("status"), completedAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


if __name__ == "__main__":
    main()
