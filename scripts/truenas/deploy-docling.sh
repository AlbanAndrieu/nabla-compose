#!/usr/bin/env bash
set -euo pipefail

APP_ID="${DOCLING_APP_ID:-docling}"
CANONICAL_ROOT="${DOCLING_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so TrueNAS middleware and ZFS can be managed"
for command in docker git jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

bash scripts/truenas/bootstrap-repository-runtime.sh --apply
bash scripts/truenas/bootstrap-repository-runtime.sh --check

compose_path="${CANONICAL_ROOT}/apps/docling/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"

docker compose \
  -f "${compose_path}" \
  config \
  --quiet \
  --no-interpolate \
  --no-env-resolution

if midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
  jq -e 'length > 0' >/dev/null; then
  printf 'Updating existing TrueNAS Custom App %s...\n' "${APP_ID}"
  midclt call -j app.update "${APP_ID}" "$(
    jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {
        include: [$include]
      }
    }'
  )"
else
  printf 'Creating missing TrueNAS Custom App %s...\n' "${APP_ID}"
  wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
  midclt call -j app.create "$(
    jq -cn \
      --arg app_name "${APP_ID}" \
      --arg compose "${wrapper}" \
      '{
        app_name: $app_name,
        custom_app: true,
        custom_compose_config_string: $compose
      }'
  )"
fi

app_json="$(midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]")"
printf '%s\n' "${app_json}" | jq -e 'length == 1' >/dev/null ||
  fail "TrueNAS app ${APP_ID} is not uniquely present after reconciliation"
printf '%s\n' "${app_json}" |
  jq -r '.[0] | "✅ TrueNAS app \(.id): state=\(.state // \"UNKNOWN\")"'

printf 'Expected Custom App YAML include:\n'
printf 'include:\n  - %s\n' "${compose_path}"
