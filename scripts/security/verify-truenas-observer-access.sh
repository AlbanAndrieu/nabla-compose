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
from nabla.settings.homelab import TrueNASProviderSettings

settings = TrueNASProviderSettings()
key = settings.adapter_api_key
key_id = key.split("-", 1)[0] if "-" in key else "<unknown>"

print("username_variable =", settings.adapter_username_environment)
print("api_key_variable  =", settings.adapter_api_key_environment)
print("api_key_id        =", key_id)
print("verify_ssl        =", settings.verify_ssl)
print(
    "shadowed_username_variables =",
    ",".join(settings.shadowed_username_environments) or "<none>",
)
print(
    "shadowed_api_key_variables  =",
    ",".join(settings.shadowed_api_key_environments) or "<none>",
)

if settings.adapter_username_environment != "TRUENAS_API_USERNAME":
    raise SystemExit("canonical TRUENAS_API_USERNAME is not selected")
if settings.adapter_api_key_environment != "TRUENAS_API_KEY":
    raise SystemExit("canonical TRUENAS_API_KEY is not selected")
if not settings.verify_ssl:
    raise SystemExit(
        "TRUENAS_API_VERIFY_SSL must be true for the hostname-validated homelab observer"
    )
PY

shadowed_user="$(
  docker exec -i "${CONTAINER}" /code/.venv/bin/python - <<'PY'
from nabla.settings.homelab import TrueNASProviderSettings

print(",".join(TrueNASProviderSettings().shadowed_username_environments))
PY
)"
if [[ -n "${shadowed_user}" ]]; then
  warn "legacy TrueNAS username aliases remain configured and shadowed: ${shadowed_user}"
fi

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
