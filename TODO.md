# TODO

## Page maintenance

- [ ] Propagate the FMR Budget 2027 menu entry through the remaining 42 page builders; currently only archive, connectivity, FMR, and FMR archive outputs show it.

## Miagao research

- [x] Crawl BetterGov public research pages and process local ODV data for Miagao-related records; publish the 583-row source inventory at `analysis_output/miagao-bettergov-inventory.json` with reproducible builder `build_miagao_bettergov_inventory.py`.

## Builder ownership

- [ ] Refactor `build_external_reference_review.py --refresh-pages`, which directly rewrites unrelated NIA, HFEP, DPWH, FMR, cost, repeats, Congress, and summary pages. Move page fragments into modules called by each owning builder.
- [x] Make the HGAB revision refresh order explicit: shared data builders run first, then the DPWH comparison, its dependent HGAB page, and the other page owners.
- [ ] Audit shared-data side effects in `build_hgab_revision_pages.py`; it still prepares published JSON for multiple page owners.
- [ ] Audit shared published-data writes in `build_fmr_dataset.py` and move non-FMR outputs to their owning builders/modules.
