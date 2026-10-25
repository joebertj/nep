# PH location DB · Philippine location, LEG and DEO evidence

Private SQLite database in NEP. All source access is confined to NEP and ODV.
ODV continues serving static reports; this database does not change public
rankings or deploy anything.

## Build and inspect

### Matched inventory IDs on road/bridge tables

The cost builder exports `matchedInventoryId` from supported lane/bridge
matches. `matched_inventory_ids.py` combines those matches with screened
physical-asset contexts using exact full titles; conflicting ID claims stay
unresolved. The shared table asset adds an inventory ID column to other project
tables with supported matches, including labelled current/prior IDs where both
comparison sides match. Native cost columns are preserved. Filtered CSV exports
include the same IDs. Identifiers are road `SECTION_ID` or `BRIDGE_ID`, not
ArcGIS OBJECTIDs, HGAB occurrence IDs or evidence of funded quantities.

### Road/bridge surface and condition context

`road_asset_context.py` enriches the cost build from exact inventory asset and
section-measure matches. `build_cost_per_km.py` calls it through the shared lane
inventory reader, then refreshes the contextual peer groups and source exports.
The condition inventory reports 2025 assessments. Last-surfacing years come from
the older lane inventory; zero/missing years stay unknown. Methodology, matching
IDs, coverage percentages and assessment years are published with each match.
Fully assessed Good/Fair rehabilitation and full-range five-budget-year
surfacing screens can add review flags to the combined queue. Undated bridge
condition remains contextual, with no dated-condition point. None of these
screens proves unnecessary work, overpricing or incorrect prioritization.

### Inventory-assisted project locations

```sh
# Geometry build requires Shapely; no network access.
python location_data/build_inventory_locations.py
python3 location_data/import_inventory_locations.py
python3 location_data/build_congress_db_review.py --write-scope-review
python3 ../open-data-visualization/analysis/build_congress_allocation_data.py \
  --write --geographic-decisions analysis_output/congress_location_db_review.json \
  --audit analysis_output/congress_geographic_attribution_db_3rd.json
python3 build_congress_leg_insertions.py
python3 build_investigation_summary.py
python3 location_data/enrich_report_tables.py
```

Exact bridge IDs and measured road alignment ranges can supply project-specific
location context. Full measured alignment coverage is required, with one
municipality and a 25-meter clearance. Bridge points need the full inventory
span plus 25 meters of clearance, since the inventory point might be an endpoint.
Bridge labels must agree with the containing municipality/province. Explicit
source location contradictions, multiple places and unresolved current-map or
PH location DB identities prevent assignment. Municipal geometry repairs also
require manual review. Source geometry remains EPSG:32651 throughout this build.

The resulting `inventory_location_contexts` DB table is project evidence, not a
replacement administrative hierarchy or a whole-municipality LEG membership.
The public `static/data/inventory_location_contexts.json` is consumed by the
shared geography resolver. It rechecks current map consensus and disables the
fallback if dependency hashes change. It never uses the polygon's old LEG label.
The same resolver supplies report table names. Historical rows receive current
geographic context, not historical representative claims. Existing scope holds
continue to apply, including the multi-place Butuan/RTR project.

`congress_inventory_location_update` JSON/CSV records every additional HGAB
assignment against `congress_before_inventory_locations.json`. The builder
rejects source ID/title/amount differences and changes to existing assignments.
Its public method section explains coverage gains without attributing funding
control, sponsorship or personal receipt.

### Downloaded DEO–LEG boundary evidence

```sh
# Requires Shapely 2.2 in the chosen Python environment; reads cached JSON only.
python location_data/build_boundary_crosswalk.py
python3 location_data/import_boundary_crosswalk.py
python3 location_data/query_locations.py --deo 'Bulacan 1st DEO'
```

The overlay writes `analysis_output/deo_leg_boundary_crosswalk.json` and CSV.
It preserves all positive-area intersections; touching edges alone are excluded.
Intersections below 10,000 square meters or 0.1% of either boundary are marked
for small-intersection review, not silently dropped. Area fractions describe
the polygons and must never be used to split project allocations. Geometry
repair flags, hashes, source object IDs, CRS and copyright dates are retained.

