# Surface, condition and prior-surfacing cost context

## Implementation

`road_asset_context.py` joins the downloaded condition schedule by exact road
section ID and supported section-local measure ranges already established by
the lane/kilometer-post matcher. Range partitions prevent double-counting
overlapping inventory claims. Missing, conflicting and unassessed cells remain
unknown. Surface type uses `SURFACE1` from the road-condition inventory. Pavement
subtype and last-surfacing year use the older lane inventory and retain that
provenance.

The cost page shows surface/material, recorded condition and assessment year,
and last-surfacing year in relevant road/bridge rate tables and CSV exports.
Separate program, surface, condition/year and priority-review filters support
peer inspection. High per-meter screens now also require the same supported
surface/condition/year group; unknown-context records remain explicitly
unadjusted and are never pooled with known-context records.

## Review rules

- **Rehabilitation on Good/Fair recorded roads:** rehabilitation, reconstruction
  or major repair; the full matched range must have a known pre-budget
  assessment year and only Good/Fair condition. This is a source-review lead.
- **Recent recorded surfacing:** eligible pavement work with a positive
  last-surfacing year over the whole matched range, within five budget years of
  FY2027 (2022–2026). The threshold is a disclosed screening choice, not an
  engineering service-life standard. Missing/zero years are not reconstructed
  from construction, edit or copyright dates.
- Widening, approaches, slope/slip, drainage and off-carriageway scopes do not
  receive these points.
- Good/Fair bridge ratings are separately reviewable, but their missing
  assessment dates prevent a dated-condition ranking point.

The supplied road assessments all report 2025. The lane archive's latest
reported last-surfacing year is 2022; it does not describe all subsequent work.
A zero recent-surfacing count therefore does not establish that no projects
were resurfaced recently. FY2025 condition may have changed before FY2027 work.

## Affected outputs

Cost tables, inventory evidence JSON/CSV, rate peers, summary/index and Top 25
review queue are rebuilt. The two qualifying condition/recency flags can each
add a point; methodology explains their dependence and legitimate alternative
explanations. Undated bridge context adds no point. Historic FY2026 price
comparisons remain explicitly uncontrolled for surface/condition rather than
claiming an adjustment not established for both stages.

These are proposed allocations and recorded asset context, not measured
construction unit costs or findings that work is unnecessary. Later damage,
structural/safety requirements and different funded components can justify work
on a previously Good/Fair asset. Request original assessment, quantities,
designs, scope and prior completion records before drawing conclusions.
