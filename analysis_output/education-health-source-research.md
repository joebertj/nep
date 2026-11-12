# Additional education, health and evacuation data

Reviewed 12 November 2026. These are source leads, not ingested records.

| Source | Coverage and useful fields | Status and use |
| --- | --- | --- |
| [DepEd Region VIII RM 704, 2025](https://region8.deped.gov.ph/2025/06/25/june-23-2025-rm-704-s-2025-masterlist-of-public-schools-with-approved-government-authority-to-operate-effective-s-y-2025-2026/) | Public-school masterlist for SY 2025–2026, Region VIII | Official publication located. Inspect its attachment and extract school identifiers before joining; not a national inventory. |
| [Quezon City evacuation-center directory](https://quezoncity.gov.ph/qcitizen-guides/quezon-city-evacuation-centers/) | Barangay, location name, address, center type | Public HTML table inspected. Contains schools, courts, halls and open spaces; preserve temporary/semi-permanent labels and avoid counting multipurpose sites as newly built facilities. Resolve barangay names to PSGC and deduplicate sites before use. |
| [DOH NHFR](https://nhfr.doh.gov.ph/) | Health-facility registry source lead | HTTP 403 in this review. No registry rows acquired or verified. Obtain a dated public export before replacing OSM candidates. |
| [DILG NCR DRRM-PULSE](https://drrm.ncr.dilg.gov.ph/) | Participating LGU facilities and resource inventory | Public landing page describes mapped evacuation sites, capacities and status. Regional coverage; export availability and record completeness not established. |
| [PSA response on evacuation centers](https://www.foi.gov.ph/agencies/psa/evacuation-centers/) | Source ownership guidance | PSA says it does not have the requested inventory and directs users to NDRRMC/OCD. Follow those agencies for a nationwide inventory rather than treating active disaster shelters as the full stock. |

Keep source dates, public/private classification, administrative identifiers, site types, and geographic coverage in any future import. A budget project line, a mapped feature and a facility site are distinct record units. School or health sites used for evacuation can overlap across categories.
