#!/usr/bin/env bash
# Deploy one *arr media-stack app as a TrueNAS Custom App, one app at a time.
# --check is read-only. --apply never pulls images, never deletes a native App
# and never touches another app. Design: docs/arr-media-library-roadmap.md
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
truenas_repo_provenance "$(git rev-parse --show-toplevel)"

MEDIA_APPS=(media-acquisition prowlarr radarr sonarr lidarr bazarr recyclarr jellyfin seerr)
MEDIA_NETWORK="media"
MEDIA_ROOT="/mnt/cpool/media"
MEDIA_DIRS=(
  torrents/incomplete torrents/movies torrents/tv torrents/music
  library/movies library/tv library/music
)

usage() {
  printf 'usage: deploy-media-stack.sh --check|--apply <app>\n' >&2
  printf 'apps: %s\n' "${MEDIA_APPS[*]}" >&2
  exit 1
}

[[ "$#" -eq 2 ]] || usage
case "$1" in
  --check | --apply) MODE="$1" ;;
  *) usage ;;
esac
APP_ID="$2"
known=false
for candidate in "${MEDIA_APPS[@]}"; do
  [[ "${candidate}" == "${APP_ID}" ]] && known=true
done
[[ "${known}" == true ]] || usage

CANONICAL_ROOT="${MEDIA_STACK_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
require_root "run with sudo so TrueNAS middleware, Docker and ZFS can be inspected"
require_commands docker git jq midclt zfs stat

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

compose_path="${CANONICAL_ROOT}/apps/${APP_ID}/compose.yml"
[[ -f "${compose_path}" ]] || fail "missing ${compose_path}"

section "Static Compose validation (${APP_ID})"
docker compose --project-directory "$(dirname -- "${compose_path}")" \
  -f "${compose_path}" config --quiet --no-interpolate --no-env-resolution
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
done < <(docker compose --project-directory "$(dirname -- "${compose_path}")" \
  -f "${compose_path}" config --images 2>/dev/null)

section "Media storage"
uses_media=false
grep -q "${MEDIA_ROOT}" "${compose_path}" && uses_media=true
storage_ready=true
if [[ "${uses_media}" == true ]]; then
  if ! zfs list -H -o name cpool/media >/dev/null 2>&1; then
    warn "dataset cpool/media is absent (roadmap P1)"
    storage_ready=false
  else
    quota="$(zfs get -H -o value quota cpool/media)"
    if [[ "${quota}" == "none" || "${quota}" == "0" ]]; then
      warn "cpool/media has no quota: a full pool would stop every homelab service"
      storage_ready=false
    else
      ok "cpool/media quota=${quota}"
    fi
    for directory in "${MEDIA_DIRS[@]}"; do
      if [[ ! -d "${MEDIA_ROOT}/${directory}" ]]; then
        warn "missing ${MEDIA_ROOT}/${directory} (Docker would create it as root)"
        storage_ready=false
      fi
    done
  fi
else
  info "${APP_ID} does not mount ${MEDIA_ROOT}"
fi

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

section "Runtime layout and secrets (value-blind)"
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

if [[ "${MODE}" == "--check" ]]; then
  printf 'READ_ONLY: no network, dataset, App or image was created, pulled or changed\n'
  exit 0
fi

((missing_images == 0)) || fail "pull the pinned images listed above before --apply"
[[ "${storage_ready}" == true ]] || fail "prepare cpool/media (roadmap P1) before --apply"

if [[ "${media_network_present}" == false ]]; then
  docker network create --driver bridge --label com.nabla.role=media-stack \
    "${MEDIA_NETWORK}" >/dev/null
  ok "created external network ${MEDIA_NETWORK}"
fi

bash scripts/truenas/bootstrap-repository-runtime.sh --apply "${APP_ID}"
bash scripts/truenas/bootstrap-repository-runtime.sh --check "${APP_ID}"

truenas_reconcile_custom_app "${APP_ID}" "${compose_path}"
truenas_wait_app_running "${APP_ID}"
truenas_app_summary "${APP_ID}"
printf 'NEXT: run the acceptance checks of docs/arr-media-library-roadmap.md before status: active\n'
