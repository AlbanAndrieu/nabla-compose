#!/usr/bin/env bash
# Read-only health and ownership diagnosis of Home Assistant on TrueNAS:
# which App owns the runtime, container hardening, HTTP/API, integration
# states, custom (HACS) integrations, configuration hygiene and TCP/TLS
# reachability from inside the container.
#
#   sudo bash scripts/truenas/diagnose-homeassistant.sh [--check]
#
# Optional API token: root:root 600 env file ${NABLA_HA_SECRETS_FILE}
# (default /mnt/cpool/secrets/runtime/homeassistant/diagnostics.env) with
# HA_TOKEN=<long-lived token of a dedicated admin user; revoke after use>.
# Targets reached from the container, space separated name=host:port:
#   NABLA_HA_PROBE_TARGETS  (default recorder-postgres=172.17.0.24:5432)
#   NABLA_HA_CLOUD_TARGETS  (default none; TLS-verified, e.g. somfy-protect=api.myfox.io:443)
# Changes nothing. Never prints the token, entry titles or data, secrets.yaml
# values, environment variables or logs.
set -euo pipefail

if [[ $# -gt 1 || "${1:---check}" != --check ]]; then
  echo 'Usage: sudo bash scripts/truenas/diagnose-homeassistant.sh [--check]' >&2
  exit 2
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
# shellcheck source=../lib/probe.sh
source "${SCRIPT_DIR}/../lib/probe.sh"
# shellcheck source=../lib/secrets.sh
source "${SCRIPT_DIR}/../lib/secrets.sh"
# shellcheck source=../lib/homeassistant.sh
source "${SCRIPT_DIR}/../lib/homeassistant.sh"
# shellcheck source=../lib/truenas.sh
source "${SCRIPT_DIR}/../lib/truenas.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2

for cmd in docker jq curl stat grep; do
  command -v "${cmd}" >/dev/null 2>&1 || {
    printf 'ERROR missing=%s\n' "${cmd}" >&2
    exit 2
  }
done

PROBE_TARGETS="${NABLA_HA_PROBE_TARGETS-recorder-postgres=172.17.0.24:5432}"
CLOUD_TARGETS="${NABLA_HA_CLOUD_TARGETS:-}"

diag_section '1/5' 'Runtime ownership and container hardening (metadata only)'
if command -v midclt >/dev/null 2>&1; then
  running_apps=()
  for app in "${HA_NATIVE_APP_ID}" "${HA_APP_ID}"; do
    [[ "${app}" =~ ^[a-z0-9-]+$ ]] || {
      diag_fail "invalid TrueNAS app id: ${app}"
      continue
    }
    state="$(truenas_app_state "${app}" 2>/dev/null || echo UNKNOWN)"
    printf 'truenas_app=%s state=%s\n' "${app}" "${state}"
    [[ "${state}" == RUNNING ]] && running_apps+=("${app}")
  done
  case "${#running_apps[@]}" in
  0) diag_fail 'No Home Assistant App is RUNNING' ;;
  2) diag_fail 'Native and Custom Apps both RUNNING: LAN port 30103 conflict and split state' ;;
  *)
    if [[ "${running_apps[0]}" == "${HA_NATIVE_APP_ID}" ]]; then
      diag_info 'The native App still owns the runtime: see migrate-homeassistant-to-compose.sh --check'
    else
      diag_ok "Runtime owned by the repository Custom App ${HA_APP_ID}"
    fi
    ;;
  esac
else
  diag_unknown 'midclt unavailable: TrueNAS App ownership not checked'
fi

cid="$(ha_find_container || true)"
running=0
if [[ -z "${cid}" ]]; then
  diag_fail 'Home Assistant container not found; set NABLA_HA_CONTAINER'
