#!/usr/bin/env bash
# Deploy ODV main through Git without running the broad build/restart script.
# The direct-copy helpers remain available for explicitly approved intervention.
set -euo pipefail

REMOTE_HOST="${NEP_DEPLOY_HOST:-165.245.186.194}"
REMOTE_USER="${NEP_DEPLOY_USER:-joebert}"
REMOTE_DIR="${NEP_DEPLOY_DIR:-/home/joebert/open-data-visualization}"
SSH_IDENTITY="${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}"

usage() {
  cat <<'EOF'
Usage: ./deployment/deploy_odv_git.sh [inspect|deploy]

  inspect  Read-only server checkout status (default)
  deploy   Fetch origin/main, fast-forward the server checkout, and check the
           local frontend response. No service restart is needed for these files.

Overrides: NEP_DEPLOY_HOST, NEP_DEPLOY_USER, NEP_DEPLOY_DIR, NEP_SSH_IDENTITY
EOF
}

if [[ ! -r "$SSH_IDENTITY" ]]; then
  echo "SSH identity is not readable: $SSH_IDENTITY" >&2
  exit 2
fi

ACTION="${1:-inspect}"
if [[ $# -gt 1 ]]; then usage >&2; exit 2; fi

SSH=(ssh -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new)

case "$ACTION" in
  inspect)
    "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
      "REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE_INSPECT'
set -u
r="$REMOTE_DIR"
printf '=== Checkout ===\n'
git -C "$r" branch --show-current
git -C "$r" rev-parse --short HEAD
git -C "$r" status --short
printf '\n=== Frontend service ===\n'
systemctl is-active visualization.service 2>/dev/null || true
systemctl --no-pager --full status visualization.service 2>/dev/null | sed -n '1,18p' || true
printf '\n=== Listening TCP sockets ===\n'
ss -ltnp 2>/dev/null | sed -n '1,24p' || true
printf '\n=== Homepage edits vs checkout ===\n'
git -C "$r" diff --unified=3 -- templates/visualizations_home.html templates/mobile/visualizations_home.html | sed -n '1,180p'
sha256sum "$r/templates/visualizations_home.html" "$r/templates/mobile/visualizations_home.html"
printf '\n=== Nginx checks with the site Host header ===\n'
for path in / /static/nep-preview/budget-innovations.html /static/nep-preview/congress.html /static/nep-preview/deped.html /static/nep-preview/dpwh-hgab-comparison.html /static/nep-preview/dpwh-hgab.html /static/nep-preview/dpwh.html /static/nep-preview/fmr.html /static/nep-preview/hfep.html /static/nep-preview/nia-irrigation.html /static/nep-preview/nia.html /static/nep-preview/rcs.html; do
  status="$(curl --silent --show-error --location --max-time 8 --resolve 'research.bettergov.ph:443:127.0.0.1' --output /dev/null --write-out '%{http_code}' "http://research.bettergov.ph$path" 2>/dev/null || true)"
  printf '%s %s\n' "$status" "$path"
done
printf '\n=== Service working directory and static files ===\n'
systemctl show visualization.service --property=WorkingDirectory --property=ExecStart 2>/dev/null || true
ls -lh "$r/static/nep-preview" 2>/dev/null || true
printf 'favicon status: '
curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}\n' http://127.0.0.1/static/favicon.ico 2>/dev/null || true
app_ip="$(ss -H -ltn 'sport = :8888' 2>/dev/null | awk 'NR==1 {sub(/:[0-9]+$/, "", $4); print $4}')"
if [[ -n "$app_ip" ]]; then
  printf 'Direct Actix listener checks (%s):\n' "$app_ip"
  for path in / /static/nep-preview/budget-innovations.html /static/nep-preview/congress.html /static/nep-preview/deped.html /static/nep-preview/dpwh-hgab-comparison.html /static/nep-preview/dpwh-hgab.html /static/nep-preview/dpwh.html /static/nep-preview/fmr.html /static/nep-preview/hfep.html /static/nep-preview/nia-irrigation.html /static/nep-preview/nia.html /static/nep-preview/rcs.html; do
    status="$(curl --silent --show-error --max-time 5 --output /dev/null --write-out '%{http_code}' "http://$app_ip:8888$path" 2>/dev/null || true)"
    printf '%s %s\n' "$status" "$path"
  done
fi
REMOTE_INSPECT
    ;;
  deploy)
    printf 'This will fast-forward the server checkout to origin/main and check the local frontend response.\n'
    printf 'Type DEPLOY ODV MAIN to continue: '
    read -r answer
    [[ "$answer" == "DEPLOY ODV MAIN" ]] || { echo "Cancelled."; exit 1; }
    "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
      "REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE_DEPLOY'
set -euo pipefail
r="$REMOTE_DIR"
files=(
  static/nep-preview/ph-location-representatives.js
  static/nep-preview/budget-innovations-data.json
  static/nep-preview/budget-innovations.html
  static/nep-preview/congress-data.json
  static/nep-preview/congress.html
  static/nep-preview/deped-data.json
  static/nep-preview/deped.html
  static/nep-preview/dpwh-data.json
  static/nep-preview/dpwh-hgab-comparison.html
  static/nep-preview/dpwh-hgab-comparison.json
  static/nep-preview/dpwh-hgab.html
  static/nep-preview/dpwh.html
  static/nep-preview/fmr.html
  static/nep-preview/hfep.html
  static/nep-preview/hgab-revision-data.json
  static/nep-preview/nia-irrigation-data.json
  static/nep-preview/nia-irrigation.html
  static/nep-preview/nia.html
  static/nep-preview/rcs-data.json
  static/nep-preview/rcs.html
)
health_files=(
  static/nep-preview/ph-location-representatives.js
  static/nep-preview/budget-innovations-data.json
  static/nep-preview/budget-innovations.html
  static/nep-preview/congress-data.json
  static/nep-preview/congress.html
  static/nep-preview/deped-data.json
  static/nep-preview/deped.html
  static/nep-preview/dpwh-hgab-comparison.html
  static/nep-preview/dpwh-hgab-comparison.json
  static/nep-preview/dpwh-hgab.html
  static/nep-preview/dpwh-data.json
  static/nep-preview/dpwh.html
  static/nep-preview/fmr.html
  static/nep-preview/hfep.html
  static/nep-preview/hgab-revision-data.json
  static/nep-preview/nia-irrigation-data.json
  static/nep-preview/nia-irrigation.html
  static/nep-preview/nia.html
  static/nep-preview/rcs-data.json
  static/nep-preview/rcs.html
)

