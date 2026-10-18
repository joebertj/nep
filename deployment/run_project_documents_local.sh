#!/usr/bin/env bash
# Run from the local Mac with the user's PH VPN connected. No bulk download.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${DOCUMENT_PYTHON:-$repo/.venv-documents/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  python3 -m venv "$repo/.venv-documents"
  "$python_bin" -m pip install -r "$repo/project_documents/requirements.txt"
fi
cd "$repo"
if [[ "${1:-}" == "serve" ]]; then
  shift
  exec "$python_bin" -m project_documents.service "$@"
fi
if [[ $# -lt 1 ]]; then
  echo 'Usage: deployment/run_project_documents_local.sh 2027DPWH-Proposal-03421'
  echo '   or: deployment/run_project_documents_local.sh serve'
  exit 2
fi
exec "$python_bin" on_demand_project_documents.py "$@"
