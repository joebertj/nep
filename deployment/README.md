# Private remote interaction

`nep` holds the report source, generated HTML, and private deployment helper.
Keep this repository private because the helper contains the server address.
Do not edit or deploy `open-data-visualization` as part of this preview stage.

## Read-only inspection

```sh
./deployment/remote.sh inspect
```

Inspection is the default. It reports repository state, deployment filenames,
service activity, and the web-root listing without changing the server.

## Preview copy (not yet run)

```sh
./deployment/remote.sh copy-preview
```

After the explicit `COPY HTML` confirmation, this copies only `dpwh.html`,
`fmr.html`, `nia.html`, and `hfep.html` from `analysis_output/` into the new
`static/nep-preview/` directory in the remote checkout. The reports are served
by the existing Actix static-file mapping at `/static/`, so their preview paths
will be `/static/nep-preview/dpwh.html`, `/static/nep-preview/fmr.html`,
`/static/nep-preview/nia.html`, and `/static/nep-preview/hfep.html`.

The helper creates only that new directory and does not overwrite current
templates, edit routes, reset Git, build binaries, install packages, change
service configuration, or restart services. The copy command has not been run;
remote access remains read-only until separately directed.

FMR and NIA repeat-candidate downloads are embedded in their HTML, keeping the
four-file copy self-contained. Regenerate those pages with
`python3 analyze_fmr_nia_repeats.py` after changing the source analysis or
candidate data.

## Observed remote layout

Read-only inspection found the Rust frontend, Python API, and nginx services
active. The app serves `./static/` under `/static/`; the existing `/nep` route
renders Tera templates. The existing upstream `deployment/restart.sh` resets
the checkout to `origin/main`, builds the full application, installs
requirements, and restarts services. That workflow is intentionally excluded
from this preview helper.
