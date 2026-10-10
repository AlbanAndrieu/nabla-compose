#!/usr/bin/env bash
# Correct only the generated Gatus config access contract; preserve SQLite.
set -euo pipefail

MODE="${1:---check}"
[[ "${MODE}" == "--check" || "${MODE}" == "--apply" ]] || {
  printf 'Usage: bash %s [--check|--apply]\n' "$0" >&2
  exit 2
}

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_DIR="${ROOT}/apps/gatus/config"
CONFIG="${CONFIG_DIR}/config.yml"
EXPECTED_GID="${GATUS_CONFIG_GID:-568}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
for command in stat getent docker grep cut; do
  command -v "${command}" >/dev/null 2>&1 || fail "missing ${command}"
done
[[ "${EXPECTED_GID}" =~ ^[0-9]+$ ]] || fail "GATUS_CONFIG_GID must be numeric"
group_gid="$(getent group apps | cut -d: -f3)"
[[ -n "${group_gid}" && "${group_gid}" == "${EXPECTED_GID}" ]] ||
  fail "apps group gid mismatch: expected ${EXPECTED_GID}; verify TrueNAS group assignment"
[[ -d "${CONFIG_DIR}" && ! -L "${CONFIG_DIR}" ]] || fail "unsafe config directory"
[[ -f "${CONFIG}" && ! -L "${CONFIG}" ]] || fail "missing or unsafe generated config"
[[ -s "${CONFIG}" ]] || fail "generated Gatus config is empty"
container_groups="$(docker inspect gatus --format '{{json .HostConfig.GroupAdd}}' 2>/dev/null)" ||
  fail "Gatus container missing; verify TrueNAS app definition first"
# Refuse to repair a source tree different from the bind mount actually read by
# Gatus; TrueNAS may retain a previous Custom App Compose after updates.
mount_source="$(docker inspect gatus --format '{{range .Mounts}}{{if eq .Destination "/config"}}{{println .Source}}{{end}}{{end}}' 2>/dev/null)" ||
  fail "cannot inspect Gatus configuration mount"
[[ "${mount_source}" == "${CONFIG_DIR}" ]] ||
  fail "Gatus /config mount is not the repository generated config directory; inspect mounted source before repairing"
# Accept numeric IDs, not a guessed process UID. Never expose .Config.Env.
if ! grep -Eq "(^|[^0-9])\"${EXPECTED_GID}\"([^0-9]|$)" <<<"${container_groups}"; then
  fail "running Gatus container has no supplemental apps GID ${EXPECTED_GID}; review/reconcile TrueNAS Compose, not filesystem permissions"
fi

dir_gid="$(stat -c '%g' -- "${CONFIG_DIR}")"
file_gid="$(stat -c '%g' -- "${CONFIG}")"
dir_mode="$(stat -c '%a' -- "${CONFIG_DIR}")"
file_mode="$(stat -c '%a' -- "${CONFIG}")"
printf 'config_dir gid=%s mode=%s; config_file gid=%s mode=%s; required_group=%s\n' \
  "${dir_gid}" "${dir_mode}" "${file_gid}" "${file_mode}" "${EXPECTED_GID}"

if [[ "${MODE}" == "--check" ]]; then
  [[ "${dir_gid}" == "${EXPECTED_GID}" && "${file_gid}" == "${EXPECTED_GID}" ]] ||
    fail "config directory/file group mismatch; run --apply after reviewing metadata"
  # Explicitly verify directory group search and file group read, regardless of
  # other owner/ACL access. Do not loosen permissions to world-readable.
  [[ $((8#${dir_mode} & 8#050)) -eq 8#050 ]] ||
    fail "group cannot traverse/read config directory"
  [[ $((8#${file_mode} & 8#040)) -eq 8#040 ]] ||
    fail "group cannot read Gatus configuration"
  printf '%s\n' 'OK: Gatus config group read/traversal contract satisfied (read-only)'
  exit 0
fi

[[ "${EUID}" -eq 0 ]] || fail "--apply requires sudo"
# Never mutate SQLite dataset, DB, logs, runtime app or other repository trees.
chgrp -- "${EXPECTED_GID}" "${CONFIG_DIR}" "${CONFIG}"
chmod 0750 -- "${CONFIG_DIR}"
chmod 0640 -- "${CONFIG}"
printf '%s\n' 'OK: repaired only config directory (0750) and file (0640), group apps'
printf '%s\n' 'INFO: Gatus restart policy will retry naturally; do not restart or remove the SQLite database'
