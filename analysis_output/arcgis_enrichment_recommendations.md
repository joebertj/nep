# ArcGIS enrichment candidates — not selected for feature download

Collection is restricted to the user's selected services. The whole-catalog
job was removed and its legacy CLI mode disabled. Existing downloaded data is
retained. At most two selected-feature workers run, with shared request pacing.

## Highest priority: schemas inspected

### Cost and condition: minimal complementary set

- **Keep the already selected Number_of_Lanes.** Its layer schema includes
  `NUM_LANES`, `WIDTH_START`, `WIDTH_END`, `SLAB_THICK`, `RECENT_STHICK`,
  `PREV_STHICK`, pavement/surface type, reconstruction/surfacing years,
  `SECTION_ID`, segment bounds and directional flow. These are the same field
  names inspected in Carriageway_Width. Do not add Carriageway_Width,
  Surface_Type or Year_of_Last_Surfacing just for those overlapping fields.
  Matching schemas alone do not establish identical rows or coverage; revisit
  only if a specific gap or newer survey is demonstrated. Number_of_Lanes layer
  metadata cites April 2022, while its service cites June 2020; preserve both.
- **Road_Condition_with_No_Assessment is the main additional candidate.** It
  adds condition, VCI, assessment year/comment and segment-level identifiers.
  Keep unassessed roads unknown. Added to the selected download queue following
  the user's approval.
- **Kilometer_Post is an optional linkage aid**, rather than another cost
  measure: it can anchor stationing to road/route/section identifiers. Added to
  the selected download queue following the user's approval.
- The selected detailed bridge inventory already provides bridge dimensions,
  lanes and condition. Separate thematic bridge layers need a demonstrated
  coverage or vintage advantage before selection.

For cost calculations, distinguish allocation per route-meter, allocation per
funded lane-meter, and allocation per funded square meter. Existing inventory
lanes/widths must not be substituted for the lanes/widths actually funded by a
project, especially widening, shoulder works and partial rehabilitation. Keep
unknown scope unknown and compare like work types and pavement structures.

### ODV condition screening reviewed

`open-data-visualization/generate_condition_risks_cache.py` already compares
FY2026 allocations against 2025 road/bridge condition inputs. It groups funded
Good/Fair-only matches separately and lists Bad/Poor segments without a matched
project. Its modulo-1000 stationing fallback, even with geography guards, is
not reliable enough for confirmed segment attribution. Reuse the idea with
verified road/section IDs, compatible stationing and positive segment overlap;
retain fallback matches as provisional. Do not transfer its categorical
“Redundant”, “Justified”, or “No Project Assigned” labels as established facts.
Good/Fair roads can legitimately receive preventive or non-pavement work, and
no matched project does not establish that no funding exists elsewhere.

The two local ODV inventory parquet files were inspected: road inventory has
road ID/name only; section inventory adds region, DEO, functional classification,
section ID and length. The condition parquet paths are referenced by ODV's
script but were not found locally during this review.

The following earlier candidate list is retained as context; the minimal-set
recommendation above supersedes its priority for Carriageway_Width.

1. **Kilometer_Post** — `ROAD_ID`, `ROUTE_ID`, `SECTION_ID`, `KM_POST`, `LOCATION`,
   road name, province, DEO and congressional-district fields. Useful anchors for
   chainage-to-location resolution and repeat-scope checks. Matching station
   numbers on different roads must never imply overlap.
   Source: https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/Kilometer_Post/FeatureServer
2. **Carriageway_Width** — section ID and segment bounds; start/end widths;
   surface/pavement type; surfacing and reconstruction years; surface/slab
   thickness; lane count and directional flow. Supports better road-cost peers
   and possible area-based comparisons only when the funded width and work
   scope agree with the inventory. Inventory width is not automatically funded
   construction width. Layer copyright cites April 2022: verify vintage.
   Source: https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/Carriageway_Width/FeatureServer
3. **Road_Condition_with_No_Assessment** — `CONDITION`, `VCI`, `YEAR`, `COMMENT`,
   segment bounds, road/route/section IDs and surface fields. Can contextualize
   rehabilitation and resurfacing allocations, preserving unassessed segments
   as unknown rather than assigning good condition.
   Source: https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/Road_Condition_with_No_Assessment/FeatureServer

## Additional catalog candidates: inspect schema and dates before selection

4. **FloodControl_Data_Completed** and **DPWH_Flood_Control_Projects** — candidate
   records for comparing funded flood-control sites with earlier completed works.
   Completion, project IDs, scope, dates and coordinate reliability need review;
   proximity does not establish repeated work.
   Source: https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/FloodControl_Data_Completed/FeatureServer
5. **DA_FMR_FY2024_LiveView**, then earlier FY2021–2023 live views — candidate
   historical spatial inventories to complement FY2025 and the existing budget
   repeat screen. Check actual coverage and status/date semantics; do not count
   duplicate view versions as independent projects.
   Source: https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/DA_FMR_FY2024_LiveView/FeatureServer
6. **Flood_Control_25_Year** — candidate hazard/context layer for location-based
   funding review. Verify whether this represents modeled hazard, project
   coverage or another concept before deriving needs claims.
   Source: https://services1.arcgis.com/IwZZTMxZCmAmFYvF/ArcGIS/rest/services/Flood_Control_25_Year/FeatureServer

## Avoid redundant downloads

The selected bridge inventory already includes length, width, condition, age,
spans, piers and lanes. Separate Bridge_Age and Bridge_Condition thematic services
are lower priority unless they add a different verified vintage or fields.
Carriageway_Width also contains the information suggested by standalone
Surface_Type and Year_of_Last_Surfacing names. Compare schemas/coverage with the
already selected Number_of_Lanes and National_Road_Network before downloading
more overlapping road inventories.

Road_Condition_with_No_Assessment and Kilometer_Post were added to the feature
download queue following user approval of the minimal complementary set.
Other earlier candidates remain metadata-review suggestions only. No catalog
source here has established a suitable additional NIA, HFEP or DepEd dataset.
