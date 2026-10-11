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
