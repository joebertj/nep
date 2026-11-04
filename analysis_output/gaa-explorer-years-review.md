# GAA Explorer historical-year coverage review

Reviewed 2026-11-02 against the public manifest and the all-years Parquet snapshot (`gaa-2000-2026.parquet`). The manifest snapshot is stored at `data_sources/gaa-explorer-manifest.json`; the 73 MB Parquet was kept in `/tmp` for inspection and is not part of the repository.

## What the source contains

The all-years file has 5,432,425 records. The row grain is `program_operunit_fund_expense_object`, but DPWH `fpap_dsc` often contains a project title/location, and `operunit_dsc` contains a district engineering office in recent-enough years. Multiple rows can describe one appropriation line because amounts are split by expense object/fund; they must be grouped before counting projects or comparing amounts.

DPWH named-line coverage from the Parquet, grouped on the available FPAP key/title (coverage diagnostic, not a final project count):

| FY | Distinct named FPAP keys | Title keyword hits: flood/drainage | MPB | Bridge | Road/highway | DEO names |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2009 | 2,563 | 59 | 2 | 145 | 1,104 | 0 |
| 2010 | 2,632 | 55 | 18 | 158 | 1,083 | 0 |
| 2011 | 2,767 | 15 | 0 | 52 | 109 | 0 |
| 2012 | 3,497 | 39 | 0 | 375 | 497 | 0 |
| 2013 | 4,569 | 108 | 7 | 469 | 719 | 0 |
| 2015 | 13,660 | 986 | 3,652 | 491 | 3,509 | 197 |
| 2016 | 14,118 | 1,289 | 810 | 521 | 3,662 | 197 |
| 2017 | 29,268 | 2,800 | 3,646 | 1,147 | 7,141 | 198 |
| 2018 | 20,597 | 2,280 | 4,670 | 981 | 5,615 | 189 |

The keyword counts are rough screening counts. They do not confirm category or unique scope. The source has source URLs and raw source text for these rows, but generally no PDF page numbers. FY2009–2013 also lacks operating-unit/DEO names in this dataset.

## Pages that can gain project-history years

- **MPB / MPB Barangay:** FY2015–2018 are promising additions; titles include barangays and DEOs. FY2009–2013 can be screened by title/location, but without DEO and with uneven title coverage. Repeat/upgraded-level labels must be recalculated across the added years, not carried over as-is.
- **Flood-control:** FY2015–2018 have many title-level candidates and can extend the annual pattern/review. FY2009–2013 have substantially fewer keyword hits and need the older-title classifier checked. Keep title-keyword hits as candidates, not confirmed flood-control projects.
- **Repeats / historical title recurrence:** FY2009–2013 and FY2015–2018 can expand title-history search. Amounts must be aggregated by appropriation key; matching must preserve municipality/province and chainage/scope checks. Earlier rows lack DEO names.
- **Cost per km / cost matching:** FY2015–2018 appear usable for chainage-title screening and project amounts after expense-object aggregation. The 2009–2013 titles are also candidates, but need a separate check of title structure and amount consistency before inclusion.
- **Integrated / integrated-district reports:** FY2015–2018 include operating units and could support an added historical DEO allocation series. FY2009–2013 do not include DEOs in this data. Do not attribute these older amounts to individual legislators without a reliable year-specific district/member crosswalk.
- **Budget Innovations:** the source has project/category descriptions in `fpap_dsc`, so its GAA search window could extend beyond FY2020–2025. Its broader cross-agency keyword counts need to query all departments and be recalculated under one stated scope; a DPWH-only extract is insufficient for that page.

## Years to exclude or separate

- **FY2014:** the manifest only has 358 rows for a published summary; DPWH is a single aggregate row without named projects.
- **FY2019:** the source is explicitly marked as editions-differ. It has only 38 DPWH rows and no named DPWH project titles in the inspected data; the technical DPWH total differs materially from the Volume I summary. Keep it out of project-history matching until reconciled.
- **FY2000–2008:** the manifest marks these as partial historical coverage. DPWH is represented by only one to four rows per year, mostly aggregate controls rather than project titles. They cannot support the project-level pages.
- **FY2001, FY2004 and FY2006:** no new GAA was enacted (reenacted budgets); zero rows must not be charted as zero appropriations.

## Recommended extension

Add FY2009–2013 and FY2015–2018 as a clearly identified historical project-title layer, keeping the nine years separate from the current FY2020–2026 source until amount aggregation and cross-year matching are validated. Add FY2015–2018 first to MPB, flood-control and repeat-history pages; then include FY2009–2013 only in title-based history where the missing DEO field does not invalidate the analysis. Use the full 2000–2026 manifest for separate national/department-level trends only, with partial and reenacted years visibly marked.

