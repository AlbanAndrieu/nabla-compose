#!/usr/bin/env bash
set -euo pipefail

STRICT=false
case "${1:-}" in
  --check)
    STRICT=true
    ;;
  "") ;;
  *)
    printf 'usage: %s [--check]\n' "$0" >&2
    exit 2
    ;;
esac

DATA_DIR="${GRAFANA_DATA_DIR:-/mnt/cpool/grafana/data}"
DB_PATH="${GRAFANA_DB_PATH:-${DATA_DIR}/grafana.db}"
PORT="${GRAFANA_PORT:-30037}"

failures=0
fail_or_warn() {
  if [[ "${STRICT}" == true ]]; then
    printf '❌ %s\n' "$*" >&2
    failures=$((failures + 1))
  else
    printf '⚠️  %s\n' "$*" >&2
  fi
}

for command in python3 stat du find; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
done

echo '=== Grafana native -> Compose migration preflight (read-only) ==='
printf 'data_dir=%s\n' "${DATA_DIR}"
printf 'database=%s\n' "${DB_PATH}"
printf 'target_port=%s\n' "${PORT}"

if [[ ! -d "${DATA_DIR}" ]]; then
  fail_or_warn "Grafana data directory is missing: ${DATA_DIR}"
else
  stat -c 'data owner=%U group=%G mode=%a' "${DATA_DIR}"
  du -sh "${DATA_DIR}" 2>/dev/null || true
  echo 'Recent Grafana data files:'
  find "${DATA_DIR}" -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' 2>/dev/null |
    sort -r |
    head -n 15 || true
fi

if [[ ! -f "${DB_PATH}" ]]; then
  fail_or_warn "grafana.db is missing; do not remove the native Grafana App until its actual database location is identified"
else
  stat -c 'db owner=%U group=%G mode=%a size=%s' "${DB_PATH}"

  if ! python3 - "${DB_PATH}" "${STRICT}" <<'PY'
import sqlite3
import sys
from pathlib import Path

path = Path(sys.argv[1])
strict = sys.argv[2].lower() == "true"
uri = f"file:{path}?mode=ro"

try:
    connection = sqlite3.connect(uri, uri=True)
except sqlite3.Error as exc:
    print(f"❌ cannot open Grafana SQLite database read-only: {exc}", file=sys.stderr)
    raise SystemExit(1)

connection.row_factory = sqlite3.Row

def table_exists(name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None

missing = [name for name in ("dashboard", "data_source") if not table_exists(name)]
if missing:
    print(f"❌ expected Grafana table(s) missing: {', '.join(missing)}", file=sys.stderr)
    raise SystemExit(1)

dashboards = connection.execute(
    "SELECT uid, title FROM dashboard WHERE is_folder=0 ORDER BY updated DESC LIMIT 10"
).fetchall()
datasources = connection.execute(
    "SELECT uid, name, type, url FROM data_source ORDER BY name LIMIT 10"
).fetchall()

dashboard_count = connection.execute(
    "SELECT COUNT(*) FROM dashboard WHERE is_folder=0"
).fetchone()[0]
datasource_count = connection.execute("SELECT COUNT(*) FROM data_source").fetchone()[0]

print(f"✅ dashboards={dashboard_count} datasources={datasource_count}")
print("Dashboard sample:")
for row in dashboards:
    print(f"  - uid={row['uid'] or '<none>'} title={row['title']}")
print("Datasource sample (no credentials):")
for row in datasources:
    print(
        f"  - uid={row['uid'] or '<none>'} name={row['name']} "
        f"type={row['type']} url={row['url'] or '<empty>'}"
    )

if strict and (dashboard_count < 1 or datasource_count < 1):
    print(
        "❌ strict migration preflight requires at least one dashboard and one datasource",
        file=sys.stderr,
    )
    raise SystemExit(2)
PY
  then
    fail_or_warn "Grafana database content could not satisfy the migration preflight"
  fi
fi

echo
echo '=== Port 30037 ownership ==='
if command -v ss >/dev/null 2>&1; then
  if ss -ltnp 2>/dev/null | grep -Eq "[:.]${PORT}[[:space:]]"; then
    ss -ltnp 2>/dev/null | grep -E "[:.]${PORT}[[:space:]]" || true
    echo "ℹ️  port ${PORT} is currently in use; it must be free before the Compose Grafana starts"
  else
    echo "✅ port ${PORT} is free"
  fi
else
  echo 'ℹ️  ss unavailable; port ownership not checked'
fi

echo
echo 'Migration guardrails:'
echo '  1. Keep /mnt/cpool/grafana/data intact and take a ZFS snapshot before deleting the native App.'
echo '  2. Preserve grafana.db until dashboards/datasources are verified in the Compose Grafana.'
echo '  3. Start Compose Grafana on 172.17.0.24:30037 using the same data directory.'
echo '  4. Verify /api/health plus representative dashboard and datasource UIDs before enabling the rest of the Grafana observability stack.'

if ((failures > 0)); then
  printf 'FAILED: %d Grafana migration preflight problem(s)\n' "${failures}" >&2
  exit 1
fi

echo 'OK: Grafana migration preflight completed read-only'
