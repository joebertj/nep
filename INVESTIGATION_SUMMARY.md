# Investigative summary build

```sh
python3 build_investigation_summary.py
```

Run after the source report data, current HGAB matching CSV, Congress audit
and representative enrichment are refreshed. It builds `summary.html` and
`summary-data.json` in ODV's static preview directory, copies the summary to
NEP `analysis_output`, and adds supporting sections to RCS, DPWH, the HGAB
screen, Congress and Budget Innovations. It updates the shared report menu
with a fixed height for eleven links. It does not deploy.

The talking-point ranking is editorial investigation priority. It is not a
probability of corruption, and overlapping allocations must not be added.
Published NEP and enacted GAA are the bookends; trace House HGAB, Senate GAB
and Bicam reconciliation before making a claim about the final budget.
Only NEP/House stages are currently traced here.

## Supporting analyses

- RCS: constant allocations versus variable rainfall proxies; province-first,
  per-office mean, and per-office median sensitivity models. All conserve
  199 budget units. Per-office weighting rounds back to one unit each, while
  province-first weighting moves 44 units on the present data. No meaningless
  correlation test is reported for constant allocations.
- Repeat screen: comparison pairs versus distinct FY2027 proposals; current
  amount counted once per source code; explicit chainage evidence separated.
- Exact ₱5M office co-occurrence: recomputed one-sided hypergeometric test,
  odds ratio and approximate Wald interval. Existing region-controlled
  permutation results are identified as existing analysis. These exploratory
  tests are not adjusted for post-selection or multiple comparisons.
- Insertion screen: native status partitions, parser limitations and a
  proposed stratified original-page adjudication study. Unpaired FAPs remain
  separate. Candidate counts are not certified additions.
- Congress: line/value coverage and confirmed multi-place exclusions. District
  amounts describe supported geographic attribution, not sponsorship.
- INSPIRE: observed appropriation history, without equating appropriation to
  spending or recurring funding to duplicated work.

## Repeat survival in HGAB

`build_repeat_stage_survival.py` is also runnable independently. It joins each
repeat candidate's source code to the API code carried by current native HGAB
comparison records. Only selected one-to-one links establish retention classes.
Potential links are separate; absent links do not establish removal. It emits
pair and unique-proposal counts, source hashes, full JSON evidence and a CSV
of every distinct proposal. The summary builder calls it automatically.

Current counts: 737 NEP–old GAA pairs / 686 distinct NEP proposals; 634 pairs
and 591 proposals have clear retained HGAB links, 55/50 have potential retained
links, and 48/45 lack a selected or cited counterpart. Treat these as parser
screening outcomes pending source/component verification.

The private Git deployment helper includes the summary, data and survival
exports in its release backup and health-check paths. The user commits/pushes
ODV and authorizes deployment separately.

## All-district reference comparison

`build_congress_benchmark.py` builds all district rows in the local Congress
roster using the same strict geography, candidate insertion and selected
counterpart rules. The summary builder embeds the ranking in Congress with
search, coverage/candidate filters, numeric metric sorting, ascending/descending
order and comparisons against the three reference districts. Undefined shares
sort last; numeric reference comparisons exclude them. Zero accepted attribution
does not mean zero funding. Party-list members have no geographic LEG district
in this view.

Charts follow the filtered ranking: top twelve vertical bars for count/value
metrics and a scatter plot for insertion share versus strictly attributed
allocation. The CSV exports every filtered row, not just the displayed page.
Reference rows use the same rules and are highlighted without defining a
normal allocation, threshold of misconduct or ranking of wrongdoing.

## Editorial evidence review

`python3 review_report_language.py` reviews all preview pages, applies the
shared evidence notice, removes unsupported probability wording, keeps the
HGAB methodology visible and inventories sensitive-term contexts. The summary
builder calls it after generation. Refresh the HGAB hero from current native
comparison data when rebuilding; source/data disagreements are material and
cannot be cured by a disclaimer.