This review establishes source availability and likely page fit. It does not yet alter public page numbers or imply that every old FPAP title is a single project; a normalized extraction and page-specific reconciliation are needed before publication.

## MPB source-repository cross-check · 2026-11-02

### Ten available fiscal-year slices for MPB RTS

BetterGov’s GAA Explorer manifest and Parquet assets provide usable, named DPWH project rows for FY2017 and FY2018. I fetched `gaa-2017.parquet` and `gaa-2018.parquet` from the public asset directory and verified both SHA-256 hashes against the manifest. FY2017 has 5,885 DPWH title candidates matching the MPB wording rule below, totaling ₱8,625,449,000; FY2018 has 4,504, totaling ₱18,497,375,000. All source rows retain FPAP code, title, operating-unit office, DBM source URL/workbook sheet, and source hash. The source does not provide printed page numbers for these rows.

The candidate rule was checked against the current integrated-project classification: title text must contain “multi-purpose” (including spelling variants) and “building”, “bldg” or “facility” within 60 characters. It matched every FY2020–FY2026 row already classified as Multi-purpose building in the integrated dataset. It remains a title classifier, not confirmation that each line is a standalone building. The extract is stored at `data_sources/mpb-historical-2017-2018.json` and is now an input to `build_mpb_barangay.py`.

The MPB barangay page now covers ten available fiscal-year slices: FY2017, FY2018, and FY2020–FY2027. FY2019 is a visible gap, not a zero: the GAA Explorer manifest marks its editions as differing, and its 11,393-row snapshot has only 38 DPWH aggregate/object rows with no named DPWH project FPAP titles. The refreshed MPB snapshot classifies 48,326 rows; 31,094 link to an official barangay and enter the rankings, while 17,232 remain unlinked. Linked allocations total ₱213,997,808,000 before overlapping multi-barangay links. These remain allocations and title-based review signals, not verified spending or physical buildings.

### What the two site repositories add

