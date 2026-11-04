# FY2027 contractor manifest cross-check

Checked the downloaded manifest built **2026-11-03T07:20:36Z** against the local
[`contractors.html`](contractors.html), generated **2026-11-03T06:38:03+00:00**.
The relevant downloaded files are in `research_downloads/hgab2027_contractors/`.

## Manifest and download integrity

- Manifest contractor dataset: 6,728 contractor records; `6,728` rows in `index.json`; `6,728` rows in the contractors CSV.
- Contract extract: 267,292 rows, 250,722 with a contractor name; the raw rows sum to ₱6,619,647,704,687.96, within ₱0.08 of the DPWH API summary. The 16,570 rows without a contractor account for ₱16,380,678.12; the remaining named-contractor amount is ₱6,619,631,324,009.84, exactly matching the manifest contractor total.
- Manifest-linked data checks passed: **9/9** downloaded size/hash checks. The raw DPWH contract gzip, contractor CSV, archive, README, accuracy sample, and extracted Parquet files match their manifest hashes. The `index.json` and `mpb-links.json` hashes match the site summary.
- The public contractor CSV has 4 rows with no license ID; the names are still present as contractor records.
- The source itself reports successful consistency checks for unique keys, contract totals, index/shard counts, and linked-contract completeness.

## What matches `contractors.html`

- Local page: **43 contractors, 121 matched DIME projects**, covering FY2022 and FY2025. The page reports ₱854,000,000.00 GAA allocation and ₱1,074,553,433.79 DIME contract value.
- **38/43** local contractor names exactly match the remote contractor index. Five local names do not have an exact index-name match; they may be aliases or spelling variants, so I did not force a match.
- Of the 121 local DIME projects, **113** have one exact remote match on contractor license, contract year, and normalized project description. Seven have no remote contractor/year candidate; one has a candidate but a different description.
- Among the 113 exact project matches, **34 have the same contract amount and 79 differ**. For the differing rows, local DIME amounts total ₱683,484,869.96; DPWH-listed amounts total ₱485,744,740.30. The absolute sum of differences is ₱272,777,977.72; the largest single difference is ₱44,148,990.17. The row-level comparisons are in [`contractors_manifest_amount_differences.csv`](contractors_manifest_amount_differences.csv).
- These are DIME-versus-DPWH listed contract amounts for exact contractor/year/title matches. They are discrepancies to review, not proof that either source is wrong. The local page's DIME fields are explicitly attributed to DIME records.

## GAA MPB coverage does not reconcile yet

- The local page's source says it classified **38,457 GAA MPB rows** over **2016–2018 and 2020–2026**. In the shared FY2020–FY2026 window, the underlying ODV integrated-project snapshot contains **32,172 rows / ₱281,582,130,000.00** classified as `Multi-purpose building`.
- The remote board artifact reports **49,376 lines / ₱554,511,976,000.00** for FY2020–FY2026. That is **17,204 more rows and ₱272,929,846,000.00 more appropriation** than the local same-window classification. These totals are not directly equivalent until the source-row classifier/scope is reconciled.
- As a narrower text-level check, filtering the downloaded remote DPWH GAA lines for titles containing “multi-purpose building” yields **35,363 rows / ₱329,887,436,000.00**. **30,069** rows overlap local MPB rows by exact normalized title and year; all those overlapping rows also have equal amounts. That leaves **2,103 local-only** and **5,294 remote-only** rows under this narrower comparison. The remote title filter has no FY2024 results, while the local data classifies 292 FY2024 rows, which signals different classification rules.

## Interpretation

The two sources agree exactly on a large common set of GAA lines, but their MPB scopes and DIME/DPWH contract amounts do not fully reconcile. The local page is a focused DIME match list (43 contractors / 121 projects in 2022 and 2025); the remote manifest is a broader DPWH contract and GAA-line dataset (6,728 contractors; FY2016–FY2026 contracts and FY2020–FY2026 GAA linkage). It does not validate the local page's 510 unlinked PhilGEPS keyword rows or its cached AMO/PCAB annotations.

The manifest's match validation is a sample of 299 links, with 284 confirmed under its title-comparison rule. Its method also says split contracts are left out. Treat that as a quality check on its own DPWH-to-GAA links, not as a validation of the local DIME joins.
