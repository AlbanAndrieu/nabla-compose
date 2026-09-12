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

for command in curl docker grep jq sha256sum sort comm awk sed; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
done
[[ -f "${CONFIG}" ]] || {
  printf 'ERROR: Prometheus config not found: %s\n' "${CONFIG}" >&2
  exit 1
}

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
  warn_or_fail "cannot query ${PROMETHEUS_URL}/api/v1/targets?state=active"
else
  jq -r '
    .data.activeTargets[]?
    | [(.labels.job // "<missing-job>"), (.health // "unknown"), (.scrapeUrl // ""), (.lastError // ""), (.lastScrape // "")]
    | @tsv
  ' "${TARGETS_JSON}" |
    sort

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
    | [(.labels.job // "<missing-job>"), (.health // "unknown"), (.scrapeUrl // ""), (.lastError // "")]
    | @tsv
  ' "${TARGETS_JSON}" >"${TMP_DIR}/unhealthy-targets.tsv"
  if [[ -s "${TMP_DIR}/unhealthy-targets.tsv" ]]; then
    printf 'Unhealthy targets:\n' >&2
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
