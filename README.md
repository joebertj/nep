# NEP DuckDB analysis suite

`analyze_budget.py` reads one or more Parquet files and writes separate CSVs for repeatable price, duplication, trend, and outlier screening. It uses DuckDB's Python package when available, or the DuckDB CLI (`brew install duckdb`) as a fallback. You do not need both.

Run all analyses against the Parquet files in this directory:

```sh
python3 analyze_budget.py
python3 compute_five_million_stats.py
python3 build_report.py
```

The third command builds `analysis_output/dpwh.html`, a self-contained DPWH/NEP presentation page with embedded charts and searchable tables. The report menu links to the standalone FMR, NIA, and HFEP pages. You can open each HTML file without a local server; rerun its build script after regenerating the CSV reports.

Or provide files explicitly, filter to one year, or run one report:

```sh
python3 analyze_budget.py 2020.parquet 2021.parquet 2027.parquet --out analysis_output
python3 analyze_budget.py --year 2027 --analysis same_price_across_locations
```

The runner unions files by column name. It recognizes common NEP/project names such as `projectName`, `project_name`, `description`; amount names such as `amount`, `budget_amount`, `project_cost`; and year names such as `fiscalYear`, `fiscal_year`, `year`. If a year field is absent, it tries to read a four-digit year from the filename. The confirmed 2027 source amount unit is thousand pesos, so the runner multiplies monetary values by 1,000 and writes report amounts in pesos. `--amount-scale` changes that conversion; for example, use `--amount-scale 1` if inputs already store pesos. When combining files with mixed units, normalize them first.

## HB 10858 project extraction

`extract_hb_projects.py` extracts candidate DPWH project rows from the HB 10858 Volume I-C schedules and writes `hb10858_projects.json` in a structure similar to `2027.json`:

```sh
brew install ghostscript
python3 extract_hb_projects.py
```

The PDF amounts are pesos; the output `amount` is converted to thousands of pesos to match `2027.json`, while `amountPesos` preserves the exact printed amount. Each candidate includes its source PDF, PDF page, extracted text, and a review status. Ghostscript text extraction follows the two printed pages on each PDF sheet in sequence and carries the regional/office context forward. This remains a layout heuristic, not a certified transcription: verify candidate rows and missed records against the cited pages before comparing with NEP or describing anything as an insertion. Use `--include-all` to attempt parsing the other volumes; the default is the DPWH detail schedule in Volume I-C.

The bill also contains non-DPWH schedules. `extract_hb_agency_projects.py` currently extracts the Department of Agriculture's Farm-to-Market Roads schedule from Volume I-B. Its layout-specific parser uses project text and PDF coordinates to pair a title with an amount in the same printed table column. It retains nearby source context, marks suspect amounts, and labels every row as a candidate because PAPs, subtotals, and projects sit in a hierarchy. Review the source page before relying on a row:

```sh
python3 extract_hb_agency_projects.py
python3 convert_hb_json_to_parquet.py
python3 analyze_hb_agencies.py hb10858_agency_projects.parquet
```

The Volume I-B FMR schedule is printed under the Department of Agriculture; its 795 rows should not be relabeled as NIA because some FMR work may involve NIA in other contexts. NIA has a separate project schedule on pages 570–572, extracted independently with its own hierarchy checks:

```sh
python3 extract_hb_nia_projects.py
python3 convert_hb_json_to_parquet.py hb10858_nia_projects.json
python3 analyze_hb_agencies.py hb10858_nia_projects.parquet
python3 build_nia_report.py
```

This writes the standalone `analysis_output/nia.html` project and amount review page.

HFEP is another separate schedule with infrastructure, equipment, motor vehicle, and printed Total columns. The facility parser extracts itemized facility candidates from Volume I-B pages 876–892 using the schedule's indentation and printed Total column, preserving page and nearby text for review:

```sh
python3 extract_hb_hfep_projects.py
python3 convert_hb_json_to_parquet.py hb10858_hfep_projects.json
python3 analyze_hb_agencies.py hb10858_agency_projects.parquet hb10858_nia_projects.parquet hb10858_hfep_projects.parquet
python3 build_hfep_report.py
```

The HFEP parser now extracts 513 deduplicated facility candidates totaling ₱10,021,659,000, matching the printed schedule grand total. That reconciliation exposed and recovered six wrapped or split facility rows worth ₱74.92 million. The total now matches, and the extracted component columns reconcile with every candidate Total, but a matching sum cannot rule out offsetting row errors; sample titles and amounts against the PDF before citing the extract. The DuckDB outputs include amount frequencies by facility type and repeated infrastructure/equipment/vehicle component profiles for like-for-like review.

