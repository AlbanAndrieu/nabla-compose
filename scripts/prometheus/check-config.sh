#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

PROMETHEUS_DIR="${PROMETHEUS_CONFIG_DIR:-${ROOT}/apps/prometheus}"
CONFIG="${PROMETHEUS_CONFIG:-${PROMETHEUS_DIR}/prometheus.yml}"
RULES_DIR="${PROMETHEUS_RULES_DIR:-${PROMETHEUS_DIR}/rules}"
IMAGE="${PROMETHEUS_IMAGE:-prom/prometheus:${PROMETHEUS_IMG:-v3.13.2}}"

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

command -v docker >/dev/null 2>&1 || fail "docker is required for runtime-equivalent promtool validation"
[[ -f "${CONFIG}" ]] || fail "Prometheus config not found: ${CONFIG}"
[[ -d "${RULES_DIR}" ]] || fail "Prometheus rules directory not found: ${RULES_DIR}"

# promtool stats the /run/secrets files that production mounts: give it empty placeholders.
secrets_dir="$(mktemp -d)"
trap 'rm -rf -- "${secrets_dir}"' EXIT
chmod 0755 "${secrets_dir}"
secret_mounts=()
while IFS= read -r secret; do
  install -m 0644 /dev/null "${secrets_dir}/${secret##*/}"
  secret_mounts+=(--volume "${secrets_dir}/${secret##*/}:${secret}:ro")
done < <(grep -ohE '/run/secrets/[A-Za-z0-9._-]+' "${CONFIG}" | sort -u)

# Validate exactly as the TrueNAS App identity, not as Docker root.
docker run --rm \
  --user 568:568 \
  --volume "${PROMETHEUS_DIR}:/etc/prometheus:ro" \
  "${secret_mounts[@]}" \
  --entrypoint promtool \
  "${IMAGE}" \
  check config /etc/prometheus/prometheus.yml
