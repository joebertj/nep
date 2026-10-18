# External analyst source review

Source: [https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS](https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS) · [workbench](https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#overview)
Pinned revision: `34ef5d8cbbacda92f6503ffd9a428569f157f64d` · fetched 2026-10-18T08:46:20Z

## Findings

### Reviewed source adoption and annex coverage

The external NIA House annex contains 828 project rows / PHP 17,999,305,000; the local detailed schedule contains 828 / PHP 17,999,305,000. The external NEP detailed annex is now available (791 rows). The reviewed extraction takes priority over older local automated parsing. Newly recovered rows are parser corrections, not budget insertions.

Affected pages: nia-irrigation.html, nia.html, summary.html

### Detailed baseline now available

The external HFEP NEP ledger contains 464 facilities, PHP 14,472,519,000. Printed control minus the facility ledger is PHP 140,000. Preserve that discrepancy; do not manufacture a balancing row or treat unmatched facility names as certified insertions.

Affected pages: hfep.html

### House reading control cross-check

External House controls contain 16,270 second-reading and 16,275 third-reading allocations; net operations change PHP 134,000,000. Local count and allocation controls agree: True. Repeated-key comparison groups are not the same grain as their member allocations.

Affected pages: dpwh-hgab-comparison.html

### Methods and stages differ

The external retained NEP/House comparison uses the SECOND reading and reports 5801 unmatched House candidates and 1341 unmatched NEP candidates. Our principal analysis uses the THIRD reading. Chainage/re-scoping fallbacks consume some external pairs; differing stations and altered geography still require independent review. The earlier 5,837/2,139 figures are not a current target.

Affected pages: dpwh-hgab.html, congress.html, summary.html

### Shared source limitation

The external source verification manifest records comparison_ready=False. Balanced arithmetic does not certify every OCR title, amount, source scope or project identity. Its NEP review queue includes 3,193 pending checks; these are not confirmed extraction errors.

Affected pages: dpwh.html, dpwh-hgab.html, repeats.html, congress.html

### Agreement on unresolved cases

Of our 4 unmatched FAP lines, 4 also remain house_unmatched in the downloaded comparison. External narrative and matching JSON can differ; retained row statuses must be checked before assuming every FAP loan has a counterpart. Keep unresolved cases separate and provisional.

Affected pages: dpwh-hgab.html

### Review before changing cost denominators

Compared with our imported FMR ledger, 0 records have changed data/review fields, including 0 with changed coordinate arrays. Numeric repairs, review flags and new provenance must be reconciled before changing distance-based rates or geographic attribution. The update report lists every changed source row.

Affected pages: fmr.html, cost-per-km.html, cost-matching.html

### Different screening populations

The external chainage table includes flood control, local/FAP scopes and three source stages. Its length counts cannot be compared directly with our selected domestic roads/bridges/FMR denominator. Chainage-derived funded extent and endpoint distance remain distinct.

Affected pages: cost-matching.html, cost-per-km.html

## Additional source-derived research leads

Other Irrigation System: NEP PHP 3,000,000,000 versus House PHP 460,000,000; change PHP -2,540,000,000. These are external printed-annex controls, not project identities or proof of a transfer.

2. LGU Hospitals: NEP PHP 2,428,391,000 versus House PHP 5,558,546,000; change PHP 3,130,155,000. Opposing movements do not establish a direct transfer or service consequences.

3. DOH Hospitals: NEP PHP 9,509,703,000 versus House PHP 3,131,703,000; change PHP -6,378,000,000. Opposing movements do not establish a direct transfer or service consequences.

## Refresh workflow

Run `python3 update_csiiiv_reference.py --refresh-pages` to fetch the current selected files, verify hashes, rebuild this review and update the attributed panels. Use `--offline --refresh-pages` to reuse the retained snapshot. Reviewed NIA/HFEP/FMR source extractions are adopted with provenance; affected calculations are rebuilt. Cross-stage identity claims remain separate. Changes are recorded in the manifest and adoption JSON.

Downloaded source code is retained for reading, never executed. Snapshots are private and ignored by Git; the manifest, downloader and findings are retained. Existing identical files are referenced rather than duplicated.

## Coordinate updates

- nep: 0 changed records, 0 removed IDs; 704 total. Full before/after values in JSON.
- hgab: 0 changed records, 0 removed IDs; 964 total. Full before/after values in JSON.
