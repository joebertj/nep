#!/usr/bin/env bash
# Git deploy; HTTP checks run locally, outside the SSH command.
set -euo pipefail

REMOTE_HOST="${NEP_DEPLOY_HOST:-165.245.186.194}"
REMOTE_USER="${NEP_DEPLOY_USER:-joebert}"
REMOTE_DIR="${NEP_DEPLOY_DIR:-/home/joebert/open-data-visualization}"
SSH_IDENTITY="${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}"
HEALTH_URL="${NEP_DEPLOY_HEALTH_URL:-https://research.bettergov.ph}"
ODV_HEALTH_URL="${NEP_ODV_HEALTH_URL:-https://visualizations.bettergov.ph}"
ACTION="${1:-inspect}"
DEPLOY_COMMIT="${NEP_DEPLOY_COMMIT:-origin/main}"
SSH=(ssh -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

if [[ ! -r "$SSH_IDENTITY" ]]; then echo "SSH identity is not readable: $SSH_IDENTITY" >&2; exit 2; fi
if [[ "$ACTION" == "-h" || "$ACTION" == "--help" || "$ACTION" == "help" ]]; then
  echo "Usage: ./deployment/deploy_odv_git.sh [inspect|diagnose|deploy]"
  echo "Override with NEP_DEPLOY_COMMIT, NEP_DEPLOY_HEALTH_URL, NEP_ODV_HEALTH_URL, NEP_DEPLOY_HOST, NEP_DEPLOY_USER, NEP_DEPLOY_DIR, NEP_SSH_IDENTITY."
  exit 0
fi
if [[ "$ACTION" == "inspect" ]]; then
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" "git -C '$REMOTE_DIR' status --short && git -C '$REMOTE_DIR' branch --show-current && git -C '$REMOTE_DIR' rev-parse --short HEAD"
  exit 0
fi
if [[ "$ACTION" == "diagnose" ]]; then
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" "bash -s" <<'REMOTE_DIAGNOSE'
set -uo pipefail
echo "Service state:"
sudo -n systemctl show --property=Id --property=ActiveState --property=MainPID --property=ActiveEnterTimestamp visualization.service visualization_api.service
echo "Loopback HTTP status (Rust:8888, FastAPI:8001):"
for url in http://127.0.0.1:8888/ http://127.0.0.1:8001/; do
  code="$(curl --connect-timeout 3 --max-time 8 -sS -o /dev/null -w '%{http_code}' "$url" || true)"
  echo "$url -> ${code:-unreachable}"
done
echo "Nginx validation:"
sudo -n nginx -t 2>&1 || true
echo "Loaded visualizations vhost declarations:"
sudo -n nginx -T 2>&1 | awk '
  function brace_delta(line, opens, closes) {
    opens=gsub(/\{/, "{", line)
    closes=gsub(/\}/, "}", line)
    return opens-closes
  }
  /^# configuration file / { source=$0 }
  /^[[:space:]]*server[[:space:]]*\{/ { in_server=1; depth=0; count=0; block="" }
  in_server {
    lines[++count]=$0
    block=block $0 "\n"
    depth+=brace_delta($0)
    if (depth<=0) {
      if (block ~ /server_name[^;]*visualizations\.bettergov\.ph/) {
        print source
        for (i=1; i<=count; i++)
          if (lines[i] ~ /^[[:space:]]*(listen|server_name|location|proxy_pass|root|try_files|return)[[:space:]]/) print lines[i]
      }
      in_server=0
    }
  }
'
echo "Local Nginx HTTPS route (with visualizations host/SNI):"
code="$(curl --connect-timeout 3 --max-time 8 -k -sS -o /dev/null -w '%{http_code}' --resolve visualizations.bettergov.ph:443:127.0.0.1 https://visualizations.bettergov.ph/ || true)"
echo "https://visualizations.bettergov.ph/ -> ${code:-unreachable}"
REMOTE_DIAGNOSE
  exit $?
fi
if [[ "$ACTION" != "deploy" || $# -gt 1 ]]; then
  echo "Usage: ./deployment/deploy_odv_git.sh [inspect|diagnose|deploy]" >&2
  exit 2
fi
if [[ ! "$DEPLOY_COMMIT" =~ ^(origin/main|[0-9a-fA-F]{7,40})$ ]]; then
  echo "Invalid NEP_DEPLOY_COMMIT: use origin/main or a commit hash." >&2
  exit 2
fi

printf 'Deploy %s from origin/main history? [y/N] ' "$DEPLOY_COMMIT"
read -r answer
case "$answer" in
  y|Y|yes|YES|Yes) ;;
  *) echo "Cancelled."; exit 1 ;;
esac

if ! deploy_output="$("${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" "REMOTE_DIR='$REMOTE_DIR' DEPLOY_COMMIT='$DEPLOY_COMMIT' bash -s" <<'REMOTE_DEPLOY'
set -euo pipefail
r="$REMOTE_DIR"
if [[ "$(git -C "$r" branch --show-current)" != "main" ]]; then
  echo "Refusing deployment: checkout is not on main." >&2
  exit 2
fi
previous="$(git -C "$r" rev-parse HEAD)"
if ! git -C "$r" diff --cached --quiet; then
  echo "Refusing deployment: server checkout has staged changes." >&2
  exit 2
fi
dirty_paths="$(git -C "$r" diff --name-only; git -C "$r" ls-files --others --exclude-standard)"
unrelated_paths="$(
  git -C "$r" diff --name-only -- . \
    ':(exclude,glob)static/nep-preview/**' \
    ':(exclude)templates/visualizations_home.html' \
    ':(exclude)templates/mobile/visualizations_home.html'
  git -C "$r" ls-files --others --exclude-standard -- . \
    ':(exclude,glob)static/nep-preview/**' \
    ':(exclude)templates/visualizations_home.html' \
    ':(exclude)templates/mobile/visualizations_home.html'
)"
if [[ -n "$unrelated_paths" ]]; then
  echo "Refusing deployment: server checkout has changes outside the deployable assets." >&2
  exit 2
fi
git -C "$r" fetch origin main
if [[ "$DEPLOY_COMMIT" == "origin/main" ]]; then
  target="$(git -C "$r" rev-parse FETCH_HEAD)"
else
  target="$(git -C "$r" rev-parse "$DEPLOY_COMMIT^{commit}")"
  git -C "$r" merge-base --is-ancestor "$target" FETCH_HEAD
fi
rollback_stash="-"
if [[ -n "$dirty_paths" ]]; then
  stash_before="$(git -C "$r" rev-parse -q --verify refs/stash 2>/dev/null || true)"
  git -C "$r" stash push --include-untracked -m "odv deploy rollback $previous"
  stash_after="$(git -C "$r" rev-parse -q --verify refs/stash 2>/dev/null || true)"
  if [[ -z "$stash_after" || "$stash_after" == "$stash_before" ]]; then
    echo "Refusing deployment: Git could not stash the server changes." >&2
    exit 2
  fi
  rollback_stash="$stash_after"
fi
if [[ "$previous" != "$target" ]]; then
  restart_api=false
  restart_nginx=false
  restart_frontend=false
  install_service_units=false
  configure_shared_proxy=false
  rebuild_frontend=false
  binary="$r/target/release/open-data-visualization"
  binary_backup="-"
  if ! git -C "$r" diff --quiet "$previous" "$target" -- src Cargo.toml Cargo.lock; then
    if [[ ! -x "$binary" ]]; then
      echo "Refusing deployment: the current Rust frontend binary is missing; cannot preserve rollback." >&2
      exit 2
    fi
    rebuild_frontend=true
    restart_frontend=true
    binary_backup="$binary.deploy-backup-$previous"
    cp -p "$binary" "$binary_backup"
  fi
  if ! git -C "$r" diff --quiet "$previous" "$target" -- visualization.py deployment/visualization_api.service; then restart_api=true; fi
  if ! git -C "$r" diff --quiet "$previous" "$target" -- deployment/visualization.service; then
    restart_frontend=true
    install_service_units=true
  fi
  if ! git -C "$r" diff --quiet "$previous" "$target" -- deployment/visualization_api.service; then install_service_units=true; fi
  if ! git -C "$r" diff --quiet "$previous" "$target" -- deployment/visualizations_nginx.conf deployment/configure_shared_nginx_proxy.sh deployment/visualization.service deployment/visualization_api.service; then
    restart_nginx=true
    configure_shared_proxy=true
  fi
  git -C "$r" reset --hard "$target"
  if [[ "$rollback_stash" != "-" ]]; then
    for path in templates/visualizations_home.html templates/mobile/visualizations_home.html; do
      if git -C "$r" diff --quiet "$previous" "$target" -- "$path" &&
         git -C "$r" diff --quiet "$rollback_stash" -- "$path"; then
        git -C "$r" restore --source="$rollback_stash" --worktree -- "$path"
      fi
    done
  fi
else
  restart_api=false
  restart_nginx=false
  restart_frontend=false
  install_service_units=false
  configure_shared_proxy=false
  rebuild_frontend=false
  binary_backup="-"
fi

# Restart services only when committed files warrant it.
if [[ "$rebuild_frontend" == true ]]; then
  if ! (cd "$r" && cargo build --locked --release); then
    cp -p "$binary_backup" "$binary"
    git -C "$r" reset --hard "$previous"
    rm -f "$binary_backup"
    echo "Rust build failed; restored the previous checkout and frontend binary." >&2
    exit 2
  fi
fi

if [[ "$configure_shared_proxy" == true ]]; then
  echo "Updating the existing shared Nginx proxy (no additional vhost)..."
  bash "$r/deployment/configure_shared_nginx_proxy.sh"
fi

if [[ "$install_service_units" == true ]]; then
  echo "Installing updated systemd service units..."
  sudo -n install -m 644 "$r/deployment/visualization.service" /etc/systemd/system/visualization.service
  sudo -n install -m 644 "$r/deployment/visualization_api.service" /etc/systemd/system/visualization_api.service
  sudo -n systemctl daemon-reload
  echo "Systemd service units installed and daemon reloaded."
fi

if [[ "$restart_frontend" == true ]]; then
  echo "Restarting Rust frontend (visualization.service)..."
  sudo -n systemctl restart visualization.service
  sudo -n systemctl is-active --quiet visualization.service
  echo "Rust frontend restart confirmed."
fi
if [[ "$restart_api" == true ]]; then
  echo "Restarting FastAPI (visualization_api.service)..."
  sudo -n systemctl restart visualization_api.service
  sudo -n systemctl is-active --quiet visualization_api.service
  api_pid="$(sudo -n systemctl show --property=MainPID --value visualization_api.service)"
  api_started="$(sudo -n systemctl show --property=ActiveEnterTimestamp --value visualization_api.service)"
  echo "FastAPI restart confirmed: active (PID ${api_pid:-unknown}; since ${api_started:-unknown})."
fi
if [[ "$restart_frontend" == false && "$restart_api" == false && "$restart_nginx" == false ]]; then
  echo "No code or deployed service configuration changed; no services restarted."
fi
for url in http://127.0.0.1:8888/ http://127.0.0.1:8001/; do
  if ! curl --connect-timeout 5 --max-time 15 -s -f "$url" >/dev/null; then
    echo "Local service health check failed at $url." >&2
    sudo -n systemctl --no-pager --full status visualization.service visualization_api.service || true
    exit 2
  fi
done
echo "Local Rust and FastAPI health checks passed."
printf '__DEPLOY_META__ %s %s %s %s %s %s %s %s\n' "$previous" "$target" "$restart_api" "$restart_nginx" "$restart_frontend" "$rebuild_frontend" "$rollback_stash" "$binary_backup"
REMOTE_DEPLOY
)"; then
  printf '%s\n' "$deploy_output" >&2
  exit 2
fi
deploy_meta=""
while IFS= read -r line; do
  case "$line" in
    __DEPLOY_META__\ *) deploy_meta="${line#__DEPLOY_META__ }" ;;
    *) printf '%s\n' "$line" ;;
  esac
