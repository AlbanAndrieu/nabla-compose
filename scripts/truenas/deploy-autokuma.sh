#!/usr/bin/env bash
set -euo pipefail

APP_ID="${AUTOKUMA_APP_ID:-autokuma}"
CONTAINER="${AUTOKUMA_CONTAINER:-autokuma}"
CANONICAL_ROOT="${AUTOKUMA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
SECRET_FILE="${AUTOKUMA_SECRET_FILE:-/mnt/cpool/secrets/runtime/autokuma/.env.secrets}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in git docker jq sudo midclt grep stat; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply
sudo bash scripts/truenas/bootstrap-repository-runtime.sh --check

[[ -f "${SECRET_FILE}" ]] ||
  fail "missing AutoKuma runtime secret file: ${SECRET_FILE}"
[[ -s "${SECRET_FILE}" ]] ||
  fail "AutoKuma runtime secret file is empty: ${SECRET_FILE}; run bootstrap-autokuma-token.sh"

mode="$(stat -c '%a' "${SECRET_FILE}")"
[[ "${mode}" == "600" ]] ||
  fail "${SECRET_FILE} must be mode 0600 (current: ${mode})"

grep -q '^AUTOKUMA__KUMA__URL=.' "${SECRET_FILE}" ||
  fail "AUTOKUMA__KUMA__URL is missing from ${SECRET_FILE}"

has_token=false
has_user=false
has_password=false

if grep -q '^AUTOKUMA__KUMA__AUTH_TOKEN=.' "${SECRET_FILE}"; then
  has_token=true
fi
if grep -q '^AUTOKUMA__KUMA__USERNAME=.' "${SECRET_FILE}"; then
  has_user=true
fi
if grep -q '^AUTOKUMA__KUMA__PASSWORD=.' "${SECRET_FILE}"; then
  has_password=true
fi

if [[ "${has_token}" != "true" && ! ( "${has_user}" == "true" && "${has_password}" == "true" ) ]]; then
  fail "configure either AUTOKUMA__KUMA__AUTH_TOKEN or username+password"
fi

docker compose \
  -f apps/autokuma/compose.yml \
  config \
  --quiet \
  --no-interpolate \
  --no-env-resolution

monitor_count="$(
  jq 'length' apps/autokuma/static/generated-monitors.json
)"
[[ "${monitor_count}" -gt 0 ]] ||
  fail "generated AutoKuma monitor inventory is empty"

compose_path="${CANONICAL_ROOT}/apps/autokuma/compose.yml"

if midclt call app.query "[[\"id\",\"=\",\"${APP_ID}\"]]" |
  jq -e 'length > 0' >/dev/null; then
  printf 'Updating existing TrueNAS Custom App %s...\n' "${APP_ID}"
  sudo midclt call -j app.update "${APP_ID}" "$(
    jq -cn \
      --arg include "${compose_path}" \
      '{
        custom_compose_config: {
          include: [$include]
        }
      }'
  )"
  sudo midclt call -j app.redeploy "${APP_ID}"
else
  printf 'Creating missing TrueNAS Custom App %s...\n' "${APP_ID}"
  wrapper="$(
    printf 'include:\n  - %s\n' "${compose_path}"
  )"

  sudo midclt call -j app.create "$(
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

for _ in $(seq 1 30); do
  if docker ps --format '{{.Names}}' | grep -Fxq "${CONTAINER}"; then
    printf 'OK: AutoKuma container is running; generated monitor count=%s\n' \
      "${monitor_count}"
    midclt call app.query \
      "[[\"id\",\"=\",\"${APP_ID}\"]]" |
      jq '.[0] | {id,state,active_workloads}'
    exit 0
  fi
  sleep 2
done

docker ps -a --filter "name=^${CONTAINER}$" \
  --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' || true
docker logs --tail 100 "${CONTAINER}" 2>&1 || true
fail "AutoKuma did not reach running state"
