#!/usr/bin/env python3
"""Build a GAA/HGAB-led MPB tracker with optional DIME and PhilGEPS matches.

The GAA-side MPB set follows the same source scope and category filters as
build_mpb_barangay.py. Optional source matches require identical normalized
titles, keeping the left join conservative and each GAA MPB to one output row.
"""
import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ODV = ROOT.parent / "open-data-visualization"
INTEGRATED = ODV / "static/nep-preview/integrated-project-data.json"
HISTORICAL = ROOT / "data_sources/mpb-historical-2017-2018.json"
GAA_2016_18 = ROOT / "data_sources/gaa-dpwh-project-families-2016-2018.json"
GAA_2019 = ROOT / "data_sources/mpb-historical-2019.json"
HGAB = ROOT / "hb10858_3rd_dpwh_projects.json"
DIME = ODV / "data/parquet/dime_projects.parquet"
PHILGEPS = ODV / "data/parquet/philgeps_contracts.parquet"
OUT = ROOT / "analysis_output/mpb_source_union.parquet"

FIELDS = ["source_dataset", "source_id", "fiscal_year", "stage", "title",
          "amount", "category", "program", "agency", "region", "province",
          "municipality", "barangay", "record_url"]
MPB_CATEGORY = "Multi-purpose building"
HGAB_PAP = "BIP - Multi-Purpose Buildings/ Facilities to support Social Services"


def base_record(source, row, year=None, stage=None, title_key="name", id_key="sourceId"):
    return {
        "source_dataset": source,
        "source_id": row.get(id_key) or row.get("id") or row.get("code") or "",
        "fiscal_year": year if year is not None else row.get("year"),
        "stage": stage if stage is not None else row.get("stage") or "GAA",
        "title": row.get(title_key) or row.get("projectName") or row.get("sourceTitle") or "",
        "amount": row.get("amountPesos"),
        "category": row.get("category") or "",
        "program": row.get("pap3") or "",
        "agency": row.get("office") or "",
        "region": row.get("region") or "",
        "province": row.get("province") or "",
        "municipality": row.get("municipality") or "",
        "barangay": row.get("barangay") or "",
        "record_url": row.get("sourceUrl") or "",
    }


def gaa_mpb_rows():
    # Match build_mpb_barangay.py's historic GAA scope and category selector.
    historical = json.loads(HISTORICAL.read_text(encoding="utf-8"))["records"]
    rows = [base_record("GAA", r) for r in historical
            if int(r.get("year") or 0) in (2017, 2018)
            and r.get("category") == MPB_CATEGORY]
    old = json.loads(GAA_2016_18.read_text(encoding="utf-8"))["records"]
    rows.extend(base_record("GAA", r) for r in old
                if int(r.get("year") or 0) == 2016
                and r.get("category") == MPB_CATEGORY)
    technical_2019 = json.loads(GAA_2019.read_text(encoding="utf-8"))["records"]
    rows.extend(base_record("GAA", r) for r in technical_2019)
    integrated = json.loads(INTEGRATED.read_text(encoding="utf-8"))["projects"]
    rows.extend(base_record("GAA", r) for r in integrated
                if 2020 <= int(r.get("year") or 0) <= 2026
                and r.get("category") == MPB_CATEGORY)
    # Keep the proposal slice in the same base inventory, visibly labelled.
    hgab_data = json.loads(HGAB.read_text(encoding="utf-8"))["data"]["data"]
    rows.extend(base_record("HGAB", r, year=2027, stage="HGAB 3rd")
                for r in hgab_data if r.get("pap3") == HGAB_PAP)
    return rows


def main():
    duckdb = shutil.which("duckdb")
    if not duckdb:
        raise SystemExit("DuckDB CLI is required to read the existing source Parquets")
    if not all(p.exists() for p in (INTEGRATED, HISTORICAL, GAA_2016_18, GAA_2019, HGAB, DIME, PHILGEPS)):
        raise SystemExit("One or more GAA/HGAB, DIME, or PhilGEPS input files are missing")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mpb-source-union-") as tmp:
        gaa_csv = Path(tmp) / "gaa_mpb.csv"
        with gaa_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(gaa_mpb_rows())

        def sql_path(path):
            return str(path).replace("'", "''")

        gaa_path, dime_path, ph_path, out_path = map(sql_path, (gaa_csv, DIME, PHILGEPS, OUT))
        sql = f"""
COPY (
  WITH base AS (
    SELECT *, regexp_replace(lower(coalesce(title, '')), '[^a-z0-9]', '', 'g') title_key
    FROM read_csv_auto('{gaa_path}', all_varchar=true)
  ), dime AS (
    SELECT regexp_replace(lower(coalesce(project_name, '')), '[^a-z0-9]', '', 'g') title_key,
      count(*) match_count,
      string_agg(DISTINCT coalesce(global_id, ''), ' | ') match_ids,
      string_agg(DISTINCT project_name, ' | ') match_titles
    FROM read_parquet('{dime_path}')
    WHERE nullif(project_name, '') IS NOT NULL
    GROUP BY 1
  ), philgeps AS (
    SELECT regexp_replace(lower(coalesce(philgeps_award_title, project_name, project_description, '')), '[^a-z0-9]', '', 'g') title_key,
      count(*) match_count,
      string_agg(DISTINCT coalesce(contract_id, philgeps_reference_id, ''), ' | ') match_ids,
      string_agg(DISTINCT coalesce(philgeps_award_title, project_name, project_description), ' | ') match_titles
    FROM read_parquet('{ph_path}')
    WHERE nullif(coalesce(philgeps_award_title, project_name, project_description), '') IS NOT NULL
    GROUP BY 1
  )
  SELECT base.source_dataset, base.source_id, try_cast(base.fiscal_year AS INTEGER) fiscal_year,
    base.stage, base.title, try_cast(base.amount AS DOUBLE) amount,
    base.category, base.program, base.agency, base.region, base.province,
    base.municipality, base.barangay, base.record_url,
    TRUE is_mpb, 'GAA/HGAB MPB category/PAP source row' mpb_evidence,
    coalesce(dime.match_count, 0) dime_match_count, dime.match_ids dime_ids,
    dime.match_titles dime_titles,
    coalesce(philgeps.match_count, 0) philgeps_match_count,
    philgeps.match_ids philgeps_ids, philgeps.match_titles philgeps_titles
  FROM base
  LEFT JOIN dime USING (title_key)
  LEFT JOIN philgeps USING (title_key)
) TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD);
"""
        subprocess.run([duckdb, "-c", sql], check=True)

    summary_sql = f"""
SELECT source_dataset, fiscal_year, count(*) mpb_rows,
  count(*) FILTER (WHERE dime_match_count > 0) rows_with_dime,
  count(*) FILTER (WHERE philgeps_match_count > 0) rows_with_philgeps
FROM read_parquet('{sql_path(OUT)}')
GROUP BY 1,2 ORDER BY 1,2;
"""
    subprocess.run([duckdb, "-c", summary_sql], check=True)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