else
  docker inspect --type container --format 'container={{.Name}} status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}not-defined{{end}} restarts={{.RestartCount}} oom={{.State.OOMKilled}} image={{.Config.Image}}' "${cid}"
  inspect="$(docker inspect --type container "${cid}")"
  [[ "$(jq -r '.[0].State.Status' <<<"${inspect}")" == running ]] && running=1
  ((running)) || diag_fail 'Home Assistant container is not running'
  [[ "$(jq -r '.[0].State.Health.Status // "none"' <<<"${inspect}")" != unhealthy ]] || diag_fail 'Container health=unhealthy'
  printf 'network_mode=%s privileged=%s no_new_privileges=%s devices=%s\n' \
    "$(jq -r '.[0].HostConfig.NetworkMode' <<<"${inspect}")" \
    "$(jq -r '.[0].HostConfig.Privileged' <<<"${inspect}")" \
    "$(jq -r '[.[0].HostConfig.SecurityOpt[]? | select(startswith("no-new-privileges"))] | length > 0' <<<"${inspect}")" \
    "$(jq -r '[.[0].HostConfig.Devices[]?] | length' <<<"${inspect}")"
  [[ "$(jq -r '.[0].HostConfig.Privileged' <<<"${inspect}")" == false ]] || diag_fail 'Privileged container: use explicit devices: entries instead'
  [[ "$(jq -r '.[0].HostConfig.NetworkMode' <<<"${inspect}")" != host ]] || diag_warn 'Host network: Home Assistant listens on every TrueNAS interface'
  [[ "$(jq -r '.[0].Config.Image' <<<"${inspect}")" == *@sha256:* ]] || diag_warn 'Image not pinned by digest (tag only)'
  # Destinations only: host paths are layout details, contents are never read.
  jq -r '.[0].Mounts[]? | "mount=\(.Destination) rw=\(.RW)"' <<<"${inspect}"
  if jq -e '[.[0].Mounts[]? | select(.Destination | test("docker\\.sock$"))] | length > 0' <<<"${inspect}" >/dev/null; then
    diag_fail 'Docker socket mounted into Home Assistant (host-root equivalent)'
  fi
fi

diag_section '2/5' 'HTTP and API'
code="$(probe_http_code "${HA_URL%/}/manifest.json" 3 10)"
printf 'url=%s/manifest.json http=%s\n' "${HA_URL%/}" "${code}"
if [[ "${code}" == 200 ]]; then diag_ok 'Frontend answers'; else diag_fail "Frontend HTTP ${code}"; fi
code="$(probe_http_code "${HA_URL%/}/api/" 3 10)"
printf 'unauthenticated /api/ http=%s\n' "${code}"
[[ "${code}" == 401 ]] || diag_warn "Unauthenticated /api/ returned ${code} (401 expected)"
token_rc=0
ha_load_token || token_rc=$?
case "${token_rc}" in
0)
  if config="$(ha_api_get /api/config)"; then
    jq -r '"version=\(.version) state=\(.state) safe_mode=\(.safe_mode) recovery_mode=\(.recovery_mode // false) components=\(.components | length)"' <<<"${config}"
    [[ "$(jq -r '.state' <<<"${config}")" == RUNNING ]] || diag_fail 'Core state is not RUNNING'
    jq -e '(.safe_mode == true) or (.recovery_mode == true)' <<<"${config}" >/dev/null &&
      diag_fail 'Home Assistant started in safe or recovery mode'
  else
    diag_fail 'API token rejected or API unreachable'
    token_rc=3
  fi
  ;;
1) diag_info "No API token (${HA_SECRETS_FILE}, key HA_TOKEN): runtime state from the API not checked" ;;
*) diag_fail "API token file ${HA_SECRETS_FILE} is unsafe or malformed (expected root:root 600 with HA_TOKEN=)" ;;
esac

diag_section '3/5' 'Integration (config entry) states (domains only)'
if ((token_rc == 0)) && entries="$(ha_api_get /api/config/config_entries/entry)"; then
  jq -r 'group_by(.state) | map("state=\(.[0].state) entries=\(length)") | .[]' <<<"${entries}"
  failing="$(jq -r '.[] | select(.disabled_by == null and .state != "loaded") | "\(.domain) \(.state)"' <<<"${entries}")"
  while read -r domain state; do
    [[ -n "${domain}" ]] && diag_fail "Integration ${domain} is ${state}"
  done <<<"${failing}"
  [[ -n "${failing}" ]] || diag_ok 'Every enabled integration is loaded'
elif offline="$(ha_config_entries_offline 2>/dev/null)"; then
  cut -f1 <<<"${offline}" | sort | uniq -c | awk '{printf "domain=%s entries=%s\n", $2, $1}'
  diag_info 'On-disk registry only: load states need the API token'
