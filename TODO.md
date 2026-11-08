# TODO

## UI data loading

- [ ] Replace deferred whole-dataset requests with static, page-sized chunks. Fetch only the active table page while keeping chart and summary data small. Order: `cost-per-km.html`, `cost-matching.html` (source shared with `cost-per-km.html`; page owner `build_cost_matching_page.py`), then `mpb.html`.

## Large JSON assets loaded by pages

Use a 10 MB maximum for each published shard. Check each fetch path before splitting; do not shard analysis-only inputs or files fetched only after an explicit download.

- [x] Reduce existing `dpwh-in-depth-shards/` chunks to 10 MB. The DPWH data builder invokes the splitter; other scripts read the index and chunks without rewriting them.
- [x] Keep `connectivity-data.json` under one owner, `build_connectivity_report.py`. The cropland raster pass now writes measurement/map inputs only; the connectivity page builder merges the measurements into public data.
- [ ] Next: shard `contractors-data/index.json` (48.64 MB). `contractors.html` fetches it on page load; keep ranking/filter summaries usable while deferring detailed contractor records. Owner: `build_general_contractors.py`; shared shard writer: `build_contractors.py`.

Remaining live JSON candidates over 10 MB, checked 2026-11-08:

| Size | Asset |
|---:|---|
| 43.56 MB | `mpb-barangay-data.json` |
| 35.65 MB | `integrated-project-data.json` |
| 34.76 MB | `barangay-historical-data.json` |
| 28.81 MB | `cost-per-km-data.json` |
| 17.80 MB | `lane-cost-evidence.json` |
| 16.71 MB | `congress-district-review-data.json` |
| 16.53 MB | `mpb-data.json` |
| 15.07 MB | `mpb-barangay-base-data.json` |
| 14.88 MB | `connectivity-venues-data.json` |
| 13.94 MB | `dpwh-data.json` |
| 13.23 MB | `dpwh-hgab-comparison.json` |
| 12.27 MB | `mpb-proximity.json` |
| 11.62 MB | `mpb-municipality-boundaries.json` |
| 11.37 MB | `out-of-place-boundaries.json` |
| 10.59 MB | `hgab-document-coverage.json` |
| 10.37 MB | `connectivity-road-projects.json` |

## Builder ownership

- [ ] Audit remaining page build entry points and scheduled refresh order; verify that each page builder cannot rewrite another page or another page's published data.
