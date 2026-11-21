#!/usr/bin/env bash
set -euo pipefail

# Security-advisory updates only for the two explicitly listed VMs.
readonly HOSTS=(178.128.95.212 165.245.186.194)
MODE=check
TARGET=all
REMOTE_USER="${SECURITY_PATCH_USER:-}"
SSH_IDENTITY="${SECURITY_PATCH_SSH_IDENTITY:-${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}}"

usage() {
  cat <<'HELP'
Usage: deployment/patch-security-vms.sh [--check|--apply] [--host IP|all] [--user USER] [--identity FILE]

  --check          Simulate security-only OS updates (default)
  --apply          Apply security-only OS updates; requires exact confirmation
  --host IP        Select one allowlisted VM (default: both)
  --user USER      SSH user (defaults per host: joebert; WireGuard host: joebertj)
  --identity FILE  SSH private key (default: ~/.ssh/klti)

Uses Debian/Ubuntu security pockets or DNF/YUM security advisories only.
Unsupported OS/package-manager combinations fail closed. Does not update
application lockfiles (FastAPI, Tailwind, npm or Cargo dependencies), deploy
application code, or perform a general OS upgrade.
HELP
}

while (($#)); do
  case "$1" in
    --check) MODE=check ;;
    --apply) MODE=apply ;;
    --host) (($# >= 2)) || { usage >&2; exit 2; }; TARGET="$2"; shift ;;
    --user) (($# >= 2)) || { usage >&2; exit 2; }; REMOTE_USER="$2"; shift ;;
    --identity) (($# >= 2)) || { usage >&2; exit 2; }; SSH_IDENTITY="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$TARGET" == all ]]; then
  SELECTED_HOSTS=("${HOSTS[@]}")
elif [[ "$TARGET" == 178.128.95.212 || "$TARGET" == 165.245.186.194 ]]; then
  SELECTED_HOSTS=("$TARGET")
else
  echo "Host is not on the authorized target list: $TARGET" >&2; exit 2
fi
command -v ssh >/dev/null 2>&1 || { echo "Required command not found: ssh" >&2; exit 2; }
[[ -r "$SSH_IDENTITY" ]] || { echo "SSH identity is not readable: $SSH_IDENTITY" >&2; exit 2; }
SSH=(ssh -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 \
  -o ServerAliveInterval=15 -o ServerAliveCountMax=2 -o StrictHostKeyChecking=accept-new)

REMOTE_SECURITY='set -euo pipefail
echo "Host: $(hostname -f 2>/dev/null || hostname)"
[[ -r /etc/os-release ]] || { echo "Cannot identify OS" >&2; exit 2; }
. /etc/os-release
echo "OS: ${PRETTY_NAME:-${ID:-unknown}}"
sudo -n true
if command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1; then
  case "${ID:-}" in ubuntu|debian) ;; *) echo "APT OS is not Ubuntu/Debian; refusing to guess security suite" >&2; exit 4 ;; esac
  echo "Refreshing APT indexes (IPv4, fail on any repository error)"
  sudo apt-get -o Acquire::ForceIPv4=true update --error-on=any
  origins="$(apt-config dump | grep ^Unattended-Upgrade::Allowed-Origins:: | cut -d \" -f 2)"
  [[ -n "$origins" ]] || { echo "No unattended-upgrades origin allowlist is configured" >&2; exit 4; }
  while IFS= read -r origin; do
    [[ "$origin" == *-security || "$origin" == *-apps-security || "$origin" == *-infra-security || "$origin" == "\${distro_id}:\${distro_codename}" ]] || {
      echo "Non-security unattended-upgrades origin is enabled: $origin" >&2; exit 4;
    }
  done <<<"$origins"
  echo "Security-only simulation using allowed origins: ${origins//$'\n'/, }"
  sudo unattended-upgrade --dry-run --debug
elif command -v dnf >/dev/null 2>&1; then
  echo "Security-only simulation via DNF advisory metadata"
  sudo dnf upgrade-minimal --security --assumeno
elif command -v yum >/dev/null 2>&1; then
  echo "Security-only simulation via YUM advisory metadata"
  sudo yum update-minimal --security --assumeno
else
  echo "Unsupported package manager; no changes made" >&2; exit 4
fi
echo "System runtime inventory:"
for bin in sshd nginx python3 rustc cargo node npm; do
  if command -v "$bin" >/dev/null 2>&1; then
    case "$bin" in
      nginx) version="$(nginx -v 2>&1 || true)" ;;
      sshd)
        if command -v dpkg-query >/dev/null 2>&1; then
          version="$(dpkg-query -W -f=\${Version} openssh-server 2>/dev/null || true)"
        elif command -v rpm >/dev/null 2>&1; then
          version="$(rpm -q --qf "%{VERSION}-%{RELEASE}" openssh-server 2>/dev/null || true)"
        else
          version="$(ssh -V 2>&1 || true)"
        fi
        ;;
      *) version="$("$bin" --version 2>&1 | head -n 1 || true)" ;;
    esac
    printf "  %s: %s\n" "$bin" "${version:-installed}"
  fi
