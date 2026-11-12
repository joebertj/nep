# ODV source databases moved out of the ODV repository

Cold source databases, offline Parquet inputs, historical extracts, and duplicate static Parquet copies are stored here. The ODV runtime retains its live database inputs; the current retained set includes the FY2020–FY2026 budget comparison files, current DPWH/road datasets, the typed PhilGEPS query dataset, merchant lookup data, contract-splitting inputs, and unified-location data. Cold ODV paths are sibling-repository symlinks for local offline builders; those files are not needed by the live site routes.

The large untyped PhilGEPS export is kept locally here but excluded from Git to avoid adding a 1.1 GB Git object. The active typed export remains at its ODV runtime path.

Their original paths, byte sizes, and SHA-256 checksums are recorded in `MOVED_FILES.json`.
