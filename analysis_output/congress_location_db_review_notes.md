# Location database review of Congress attribution

The private database was applied to the local HGAB 3rd-reading source. Exact
adjacent municipality/city and province fields identify geographic candidates
on 8,227 rows, including 2,761 unresolved under the existing strict rules.
These are place candidates, not newly verified legislative assignments.
Membership claims currently have no effective boundary dates, and some maps
conflict; no new district assignments were introduced from these claims.

The database's recorded route-scope issue holds out
`HB10858-3-0447-006385`, ₱1,200,000,000. The title mentions RTR, confirmed by
the user as Remedios T. Romualdez. No construction segment or budget split
proves the entire amount belongs to Butuan. The user confirmed: “Keep it
unresolved pending segment evidence.”

| Accepted strict totals | Before | After |
| --- | ---: | ---: |
| Butuan lone allocation | ₱5,428,982,000 | ₱4,228,982,000 |
| Butuan lone lines | 99 | 98 |
| All accepted allocation | ₱154,459,302,000 | ₱153,259,302,000 |
| All accepted lines | 5,885 | 5,884 |
| Allocation coverage | 26.31% | 26.11% |

Ilocos Norte 1st remains ₱4,672,900,000 across 322 lines and leads the current
accepted ranking. Rankings are partial geographic attribution, not complete
district budgets or project sponsorship. The ₱587,075,661,000 source schedule
is unchanged and the builder's count and peso reconciliation checks pass.

Outputs:

- `congress_location_db_review.json`: private geographic candidates, claim
  provenance, source hashes and supported scope holds.
- `congress_geographic_attribution_db_3rd.json/.csv`: complete revised decisions.
- ODV `static/data/congress_location_scope_reviews.json`: small supported hold
  snapshot, consumed by the ODV builder by default.
- ODV `static/nep-preview/congress-data.json` and `congress.html`: revised static
  ranking and matching hero totals, with a fresh data-request cache key.

The public snapshot matches source IDs, full titles, amounts and the HGAB file
hash; a changed source requires regenerating/reviewing it. Runtime serving
needs no private SQLite connection. No deployment was performed.

## Subsequent province/city context correction

While building the focused district insertion tables, a province/city label
collision was found: bare “Isabela” was treated as a city even when preceded
by a complete locality field such as “Echague, Isabela”. The matcher now uses
that complete field to establish province context and still requires both
district crosswalks to agree. No new undated boundary claim was promoted.
The totals above document the earlier scope-hold pass; the current ranking
has 6,941 accepted lines, ₱181,581,532,000 and 30.93% allocation coverage.

Focused potential insertion shortlists:

| Current roster district | Candidate lines | HGAB allocations |
| --- | ---: | ---: |
| Mika Suansing · Nueva Ecija 1st | 0 | ₱0 |
| Bojie Dy · Isabela 6th | 14 | ₱738,000,000 |
| Sandro Marcos · Ilocos Norte 1st | 214 | ₱2,745,230,000 |

These intersect the domestic no-plausible-NEP-counterpart shortlist with unique
district location assignments. Zero means no accepted candidate survives this
screen, not proof of no insertions. Each table shows its largest 20 candidates
and exports the full shortlist. Mika's accepted district total still includes
116 lines, ₱1,274,762,000, which do not survive the insertion screen.
