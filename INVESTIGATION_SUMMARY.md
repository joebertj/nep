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

`build_line_item_review_queue.py` ranks domestic DPWH HGAB 3rd-reading
occurrences. One point per potential insertion, qualifying repeated amount group,
qualified exact historical title recurrence, and explicit historical chainage
overlap. Flag count is sorted descending, then HGAB allocation descending; source
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

The summary's final section shows 25 rows, paired flag-count/allocation graphics,
a CSV export and all scoring methodology. `line-item-review-queue.json` includes
all ranked occurrences, sources/input hashes, flags, accepted historical evidence
and exclusions. The scope is DPWH; other agency screens are not yet equally
complete. Overlapping figures must not be summed as losses.

## Cost per stated kilometer

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
