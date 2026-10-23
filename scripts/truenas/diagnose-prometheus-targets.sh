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

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

CONTAINER="${PROMETHEUS_CONTAINER:-prometheus}"
CONFIG="${PROMETHEUS_CONFIG:-${ROOT}/apps/prometheus/prometheus.yml}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

failures=0
warn_or_fail() {
  if [[ "${STRICT}" == true ]]; then
    printf '❌ %s\n' "$*" >&2
    failures=$((failures + 1))
  else
    printf '⚠️  %s\n' "$*" >&2
  fi
}

for command in curl docker grep jq sha256sum sort comm awk sed stat; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
done
[[ -f "${CONFIG}" ]] || {
  printf 'ERROR: Prometheus config not found: %s\n' "${CONFIG}" >&2
  exit 1
}

# A RUNNING TrueNAS App can still contain a restarting Prometheus
# container. In that state, docker exec/promtool and target HTTP cannot
# provide useful evidence; summarize crash categories instead of repeating
# network failures or dumping secrets from raw logs.
runtime_status="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}' 2>/dev/null || true)"
if [[ "${runtime_status}" != running ]]; then
  case "${runtime_status}" in
    restarting|exited|dead|created) ;;
    *) runtime_status='unknown' ;;
  esac
  printf '❌ Prometheus runtime=%s (config, permissions or startup error)\n' "${runtime_status}" >&2
  # Allowlisted metadata only: .State JSON can include sensitive Health.Log.Output.
  runtime_meta="$(docker inspect "${CONTAINER}" --format \
    'exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' \
    2>/dev/null || true)"
  if [[ "${runtime_meta}" =~ ^exit=[0-9]+[[:space:]]oom=(true|false)[[:space:]]restarts=[0-9]+$ ]]; then
    printf '  runtime %s\n' "${runtime_meta}" >&2
    if [[ "${runtime_meta}" == *'oom=true'* ]]; then
      printf '  likely cause: container OOMKilled; check resource limits privately\n' >&2
    fi
  fi
  # Metadata only; never read or modify TSDB blocks or the WAL.
  for storage_path in "${CONFIG}" /mnt/cpool/prometheus/data; do
    if [[ -e "${storage_path}" ]]; then
      stat -c '  host metadata: mode=%a uid=%u gid=%g type=%F' -- \
        "${storage_path}" >&2 || true
    else
      printf '  host metadata: expected path absent\n' >&2
    fi
  done
  if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
    docker logs --tail 80 "${CONTAINER}" 2>&1 |
      awk '{
          t=tolower($0); lines++;
          if (t ~ /permission denied|operation not permitted/) permissions++;
          if (t ~ /prometheus[.]yml/ && t ~ /permission denied/) config_unreadable++;
          if (t ~ /yaml|parse error|invalid config|unknown field/) configuration++;
          if (t ~ /tsdb|corrupt|wal|storage/) storage++;
          if (t ~ /out of memory|oom/) memory++;
        } END {
          printf "  recent log categories: sample=%d permissions=%d config=%d storage=%d oom=%d\n",
            lines,permissions,configuration,storage,memory;
          if (config_unreadable > 0)
            print "  root_cause=prometheus_config_permission_denied (check 568:568, parent traversal and ZFS ACL)"
        }' >&2 || true
  fi
  printf '  Review privately: docker inspect %s --format "status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}"\n' "${CONTAINER}" >&2
  printf '  Preserve /mnt/cpool/prometheus/data; do not redeploy until crash cause is known.\n' >&2
  exit 1
fi

echo '=== Prometheus config drift ==='
host_hash="$(sha256sum "${CONFIG}" | awk '{print $1}')"
if container_config="$(docker exec "${CONTAINER}" sh -c 'cat /etc/prometheus/prometheus.yml' 2>/dev/null)"; then
  container_hash="$(printf '%s\n' "${container_config}" | sha256sum | awk '{print $1}')"
  printf 'host      sha256=%s\n' "${host_hash}"
  printf 'container sha256=%s\n' "${container_hash}"
  if [[ "${host_hash}" == "${container_hash}" ]]; then
    echo '✅ host and mounted Prometheus config match'
  else
    warn_or_fail 'host Prometheus config differs from the file visible inside the container; a single-file bind mount may still reference the pre-git-pull inode. Recreate/redeploy the Prometheus container before relying on HUP.'
  fi
else
  warn_or_fail "cannot read /etc/prometheus/prometheus.yml from container ${CONTAINER}"
fi

echo
echo '=== promtool on running container ==='
if docker exec "${CONTAINER}" promtool check config /etc/prometheus/prometheus.yml; then
  echo '✅ running-container Prometheus config is syntactically valid'
else
  warn_or_fail 'promtool rejected the config visible inside the running container'
fi

echo
echo '=== Active scrape targets ==='
TARGETS_JSON="${TMP_DIR}/targets.json"
if ! curl --fail --silent --show-error --max-time 10 \
  "${PROMETHEUS_URL}/api/v1/targets?state=active" >"${TARGETS_JSON}"; then
  warn_or_fail "Prometheus active-target API unavailable"
else
  # Compact and redacted: scrapeUrl and lastError may include tokens,
  # private IPs, credentials or server messages. Never print these fields.
  jq -r '
    [.data.activeTargets[]? | {job: (.labels.job // "<missing-job>"),
                               health: (.health // "unknown")}] |
    group_by(.job)[] |
    "\(.[0].job) targets=\(length) up=\(map(select(.health == "up")) | length) not_up=\(map(select(.health != "up")) | length)"
  ' "${TARGETS_JSON}" | sort

  grep -E '^[[:space:]]*-[[:space:]]+job_name:[[:space:]]*' "${CONFIG}" |
    sed -E "s/.*job_name:[[:space:]]*['\"]?([^'\"[:space:]]+)['\"]?.*/\\1/" |
    sort -u >"${TMP_DIR}/expected-jobs.txt"
  jq -r '.data.activeTargets[]?.labels.job // empty' "${TARGETS_JSON}" |
    sort -u >"${TMP_DIR}/live-jobs.txt"

  comm -23 "${TMP_DIR}/expected-jobs.txt" "${TMP_DIR}/live-jobs.txt" >"${TMP_DIR}/missing-jobs.txt"
  if [[ -s "${TMP_DIR}/missing-jobs.txt" ]]; then
    printf 'Expected scrape jobs with no active target:\n' >&2
    sed 's/^/  - /' "${TMP_DIR}/missing-jobs.txt" >&2
    warn_or_fail 'one or more declared Prometheus jobs are absent from the live target inventory'
  else
    echo '✅ every declared Prometheus job has at least one active target'
  fi

  jq -r '
    .data.activeTargets[]?
    | select((.health // "unknown") != "up")
    | [(.labels.job // "<missing-job>"), (.health // "unknown")]
    | @tsv
  ' "${TARGETS_JSON}" >"${TMP_DIR}/unhealthy-targets.tsv"
  if [[ -s "${TMP_DIR}/unhealthy-targets.tsv" ]]; then
    printf 'Unhealthy targets (job and health only):\n' >&2
    sed 's/^/  /' "${TMP_DIR}/unhealthy-targets.tsv" >&2
    warn_or_fail 'one or more Prometheus targets are not UP'
  else
    echo '✅ all active Prometheus targets are UP'
  fi
fi

echo
if ((failures > 0)); then
  printf 'FAILED: %d Prometheus validation problem(s)\n' "${failures}" >&2
  exit 1
fi

echo 'OK: Prometheus config/target diagnostic completed read-only'