The importer adds `boundary_deo_leg_evidence` and `boundary_locality_evidence`
to PH location DB. Exact qualified identities can link to existing IDs, while
unmatched or conflicting names remain unresolved. Municipal source codes are
preserved without declaring them current PSGC. All effective dates remain NULL.
Existing accepted LEG memberships, representative assignments and public budget
totals are not changed by this evidence import. The normal database rebuild
also imports the generated evidence when present; it needs no geometry package.

To assess whether boundary evidence can improve the existing Congress attribution:

```sh
python3 location_data/build_congress_db_review.py
python3 location_data/assess_congress_boundary_evidence.py
```

The second command compares the native HGAB IDs, titles and amounts against the
project attribution audit before generating `congress_boundary_accuracy_review`
JSON and CSV. It separates matching labels, boundary disagreements, unresolved
LEG identities and unassigned rows with candidates. It approves no assignment
from legacy boundary labels alone and does not change public HTML or rankings.

HGAB headline office/program counts and insertion filters are generated with:

```sh
python3 build_dpwh_hgab_headlines.py
```

The FAP review rebuild also calls this after removals and allocation adjustments.
Breakdowns join source IDs to the printed program labels; they do not infer
implementing offices from project locations. Domestic insertions stay separate
from unpaired FAP review records. CSV filters and ranking charts use the same
selected rows. The builder reconciles each count and peso subtotal to its input.


The name of this database is **PH location DB**. It supports Philippine
location disambiguation across agencies and budget stages, rather than NEP
alone. The existing SQLite filename is retained for script compatibility.

To refresh representatives across all 11 static reports and their CSV exports:

```sh
python3 location_data/enrich_report_tables.py
```

This rebuilds names from the database's 20th Congress source claims and the
strict qualified-location screening rules. It replaces old guesses and DEO
fallbacks. Existing unknown-date historical membership claims do not create
new assignments. A shared static asset updates legacy and dynamic table cells
after rendering, while a CSV adapter preserves each existing export's full
filtered rows and adds/refills the same names. Only CSV Blob creation in the
11 reports uses the adapter; the browser's global Blob implementation remains
unchanged. Province aggregate labels indicate province-wide roster context;
project labels indicate that project's geographic coverage. Names on historic
rows are current-roster context, not claims about the historical member.

`ph_location_representative_audit.json` inventories pages, tables and refreshed
data rows. Include `ph-location-representatives.js` with the generated public
pages and data when committing ODV. Rerun enrichment after rebuilding pages.

`python3 build_congress_leg_insertions.py` generates the potential additions
per LEG summary, ranking chart, selected-district project table, and full CSV
exports in `congress.html`. It replaces the former three-district view and
keeps total accepted HGAB lines separate from insertion candidates. The old
`build_congress_focused_insertions.py` command delegates to this builder.
Regenerate the scope-reviewed Congress audit first. Shared/unresolved
locations and FAP records stay outside LEG insertion totals; zero candidates
are not evidence that a district received no additions.

```sh
python3 location_data/build_database.py
python3 location_data/query_locations.py --summary
python3 location_data/query_locations.py --name Quezon
python3 location_data/query_locations.py --name Quezon --level locality --province Quezon
python3 location_data/query_locations.py --name Puerto --level barangay --municipality 'Cagayan de Oro City' --province 'Misamis Oriental'
python3 location_data/query_locations.py --leg Quezon --district 3rd
python3 location_data/query_locations.py --deo 'Bulacan 1st DEO'
python3 location_data/investigate_butuan.py
python3 location_data/build_database.py  # imports the generated edge cases
python3 location_data/query_locations.py --case HB10858-3-0447-006385
```

The builder uses Python's standard library. It builds a temporary database,
checks SQLite and foreign-key integrity, and atomically replaces the prior
database after a successful import. `build_summary.json` inventories every
source, its import disposition and limitations. File hashes are stored in
`sources`. A rebuild recreates the database; source-derived place IDs are stable
for an unchanged type, parent context and normalized identity.

## Identity and hierarchy

- Names are lookup labels. IDs include geographic level and parent context.
- Administrative areas that are named in project titles but are not barangays
  use `static/data/administrative_locality_crosswalk.json`. Malate, Manila is
  stored as a Manila administrative district and linked to the Fifth District;
  the separate Malate barangay under Palayan remains unchanged. The strict
  title resolver uses the parent-qualified entry when coordinates are absent.
