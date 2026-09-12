#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

PROMETHEUS_DIR="${PROMETHEUS_CONFIG_DIR:-${ROOT}/apps/prometheus}"
CONFIG="${PROMETHEUS_CONFIG:-${PROMETHEUS_DIR}/prometheus.yml}"
RULES_DIR="${PROMETHEUS_RULES_DIR:-${PROMETHEUS_DIR}/rules}"
IMAGE="${PROMETHEUS_IMAGE:-prom/prometheus:${PROMETHEUS_IMG:-v3.13.2}}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

command -v docker >/dev/null 2>&1 || fail "docker is required for runtime-equivalent promtool validation"
[[ -f "${CONFIG}" ]] || fail "Prometheus config not found: ${CONFIG}"
[[ -d "${RULES_DIR}" ]] || fail "Prometheus rules directory not found: ${RULES_DIR}"

docker run --rm \
  --volume "${PROMETHEUS_DIR}:/etc/prometheus:ro" \
  --entrypoint promtool \
  "${IMAGE}" \
  check config /etc/prometheus/prometheus.yml
