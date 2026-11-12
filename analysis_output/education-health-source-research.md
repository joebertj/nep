# Facility count refinement — 12 November 2026

The page now incorporates extracted records and corrected geographic joins, rather than listing unprocessed source leads.

| Category | Previous joined count | Refined joined count |
| --- | ---: | ---: |
| Public-tagged school candidates | 38,584 | 44,060 |
| Public-tagged health candidates | 2,167 | 2,612 |
| Evacuation sites/candidates | 246 | 756 |

School and health totals remain OSM candidates from the 4 November 2026 snapshot. The increase comes from unique municipality/province joins and unique municipality/province-family joins for broad published labels such as Negros and Mindoro. Ambiguous matches remain excluded. The facility crosswalk retains source feature IDs, target municipality codes and the selected join method.

## Quezon City extraction

Source: https://quezoncity.gov.ph/qcitizen-guides/quezon-city-evacuation-centers/

Retained HTML: data_sources/education_health_official/qc-evacuation.html. Rebuild with python3 import_education_health_official.py, then python3 build_education_health.py.

496 data rows yield 493 listed sites after excluding 3 repeated normalized barangay/name/address identities. Same-named sites at different addresses remain separate. The official directory replaces city OSM evacuation counts, rather than being added to them. The resulting total is designated sites, not dedicated buildings: 422 temporary, 69 semi-permanent and 2 permanent. 491 sites resolve to barangay identifiers; two Quirino 3-B records remain only in city and regional counts. Audited aliases include Doña Aurora → Aurora and San Isidro Galas → San Isidro.

## Additional sources checked

The DepEd Region VIII public-school list for SY 2025–2026 was downloaded but has no extractable text; the local OCR attempt returned no recognized words. It is regional and contributes no rows. A direct national DepEd derived-data URL returned HTTP 403, so the page now uses the separately documented NASH Reviewer release described below.

A DOH FOI response says its 2025 NHFR derived Excel and shapefile may be released on request. DOH notes that the 2025 coordinates may be incomplete, some locations have blank coordinates, and the records represent facilities registered in NHFR rather than the true number operating in a given year. Those files have not been received and contribute no rows. See https://www.foi.gov.ph/agencies/doh/digitized-map-of-hospitals-and-health-facilities/.

## The page now presents the exact candidate totals screened, matched totals, unmatched totals, source vintage, and the Quezon City split between directory and OSM sources.

## Validation

All regional category sums reconcile to joined inventory totals. Quezon City totals reconcile to the normalized site ledger. All four geography controls and five view controls were exercised with the generated data. Unknown barangay facility counts remain null and display as unavailable.

## DepEd public-school register added — SY 2025–26

Source: [NASH Reviewer DepEd data release](https://nash.com.ph/blog/download-cleaned-deped-school-data), which documents cleaned school data based on DepEd public files and provides a versioned gzip CSV, codebook, and SHA-256 checksums. The 2025–26 enrollment panel includes school ID, name, sector, region, province, municipality/city, and barangay. The page now counts unique rows with `sector = Public` as a separate DepEd series; it does not add them to OSM candidates.

- 48,129 unique public school IDs in the release.
- 47,372 uniquely joined to a PSGC municipality/city (757 unresolved).
- 46,686 joined to a PSGC barangay (686 municipality-matched school records have an unmatched/ambiguous barangay).
- Join fallback uses unique municipality/region and, where necessary, unique municipality/province-family/region matches. All unmatched records are excluded from place counts.
- OSM remains a separate cross-check: 44,060 public-tagged school candidates joined in the 4 Nov 2026 extract. These sources overlap and should not be summed.

The DepEd per-place figures are joined-record counts, so places with no matched ID are displayed as no joined record, not zero schools. The NASH release reports 60,204 schools in the 2025–26 panel across all sectors; the public-only subset above was calculated from the file. Dataset checksum verified against the published checksum manifest.

## Health source lead

DOH HFSRB identifies itself as the repository for DOH-regulated health facilities. A DOH circular posted in September 2026 links the 2025–26 NHFR consolidated annual reports, but the linked Google Drive folder was not accessible through this research pass and these reports are addressed to DOH regional offices. I did not add health counts from this lead. The page therefore continues to distinguish the partial 2,612 joined OSM health candidates from an official facility register. Sources: [HFSRB repository description](https://sites.google.com/doh.gov.ph/hfsrbdata/home), [NHFR 2025–26 circular](https://sites.google.com/view/doh-hfdb/2026-q3-updates/dc-2026-0525).

The 2025–26 panel also reports total enrollment for 48,126 of the public-school records (22,078,460 learners in the full public subset). The page now adds a separate joined-enrollment density series and a school-table enrollment column. Place-level learner totals sum only the joined school rows with reported enrollment; they are not extrapolated to unmatched schools. A school may have enrollment reported as missing, so the table marks such rows as unavailable rather than treating them as zero.

## PhilHealth health facility data added — 30 September 2026

The [official PhilHealth accredited-facilities page](https://www.philhealth.gov.ph/partners/providers/facilities/accredited/) provides downloadable lists updated 30 September 2026. I downloaded and retained the hospital/infirmary list and YAKAP provider list, then extracted the PDF tables and joined facility municipalities against PSGC. `SEC = G` is counted as government; `P` is excluded from government measures. PSGC joins use municipality plus the section's province where available, otherwise unique municipality within region, then unique municipality nationally. Ambiguous records are excluded. Since the source has no stable facility ID, repeated normalized facility name + street + matched PSGC municipality rows are collapsed for place counts, preserving same-named facilities at different addresses.

- Hospitals and infirmaries: 1,934 listed entries, 824 marked government; 781 government facilities joined, 43 government rows unmatched. The matched government facilities list 60,744 beds; the full government entries list 66,914 beds.
- YAKAP providers: 4,138 listed entries, 2,917 marked government; 2,722 government providers joined, 195 government rows unmatched.
- Overall municipality joins: 1,805/1,934 hospital entries (93.3%) and 3,843/4,138 YAKAP entries (92.9%). Place counts use unique matched name + street + PSGC municipality records rather than raw rows.
- These are separate accreditation/program lists and overlap: YAKAP includes RHUs, health centers and hospitals, some of which also appear in the hospital list or OSM. Counts must not be summed. Neither PhilHealth PDF gives barangay fields; these measures are unavailable at barangay level.

The page uses these matched counts as separate selectable density series and adds them to the health table. The government hospital bed measure is distinct from facility counts. The DOH NHFR interactive page still returns HTTP 403 in this research pass; the PhilHealth PDFs add usable official health data but are not a replacement for the DOH master registry.
