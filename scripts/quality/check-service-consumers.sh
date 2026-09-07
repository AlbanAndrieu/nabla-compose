#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
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
      printf '%s  %s\n' "$(git hash-object "${file}")" "${file}"
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
if ! python -m unittest discover -s tests -p 'test_*.py'; then
  TESTS_FAILED=true
fi

if [[ "${DRIFT}" == true || "${TESTS_FAILED}" == true ]]; then
  exit 1
fi

echo "✅ Service-consumer generated files and unit tests are consistent."
