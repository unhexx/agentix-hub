#!/usr/bin/env bash
# Thin wrapper: Linear cycle sync via memory.integrations.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  PY="${PYTHON:-python3}"
fi
WORKDIR="${WORKDIR:-$ROOT}"
exec "$PY" -m memory.integrations sync --workdir "$WORKDIR" "$@"
