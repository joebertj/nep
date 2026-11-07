# Official and designation database

All politicians and roles: query `all_official_roles.duckdb` (`all_officials`, `source_records`, `role_counts`) or `all_official_roles.parquet`. Original position labels, source years, locality and public organization fields are preserved.

For RDC/PDC/LDC and POW signatories, `officials.json`, `officials.csv` and `officials.sqlite` contain explicit Governor, Mayor, District Engineer and Assistant District Engineer designation candidates. These are historical source records, not current appointments or proof of a signature.

Source capture: `../odv_dynasty/source-table-manifest.json` and the public API page snapshots. Private date-of-birth fields from the original SQL dump are excluded.

{
  "source_records": 445160,
  "official_role_records": 314052,
  "distinct_position_labels": 744,
  "source_ids_with_name_conflicts": 1132
}
