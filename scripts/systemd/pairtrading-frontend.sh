#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

cd "${PROJECT_DIR}/regime-dashboard"

if [[ ! -d node_modules ]]; then
  echo "[frontend] node_modules ausente, rodando npm install..."
  npm install
fi

exec npm run dev -- --host "${PAIR_FRONTEND_HOST:-0.0.0.0}" --port "${PAIR_FRONTEND_PORT:-5174}"
