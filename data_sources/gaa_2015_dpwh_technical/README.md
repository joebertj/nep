# FY2015 DPWH GAA source

Source: DBM's official [Budget Documents Archives](https://www.dbm.gov.ph/index.php/budget-documents-archives), GAA FY2015 ZIP archive, member `GAA2015/DPWH.csv`.

The archive is 725,113,202 bytes. The member was retrieved by HTTP byte ranges from the official archive; the entire ZIP was not downloaded. The raw member is preserved here as `dpwh.csv` (8,765,343 bytes; Windows-1252 encoding), SHA-256 `a9c18f33daa27fdcdc4a8f302f5c2f64ff35e4a7d33ab95eaa6ab4b5cb2cff30`.

`lines.json` groups account-detail rows in allotment class 6 (Capital Outlays) by PAP code, full PAP description, implementing office, region and fund source. DBM CSV amounts are in thousand pesos and have been converted to pesos. Multiple object-account rows are summed within each group. This yields the capital-outlay schedule total, but a title-based category filter is only a candidate layer: some titles describe broad programs and repeated descriptions do not prove distinct physical projects. PAP codes are program/account codes, not unique project IDs. The group rows should not be added to higher-level PAP summaries.

Run `python3 parse_fy2015_dpwh_technical_gaa.py` to reproduce `lines.json`.
