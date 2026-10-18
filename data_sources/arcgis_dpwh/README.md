# Public ArcGIS inventory archive

Collection policy: download and preserve JSON now. Parquet conversion is
deferred until separately requested. The downloader performs no Parquet conversion.
Current scope is **user-selected services only**. The whole-directory job has
been removed from `selections.json`. Candidate metadata inspections do not
download feature rows or add services to the queue.

Priority: `Detailed_Bridge_Inventory_Final/FeatureServer/1` in the public
`services1.arcgis.com/IwZZTMxZCmAmFYvF` directory.

Run from the private NEP repository:

```sh
python3 start_arcgis_downloads.py
python3 start_arcgis_downloads.py --status
```

## Dedicated selected-feature downloaders

```sh
python3 download_bridge_inventory.py
python3 download_bridge_inventory.py status
python3 download_congressional_districts.py
python3 download_congressional_districts.py status
```

Each selected feature has an independent checkpoint, log and PID under
`archive/selected/<profile>/`. They share a filesystem network lock and wait
at least three seconds between requests, even with multiple workers. Existing
raw batches are reused through immutable cache files. Attributes, native
geometry, metadata, attachments and export checksums are retained as before.

### Selected-service queue: maximum two active downloaders

The queue now also includes these dedicated service launchers, each archiving
every advertised layer/table in that service:

- `download_city_municipal_boundaries.py`
- `download_engineering_districts.py`
- `download_da_fmr_fy2025.py`
- `download_road_classification.py`
- `download_national_road_network.py`
- `download_number_of_lanes.py`
- `download_ports.py`
- `download_provincial_boundaries.py`
- `download_road_condition.py`
- `download_kilometer_posts.py`

`python3 start_arcgis_downloads.py` starts the persistent queue. Check it with
`python3 start_arcgis_downloads.py --status`. Completed selections are skipped;
remaining selected services run in selection order. No more than two downloader processes are active, excluding the idle
scheduler itself. Two global slot locks also enforce the limit on manual launches.
The selected jobs are listed in `selections.json`; the scheduler rereads it each
cycle, allowing more selections to be added without interrupting active downloads.
`--reload-queue` upgrades the scheduler process while leaving downloaders running.
The shared network lock still serializes HTTP requests with three-second gaps.
Polygon layers use ten IDs per request to avoid very large boundary responses;
gzip transfer is requested. Interrupted responses are retried in smaller ID
groups. Existing larger saved batches are reused unchanged, so adjusting the
request batch size does not discard completed data or simplify geometry.
Failed workers and inaccessible layers remain explicitly recorded, not silently
marked as successful. Check profile logs/status before retrying a failed job.

`python3 start_arcgis_downloads.py --restart-bulk` checkpoints older workers
and adopts the two-worker queue and shared pacing engine.
Only selected services run. New selections should get
their own small `download_<feature>.py` launcher using the shared engine.

The congressional service describes 238 districts and cites March 2019 at
service level, while layer 0 cites March 2022. Preserve this conflicting vintage
metadata; do not treat it as validated FY2027 legislative boundaries. Polygon
coordinates are native EPSG:32651, and population fields refer to 2010/2015.

Only selected services are queued. The legacy whole-catalog mode is disabled.
Within each selected service, every advertised queryable layer/table is visited.
Cached batches
resume on the next run. Restricted or unsupported services are recorded; no
authentication or bypass is attempted. Attachments are downloaded when advertised.

`archive/status.json` records progress and individual failures. `archive/worker.log`
is used for a background worker. Stop gracefully with `kill -INT` using the PID
in `archive/worker.pid`, then rerun the same command to resume.

Each layer preserves metadata, an object-ID snapshot, compressed feature batches,
original attributes and native geometries. `features.jsonl` is one feature per line;
`features.esrijson` is a complete Esri feature set with fields and spatial reference.
The latter is **not GeoJSON**; projected coordinates are never labeled longitude/
latitude. Domain definitions, edit timestamps, counts and export hashes are retained.

Completion means every snapshotted ID was returned exactly once. These are live
services, not transactionally frozen exports. Source edits/count changes during a
download are recorded. Distinct thematic layers can repeat the same real-world
bridges and must not be counted as independent assets. Re-running skips complete
layers; use a different `--output` directory for a later fresh snapshot.

The archive is ignored by Git to keep large downloaded data out of commits.
