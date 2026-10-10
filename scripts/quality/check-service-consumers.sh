#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve exactly one root path: the previous 'cmd || cd && pwd' printed
# both Git's root and pwd on success due to shell operator precedence.
if ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi
cd "${ROOT}"

OUTPUTS=(
  apps/homarr/generated/apps.json
  apps/gatus/config/config.yml
  apps/autokuma/static/generated-monitors.json
)

hash_outputs() {
  local file
  for file in "${OUTPUTS[@]}"; do
    if [[ -f "${file}" ]]; then
      printf '%s  %s\n' "$(sha256sum "${file}" | awk '{print $1}')" "${file}"
    else
      printf 'MISSING  %s\n' "${file}"
    fi
  done
}

BEFORE="$(hash_outputs)"
python scripts/generate-service-consumers.py
AFTER="$(hash_outputs)"
DRIFT=false

if [[ "${BEFORE}" != "${AFTER}" ]]; then
  DRIFT=true
  echo "❌ Generated service-consumer files were stale."
  echo "   Review the regenerated files, then rerun the quality gate."
fi

TESTS_FAILED=false
if ! python -m unittest -v \
  tests.test_homarr_sync \
  tests.test_service_consumers_status_contract \
  tests.test_service_topology_generator; then
  TESTS_FAILED=true
fi

if [[ "${DRIFT}" == true || "${TESTS_FAILED}" == true ]]; then
  exit 1
fi

echo "✅ Service-consumer generated files and unit tests are consistent."
