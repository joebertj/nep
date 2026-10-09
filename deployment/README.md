# Private remote interaction

`nep` holds the report source, generated HTML, and private deployment helper.
Keep this repository private because the helper contains the server address.

## Routine ODV deployment through Git

Make and review the ODV changes in `open-data-visualization`, commit them, and
push the intended commit to `origin/main`. The local ODV checkout may contain
unrelated work; stage only the intended files. The server deploy helper refuses
to run if the server checkout has unrelated changes or cannot fast-forward.
It backs up the 19 report HTML and data paths before advancing Git, replaces
them with the committed versions, and preserves server-only homepage edits
when the target commit leaves those templates unchanged. If the frontend or any
report HTML/JSON URL fails its post-update check, it restores the previous commit
and all 19 pre-deployment report paths.

Inspect the server first:

```sh
./deployment/deploy_odv_git.sh inspect
```

Deploy after the intended ODV commit is on `origin/main`:

```sh
./deployment/deploy_odv_git.sh deploy
```

The deploy action asks for `DEPLOY ODV MAIN`, fetches `origin/main`, and
fast-forwards the server checkout. The frontend loads Tera templates per
request, and static reports are served directly, so these file changes need no
service restart. It does not build Rust, install packages, restart services, or
change service configuration. It checks the frontend before and after the
update and returns the checkout to its previous commit if the post-update
check fails.

If deployment refuses because the server tree has unrelated changes or a
published file differs from the target commit, inspect and reconcile those
changes before retrying. The helper never stashes or resets unrelated work.

## Direct intervention scripts

`publish_odv_nep.sh` and `remote.sh` remain available for explicitly directed
direct file publication or read-only inspection. Use them for exceptional
intervention when the Git path is unsuitable, and keep routine releases in Git.

## Direct remote inspection

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
will be `/static/nep-preview/*.html`, including the unlinked congressional
allocation page at `/static/nep-preview/congress.html`.

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
