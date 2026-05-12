#!/usr/bin/env bash
# Idempotent provisioning of PostgreSQL + TimescaleDB on Debian/Ubuntu WSL.
# Slice 1 of TASK-14 (bar_history → TimescaleDB migration).
#
# This script only touches the database. It does NOT modify application code,
# config files outside of /etc/postgresql, or any file under the repo.
#
# Usage:
#   sudo bash scripts/setup_timescale_wsl.sh
#   # or with overrides:
#   DB_PASSWORD=secret sudo -E bash scripts/setup_timescale_wsl.sh
#
# Re-running is safe: every step checks state and skips if already done.

set -euo pipefail

PG_VER="${PG_VER:-17}"
PG_CLUSTER="${PG_CLUSTER:-main}"
DB_USER="${DB_USER:-pairtrading}"
DB_PASSWORD="${DB_PASSWORD:-pairtrading_dev}"
DB_MAIN="${DB_MAIN:-pairtrading}"
DB_TEST="${DB_TEST:-pairtrading_test}"

step() { printf '\n>> %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }

if [ "${EUID}" -ne 0 ]; then
    echo "This script needs sudo (apt + postgres admin). Run with: sudo bash $0" >&2
    exit 1
fi

PG_CONF="/etc/postgresql/${PG_VER}/${PG_CLUSTER}/postgresql.conf"
if [ ! -f "$PG_CONF" ]; then
    echo "Expected ${PG_CONF} to exist (Postgres ${PG_VER} cluster ${PG_CLUSTER}). Install PG ${PG_VER} first." >&2
    exit 1
fi

step "Install postgresql-${PG_VER}-timescaledb (if missing)"
if dpkg -s "postgresql-${PG_VER}-timescaledb" >/dev/null 2>&1; then
    note "already installed: $(dpkg-query -W -f='${Version}' postgresql-${PG_VER}-timescaledb)"
else
    apt-get update -qq
    apt-get install -y "postgresql-${PG_VER}-timescaledb"
fi

step "Ensure shared_preload_libraries='timescaledb' in postgresql.conf"
if grep -qE "^\s*shared_preload_libraries\s*=\s*'[^']*timescaledb[^']*'" "$PG_CONF"; then
    note "already set"
    SPL_CHANGED=0
else
    cp "$PG_CONF" "${PG_CONF}.bak-$(date +%s)"
    if grep -qE "^\s*#?\s*shared_preload_libraries\s*=" "$PG_CONF"; then
        sed -i -E "s|^\s*#?\s*shared_preload_libraries\s*=.*|shared_preload_libraries = 'timescaledb'|" "$PG_CONF"
    else
        echo "shared_preload_libraries = 'timescaledb'" >> "$PG_CONF"
    fi
    note "patched ${PG_CONF}"
    SPL_CHANGED=1
fi

step "Start / restart cluster ${PG_VER}/${PG_CLUSTER}"
CLUSTER_STATE="$(pg_lsclusters -h "$PG_VER" "$PG_CLUSTER" 2>/dev/null | awk '{print $4}')"
if [ "$CLUSTER_STATE" = "online" ]; then
    if [ "$SPL_CHANGED" -eq 1 ]; then
        note "restarting (config changed)"
        pg_ctlcluster "$PG_VER" "$PG_CLUSTER" restart
    else
        note "already online"
    fi
else
    note "starting"
    pg_ctlcluster "$PG_VER" "$PG_CLUSTER" start
fi

PSQL_SU=(sudo -u postgres psql -v ON_ERROR_STOP=1 -X)

step "Create role ${DB_USER} (if missing)"
if "${PSQL_SU[@]}" -tAc "SELECT 1 FROM pg_roles WHERE rolname = '${DB_USER}'" | grep -q 1; then
    note "exists"
else
    "${PSQL_SU[@]}" -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';"
    note "created"
fi

step "Create databases (if missing)"
for db in "$DB_MAIN" "$DB_TEST"; do
    if "${PSQL_SU[@]}" -tAc "SELECT 1 FROM pg_database WHERE datname = '${db}'" | grep -q 1; then
        note "${db}: exists"
    else
        "${PSQL_SU[@]}" -c "CREATE DATABASE ${db} OWNER ${DB_USER};"
        note "${db}: created"
    fi
done

step "Enable extension timescaledb on each database"
for db in "$DB_MAIN" "$DB_TEST"; do
    sudo -u postgres psql -X -v ON_ERROR_STOP=1 -d "$db" -c "CREATE EXTENSION IF NOT EXISTS timescaledb;" >/dev/null
    VER=$(sudo -u postgres psql -X -tAc "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" -d "$db")
    note "${db}: timescaledb ${VER}"
done

step "Summary"
cat <<EOF
   PostgreSQL ${PG_VER} cluster: ${PG_CLUSTER} (port $(pg_lsclusters -h "$PG_VER" "$PG_CLUSTER" | awk '{print $3}'))
   Role:                       ${DB_USER}
   Database (main):            ${DB_MAIN}
   Database (test):            ${DB_TEST}

   Suggested env vars (Slice 8 will codify these in .env.example):

     export PG_URI=postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_MAIN}
     export PG_TEST_URI=postgresql://${DB_USER}:${DB_PASSWORD}@127.0.0.1:5432/${DB_TEST}
     export BAR_HISTORY_BACKEND=sqlite   # still the default; switch when Slice 4 lands

   Rollback: BAR_HISTORY_BACKEND=sqlite (default). This script does not
   touch the application; the databases simply sit unused until the wrapper
   in Slice 2+ picks them up.
EOF
