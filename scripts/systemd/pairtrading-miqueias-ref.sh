#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"

PYTHON_BIN="${PAIR_PYTHON:-/mnt/c/Users/brenoperucchi/AppData/Local/Microsoft/WindowsApps/py.exe}"
PYTHON_VERSION_FLAG="${PAIR_PYTHON_VERSION_FLAG:--3.12}"

cd "${PROJECT_DIR}"
export PYTHONPATH="${PROJECT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONUNBUFFERED=1

exec "${PYTHON_BIN}" ${PYTHON_VERSION_FLAG} scripts/launch_miqueias_reference.py
