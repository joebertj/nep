# DPWH contractors and the GAA lines their contracts carry

Built 2026-11-03 by budget.bettergov.ph (pipeline `scripts/dpwh-contracts/`, commit d4356a3e4e1b). Start from `manifest.json`: every file, its rows, size, SHA-256, URL and columns.

Independent and unofficial: our reading of DPWH’s contract list and the GAA, not an official record. Contractor names, license numbers, amounts and statuses are as DPWH’s list publishes them; amounts are contract amounts, not payments. DPWH does not publish which GAA line a contract carries: the links are our match by title, office and amount, and may be wrong. A contract, a total or a ranking alone does not establish irregularity or wrongdoing by any contractor, office or official.

## Sources

- DPWH’s contract list, from https://api.dpwh.bettergov.ph/projects (BetterGov’s cached proxy over DPWH’s transparency portal, repo bettergovph/api.dpwh), downloaded 2026-11-03: 267,292 contracts, FY2016–FY2026.
- The GAA for FY2020–FY2026, DPWH (department 18): every capital-outlay line with an amount, from the site’s GAA extract.

## How lines were matched to contracts

- A line is compared with contracts funded from the same year’s GAA (the year in `source_of_funds`).
- `one_to_one`: titles agree (token set ≥ 90 after expanding Brgy, Bldg, MPB…) and the contract is 50–102% of the line.
- `bundle`: one contract whose title takes in several lines, worth 50–102% of them together (DPWH “clusters”).
- District office lines are searched at their office, then their region (≥ 95); Central Office lines in every office.
- Guards: a road line’s first station must be among the contract’s stations; Package and Phase numbers must agree.
- Several contracts for one line (“splits”) were left out: a sample check found a third right. Unmatched lines stay unmatched.

## Results and accuracy

- FY2020–FY2025: 105,003 of 146,157 lines matched. FY2026 is low: many of its contracts are still for procurement.
- Sample check (`match-accuracy-sample.json`): 284 of 299 links confirmed by the contracts’ own component titles, which DPWH writes as “<type of work> - <title as in the GAA>”. By hand, about 1 in 100 one-to-one links is wrong.

| Year | GAA lines | Matched | In clusters | Share of the amount | Contracts funded |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2020 | 21,055 | 15,915 | 233 | 58% | 21,152 |
| 2021 | 28,422 | 17,483 | 287 | 50% | 22,769 |
| 2022 | 22,866 | 17,132 | 129 | 68% | 22,808 |
| 2023 | 23,263 | 17,234 | 168 | 68% | 24,528 |
| 2024 | 24,955 | 18,792 | 127 | 70% | 26,894 |
| 2025 | 25,596 | 18,447 | 122 | 63% | 24,434 |
| 2026 | 18,132 | 4,599 | 5 | 21% | 5,868 |

## Files

- `dpwh-contracts-2016-2026.parquet` / `dpwh-contracts-2016-2026.csv.gz`: Every contract in DPWH’s list as downloaded, all its list fields, one row per contract; with DPWH’s page for each. 267,292 rows.
- `dpwh-contractors-2016-2026.parquet` / `dpwh-contractors-2016-2026.csv`: One row per contractor (by license number): contracts, amounts by year, joint ventures, offices, GAA lines matched. 6,728 rows.
- `gaa-2020-2026-dpwh-line-contracts.parquet` / `gaa-2020-2026-dpwh-line-contracts.csv`: One row per GAA line and matched contract, with how it was matched. Our match, not DPWH’s record. 109,602 rows.
- `gaa-2020-2026-dpwh-lines.parquet` / `gaa-2020-2026-dpwh-lines.csv`: One row per DPWH capital-outlay line of the GAA, with its match status, contract and contractor. 164,289 rows.
- `match-accuracy-sample.json`: the sample check, every link sampled that a component title did not confirm.

## Conventions

- CSVs are UTF-8 with a BOM; the contract list’s CSV is gzipped. Parquet holds the same rows with types.
- Pesos: GAA amounts are whole pesos; contract amounts keep centavos. Empty means none, never 0.
- Each file’s link carries `?v=` and the start of its SHA-256: the data host caches files under fixed names.

## Rebuild and check

- `npm run build:hgab-contractors` (downloads DPWH’s list again, about 25 minutes; `REUSE=1` keeps the pages), then
  `npm run verify:hgab` (its `contractors/` section). Method: `docs/dpwh-contracts.md` in github.com/bettergovph/ai-budget.

## Also published (the JSON the site’s pages read)

- https://budget-assets.bettergov.ph/hgab/2027/contractors/index.json: Every contractor with its figures (cols + rows), for /hgab/2027/contractors.
- https://budget-assets.bettergov.ph/hgab/2027/contractors/c/NN.json: Each contractor’s contracts, in 64 files by FNV-1a(key) % 64 (src/lib/hgab-contractors.ts shardOf).
- https://budget-assets.bettergov.ph/hgab/2027/contractors/mpb-links.json: The matched contract, contractors and awarding office of each multi-purpose building map line.
- https://budget-assets.bettergov.ph/hgab/2027/contractors/summary.json: Totals, the match table by year, the builder’s checks and every site file’s SHA-256.
- https://budget-assets.bettergov.ph/hgab/2027/mpb-boards/boards.json: The four multi-purpose building leaderboards (src/lib/hgab-leaderboard.ts decodeMpbBoards).
