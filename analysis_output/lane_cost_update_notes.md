# Lane-meter cost enrichment

## Implemented

- `lane_cost_enrichment.py` reads completed local lane, bridge and kilometer-post
  inventories. No additional network requests or fuzzy road-name matches.
- Road matching uses exact section IDs or a full exact road name with compatible
  region/DEO and a unique section. Global K chainage maps to section measure only
  inside supported kilometer-post brackets. Conflicting lanes, incomplete
  coverage, unknown references and widening scope prevent a rate estimate.
- Three road titles supply explicit lane counts and stated lengths. Their
  title-stated allocation/lane-meter rates are displayed separately.
- 279 road records support inventory-normalized stated-length estimates.
- 753 bridge IDs match inventory records. Of these, 390 rehabilitation/major
  repair or strengthening/retrofitting records support an existing-asset estimate
  using inventory span × lanes. This denominator is not a recovered funded
  project length. Replacement, widening and new construction are excluded.
- Funded-length coverage is not increased by inventory asset spans. FMR lanes
  are not inferred from a national-road inventory.

## Presentation and rebuilds

The cost page includes lane coverage, methodology, source vintage, separate
graphs/tables and filtered CSV exports. Full evidence is also available as
`lane-cost-evidence.json` and CSV in ODV's static report directory; the private
copies use `lane_cost_evidence` filenames. Rates, unknowns, exclusions, inventory
object IDs, station-reference methods and source hashes are retained.

The summary, its index alias, Top 25 review queue, length-density analysis and
FY2026 per-meter comparison are rebuilt. Lane estimates are contextual evidence,
not new ranking points. Historical comparisons remain explicitly per meter;
neither stage has sufficient verified funded-lane quantities for a general
lane-adjusted inflation claim.

## Peer correction

Named overpasses, flyovers and viaducts now classify as bridge structures, even
when a title mentions the road on which the structure stands. Per-meter flags
also separate overpass/flyover, viaduct and pedestrian structure peer groups.
Burol Overpass no longer receives an ordinary-road peer comparison. Its current
structure/program/length group has insufficient peers for a high-rate finding;
the allocation and source range remain visible for scope review.

## Limits

These are appropriations, not measured construction payments or contract unit
costs. Existing inventory lanes do not prove funded lanes. Inventory vintage,
approaches, repair extent, terrain, width and quantities still matter. No absent
funded quantity is filled with an assumed two-lane road, whole bridge span,
nearby road or similarly named asset. Inventory estimates never replace the
title-based measure or enter per-meter flags.

Rebuild with `python3 build_investigation_summary.py`; its existing finalization
pipeline preserves the shared menu, hero styles, methodology and summary alias.
Generated outputs are copied to ODV for local review. No deployment performed.

## Matched-asset dimension recovery · October 18, 2026

Asset identity is now independent of rate eligibility. The cost page exposes
existing-asset lengths, lanes and widths in two filterable category tables,
with graphs and CSV exports. All dimensions and provenance also appear in the
full JSON/CSV evidence downloads.

- Roads: 596 line items have supported section identities; 595 have contiguous
  recorded inventory extents with usable length, lanes and width. One has
  internal gaps and aggregate dimensions are withheld. This is 9.18% of the
  6,482 road line items. The prior funded-range lane match count was 471.
- Bridges: 754 line items recover span and width (65.06% of 1,159), and 753
  recover lanes. Length no longer depends on a known lane count or eligible
  rehabilitation program. Previously only 390 eligible existing-asset rate
  records exposed span in the asset-length field.
- Asset lengths are available for 763 line items with missing stated funded
  length: 9 roads and 754 bridges. These remain missing in the stated-length
  coverage denominator. An inventory span or road section does not establish
  which portion is funded.
- The separately eligible existing-asset bridge lane-rate count remains 390;
  road funded-range lane-rate estimates remain 279. No additional price flags
  are manufactured from whole-asset dimensions.

Road interval unions count overlapping inventory records once. Effective lanes
and width are weighted over recorded measures; unknown/conflicting values or
internal gaps prevent aggregate values. Width interpolation uses the segment's
start/end widths. The recorded contiguous extent may not cover the entire road
section. All printed multiple-section titles are withheld from single-asset
recovery, rather than choosing whichever section happens to match.

## Matching/computation page split

`cost-per-km.html` now contains per-meter/lane-meter calculations, peer screens,
coordinate-based rate approximations, historical comparisons and density groups.
`cost-matching.html` contains inventory matching/dimensions, condition evidence,
length coverage, notation recovery and source-check/extraction methodology.
Both link directly to each other; the companion page is absent from the menu.
The summary coverage/source-check links now target the companion page. The
shared controls retain filters, sorting and CSV for each rendered table. Both
are generated together by `build_cost_per_km.py`; the underlying calculations
and coverage denominators are unchanged.

## Preferred reviewed source adoption

Documented human corrections in the csiiiv NIA/HFEP/FMR datasets now take
precedence over the older local automated extraction. NIA House coverage is
828 rows / PHP 17,999,305,000, replacing the incomplete 423-row subset.
The detailed NIA NEP baseline has 791 rows / PHP 17,598,181,000. Comparable
annex controls therefore increase by PHP 401,124,000. This recovery is an
extraction correction, not a count of legislative insertions.

Reviewed HFEP NEP/House facility baselines contain 464/513 facilities. The
NEP PHP 140,000 printed-control residual remains explicit. Updated FMR
coordinates retain every source repair and unresolved flag: 2 House coordinate
rows remain under review and none in NEP. Straight-line length approximations
now cover 962 of 964 House FMR rows; these do not replace stated road lengths
or enter the stated-length price flags. CSV project/point/segment views are
regenerated from the accepted coordinate JSON to avoid stale numeric values.

See `analysis_output/reviewed_source_adoption.json`,
`data_sources/csiiiv/source_policy.json` and `adopt_csiiiv_reference.py`.
The recurring update command adopts reviewed extractions and rebuilds affected
calculations before enriching and copying pages into ODV. Project identity and
geographic attribution remain distinct from PDF extraction correctness.
