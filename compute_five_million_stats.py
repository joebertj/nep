#!/usr/bin/env python3
"""Compute reproducible tests for exact ₱5M road/flood office overlap."""

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import random


ROAD = "BIP - Access Roads and/or Bridges from the National Roads leading to Major/ Strategic Public Buildings/ Facilities"
FLOOD = {
    "Construction/ Maintenance of Flood Mitigation Structures and Drainage Systems",
    "Construction/ Rehabilitation of Flood Mitigation Facilities within Major River Basins and Principal Rivers",
}


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def hypergeom_tail(population, road_offices, flood_offices, observed):
    denominator = math.comb(population, flood_offices)
    low = max(0, flood_offices - (population - road_offices))
    high = min(road_offices, flood_offices)
    return sum(
        math.comb(road_offices, overlap)
        * math.comb(population - road_offices, flood_offices - overlap)
        / denominator
        for overlap in range(max(low, observed), high + 1)
    )


def compute_year(year, offices, repeated_rows, district_programs, reps):
    office_regions = {row["office"]: row["region"] for row in offices}
    population = len(office_regions)
    by_office = defaultdict(lambda: {"road": 0, "flood": 0})
    road_entries = flood_entries = 0
    road_set, flood_set = set(), set()
    for row in repeated_rows:
        office = row["office"]
        category = row["category"]
        if category == ROAD:
            by_office[office]["road"] += 1
            road_entries += 1
            road_set.add(office)
        elif category in FLOOD:
            by_office[office]["flood"] += 1
            flood_entries += 1
            flood_set.add(office)
    observed = len(road_set & flood_set)
    expected = len(road_set) * len(flood_set) / population if population else 0

    programs = defaultdict(int)
    for row in district_programs:
        programs[row["category"]] += int(float(row["project_count"]))
    road_project_count = programs[ROAD]
    flood_project_count = sum(programs[label] for label in FLOOD)

    strata = defaultdict(list)
    for office, region in office_regions.items():
        strata[region].append(office)
    stratified_expected = 0.0
    simulations = []
    for region, members in sorted(strata.items()):
        road_n = sum(office in road_set for office in members)
        flood_n = sum(office in flood_set for office in members)
        stratified_expected += road_n * flood_n / len(members)
        if road_n and flood_n:
            simulations.append((members, road_n, flood_n))

    rng = random.Random(502026 + int(year))
    exceedances = 0
    for _ in range(reps):
        overlap = 0
        for members, road_n, flood_n in simulations:
            shuffled_flood_offices = rng.sample(members, flood_n)
            overlap += sum(office in road_set for office in shuffled_flood_offices)
        if overlap >= observed:
            exceedances += 1

    odds_ratio = (
        observed * (population - len(road_set) - len(flood_set) + observed)
        / ((len(road_set) - observed) * (len(flood_set) - observed))
        if (len(road_set) - observed) * (len(flood_set) - observed)
        else None
    )
    return {
        "fiscal_year": int(year),
        "district_offices": population,
        "road_offices": len(road_set),
        "flood_offices": len(flood_set),
        "overlap_offices": observed,
        "union_offices": len(road_set | flood_set),
        "road_entries_at_5m": road_entries,
        "flood_entries_at_5m": flood_entries,
        "road_entries_total": road_project_count,
        "flood_entries_total": flood_project_count,
        "road_entry_share": road_entries / road_project_count if road_project_count else None,
        "flood_entry_share": flood_entries / flood_project_count if flood_project_count else None,
        "independent_expected_overlap": expected,
        "hypergeometric_p_value": hypergeom_tail(population, len(road_set), len(flood_set), observed) if population else None,
        "odds_ratio": odds_ratio,
        "region_controlled_expected_overlap": stratified_expected,
        "region_controlled_simulated_p_value": (exceedances + 1) / (reps + 1),
        "simulation_repetitions": reps,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=Path("analysis_output"))
    parser.add_argument("--repetitions", type=int, default=100_000)
    args = parser.parse_args()
    if args.repetitions < 1:
        parser.error("--repetitions must be positive")

    offices = read_csv(args.reports / "district_allocations.csv")
    repeated = read_csv(args.reports / "five_million_roads_flood.csv")
    programs = read_csv(args.reports / "district_program_allocations.csv")
    years = sorted({int(row["fiscal_year"]) for row in offices})
    results = [
        compute_year(
            year,
            [row for row in offices if int(row["fiscal_year"]) == year],
            [row for row in repeated if int(row["fiscal_year"]) == year],
            [row for row in programs if int(row["fiscal_year"]) == year],
            args.repetitions,
        )
        for year in years
    ]
    payload = {
        "method": {
            "hypergeometric": "One-sided overlap test: among the year's district offices, fix the number with exact ₱5M road entries and flood entries, then ask how often independent assignment gives at least the observed overlap.",
            "region_controlled": "Monte Carlo randomization shuffles which offices have exact ₱5M flood entries within each region, preserving each region's flood-office count and the observed road offices.",
            "limitations": "Exploratory tests of office co-occurrence, not intent. They do not account for project need, office workload, project mix, or selection of ₱5M and these categories after seeing the pattern. A small p-value rejects the specified chance model; it does not prove deliberate allocation.",
            "random_seed": 502026,
        },
        "results": results,
    }
    destination = args.reports / "five_million_stats.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for row in results:
        print(
            f"FY {row['fiscal_year']}: {row['overlap_offices']}/{row['road_offices']} roads offices "
            f"overlap {row['flood_offices']} flood offices; expected {row['independent_expected_overlap']:.1f} "
            f"(region controlled {row['region_controlled_expected_overlap']:.1f}); "
            f"region-controlled p≈{row['region_controlled_simulated_p_value']:.6g}"
        )
    print(f"Wrote: {destination}")


if __name__ == "__main__":
    main()
