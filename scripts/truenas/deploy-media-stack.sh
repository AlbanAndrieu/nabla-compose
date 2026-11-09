#!/usr/bin/env bash
# Deploy one *arr media-stack app as a TrueNAS Custom App, one app at a time.
# --check is read-only. --apply needs NABLA_RUNTIME_CHANGE_APPROVED=yes, never
# pulls images, never deletes a native App and never touches another app.
# Design: docs/arr-media-library-roadmap.md
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/app-deploy.sh
source "${SCRIPT_DIR}/../lib/app-deploy.sh"
truenas_repo_provenance "$(git rev-parse --show-toplevel)"

MEDIA_APPS=(media-acquisition prowlarr radarr sonarr lidarr bazarr recyclarr jellyfin seerr qbittorrent-exporter)
MEDIA_NETWORK="media"
MEDIA_DATASET="cpool/media"

usage() {
  printf 'usage: deploy-media-stack.sh --check|--apply <app>\n' >&2
  printf 'apps: %s\n' "${MEDIA_APPS[*]}" >&2
  exit 2
}

[[ "$#" -eq 2 ]] || usage
MODE="$(app_deploy_mode "$1" "$0")" || usage
APP_ID="$2"
known=false
for candidate in "${MEDIA_APPS[@]}"; do
  [[ "${candidate}" == "${APP_ID}" ]] && known=true
done
[[ "${known}" == true ]] || usage

CANONICAL_ROOT="${MEDIA_STACK_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
app_deploy_canonical_checkout "${CANONICAL_ROOT}" zfs
compose_path="${CANONICAL_ROOT}/apps/${APP_ID}/compose.yml"

section "Static Compose validation (${APP_ID})"
app_deploy_compose_validate "${compose_path}"
ok "Compose configuration is valid"

section "Existing TrueNAS App"
app_json="$(truenas_app_query_by_id "${APP_ID}")"
app_count="$(jq -r 'length' <<<"${app_json}")"
[[ "${app_count}" =~ ^[01]$ ]] || fail "unexpected or ambiguous App count for ${APP_ID}"
if [[ "${app_count}" == "1" ]]; then
  # The never-finished native PoC Apps share these names. Updating a catalog
  # App with a custom Compose would silently rewrite it: refuse instead.
  jq -e '.[0].custom_app == true' >/dev/null <<<"${app_json}" ||
    fail "${APP_ID} is a native catalog App (PoC): delete it first (roadmap P0, item 3)"
  app_state="$(jq -r '.[0].state // "UNKNOWN"' <<<"${app_json}")"
  [[ "${app_state}" != "DEPLOYING" ]] ||
    fail "${APP_ID} is DEPLOYING; observe it, do not repeat --apply"
  info "existing Custom App ${APP_ID}: ${app_state}"
else
  info "App ${APP_ID} is absent (ready for a deliberate --apply)"
fi

section "Networks"
docker network inspect traefik_network >/dev/null 2>&1 ||
  fail "external network traefik_network is absent"
media_network_present=false
if docker network inspect "${MEDIA_NETWORK}" >/dev/null 2>&1; then
  media_network_present=true
  ok "external network ${MEDIA_NETWORK} present"
else
  warn "external network ${MEDIA_NETWORK} absent; --apply creates it"
fi

section "Images (pinned by digest, never pulled by this script)"
missing_images=0
while IFS= read -r image; do
  [[ -n "${image}" ]] || continue
  if docker image inspect "${image}" >/dev/null 2>&1; then
    ok "cached ${image}"
  else
    warn "not cached: run 'docker pull ${image}' deliberately first"
    missing_images=$((missing_images + 1))
  fi
done < <(docker compose -f "${compose_path}" config --images 2>/dev/null)

# cpool/media converges through bootstrap-repository-storage.sh and
# config/truenas/dataset-profiles.json; never start a downloader without quota.
media_storage_ready() {
  local quota
  zfs list -H -o name "${MEDIA_DATASET}" >/dev/null 2>&1 || return 1
  quota="$(zfs get -Hp -o value quota "${MEDIA_DATASET}")"
  [[ "${quota}" =~ ^[0-9]+$ ]] || return 1
  ((quota > 0)) || return 1
  [[ -d "/mnt/${MEDIA_DATASET}/torrents/incomplete" && -d "/mnt/${MEDIA_DATASET}/library/movies" ]]
}
uses_media=false
grep -q "/mnt/${MEDIA_DATASET}" "${compose_path}" && uses_media=true

if [[ "${APP_ID}" == "media-acquisition" ]]; then
  [[ -c /dev/net/tun ]] || fail "/dev/net/tun is absent on this host"
fi
if [[ "${APP_ID}" == "jellyfin" ]]; then
  render_node="/dev/dri/renderD128"
  [[ -e "${render_node}" ]] || fail "${render_node} is absent: no iGPU for transcoding"
  render_gid="$(stat -c '%g' "${render_node}")"
  grep -q "JELLYFIN_RENDER_GID:-${render_gid}}" "${compose_path}" ||
    fail "render group of ${render_node} is ${render_gid}: update JELLYFIN_RENDER_GID default in apps/jellyfin/compose.yml"
  ok "render group ${render_gid} matches the Compose default"
fi

section "Runtime layout, dataset profile and secrets (value-blind)"
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

if [[ "${MODE}" == "--check" ]]; then
  if [[ "${uses_media}" == true ]] && ! media_storage_ready; then
    warn "${MEDIA_DATASET} is not converged yet (quota/directories): --apply runs the storage bootstrap first"
  fi
  [[ "${app_count}" == "1" ]] && app_deploy_check_report "${APP_ID}"
  printf 'READ_ONLY: no network, dataset, App or image was created, pulled or changed\n'
  exit 0
fi

[[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after a reviewed --check preflight"
((missing_images == 0)) || fail "pull the pinned images listed above before --apply"

if [[ "${media_network_present}" == false ]]; then
  docker network create --driver bridge --label com.nabla.role=media-stack \
    "${MEDIA_NETWORK}" >/dev/null
  ok "created external network ${MEDIA_NETWORK}"
fi

bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"
if [[ "${uses_media}" == true ]]; then
  media_storage_ready || fail "${MEDIA_DATASET} has no quota or directory tree after the storage bootstrap"
fi

truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
if [[ "$(truenas_app_state "${APP_ID}")" == "STOPPED" ]]; then
  truenas_job_compact app.start "${APP_ID}"
fi
truenas_wait_app_running "${APP_ID}" 600 5
truenas_app_summary "${APP_ID}"
printf 'NEXT: run the acceptance checks of docs/arr-media-library-roadmap.md before status: active\n'
