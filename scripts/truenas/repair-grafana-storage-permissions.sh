#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    printf 'usage: sudo bash scripts/truenas/repair-grafana-storage-permissions.sh [--check|--apply]\n'
    exit 0
    ;;
  *)
    fail "unknown mode: ${MODE}"
    ;;
esac

require_root "run as root on TrueNAS"
require_commands docker stat chown chmod

check_path() {
  local container="$1" path="$2" image configured_user owner mode uid gid target_owner

  docker inspect "${container}" >/dev/null 2>&1 ||
    fail "container not found: ${container}"

  image="$(docker inspect "${container}" --format '{{.Config.Image}}')"
  configured_user="$(docker image inspect "${image}" --format '{{.Config.User}}')"
  [[ -n "${configured_user}" ]] ||
    fail "${container}: image ${image} runs as root/unspecified; refusing ownership guess"

  uid="${configured_user%%:*}"
  [[ "${uid}" =~ ^[0-9]+$ ]] ||
    fail "${container}: non-numeric image user '${configured_user}' cannot be mapped safely"

  if [[ "${configured_user}" == *:* ]]; then
    gid="${configured_user#*:}"
    [[ "${gid}" =~ ^[0-9]+$ ]] ||
      fail "${container}: non-numeric image group '${configured_user}' cannot be mapped safely"
  else
    gid=""
  fi

  [[ -d "${path}" ]] || fail "storage path missing: ${path}"
  owner="$(stat -c '%u:%g' "${path}")"
  mode="$(stat -c '%a' "${path}")"

  printf '%s image=%s image_user=%s path=%s owner=%s mode=%s\n' \
    "${container}" "${image}" "${configured_user}" "${path}" "${owner}" "${mode}"

  target_owner="${uid}"
  if [[ -n "${gid}" ]]; then
    target_owner="${uid}:${gid}"
  fi

  if [[ "${owner%%:*}" == "${uid}" ]] &&
    { [[ -z "${gid}" ]] || [[ "${owner#*:}" == "${gid}" ]]; }; then
    ok "${container}: storage root owner matches image identity ${target_owner}"
    return 0
  fi

  if [[ "${MODE}" == "--check" ]]; then
    warn "${container}: storage root uid ${owner%%:*} != image uid ${uid}"
    return 1
  fi

  printf 'APPLY %s owner %s -> %s (root only; no recursive chown)\n' "${path}" "${owner}" "${target_owner}"
  chown "${target_owner}" "${path}"
  chmod u+rwx "${path}"
  ok "${container}: storage root repaired"
}

failures=0
check_path loki /mnt/cpool/loki || failures=$((failures + 1))
check_path tempo /mnt/cpool/tempo || failures=$((failures + 1))

if [[ "${MODE}" == "--apply" ]]; then
  failures=0
  check_path loki /mnt/cpool/loki || failures=$((failures + 1))
  check_path tempo /mnt/cpool/tempo || failures=$((failures + 1))
fi

((failures == 0))
