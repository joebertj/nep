#!/usr/bin/env bash
# Read-only checks of deployed Git revision, served content and report menus.
set -euo pipefail
REMOTE_HOST="${NEP_DEPLOY_HOST:-165.245.186.194}"
REMOTE_USER="${NEP_DEPLOY_USER:-joebert}"
REMOTE_DIR="${NEP_DEPLOY_DIR:-/home/joebert/open-data-visualization}"
SSH_IDENTITY="${NEP_SSH_IDENTITY:-$HOME/.ssh/klti}"

ssh -i "$SSH_IDENTITY" -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$REMOTE_USER@$REMOTE_HOST" "REMOTE_DIR='$REMOTE_DIR' bash -s" <<'REMOTE_VERIFY'
set -euo pipefail
r="$REMOTE_DIR"
echo "Revision: $(git -C "$r" rev-parse --short HEAD)"
systemctl is-active visualization.service
git -C "$r" status --short
app_ip="$(ss -H -ltn 'sport = :8888' | awk 'NR==1 {sub(/:[0-9]+$/, "", $4); print $4}')"
[[ -n "$app_ip" ]]
base="http://$app_ip:8888"
for file in "$r"/static/nep-preview/*.html; do
  name="$(basename "$file")"
  actual="$(curl --silent --show-error --fail "$base/static/nep-preview/$name" | sha256sum | cut -d ' ' -f1)"
  expected="$(sha256sum "$file" | cut -d ' ' -f1)"
  [[ "$actual" == "$expected" ]]
  grep -q 'id="uniform-report-menu-style"' "$file"
  python3 - "$file" <<'MENU_CHECK'
import re,sys
from pathlib import Path
text=Path(sys.argv[1]).read_text()
nav=re.search(r'<nav class="report-nav".*?</nav>',text,re.S)
if not nav or re.findall(r'href="([^"]+)"',nav[0])[:2]!=['summary.html','congress.html']:
    raise SystemExit('Unexpected first menu links: '+sys.argv[1])
MENU_CHECK
  echo "OK $name: served content matches checkout; shared menu present"
done
expected="$(sha256sum "$r/static/nep-preview/summary.html" | cut -d ' ' -f1)"
actual="$(curl --silent --show-error --fail "$base/static/nep-preview/" | sha256sum | cut -d ' ' -f1)"
[[ "$actual" == "$expected" ]]
echo 'OK default directory route serves summary'
if grep -q 'id="selected-district-scrutiny"' "$r/static/nep-preview/congress.html"; then
  echo 'Retired selected-district section is still present.' >&2
  exit 1
fi
if grep -q 'Rank all districts against the Bojie Dy' "$r/static/nep-preview/summary.html"; then
  echo 'Retired person-specific summary wording is still present.' >&2
  exit 1
fi
echo 'OK retired selected-district section and person-specific summary link removed'

for path in / /static/nep-preview/ /static/nep-preview/congress.html /static/nep-preview/appropriations-roster.json /static/nep-preview/mpb.html /static/nep-preview/mpb-data.json /static/nep-preview/cost-per-km.html /static/nep-preview/cost-per-km-data.json; do
  status="$(curl --silent --show-error --location --max-time 10 --resolve 'research.bettergov.ph:443:127.0.0.1' --output /dev/null --write-out '%{http_code}' "http://research.bettergov.ph$path")"
  [[ "$status" == 200 ]]
  echo "OK public proxy $path: $status"
done
REMOTE_VERIFY
