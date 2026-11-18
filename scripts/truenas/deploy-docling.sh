#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/app-deploy.sh
source "${SCRIPT_DIR}/../lib/app-deploy.sh"

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

app_deploy_canonical_checkout "${CANONICAL_ROOT}"

bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

compose_path="${CANONICAL_ROOT}/apps/docling/compose.yml"
app_deploy_compose_validate "${compose_path}"

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

# A TrueNAS app.create may complete while the CPU image and models are
# still initializing. Never send app.update/redeploy during DEPLOYING.
if [[ "${app_count}" == "1" ]]; then
  app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
  [[ "${app_state}" != "DEPLOYING" ]] ||
    fail "Docling is already DEPLOYING; observe readiness, do not repeat --apply"
fi

# Run any prerequisite materialization only after validating the image,
# networks, Compose and App identity. Never mutate during --check.
bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

# app.update or app.create with the shared include payload. No wait for
# RUNNING here: models keep initializing after the job (see DEPLOYING above).
printf 'Reconciling TrueNAS Custom App %s...\n' "${APP_ID}"
truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"

app_json="$(truenas_app_query_by_id "${APP_ID}")"
printf '%s\n' "${app_json}" | jq -e 'length == 1' >/dev/null ||
  fail "TrueNAS app ${APP_ID} is not uniquely present after reconciliation"
truenas_app_summary "${APP_ID}"

printf 'Expected Custom App YAML include:\n'
printf 'include:\n  - %s\n' "${compose_path}"
