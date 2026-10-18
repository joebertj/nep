# csiiiv primary working dataset source

Source: [FY2027 DPWH / NEP / House workbench](https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/#overview)
and [GitHub repository](https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS).

## Research direction

Use upstream as the primary working data provider across NEP/HGAB/GAB/Bicam/GAA
when each stage is available. Focus local work on complementary, actionable
project-level evidence. See [source strategy](../../SOURCE_STRATEGY.md) for the
division of work, audience, migration status and case-file requirements.

## Update

From the private NEP repository:

```sh
python3 update_csiiiv_reference.py --refresh-pages
```

This fetches the current selected JSON, methods and application source views,
adopts the documented reviewed extraction for NIA, HFEP and FMR, then rebuilds
affected calculations and attributed supporting panels in NEP and ODV. It does
not commit, push or deploy. Human corrections take priority over conflicting
older local automated parsing. Cross-stage project identity and geographic
attribution remain separate from extraction quality; no claim is made that
every source row was individually reviewed by a human.

To reuse the current snapshot without network access:

```sh
python3 update_csiiiv_reference.py --offline --refresh-pages
```

Download only: `python3 download_csiiiv_reference.py`.
Reconciliation only: `python3 build_external_reference_review.py`.
The normal report finalization also refreshes these panels when a snapshot is
available, so subsequent builds do not erase the attribution or caveats.

## Storage and reproducibility

- `manifest.json`: last complete snapshot; commit, URLs, Git blob hashes,
  SHA-256, local paths, changes since previous fetch and potentially affected pages.
- `manifests/<commit>.json`: retained successful manifest history. Failed attempts
  use an `-incomplete` suffix and do not replace the last complete manifest.
- `snapshots/<commit>/`: downloaded JSON, documentation, frontend views and
  extraction/matching source code. Snapshots are ignored by Git. Unchanged
  files can reference earlier snapshot paths instead of storing another copy.
- `analysis_output/external_reference_review.json` and `.md`: local reconciliation.
- ODV `static/nep-preview/external-reference-review.json`: public supporting
  evidence used by attributed panels on relevant pages.

At most two concurrent downloads. Each downloaded artifact must match its Git
blob hash; JSON must parse. Only repository-listed paths are selected. There is
no whole-catalog GIS download, PDF mirror, Git history download, execution of
third-party code, or adoption of archived/superseded project ledgers. The current
snapshot contains 235 selected files, about 368 MB before filesystem deduplication.
The existing byte-identical local NEP FMR audit is reused.

## Coverage and limits

The web fetcher could not render the SPA directly. The scan therefore uses the
repository's current React workspaces (DPWH, FMR, NIA, HFEP, geographic views,
source/resource catalogs), their data builders, current JSON and methodology
documents. This is a source/data review, not a browser interaction check.

The snapshot supplies detailed NEP NIA and HFEP annex ledgers absent from our
older inputs. These are separately attributed derived sources, not replacements
for primary PDFs. The review records the NIA House scope gap, HFEP printed-control
residual, FMR coordinate changes, DPWH reading-control agreement, differing
matching methods and unresolved FAP cases. Arithmetic checks do not certify
project identity or the source's interpretation of every OCR cell.

## Preferred source policy

`source_policy.json` records the preferred reviewed extraction and accepted
revision. `adopt_csiiiv_reference.py` replaces the older NIA irrigation ledger,
retains the detailed NEP NIA/HFEP baselines, and adopts reviewed FMR normalized
coordinates and audits. It preserves original source rows, manual correction
history and unresolved flags. Earlier local inputs remain under ignored
`accepted_prior/<commit>/` directories. Bounded local text equivalence is checked
before transferring a House annex from the second to the third reading.

Public accepted rows and adoption provenance are exported as
`reviewed-annex-baselines.json` and `reviewed-source-adoption.json`. The detailed
NIA page now uses 828 House rows and six comparable NEP/House controls, replacing
the old 423-row automated subset. HFEP funding/category comparisons use the
reviewed facility ledgers, with the documented NEP PHP 140,000 residual intact.
