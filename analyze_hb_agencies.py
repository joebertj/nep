#!/usr/bin/env python3
"""Run DuckDB screening analyses on HB agency project Parquet files."""

import argparse
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def quote(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def run(cli: str, sql: str) -> None:
    result = subprocess.run([cli, "-c", sql], capture_output=True, text=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parquet", nargs="+", type=Path, help="One or more HB agency Parquet files")
    parser.add_argument("--out", type=Path, default=ROOT / "analysis_output" / "hb_agencies")
    parser.add_argument("--duckdb", default="duckdb")
    args = parser.parse_args()
    cli = shutil.which(args.duckdb)
    if not cli:
        parser.error("DuckDB CLI required. Install with: brew install duckdb")
    args.out.mkdir(parents=True, exist_ok=True)
    inputs = ", ".join("'" + quote(p) + "'" for p in args.parquet)
    source = f"read_parquet([{inputs}], union_by_name=true, filename=true)"
    reports = {
        "hb_agency_totals.csv": f"""SELECT agency, program, count(*) AS projects,
            sum(amountPesos) AS total_pesos, median(amountPesos) AS median_project_pesos,
            min(amountPesos) AS smallest_pesos, max(amountPesos) AS largest_pesos,
            count(*) FILTER (WHERE len(screeningFlags) > 0) AS amount_cell_review_rows,
            count(*) FILTER (WHERE len(reviewNotes) > 0) AS hierarchy_review_rows
            FROM {source} GROUP BY ALL ORDER BY total_pesos DESC""",
        "hb_repeated_allocations.csv": f"""SELECT agency, program, amountPesos, count(*) AS project_count,
            count(DISTINCT projectName) AS distinct_titles,
            string_agg(DISTINCT projectName, ' | ' ORDER BY projectName) AS project_examples
            FROM {source} GROUP BY ALL HAVING count(*) >= 3
            ORDER BY project_count DESC, amountPesos DESC""",
        "hb_project_candidates.csv": f"""SELECT agency, program, region, office, projectName, amountPesos,
            sourceVolume, sourcePage, sourceText, sourceContext, screeningFlags, reviewNotes, reviewStatus
            FROM {source} ORDER BY amountPesos DESC""",
        "fmr_amount_frequency.csv": f"""WITH clean AS (
            SELECT amountPesos, regexp_extract(projectName, ',\\s*([^,]+,\\s*[^,]+)$', 1) AS location_hint
            FROM {source} WHERE program='Farm-to-Market Roads' AND len(screeningFlags)=0
            ), total AS (SELECT count(*) AS n FROM clean)
            SELECT amountPesos, count(*) AS project_candidates,
                count(DISTINCT location_hint) FILTER (WHERE location_hint<>'') AS distinct_location_hints,
                round(100.0*count(*)/(SELECT n FROM total), 1) AS share_of_unflagged_pct
            FROM clean GROUP BY 1 ORDER BY project_candidates DESC, amountPesos DESC""",
        "fmr_province_allocations.csv": f"""WITH clean AS (
            SELECT regexp_extract(projectName, ',\\s*([^,]+,\\s*[^,]+)$', 1) AS location_hint, amountPesos
            FROM {source} WHERE program='Farm-to-Market Roads' AND len(screeningFlags)=0
            ), located AS (
            SELECT regexp_extract(location_hint, ',\\s*(.+)$', 1) AS province_hint, amountPesos
            FROM clean WHERE location_hint<>'')
            SELECT province_hint, count(*) AS project_candidates, sum(amountPesos) AS candidate_total_pesos,
                median(amountPesos) AS median_candidate_pesos,
                count(*) FILTER (WHERE amountPesos=15000000) AS candidates_at_15m,
                round(100.0*count(*) FILTER (WHERE amountPesos=15000000)/count(*),1) AS pct_at_15m
            FROM located GROUP BY 1 HAVING count(*)>=5 ORDER BY project_candidates DESC""",
        "fmr_location_repeated_allocations.csv": f"""WITH clean AS (
            SELECT regexp_extract(projectName, ',\\s*([^,]+,\\s*[^,]+)$', 1) AS location_hint,
                amountPesos, projectName
            FROM {source} WHERE program='Farm-to-Market Roads' AND len(screeningFlags)=0
            )
            SELECT location_hint, amountPesos, count(*) AS project_candidates,
                string_agg(projectName, ' | ' ORDER BY projectName) AS project_examples
            FROM clean WHERE location_hint<>'' GROUP BY 1,2 HAVING count(*)>=3
            ORDER BY project_candidates DESC, amountPesos DESC""",
        "fmr_flagged_rows.csv": f"""SELECT amountPesos, projectName, sourceVolume, sourcePage,
            sourceText, sourceContext, screeningFlags, reviewNotes
            FROM {source} WHERE program='Farm-to-Market Roads' AND (len(screeningFlags)>0 OR len(reviewNotes)>0)
            ORDER BY amountPesos DESC""",
        "fmr_coordinate_review.csv": f"""SELECT projectName, amountPesos, startCoordinate, endCoordinate,
            straightLineDistanceKm, pesosPerStraightLineKm, sourceVolume, sourcePage
            FROM {source} WHERE program='Farm-to-Market Roads' AND len(screeningFlags)=0
            AND straightLineDistanceKm IS NOT NULL
            AND (straightLineDistanceKm<0.1 OR straightLineDistanceKm>10)
            ORDER BY straightLineDistanceKm DESC""",
        "fmr_unit_cost_candidates.csv": f"""SELECT projectName, amountPesos, straightLineDistanceKm,
            pesosPerStraightLineKm, startCoordinate, endCoordinate, sourceVolume, sourcePage
            FROM {source} WHERE program='Farm-to-Market Roads' AND len(screeningFlags)=0
            AND straightLineDistanceKm BETWEEN 0.1 AND 10
            ORDER BY pesosPerStraightLineKm DESC""",
        "fmr_chainage_unit_cost.csv": f"""SELECT projectName, amountPesos,
            chainageStartMeters, chainageEndMeters, chainageDistanceMeters,
            chainageDistanceKm, pesosPerChainageKm, sourceVolume, sourcePage,
            sourceText, sourceContext
            FROM {source} WHERE program='Farm-to-Market Roads'
            AND chainageDistanceKm IS NOT NULL AND chainageDistanceKm>0
            ORDER BY pesosPerChainageKm DESC""",
        "nia_amount_frequency.csv": f"""SELECT amountPesos, count(*) AS project_candidates,
            string_agg(projectName, ' | ' ORDER BY projectName) AS project_examples
            FROM {source} WHERE program='NIA named irrigation projects'
            GROUP BY 1 ORDER BY project_candidates DESC, amountPesos DESC""",
        "nia_project_candidates.csv": f"""SELECT projectName, amountPesos, sourceVolume, sourcePage,
            sourceText, sourceContext, reviewNotes, reviewStatus
            FROM {source} WHERE program='NIA named irrigation projects'
            ORDER BY amountPesos DESC""",
        "hfep_amount_frequency.csv": f"""SELECT amountPesos, count(*) AS facility_candidates,
            count(DISTINCT projectName) AS distinct_titles,
            string_agg(DISTINCT projectName, ' | ' ORDER BY projectName) AS project_examples
            FROM {source} WHERE program='Health Facilities Enhancement Program'
            GROUP BY 1 ORDER BY facility_candidates DESC, amountPesos DESC""",
        "hfep_project_candidates.csv": f"""SELECT projectName, amountPesos,
            amountInfrastructurePesos, amountMedicalEquipmentPesos, amountMotorVehiclePesos,
            sourceVolume, sourcePage,
            sourceText, sourceContext, reviewNotes, reviewStatus
            FROM {source} WHERE program='Health Facilities Enhancement Program'
            ORDER BY amountPesos DESC""",
        "hfep_type_amount_frequency.csv": f"""WITH typed AS (
            SELECT projectName, amountPesos,
                CASE
                    WHEN regexp_matches(projectName, '(?i)barangay health station|\\bBHS\\b') THEN 'Barangay Health Station'
                    WHEN regexp_matches(projectName, '(?i)rural health unit|\\bRHU\\b') THEN 'Rural Health Unit'
                    WHEN regexp_matches(projectName, '(?i)super health center') THEN 'Super Health Center'
                    WHEN regexp_matches(projectName, '(?i)primary care facility') THEN 'Primary Care Facility'
                    WHEN regexp_matches(projectName, '(?i)hospital|ospital|infirmary|sanitarium') THEN 'Hospital / Infirmary'
                    WHEN regexp_matches(projectName, '(?i)dialysis|renal') THEN 'Dialysis / Renal'
                    WHEN regexp_matches(projectName, '(?i)blood center|blood bank') THEN 'Blood Facility'
                    WHEN regexp_matches(projectName, '(?i)laboratory|reference lab') THEN 'Laboratory'
                    WHEN regexp_matches(projectName, '(?i)quarantine') THEN 'Quarantine Facility'
                    WHEN regexp_matches(projectName, '(?i)rehabilitation|DATRC|drug abuse') THEN 'Rehabilitation Facility'
                    WHEN regexp_matches(projectName, '(?i)health center|health centre') THEN 'Health Center'
                    WHEN regexp_matches(projectName, '(?i)health station') THEN 'Health Station'
                    ELSE 'Other named facility'
                END AS facility_type
            FROM {source} WHERE program='Health Facilities Enhancement Program'
            )
            SELECT facility_type, amountPesos, count(*) AS facility_candidates,
                string_agg(projectName, ' | ' ORDER BY projectName) AS project_examples
            FROM typed GROUP BY 1,2
            ORDER BY facility_type, facility_candidates DESC, amountPesos DESC""",
        "hfep_component_profiles.csv": f"""SELECT amountPesos,
            amountInfrastructurePesos, amountMedicalEquipmentPesos, amountMotorVehiclePesos,
            count(*) AS facility_candidates,
            string_agg(projectName, ' | ' ORDER BY projectName) AS project_examples
            FROM {source} WHERE program='Health Facilities Enhancement Program'
            GROUP BY ALL ORDER BY facility_candidates DESC, amountPesos DESC""",
        "hfep_component_reconciliation.csv": f"""SELECT projectName, amountPesos,
            amountInfrastructurePesos, amountMedicalEquipmentPesos, amountMotorVehiclePesos,
            coalesce(amountInfrastructurePesos,0)+coalesce(amountMedicalEquipmentPesos,0)+
                coalesce(amountMotorVehiclePesos,0) AS component_sum_pesos,
            amountPesos-(coalesce(amountInfrastructurePesos,0)+coalesce(amountMedicalEquipmentPesos,0)+
                coalesce(amountMotorVehiclePesos,0)) AS total_minus_components_pesos,
            sourceVolume, sourcePage
            FROM {source} WHERE program='Health Facilities Enhancement Program'
            AND amountPesos<>(coalesce(amountInfrastructurePesos,0)+coalesce(amountMedicalEquipmentPesos,0)+
                coalesce(amountMotorVehiclePesos,0))
            ORDER BY abs(total_minus_components_pesos) DESC""",
    }
    for name, query in reports.items():
        run(cli, f"COPY ({query}) TO '{quote(args.out / name)}' (HEADER, DELIMITER ',')")
        print(f"Wrote {args.out / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
