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
request, and static reports are served directly, so static-only releases need no service restart. If the target commit changes
Rust source or Cargo files, the helper backs up the running binary, builds the
frontend with the locked dependencies, and restarts visualization.service.
It does not install packages or change service configuration. It checks the frontend before and after the
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

## OS security patching

`patch-security-vms.sh` targets the two authorized hosts, `178.128.95.212` and
`165.245.186.194`. The default simulates security-only OS updates:

```sh
./deployment/patch-security-vms.sh --check
```

Apply only after reviewing the simulation for both hosts:

```sh
./deployment/patch-security-vms.sh --apply
```

The apply action requires typing `APPLY SECURITY UPDATES ON BOTH VMS`. Debian
and Ubuntu use the configured `unattended-upgrades` origin allowlist, which the
helper checks for security origins and permits the base release only as a
dependency source; DNF and YUM use security advisories. APT refreshes its indexes
over IPv4 and stops if any source fails. Unsupported package manager/OS
combinations stop without applying updates. This covers system packages such as OpenSSH, NGINX, Python, Rust and
npm when those packages receive OS security advisories. If NGINX is installed,
the helper validates its configuration as root with `sudo nginx -t` and reloads
it only if the service was already active. The update can report that a reboot
is required. Both actions require the local `~/.ssh/klti` key and non-interactive
SSH; apply requires passwordless sudo.

Application dependencies are a separate deployment path. This helper does
not change Python requirements, Cargo.lock, package-lock.json, FastAPI, Tailwind,
or other app dependencies. Those need security audits, lockfile changes, a
build, and deployment so the running apps match the reviewed source.

The VM at `178.128.95.212` timed out over public SSH during the November 21,
2026 preflight. The patch helper routes this allowlisted target through its
verified WireGuard address `10.27.79.2` and uses account `joebertj`, matching
the successful key login. Override the endpoint with
`SECURITY_PATCH_WG_178_128_95_212` if the tunnel address changes. An explicit
`--user` option overrides the per-host SSH account. The Jammy VM routes APT's
`_apt` fetch user over its primary interface because
the host's WireGuard full-tunnel route cannot reach public repositories. Its
`/etc/resolv.conf` uses the active `systemd-resolved` stub, and APT is configured
to use IPv4 because the VM has no IPv6 route. The route exception is limited to
the `_apt` UID; other host and VPN traffic retains its existing routing.

The default SSH user is `joebert`, which matches the BetterGov VM. If the
Better Miagao VM uses another account, pass it explicitly, for example:

```sh
./deployment/patch-security-vms.sh --check --host 178.128.95.212 --user deploy
./deployment/patch-security-vms.sh --apply --host 178.128.95.212 --user deploy
```

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