- Province **Quezon**, municipality **Quezon**, **Quezon City**, and barangays
  called **Quezon** are distinct candidates. Directions and punctuation remain.
- Accent and case variants share a lookup key; accent folding does not force
  identity merging. City of X / X City aliases are
  restricted to a city identity; they do not erase province or municipal levels.
- Unclassified municipality/city names use `locality`. Conflicting type claims
  remain separate and are surfaced for review instead of being silently merged.
- Province IDs are anchored to the country for stability across region changes.
  Region membership is stored separately with source evidence. Use
  `province_region_review` to see an unambiguous region claim or a conflict.
- Independent cities retain their geographic parent as a source claim. This
  relationship is not a statement that they belong to the province's LEG seat.
- Source-specific geographic codes are labeled by their scheme. Legacy rainfall
  P-codes and GeoJSON reference numbers are **not asserted to be current PSGC**.
- Region, province and place counts include old names, disputed classifications,
  unqualified records and source variants; they are not official totals.

## LEG, representatives and DEOs

`leg_districts` preserves the jurisdiction and district designation. Coverage
is in `leg_memberships`; source conflicts are visible in
`leg_membership_review`. A coverage claim can have a NULL place ID and several
candidate place IDs. It is retained even when it cannot be safely located.

Representatives and source term claims are separate. Personal names are scoped
to a LEG identity; identical names in different districts are not automatically
the same person. Source-provided year ranges are retained without inventing
exact dates. Unknown dates remain NULL. Raw representative text is retained
even when historical text must be split into several term claims.

`deos` and `deo_leg_claims` support multiple LEG districts per DEO and multiple
DEOs per LEG district. The existing PDF transcription supplies 108 reference
links, with its stated thousands-of-pesos unit converted to pesos. The scan's
fiscal year/stage and individual page numbers are unknown and remain NULL.
A printed dash represented as zero is noted in the raw record. These amounts
are **not attributed to HGAB projects**. HGAB office observations identify
administrators; they do not establish coverage or ownership of every project.
The `deo_place_claims` table is available for documented coverage; this build
does not invent that coverage from office names or district numbers.

## Sources and conflicts

Imported source families include the nationwide merged hierarchy, local
barangay hierarchy, cached geographic database, GeoJSON metadata, province
locality caches, explicit metropolitan aliases, legacy rainfall crosswalk,
primary/generated district maps and backups, BARMM overrides, the 20th Congress
roster, historical representative coverage, PDF crosswalk transcription and
HGAB office observations.

Backups share their source family. The merged nationwide file is derived from
other local maps and is not independent confirmation. Its Parquet/DuckDB copies
are inventoried but not counted as new evidence. Project rankings and automated
matching caches are reference-only, not boundary evidence. Original external
administrative/election repositories are not accessed.

`multiple_local_claims` is descriptive, **not verified membership**. Unknown
effective dates mean that claims cannot automatically establish the boundary
applicable to FY2027. Historical conflicts should be reviewed by time period,
not resolved by majority vote. Fuzzy matches are not accepted as identities.

## Next use

### Congress page evidence audit

```sh
python3 location_data/build_congress_db_review.py --write-scope-review
python3 ../open-data-visualization/analysis/build_congress_allocation_data.py \
  --write --geographic-decisions analysis_output/congress_location_db_review.json \
  --audit analysis_output/congress_geographic_attribution_db_3rd.json
python3 build_report_heroes.py --page congress.html
```

The private audit matches full adjacent municipality/city + province fields
against exact DB aliases and records all candidate identities and LEG source
claims. It does not promote undated claims into current district assignments.
Existing supported assignments retain the prior conservative crosswalk rules.
Recorded construction-scope issues can hold an accepted allocation unresolved;
each hold must match the source ID, full title and amount.

Only supported scope holds are copied to ODV's small static
`congress_location_scope_reviews.json`. Its builder consumes that snapshot by
default, so a normal rebuild retains the correction without accessing the
private SQLite database. Public pages remain static. Changes to the source
must be reviewed before regenerating that snapshot.

### Follow-up: representatives across report tables

