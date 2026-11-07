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
Run `python3 build_connectivity_unpaved_road_indicator.py` to compare printed
FY2027 FMR route geometry with offline OSM tracks and roads tagged with an
unpaved surface. Then run `python3 build_connectivity_report.py` and
`python3 build_connectivity_venue_links.py` to rebuild road-distance, unpaved
road indicators and FMR–venue screening outputs.

OpenStreetMap data is © OpenStreetMap contributors, licensed under ODbL 1.0:
https://www.openstreetmap.org/copyright

## Country-extract fallback and official directory

When Overpass is unavailable, download the dated Philippines PBF from Geofabrik
and run `extract_connectivity_places.py <path-to-country.osm.pbf>` with the
`osmium` dependency in `requirements-connectivity.txt`. It makes three bounded
memory passes and saves the selected source objects, geometries, extract SHA-256
and source timestamp. The 2026-11-04 country extract is cached locally only.

`san-juan-dot-directory.html` is the municipal tourism office's public directory.
The normalized official listings omit contact details and full street addresses.
Exact unique names and reviewed brand aliases attach citations to map records;
municipality conflicts are retained. Unmatched listings have no inferred
coordinates and do not participate in proximity measurements.

After normalizing the inventories, run `build_connectivity_property_links.py`
with the connectivity environment, then `build_connectivity_map_data.py` and
`connectivity_places_page.py`. Polygon matches use distance to the footprint,
not its center. The property results remain ownership and access review leads.
