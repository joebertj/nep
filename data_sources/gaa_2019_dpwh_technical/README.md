# FY2019 DPWH Technical GAA extraction

The source is DBM's FY2019 Technical General Appropriations Act, Department of
Public Works and Highways, Office of the Secretary:

- Original PDF: `research_downloads/philgeps_dime_2019gaa/fy2019-gaa-dpwh-technical.pdf`
- Official URL: <https://www.dbm.gov.ph/wp-content/uploads/GAA/GAA2019/TechGAA2019/DPWH/A.pdf>
- SHA-256: `2a2e5dc4271394777ba9fbe6fbc8a2fc344c7a25fb7b7fd02d22a207912693fe`
- Parsed output: `lines.json`
- Parse script: `parse_fy2019_dpwh_technical_gaa.py`

The PDF contains selectable text, so the extraction reads its text layer and
uses coordinates to associate UACS codes, descriptions, and the rightmost
amount column. It yields 21,751 unique UACS codes from 1,527 PDF pages. Repeated
code occurrences are reconciled by the most frequent extracted amount; all
observed amounts remain in `amountCandidatesPesos` for review.

The source summary states DPWH new appropriations of ₱454,016,273,000. Parsed
rows include summary/control and detailed UACS lines. Their amounts overlap;
do not sum every parsed row. `project_title_candidate` is a text-based review
filter, not a count of verified independent projects.

GAA project-history pages use the specific 12-significant-digit PAP lines that
match the existing road, bridge, flood-control, or MPB title classifiers.
Those are a classified subset of the source, not the full DPWH total. District
totals include only unique assignments under the existing title-location rules;
shared or unresolved rows are retained separately from assigned totals.

The MPB subset is also exported to `data_sources/mpb-historical-2019.json` for
the barangay and contractor MPB datasets. Its title rule requires a
multi-purpose variant and building/bldg/facility wording and excludes shorter
UACS program/group rows. The titles and amounts should be checked against the
cited original PDF pages before use in decisions. Allocations are not payments.