After location enrichment, use this evidence database to supply representative
names to district/location tables across all 11 report pages, including
`congress.html`. Keep the public reports static; perform enrichment in the
private build pipeline and copy generated results to ODV.

Resolve project locations through barangay → municipality/city → province
context, then apply dated LEG membership and representative-term claims.
Province splits require separate predecessor/successor identities, dated
lineage and municipality transfers; an old province name is not automatically
an alias for either successor. Unknown boundary dates stay unresolved.

DEO identity alone does not establish the project's legislative district.
Distinguish construction segments from route endpoints and qualify repeated
names at every geographic level. Show multiple names only when the evidence
supports multiple covered districts; show no name when location, boundary or
term is uncertain. Retain source provenance and unresolved cases for user
review. Representative names indicate geographic coverage, not sponsorship
or responsibility for a project. Generate consistent names in tables and CSV
exports without changing allocation totals solely to add names.

Historical GAA names can now enrich the evidence database:

```sh
python3 location_data/build_database.py --with-gaa
# Or add/refresh the historical tables in an existing database:
python3 location_data/import_gaa_names.py
python3 location_data/query_locations.py --gaa Butuan --limit 10
python3 location_data/query_locations.py --review RTR
```

This uses the locally installed DuckDB CLI to read ODV's FY2020–FY2025 GAA
Parquet files and the FY2026 DPWH enrolled-copy extract. FY2026 coverage is
DPWH only, and its title column may contain wrapped fragments. Descriptions
are grouped by exact agency, department and region context with original row
counts and locators retained; these are not certified project counts.
Only existing exact place aliases produce candidates. Adjacent geographic
fields can supply historical parent evidence; names do not create places or
LEG boundaries. Route endpoints remain distinct from construction segments.

`gaa_name_import_summary.json` reports coverage; `gaa_location_review_queue.csv`
groups unresolved classification questions. User answers are retained in
`manual_location_decisions.json` with explicit title/year scope. The confirmed
RTR interpretation applies to the two titles asked about and does not assign
their entire allocations to Remedios T. Romualdez. Unanswered cases remain
unresolved. A base rebuild without `--with-gaa` omits these addon tables.

The exact-name query provides candidate places and evidence. A project resolver
still needs to classify each mention's role, establish a qualified geographic
chain, review applicable LEG boundaries and dates, and distinguish project
locations from route endpoints or road/bridge names. Only reviewed mappings
should feed a subsequent congressional allocation rebuild.

## Refinement: short names and historical provinces

```sh
python3 location_data/import_gaa_names.py --reclassify
python3 location_data/refine_database.py
python3 location_data/query_locations.py --ambiguity Isabela
python3 location_data/query_locations.py --lineage Maguindanao
```

Reclassification keeps historical evidence IDs, original titles, source locators
and year/context records; it refreshes name mentions and review groups. Short
names and numbered barangays require explicit geographic markers. Marked
`Brgy. 122` can use an existing `Barangay 122` identity; bare numbers never
establish a geographic chain. All matching retains exact parent context.

`qualified_alias_candidates` and `alias_ambiguity_review` expose collisions
across levels and parents. `administrative_transition_review` records proposed
predecessor/successor identities separately from aliases. A shared province
base name with del Norte / del Sur creates only a review candidate. It does
not establish a legal split, date, municipality transfer or current LEG
boundary. NULL dates stay NULL. Historical GAA mention years are title
evidence, not effective dates. Old province names are never expanded to
successor provinces automatically. A base database rebuild includes these
review views; the standalone command can refresh an existing database.

These refinements do not regenerate Congress allocations or public reports.

User-confirmed Santo Niño / Sto. Niño / Sto. Nino / corrupted Sto. Ni±o
spellings are recorded in `name_spelling_decisions.json`. Run
`python3 location_data/apply_spelling_decisions.py` to apply them to existing
identities; refinement and base/import builds also consume the decision.
Only complete place names (or explicit barangay labels) qualify. IDs, levels
and parent locations remain distinct, including same-named barangays in
separate municipalities. This answers a spelling question, not LEG coverage
or construction scope. Existing historical mentions can be refreshed with
`import_gaa_names.py --reclassify`; source titles are retained verbatim.

