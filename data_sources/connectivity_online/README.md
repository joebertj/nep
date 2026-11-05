# Connectivity source snapshots

Local download cache for public OpenStreetMap source snapshots. Raw responses
and discovery pages stay outside Git. Publish only the normalized inventories
produced by `build_connectivity_places.py`; these omit contact details, owner
names, full street addresses and raw account metadata.

The reusable outputs are in `analysis_output/connectivity-venues-data.*`,
`connectivity-venue-review-data.*`, and
`connectivity-property-indicators-data.*`. The page loads their JSON copies
from ODV's `static/nep-preview/` directory. GeoJSON copies are in
`analysis_output/` for GIS use.

`build_connectivity_report.py` uses the archived DPWH Road Classification
layer. `build_connectivity_venue_links.py` matches coordinate-backed HGAB/DA
FMR routes to municipal visitor venues within 100 m; these route geometries
are straight segments between available endpoints and are proximity leads.

Run `python3 build_connectivity_places.py` to rebuild cached data, or add
`--download` to refresh public place/property snapshots. The source queries
are embedded in the builder. This workflow does not acquire road data.
Then run `python3 build_connectivity_report.py` and
`python3 build_connectivity_venue_links.py` to rebuild road-distance and
FMR–venue screening outputs.

OpenStreetMap data is © OpenStreetMap contributors, licensed under ODbL 1.0:
https://www.openstreetmap.org/copyright