done
echo "App dependency note: OS security updates do not patch npm/Cargo/Python lockfile dependencies."'

REMOTE_APPLY='set -euo pipefail
[[ -r /etc/os-release ]] || { echo "Cannot identify OS" >&2; exit 2; }
. /etc/os-release
sudo -n true
if command -v apt-get >/dev/null 2>&1 && command -v dpkg-query >/dev/null 2>&1; then
  case "${ID:-}" in ubuntu|debian) ;; *) echo "APT OS is not Ubuntu/Debian; refusing to guess security suite" >&2; exit 4 ;; esac
  sudo apt-get -o Acquire::ForceIPv4=true update --error-on=any
  origins="$(apt-config dump | grep ^Unattended-Upgrade::Allowed-Origins:: | cut -d \" -f 2)"
  [[ -n "$origins" ]] || { echo "No unattended-upgrades origin allowlist is configured" >&2; exit 4; }
  while IFS= read -r origin; do
    [[ "$origin" == *-security || "$origin" == *-apps-security || "$origin" == *-infra-security || "$origin" == "\${distro_id}:\${distro_codename}" ]] || {
      echo "Non-security unattended-upgrades origin is enabled: $origin" >&2; exit 4;
    }
  done <<<"$origins"
  sudo env DEBIAN_FRONTEND=noninteractive unattended-upgrade
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf upgrade-minimal -y --security
elif command -v yum >/dev/null 2>&1; then
  sudo yum update-minimal -y --security
else
  echo "Unsupported package manager; no changes made" >&2; exit 4
fi
if command -v nginx >/dev/null 2>&1; then
  echo "Validating NGINX config as root"
  sudo nginx -t
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nginx; then
    sudo systemctl reload nginx
    systemctl is-active --quiet nginx
  fi
fi
if command -v systemctl >/dev/null 2>&1; then
  [[ ! -e /var/run/reboot-required ]] || echo "REBOOT REQUIRED: /var/run/reboot-required"
  systemctl is-active --quiet ssh 2>/dev/null && echo "SSH service active" || true
  systemctl is-active --quiet sshd 2>/dev/null && echo "SSHD service active" || true
fi
echo "Security-advisory package update command completed."'

echo "Selected hosts: ${SELECTED_HOSTS[*]}"
if [[ -n "$REMOTE_USER" ]]; then echo "SSH user override: $REMOTE_USER"; fi
echo "Mode: $MODE"
for host in "${SELECTED_HOSTS[@]}"; do
  # Prefer the verified WireGuard route for the host whose public SSH endpoint timed out.
  target="$host"
  host_user="${REMOTE_USER:-joebert}"
  case "$host" in
    178.128.95.212) target="${SECURITY_PATCH_WG_178_128_95_212:-10.27.79.2}"; host_user="${REMOTE_USER:-joebertj}" ;;
  esac
  echo
  echo "=== Security update preflight: $host via $target (user $host_user) ==="
  "${SSH[@]}" "$host_user@$target" 'bash -s' <<<"$REMOTE_SECURITY"
done

if [[ "$MODE" == check ]]; then
  echo; echo "Read-only simulation finished. No VM was changed."; exit 0
fi

if ((${#SELECTED_HOSTS[@]} == 1)); then
  confirmation="APPLY SECURITY UPDATES ON ${SELECTED_HOSTS[0]}"
else
  confirmation="APPLY SECURITY UPDATES ON BOTH VMS"
fi
printf '\nThis applies only security-advisory OS package updates. Type exactly: %s\n> ' "$confirmation"
read -r answer
[[ "$answer" == "$confirmation" ]] || { echo "Cancelled; no package changes made."; exit 1; }
for host in "${SELECTED_HOSTS[@]}"; do
  target="$host"
  host_user="${REMOTE_USER:-joebert}"
  case "$host" in
    178.128.95.212) target="${SECURITY_PATCH_WG_178_128_95_212:-10.27.79.2}"; host_user="${REMOTE_USER:-joebertj}" ;;
  esac
  echo; echo "=== Applying security updates: $host via $target (user $host_user) ==="
  "${SSH[@]}" "$host_user@$target" 'bash -s' <<<"$REMOTE_APPLY"
done
echo; echo "Security update cycle finished for: ${SELECTED_HOSTS[*]}"