done <<< "$deploy_output"
read -r previous target restart_api restart_nginx restart_frontend rebuild_frontend rollback_stash binary_backup <<< "$deploy_meta"

if ! curl --silent --show-error --fail --max-time 15 "$ODV_HEALTH_URL/" >/dev/null ||
   ! curl --silent --show-error --fail --max-time 15 "$ODV_HEALTH_URL/api/philgeps/v2/awards" >/dev/null ||
   ! curl --silent --show-error --fail --max-time 15 "$HEALTH_URL/" >/dev/null ||
   ! curl --silent --show-error --fail --max-time 15 "$HEALTH_URL/static/nep-preview/" >/dev/null; then
  echo "Public HTTP health check failed (visualizations: $ODV_HEALTH_URL; research: $HEALTH_URL)." >&2
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
    "REMOTE_DIR='$REMOTE_DIR' PREVIOUS='$previous' RESTART_API='$restart_api' RESTART_NGINX='$restart_nginx' RESTART_FRONTEND='$restart_frontend' REBUILD_FRONTEND='$rebuild_frontend' BINARY_BACKUP='$binary_backup' ROLLBACK_STASH='$rollback_stash' bash -s" <<'REMOTE_ROLLBACK'
set -euo pipefail
r="$REMOTE_DIR"
git -C "$r" reset --hard "$PREVIOUS"
if [[ "$REBUILD_FRONTEND" == true && "$BINARY_BACKUP" != "-" ]]; then
  cp -p "$BINARY_BACKUP" "$r/target/release/open-data-visualization"
  rm -f "$BINARY_BACKUP"
