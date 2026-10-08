#!/usr/bin/env bash
# Publish the NEP report pages and homepage card update directly, without Git.
set -euo pipefail

REMOTE_HOST="${NEP_DEPLOY_HOST:-165.245.186.194}"
REMOTE_USER="${NEP_DEPLOY_USER:-joebert}"
REMOTE_DIR="${NEP_DEPLOY_DIR:-/home/joebert/open-data-visualization}"
SSH_IDENTITY="${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/../../open-data-visualization" && pwd)"

FILES=(
  templates/visualizations_home.html
  templates/mobile/visualizations_home.html
  static/nep-preview/dpwh.html
  static/nep-preview/fmr.html
  static/nep-preview/nia.html
  static/nep-preview/hfep.html
)
SSH=(ssh -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new)
SCP=(scp -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new)

if [[ ! -r "$SSH_IDENTITY" ]]; then
  echo "SSH identity is not readable: $SSH_IDENTITY" >&2
  exit 2
fi
for file in "${FILES[@]}"; do
  if [[ ! -f "$SOURCE_ROOT/$file" ]]; then
    echo "Missing source file: $SOURCE_ROOT/$file" >&2
    exit 2
  fi
done

ACTION="${1:-inspect}"
if [[ $# -gt 1 ]]; then
  echo "Usage: $0 [inspect|publish]" >&2
  exit 2
fi

case "$ACTION" in
  inspect)
    "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
      "REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE_INSPECT'
set -u
printf '=== ODV repo ===\n'
git -C "$REMOTE_DIR" status --short
printf '\n=== NEP publish targets ===\n'
for file in \
  templates/visualizations_home.html \
  templates/mobile/visualizations_home.html \
  static/nep-preview/dpwh.html \
  static/nep-preview/fmr.html \
  static/nep-preview/nia.html \
  static/nep-preview/hfep.html; do
  if [ -f "$REMOTE_DIR/$file" ]; then
    sha256sum "$REMOTE_DIR/$file"
  else
    printf 'MISSING\t%s\n' "$file"
  fi
done
REMOTE_INSPECT
    ;;
  publish)
    STAGE_ID="nep-publish-$(date +%Y%m%d%H%M%S)-$$"
    STAGE_DIR="$REMOTE_DIR/.$STAGE_ID"
    BACKUP_DIR="/home/$REMOTE_USER/.local/state/nep-deploy-backups/$STAGE_ID"
    printf 'Publishing six files directly to the ODV working tree (no Git operation).\n'
    printf 'Backup will be kept outside the ODV repo.\n'
    "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
      "mkdir -p '$STAGE_DIR/templates/mobile' '$STAGE_DIR/static/nep-preview' '$BACKUP_DIR'"
    for file in "${FILES[@]}"; do
      "${SCP[@]}" "$SOURCE_ROOT/$file" "$REMOTE_USER@$REMOTE_HOST:$STAGE_DIR/$file"
    done
    "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
      "REMOTE_DIR='$REMOTE_DIR' STAGE_DIR='$STAGE_DIR' BACKUP_DIR='$BACKUP_DIR' bash -s" <<'REMOTE_PUBLISH'
set -euo pipefail
files=(
  templates/visualizations_home.html
  templates/mobile/visualizations_home.html
  static/nep-preview/dpwh.html
  static/nep-preview/fmr.html
  static/nep-preview/nia.html
  static/nep-preview/hfep.html
)
rollback() {
  for file in "${files[@]}"; do
    if [ -f "$BACKUP_DIR/$file" ]; then
      mkdir -p "$(dirname "$REMOTE_DIR/$file")"
      cp -p "$BACKUP_DIR/$file" "$REMOTE_DIR/$file"
    elif [ -f "$BACKUP_DIR/.missing/$file" ]; then
      rm -f "$REMOTE_DIR/$file"
    fi
  done
}
trap 'result=$?; if [ "$result" -ne 0 ]; then rollback; fi' EXIT
for file in "${files[@]}"; do
  mkdir -p "$(dirname "$REMOTE_DIR/$file")" "$(dirname "$BACKUP_DIR/$file")"
  if [ -f "$REMOTE_DIR/$file" ]; then
    cp -p "$REMOTE_DIR/$file" "$BACKUP_DIR/$file"
  else
    mkdir -p "$BACKUP_DIR/.missing/$(dirname "$file")"
    : > "$BACKUP_DIR/.missing/$file"
  fi
done
for file in "${files[@]}"; do
  mv -f "$STAGE_DIR/$file" "$REMOTE_DIR/$file"
done
rm -rf "$STAGE_DIR"
trap - EXIT
printf 'Published file checksums:\n'
for file in "${files[@]}"; do sha256sum "$REMOTE_DIR/$file"; done
printf 'Backups: %s\n' "$BACKUP_DIR"
REMOTE_PUBLISH
    ;;
  *)
    echo "Usage: $0 [inspect|publish]" >&2
    exit 2
    ;;
esac
