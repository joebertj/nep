# TODO

## Split remaining multi-page report builds

The listed pages currently pass the shared table presentation checks. The remaining work is builder ownership: page-specific output should be owned by that page's builder, with shared behavior imported as modules.

### Menu pages · prioritize

- [ ] `integrated-district-allocations.html` — extract a page-owned build entry point from `build_integrated_district_reports.py`.
- [ ] `mpb-barangay.html` — separate its output from the multi-output MPB build.
- [ ] `mpb-historical.html` — extract a page-owned build entry point from the MPB historical/report build.
- [ ] `mpb.html` — separate its output from the multi-output MPB build.

### Not in the menu · lower priority

- [ ] `gaa-2015-dpwh-technical.html` — identify its current writer and give it a page-owned build entry point.
- [ ] `gaa-2019-dpwh-technical.html` — identify its current writer and give it a page-owned build entry point.
- [ ] `gaa-2019-volume-ia.html` — identify its current writer and give it a page-owned build entry point.
- [ ] `integrated-district-totals.html` — extract a page-owned build entry point from `build_integrated_district_reports.py`.
- [ ] Audit all page build entry points and scheduled refresh order; confirm that running one page builder cannot rewrite another page.
