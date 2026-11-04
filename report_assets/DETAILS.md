# Linked project Details

`table_readability.js` keeps every source-table field in a dialog and calls
`project_evidence_details.js` for linked evidence. MPB map cards and the flag
evidence dialog use the same reader. Existing links that open project pages keep
their own navigation.

`build_project_evidence.py` reads public report datasets and their referenced
source tables. It publishes an external manifest and 256 title buckets in
`static/nep-preview/project-evidence/`; project data is not embedded in HTML.
Only explicit source identifiers or complete normalized titles are accepted.
Available fiscal year, stage, district and exact allocation context narrow title
matches. Different occurrences remain selectable, and source amounts are never
added together in a popup. Explicit counterpart identifiers retrieve supporting
NEP/Transparency records. Long project and bill lists use pagination.

The export uses a public field allowlist. Private SEC/person records and raw
document signatory lists are excluded. Representative cards contain only the
public geographic roster context already used by the reports.

After refreshing report or parser snapshots, run from the NEP workspace:

```sh
python3 refresh_linked_project_details.py
```

This refreshes linked data and asset cache versions without applying menu
templates. It asserts that each page's existing navigation is preserved.

The current congressional roster is loaded through
`analysis/enrich_nep_preview_representatives.py:roster_rows` with the separately
sourced `static/data/20th_congress_roster_corrections.json`. Run
`verify_congress_portraits.py` to verify/cache image responses, rebuild the
district report, and then run `sync_current_congress_context.py` to synchronize
public roster labels and photo sources. The photo audit records image loading
verification separately from roster identity matching and inactive membership.
