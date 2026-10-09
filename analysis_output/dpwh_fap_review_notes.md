# Separate foreign assisted reconciliation

FAP classification comes from the printed DPWH program schedule, retained by
the parser as PAP `Foreign-assisted projects (FAP)`. A title mismatch is not
adequate evidence of a new negotiated foreign assisted project.

The domestic shortlist previously included four unmatched FAP lines carrying
₱806,910,000. They have been removed: 4,610 → 4,606 domestic review candidates,
₱147,559,292,000 → ₱146,752,382,000. No project is declared an insertion by this
change. All 29 HGAB FAP lines, totaling ₱44,749,011,000, remain in full-schedule
data and are presented in a separate NEP/HGAB reconciliation table with CSV.

The two named JICA projects were already selected NEP matches, not shortlisted
additions:

| Project | NEP | HGAB 3rd | Change |
| --- | ---: | ---: | ---: |
| Cebu–Mactan, PH-P274 | ₱8,570,911,000 | ₱2,570,911,000 | −₱6,000,000,000 |
| MMPBSIP, PH-P272 | ₱792,964,000 | ₱792,964,000 | ₱0 |

Selected NEP records originate from the locally audited baseline using
`stage_trace_2027.json`, not the incomplete Transparency API alone. The parser
locates Cebu–Mactan on physical PDF page 940 and PH-P272 on 941; NEP pages are
689 for both. These locators preserve the parser's convention.

Four FAP records lack selected NEP counterparts: Priority Bridges Crossing
Pasig-Marikina/Manggahan (China), Metro Manila Bridges (ADB 4168-PHI), RNDP-CAAM
(JICA PH-F-P1), and SIDC (China GCL 202200600763). They require separate source,
loan, counterpart funding and scope review; they are not automatically new
projects or removed NEP projects. Nonexact paired counterparts remain
provisional. An unpaired line never receives an assumed zero NEP amount.

Rebuild the separation with `python3 build_dpwh_fap_review.py`. The DPWH
revision-page builder also calls this helper. Local pages/data are updated;
deployment requires the usual user commit/push and deployment signal.

## Insertion and removal terminology

Potential insertions are HGAB-only line items; potential removals are NEP-only
line items. A retained project with a lower amount is an allocation decrease,
not a removal. Domestic and FAP schedules are shown separately.

The reverse screen starts with 1,140 unpaired domestic NEP occurrences, holds
out 280 with compatible exact or nonexact HGAB title counterparts scoring at
least 83%, and leaves 860 removal candidates with ₱60,742,832,000 in original
NEP allocations. This cost is not a certified budget reduction. All 25 NEP
FAP occurrences have selected counterparts, including provisional matches;
no FAP line-item removals are shortlisted by the current mapping. Existing FAP
allocation changes remain in the reconciliation table. Graphs, searchable
paginated tables and CSV exports are included for both removal sections.

Allocation adjustments cover retained projects with increases or decreases.
The domestic table has 493 selected adjustments: 247 increases and 246
decreases. Filters distinguish direction and exact/provisional counterparts;
the accompanying signed bar graph and CSV follow those filters. The FAP
reconciliation table retains both positive and negative allocation changes.
