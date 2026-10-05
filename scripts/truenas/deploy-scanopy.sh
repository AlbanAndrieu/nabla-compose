#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"

APP_ID="${SCANOPY_APP_ID:-scanopy}"
CANONICAL_ROOT="${SCANOPY_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
SECRETS_FILE="${SCANOPY_SECRETS_FILE:-/mnt/cpool/secrets/runtime/scanopy/.env.secrets}"
ALLOW_MUTABLE_IMAGE="${SCANOPY_ALLOW_MUTABLE_IMAGE:-0}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so TrueNAS middleware and ZFS can be managed"
for command in docker git grep jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

[[ -f "${SECRETS_FILE}" ]] || fail "missing Scanopy secret file: ${SECRETS_FILE}"
grep -Eq '^POSTGRES_PASSWORD=.+$' "${SECRETS_FILE}" || fail "${SECRETS_FILE} must define POSTGRES_PASSWORD"
grep -Eq '^SCANOPY_DATABASE_URL=.+$' "${SECRETS_FILE}" || fail "${SECRETS_FILE} must define SCANOPY_DATABASE_URL"
chmod 600 "${SECRETS_FILE}"

if ! bash scripts/truenas/bootstrap-scanopy-postgres.sh --check; then
  fail "shared PostgreSQL role/database scanopy is not ready; run: sudo bash scripts/truenas/bootstrap-scanopy-postgres.sh --apply"
fi

compose_path="${CANONICAL_ROOT}/apps/scanopy/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"

docker compose \
  -f "${compose_path}" \
  config \
  --quiet \
  --no-interpolate \
  --no-env-resolution

mapfile -t scanopy_images < <(
  docker compose -f "${compose_path}" config --images |
    sort -u
)
mutable_images=()
for image in "${scanopy_images[@]}"; do
  [[ "${image}" == *@sha256:* ]] || mutable_images+=("${image}")
done

if ((${#mutable_images[@]})); then
  if [[ "${ALLOW_MUTABLE_IMAGE}" == "1" ]]; then
    printf 'WARNING: explicit PoC override accepts mutable Scanopy image(s): %s\n' \
      "${mutable_images[*]}" >&2
  else
    fail "Scanopy image(s) are mutable: ${mutable_images[*]}; pin server and daemon to reviewed @sha256 digests before deployment, or set SCANOPY_ALLOW_MUTABLE_IMAGE=1 only for an explicit PoC"
  fi
fi

if truenas_app_query_by_id "${APP_ID}" |
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

app_json="$(truenas_app_query_by_id "${APP_ID}")"
printf '%s\n' "${app_json}" | jq -e 'length == 1' >/dev/null || fail "TrueNAS app ${APP_ID} is not uniquely present after reconciliation"
printf '%s\n' "${app_json}" | jq -r '.[0] | "✅ TrueNAS app \(.id): state=\(.state // \"UNKNOWN\")"'
printf '✅ shared PostgreSQL dependency verified: 172.17.0.24:5432 role/database=scanopy\n'

printf 'Expected Custom App YAML include:\n'
printf 'include:\n  - %s\n' "${compose_path}"