The private audit is `analysis_output/report_language_review.json`. This is
not jurisdiction-specific legal clearance or a guarantee against a libel
claim. Named individuals are geographic roster labels, not findings of
sponsorship, personal receipts or responsibility. Allegations of unlawful
conduct require corroborating records and qualified legal review.

## MPB program page

`build_investigation_summary.py` rebuilds `mpb.html` and `mpb-data.json` using
`build_mpb_report.py`, then applies the shared menu and report styles. The summary
now contains six ranked findings. MPB is a subset of the existing DPWH findings;
its allocations overlap them and must not be summed as separate exposure.

The MPB page uses the exact BIP multi-purpose buildings PAP, rather than a keyword
search across programs. Its seven filtered graph/table views cover potential
insertions, ambiguous counterparts, selected allocation adjustments, potential
removals, historical repeat retention, amount groups, and implementing offices.
All views export their filtered rows, including rows beyond the visible page.
The input hashes are recorded in the downloadable analysis JSON.

Potential selected counterpart rows can appear in both the ambiguity review and
allocation-adjustment view. This overlap is labeled explicitly. Building-type
groups are descriptive title classifications, not comparable construction unit
costs. The page works locally without external chart frameworks.

## Top 25 line-item review queue

### Within-stage line-item screen

`repeats.html` collates DPWH historical GAA matches (including MPB through the
program filter), NEP-repeat survival into HGAB, within-stage pairs, and existing
FMR/NIA historical repeat tables. Original repeat tables move off their agency
pages and leave links. Repeated allocation amount patterns stay on agency pages.
`build_repeats_page.py` preserves original generated sections and their source
evidence in `repeat_page_fragments.json`, refreshes sections when agency builders
regenerate them, and runs through the shared editorial pipeline. The new shared
menu contains 15 links; mobile height is 328px to fit all eight rows.

`analyze_within_stage_repeats.py` compares distinct domestic DPWH NEP occurrences
within NEP, and native HGAB 3rd-reading occurrences within HGAB. Results and full
source evidence are in `within-stage-repeats.json`; the DPWH page displays paired
counts, distinct occurrence counts, explicit chainage overlaps and the first 50
pairs per stage with CSV exports. Summary regeneration refreshes this section.
Official PAP and qualified town/province or implementing-office context must
agree. Same base titles qualify; fuzzy titles require ≥0.94 text similarity,
qualified town/province and identical distinctive scope-token sets. Changed named
route endpoints cannot be overridden by a high text ratio. Disjoint chainage,
direction, qualified-location and tranche conflicts veto. Generic and untrusted
titles and FAP records are excluded. Missing chainage means funded-segment scope
is unresolved. The queue does not establish duplicate contracts or payments;
pair counts and allocation-occurrence counts must remain separate.

`build_line_item_review_queue.py` ranks domestic DPWH HGAB 3rd-reading
occurrences. One point per potential insertion, qualifying repeated amount group,
qualified exact historical title recurrence, explicit historical chainage
overlap, and high allocation per stated meter. Flag count is sorted descending, then HGAB allocation descending; source
occurrence ID breaks exact ties. Persons, offices' political affiliations and
roles do not influence scores.

The historical screen directly compares HGAB titles with local FY2025/FY2026 GAA
records; it does not require an NEP match and can therefore screen HGAB-only
candidates. Parent municipality/province context is required. Case/punctuation
and complete trailing station/coordinate metadata can be normalized; work
descriptions, directions and packages remain. Disjoint ranges and geographic or
tranche conflicts veto historical recurrence. Amount groups require at least
10 occurrences and 3 named offices in the same PAP. These thresholds are editorial
triage rules, not statistically calibrated risk levels. Related historical-title
and chainage flags are disclosed as dependent indicators.

The meter-rate flag reuses the current cost page's same-category, exact-PAP,
data-derived length-band screen: at least 20 peers of length ≥10 meters, with
rate above both twice the median and Q3 + 1.5 × IQR. A native HGAB input hash and
occurrence title/amount checks prevent stale or mismatched rate joins. Extreme
rates retain a denominator/scope caution; no missing length, sub-10-meter range
or insufficient-peer case earns a rate point. These are relative allocation
rates, not verified engineering unit costs or established overpricing.

