# Connectivity place source inventory

Current OSM snapshots; source links and SHA-256 hashes are retained in each JSON inventory. Clear profanity and slurs in mapped venue names are replaced with a neutral label in public outputs. No new road dataset is acquired by this builder.

## Visitor venues

14,156 normalized mapped venue records; same-name records within 50 m merged.

- Event venue: 695
- Guest house: 2,976
- Hostel: 1,099
- Hotel: 4,988
- Motel: 764
- Resort: 3,172
- Rest house / chalet: 462

## Private-property review candidates

4,653 mapped source features. These are not yet joined to remote roads and are not confirmed beneficiary properties.

- Large residential footprint · ≥1,000 m²: 1,491
- Residential estate cue: 90
- Subdivision / residential village cue: 3,071
- Villa / mansion tag · size/value unverified: 1

Large residential footprints use a provisional threshold of 1,000 m². Land-use estate/village cues may represent an entire development; private ownership and property value are unverified. Owner names and private-property labels are omitted.

A 100 m road-alignment buffer identifies proximity leads. A subdivision connection requires evidence of a road entrance or intersection. City and national roads remain excluded from the remote-road screen.

## Files

- `connectivity-venues-data.json/.csv/.geojson`
- `connectivity-property-indicators-data.json/.csv/.geojson`
- `connectivity-venue-review-data.json/.csv/.geojson`: unverified name cues; excluded from the business inventory.
- `connectivity-remote-fmr-venues.json/.csv`: generated separately by `build_connectivity_venue_links.py`; coordinate-backed FMR route/venue proximity pairs.
- Potentially offensive venue names withheld: 0.

JSON/CSV copies are served separately from HTML under ODV `static/nep-preview/`; GeoJSON is saved in NEP `analysis_output/` for GIS use.

© OpenStreetMap contributors, ODbL 1.0: https://www.openstreetmap.org/copyright
