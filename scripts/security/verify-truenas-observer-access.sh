#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-intranet}"
EXPECTED_SOURCE_IP="${FASTAPI_SAMPLE_OBSERVER_IP:-172.16.55.9}"
TRUENAS_NAME="${TRUENAS_NAME:-truenas.albandrieu.com}"
TRUENAS_PORT="${TRUENAS_PORT:-7000}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

for command in docker jq midclt python3 curl; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf '==> FastAPI observer container source address\n'
container_ip="$(
  docker inspect "${CONTAINER}" |
    jq -r --arg network "${NETWORK}"       '.[0].NetworkSettings.Networks[$network].IPAddress // empty'
)"
[[ -n "${container_ip}" ]] ||
  fail "${CONTAINER} is not attached to Docker network ${NETWORK}"

printf 'container=%s network=%s source_ip=%s expected_source_ip=%s\n'   "${CONTAINER}" "${NETWORK}" "${container_ip}" "${EXPECTED_SOURCE_IP}"

[[ "${container_ip}" == "${EXPECTED_SOURCE_IP}" ]] ||
  fail "observer source IP drift: expected ${EXPECTED_SOURCE_IP}, got ${container_ip}; do not widen TrueNAS ui_allowlist"

printf '==> TrueNAS UI/API source allowlist\n'
allowlist_json="$(
  midclt call system.general.config |
    jq -c '.ui_allowlist // []'
)"
printf '%s\n' "${allowlist_json}" | jq .

if ! python3 - "${container_ip}" "${allowlist_json}" <<'PY'
import ipaddress
import json
import sys

address = ipaddress.ip_address(sys.argv[1])
allowlist = json.loads(sys.argv[2])
if not allowlist:
    raise SystemExit(0)

for entry in allowlist:
    try:
        if address in ipaddress.ip_network(entry, strict=False):
            raise SystemExit(0)
    except ValueError:
        continue

raise SystemExit(1)
PY
then
  fail "TrueNAS ui_allowlist does not permit ${container_ip}; review a narrow ${container_ip}/32 with rollback/check-in protection"
fi

printf 'OK: TrueNAS ui_allowlist permits %s\n' "${container_ip}"

printf '==> sanitized FastAPI TrueNAS credential selection\n'
docker exec -i "${CONTAINER}" /code/.venv/bin/python - <<'PY'
import os

from nabla.settings.homelab import TrueNASProviderSettings

settings = TrueNASProviderSettings()
key = settings.adapter_api_key
key_id = key.split("-", 1)[0] if "-" in key else "<unknown>"

username_candidates = (
    ("TRUENAS_API_USERNAME", os.getenv("TRUENAS_API_USERNAME", "").strip()),
    ("TRUENAS_USERNAME", os.getenv("TRUENAS_USERNAME", "").strip()),
    ("TRUENAS_USER", os.getenv("TRUENAS_USER", "").strip()),
)
selected_username_variable = next(
    (name for name, value in username_candidates if value),
    "TRUENAS_API_USERNAME",
)
shadowed_username_variables = [
    name
    for name, value in username_candidates
    if value and name != selected_username_variable
]

api_key_candidates = (
    ("TRUENAS_API_KEY", os.getenv("TRUENAS_API_KEY", "").strip()),
    ("TRUENAS_MCP_API_KEY", os.getenv("TRUENAS_MCP_API_KEY", "").strip()),
)
selected_api_key_variable = next(
    (name for name, value in api_key_candidates if value),
    "TRUENAS_API_KEY",
)
shadowed_api_key_variables = [
    name
    for name, value in api_key_candidates
    if value and name != selected_api_key_variable
]

print("username_variable =", selected_username_variable)
print("api_key_variable  =", selected_api_key_variable)
print("api_key_id        =", key_id)
print("verify_ssl        =", settings.verify_ssl)
print(
    "shadowed_username_variables =",
    ",".join(shadowed_username_variables) or "<none>",
)
print(
    "shadowed_api_key_variables  =",
    ",".join(shadowed_api_key_variables) or "<none>",
)

if selected_username_variable != "TRUENAS_API_USERNAME":
    raise SystemExit("canonical TRUENAS_API_USERNAME is not selected")
if selected_api_key_variable != "TRUENAS_API_KEY":
    raise SystemExit("canonical TRUENAS_API_KEY is not selected")
if not settings.verify_ssl:
    raise SystemExit(
        "TRUENAS_API_VERIFY_SSL must be true for the hostname-validated homelab observer"
    )
PY

shadowed_user="$(
  docker exec -i "${CONTAINER}" /code/.venv/bin/python - <<'PY'
import os

selected = "TRUENAS_API_USERNAME" if os.getenv("TRUENAS_API_USERNAME", "").strip() else (
    "TRUENAS_USERNAME" if os.getenv("TRUENAS_USERNAME", "").strip() else "TRUENAS_USER"
)
configured = (
    ("TRUENAS_API_USERNAME", os.getenv("TRUENAS_API_USERNAME", "").strip()),
    ("TRUENAS_USERNAME", os.getenv("TRUENAS_USERNAME", "").strip()),
    ("TRUENAS_USER", os.getenv("TRUENAS_USER", "").strip()),
)
print(",".join(name for name, value in configured if value and name != selected))
PY
)"
if [[ -n "${shadowed_user}" ]]; then
  warn "legacy TrueNAS username aliases remain configured and shadowed: ${shadowed_user}"
fi

printf '==> websocket-client proxy decision\n'
docker exec -i "${CONTAINER}" /code/.venv/bin/python - <<'PY'
from urllib.parse import urlparse

from nabla.settings.homelab import TrueNASProviderSettings
from websocket._url import get_proxy_info

settings = TrueNASProviderSettings()
hostname = urlparse(settings.websocket_uri).hostname
proxy_host, proxy_port, _proxy_auth = get_proxy_info(
    hostname,
    True,
    None,
    0,
    None,
    None,
)
if proxy_host:
    raise SystemExit(
        f"websocket-client would proxy TrueNAS via {proxy_host}:{proxy_port}; "
        "add the TrueNAS hostname/private address to NO_PROXY instead"
    )
print(f"direct websocket route for {hostname}")
PY

printf '==> TrueNAS HTTPS version discovery from container\n'
docker exec "${CONTAINER}" curl --fail --silent --show-error   "https://${TRUENAS_NAME}:${TRUENAS_PORT}/api/versions" |
  jq .

printf '==> authenticated TrueNAS WebSocket observer calls\n'
docker exec -i "${CONTAINER}" /code/.venv/bin/python - <<'PY'
from nabla.integrations.truenas_client import build_truenas_adapter

adapter = build_truenas_adapter()
if adapter is None:
    raise SystemExit("TrueNAS adapter is not configured")

version = adapter.system_version()
apps = adapter.list_apps()

print(f"version={version}")
print(f"apps={len(apps)}")
PY

printf 'OK: TrueNAS observer source allowlist, credential selection and read-only API calls are valid\n'
