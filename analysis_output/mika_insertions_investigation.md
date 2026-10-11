# Mika / Nueva Ecija DEO–LEG reconciliation

Source: supplied `dpwh-projects-filtered.json`; all 100 rows located by complete normalized title + exact HGAB pesos + physical PDF page.

The external filter is Nueva Ecija **1st DEO**, not 1st LEG. Of its 100 records, 53 map strictly to 1st LEG, 21 to 2nd LEG, and 26 remain unresolved. Of the 53, 51 are insertion candidates and two stay in match review.

Across all offices, the 1st LEG has 179 assigned HGAB rows (₱2,231,890,000); 57 are domestic insertion candidates (₱669,978,000). Names indicate geography, not sponsorship.

## Licab examples

| HGAB title | HGAB pesos | Our screen | PDF page |
|---|---:|---|---:|
| Construction (Completion) of Multi-Purpose Building, Barangay Linao, Licab, Nueva Ecija, 15.566295, 120.781137 | ₱3,500,000 | No plausible NEP title counterpart; review candidate | 736 |
| Construction (Completion) of Multi-Purpose Building, Barangay Poblacion Sur, Licab, Nueva Ecija, 15.5384, 120.76093 | ₱50,000,000 | Multiple or already paired NEP counterparts; review scope | 736 |
| Licab - Victoria Diversion Road, Nueva Ecija Sta. 4+067.00 - Sta. 4+554.95 | ₱15,000,000 | No plausible NEP title counterpart; review candidate | 230 |
| Rehabilitation/ Improvement of Flood Control, Barangay Aquino, Licab, Nueva Ecija, Sta. 0+000 - Sta. 0+290 | ₱50,000,000 | No plausible NEP title counterpart; review candidate | 340 |
| Rehabilitation/ Improvement of Flood Control, Barangay San Juan, Licab, Nueva Ecija, Sta. 0+000 - Sta. 0+290 | ₱50,000,000 | No plausible NEP title counterpart; review candidate | 340 |

The ₱50M San Juan and Aquino flood-control entries are candidates. The ₱50M Poblacion Sur completion row stays under review: NEP already contains a ₱15M construction row at the same named barangay, retained separately in HGAB. Do not treat this as a proven new project. The ₱15M Licab–Victoria diversion-road record remains geographically unresolved: a road name and a DEO do not establish the construction segment’s LEG.

Separate Licab waterways entries at San Cristobal and Tabing Ilog, each ₱50M, have exact NEP counterparts and unchanged allocations. They are outside the supplied 100-record export and are not insertion candidates.

## Fixes and limits

- Shared PH location DB address rules separate trailing STA/K/KM fields and explicit Philippine-range decimal coordinate pairs for address lookup only. Original project titles and scope are retained.
- Explicit municipality/province and city/barangay agreement between local crosswalks is still required.
- The PH DB location guard rejects conflicting qualified locations in NEP/HGAB fuzzy matching and reverse removal screening. Composite routes and possible abbreviations remain review cases.
- Both reading screens were regenerated; the independent 26 new-in-3rd-reading comparison is unchanged.
- Current national shortlist: 5,528 domestic insertion candidates, four unpaired FAP review lines, 1,000 domestic removal candidates. These are provisional source comparisons, not certified legislative changes or findings of wrongdoing.
- No target count from the other analyst was imposed.

Updated local ODV reports await user commit/push and a separate deployment signal.
