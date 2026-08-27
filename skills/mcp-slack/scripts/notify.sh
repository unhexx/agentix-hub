#!/usr/bin/env bash
# Thin wrapper: Slack notify via memory.integrations.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${PYTHON:-python3}"
fi
WORKDIR="${WORKDIR:-$ROOT}"
STATUS="${1:-DONE}"
if [[ $# -gt 0 ]]; then shift; fi
exec "$PY" -m memory.integrations notify --workdir "$WORKDIR" --status "$STATUS" "$@"
