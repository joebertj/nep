# FY 2027 Farm-to-Market Road (FMR) Project Dataset — Shareable Outputs

Extracted project ledgers, normalized coordinates, and machine-verifiable audits for the
**Department of Agriculture locally-funded Farm-to-Market Road annex** under two FY 2027
budget stages. Prepared for anyone who needs a citable, traceable list of FMR projects
with locations and peso amounts.

## What is in this dataset

Two independent project ledgers covering the same FMR program at two legislative stages:

| Stage | Source document | Projects | Total (PHP) | Regions |
|---|---|---:|---:|---:|
| DBM National Expenditure Program (executive proposal) | Standalone FMR schedule, `FMR.pdf` (printed pp. 1511–1557) | 704 | 16,000,000,000 | 16 |
| House General Appropriations Bill (HB 10858, supplied local copy) | Volume I-B FMR annex (printed pp. 651–710 / PDF pp. 667–726) | 964 | 19,628,100,000 | 16 |

Every project row carries its full lineage: source PDF, PDF page, printed page, raw OCR
coordinate text, interpreted transcription, and any normalization rules or review flags
applied. Nothing in these files requires trusting the extractors — the audit files
reproduce the arithmetic from source hashes.

## Files

### Project ledgers (start here)

| File | Description |
|---|---|
| `hgab_fmr_projects_normalized.csv` | 964 House GAB FMR projects. 950 fully normalized; 14 flagged `needs_review`. |
| `nep_fmr_projects_normalized.csv` | 704 NEP FMR projects. 696 fully normalized; 8 flagged `needs_review`. |

Key columns in both:

- `project_id` — source-stable identifier (e.g. `ib:p667:r5`, `nep_fmr:p1:r5`). Identifies
  the row within its own source document; it is **not** a cross-document project identity.
- `region` — one of 16 Philippine regions, as printed in the source.
- `title` — project name as printed, with line wrapping collapsed.
- `amount_php` — allocation in pesos, exactly as printed (no unit multiplier).
- `coordinates_json` — normalized coordinate arrays, structured as
  `[[[longitude, latitude], ...], ...]` (segments → points; order is lon, lat).
- `status` — `normalized` or `needs_review`.
- `review_flags`, `normalization_rules`, `original_review_flags` — coordinate
  normalization provenance. Empty flags on a `normalized` row mean a clean parse.
- `coordinates_raw` — the original OCR text (START/END lines) exactly as extracted.
- `source_pdf`, `pdf_page`, `printed_page` — physical page in the PDF and the printed
  page number on the document.
- NEP-only extra columns: `coordinates_interpreted`, `coordinate_text_basis`,
  `image_review_finding`, `image_review_evidence` — record the rendered-image review of
  initially flagged cells.

### Coordinate detail

| File | Description |
|---|---|
| `hgab_fmr_segments.csv` / `nep_fmr_segments.csv` | One row per road segment (1004 / 722 rows). Adds `straight_line_distance_km` and `pairing_basis` (how START/END were paired). |
| `hgab_fmr_points.csv` / `nep_fmr_points.csv` | One row per coordinate point (2007 / 1444 rows). Adds `role` (start/end/intermediate), raw source fragments, station labels, and any unconsumed OCR text. |
| `hgab_fmr_coordinates_normalized.json` / `nep_fmr_coordinates_normalized.json` | The same coordinate data as nested JSON keyed by project, with rule metadata. |

Distances are straight-line (diagnostic only) — they do **not** establish road length or
cost-per-km.

### Verification and provenance

| File | Description |
|---|---|
| `hgab_fmr_audit.json` / `nep_fmr_audit.json` | Machine audits. Record source PDF SHA-256, extractor script hash, row-role counts, and all additive control checks. Both report `passed: true` with 17/17 internal controls and 17/17 cross-volume/agency-schedule controls reconciled. |
| `hgab_fmr_coordinate_normalization_audit.json` / `nep_fmr_coordinate_normalization_audit.json` | How each initial review flag was resolved: per-flag project counts, rule usage, and outcomes. |
| `nep_fmr_coordinate_image_review_audit.json` | The rendered-image review of all 23 initially flagged NEP cells: 15 resolved corrections, 8 retaining printed-source anomalies. Includes hashes of the source tree and review manifest. |

## Source integrity

| Source | SHA-256 |
|---|---|
| House GAB Vol. I-B (`2 - HB 10858 VOL IB.pdf`) | `a82800c4cc2684566a37f7780d8f9131d2e7b2c97444d335d94df012dec065b6` |
| House GAB Vol. I-A (cross-volume controls) | `6fffb251c2b98e9aefd5d3295e561780c6744e83f313507b8da0d3671cc9be13` |
| DBM NEP FMR schedule (`FMR.pdf`) | `07355c115f45a84771b8a8ac22711992ea695ea28f0c9c1b2c71879d4a6dc4ba` |

To verify a ledger independently: re-extract from the hashed PDF, or at minimum confirm
that regional subtotals in the project CSVs sum to the printed program control, and that
the two ledgers' grand totals match the figures above.

## Important caveats

1. **The NEP file is an executive proposal, not an enacted appropriation.** Amounts are
   proposals as printed in the NEP FMR schedule.
2. **The House copy's legislative reading is not independently authenticated.** It is
   labeled second reading. A bounded comparison found identical extracted text on all 60
   FMR annex pages against the named third-reading copy, and both print the same
   ₱19,628,100,000 control — but the bill as a whole was not authenticated.
3. **The two ledgers must not be summed together.** They are the same program at two
   stages; parents and children within each hierarchy describe the same money.
4. **Rows flagged `needs_review` (14 House, 8 NEP) retain printed-source coordinate
   anomalies** (e.g. swapped digits, values repeated from another document). Their
   original OCR strings and amounts are untouched; only coordinate normalization was
   withheld. Seven of the NEP flags repeat values found in the House GAB.
5. **No cross-stage project matching is included here.** Candidate House↔NEP pairings
   exist in the parent repository's workbench, but they are provisional (title + exact
   coordinate keys) and are deliberately excluded from this shareable set. Treat any
   join between the two ledgers as your own analysis.
6. **`project_id` values are page/row locators, not identities.** They do not assert that
   `ib:p667:r5` and `nep_fmr:p1:r5` (which happen to be the same-named project) are the
   same budget item.

## Scope

This covers only the DA **locally-funded FMR annex** (repair/rehabilitation and
construction of farm-to-market roads in designated key production areas). It does not
include the DA's FMR Network Planning and Monitoring Services allocation, FMR planning or
bridge activities, the wider DA budget, or any DPWH road programs.

Generated from the `other-analysis/` extraction pipeline in the parent repository.
Method notes: [`FMR_EXTRACTION.md`](../../FMR_EXTRACTION.md) (House),
[`NEP_FMR_EXTRACTION.md`](../../NEP_FMR_EXTRACTION.md) (NEP),
[`FMR_COORDINATE_REVIEW_FLAGS.md`](../../FMR_COORDINATE_REVIEW_FLAGS.md),
[`NEP_FMR_COORDINATE_REVIEW_FLAGS.md`](../../NEP_FMR_COORDINATE_REVIEW_FLAGS.md).
