#!/usr/bin/env python3
"""Run a small, reproducible DuckDB analysis suite on NEP/project Parquet files."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:  # Homebrew installs the CLI, which can run the same SQL.
    duckdb = None


ANALYSES = {
    "data_quality": """
        SELECT fiscal_year, count(*) AS records,
               count(*) FILTER (WHERE amount IS NULL) AS missing_amount,
               count(*) FILTER (WHERE amount <= 0) AS nonpositive_amount,
               count(*) FILTER (WHERE project_name IS NULL OR trim(project_name) = '') AS missing_name,
               count(DISTINCT project_name) AS distinct_names,
               count(DISTINCT amount) AS distinct_amounts,
               sum(amount) AS total_amount,
               quantile_cont(amount, 0.5) AS median_amount
        FROM projects GROUP BY fiscal_year ORDER BY fiscal_year
    """,
    "spending_by_year_category_region": """
        SELECT fiscal_year, category, region,
               count(*) AS project_count, sum(amount) AS total_amount,
               avg(amount) AS average_amount, median(amount) AS median_amount
        FROM projects
        WHERE amount IS NOT NULL
        GROUP BY fiscal_year, category, region
        ORDER BY fiscal_year, total_amount DESC
    """,
    "district_allocations": """
        WITH office_totals AS (
          SELECT fiscal_year, office, any_value(region) AS region,
                 count(*) AS project_count, sum(amount) AS total_amount,
                 median(amount) AS median_project_amount,
                 max(amount) AS largest_project_amount,
                 max_by(project_name, amount) AS largest_project_name,
                 count(DISTINCT category) AS categories
          FROM projects
          WHERE amount IS NOT NULL AND office ILIKE '%District Engineering Office%'
          GROUP BY fiscal_year, office
        ), ranked AS (
          SELECT *,
                 sum(total_amount) OVER (PARTITION BY fiscal_year) AS district_total,
                 sum(total_amount) OVER (PARTITION BY fiscal_year ORDER BY total_amount DESC
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_amount,
                 row_number() OVER (PARTITION BY fiscal_year ORDER BY total_amount DESC) AS rank
          FROM office_totals
        )
        SELECT fiscal_year, rank, office, region, project_count, categories,
               total_amount,
               100.0 * total_amount / nullif(district_total, 0) AS district_share_pct,
               100.0 * cumulative_amount / nullif(district_total, 0) AS cumulative_share_pct,
               median_project_amount, largest_project_amount, largest_project_name,
               100.0 * largest_project_amount / nullif(total_amount, 0) AS largest_project_share_pct
        FROM ranked ORDER BY fiscal_year, rank
    """,
    "district_program_allocations": """
        WITH district_records AS (
          SELECT * FROM projects
          WHERE amount IS NOT NULL
            AND office ILIKE '%District Engineering Office%'
            AND category IN (
              'Rainwater Collector System',
              'Water Supply System',
              'Septage and Sewerage',
              'BIP - Multi-Purpose Buildings/ Facilities to support Social Services',
              'BIP - Access Roads and/or Bridges from the National Roads leading to Major/ Strategic Public Buildings/ Facilities',
              'Construction/ Maintenance of Flood Mitigation Structures and Drainage Systems',
              'Construction/ Rehabilitation of Flood Mitigation Facilities within Major River Basins and Principal Rivers'
            )
        ), category_offices AS (
          SELECT fiscal_year, category, office, any_value(region) AS region,
                 count(*) AS project_count, sum(amount) AS total_amount,
                 median(amount) AS median_project_amount,
                 count(DISTINCT amount) AS distinct_prices,
                 max(amount) AS largest_project_amount,
                 max_by(project_name, amount) AS largest_project_name
          FROM district_records
          GROUP BY fiscal_year, category, office
        ), price_counts AS (
          SELECT fiscal_year, category, office, amount, count(*) AS price_count
          FROM district_records
          GROUP BY fiscal_year, category, office, amount
        ), price_modes AS (
          SELECT fiscal_year, category, office,
                 max_by(amount, price_count) AS most_common_amount,
                 max(price_count) AS most_common_amount_count
          FROM price_counts
          GROUP BY fiscal_year, category, office
        ), district_totals AS (
          SELECT fiscal_year, office, sum(amount) AS all_category_total
          FROM projects
          WHERE amount IS NOT NULL AND office ILIKE '%District Engineering Office%'
          GROUP BY fiscal_year, office
        ), ranked AS (
          SELECT co.*,
                 sum(total_amount) OVER (PARTITION BY fiscal_year, category) AS category_total,
                 row_number() OVER (PARTITION BY fiscal_year, category ORDER BY total_amount DESC) AS category_rank,
                 pm.most_common_amount, pm.most_common_amount_count,
                 dt.all_category_total
          FROM category_offices co
          JOIN price_modes pm USING (fiscal_year, category, office)
          JOIN district_totals dt USING (fiscal_year, office)
        )
        SELECT fiscal_year, category_rank, category, office, region, project_count,
               total_amount,
               100.0 * total_amount / nullif(category_total, 0) AS category_share_pct,
               100.0 * total_amount / nullif(all_category_total, 0) AS district_share_pct,
               median_project_amount, distinct_prices,
               most_common_amount, most_common_amount_count,
               100.0 * most_common_amount_count / nullif(project_count, 0) AS most_common_amount_share_pct,
               largest_project_amount, largest_project_name
        FROM ranked
        ORDER BY fiscal_year, category, category_rank
    """,
    "five_million_roads_flood": """
        SELECT fiscal_year, region, office, category, project_name, amount
        FROM projects
        WHERE amount = 5000000
          AND office ILIKE '%District Engineering Office%'
          AND (category = 'BIP - Access Roads and/or Bridges from the National Roads leading to Major/ Strategic Public Buildings/ Facilities'
            OR category IN (
              'Construction/ Maintenance of Flood Mitigation Structures and Drainage Systems',
              'Construction/ Rehabilitation of Flood Mitigation Facilities within Major River Basins and Principal Rivers'
            ))
        ORDER BY fiscal_year, office, category, project_name
    """,
    "inspire_building_allocations": """
        WITH matched AS (
          SELECT * FROM projects
          WHERE amount IS NOT NULL
            AND office ILIKE '%District Engineering Office%'
            AND project_name ILIKE '%INSPIRE%'
        ), office_totals AS (
          SELECT fiscal_year, office, any_value(region) AS region,
                 count(*) AS project_count, sum(amount) AS total_amount,
                 median(amount) AS median_project_amount,
                 count(DISTINCT amount) AS distinct_prices,
                 max(amount) AS largest_project_amount,
                 max_by(project_name, amount) AS largest_project_name
          FROM matched GROUP BY fiscal_year, office
        ), price_counts AS (
          SELECT fiscal_year, office, amount, count(*) AS price_count
          FROM matched GROUP BY fiscal_year, office, amount
        ), price_modes AS (
          SELECT fiscal_year, office,
                 max_by(amount, price_count) AS most_common_amount,
                 max(price_count) AS most_common_amount_count
          FROM price_counts GROUP BY fiscal_year, office
        ), district_totals AS (
          SELECT fiscal_year, office, sum(amount) AS all_category_total
          FROM projects
          WHERE amount IS NOT NULL AND office ILIKE '%District Engineering Office%'
          GROUP BY fiscal_year, office
        ), ranked AS (
          SELECT ot.*, pm.most_common_amount, pm.most_common_amount_count,
                 dt.all_category_total,
                 sum(ot.total_amount) OVER (PARTITION BY ot.fiscal_year) AS category_total,
                 row_number() OVER (PARTITION BY ot.fiscal_year ORDER BY ot.total_amount DESC) AS category_rank
          FROM office_totals ot
          JOIN price_modes pm USING (fiscal_year, office)
          JOIN district_totals dt USING (fiscal_year, office)
        )
        SELECT fiscal_year, category_rank,
               'INSPIRE Building (title match)' AS category,
               office, region, project_count, total_amount,
               100.0 * total_amount / nullif(category_total, 0) AS category_share_pct,
               100.0 * total_amount / nullif(all_category_total, 0) AS district_share_pct,
               median_project_amount, distinct_prices,
               most_common_amount, most_common_amount_count,
               100.0 * most_common_amount_count / nullif(project_count, 0) AS most_common_amount_share_pct,
               largest_project_amount, largest_project_name
        FROM ranked ORDER BY fiscal_year, category_rank
    """,
    "non_road_bridge_top_projects": """
        WITH candidates AS (
          SELECT fiscal_year, region, office, category, project_name, amount,
                 row_number() OVER (PARTITION BY fiscal_year ORDER BY amount DESC) AS rank
          FROM projects
          WHERE amount IS NOT NULL
            AND category NOT ILIKE '%road%'
            AND category NOT ILIKE '%bridge%'
            AND coalesce(project_name, '') NOT ILIKE '%road%'
            AND coalesce(project_name, '') NOT ILIKE '%bridge%'
        )
        SELECT fiscal_year, rank, region, office, category, project_name, amount
        FROM candidates
        WHERE rank <= 25 OR project_name ILIKE '%INSPIRE%'
        ORDER BY fiscal_year, rank
    """,
    "water_sector_watchlist": """
        SELECT fiscal_year, region, office, category, project_name, amount,
               record_id, program_group,
               CASE WHEN program_group ILIKE '%Rain Water Collectors%'
                    THEN 'Shared water-sector PAP2'
                    ELSE 'Water-related title keyword outside shared PAP2' END AS match_basis
        FROM projects
        WHERE office ILIKE '%District Engineering Office%'
          AND (program_group ILIKE '%Rain Water Collectors%'
            OR regexp_matches(lower(coalesce(project_name, '')),
               'rain[[:space:]]*water|water[[:space:]]*collector|rain[[:space:]]*harvest|catchment|cistern|water[[:space:]]*(supply|system|storage)'))
        ORDER BY fiscal_year, category, office, amount DESC
    """,
    "same_name_price_variance": """
        SELECT fiscal_year, normalized_name,
               any_value(project_name) AS example_name,
               category, count(*) AS records,
               count(DISTINCT location) AS locations,
               count(DISTINCT amount) AS distinct_prices,
               min(amount) AS minimum_amount, median(amount) AS median_amount,
               max(amount) AS maximum_amount,
               max(amount) - min(amount) AS price_range,
               (max(amount) - min(amount)) / nullif(avg(amount), 0) AS range_over_mean,
               string_agg(DISTINCT location, ' | ' ORDER BY location) AS locations_seen
        FROM projects
        WHERE normalized_name <> '' AND amount IS NOT NULL
        GROUP BY fiscal_year, normalized_name, category
        HAVING count(DISTINCT location) >= 2 AND count(DISTINCT amount) >= 2
        ORDER BY price_range DESC
    """,
    "same_price_across_locations": """
        SELECT fiscal_year, category, amount,
               count(*) AS records, count(DISTINCT location) AS locations,
               count(DISTINCT normalized_name) AS distinct_project_names,
               string_agg(DISTINCT location, ' | ' ORDER BY location) AS locations_seen,
               string_agg(DISTINCT project_name, ' | ' ORDER BY project_name) AS project_names
        FROM projects
        WHERE amount IS NOT NULL AND category <> ''
        GROUP BY fiscal_year, category, amount
        HAVING count(DISTINCT location) >= 3 AND count(*) >= 3
        ORDER BY locations DESC, records DESC, amount DESC
    """,
    "category_amount_outliers": """
        WITH base AS (
          SELECT * FROM projects WHERE amount IS NOT NULL AND category <> ''
        ), medians AS (
          SELECT fiscal_year, category, count(*) AS category_records,
                 median(amount) AS median_amount,
                 quantile_cont(amount, 0.25) AS q1,
                 quantile_cont(amount, 0.75) AS q3
          FROM base GROUP BY fiscal_year, category
        ), stats AS (
          SELECT b.fiscal_year, b.category, m.category_records, m.median_amount,
                 m.q1, m.q3, median(abs(b.amount - m.median_amount)) AS mad
          FROM base b JOIN medians m USING (fiscal_year, category)
          GROUP BY b.fiscal_year, b.category, m.category_records, m.median_amount, m.q1, m.q3
        ), scored AS (
          SELECT p.*, s.category_records, s.median_amount, s.q1, s.q3, s.mad,
                 CASE WHEN s.mad > 0 THEN abs(p.amount - s.median_amount) / (1.4826 * s.mad)
                      ELSE NULL END AS robust_z,
                 s.q3 - s.q1 AS iqr
          FROM projects p JOIN stats s USING (fiscal_year, category)
        )
        SELECT fiscal_year, category, project_name, location, office, amount,
               category_records, median_amount, q1, q3, iqr, mad, robust_z
        FROM scored
        WHERE category_records >= 8
          AND ((mad > 0 AND abs(amount - median_amount) / (1.4826 * mad) >= 3.5)
            OR (mad = 0 AND (amount < q1 - 3 * iqr OR amount > q3 + 3 * iqr)))
        ORDER BY robust_z DESC NULLS LAST, amount DESC
    """,
    "repeated_prices": """
        SELECT fiscal_year, amount, count(*) AS records,
               count(DISTINCT category) AS categories,
               count(DISTINCT location) AS locations,
               string_agg(DISTINCT category, ' | ' ORDER BY category) AS categories_seen,
               string_agg(DISTINCT location, ' | ' ORDER BY location) AS locations_seen
        FROM projects
        WHERE amount IS NOT NULL
        GROUP BY fiscal_year, amount
        HAVING count(*) >= 5
        ORDER BY records DESC, amount DESC
    """,
}


def quote_path(path: Path) -> str:
    return "'" + str(path.resolve()).replace("'", "''") + "'"


def pick(columns: set[str], names: tuple[str, ...], fallback: str, target: str = "VARCHAR") -> str:
    found = [f'try_cast("{name}" AS {target})' for name in names if name.lower() in columns]
    return "coalesce(" + ", ".join(found + [fallback]) + ")" if found else fallback


def cli_json(cli: str, sql: str):
    result = subprocess.run(
        [cli, "-json", ":memory:", "-c", sql],
        check=True, capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path,
                        help="Parquet files (default: all root-level *.parquet files except generated output)")
    parser.add_argument("--out", type=Path, default=Path("analysis_output"), help="Directory for CSV reports")
    parser.add_argument("--analysis", choices=["all", *ANALYSES], default="all")
    parser.add_argument("--year", type=int, help="Keep records from this fiscal year only")
    parser.add_argument("--amount-scale", type=float, default=1000,
                        help="Multiply source amounts by this value to get pesos (default: 1000; source is in thousand pesos)")
    args = parser.parse_args()

    if args.inputs:
        inputs = args.inputs
    else:
        inputs = sorted(p for p in Path.cwd().glob("*.parquet") if p.name != "analysis_output.parquet")
    inputs = [p for p in inputs if p.is_file()]
    if not inputs:
        raise SystemExit("No Parquet inputs found. Pass one or more file paths, for example: 2027.parquet")

    con = duckdb.connect() if duckdb is not None else None
    cli = None if con is not None else shutil.which("duckdb")
    if con is None and cli is None:
        raise SystemExit(
            "DuckDB was not found. Install the Python package with `python3 -m pip install duckdb` "
            "or install the CLI with `brew install duckdb`."
        )
    paths = ", ".join(quote_path(p) for p in inputs)
    raw_view = f"CREATE VIEW raw AS SELECT * FROM read_parquet([{paths}], union_by_name = true, filename = true)"
    describe = f"DESCRIBE SELECT * FROM read_parquet([{paths}], union_by_name = true, filename = true)"
    if con is not None:
        con.execute(raw_view)
        columns = {row[0].lower() for row in con.execute("DESCRIBE raw").fetchall()}
    else:
        columns = {row["column_name"].lower() for row in cli_json(cli, describe)}

    year_expr = pick(columns, ("fiscalYear", "fiscal_year", "year"),
                     "try_cast(regexp_extract(filename, '20[0-9]{2}', 0) AS INTEGER)", "INTEGER")
    amount_expr = pick(columns, ("amount", "total_amount", "budget_amount", "project_cost", "total_cost"), "NULL::DOUBLE", "DOUBLE")
    name_expr = pick(columns, ("projectName", "project_name", "description", "title", "item_description"), "NULL::VARCHAR")
    region_expr = pick(columns, ("region", "region_name", "region_description"), "NULL::VARCHAR")
    office_expr = pick(columns, ("office", "agency", "agency_description", "operating_unit", "office_name"), "NULL::VARCHAR")
    department_expr = pick(columns, ("department", "department_description", "dept_description"), "NULL::VARCHAR")
    category_expr = pick(columns, ("pap3", "program", "program_name", "pap2", "pap1", "category", "fund_category", "expense_description"), "NULL::VARCHAR")
    program_group_expr = pick(columns, ("pap2", "program_group", "program_category"), "NULL::VARCHAR")
    identity_expr = pick(columns, ("code", "id", "record_id"), "NULL::VARCHAR", "VARCHAR")
    year_filter = f"WHERE try_cast({year_expr} AS INTEGER) = {int(args.year)}" if args.year is not None else ""
    project_view = f"""
        CREATE VIEW projects AS
        SELECT try_cast({identity_expr} AS VARCHAR) AS record_id,
               try_cast({year_expr} AS INTEGER) AS fiscal_year,
               try_cast({name_expr} AS VARCHAR) AS project_name,
               regexp_replace(lower(trim(coalesce(try_cast({name_expr} AS VARCHAR), ''))), '[^a-z0-9]+', ' ', 'g') AS normalized_name,
               try_cast({amount_expr} AS DOUBLE) AS source_amount_thousands,
               try_cast({amount_expr} AS DOUBLE) * {float(args.amount_scale)} AS amount,
               coalesce(nullif(trim(try_cast({region_expr} AS VARCHAR)), ''), 'Unknown') AS region,
               coalesce(nullif(trim(try_cast({office_expr} AS VARCHAR)), ''), 'Unknown') AS office,
               coalesce(nullif(trim(try_cast({department_expr} AS VARCHAR)), ''), 'Unknown') AS department,
               coalesce(nullif(trim(try_cast({category_expr} AS VARCHAR)), ''), 'Unclassified') AS category,
               coalesce(nullif(trim(try_cast({program_group_expr} AS VARCHAR)), ''), 'Unclassified') AS program_group,
               coalesce(nullif(trim(try_cast({office_expr} AS VARCHAR)), ''),
                        nullif(trim(try_cast({region_expr} AS VARCHAR)), ''), 'Unknown') AS location
        FROM raw {year_filter}
    """

    args.out.mkdir(parents=True, exist_ok=True)
    selected = ANALYSES if args.analysis == "all" else {args.analysis: ANALYSES[args.analysis]}
    if con is None:
        sql = raw_view + ";\n" + project_view + ";\n"
        for name, query in selected.items():
            destination = (args.out / f"{name}.csv").resolve()
            sql += f"COPY ({query}) TO {quote_path(destination)} (HEADER, DELIMITER ',');\n"
        subprocess.run([cli, "-bail", ":memory:"], input=sql, check=True, text=True, capture_output=True)
    for name, query in selected.items():
        destination = (args.out / f"{name}.csv").resolve()
        if con is not None:
            con.execute(f"COPY ({query}) TO {quote_path(destination)} (HEADER, DELIMITER ',')")
            count = con.execute(f"SELECT count(*) FROM read_csv_auto({quote_path(destination)})").fetchone()[0]
        else:
            count = cli_json(cli, f"SELECT count(*) AS row_count FROM read_csv_auto({quote_path(destination)})")[0]["row_count"]
        print(f"{name}: {count:,} rows -> {destination}")
    print(f"Inputs: {', '.join(str(p) for p in inputs)}")
    print(f"Amounts were multiplied by {args.amount_scale:g} to convert source values to pesos; confirm input units match this scale.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