Congress spelling reapplication uses `qualified-location-consensus-v3-confirmed-spelling`
in ODV's strict matcher. Complete Santo Niño variants are canonicalized only
inside geographic field and marked-barangay matching. Both local LEG maps
must still agree; canonical collisions with different seats remain conflicts.
Original project titles and source IDs are preserved. The private before/after
assignment audit is `analysis_output/congress_spelling_reapply_changes.json`.
After a Congress rebuild, regenerate the hero and LEG insertion view, then
refresh report-table representatives before copying/committing static files.

## Shared address metadata and comparison location guard

`location_text.py` is the PH location DB's canonical address-text helper.
`refine_database.py` stores the version, rule definitions and source hash in
`location_text_rules`. Export it with `sync_location_rules.py`; ODV's
`analysis/ph_location_text.py` is a generated copy. Its strict Congress
matcher consumes this helper; the NEP/HGAB matcher consumes the private copy.
Original source titles and chainage remain intact. Only complete trailing
station fields or Philippine-range decimal coordinate pairs can be separated
from an address. Bare road names and route endpoints never prove a LEG.

`project_location_scope.py` uses DB aliases and exact province/municipality
parent links to veto comparisons with conflicting explicit locations. Complete
marked barangay fields remain distinct even when local barangay inventory is
incomplete. Compound routes remain review cases. A possible spelling variant
can prevent a veto; it does not establish project identity or LEG attribution.
The same guard is used for forward matching and reverse removal screening.

For a local analyst export such as the 100 Nueva Ecija 1st DEO records:

```sh
python3 location_data/reconcile_deo_insertions.py
```

This reconciles full title + allocation + physical PDF page to native HGAB
records before comparing local NEP statuses and strict LEG assignments. Office
coverage is not treated as LEG ownership. The JSON/CSV includes unmatched
source lookups, candidate matches, unresolved locations and accepted district
assignments. The external analyst's insertion labels are not adopted.

## Nationwide analyst evidence enrichment

```sh
python3 location_data/import_analyst_candidates.py
python3 location_data/query_locations.py --analyst Licab --limit 10
python3 location_data/query_locations.py --analyst 'Dupinga Sabo Dam'
```

The importer reads the 100-row Mika export and `all_house_only_candidates.json`.
It preserves full external records and source hashes in `analyst_candidate_evidence`,
links exact native allocations in `analyst_native_links`, and records existing
parent-qualified identities in `analyst_location_candidates`. These are location
evidence, not new aliases, funded construction segments or legislative boundaries.
The base DB rebuild includes the importer when these local files are available.

Comparison rows and allocation records are counted separately: a complete
identical-occurrence group can link two native allocations without assigning an
arbitrary occurrence. FAPs remain separate; a `region` header never becomes a
project. Truncated or disagreeing titles, parenthesized address metadata, missing
municipality context and unresolved LEG/scope claims enter `analyst_location_review`.
Refreshes preserve manually changed review statuses. Original titles stay intact.

`analyst_candidate_import_summary.json` inventories source and link counts;
`analysis_output/*_location_evidence.json` and the accompanying review CSVs retain
row-level provenance. External insertion assertions are compared with our own
NEP/HGAB statuses, never adopted as truth. The user-confirmed Gabadlon → Gabaldon
correction is scoped to the Dupinga Sabo Dam title, FY2027 HGAB 3rd Reading and
Nueva Ecija; it creates no global alias. This import does not rebuild or deploy
public pages or change congressional totals.

The shared address parser v5 accepts complete final parenthesized coordinate
pairs (optional degree signs, Philippine bounds) and balanced STA/K/KM/chainage
lists, including parenthesized signed offsets. It separates these annotations
only for address lookup. Interior annotations, route endpoints, mixed comments,
multiple coordinate pairs and malformed parentheses remain in the source text.
Coordinates never establish a district; station ranges still constrain project
matching through the original title. Parsed address observations retain the
original title, separated metadata and any title-scoped correction decision.

### Crosswalk PDF provenance

The contributor confirmed on 2026-10-11 that `DPWH per district.pdf` came from the Philippine Center for Investigative Journalism (PCIJ). The file hash and attribution basis are recorded in `crosswalk_pdf_provenance.json`. Credit is displayed in the congressional report footer. Budget stage and boundary dates remain unverified; this provenance confirmation does not change project attribution or allocation totals.
