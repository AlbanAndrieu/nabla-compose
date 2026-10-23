#!/usr/bin/env bash
# Repair only Prometheus config read access for TrueNAS apps UID/GID 568.
# No Prometheus data/WAL changes, Docker restarts or App reconciliations.
set -euo pipefail

MODE="${1:---check}"
if [[ "${MODE}" != --check && "${MODE}" != --apply ]]; then
  printf 'Usage: bash %s [--check|--apply]\n' "$0" >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_DIR="${ROOT}/apps/prometheus"
CONFIG="${CONFIG_DIR}/prometheus.yml"
EXPECTED_GID=568
EXPECTED_USER='568:568'

fail() { printf '❌ Prometheus config: %s\n' "$*" >&2; exit 1; }
for binary in docker getent cut stat chmod chgrp; do
  command -v "${binary}" >/dev/null 2>&1 || fail "missing ${binary}"
done
[[ -d "${CONFIG_DIR}" && ! -L "${CONFIG_DIR}" ]] ||
  fail 'unsafe Prometheus configuration directory'
[[ -f "${CONFIG}" && ! -L "${CONFIG}" && -s "${CONFIG}" ]] ||
  fail 'missing, empty or unsafe prometheus.yml'

apps_gid="$(getent group apps | cut -d: -f3)" || fail 'TrueNAS group apps missing'
[[ "${apps_gid}" == "${EXPECTED_GID}" ]] ||
  fail "TrueNAS apps group mismatch (expected ${EXPECTED_GID})"

# Fail closed if the running container reads a different bind mount or uses
# another runtime UID. Never inspect .Config.Env or reveal Prometheus YAML.
runtime_user="$(docker inspect prometheus --format '{{.Config.User}}' 2>/dev/null)" ||
  fail 'prometheus Docker container not found'
[[ "${runtime_user}" == "${EXPECTED_USER}" ]] ||
  fail "Prometheus runtime user differs from Compose 568:568; review deployed App"
mount_source="$(docker inspect prometheus --format '{{range .Mounts}}{{if eq .Destination "/etc/prometheus"}}{{println .Source}}{{end}}{{end}}' 2>/dev/null)" ||
  fail 'cannot inspect Prometheus configuration mount'
[[ "${mount_source}" == "${CONFIG_DIR}" ]] ||
  fail 'running /etc/prometheus mount differs from repository; do not chmod an unrelated file'

# Container reads the directory bind root as /etc/prometheus. Check its
# effective directory search bit; leave unrelated repository directories alone.
dir_uid="$(stat -c '%u' -- "${CONFIG_DIR}")"
dir_gid="$(stat -c '%g' -- "${CONFIG_DIR}")"
dir_mode="$(stat -c '%a' -- "${CONFIG_DIR}")"
if [[ "${dir_uid}" == 568 ]]; then
  search_bit=8#0100
elif [[ "${dir_gid}" == 568 ]]; then
  search_bit=8#0010
else
  search_bit=8#0001
fi
(( (8#${dir_mode} & search_bit) == search_bit )) ||
  fail 'config directory is not traversable for UID/GID 568; review POSIX mode/ZFS ACL'

file_uid="$(stat -c '%u' -- "${CONFIG}")"
file_gid="$(stat -c '%g' -- "${CONFIG}")"
file_mode="$(stat -c '%a' -- "${CONFIG}")"
printf 'config file uid=%s gid=%s mode=%s; runtime=%s; expected_gID=%s\n' \
  "${file_uid}" "${file_gid}" "${file_mode}" "${runtime_user}" "${EXPECTED_GID}"

# File mode and group ownership alone cannot prove permission on ZFS ACLs.
# Check effective UID/GID 568:568 from a host process. No contents are read.
effective_read_probe() {
  if (( EUID != 0 )); then
    printf '⚠️ Effective UID access not attested (rerun --check with sudo)\n' >&2
    return 0
  fi
  if ! command -v setpriv >/dev/null 2>&1; then
    printf '⚠️ setpriv unavailable; effective UID 568 access not attested\n' >&2
    return 0
  fi
  if setpriv --reuid 568 --regid 568 --clear-groups /usr/bin/test -r "$CONFIG"; then
    printf '✅ Effective UID:GID 568:568 can read configuration on the host\n'
  else
    fail 'effective UID:GID 568:568 cannot read prometheus.yml; check ZFS ACLs/ancestor traversal, no recursive chmod'
  fi
}

if [[ "${MODE}" == --check ]]; then
  [[ "${file_gid}" == "${EXPECTED_GID}" ]] ||
    fail 'config group mismatch; use scoped --apply only after reviewing mount'
  (( (8#${file_mode} & 8#0040) == 8#0040 )) ||
    fail 'group cannot read prometheus.yml; use scoped --apply'
  (( (8#${file_mode} & 8#0004) == 0 )) ||
    fail 'config is world-readable; use scoped --apply to restore 0640'
  effective_read_probe
  printf '✅ Prometheus config group-read contract satisfied (ACL and runtime still to verify)\n'
  exit 0
fi

(( EUID == 0 )) || fail '--apply requires sudo'
# Preserve the file owner and inode. Only this one file is modified.
chgrp -- "${EXPECTED_GID}" "${CONFIG}"
chmod 0640 -- "${CONFIG}"
[[ "$(stat -c '%g:%a' -- "${CONFIG}")" == '568:640' ]] ||
  fail 'post-repair group/mode verification failed'
effective_read_probe
printf '✅ Prometheus config repaired: group=568 mode=0640, file owner preserved\n'
printf 'ℹ️ No restart performed; Docker restart policy may recover Prometheus automatically.\n'
printf 'ℹ️ Check ZFS ACL if permission errors persist; preserve /mnt/cpool/prometheus/data.\n'
