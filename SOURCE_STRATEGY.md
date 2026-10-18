# Source strategy and project-level investigations

## Direction

The primary working data provider for NEP → HGAB → GAB → Bicam → GAA is
[csiiiv's budget-analysis project](https://csiiiv.github.io/DPWH-NEP-HB-2027-ANALYSIS/app/)
and its [source repository](https://github.com/csiiiv/DPWH-NEP-HB-2027-ANALYSIS).
Official budget documents remain the underlying documentary evidence.

Our audience is technical readers and investigators seeking specific,
actionable project-level findings. Success means a lead can be reproduced,
located, checked against the funded scope and followed up with a precise
record request. Broad totals and public summaries help readers navigate;
they do not define the main research agenda.

## Division of work

| Work | Approach |
| --- | --- |
| Budget PDF/Excel extraction, source hierarchies, stage controls | Consume the upstream maintained datasets; give documented human corrections priority. |
| Stage matching and general allocation summaries | Reuse upstream outputs, identifiers and definitions where available. Explain differences in scope rather than maintaining a competing general analysis. |
| Chainage, repeated titles, coordinate normalization, annex comparisons | Upstream already covers these areas. Reuse its work and concentrate on verification or enrichment it does not supply. |
| Asset identification and funded extent | Add supported bridge/road IDs, distinguish the full asset from the funded segment, and retain uncertain endpoints and split projects. |
| Engineering context | Join supported length, lanes, width, surface, condition and assessment dates; compare compatible work scopes. Existing asset measurements are not automatically funded quantities. |
| Geographic attribution | Use the PH location DB with qualified barangay/town/province identities, current LEG/DEO mappings, historical changes and explicit ambiguity. |
| Investigation evidence | Connect selected budget records to inventories, procurement/contract records, bills of quantities, previous work and audit findings when available. |
| Individual leads | Produce reproducible case files, supporting and contrary evidence, and specific next checks. |

Areas in the lower rows are priorities for a coverage check, not a blanket
claim that upstream has no related work. Before building a feature, inspect
the current upstream source catalog and relevant workspace. Record exactly
what additional question our work answers.

## Source and update rules

1. Pin upstream revisions and retain URLs, hashes, original identifiers,
   source stage/year, units, raw labels, human corrections and remaining flags.
2. Prefer the maintained reviewed extraction to older local automated parsing.
   An arithmetic check supplements human source review; it does not outrank it.
3. Treat extraction correctness, cross-stage project identity, geographic
   attribution and a finding of wrongdoing as distinct questions.
4. Keep import adapters small. Do not build another general PDF parser or
   matching engine when an adequate upstream output already exists. A local
   extraction is justified by a specific missing record or reproducible source
   defect, documented against the original page.
5. A stage absent upstream remains explicitly unavailable. Do not infer GAB,
   Bicam or GAA from a different stage, or silently reuse an older reading.
6. Publish source links beside the derived evidence and preserve the revision
   that produced each result. Keep upstream corrections separate from actual
   changes between budget stages.
7. Retain existing reports during the transition. Source adoption is currently
   integrated for the NIA/HFEP/FMR annex inputs; the remaining DPWH source and
   matching paths still need migration to upstream identifiers and outputs.
   This policy does not claim that migration is already complete.

## Next work, in order

1. **Complete the source migration.** Map current DPWH occurrences to upstream
   source IDs and consume its stage ledgers. Reconcile amounts, scope and
   classification changes while retaining old versions for traceability.
2. **Build the project case-file format.** Each case should contain:
   - upstream source ID/revision and exact stage/year;
   - original title, amount, units, PDF page and source link;
   - qualified location and supported asset ID;
   - stated funded segment versus inventory span/alignment, including lanes,
     width, condition and evidence dates;
   - the specific discrepancy and reproducible calculation;
   - plausible alternative explanations and contrary evidence;
   - missing documents and a concrete next verification step;
   - status: unresolved, explained, supported discrepancy, or corrected data.
3. **Pilot with well-supported cases.** Prioritize exact asset IDs and adequate
   scope evidence: rehabilitation quantities, repeated funded segments,
   near-coincident building coordinates, or conflicting inventory context.
   Check existing upstream coverage before selecting each case.
4. **Enrich only where it changes the decision.** Seek procurement details,
   engineering drawings, quantities, completion histories and dated condition
   assessments for the selected cases instead of collecting unrelated datasets.

## Presentation

Lead with the exact project and the evidence a reader can act on. Provide
original rows, formulas, units, exclusions and downloadable data. Show unknowns
and contrary evidence beside the issue. High allocation or multiple screening
flags alone do not establish an unnecessary project or wrongdoing. Names and
roles remain in tables/graphs, not narrative allegations.

Existing broad summary pages can remain as navigation into the detailed
findings. New work should earn its place by adding evidence or a concrete
verification step beyond the upstream analysis.

## Higher-level overview archive

`archive_higher_level_analysis.py` records the existing committed report revision
and HTML checksums, retains private byte-for-byte HTML snapshots, and generates
`static/nep-preview/archive/index.html` with immutable Git source links. The
archived Git revision includes the matching datasets and assets. This avoids
publishing another large, duplicate copy of the same datasets.

Current pages replace the named duplicate overview panels with links to
csiiiv. A small display adapter retires these panels after legacy page scripts
initialize, allowing their project-level tables and controls to keep working.
Source/methodology paragraphs and data downloads remain accessible. No project
rows, repeat evidence, overlap diagrams, asset/location evidence or cost
calculations are removed. Reading-level project rows remain locally available;
the main menu's stage-comparison entry goes to upstream instead.

The archival adapter runs in normal report finalization, before the summary
index alias is written. The first snapshot revision is retained rather than
being replaced on every subsequent build. This archival presentation change is
prepared locally after deploying the already-pushed reviewed-source release;
it still needs the user's normal ODV commit/push before git deployment.
