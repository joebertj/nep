# ODV source databases moved out of the ODV repository

These source-only SQL dumps, workbook, and unused merchant backup files were moved from the adjacent `open-data-visualization` repository after checking Rust route and browser-template references. The live pages continue to use their generated static/API outputs. The active `database/philgeps_merchant_info.parquet` remains in ODV because the Python backend reads it.

The moved build inputs remain available to local ODV scripts through sibling-repository paths. Their original paths, byte sizes, and SHA-256 checksums are recorded in `MOVED_FILES.json`.
