# GAA-led MPB tracker with DIME and PhilGEPS left joins

`mpb_source_union.parquet` has one row per GAA MPB record in the same source scope used by the MPB barangay report, plus the FY2027 House GAB proposal slice. GAA/HGAB is the row-defining side of the join: every included base record has `is_mpb = true`, whether or not DIME or PhilGEPS has a match.

```sql
SELECT *
FROM read_parquet('analysis_output/mpb_source_union.parquet')
WHERE is_mpb
ORDER BY fiscal_year, source_dataset;
```

DIME and PhilGEPS matches are conservative exact normalized-title matches. `dime_match_count` and `philgeps_match_count` are zero when there is no match; IDs and titles are null then. Matching records are aggregated onto the GAA row so a GAA MPB never becomes multiple counted rows. This is not proof that unmatched work is absent from either system, and exact-title matching will miss renamed titles.

Expected source totals by year are 836 for FY2016; 5,885 for FY2017; 4,504 for FY2018; 5,268 for FY2020; 7,054 for FY2021; 4,418 for FY2022; 4,393 for FY2023; 292 for FY2024; 5,840 for FY2025; 4,907 for FY2026; and 5,765 HGAB proposal rows for FY2027. FY2019 named-project records are unavailable in the source extract. FY2027 is a proposal, not enacted GAA.

To rebuild after updating source data, run `python3 build_mpb_source_union.py` from the repository root. The build uses the DuckDB CLI and does not modify the source files.