if [[ "$(git -C "$r" branch --show-current)" != "main" ]]; then
  echo "Refusing deployment: server checkout is not on main." >&2
  exit 2
fi
if ! git -C "$r" diff --cached --quiet; then
  echo "Refusing deployment: the server has staged changes." >&2
  git -C "$r" status --short >&2
  exit 2
fi
previous="$(git -C "$r" rev-parse HEAD)"
git -C "$r" fetch origin main
target="$(git -C "$r" rev-parse FETCH_HEAD)"

# The direct publisher may have left the release files dirty in the checkout.
# Keep server-only homepage edits when this commit does not change those
# templates. Replace the report files with the committed versions after
# backing up every release path for rollback.
dirty_paths="$(git -C "$r" diff --name-only; git -C "$r" diff --cached --name-only; git -C "$r" ls-files --others --exclude-standard)"
preserve_templates=()
if [[ -n "$dirty_paths" ]]; then
  while IFS= read -r path; do
      case "$path" in
        templates/visualizations_home.html|templates/mobile/visualizations_home.html)
        worktree_blob="$(git -C "$r" hash-object -- "$path")"
        target_blob="$(git -C "$r" rev-parse "$target:$path")"
        if [[ "$worktree_blob" == "$target_blob" ]]; then
          # A direct publication already placed the committed template here.
          continue
        fi
        previous_blob="$(git -C "$r" rev-parse "$previous:$path")"
        if [[ "$previous_blob" != "$target_blob" ]]; then
          echo "Refusing deployment: origin/main also changes server-edited $path." >&2
          exit 2
        fi
        preserve_templates+=("$path")
        ;;
        *)
        release_path=false
        for file in "${files[@]}"; do
          if [[ "$path" == "$file" ]]; then release_path=true; break; fi
        done
        if [[ "$release_path" != true ]]; then
          echo "Refusing deployment: unrelated server changes exist." >&2
          git -C "$r" status --short >&2
          exit 2
        fi
        ;;
      esac
  done <<< "$dirty_paths"
fi
if ! git -C "$r" merge-base --is-ancestor "$previous" "$target"; then
  echo "Refusing deployment: origin/main does not fast-forward the server commit." >&2
  exit 2
fi
if [[ "$previous" == "$target" && -z "$dirty_paths" ]]; then
  echo "Server is already at origin/main ($target); no deployment needed."
  exit 0
fi

app_ip="$(ss -H -ltn 'sport = :8888' 2>/dev/null | awk 'NR==1 {sub(/:[0-9]+$/, "", $4); print $4}')"
if [[ -z "$app_ip" ]]; then
  echo "Refusing deployment: no Actix listener was found on port 8888." >&2
  exit 2
fi
health_base="http://$app_ip:8888"
if ! curl --silent --show-error --fail "$health_base/" >/dev/null; then
  echo "Refusing deployment: frontend health check failed before update." >&2
  exit 2
fi

# Back up all release paths. The report files can be outdated direct copies;
# template edits are restored after the Git fast-forward.
backup="$(mktemp -d /tmp/odv-git-deploy.XXXXXX)"
for file in "${files[@]}"; do
  if [[ -e "$r/$file" ]]; then
    mkdir -p "$backup/$(dirname "$file")"
    cp -a "$r/$file" "$backup/$file"
    touch "$backup/$file.existed"
  fi
done

# HEAD is an ancestor of target. The only preserved dirt is in templates that
# are unchanged by this commit; all report assets are replaced by Git blobs.
git -C "$r" reset --hard "$target"
for file in "${preserve_templates[@]}"; do
  cp -a "$backup/$file" "$r/$file"
done

healthy=true
if ! curl --silent --show-error --fail "$health_base/" >/dev/null; then
  healthy=false
fi
for file in "${health_files[@]}"; do
  if ! curl --silent --show-error --fail "$health_base/$file" >/dev/null; then
    healthy=false
  fi
done
if [[ "$healthy" == true ]]; then
  rm -rf "$backup"
  echo "Deployment succeeded at $(git -C "$r" rev-parse --short HEAD)."
  if [[ ${#preserve_templates[@]} -gt 0 ]]; then
    echo "Preserved server-only template edits: ${preserve_templates[*]}"
  fi
  exit 0
fi

echo "Frontend health check failed; rolling back to $previous." >&2
git -C "$r" reset --hard "$previous"
for file in "${files[@]}"; do
  if [[ -f "$backup/$file.existed" ]]; then
    mkdir -p "$r/$(dirname "$file")"
    cp -a "$backup/$file" "$r/$file"
  else
    rm -f "$r/$file"
  fi
done
rm -rf "$backup"
echo "Rolled back to $(git -C "$r" rev-parse --short HEAD)." >&2
exit 1
REMOTE_DEPLOY
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
