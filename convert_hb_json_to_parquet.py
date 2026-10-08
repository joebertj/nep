#!/usr/bin/env python3
"""Convert an HB candidate JSON's data.data records to Parquet with DuckDB."""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sql_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json", nargs="?", type=Path, default=ROOT / "hb10858_agency_projects.json")
    parser.add_argument("--out", type=Path, help="Parquet output (default: same basename)")
    parser.add_argument("--duckdb", default="duckdb", help="DuckDB executable")
    args = parser.parse_args()
    cli = shutil.which(args.duckdb)
    if not cli:
        parser.error("DuckDB CLI required. Install with: brew install duckdb")
    payload = json.loads(args.json.read_text(encoding="utf-8"))
    records = payload.get("data", {}).get("data", [])
    if not records:
        parser.error(f"No data.data records found in {args.json}")
    for row in records:
        row.setdefault("agency", "")
        row.setdefault("program", "")
        row.setdefault("screeningFlags", [])
        row.setdefault("reviewNotes", [])
        # Keep empty arrays typed as VARCHAR[] in every agency file so DuckDB
        # can union independently converted Parquets without list-type clashes.
        if not row["screeningFlags"]:
            row["screeningFlags"] = [""]
        if not row["reviewNotes"]:
            row["reviewNotes"] = [""]
    out = args.out or args.json.with_suffix(".parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hb-json-") as temp:
        ndjson = Path(temp) / "records.ndjson"
        ndjson.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
        sql = f"COPY (SELECT * REPLACE (list_filter(screeningFlags, x -> x <> '') AS screeningFlags, list_filter(reviewNotes, x -> x <> '') AS reviewNotes) FROM read_json_auto('{sql_path(ndjson)}')) TO '{sql_path(out)}' (FORMAT PARQUET, COMPRESSION ZSTD)"
        result = subprocess.run([cli, "-c", sql], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit(result.stderr.strip() or result.stdout.strip())
    print(f"Wrote {len(records):,} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