All nine summary themes are mapped visibly to their scoring or caution treatment.
Missing lengths and very short printed ranges are evidence cautions, not extra
points. MPB membership is a program scope, not a flag. Equal RCS amounts use the
existing amount-group flag rather than a second point. INSPIRE is outside the
domestic DPWH scope. Nine summary findings do not imply nine independent flags.

The summary's final section shows 25 rows, paired flag-count/allocation graphics,
a CSV export and all scoring methodology. `line-item-review-queue.json` includes
all ranked occurrences, sources/input hashes, flags, accepted historical evidence
and exclusions. The scope is DPWH; other agency screens are not yet equally
complete. Overlapping figures must not be summed as losses.

## Cost per stated kilometer

### NEP workbook scope and non-DPWH stage comparisons (2026-10-12)

Agency pages lead with NEP → HGAB 3rd reading. `standardize_nep_hgab_pages.py`
renders DepEd and the NIA irrigation appendix as HGAB-only schedules with explicit
"Not established" NEP counterpart/difference status until comparable baselines
exist. It removes the legacy 2nd/3rd panels from named NIA and HFEP. Other-agency
reading controls remain on `dpwh-hgab-comparison.html#other-agency-readings` with
full reading data downloadable. Summary comparison coverage uses null for missing
NEP totals/differences; those are not zero. Source provenance can still identify
reading versions, without presenting that transition as the agency-page analysis.

Existing NEP → HGAB 2nd-reading analyses are retained at the bottom of DPWH HGAB,
FMR, NIA and HFEP pages by `retain_historical_nep_comparisons.py`. The helper moves
existing sections or renders already published snapshot rows; it runs no matcher.
FMR’s older 795-row envelope-only analysis is restored from published commit
912c9a23e and explicitly marked as incomplete and superseded. Current 3rd-reading
figures lead; archived totals are excluded from current claims. Pages without an
existing NEP/2nd analysis do not get an invented one.

Workbook schema 3 distinguishes blank, zero, positive and negative amounts,
annotates programme-envelope versus named-candidate scope, and supplies a
structural grouping key. `build_nep_agency_baselines.py` sums object/fund components
by agency + PREXC + operating-unit code + region code and retains every source row.
Grouped money must equal raw component money. NIA GOCC subsidy rows are MOOE in
the workbook: a CO-only filter would miss project budgets. The full workbook still
reconciles with its printed grand-total control at zero difference.

The NIA workbook has 61 positive, 23 explicit-zero and 132 blank grouped entries
(activities/envelopes as well as project candidates). Exact full titles establish
27 named candidates: 20 same allocations and 7 changed. Five names remain
unresolved; no arbitrary cross-location similarity turns them into matches.
`audit_non_dpwh_stage_controls.py` checks all 32 HGAB title/amount rows within the
visible PDF CropBox and supplies corrected physical page references. The seven
changed rows have a combined net adjustment of −₱1.5B; this is a matched subset,
not the entire NIA budget or verified engineering-scope identity.

HFEP compares programme-level CO and MOOE separately. Its visible HGAB control
is Vol I-A PDF p.1067 / printed p.1057: MOOE ₱67.173M, CO ₱10.021659B, total
₱10.088832B. NEP workbook CO is ₱14.472659B, MOOE ₱67.173M; the CO and total
adjustments are −₱4.451B. All 513 HGAB facility allocations sum to the printed CO
control. No facility-level NEP insertion/removal claim is inferred from envelopes.
NIA, HFEP and the irrigation scope note are updated by the editorial pipeline;
their separate 2nd/3rd reading comparisons remain distinct. The new pages/data
are copied to ODV for the user's next commit/push and deployment signal.

### Corrected FMR annex import (2026-10-12)

