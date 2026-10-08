#!/usr/bin/env bash
# Private remote interaction helper for the BetterGovPH visualization VM.
# Read-only inspection is the default. The only write action copies report
# HTML files into an isolated static preview directory; it never runs the
# upstream reset/build/restart workflow.
set -euo pipefail

REMOTE_HOST="${NEP_DEPLOY_HOST:-165.245.186.194}"
REMOTE_USER="${NEP_DEPLOY_USER:-joebert}"
REMOTE_DIR="${NEP_DEPLOY_DIR:-/home/joebert/open-data-visualization}"
SSH_IDENTITY="${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}"

usage() {
  cat <<'EOF'
Usage: ./deployment/remote.sh [inspect|copy-preview]

  inspect  Read-only remote status and deployment layout (default)
  copy-preview  Copy the four report HTML files into static/nep-preview/

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
      "REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE_READ_ONLY'
set -u
r="$REMOTE_DIR"
printf '%s\n' '=== Repo state ==='
git -C "$r" branch --show-current
git -C "$r" rev-parse --short HEAD
git -C "$r" status --short
printf '\n%s\n' '=== Deployment files ==='
find "$r/deployment" -maxdepth 2 -type f -printf '%P\t%s bytes\n' 2>/dev/null | sort
printf '\n%s\n' '=== Service state ==='
for service in visualization.service visualization_api.service nginx.service; do
  printf '%s: ' "$service"
  systemctl is-active "$service" 2>/dev/null || true
done
printf '\n%s\n' '=== Live web root ==='
ls -lah /var/www/html 2>/dev/null || true
REMOTE_READ_ONLY
    ;;
  copy-preview)
    SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../analysis_output" && pwd)"
    FILES=(dpwh.html fmr.html nia.html hfep.html)
    for file in "${FILES[@]}"; do
      if [[ ! -f "$SOURCE_DIR/$file" ]]; then
        echo "Missing source HTML: $SOURCE_DIR/$file" >&2
        exit 2
      fi
    done
    printf 'This will copy only these HTML files to %s:%s/static/nep-preview/\n' "$REMOTE_USER@$REMOTE_HOST" "$REMOTE_DIR"
    printf '  %s\n' "${FILES[@]}"
    printf 'Type COPY HTML to continue: '
    read -r answer
    [[ "$answer" == "COPY HTML" ]] || { echo "Cancelled."; exit 1; }
    # Create only the new preview directory. No existing page, route, service,
    # or application configuration is changed.
    "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
      "mkdir -p '$REMOTE_DIR/static/nep-preview'"
    SCP=(scp -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 \
      -o StrictHostKeyChecking=accept-new)
    for file in "${FILES[@]}"; do
      "${SCP[@]}" "$SOURCE_DIR/$file" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/static/nep-preview/$file"
    done
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
