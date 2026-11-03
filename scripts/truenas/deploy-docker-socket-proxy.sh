#!/usr/bin/env bash
# Deploy the repository-managed docker-socket-proxy Custom App on TrueNAS.
#
#   sudo bash scripts/truenas/deploy-docker-socket-proxy.sh --check
#   sudo bash scripts/truenas/deploy-docker-socket-proxy.sh --apply
#   sudo NABLA_DOCKER_PROXY_REPLACE_APPROVED=yes \
#     bash scripts/truenas/deploy-docker-socket-proxy.sh --apply --replace-catalog-app
#
# --check (default) changes nothing. --apply creates the internal docker-proxy
# network when missing and creates/updates the Custom App. A legacy TrueNAS
# catalog app with the same id is deleted only with --replace-catalog-app and
# NABLA_DOCKER_PROXY_REPLACE_APPROVED=yes (stateless; consumers lose the Docker
# API for the duration of the swap).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

truenas_repo_provenance "$(git rev-parse --show-toplevel)"

MODE="${1:---check}"
REPLACE="${2:-}"
APP_ID="${NABLA_DOCKER_PROXY_APP_ID:-docker-socket-proxy}"
NETWORK="${NABLA_DOCKER_PROXY_DEDICATED_NETWORK:-docker-proxy}"
CANONICAL_ROOT="${NABLA_DOCKER_PROXY_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
CONSUMERS=(pihole-dns-sync autoxpose homarr gatus)

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/deploy-docker-socket-proxy.sh [--check|--apply] [--replace-catalog-app]" ;;
esac
case "${REPLACE}" in
  "" | --replace-catalog-app) ;;
  *) fail "unsupported option: ${REPLACE}" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so TrueNAS middleware and Docker can be managed"
for command in docker git jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

compose_path="${CANONICAL_ROOT}/apps/docker-socket-proxy/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"
docker compose -f "${compose_path}" config --quiet --no-interpolate --no-env-resolution

section "Current state"
app_json="$(truenas_app_query_by_id "${APP_ID}")"
app_kind="$(jq -r 'if length == 0 then "missing" elif .[0].custom_app then "custom" else "catalog" end' <<<"${app_json}")"
printf 'app %s: %s (state=%s)\n' "${APP_ID}" "${app_kind}" "$(jq -r '.[0].state // "MISSING"' <<<"${app_json}")"
if docker network inspect "${NETWORK}" >/dev/null 2>&1; then
  printf 'network %s: present internal=%s\n' "${NETWORK}" \
    "$(docker network inspect --format '{{.Internal}}' "${NETWORK}")"
  for consumer in "${CONSUMERS[@]}"; do
    attached="$(docker inspect --format "{{if index .NetworkSettings.Networks \"${NETWORK}\"}}yes{{else}}no{{end}}" "${consumer}" 2>/dev/null || printf 'absent')"
    printf '  consumer %-16s on %s: %s\n' "${consumer}" "${NETWORK}" "${attached}"
  done
else
  printf 'network %s: absent (created by --apply)\n' "${NETWORK}"
fi

if [[ "${MODE}" == "--check" ]]; then
  if [[ "${app_kind}" == "catalog" ]]; then
    warn "legacy catalog app ${APP_ID} present: replace it with NABLA_DOCKER_PROXY_REPLACE_APPROVED=yes ... --apply --replace-catalog-app"
  fi
  ok "check complete; nothing changed"
  exit 0
fi

section "Apply"
if ! docker network inspect "${NETWORK}" >/dev/null 2>&1; then
  docker network create --internal --label com.nabla.role=docker-api-boundary "${NETWORK}" >/dev/null
  ok "created internal network ${NETWORK}"
fi
[[ "$(docker network inspect --format '{{.Internal}}' "${NETWORK}")" == "true" ]] ||
  fail "network ${NETWORK} exists but is not internal; fix it by hand before deploying"

if [[ "${app_kind}" == "catalog" ]]; then
  [[ "${REPLACE}" == "--replace-catalog-app" && "${NABLA_DOCKER_PROXY_REPLACE_APPROVED:-}" == "yes" ]] ||
    fail "legacy catalog app ${APP_ID} present: --replace-catalog-app and NABLA_DOCKER_PROXY_REPLACE_APPROVED=yes are required"
  printf 'Deleting legacy catalog app %s...\n' "${APP_ID}"
  truenas_job_compact app.delete "${APP_ID}" '{"remove_images": false, "remove_ix_volumes": true}'
fi

truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
truenas_app_summary "${APP_ID}"
printf 'Next: redeploy each consumer (%s) so it joins %s, then run\n' "${CONSUMERS[*]}" "${NETWORK}"
printf '  sudo bash scripts/truenas/verify-pihole-dns-sync.sh\n'
