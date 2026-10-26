#!/usr/bin/env bash
# Select the already-installed OpenClaw 2026.10.7 as managed Gateway owner.
# Explicit --apply only. No backup, npm, OpenClaw update, sudo or model calls.
set -Eeuo pipefail
umask 077

if [[ "${1:-}" != "--apply" || "$#" -ne 1 ]]; then
  echo "Usage: $0 --apply" >&2
  exit 2
fi

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPAIR="${HERE}/repair-openclaw-gateway-node.py"
NODE="${HOME}/.local/share/mise/installs/node/24.22.1/bin/node"
CLI="${HOME}/.local/share/mise/installs/node/24.22.1/lib/node_modules/openclaw/openclaw.mjs"
# Preserve the account's documented state/config/workspace paths. Explicit
# environment overrides are kept unchanged rather than using a new profile.
export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-${OPENCLAW_STATE_DIR}/openclaw.json}"
export OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_STATE_DIR}/workspace}"
DB="${OPENCLAW_STATE_DIR}/state/openclaw.sqlite"
UNIT=openclaw-gateway.service

# Read-only installation checks BEFORE starting or changing the service.
python3 "${REPAIR}" --select-installed-plan
[[ -x "${NODE}" && -f "${CLI}" ]] || {
  echo "repair=blocked_node_or_install_owner_missing"
  exit 2
}
[[ "$("${NODE}" --version)" == "v24.22.1" ]] || {
  echo "repair=blocked_wrong_node_version"
  exit 2
}
command -v systemctl >/dev/null || {
  echo "repair=blocked_systemd_unavailable"
  exit 2
}
command -v fuser >/dev/null || {
  echo "repair=blocked_sqlite_owner_probe_missing"
  exit 2
}

# Stop only the known user service. Never kill a process by historic PID.
systemctl --user stop "${UNIT}"
if systemctl --user is-active --quiet "${UNIT}"; then
  echo "repair=blocked_gateway_still_active"
  exit 2
fi
for database_file in "${DB}" "${DB}-wal" "${DB}-shm"; do
  if [[ -f "${database_file}" ]] && fuser -s "${database_file}" 2>/dev/null; then
    echo "repair=blocked_sqlite_still_owned"
    exit 2
  fi
done

# Select the already installed 2026.10.7 package for the service.
# The updater rejected the old-to-new npm install as foreign-destination;
# no npm or schema migration is attempted by this script.
python3 "${REPAIR}" --select-installed
echo "package_selection=existing_installation_selected"

# Verify the exact new package's CLI while SQLite is not owned.
if ! "${NODE}" "${CLI}" --version | grep -Eq '^OpenClaw 2026\.10\.7([[:space:]]|$)'; then
  echo "repair=blocked_selected_package_not_verified"
  exit 2
fi
for database_file in "${DB}" "${DB}-wal" "${DB}-shm"; do
  if [[ -f "${database_file}" ]] && fuser -s "${database_file}" 2>/dev/null; then
    echo "repair=blocked_sqlite_owned_after_selection"
    exit 2
  fi
done

systemctl --user start "${UNIT}"
if ! systemctl --user is-active --quiet "${UNIT}"; then
  echo "repair=gateway_start_unverified"
  exit 2
fi
# /readyz is loopback-only and does not invoke a language model.
ready=0
for attempt in $(seq 1 30); do
  if curl --noproxy '*' --fail --silent --max-time 3 \
     http://127.0.0.1:18789/readyz >/dev/null; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "${ready}" != 1 ]]; then
  echo "repair=gateway_readiness_unverified"
  exit 2
fi
echo "repair=existing_gateway_installation_healthy"
echo "node_runtime=24.22.1"
echo "openclaw_release=2026.10.7"
echo "project_backup_created=false"
echo "npm_install_attempted=false"
echo "model_requests_sent=0"