The 13 analyst files are private inputs in `data_sources/fmr_analyst/`; the supplied
description is preserved as README.md. `build_fmr_dataset.py` validates imported
counts, totals, CSV/JSON row identity, region controls and the House PDF hash.
It independently compares all 60 FMR annex pages in the local 2nd/3rd copies;
content agrees after excluding InDesign production-footer timestamps and
normalizing whitespace. This bounded check does not authenticate the entire bill.
The corrected ledger has 964 House rows / ₱19.6281B versus 704 NEP rows / ₱16B.
The previous 795 / ₱14.035375B was incomplete extraction, not a budget-stage total.

`build_corrected_fmr_page.py` replaces the old FMR page with audited controls,
regional allocation changes, all counterpart statuses, provisional insertion and
removal queues, selected allocation adjustments, coordinate anomalies and STA
rate evidence. Source IDs and coordinate-review flags stay visible. Matching is
our own one-to-one title/region screen; exact normalized coordinates strengthen
scope evidence but do not certify funded work. Fuzzy geographic candidates stay
outside insertion counts. NEP source cells cannot be independently re-extracted
without its original standalone PDF; imported provenance remains explicit.

Three House rows have usable printed STA lengths: 479.4m, 650m and 1050m.
Cost coverage is therefore 3/964, with 99.69% without usable extracted length.
Coordinate chords remain diagnostic and never supply cost-per-road-meter
denominators. FMR remains too sparse for the high-rate peer/model screens.
The summary/index, cost/density assets, FMR historical repeat section and reading
revision data are refreshed. DPWH-only congressional allocations and its Top 25
scores are not expanded with DA funding. FMR’s source builder and reading-page
builder retain the corrected path on regeneration.

### FY2026 GAA comparison

`compare_meter_rates_2026.py` reuses the current category and length parser on
positive domestic DPWH OPERATIONS column-J records in the local FY2026 parsed
schedule. The cost-page generator rebuilds this comparison and copies
`meter-rates-2026-comparison.json` to ODV. Official PAP matches require normalized
full-label agreement. Within-program comparisons need 20 rate records per stage;
length adjustment uses FY2026-derived quartile bands with 20 records per stage
per band and FY2026-count-weighted band median ratios. Full records, input hashes,
hierarchy context and band calculations are retained. Coverage and supporting
calculations are visible on the page. This is not matched-contract price inflation:
project mix, width, terrain, geography and quantity remain uncontrolled. DPWH
column-J scope is a conservative subset; DA FMR is outside this comparison.

`build_cost_per_km.py` writes `cost-per-km.html` and `cost-per-km-data.json`.
The summary regeneration pipeline rebuilds the page, and the summary links to separate seventh and eighth findings for length coverage
and allocation per stated kilometer. Roads, bridges, FMR and mixed scopes have
separate coverage figures; each official work PAP also has its own denominator.
All length evidence and source pages are retained. Partial chainage, conflicting
lengths and ambiguous multiple route references are withheld. FMR context is
trimmed at the current project's title before pairing two printed STA endpoints.
Coordinate straight-line distances never substitute for construction length.

The ratio is allocation / stated segment kilometers, not verified construction
unit cost. Bridge segments may include approaches; mixed road/bridge allocations
receive no single-work rate. The missing percentage includes absent and unusable
extracted evidence, not a claim that original engineering records omit lengths.
The tables export all filtered records, including missing values.

The summary now contains eight editorial investigation leads. Length coverage
and allocation/km remain distinct questions, with extraction limitations and
short-denominator sensitivity visible alongside each.

Displayed lengths and rates now use meters and pesos per stated meter. The existing
`cost-per-km.html` URL is retained. JSON keeps the original kilometer fields and
adds `lengthMeters` / `allocationPerStatedMeter`; missing-length coverage and
allocation amounts are unaffected by this unit conversion.

## Short printed ranges and selection audit

`audit_short_segments.py` checks full-population lengths and re-extracts visible
text on six sampled original HGAB PDF pages. All six sampled titles agree with
visible source text. Three sampled road station differences imply under five
meters; this is printed notation, not certified funded engineering length.
The audit is keyed to the native comparison CSV hash and must be refreshed if
that input changes.

