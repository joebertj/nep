# FY2027 Senate committee report on HB 10858: the dataset

Built 2026-11-21T09:06:17Z by budget.bettergov.ph from commit `b6cca85d0dc66f93521ec5684a66be2c137ad395` of github.com/bettergovph/ai-reports
(`npm run build:senate-cr`). Pages: https://budget.bettergov.ph/senate/2027/overview

Independent and unofficial: our reading of the Senate Committee on Finance's report, not an official record.
**Under citizen review**: we have not finished checking every figure. Before you cite one, open the page of the
report it gives (`senate_pdf_url`). Amounts are as published, not spending. The NEP, the House bill and the Senate
committee report are versions of one budget: compare them, never add them.

## What's here

| File | Rows | What |
| --- | --- | --- |
| senate-2027-projects.csv / .parquet | 20,835 | every project of the four programs the report details, by version |
| senate-2027-annex-a.csv / .parquet | 2,719 | Annex A, the line-by-line amendments, as printed |
| senate-2027-general-summary.csv / .parquet | 450 | the General Summary by department and agency |
| senate-2027-provisions.csv / .parquet | 186 | Annex B, the amendments to the provisions |
| senate-2027-pairings.csv / .parquet | | insertions paired or flagged, to check (columns as the projects file's) |
| senate-2027-checks.csv | 38 | the checks this build ran (37 of 38 passed) |
| senate-2027-page-misses.csv | | page links whose page doesn't print the project's name, to check by hand |
| manifest.json | | sources, files, row counts and SHA-256 |
| senate-2027-dataset.zip | | the CSVs, the checks, this README, the manifest and SHA256SUMS.txt (its own SHA-256 is on the download page and in index.json) |
| SHA256SUMS.txt | | SHA-256 of every file and of the source PDFs |

## Sources

The Senate Committee on Finance's Committee Report on House Bill No. 10858 (FY 2027 General Appropriations Bill):
born-digital PDFs, read from their text (no OCR, no AI). Our copies, byte for byte:

- General Summary: `General Summary of Committee Report No. __ on House Bill No. 10858 (FY 2027 GAB).pdf`, SHA-256 `7345416b34d94c36b3696059f1907ddc3d2e64cc4904b484613a30c5b75e53bd`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-general-summary.pdf
- Annex A: Line-by-line amendments: `Annex A - Line By Line Amendments (1).pdf`, SHA-256 `77065842846fe14f2942464d8ba6ddca9b13200445dfe4ecf483fafeb4a7abb8`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-a.pdf
- Annex A-1: DA farm-to-market roads: `Annex A-1 DA Farm-to-Market Roads.pdf`, SHA-256 `176ff3411000942d858d9e4850a965cf1d7cafb85e9137d7d1b74d17c80484e8`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-a1.pdf
- Annex A-2: DOH Health Facilities Enhancement Program: `Annex A-2 DOH Health Facilities Enhancement Program (HFEP).pdf`, SHA-256 `87ff59ac9f0fbd8ec541252370918bc45080b9977d0ca2261bb745229ef5e5dd`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-a2.pdf
- Annex A-3: NIA projects: `Annex A-3 BSGC-OEOs-NIA-Details of NIA's Operations Budget.pdf`, SHA-256 `587dcd6b83f32c172b88cbaaab601e69f628c46e136faad0347730cf16895824`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-a3.pdf
- Annex A-4: DPWH programs and projects: `Annex A-4 Details of DPWH's Programs-Projects (FY 2027 General Appropriations Bill Volume I-C).pdf`, SHA-256 `8b849fd8661d142ae9b35d35238e8d3d76d688f279ee4fbca9f1a90e90750194`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-a4.pdf
- Annex A-5: TIEZA and Tourism Promotions Board: `Annex A-5 Details of BSGC-DOT-TIEZA and TPB.pdf`, SHA-256 `e845de4fdaf729053580eb80b72fe8c7c62c0134f1d7fe9e295eb9f5071541e4`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-a5.pdf
- Annex B: Special and general provisions: `Annex B - Amendments to the Special and General Provisions.pdf`, SHA-256 `e562247978059abbce55aefb6c2133a10c569522f5fdb3103465776782e51719`, https://budget-assets.bettergov.ph/senate/2027/pdf/senate-cr-annex-b.pdf

The House bill (HB 10858, third reading) and the NEP pages cited are at budget-assets.bettergov.ph/hgab/2027/pdf/.

## How to check this data yourself

1. **The files are the ones we published.** In the folder with the files run
   `sha256sum -c --ignore-missing SHA256SUMS.txt` (macOS: `shasum -a 256 -c --ignore-missing SHA256SUMS.txt`).
   Every file you have should say OK. The list covers the Parquet files and the source PDFs too (put the PDFs in
   `../pdf/` to check them).
2. **The source PDFs are the Senate's.** Each one's SHA-256 is above and in manifest.json; compare it with a copy
   you get from the Senate.
3. **Every amount cites its page.** `senate_pdf_url` opens the report at the page that prints the row;
   `house_pdf_url` and `nep_pdf_url` open the House bill and the NEP at theirs.
4. **Every page link prints its project.** For each project the build opens the Senate, House bill and NEP page it
   cites and looks for the project's name there (allowing for OCR misreadings in the NEP). The checks give how many
   pass; senate-2027-page-misses.csv lists any that don't, to check by hand.
5. **The totals add up.** senate-2027-checks.csv lists every check the build ran: each program's House bill and
   Senate totals against the totals the annexes print, the row arithmetic, the General Summary's own sums, and our
   line-by-line Senate amounts against the General Summary. The build stops if one fails.
6. **Rebuild it.** The code is public: `npm run build:senate-cr` with the report's PDFs in /data/senate-cr-2027/raw
   reproduces these files from commit `b6cca85d0dc66f93521ec5684a66be2c137ad395`.

Found a wrong figure? https://github.com/bettergovph/ai-reports/issues (give the file, the row and the page).

## Conventions

- Amounts are integer pesos. The report prints the General Summary and Annex A in thousands; we multiply by 1,000.
- An empty cell means none or not known, not zero.
- Names are as printed, including the documents' spelling. `title` is the report's name for a project.
- CSVs are UTF-8 with a byte-order mark. The Parquet files hold the same rows with their types.
- Pages: `*_page` is the page of the PDF file (what `#page=` opens); `house_printed_page` is the number printed on it.

## senate-2027-projects

The four programs whose projects the report lists one by one: Annex A-1 to A-4.

| program | |
| --- | --- |
| dpwh | DPWH projects (Annex A-4) |
| fmr | DA farm-to-market roads (Annex A-1) |
| hfep | DOH Health Facilities Enhancement Program (Annex A-2) |
| nia | NIA projects (Annex A-3) |

| Column | Meaning |
| --- | --- |
| program | dpwh, fmr, hfep or nia |
| id | our id for the row (a House bill project's id; `senate-<program>-N` for a Senate insertion) |
| house_id | the House bill project's id; empty for a Senate insertion |
| status, status_label | what the Senate does to it (below) |
| title | the project's name in the Senate committee report (the House bill's when it isn't listed) |
| house_title | the project's name in the House bill |
| renamed | the report gives it a revised name |
| matched_by | how the row was matched: the annex's own name (exact, prefix, fuzzy, ...); `rename_pair`, an insertion paired with the removed House project it revises; `restored_nep`, an insertion that is an NEP project the House bill doesn't have; `possible_duplicate` / `same_facility`, an insertion that looks like a House project (not merged) |
| check_id, check_note | the project it was paired with or looks like, and what to check |
| region, office | where; regions in one form ("Region IV-A", "CAR") |
| program_line, pap | the program line, or (HFEP) the kind of budget |
| nep_php, house_php, senate_php | the amount in each version; empty when the version doesn't have it |
| vs_house_php, vs_nep_php | Senate minus the House bill, Senate minus the NEP |
| inserted_by_house | in the House bill with no NEP line |
| replaces_id | for a Senate insertion that revises a removed House project (a corrected name or coordinates), that project |
| senate_doc, senate_page, senate_pdf_url | the annex and the page that print it |
| house_doc, house_page, house_pdf_url | the House bill volume and page |
| nep_doc, nep_page, nep_pdf_url | the NEP volume and page |
| page_url | the project's page on budget.bettergov.ph |

| status | |
| --- | --- |
| `cut` | Removed |
| `reduced` | Reduced |
| `raised` | Raised |
| `added` | Inserted by the Senate |
| `restored` | Restored from the NEP |
| `renamed` | Renamed |
| `unchanged` | Unchanged |
| `nep_only` | NEP only |

The annexes print a corrected House project as a removal plus an insertion, and an NEP project the House dropped as
an insertion. We pair them back: an insertion and the removed House project it revises (same region; names at least
85 similar, or 75 with the same amount and municipality; or the annex's own link) become one renamed, raised or
reduced project; an insertion that is an NEP project (names at least 90 similar, or 85 with the NEP amount; HFEP: the
same facility and component) becomes `restored`. Insertions that still look like a House project are flagged in
`check_note`, not merged. senate-2027-pairings lists them all.

A House bill project the annex doesn't list is unchanged: the annexes list every changed or renamed row. NEP-only
rows are NEP projects with no House bill line; they are in neither the House bill nor the report.

## senate-2027-annex-a

Every row of Annex A, as printed. **Don't add its rows up**: the report prints some amounts at more than one level
(a new project under its heading, its region and its office, each with the same amount), `TOTAL` rows repeat their
expense classes, and `kind` = object rows break a class down by object of expenditure. For department and agency
totals use the General Summary. Two rows print an increase with no name (SUCs: Apayao State College and Ifugao
State University, Annex A pp. 42-43, +1,000 thousand each, above "Supplies and Materials Expenses"); they are kept as
printed, with an empty `label`.

| Column | Meaning |
| --- | --- |
| department_id, department_no, department, agency_no, agency | where in the bill |
| kind | `class` (an expense class: PS, MOOE, CO, ...) or `object` (an object of expenditure under it) |
| is_total_row | a `TOTAL` row, the sum of the classes above it |
| label | the class or object as printed |
| printed_heading | the text the report prints above the row (its line breaks joined with " / ") |
| house_bill_path | the House bill line it matches, as the House bill names it |
| status, status_meaning | how the row matched the House bill (below) |
| deleted | the report strikes the line |
| instruction | the report's instruction for the row ("Between lines 36 and 37, insert ...") |
| nep_php | the same line's amount in the NEP |
| house_php, increase_php, decrease_php, net_php, senate_php | as printed (decrease is negative) |
| house_doc, house_pdf_page, house_printed_page, house_line, house_pdf_url | the House bill line the report cites |
| senate_page, senate_pdf_url | the page of Annex A that prints it |

| status | |
| --- | --- |
| `exact` | matched to the House bill line the report cites |
| `exact_nearby` | matched to a House bill line a page or a few lines from the one cited |
| `new` | not in the House bill: the Senate inserts it |
| `new_class` | a new expense class on an existing House bill line |
| `unmatched` | the House bill line it cites was not found |
| `ref_only` | the House amount the report prints differs from the House bill's |
| `no_hb_table` | no House bill table to match it to |

## senate-2027-general-summary

| Column | Meaning |
| --- | --- |
| level | total; department; agency (these add up to their department); sub-agency (breaks an agency down: "G.1" under "G"); group heading (a heading over agencies already listed, SUCs' "Region IV - Southern Tagalog and Palawan"); corporate budgets (printed after the departments: three DOE-attached corporations' budgets, not appropriations) |
| department_no, department, agency_no, agency | as printed |
| nep_php | the department's NEP total (departments only) |
| house_php, increase_php, decrease_php, net_php, senate_php | as printed, in pesos |

## senate-2027-provisions

| Column | Meaning |
| --- | --- |
| part | special or general provisions |
| department, agency, volume | where in the House bill |
| house_printed_page, house_lines | the House bill page and lines it amends |
| instruction, amended_text | the amendment, as printed |
| house_doc, house_pdf_page, house_pdf_url | the House bill page |
| senate_page, senate_pdf_url | the page of Annex B |

## senate-2027-checks

| Column | Meaning |
| --- | --- |
| check | what was checked |
| ours | our figure (a sum, or the count of rows that pass) |
| printed | the figure it must equal (the report's printed total, or the count of rows checked) |
| difference, ok | ours minus printed; whether they are equal |
| source, note | where the printed figure comes from; what differs, if anything |
| blocking | a failed blocking check stops the build; page-link checks are reported, with their misses listed |
