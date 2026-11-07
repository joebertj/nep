# Builder architecture TODO

Target: one HTML page owner per page. Shared transformations belong in importable modules called by that page's builder. Orchestrators may sequence builders but must not write HTML themselves.

## In progress

- [x] Refactor `build_hgab_revision_pages.py` to prepare revision data and render comparison markup without patching unrelated agency pages.
- [x] Refactor `standardize_nep_hgab_pages.py` into a no-write renderer/data helper; add separate builders for NIA irrigation and DepEd.
- [x] Add page-owned builders for the DPWH reading comparison and FMR, NIA, and HFEP reading overlays, plus a no-write orchestrator.
- [x] Move `dpwh-hgab.html` reading-stage transformations into its page module and one-page builder.

## Remaining cross-page writers from the audit

- [x] Move the shared hero formatter into `report_hero_module.py`, distribute each hero to its page builder, and disable the former multi-page writer `build_report_heroes.py`.
- [x] Move currency formatting into a pure shared module used by page renderers; disable the former all-page writer `format_report_currency.py`.
- [x] Move overlap data and script attachment into a shared module called only by DPWH HGAB, OO2 HGAB, and repeats page builders; disable `add_chainage_overlap_dialog.py`'s all-page injection.
- [x] Add reusable per-page table output checks and call them from each builder that formats report currency or attaches the chainage overlap viewer.
- [x] Audit `build_hgab_revision_pages.py` / `standardize_nep_hgab_pages.py`: these now prepare data or render page markup without writing unrelated pages; their page-specific builders own the outputs.
- [ ] `build_dpwh_fap_review.py` updates both `dpwh.html` and `dpwh-hgab.html`; extract shared rendering and let each page builder own its output.
- [ ] `build_dpwh_hgab_headlines.py` updates `dpwh-hgab.html`; fold it into the DPWH HGAB page owner.
- [ ] `build_dpwh_subtractions.py` and its downstream refresh chain: audit all HTML outputs and make each page output page-owned.
- [x] Mark `archive_higher_level_analysis.py` obsolete as a completed one-time migration and prevent accidental reruns.
- [x] Move non-summary investigation sections out of `build_investigation_summary.py`; each owning page builder now renders its own sections from current source data.
- [ ] Audit all page build entry points and scheduled refresh order; verify running an individual page builder cannot rewrite another page.
