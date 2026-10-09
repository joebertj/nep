# PH location DB · Philippine location, LEG and DEO evidence

Private SQLite database in NEP. All source access is confined to NEP and ODV.
ODV continues serving static reports; this database does not change public
rankings or deploy anything.

## Build and inspect

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