else
  diag_unknown "Config entries unreadable (${HA_CONFIG_DIR}/.storage): run as root or provide the API token"
fi

diag_section '4/5' 'Custom integrations (HACS) and configuration hygiene (no values)'
custom_dir="${HA_CONFIG_DIR}/custom_components"
if [[ -d "${custom_dir}" ]]; then
  custom_count=0
  for dir in "${custom_dir}"/*/; do
    [[ -d "${dir}" ]] || continue
    name="$(basename -- "${dir}")"
    version="$(jq -r '.version // "none"' "${dir}manifest.json" 2>/dev/null || echo unreadable)"
    printf 'custom_integration=%s version=%s\n' "${name}" "${version}"
    custom_count=$((custom_count + 1))
  done
  printf 'custom_integrations=%s hacs=%s\n' "${custom_count}" "$([[ -d "${custom_dir}/hacs" ]] && echo yes || echo no)"
  ((custom_count == 0)) || diag_info 'Custom integrations run inside Home Assistant with full access: pin versions and review before updating'
else
  diag_unknown "${custom_dir} unreadable or absent"
fi
config_file="${HA_CONFIG_DIR}/configuration.yaml"
if [[ -r "${config_file}" ]]; then
  printf 'http_use_x_forwarded_for=%s http_trusted_proxies=%s recorder_external_db=%s\n' \
    "$(grep -qE '^[[:space:]]+use_x_forwarded_for:[[:space:]]*true' "${config_file}" && echo yes || echo no)" \
    "$(grep -qE '^[[:space:]]+trusted_proxies:' "${config_file}" && echo yes || echo no)" \
    "$(grep -qE '^[[:space:]]+db_url:[[:space:]]*!secret' "${config_file}" && echo yes || echo no)"
else
  diag_unknown "${config_file} unreadable: run as root"
fi
secrets_file="${HA_CONFIG_DIR}/secrets.yaml"
if [[ -e "${secrets_file}" ]]; then
  mode="$(stat -c '%a' -- "${secrets_file}")"
  printf 'secrets_yaml_mode=%s\n' "${mode}"
  ((8#${mode} & 8#007)) && diag_warn 'secrets.yaml is readable by other users: restrict it to mode 600'
fi

diag_section '5/5' 'Reachability from inside the container (transport only)'
if ((running)); then
  network_mode="$(docker inspect --type container --format '{{.HostConfig.NetworkMode}}' "${cid}")"
  [[ "${network_mode}" == host ]] ||
    diag_info 'Bridge network: mDNS/SSDP discovery (HomeKit, Matter, Chromecast) cannot reach OPT devices; configure them by IP'
  probe_from_container() {
    local mode="$1" spec="$2" name host port
    name="${spec%%=*}"
    host="${spec#*=}"
    port="${host##*:}"
    host="${host%:*}"
    if ! [[ "${name}" =~ ^[a-z0-9-]+$ && "${host}" =~ ^[A-Za-z0-9.-]+$ && "${port}" =~ ^[0-9]+$ ]]; then
      diag_fail "Invalid target ${spec} (expected name=host:port)"
      return
    fi
    # shellcheck disable=SC2016 # Python program, not shell
    if docker exec "${cid}" python3 -I -c '
import socket, ssl, sys
mode, host, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
sock = socket.create_connection((host, port), timeout=4)
if mode == "tls":
    ssl.create_default_context().wrap_socket(sock, server_hostname=host).close()
else:
    sock.close()
' "${mode}" "${host}" "${port}" >/dev/null 2>&1; then
      diag_ok "${name}: ${mode} ${host}:${port} reachable"
    else
      diag_fail "${name}: ${mode} ${host}:${port} unreachable (pfSense rule, DNS, or service down)"
    fi
  }
  for spec in ${PROBE_TARGETS}; do
    probe_from_container tcp "${spec}"
  done
  for spec in ${CLOUD_TARGETS}; do
    probe_from_container tls "${spec}"
  done
  [[ -n "${PROBE_TARGETS}${CLOUD_TARGETS}" ]] || diag_info 'No target configured'
else
  diag_unknown 'Container not running: reachability not checked'
fi
diag_info 'Next: diagnose-homeassistant-usb.sh (dongles) and diagnose-homeassistant-overkiz.sh (io gateway)'

diag_summary
((DIAG_FAILURES == 0))
