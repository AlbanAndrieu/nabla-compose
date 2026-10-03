#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
DOCKER_ROOT="${NABLA_DOCKER_ROOT:-/mnt/.ix-apps/docker}"
DOCKER_DATASET="${NABLA_DOCKER_DATASET:-cpool/ix-apps/docker}"
CLI_TIMEOUT="${NABLA_DOCKER_AUDIT_CLI_TIMEOUT_SECONDS:-15}"
DEEP_TIMEOUT="${NABLA_DOCKER_AUDIT_DEEP_TIMEOUT_SECONDS:-120}"
WARN_OVERLAY_DIRS="${NABLA_DOCKER_AUDIT_WARN_OVERLAY_DIRS:-5000}"
WARN_IMAGES="${NABLA_DOCKER_AUDIT_WARN_IMAGES:-500}"
WARN_USED_GIB="${NABLA_DOCKER_AUDIT_WARN_USED_GIB:-400}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check | --deep) ;;
  *) fail "usage: sudo bash scripts/truenas/audit-docker-storage-debt.sh [--check|--deep]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in docker find timeout wc zfs numfmt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf 'Docker storage-debt audit mode=%s (read-only)\n' "${MODE}"
printf 'root=%s dataset=%s\n' "${DOCKER_ROOT}" "${DOCKER_DATASET}"

overlay_dirs=0
container_dirs=0
[[ -d "${DOCKER_ROOT}/overlay2" ]] &&
  overlay_dirs="$(find "${DOCKER_ROOT}/overlay2" -mindepth 1 -maxdepth 1 -type d -printf . | wc -c)"
[[ -d "${DOCKER_ROOT}/containers" ]] &&
  container_dirs="$(find "${DOCKER_ROOT}/containers" -mindepth 1 -maxdepth 1 -type d -printf . | wc -c)"

used_bytes="$(zfs get -Hp -o value used "${DOCKER_DATASET}" 2>/dev/null || true)"
if [[ "${used_bytes}" =~ ^[0-9]+$ ]]; then
  used_human="$(numfmt --to=iec-i --suffix=B "${used_bytes}")"
else
  used_human="unknown"
fi

printf 'filesystem overlay2_dirs=%s container_dirs=%s dataset_used=%s\n' \
  "${overlay_dirs}" "${container_dirs}" "${used_human}"

if [[ "${overlay_dirs}" =~ ^[0-9]+$ ]] && ((overlay_dirs >= WARN_OVERLAY_DIRS)); then
  printf 'WARN: overlay2 directory cardinality=%s is at/above advisory threshold=%s; cold-start metadata reload may be slow.\n' \
    "${overlay_dirs}" "${WARN_OVERLAY_DIRS}"
fi
if [[ "${used_bytes}" =~ ^[0-9]+$ ]] && ((used_bytes >= WARN_USED_GIB * 1024 * 1024 * 1024)); then
  printf 'WARN: Docker dataset usage=%s is at/above advisory threshold=%sGiB; review image/layer debt after PRA acceptance.\n' \
    "${used_human}" "${WARN_USED_GIB}"
fi

docker_info_line=""
if docker_info_line="$(timeout "${CLI_TIMEOUT}" docker info \
  --format 'runtime containers={{.Containers}} running={{.ContainersRunning}} stopped={{.ContainersStopped}} images={{.Images}} driver={{.Driver}} root={{.DockerRootDir}}')"; then
  printf '%s\n' "${docker_info_line}"
  image_count="$(sed -n 's/.* images=\\([0-9][0-9]*\\) .*/\\1/p' <<<"${docker_info_line}")"
  if [[ "${image_count}" =~ ^[0-9]+$ ]] && ((image_count >= WARN_IMAGES)); then
    printf 'WARN: image count=%s is at/above advisory threshold=%s; cold-start image/layer metadata reload may be slow.\n' \
      "${image_count}" "${WARN_IMAGES}"
  fi
else
  printf 'WARN: docker info did not answer within %ss; filesystem counts above remain valid.\n' "${CLI_TIMEOUT}"
fi

if dangling_count="$(
  timeout "${CLI_TIMEOUT}" docker image ls --filter dangling=true -q 2>/dev/null |
    sort -u |
    awk 'NF {count++} END {print count+0}'
)"; then
  printf 'candidate dangling_image_ids=%s\n' "${dangling_count}"
else
  printf 'WARN: dangling-image inventory did not answer within %ss.\n' "${CLI_TIMEOUT}"
fi

if exited_count="$(
  timeout "${CLI_TIMEOUT}" docker container ls -a --filter status=exited -q 2>/dev/null |
    awk 'NF {count++} END {print count+0}'
)"; then
  printf 'candidate exited_containers=%s (review ownership before removal)\n' "${exited_count}"
else
  printf 'WARN: exited-container inventory did not answer within %ss.\n' "${CLI_TIMEOUT}"
fi

if [[ "${MODE}" == "--deep" ]]; then
  printf 'Running bounded docker system df -v (timeout=%ss); this may itself be expensive on large overlay2 stores...\n' "${DEEP_TIMEOUT}"
  timeout "${DEEP_TIMEOUT}" docker system df -v ||
    printf 'WARN: docker system df -v exceeded %ss or failed; do not treat that as permission to prune blindly.\n' "${DEEP_TIMEOUT}"
fi

cat <<'EOF'
Cleanup policy:
- Never run cleanup during PREPARING/PREPARED/post-reboot/resume phases.
- Never use docker system prune or docker network prune as a generic remedy.
- Keep TrueNAS App ownership authoritative; removing unused images can force later re-pulls.
- Review dangling images, old unmanaged/exited containers and build cache separately.
- Remove only explicitly reviewed objects with a known owner and rollback/re-pull path.
- Re-run this audit and a normal reboot after cleanup to compare overlay2 cardinality and convergence time.
EOF