- BetterGov’s [`open-data-visualization`](https://github.com/bettergovph/open-data-visualization) repository contains FY2020–FY2025 detailed GAA Parquet data, the FY2026 amendment slice, and an MPB-to-DPWH-Transparency cross-match. Its `static/data/mpb_top_buildings.json` has 3,778 FY2026 target lines and 11,469 match links to 5,001 distinct DPWH Transparency contract IDs. Two-digit contract-ID prefixes span 2016–2025, ten years. The associated matching script selects up to five candidates per FY2026 line at a 0.65 weighted-title threshold. This is a useful contract-history lead set, not a complete ten-year GAA project ledger or proof a contract built the named structure.
- BetterGov’s [`open-budget-data`](https://github.com/bettergovph/open-budget-data) repo describes its detailed budget records as NEP/GAA FY2020–FY2026. It does not supply the missing pre-2020 named DPWH history by itself.
- The csiiiv [`DPWH-NEP-HB-2027-ANALYSIS`](https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS) repo’s `analysis/data/mpb_legislative_index_2027.json` is a FY2027 map/lens artifact, not a historical series. It scopes 6,123 comparison rows to the MPB PAP/title, includes coordinates on 1,827 rows (2,069 points), and reports MPB placements in 223 districts. It is useful for cross-checking FY2027 map placement and unmapped points, not for supplying earlier GAA years.

Repository snapshots checked: BetterGov open-data-visualization `0ed79131520e`, BetterGov open-budget-data `db1b6c28b30b`, and csiiiv `1bfd187c9089`. Source-data commit ids and the GAA manifest/file checksums are retained in the extraction metadata where applicable.

## FY2019 DPWH source correction · 2026-11-03

The FY2019 GAA Explorer baseline is still edition-differ and aggregate-only for
DPWH project titles. That does not mean the enacted FY2019 GAA lacks a named
DPWH schedule. DBM's Technical GAA DPWH PDF was downloaded from the official
site and parsed from its selectable text layer:

- `research_downloads/philgeps_dime_2019gaa/fy2019-gaa-dpwh-technical.pdf`
- `data_sources/gaa_2019_dpwh_technical/lines.json`
- SHA-256: `2a2e5dc4271394777ba9fbe6fbc8a2fc344c7a25fb7b7fd02d22a207912693fe`

The 1,527-page PDF yields 21,751 unique UACS-coded lines, including overlapping
program controls and detailed rows. Its printed DPWH new-appropriation total
is ₱454,016,273,000. Do not sum all extracted rows: parent/group amounts and
their detailed lines overlap. The source has been added to the historical
district project series using 13,254 specific-code title-classified lines
(road, bridge, flood control, and MPB). Existing geographic rules uniquely
assign 10,253 lines (₱107,965,359,000); 3,001 lines (₱97,592,654,000) remain
unresolved. Those figures cover the four classified families, not the full
DPWH GAA.

The MPB title filter yields 6,598 specific PAP lines totaling ₱24,006,119,000
before location assignment. 3,973 lines link to barangay identities
(₱12,029,712,000); 2,625 remain unlinked. The contractor MPB inventory now
includes all 6,598 FY2019 lines regardless of location resolution. These are
GAA allocations, not contractor awards or expenditures; DIME and PhilGEPS
evidence remains separate and only matches by the existing title/year rules.

Historical project records, district allocations, flood-control family
comparisons, repeats, MPB/MPB Barangay, and the contractors MPB baseline now
include FY2019 where their title/location scope allows. Cost-per-meter remains
limited to its FY2026 GAA versus FY2027 HGAB model; the full FY2019 schedule is
available as a separate searchable dataset for future length review. The earlier
FY2019 exclusion notes in this review referred to the Explorer snapshot and
are superseded for DBM's technical DPWH schedule.

## GAA page year coverage rollout · 2026-11-02

The available full DPWH annual project data remains FY2020–FY2025, with FY2026 enrolled-copy rows on the pages that use that source. The only pre-2020 project extract currently present in this workspace is the title-classified MPB subset for FY2017 and FY2018 used by MPB RTS. A request for the public GAA Explorer all-years Parquet returned HTTP 403, so no new general DPWH annual rows could be imported during this update.

Unavailable years now appear as disabled placeholders in the GAA-year filters on Historical district allocations/project records, historical GAA repeat comparisons, the flood-control pattern comparison, and MPB RTS. Disabled years are not passed into filters, charts, comparisons, averages, rankings, or exports. Pages without a year filter show the same coverage note alongside the FY2026–FY2027 comparison. The notes distinguish partial/aggregate source years, reenacted budgets, edition conflicts, years without named project detail, and years whose compatible full-year extract is not loaded.

- FY2000–FY2008 are excluded because the manifest marks them partial; DPWH appears only as aggregate/control rows. FY2001, FY2004, and FY2006 had no new GAA and are not treated as zero years.
- FY2009–FY2013 contain named DPWH titles in the Explorer baseline, but this district dataset has no reconciled extraction and those records lack DEO names. They remain excluded from district attribution and other page computations.
- FY2014 has no named DPWH project rows in the inspected source snapshot.
- FY2015–FY2018 contain project-level DPWH rows in the Explorer baseline, but a complete annual extract is not loaded into the integrated, flood-control, repeat, or cost-per-meter datasets. MPB RTS alone uses its extracted FY2017–FY2018 MPB rows; it does not imply complete DPWH coverage for those years.
- FY2019 is excluded because published editions differ and the inspected snapshot contains no named DPWH project titles.

The new placeholders document coverage gaps; they do not add fabricated zero-value observations. Existing FY2020–FY2027 values and computations remain scoped to their actual loaded data.

## FY2015 source correction · 2026-11-03

DBM's official FY2015 archive contains `GAA2015/DPWH.csv`, a structured account-detail export. The member was extracted by HTTP byte ranges, preserving the 8.77 MB raw CSV and its SHA-256 in `data_sources/gaa_2015_dpwh_technical/`. The source has 29,091 DPWH account rows. Capital-outlay object rows sum to ₱283,461,895,000; all DPWH account classes sum to ₱303,164,052,000. The parsed output groups capital-outlay rows by PAP title, implementing office, region, and fund source. PAP codes are not unique project IDs.

FY2015 title classification identifies 8,080 road, bridge, flood/drainage, or multi-purpose-building PAP groups. These are research candidates, not a count of unique physical projects. The historical district dataset now includes 8,080 classified rows (725 uniquely assigned; 7,355 unresolved). The MPB subset has 3,477 rows totaling ₱10,013,638,000 before location assignment; 1,783 are linked to barangays with ₱4,585,730,000. The contractors inventory retains all 3,477 FY2015 MPB candidates. Repeat matching does not yet include FY2015: the broad PAP title and non-unique code structure needs a separate exact-title reconciliation before it can enter repeat counts. The FY2015 source page is `gaa-2015-dpwh-technical.html`; the separate data JSON is linked from that page.
