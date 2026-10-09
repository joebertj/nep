# Congressional allocation recalculation

Source: FY2027 DPWH HGAB 3rd Reading. Workspace files only. The page now has one strict allocation chart and table; the DEO–legislative crosswalk remains a separate PDF reference.

## Accepted coverage

5,885 of 16,275 source line items pass the strict location rules. Accepted allocations: ₱154,459,302,000 (26.31% of the source schedule).

These are accepted matches under local map agreement, not complete district budgets or independently verified official boundaries. Missing coverage is uneven; do not infer a national budget ranking or project sponsorship from these totals. Shared allocations are excluded rather than duplicated.

## Investigated districts

| District | Previous strict attribution | Accepted after geographic review | Accepted lines |
|---|---:|---:|---:|
| Quezon · 3rd District | ₱11,460,256,000 | ₱350,000,000 | 13 |
| Cagayan de Oro · 2nd District | ₱8,802,003,000 | ₱674,000,000 | 33 |
| Ilocos Norte · 1st District | ₱5,498,300,000 | ₱4,672,900,000 | 322 |

## Source examples kept outside the ranking

- **Lopez Viaduct (FB50957LZ) along Maharlika Highway, Barangay Canda Ibaba - Barangay Pandanan, Calauag, Quezon** — ₱1,200,000,000; 3- HB 10858 FOR 3RD READING VOL I-C .pdf, page 294. Decision: Municipality district conflicts between local crosswalks.
- **Quezon Br. (B01191MN) along Dipolog-Oroquieta National Rd** — ₱210,000,000; 3- HB 10858 FOR 3RD READING VOL I-C .pdf, page 260. Decision: No exact administrative location at the end of the project title.
- **Puerto Princesa North Rd - K0022 + 700 - K0023 + 300** — ₱150,000,000; 3- HB 10858 FOR 3RD READING VOL I-C .pdf, page 156. Decision: No exact administrative location at the end of the project title.
- **Construction of Flood Control Structure along Iponan River, Canitoan Section, Sta. 0+180- Sta. 0+310, Sta. 0+490- Sta. 1+020, Cagayan de Oro City** — ₱231,000,000; 3- HB 10858 FOR 3RD READING VOL I-C .pdf, page 369. Decision: Multi-seat city lacks an explicit mapped barangay.

## Rebuild

```sh
python3 ../open-data-visualization/analysis/build_congress_allocation_data.py --write --audit analysis_output/congress_geographic_attribution_3rd.json
python3 build_report_heroes.py --page congress.html
```

The private JSON and CSV audit retain each source project ID, literal title, amount, source volume/page, accepted seat or unresolved reason, and geographic evidence. JSON also includes input and script SHA-256 digests.

No deployment performed.