fi
if [[ "$ROLLBACK_STASH" != "-" ]]; then git -C "$r" stash apply --index "$ROLLBACK_STASH"; fi
if [[ "$RESTART_API" == true || "$RESTART_FRONTEND" == true ]]; then
  sudo -n install -m 644 "$r/deployment/visualization.service" /etc/systemd/system/visualization.service
  sudo -n install -m 644 "$r/deployment/visualization_api.service" /etc/systemd/system/visualization_api.service
  sudo -n systemctl daemon-reload
fi
if [[ "$RESTART_FRONTEND" == true ]]; then sudo -n systemctl restart visualization.service; fi
if [[ "$RESTART_API" == true ]]; then sudo -n systemctl restart visualization_api.service; fi
REMOTE_ROLLBACK
  exit 1
fi
if [[ "$rollback_stash" != "-" ]]; then
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" \
    "REMOTE_DIR='$REMOTE_DIR' ROLLBACK_STASH='$rollback_stash' bash -s" <<'REMOTE_FINALIZE'
set -euo pipefail
r="$REMOTE_DIR"
if [[ "$(git -C "$r" rev-parse -q --verify refs/stash 2>/dev/null || true)" == "$ROLLBACK_STASH" ]]; then
  git -C "$r" stash drop stash@{0}
fi
REMOTE_FINALIZE
fi
if [[ "$binary_backup" != "-" ]]; then
  "${SSH[@]}" "$REMOTE_USER@$REMOTE_HOST" "rm -f '$binary_backup'"
fi
echo "Public HTTP health checks passed for visualizations and research."
echo "Deployment summary: FastAPI restarted=$restart_api; Rust frontend restarted=$restart_frontend; shared Nginx config update triggered=$restart_nginx."
