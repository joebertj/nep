#!/usr/bin/env python3
"""Extract reviewable Farm-to-Market Road project candidates from HB 10858.

The bill's FMR table places project descriptions and peso amounts in aligned
columns. This script uses Ghostscript character coordinates to pair each
project heading with its nearest amount, retaining PDF page and raw source.
It is an explicit candidate extract, not a certified transcription.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from extract_hb_projects import extract_text

ROOT = Path(__file__).resolve().parent
PDF_DIR = ROOT / "HB 10858 FOR 2ND READING"
OUT = ROOT / "hb10858_agency_projects.json"
ACTION = re.compile(r"^(?:construction|concreting|opening and concreting|rehabilitation|improvement|completion|repair|upgrading|reconstruction)\b", re.I)
MONEY = re.compile(r"^\s*(\d{1,3}(?:,\s*\d{3})+)\s*$")
FMR = re.compile(r"\bFMR\b|farm[- ]to[- ]market", re.I)


def page_lines(xml_text: str) -> list[dict]:
    # Remove invalid XML character references emitted for PDF glyphs.
    def valid_ref(m: re.Match) -> str:
        raw = m.group(1)
        cp = int(raw[1:], 16) if raw.startswith("x") else int(raw)
        return m.group(0) if cp in (9, 10, 13) or 0x20 <= cp <= 0xD7FF or 0xE000 <= cp <= 0xFFFD or 0x10000 <= cp <= 0x10FFFF else ""

    root = ET.fromstring(re.sub(r"&#(x[0-9A-Fa-f]+|[0-9]+);", valid_ref, xml_text))
    out = []
    for line in root.iter("line"):
        chars = list(line.iter("char"))
        if not chars:
            continue
        value = "".join(c.attrib.get("c", "") for c in chars).strip()
        if not value:
            continue
        boxes = [tuple(map(float, c.attrib["bbox"].split())) for c in chars]
        out.append({"text": re.sub(r"\s+", " ", value),
                    "x0": min(b[0] for b in boxes), "x1": max(b[2] for b in boxes),
                    "y": sum((b[1] + b[3]) / 2 for b in boxes) / len(boxes)})
    return out


def clean_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def parse_decimal_coordinate(text: str) -> tuple[float, float] | None:
    """Parse decimal-degree START/END values; deliberately skip DMS strings."""
    if "'" in text or '"' in text:
        return None
    body = re.sub(r"^\s*(?:START|END)\s*:\s*", "", text, flags=re.I)
    lat_match = re.search(r"lat(?:itude)?\s*:\s*([-+]?\d+(?:\.\d+)?)\s*([NS])?", body, re.I)
    lon_match = re.search(r"(?:long|longitude)\s*:\s*([-+]?\d+(?:\.\d+)?)\s*([EW])?", body, re.I)
    if lat_match and lon_match:
        lat, lon = float(lat_match.group(1)), float(lon_match.group(1))
        if lat_match.group(2) and lat_match.group(2).upper() == "S": lat = -abs(lat)
        if lon_match.group(2) and lon_match.group(2).upper() == "W": lon = -abs(lon)
    else:
        numbers = re.findall(r"[-+]?\d+(?:\.\d+)?", body)
        if len(numbers) != 2:
            return None
        first, second = map(float, numbers)
        if abs(first) <= 90 and abs(second) <= 180:
            lat, lon = first, second
        elif abs(second) <= 90 and abs(first) <= 180:
            lat, lon = second, first
        else:
            return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def straight_line_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(h))


def parse_station_meters(text: str) -> float | None:
    match = re.search(r"\bSTA\.?\s*[:.]?\s*(\d{1,3})\s*\+\s*(\d{1,4}(?:\.\d+)?)", text, re.I)
    if not match:
        return None
    return int(match.group(1)) * 1000 + float(match.group(2))


def extract_page(pdf: Path, page_no: int, xml_text: str) -> list[dict]:
    lines = page_lines(xml_text)
    starts = [x for x in lines if ACTION.match(x["text"]) and FMR.search(x["text"])]
    amounts = []
    for x in lines:
        m = MONEY.fullmatch(x["text"])
        if m:
            amounts.append({**x, "amount": int(re.sub(r"\D", "", m.group(1)))})
    records = []
    for i, start in enumerate(starts):
        # Do not treat the schedule's introductory heading as an individual
        # project simply because it contains the word "construction".
        if re.search(r"repair/rehabilitation and construction of farm-to-market roads", start["text"], re.I):
            continue
        # Keep category/PAP headings out of the project candidate list. A
        # specific barangay, sitio, municipality, city, province, or road name
        # must be present in the extracted description.
        next_y = starts[i + 1]["y"] if i + 1 < len(starts) else start["y"] + 45
        same_column_titles = [
            item for item in starts
            if abs(item["x0"] - start["x0"]) < 70 and item["y"] > start["y"]
        ]
        next_same_column_y = min((item["y"] for item in same_column_titles), default=start["y"] + 70)
        # Append short location continuations from the description column;
        # omit coordinate lines and table amounts.
        pieces = [start["text"]]
        for line in lines:
            if start["y"] < line["y"] < min(next_y, start["y"] + 38) and abs(line["x0"] - start["x0"]) < 70:
                t = line["text"]
                if not re.match(r"^(?:START|END):", t, re.I) and not MONEY.fullmatch(t) and not ACTION.match(t):
                    if len(t) > 3 and not re.fullmatch(r"[\d.,+\- ]+", t):
                        pieces.append(t)
        title = re.sub(r"\s+", " ", " ".join(dict.fromkeys(pieces))).strip()
        if len(title) > 190 or not re.search(
            r"\b(?:brgy\.?|barangay|sitio|purok|municipality|city|province|road|bridge|town)\b",
            title, re.I,
        ):
            continue
        # Each printed page has its own description and amount columns. Pair
        # within that same left or right column; otherwise a nearby regional
        # subtotal in the adjacent column can be mistaken for a project price.
        # The page crop shifts across the PDF. Match the amount cell that sits
        # roughly one table column to the right of this description instead
        # of hard-coding absolute x coordinates.
        amount_in_same_column = (200 <= a["x0"] - start["x0"] <= 550 for a in amounts)
        nearby = [a for a, same_column in zip(amounts, amount_in_same_column)
                  if same_column and -2 <= a["y"] - start["y"] <= 25]
        if not nearby:
            continue
        amount = min(nearby, key=lambda a: abs(a["y"] - start["y"]))
        if amount["amount"] <= 0:
            continue
        context = [
            line["text"] for line in lines
            if abs(line["y"] - start["y"]) <= 24
            and abs(line["x0"] - start["x0"]) <= 550
            and len(line["text"]) > 2
            and not re.match(r"^(?:START|END):", line["text"], re.I)
        ]
        flags = []
        review_notes = []
        if amount["amount"] < 1_000_000:
            flags.append("amount below ₱1M; verify the printed amount cell")
        if amount["amount"] > 60_000_000:
            review_notes.append("large amount; verify PAP/project level and amount against the schedule")
        coord_lines = [
            line for line in lines
            if abs(line["x0"] - start["x0"]) < 70
            and start["y"] < line["y"] < min(next_same_column_y, start["y"] + 70)
            and re.match(r"^(?:START|END)\s*:", line["text"], re.I)
        ]
        parsed_coords = {}
        for line in coord_lines:
            kind = re.match(r"^(START|END)\s*:", line["text"], re.I).group(1).upper()
            parsed = parse_decimal_coordinate(line["text"])
            if parsed and kind not in parsed_coords:
                parsed_coords[kind] = parsed
        distance_km = straight_line_km(parsed_coords["START"], parsed_coords["END"]) if {"START", "END"} <= parsed_coords.keys() else None
        station_values = [
            value for line in lines
            if abs(line["x0"] - start["x0"]) < 70
            and start["y"] < line["y"] < min(next_same_column_y, start["y"] + 100)
            if (value := parse_station_meters(line["text"])) is not None
        ]
        station_start = station_values[0] if len(station_values) == 2 else None
        station_end = station_values[1] if len(station_values) == 2 else None
        station_distance_m = abs(station_end - station_start) if station_start is not None else None
        records.append({
            "id": f"HB10858-FMR-{page_no:04d}-{i+1:03d}",
            "code": f"HB10858-FMR-{page_no:04d}-{i+1:03d}",
            "fiscalYear": 2027,
            "agency": "Department of Agriculture",
            "program": "Farm-to-Market Roads",
            "region": "",
            "office": "",
            "projectName": title,
            "pap1": "Department of Agriculture",
            "pap2": "Farm-to-Market Roads",
            "pap3": "FMR",
            "rowType": "project candidate; may be a PAP or other hierarchy row",
            "amount": amount["amount"] / 1000,
            "amountUnit": "thousand pesos",
            "amountPesos": amount["amount"],
            "startCoordinate": list(parsed_coords["START"]) if "START" in parsed_coords else None,
            "endCoordinate": list(parsed_coords["END"]) if "END" in parsed_coords else None,
            "straightLineDistanceKm": round(distance_km, 3) if distance_km is not None else None,
            "pesosPerStraightLineKm": round(amount["amount"] / distance_km, 2) if distance_km and distance_km > 0 else None,
            "distanceMethod": "Haversine distance between printed endpoints; straight-line proxy, not road length",
            "chainageStartMeters": station_start,
            "chainageEndMeters": station_end,
            "chainageDistanceMeters": station_distance_m,
            "chainageDistanceKm": round(station_distance_m / 1000, 3) if station_distance_m is not None else None,
            "pesosPerChainageKm": round(amount["amount"] / (station_distance_m / 1000), 2) if station_distance_m and station_distance_m > 0 else None,
            "chainageMethod": "Absolute difference between the two printed STA values in the project column",
            "amountField": "printed FMR project allocation; nearest aligned amount column",
            "sourceVolume": pdf.name,
            "sourcePage": page_no,
            "sourceText": title + " | " + amount["text"],
            "sourceContext": " | ".join(dict.fromkeys(context)),
            "screeningFlags": flags,
            "reviewNotes": review_notes,
            "reviewStatus": "candidate; verify PAP/project level and amount against PDF",
        })
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=PDF_DIR)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--ghostscript", default="gs")
    parser.add_argument("--page-dir", type=Path, help="Reuse Ghostscript page XML already extracted from the source PDF")
    args = parser.parse_args()
    gs = shutil.which(args.ghostscript)
    if not gs and not args.page_dir:
        parser.error("Ghostscript is required: brew install ghostscript")
    pdfs = sorted(args.pdf_dir.glob("*VOL*IB*.pdf"))
    if not pdfs:
        parser.error(f"No Volume I-B PDF found in {args.pdf_dir}")
    all_rows, stats = [], []
    with tempfile.TemporaryDirectory(prefix="hb10858-fmr-") as tmp:
        for pdf in pdfs:
            folder = args.page_dir if args.page_dir else Path(tmp) / "pages"
            if not args.page_dir:
                print(f"Extracting text: {pdf.name}")
                extract_text(gs, pdf, folder)
            rows = []
            for f in sorted(folder.glob("page-*.xml")):
                page_no = int(f.stem.split("-")[-1])
                rows.extend(extract_page(pdf, page_no, f.read_text(encoding="utf-8", errors="replace")))
            # Facing-page repeats are common in this PDF extraction. Keep one
            # row per normalized title and amount, retaining first provenance.
            unique, seen = [], set()
            for row in rows:
                key = (clean_key(row["projectName"]), row["amountPesos"])
                if key not in seen:
                    seen.add(key)
                    unique.append(row)
            all_rows.extend(unique)
            stats.append({"file": pdf.name, "candidateRows": len(unique)})
    payload = {"status": 200, "code": "SUCCESS", "data": {"data": all_rows}, "metadata": {
        "source": "House Bill No. 10858, FY 2027, Volume I-B, Department of Agriculture FMR schedule",
        "amountUnit": "thousand pesos; amountPesos preserves printed peso amount",
        "extractionMethod": "Ghostscript text with coordinate-based nearest-row amount pairing",
        "sourceFiles": stats, "candidateCount": len(all_rows),
        "warning": "Candidate extraction only. Check PDF pages before treating these rows as exact or as additions to NEP.",
    }}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(all_rows):,} candidate FMR rows: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
