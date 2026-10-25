#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
truenas_repo_provenance "$(git rev-parse --show-toplevel)"

# Do not deploy by accident; check mode never renders secrets or mutates Apps.
case "${1:-}" in
  --check|--apply) [[ "$#" -eq 1 ]] || fail 'usage: deploy-docling.sh --check|--apply' ;;
  *) fail 'usage: deploy-docling.sh --check|--apply (explicit apply required)' ;;
esac
MODE="$1"

APP_ID="docling"
[[ "${DOCLING_APP_ID:-docling}" == "${APP_ID}" ]] ||
  fail "only the docling Custom App may be created or changed by this script"
CANONICAL_ROOT="${DOCLING_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so TrueNAS middleware and ZFS can be managed"
for command in docker git jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

if [[ "${MODE}" == "--apply" ]]; then
  bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
fi
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

compose_path="${CANONICAL_ROOT}/apps/docling/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"

docker compose \
  -f "${compose_path}" \
  config \
  --quiet \
  --no-interpolate \
  --no-env-resolution

# External networks and image must already be present: avoid unexpected
# network creation, large image pulls or repeated TrueNAS App jobs.
image="quay.io/docling-project/docling-serve-cpu:${DOCLING_VERSION:-v1.32.0}"
for network in intranet traefik_network; do
  if ! docker network inspect "${network}" >/dev/null 2>&1; then
    fail "Docling preflight: external network ${network} is absent"
  fi
done
if ! docker image inspect "${image}" >/dev/null 2>&1; then
  fail "Docling preflight: image ${image} is not cached locally; do not run a blind pull"
fi
app_json="$(truenas_app_query_by_id "${APP_ID}")"
app_count="$(jq -r 'length' <<<"${app_json}")"
[[ "${app_count}" =~ ^[01]$ ]] ||
  fail "Docling preflight: unexpected or ambiguous existing App count"

if [[ "${MODE}" == "--check" ]]; then
  printf '✅ Docling static Compose, cached image, and external networks present\n'
  if [[ "${app_count}" == "0" ]]; then
    printf 'app=ABSENT (ready for deliberate --apply)\n'
  else
    jq -r '.[0] | "app=" + (.state // "UNKNOWN")' <<<"${app_json}"
  fi
  printf 'READ_ONLY: no app.create, app.update, app.redeploy, image pull or PDF processing\n'
  exit 0
fi

if [[ "${app_count}" == "1" ]]; then
  printf 'Updating existing TrueNAS Custom App %s...\n' "${APP_ID}"
  truenas_job_compact app.update "${APP_ID}" "$(
    jq -cn --arg include "${compose_path}" '{
      custom_compose_config: {
        include: [$include]
      }
    }'
  )"
else
  printf 'Creating missing TrueNAS Custom App %s...\n' "${APP_ID}"
  wrapper="$(printf 'include:\n  - %s\n' "${compose_path}")"
  truenas_job_compact app.create "$(
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
printf '%s\n' "${app_json}" | jq -e 'length == 1' >/dev/null ||
  fail "TrueNAS app ${APP_ID} is not uniquely present after reconciliation"
truenas_app_summary "${APP_ID}"

printf 'Expected Custom App YAML include:\n'
printf 'include:\n  - %s\n' "${compose_path}"
