#!/usr/bin/env python3
"""Index structured data files across the NEP and ODV workspaces.

PDF and spreadsheet files are intentionally excluded because they require
document parsing before their contents can be indexed meaningfully.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOTS = {
    "nep": Path("/Users/joebertj/nep"),
    "odv": Path("/Users/joebertj/open-data-visualization"),
}
OUTPUT = ROOTS["nep"] / "analysis_output" / "data-file-index.csv"
SCRIPT = Path(__file__).resolve()
EXCLUDED_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "target", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
}
EXTENSIONS = {
    ".csv": "CSV", ".tsv": "TSV", ".json": "JSON", ".jsonl": "JSON Lines",
    ".ndjson": "NDJSON", ".parquet": "Parquet", ".sqlite": "SQLite",
    ".sqlite3": "SQLite", ".db": "Database", ".duckdb": "DuckDB",
    ".xml": "XML", ".geojson": "GeoJSON", ".yaml": "YAML", ".yml": "YAML",
    ".sql": "SQL", ".feather": "Feather", ".arrow": "Arrow",
}
MAX_PARSE_BYTES = 50 * 1024 * 1024
DUCKDB = shutil.which("duckdb") or "/opt/homebrew/bin/duckdb"
HEADERLESS_CSV_COLUMNS = {
    "data_sources/gaa_2015_dpwh_technical/dpwh.csv": [
        "agencyCode", "agencyName", "officeCode", "officeName", "papCode",
        "papDescription", "implementingUnitCode", "implementingOffice",
        "regionCode", "fundSourceCode", "fundSourceDescription",
        "allotmentClassCode", "allotmentClassDescription", "objectAccountCode",
        "objectAccountDescription", "amountThousandPesos",
    ],
}


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def source_hint(path: Path, payload=None) -> str:
    if isinstance(payload, dict):
        for key in ("source", "origin", "url", "source_url", "description", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip().replace("\n", " ")[:240]
    return str(path.parent).replace(str(path.anchor), "")[:240]


def inspect_json(path: Path, extension: str):
    size = path.stat().st_size
    if size > MAX_PARSE_BYTES:
        return "", "", "", "Skipped content scan (>50 MB)"
    try:
        if extension in {".jsonl", ".ndjson"}:
            with path.open("r", encoding="utf-8-sig", errors="replace") as f:
                count = sum(1 for line in f if line.strip())
            return count, "JSON Lines", "", ""
        with path.open("r", encoding="utf-8-sig") as f:
            obj = json.load(f)
        if isinstance(obj, dict):
            fields = list(obj.keys())
            arrays = [f"{k}[{len(v)}]" for k, v in obj.items() if isinstance(v, list)]
            count = sum(len(v) for v in obj.values() if isinstance(v, list))
            structure = "object"
            field_note = "; ".join(arrays[:12])
        elif isinstance(obj, list):
            count = len(obj)
            structure = "array"
            first = obj[0] if obj else None
            fields = list(first.keys()) if isinstance(first, dict) else []
            field_note = ""
        else:
            count, structure, fields, field_note = 1, type(obj).__name__, [], ""
        return count, structure, "; ".join(fields[:40]), field_note
    except Exception as exc:
        return "", "", "", f"Content scan failed: {type(exc).__name__}"


def inspect_csv(path: Path, delimiter: str):
    try:
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            header = next(reader, [])
            count = sum(1 for row in reader if row)
        return count, "tabular", "; ".join(header[:80]), ""
    except Exception as exc:
        return "", "", "", f"Content scan failed: {type(exc).__name__}"


def decode_json_results(text: str):
    decoder = json.JSONDecoder()
    values, position = [], 0
    while position < len(text):
        while position < len(text) and text[position].isspace():
            position += 1
        if position >= len(text):
            break
        value, position = decoder.raw_decode(text, position)
        values.append(value)
    return values


def inspect_parquet(path: Path):
    try:
        p = str(path).replace("'", "''")
        query = f"DESCRIBE SELECT * FROM read_parquet('{p}'); SELECT COUNT(*) AS row_count FROM read_parquet('{p}');"
        result = subprocess.run(
            [DUCKDB, "-json", "-no-stdin", "-c", query],
            capture_output=True, text=True, timeout=60, check=True,
        )
        # DuckDB emits one JSON array per query, often formatted across lines.
        arrays = decode_json_results(result.stdout)
        description = arrays[0] if arrays else []
        count_rows = arrays[-1] if arrays else []
        columns = "; ".join(f"{row['column_name']} ({row['column_type']})" for row in description[:80])
        count = count_rows[0].get("row_count", "") if count_rows else ""
        return count, "tabular", columns, ""
    except Exception as exc:
        return "", "", "", f"Parquet metadata unavailable: {type(exc).__name__}"


def inspect_sqlite(path: Path):
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            tables = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
            details = []
            total = 0
            for (table,) in tables:
                columns = connection.execute(f'PRAGMA table_info("{table.replace(chr(34), chr(34)*2)}")').fetchall()
                count = connection.execute(f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34)*2)}"').fetchone()[0]
                total += count
                details.append(f"{table}[{count}]: " + ", ".join(c[1] for c in columns[:50]))
        return total, "database", "; ".join(details[:40]), ""
    except Exception as exc:
        return "", "", "", f"SQLite metadata unavailable: {type(exc).__name__}"


def inspect_duckdb(path: Path):
    try:
        result = subprocess.run(
            [DUCKDB, "-readonly", "-json", str(path), "-c", "SHOW TABLES;"],
            capture_output=True, text=True, timeout=60, check=True,
        )
        table_rows = decode_json_results(result.stdout)
        tables = [row.get("name") for row in (table_rows[0] if table_rows else []) if row.get("name")]
        details, total = [], 0
        for table in tables:
            escaped = table.replace('"', '""')
            query = f'DESCRIBE "{escaped}"; SELECT COUNT(*) AS row_count FROM "{escaped}";'
            result = subprocess.run(
                [DUCKDB, "-readonly", "-json", str(path), "-c", query],
                capture_output=True, text=True, timeout=60, check=True,
            )
            arrays = decode_json_results(result.stdout)
            description = arrays[0] if arrays else []
            count_rows = arrays[-1] if arrays else []
            count = count_rows[0].get("row_count", 0) if count_rows else 0
            total += count
            cols = ", ".join(row.get("column_name", "") for row in description[:50])
            details.append(f"{table}[{count}]: {cols}")
        return total, "database", "; ".join(details), ""
    except Exception as exc:
        return "", "", "", f"DuckDB metadata unavailable: {type(exc).__name__}"


def inspect_xml(path: Path):
    try:
        root = ET.parse(path).getroot()
        children = [child.tag.split("}")[-1] for child in list(root)]
        return len(children), "XML", f"root={root.tag.split('}')[-1]}; first-level elements: " + ", ".join(children[:50]), ""
    except Exception as exc:
        return "", "", "", f"XML scan failed: {type(exc).__name__}"


def inspect_yaml(path: Path):
    try:
        keys = []
        with path.open("r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                if line and not line[0].isspace() and ":" in line:
                    key = line.split(":", 1)[0].strip().lstrip("- ")
                    if key and len(keys) < 80:
                        keys.append(key)
        return "", "mapping", "; ".join(dict.fromkeys(keys)), "Top-level keys inferred from YAML text"
    except Exception as exc:
        return "", "", "", f"Content scan failed: {type(exc).__name__}"


def inspect_file(path: Path, extension: str):
    if extension in {".json", ".geojson", ".jsonl", ".ndjson"}:
        return inspect_json(path, extension)
    if extension in {".csv", ".tsv"}:
        relative = path.relative_to(ROOTS["nep"]).as_posix() if path.is_relative_to(ROOTS["nep"]) else ""
        if relative in HEADERLESS_CSV_COLUMNS:
            try:
                with path.open("r", encoding="cp1252", newline="") as handle:
                    count = sum(1 for row in csv.reader(handle) if row)
                return count, "tabular (headerless)", "; ".join(HEADERLESS_CSV_COLUMNS[relative]), "Source CSV has no header row; column labels documented by the parser"
            except Exception as exc:
                return "", "", "", f"Content scan failed: {type(exc).__name__}"
        return inspect_csv(path, "\t" if extension == ".tsv" else ",")
    if extension == ".parquet":
        return inspect_parquet(path)
    if extension in {".sqlite", ".sqlite3"}:
        return inspect_sqlite(path)
    if extension == ".duckdb":
        return inspect_duckdb(path)
    if extension == ".xml":
        return inspect_xml(path)
    if extension in {".yaml", ".yml"}:
        return inspect_yaml(path)
    if extension == ".sql":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tables = re.findall(r"(?i)\bCREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?([\w.]+)", text)
            return "", "SQL", "; ".join(dict.fromkeys(tables)), "Table names inferred from CREATE TABLE statements"
        except Exception as exc:
            return "", "", "", f"Content scan failed: {type(exc).__name__}"
    if extension in {".duckdb", ".db", ".feather", ".arrow"}:
        return "", "binary database/container", "", "Metadata scan not available for this format"
    return "", "", "", ""


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "workspace", "relative_path", "format", "size_bytes", "modified_utc",
        "record_or_row_count", "top_level_shape", "fields_columns_or_tables",
        "source_hint", "notes",
    ]
    rows = []
    for workspace, root in ROOTS.items():
        for path in root.rglob("*"):
            if not path.is_file() or path == OUTPUT or path == SCRIPT:
                continue
            if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
                continue
            extension = path.suffix.lower()
            fmt = EXTENSIONS.get(extension)
            if not fmt:
                continue
            try:
                stat = path.stat()
                count, shape, fields_note, notes = inspect_file(path, extension)
                relative = path.relative_to(root).as_posix()
                hint = ""
                if extension in {".json", ".geojson"} and stat.st_size <= MAX_PARSE_BYTES:
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8-sig"))
                        hint = source_hint(path, payload)
                    except Exception:
                        hint = str(path.parent.relative_to(root))
                else:
                    hint = str(path.parent.relative_to(root))
                rows.append({
                    "workspace": workspace,
                    "relative_path": relative,
                    "format": fmt,
                    "size_bytes": stat.st_size,
                    "modified_utc": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                    "record_or_row_count": count,
                    "top_level_shape": shape,
                    "fields_columns_or_tables": fields_note,
                    "source_hint": hint,
                    "notes": notes,
                })
            except OSError as exc:
                rows.append({"workspace": workspace, "relative_path": path.relative_to(root).as_posix(),
                             "format": fmt, "notes": f"File metadata unavailable: {type(exc).__name__}"})
    rows.sort(key=lambda row: (row["workspace"], row["relative_path"].casefold()))
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Indexed {len(rows):,} structured files to {OUTPUT}")


if __name__ == "__main__":
    main()
