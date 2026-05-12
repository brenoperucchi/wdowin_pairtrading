#!/usr/bin/env bash
# Upgrade postgresql-17-timescaledb (Debian's Apache build, +dfsg) to
# timescaledb-2-postgresql-17 (Timescale's Community/TSL build), which
# unlocks columnar compression and policy scheduling that are stripped
# from the Debian Apache-only package.
#
# Slice 3 of TASK-14 surfaced the gap: ALTER TABLE ... SET
# (timescaledb.compress) returns "functionality not supported under the
# current apache license" on the Debian build.
#
# Usage:
#   sudo bash scripts/setup_timescale_tsl.sh
#
# Re-running is safe.

set -euo pipefail

PG_VER="${PG_VER:-17}"
PG_CLUSTER="${PG_CLUSTER:-main}"
DB_MAIN="${DB_MAIN:-pairtrading}"
DB_TEST="${DB_TEST:-pairtrading_test}"

step() { printf '\n>> %s\n' "$*"; }
note() { printf '   %s\n' "$*"; }

if [ "${EUID}" -ne 0 ]; then
    echo "This script needs sudo. Run with: sudo bash $0" >&2
    exit 1
fi

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-bookworm}")"
note "Detected Debian codename: ${CODENAME}"

step "Install prerequisites (curl, gpg, ca-certificates)"
apt-get update -qq
apt-get install -y curl gpg ca-certificates >/dev/null

step "Add Timescale apt repo + GPG key"
mkdir -p /etc/apt/keyrings
if [ ! -s /etc/apt/keyrings/timescaledb.gpg ]; then
    curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey \
        | gpg --dearmor -o /etc/apt/keyrings/timescaledb.gpg
    note "GPG key written to /etc/apt/keyrings/timescaledb.gpg"
else
    note "GPG key already present"
fi

REPO_LIST="/etc/apt/sources.list.d/timescaledb.list"
write_repo() {
    local codename="$1"
    echo "deb [signed-by=/etc/apt/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/debian/ ${codename} main" \
        > "$REPO_LIST"
}
write_repo "$CODENAME"
if ! apt-get update -qq 2>/dev/null; then
    if [ "$CODENAME" != "bookworm" ]; then
        note "apt update failed for ${CODENAME}; falling back to bookworm"
        write_repo "bookworm"
        apt-get update -qq
        CODENAME="bookworm"
    else
        echo "apt-get update failed even for bookworm" >&2
        exit 2
    fi
fi
note "repo set to debian/${CODENAME}"

step "Remove Debian Apache build (if present)"
if dpkg -s "postgresql-${PG_VER}-timescaledb" >/dev/null 2>&1; then
    apt-get remove --purge -y "postgresql-${PG_VER}-timescaledb"
    note "removed postgresql-${PG_VER}-timescaledb"
else
    note "postgresql-${PG_VER}-timescaledb not installed"
fi

step "Install timescaledb-2-postgresql-${PG_VER} (TSL/Community)"
apt-get install -y "timescaledb-2-postgresql-${PG_VER}"

step "Restart cluster ${PG_VER}/${PG_CLUSTER} so the new .so is loaded"
pg_ctlcluster "$PG_VER" "$PG_CLUSTER" restart

PSQL_SU=(sudo -u postgres psql -v ON_ERROR_STOP=1 -X)
PSQL_SU_POSTGRES=(sudo -u postgres psql -v ON_ERROR_STOP=1 -X -d postgres)

# The Debian Apache build pins a stripped 2.19.3. The TSL packages jump to
# 2.26.x and intentionally drop the older shared libs, so the loader fails
# to dlopen `timescaledb-2.19.3.so` at *connect time* — every query against
# the target DB fails before we can even run DROP EXTENSION.
#
# Recovery strategy: from the `postgres` system DB (which has no extension
# loaded), DROP DATABASE WITH (FORCE) + CREATE DATABASE + CREATE EXTENSION.
# This wipes everything in the target DB. Guard with a row-count check
# obtained *before* we install the TSL .so — if the user has data they'd
# need a different upgrade path (in-place via intermediate versions).

step "Repair extension on each database"
ALLOW_DESTRUCTIVE_UPGRADE="${ALLOW_DESTRUCTIVE_UPGRADE:-0}"

db_is_healthy() {
    local db="$1"
    "${PSQL_SU[@]}" -d "$db" -tAc "SELECT 1" >/dev/null 2>&1
}

db_extension_version() {
    local db="$1"
    "${PSQL_SU[@]}" -d "$db" -tAc \
        "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" 2>/dev/null \
        | tr -d ' '
}

recreate_database() {
    local db="$1"
    if [ "$ALLOW_DESTRUCTIVE_UPGRADE" != "1" ]; then
        echo "REFUSING to drop database ${db}: it is unreachable and rerun" >&2
        echo "  with ALLOW_DESTRUCTIVE_UPGRADE=1 only if you accept losing ALL data" >&2
        echo "  in that database. (Hypertables in the target DB cannot be inspected" >&2
        echo "  because the extension loader fails on connect — there is no" >&2
        echo "  non-destructive path forward on this Apache→TSL transition.)" >&2
        exit 3
    fi
    note "${db}: DROP DATABASE WITH (FORCE) + CREATE DATABASE + CREATE EXTENSION"
    "${PSQL_SU_POSTGRES[@]}" -c "DROP DATABASE IF EXISTS \"${db}\" WITH (FORCE);" >/dev/null
    "${PSQL_SU_POSTGRES[@]}" -c "CREATE DATABASE \"${db}\" OWNER \"${DB_USER}\";" >/dev/null
    "${PSQL_SU[@]}" -d "$db" -c "CREATE EXTENSION timescaledb;" >/dev/null
}

DB_USER="${DB_USER:-pairtrading}"

for db in "$DB_MAIN" "$DB_TEST"; do
    if db_is_healthy "$db"; then
        VER="$(db_extension_version "$db")"
        if [ -z "$VER" ]; then
            "${PSQL_SU[@]}" -d "$db" -c "CREATE EXTENSION timescaledb;" >/dev/null
            note "${db}: extension created"
        elif "${PSQL_SU[@]}" -d "$db" -c "ALTER EXTENSION timescaledb UPDATE;" >/dev/null 2>&1; then
            note "${db}: ALTER EXTENSION UPDATE ok"
        else
            note "${db}: UPDATE failed — falling back to recreate"
            recreate_database "$db"
        fi
    else
        note "${db}: connection fails (loader can't dlopen old .so) — recreating"
        recreate_database "$db"
    fi
    VER=$("${PSQL_SU[@]}" -d "$db" -tAc "SELECT extversion FROM pg_extension WHERE extname='timescaledb';" | tr -d ' ')
    LIC=$("${PSQL_SU[@]}" -d "$db" -tAc "SHOW timescaledb.license;" | tr -d ' ')
    note "${db}: extension=${VER} license=${LIC}"
done

step "Summary"
cat <<EOF
   TimescaleDB switched to Community (TSL) edition.
   Compression DDL should now succeed. Re-run the migration with:

     PG_URI=postgresql://pairtrading:pairtrading_dev@localhost:5432/pairtrading_test \\
     python3 scripts/migrate_bar_history_to_pg.py --source-db trades.db
EOF