The ninth summary lead documents those verified printed ranges and requests
engineering clarification. It does not claim most roads are below 100 meters:
204/3,175 known road lengths (6.43%) are below that threshold, while 20 of the
highest-rate 25 road records are below it. The cost page now provides an all-known
length distribution separately by category, CSVs and the sampled source checks.
`short-segment-audit.json` publishes the count denominators and visible fragments.

## Data-derived length/density grouping

`analyze_length_density.py` derives approximately equal-count bands separately
within each official work PAP. It screens consecutive bands with at least 20
records each for 2× median-density differences. No fixed 100-meter threshold is
used. A separate continuous piecewise log(allocation)-versus-log(length) model
searches up to 31 boundaries drawn from observed lengths. This checks allocation
patterns separately from the arithmetic density denominator.

Model screens require 80 records, 20 per side, at least 10-meter lengths and
BIC improvement ≥6. One hundred seeded row bootstrap samples report selected
boundary stability; their 10th–90th window is not a confidence interval. A
≥25-meter sensitivity fit is reported. Width, terrain, quantities, record
dependence and non-random missingness remain uncontrolled. Multiple exploratory
searches are not confirmatory tests. The page provides model tables, descriptive
band medians, graphs, CSVs and full downloadable `length-density-groups.json`.
No universal engineering or corruption threshold is inferred.

## Citizen-facing high-rate review

The cost page now starts with high-rate candidates and paired project/typical
peer rate bars. Detailed grouping and model calculations remain below, visible.
Peers share the exact category, official PAP and data-derived length band, with
at least 20 records and stated length ≥10 meters. Candidate rates exceed both
2× median and Q3+1.5×IQR. Graph extremes exceed max(2×median, Q3+3×IQR);
sub-10-meter printed segments also stay off rate charts. All such rows remain
in tables/CSV/JSON, with exclusions and maximum omitted rate described in words.
These are relative-rate candidates, not certified overpricing findings.

### Repeated station labels without a dash

The shared chainage parser recognizes exactly two consecutive explicitly labeled
STA/Station or K/KM points separated only by whitespace as a range. Unlabeled
points, longer station lists and intervening scope/place text remain unresolved.
Ranges touching only at an endpoint have zero positive-length overlap and are
excluded by the disjoint-range veto. The historical flood-control screen now
also applies this veto instead of discarding its chainage metadata.

### Explicit Chainage meter offsets

The shared chainage parser also recognizes explicitly labeled numeric meter offsets, such as `Chainage 1287 - Chainage 2288`. The Cabutagan-Haluban-Sooc ranges 287–1287 and 1287–2288 are adjacent, with zero positive overlap, and are excluded as a repeat pair. This syntax supplies stated segment length to the cost-density analysis; it does not verify physical construction scope. Unlabeled numbers are not interpreted as chainage.

### Numbered bridge identity

Different explicit bridge numbers (including No./Number labels and Roman numerals) veto a repeat comparison when both titles identify nonoverlapping sets of numbered bridges. Mauban Bypass Road Bridge 3, Bridge 4 and Bridge 5 identify different structures. A missing bridge number leaves identity unresolved; matching numbers alone do not establish the same structure without location and scope evidence. This veto applies to within-stage and historical DPWH screens, regardless of program category.

### Mixed chainage endpoint notation and bounded nonoverlap

Mixed bare/plus endpoint notation remains incomplete for length and cost-density calculations. Under the explicit assumption that printed endpoints are ordered min/max, a known upper endpoint at or below another range's known lower endpoint excludes positive overlap. Unknown endpoints are not filled. This general bounds rule excludes the Jolo pair without a project-specific exception. If bounds cannot exclude overlap, the comparison remains unresolved rather than establishing overlap. Isolated unconnected station points do not supply interval bounds. The earlier exact-title clarification is retained privately as review history, not used as an active matching override.
