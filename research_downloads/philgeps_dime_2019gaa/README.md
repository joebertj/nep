# FY2019 GAA source file

Downloaded 2026-11-03 from the Department of Budget and Management's official
archive:

- `fy2019-gaa-volume-ia.pdf` — FY2019 General Appropriations Act, Volume IA,
  Republic Act No. 11260. This is the official document, not a normalized
  spreadsheet.
- `fy2019-gaa-dpwh-technical.pdf` — DBM's searchable technical DPWH GAA
  schedule, including named UACS project lines. This is the source parsed for
  the FY2019 DPWH historical project layer.

DBM's [FY2019 GAA page](https://www.dbm.gov.ph/index.php/central-office?catid=308&id=2154%3Ageneral-appropriations-act-gaa-fy-2019&view=article) lists the other volumes, annex, and selected BESF tables.

The existing PhilGEPS and DIME Parquet snapshots were not copied here. I did
not retain sample-like CSV responses from a non-government `ebizolution.net`
endpoint as authoritative data. PhilGEPS' [official Open Data portal](https://open.philgeps.gov.ph/)
reports its latest synchronization date and exposes public analytics; I did not
find a verified bulk Parquet export newer than the files already in the project.
The official [DIME portal](https://www.dime.gov.ph/) has a project dashboard,
but I did not find a public bulk download for its current project data.

SHA-256:

```text
9d301901433799dc1ab9fa936a05f3cc5976ee7fb066e8596c9e5b6266eeb821  fy2019-gaa-volume-ia.pdf
2a2e5dc4271394777ba9fbe6fbc8a2fc344c7a25fb7b7fd02d22a207912693fe  fy2019-gaa-dpwh-technical.pdf
```

The technical DPWH schedule reports ₱454,016,273,000 in new appropriations.
It is the appropriate FY2019 DPWH source for named project lines; Volume IA is
only one part of the act and does not contain this DPWH project schedule.
