#!/usr/bin/env bash
# Import the declarative Keycloak realm configuration (apps/keycloak/config/realms)
# with keycloak-config-cli. --check (default) is read-only: it validates the
# files, the admin secret contract and Keycloak reachability, and changes
# nothing. --apply needs NABLA_RUNTIME_CHANGE_APPROVED=yes and runs the pinned
# keycloak-config-cli image once on the private intranet network.
# The admin password is passed through a 0600 env-file, never argv or output.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"

MODE="${1:---check}"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
CONFIG_DIR="${ROOT}/apps/keycloak/config/realms"
SECRETS_FILE="${KEYCLOAK_SECRETS_FILE:-/mnt/cpool/keycloak/.env.secrets}"
KEYCLOAK_LAN_URL="${KEYCLOAK_LAN_URL:-http://172.17.0.24:30238}"
KEYCLOAK_NETWORK_URL="${KEYCLOAK_NETWORK_URL:-http://keycloak:8080}"
DOCKER_NETWORK="${KEYCLOAK_CONFIG_NETWORK:-intranet}"
# keycloak-config-cli 6.5.1 built for Keycloak 26.5.5 (Admin REST API is stable
# within 26.x; the server runs 26.7.3). Bump with Renovate, never a floating tag.
CONFIG_CLI_IMAGE="docker.io/adorsys/keycloak-config-cli:6.5.1-26.5.5@sha256:0955d98c8a341898b7aa177477edf8a1e90569ae50bbe7598141c1270b773274"

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash $0 [--check|--apply]" ;;
esac

require_root "run with sudo on TrueNAS so the private network and secrets are readable"
require_commands curl docker python3

shopt -s nullglob
realm_files=("${CONFIG_DIR}"/*.yaml)
shopt -u nullglob
((${#realm_files[@]} > 0)) || fail "no realm file in ${CONFIG_DIR}"
for file in "${realm_files[@]}"; do
  grep -Eq '^realm: [a-z0-9-]+$' "${file}" || fail "${file##*/}: missing top-level realm"
  if grep -Eq '^realm: master$' "${file}"; then
    fail "${file##*/}: the master realm is administration-only and is not managed here"
  fi
done
info "realm files: ${#realm_files[@]} (${realm_files[*]##*/})"

secrets_assert_file "${SECRETS_FILE}" KC_BOOTSTRAP_ADMIN_PASSWORD ||
  fail "Keycloak admin secret contract is not satisfied"
admin_password="$(secrets_get_value "${SECRETS_FILE}" KC_BOOTSTRAP_ADMIN_PASSWORD)" ||
  fail "unable to read KC_BOOTSTRAP_ADMIN_PASSWORD from ${SECRETS_FILE}"
[[ -n "${admin_password}" ]] || fail "KC_BOOTSTRAP_ADMIN_PASSWORD is empty"

status="$(curl -sS -o /dev/null -m 10 -w '%{http_code}' \
  "${KEYCLOAK_LAN_URL}/realms/master/.well-known/openid-configuration" || true)"
[[ "${status}" == "200" ]] || fail "Keycloak is not ready on ${KEYCLOAK_LAN_URL} (HTTP ${status:-none})"
ok "Keycloak reachable on the LAN; admin secret present (value not shown)"

if [[ "${MODE}" == "--check" ]]; then
  info "CHECK ONLY: no realm imported. Review the files, then re-run with --apply."
  exit 0
fi

[[ "${NABLA_RUNTIME_CHANGE_APPROVED:-}" == "yes" ]] ||
  fail "set NABLA_RUNTIME_CHANGE_APPROVED=yes after reviewing the realm files"

env_file="$(mktemp)"
trap 'rm -f "${env_file}"' EXIT
chmod 0600 "${env_file}"
printf 'KEYCLOAK_PASSWORD=%s\n' "${admin_password}" >"${env_file}"
unset admin_password

docker run --rm \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --network "${DOCKER_NETWORK}" \
  --env-file "${env_file}" \
  -e KEYCLOAK_URL="${KEYCLOAK_NETWORK_URL}" \
  -e KEYCLOAK_USER=admin \
  -e KEYCLOAK_AVAILABILITYCHECK_ENABLED=true \
  -e KEYCLOAK_AVAILABILITYCHECK_TIMEOUT=60s \
  -e IMPORT_FILES_LOCATIONS='/config/*.yaml' \
  -e IMPORT_VARSUBSTITUTION_ENABLED=true \
  -v "${CONFIG_DIR}:/config:ro" \
  --tmpfs /tmp \
  "${CONFIG_CLI_IMAGE}"

status="$(curl -sS -o /dev/null -m 10 -w '%{http_code}' \
  "${KEYCLOAK_LAN_URL}/realms/nabla/.well-known/openid-configuration" || true)"
[[ "${status}" == "200" ]] || fail "realm nabla not served after import (HTTP ${status:-none})"
ok "realm nabla imported and served"