The NIA schedule contains 32 named project candidates across pages 570 and 572 (page 571 is the mirrored layout), totaling ₱10,655,321,000. This matches the printed `Total, Project(s)` subtotal on page 572. Other rows on these pages are program/PAP summaries and subtotals, so they should not be counted as additional projects. Continue to retain the hierarchy review note when using these rows; the matching project subtotal is a completeness check, not proof that every project line is classified correctly.

DuckDB writes agency totals, repeated-allocation frequencies, and candidate review CSVs under `analysis_output/hb_agencies/`. Keep each bill schedule's agency, program, and source distinct when comparing it with NEP; none of these heuristic extracts is a confirmed insertion list.

To build a separate presentation page with the ₱15 million pattern first:

```sh
python3 analyze_hb_agencies.py hb10858_agency_projects.parquet
python3 build_fmr_report.py
```

This writes the self-contained `analysis_output/fmr.html`.

`compute_five_million_stats.py` runs two exploratory tests on exact ₱5M road/flood entries: a hypergeometric overlap test and a region-stratified randomization test (100,000 shuffles by default). It writes `analysis_output/five_million_stats.json`; the report shows the assumptions and limitations. These tests assess whether office overlap is unusual under the selected chance models, not whether an allocation was deliberate.

After extracting HB 10858, run `python3 compare_hb_nep.py` to create a project-title and amount review list at `analysis_output/hb_nep_comparison.csv`, sorted from largest to smallest amount. It uses exact normalized-title matching only; unmatched rows are candidate insertions for document review, not confirmed additions. The parser and comparison should be checked against the original PDF before presenting totals.

## Reports

- `data_quality.csv`: yearly totals, missing values, distinct names and amounts, and median amount.
- `spending_by_year_category_region.csv`: counts, totals, means, and medians by year, program/category, and region.
- `district_allocations.csv`: District Engineering Office ranking by total amount, share of district-office total, project count, and largest project.
- `district_program_allocations.csv`: office-by-office rankings for Rainwater Collector System, adjacent water categories, multi-purpose buildings, access roads/bridges, and flood mitigation/drainage.
- `water_sector_watchlist.csv`: district projects under the water-sector PAP2 umbrella or with water-related title keywords, including possible category/name variants.
- `same_name_price_variance.csv`: exact normalized project-name matches with different prices across distinct offices/regions.
- `same_price_across_locations.csv`: categories and exact amounts recurring in at least three distinct offices/regions.
- `category_amount_outliers.csv`: unusually high or low amounts within a year/category using robust median deviation, with an IQR fallback when median deviation is zero.
- `repeated_prices.csv`: amounts appearing at least five times in a year, regardless of category.

Names are normalized only for case and punctuation/spacing. These reports do not infer that two differently worded descriptions are the same project. The location field uses office when present and region otherwise; it is a comparison key, not a verified project site. No quantity, length, capacity, materials, or other scope/size field is present in the current 2027 Parquet, so the suite cannot compute unit costs such as pesos per kilometer or compare projects adjusted for size. Monetary values in the reports are converted to pesos from the source's thousand-peso values.

## Scope of the current files

The workspace currently has a single 2027 DPWH project extract (`2027.parquet`), with 11,372 records and fields for region, district/office, project name, PAP hierarchy, amount, and document count. The reports describe patterns in that extract only. Add the 2020–2026 Parquet files as inputs to get cross-year comparisons, provided their records are comparable and the field mapping is correct.

The standalone report has district-level views for Rainwater Collector System, multi-purpose buildings, access roads/bridges, and flood mitigation/drainage. The water-sector watchlist includes records under the shared water supply/rainwater PAP2 plus selected title keywords outside that group, so a possible rename can be reviewed across categories and years. These keyword matches are candidates only.

The NEP page also has Annex A-1/A-4/A-5 duplicate and amendment analyses, insertion pivots, NEP-to-GAB comparisons, and cost-per-kilometer categories. Those need the underlying annex/amendment tables and, for unit-cost work, physical measurements. They are not inferred from this project extract.

Treat any repeated price, matching name, or statistical outlier as a lead for source-document review. It is not, by itself, evidence of an improper allocation.
