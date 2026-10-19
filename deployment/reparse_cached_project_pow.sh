#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${DOCUMENT_PYTHON:-$repo/.venv-documents/bin/python}"
if [[ ! -x "$python_bin" ]]; then
  echo "Document parser environment not found: $python_bin" >&2
  echo "Set DOCUMENT_PYTHON to an environment with project_documents/requirements.txt installed." >&2
  exit 2
fi
if [[ $# -ne 1 ]]; then
  echo "Usage: $0 2027DPWH-Proposal-22663" >&2
  exit 2
fi
cd "$repo"
exec "$python_bin" reparse_cached_project_pow.py "$1"
