#!/usr/bin/env bash
# Git deploy; HTTP checks run locally, outside the SSH command.
set -euo pipefail

REMOTE_HOST="${NEP_DEPLOY_HOST:-165.245.186.194}"
REMOTE_USER="${NEP_DEPLOY_USER:-joebert}"
REMOTE_DIR="${NEP_DEPLOY_DIR:-/home/joebert/open-data-visualization}"
SSH_IDENTITY="${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}"
HEALTH_URL="${NEP_DEPLOY_HEALTH_URL:-https://research.bettergov.ph}"
ACTION="${1:-inspect}"
DEPLOY_COMMIT="${NEP_DEPLOY_COMMIT:-origin/main}"
SSH=(ssh -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

if [[ ! -r "$SSH_IDENTITY" ]]; then echo "SSH identity is not readable: $SSH_IDENTITY" >&2; exit 2; fi
if [[ "$ACTION" == "-h" || "$ACTION" == "--help" || "$ACTION" == "help" ]]; then
  echo "Usage: ./deployment/deploy_odv_git.sh [inspect|deploy]"
  echo "Override with NEP_DEPLOY_COMMIT, NEP_DEPLOY_HEALTH_URL, NEP_DEPLOY_HOST, NEP_DEPLOY_USER, NEP_DEPLOY_DIR, NEP_SSH_IDENTITY."
  exit 0
fi
if [[ "$ACTION" == "inspect" ]]; then
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" "git -C '$REMOTE_DIR' status --short && git -C '$REMOTE_DIR' branch --show-current && git -C '$REMOTE_DIR' rev-parse --short HEAD"
  exit 0
fi
if [[ "$ACTION" != "deploy" || $# -gt 1 ]]; then
  echo "Usage: ./deployment/deploy_odv_git.sh [inspect|deploy]" >&2
  exit 2
fi
if [[ ! "$DEPLOY_COMMIT" =~ ^(origin/main|[0-9a-fA-F]{7,40})$ ]]; then
  echo "Invalid NEP_DEPLOY_COMMIT: use origin/main or a commit hash." >&2
  exit 2
fi

printf 'Deploy %s from origin/main history? Type DEPLOY ODV MAIN: ' "$DEPLOY_COMMIT"
read -r answer
[[ "$answer" == "DEPLOY ODV MAIN" ]] || { echo "Cancelled."; exit 1; }

deploy_output="$("${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" "REMOTE_DIR='$REMOTE_DIR' DEPLOY_COMMIT='$DEPLOY_COMMIT' bash -s" <<'REMOTE_DEPLOY'
set -euo pipefail
r="$REMOTE_DIR"
if [[ "$(git -C "$r" branch --show-current)" != "main" ]]; then
  echo "Refusing deployment: checkout is not on main." >&2
  exit 2
fi
previous="$(git -C "$r" rev-parse HEAD)"
if [[ -n "$(git -C "$r" status --porcelain)" ]]; then
  echo "Refusing deployment: server checkout has local changes." >&2
  exit 2
fi
git -C "$r" fetch origin main
if [[ "$DEPLOY_COMMIT" == "origin/main" ]]; then
  target="$(git -C "$r" rev-parse FETCH_HEAD)"
else
  target="$(git -C "$r" rev-parse "$DEPLOY_COMMIT^{commit}")"
  git -C "$r" merge-base --is-ancestor "$target" FETCH_HEAD
fi
if [[ "$previous" != "$target" ]]; then
  restart_frontend=false
  restart_api=false
  restart_nginx=false
  if ! git -C "$r" diff --quiet "$previous" "$target" -- src Cargo.toml Cargo.lock; then
    echo "Refusing deployment: Rust changes require a build, which this Git-and-restart-only deploy does not run." >&2
    exit 2
  fi
  if ! git -C "$r" diff --quiet "$previous" "$target" -- visualization.py; then restart_api=true; fi
  if ! git -C "$r" diff --quiet "$previous" "$target" -- 'deployment/*.conf'; then restart_nginx=true; fi
  git -C "$r" reset --hard "$target"
  if [[ "$restart_frontend" == true ]]; then sudo -n systemctl restart visualization.service; fi
  if [[ "$restart_api" == true ]]; then sudo -n systemctl restart visualization_api.service; fi
  if [[ "$restart_nginx" == true ]]; then sudo -n systemctl restart nginx.service; fi
else
  restart_frontend=false
  restart_api=false
  restart_nginx=false
fi
printf '__DEPLOY_META__ %s %s %s %s %s\n' "$previous" "$target" "$restart_frontend" "$restart_api" "$restart_nginx"
REMOTE_DEPLOY
)"
deploy_meta=""
while IFS= read -r line; do
  case "$line" in
    __DEPLOY_META__\ *) deploy_meta="${line#__DEPLOY_META__ }" ;;
    *) printf '%s\n' "$line" ;;
  esac
done <<< "$deploy_output"
read -r previous target restart_frontend restart_api restart_nginx <<< "$deploy_meta"

if ! curl --silent --show-error --fail --max-time 15 "$HEALTH_URL/" >/dev/null ||
   ! curl --silent --show-error --fail --max-time 15 "$HEALTH_URL/static/nep-preview/" >/dev/null; then
  echo "Local HTTP health check failed for $HEALTH_URL." >&2
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
    "REMOTE_DIR='$REMOTE_DIR' PREVIOUS='$previous' RESTART_FRONTEND='$restart_frontend' RESTART_API='$restart_api' RESTART_NGINX='$restart_nginx' bash -s" <<'REMOTE_ROLLBACK'
set -euo pipefail
r="$REMOTE_DIR"
git -C "$r" reset --hard "$PREVIOUS"
if [[ "$RESTART_FRONTEND" == true ]]; then sudo -n systemctl restart visualization.service; fi
if [[ "$RESTART_API" == true ]]; then sudo -n systemctl restart visualization_api.service; fi
if [[ "$RESTART_NGINX" == true ]]; then sudo -n systemctl restart nginx.service; fi
REMOTE_ROLLBACK
  exit 1
fi
echo "Local HTTP health checks passed."
