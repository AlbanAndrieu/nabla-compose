#!/usr/bin/env bash
# Recover the managed OpenClaw service from preflight-node-runtime-incompatible.
# Explicit --apply only. No project backup, npm staging, sudo, or model calls.
set -Eeuo pipefail
umask 077

if [[ "${1:-}" != "--apply" || "$#" -ne 1 ]]; then
  echo "Usage: $0 --apply" >&2
  exit 2
fi

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPAIR="${HERE}/repair-openclaw-gateway-node.py"
NODE="${HOME}/.local/share/mise/installs/node/24.22.1/bin/node"
CLI="${HOME}/.local/share/mise/installs/node/24.18.1/lib/node_modules/openclaw/openclaw.mjs"
# Preserve the account's documented state/config/workspace paths. Explicit
# environment overrides are kept unchanged rather than using a new profile.
export OPENCLAW_STATE_DIR="${OPENCLAW_STATE_DIR:-${HOME}/.openclaw}"
export OPENCLAW_CONFIG_PATH="${OPENCLAW_CONFIG_PATH:-${OPENCLAW_STATE_DIR}/openclaw.json}"
export OPENCLAW_WORKSPACE_DIR="${OPENCLAW_WORKSPACE_DIR:-${OPENCLAW_STATE_DIR}/workspace}"
DB="${OPENCLAW_STATE_DIR}/state/openclaw.sqlite"
UNIT=openclaw-gateway.service

# Read-only checks BEFORE stopping the service.
python3 "${REPAIR}" --plan
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
if [[ -f "${DB}" ]] && fuser -s "${DB}" 2>/dev/null; then
  echo "repair=blocked_sqlite_still_owned"
  exit 2
fi

# systemd owner is still the old npm package root; change only Node.
python3 "${REPAIR}" --apply

# Run the updater from that SAME managed package under the new Node. This
# avoids the shell's different global npm prefix being selected.
# --no-restart keeps the Gateway stopped during schema/plugin migration.
echo "update=starting_from_managed_package"
"${NODE}" "${CLI}" update --tag 2026.10.7 --yes --no-restart

# The managed package must now report the target release.
if ! "${NODE}" "${CLI}" --version | grep -Eq '^OpenClaw 2026\.10\.7([[:space:]]|$)'; then
  echo "repair=blocked_updated_package_not_verified"
  exit 2
fi

# Do not start after a failed update or unresolved DB ownership.
if [[ -f "${DB}" ]] && fuser -s "${DB}" 2>/dev/null; then
  echo "repair=blocked_sqlite_owned_after_update"
  exit 2
fi

systemctl --user start "${UNIT}"
if ! systemctl --user is-active --quiet "${UNIT}"; then
  echo "repair=gateway_start_unverified"
  exit 2
fi
# /readyz is loopback-only and does not invoke a language model.
ready=0
for attempt in $(seq 1 12); do
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
echo "repair=upgraded_gateway_healthy"
echo "node_runtime=24.22.1"
echo "openclaw_release=2026.10.7"
echo "project_backup_created=false"
echo "model_requests_sent=0"
