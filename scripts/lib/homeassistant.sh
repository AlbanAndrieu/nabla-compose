# shellcheck shell=bash
# Shared read-only helpers for the Home Assistant operator diagnostics.
#
# Never print the API token, config-entry data or entry titles: titles of
# cloud integrations often hold an account e-mail. Callers source
# scripts/lib/secrets.sh first.

HA_NATIVE_APP_ID="${NABLA_HA_NATIVE_APP_ID:-home-assistant}"
HA_APP_ID="${NABLA_HA_APP_ID:-homeassistant}"
HA_URL="${NABLA_HA_URL:-http://172.17.0.24:30103}"
HA_CONFIG_DIR="${NABLA_HA_CONFIG_DIR:-/mnt/cpool/ha/config}"
HA_SECRETS_FILE="${NABLA_HA_SECRETS_FILE:-/mnt/cpool/secrets/runtime/homeassistant/diagnostics.env}"
HA_TOKEN=''

# Print the id of the Home Assistant core container. Order: explicit
# NABLA_HA_CONTAINER, then the repository Custom App, then the native TrueNAS
# App; running containers first. The native App project also runs a
# PostgreSQL sidecar, hence the image filter.
ha_find_container() {
  local scope project id image
  if [[ -n "${NABLA_HA_CONTAINER:-}" ]]; then
    docker inspect --type container --format '{{.Id}}' "${NABLA_HA_CONTAINER}" 2>/dev/null
    return
  fi
  for scope in running all; do
    for project in "ix-${HA_APP_ID}" "ix-${HA_NATIVE_APP_ID}"; do
      while read -r id image; do
        [[ -n "${id}" ]] || continue
        case "${image}" in
        *home-assistant/home-assistant* | *homeassistant/home-assistant*)
          printf '%s\n' "${id}"
          return 0
          ;;
        esac
      done < <(
        if [[ "${scope}" == running ]]; then
          docker ps --filter "label=com.docker.compose.project=${project}" --format '{{.ID}} {{.Image}}' 2>/dev/null
        else
          docker ps -a --filter "label=com.docker.compose.project=${project}" --format '{{.ID}} {{.Image}}' 2>/dev/null
        fi
      )
    done
  done
  return 1
}

# Load HA_TOKEN from a root:root 600 env file (key HA_TOKEN). Returns 1 when
# the optional file is absent, 2 when it exists but is unsafe or malformed.
ha_load_token() {
  HA_TOKEN=''
  [[ -e "${HA_SECRETS_FILE}" ]] || return 1
  secrets_assert_file "${HA_SECRETS_FILE}" HA_TOKEN || return 2
  HA_TOKEN="$(secrets_get_value "${HA_SECRETS_FILE}" HA_TOKEN)" || return 2
  [[ -n "${HA_TOKEN}" ]] || return 2
}

# GET a Home Assistant REST path. The bearer token travels through a process
# substitution, never through argv (visible in ps/proc).
ha_api_get() {
  local path="${1:?Home Assistant API path is required}"
  [[ "${path}" =~ ^/api/[A-Za-z0-9_/.-]*$ ]] || {
    printf 'invalid Home Assistant API path: %s\n' "${path}" >&2
    return 2
  }
  [[ -n "${HA_TOKEN}" ]] || return 1
  curl --fail --silent --show-error --connect-timeout 3 --max-time 15 \
    --header @<(secrets_curl_headers Authorization "Bearer ${HA_TOKEN}") \
    "${HA_URL%/}${path}"
}

# One line per config entry from the on-disk registry (root only):
# domain <TAB> disabled_by|enabled <TAB> source <TAB> comma-separated /dev paths.
# Only strings starting with /dev/ are extracted from entry data and options.
ha_config_entries_offline() {
  local file="${HA_CONFIG_DIR}/.storage/core.config_entries"
  [[ -r "${file}" ]] || return 1
  jq -r '
    .data.entries[]?
    | [ .domain,
        (.disabled_by // "enabled"),
        (.source // "unknown"),
        ([ (.data, .options) | .. | strings | select(startswith("/dev/")) ] | unique | join(","))
      ]
    | @tsv
  ' "${file}"
}
