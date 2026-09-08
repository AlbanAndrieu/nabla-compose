#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
EXPECTED_SOURCE_IP="${FASTAPI_SAMPLE_OBSERVER_IP:-}"
LEGACY_SOURCE_IP="${FASTAPI_SAMPLE_LEGACY_OBSERVER_IP:-172.16.55.9}"
FAILED_CANDIDATE_IP="${FASTAPI_SAMPLE_FAILED_OBSERVER_IP:-172.16.56.9}"
TRUENAS_NAME="${TRUENAS_NAME:-truenas.albandrieu.com}"
TRUENAS_PORT="${TRUENAS_PORT:-7000}"
EXPECTED_USERNAME="${TRUENAS_OBSERVER_EXPECTED_USERNAME:-fastapi_observer}"

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

printf '==> FastAPI observer network ownership\n'
network_role="$(
  docker network inspect "${NETWORK}" |
    jq -r '.[0].Labels["com.nabla.role"] // empty'
)"
network_expected_ip="$(
  docker network inspect "${NETWORK}" |
    jq -r '.[0].Labels["com.nabla.observer-ip"] // empty'
)"

[[ "${network_role}" == "fastapi-sample-observer" ]] ||
  fail "${NETWORK} is not the repository-managed FastAPI Sample observer network"
[[ -n "${network_expected_ip}" ]] ||
  fail "${NETWORK} has no com.nabla.observer-ip label"

if [[ -z "${EXPECTED_SOURCE_IP}" ]]; then
  EXPECTED_SOURCE_IP="${network_expected_ip}"
elif [[ "${EXPECTED_SOURCE_IP}" != "${network_expected_ip}" ]]; then
  fail "configured observer IP ${EXPECTED_SOURCE_IP} does not match network reservation ${network_expected_ip}"
fi

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
active_allowlist_json="$(
  midclt call system.general.get_ui_allowlist |
    jq -c '. // []'
)"
printf 'Persisted allowlist:\n'
printf '%s\n' "${allowlist_json}" | jq .
printf 'Active runtime allowlist:\n'
printf '%s\n' "${active_allowlist_json}" | jq .

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

printf 'OK: persisted TrueNAS ui_allowlist permits %s\n' "${container_ip}"

if ! python3 - "${container_ip}" "${active_allowlist_json}" <<'PY'
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
  fail "active TrueNAS ui_allowlist does not permit ${container_ip}; persisted settings may require system.general.ui_restart"
fi

printf 'OK: active TrueNAS ui_allowlist permits %s\n' "${container_ip}"

for forbidden_ip in "${LEGACY_SOURCE_IP}" "${FAILED_CANDIDATE_IP}"; do
  if [[ "${forbidden_ip}" == "${container_ip}" ]]; then
    continue
  fi
  if python3 - "${forbidden_ip}" "${allowlist_json}" <<'PY'
import ipaddress
import json
import sys

address = ipaddress.ip_address(sys.argv[1])
allowlist = json.loads(sys.argv[2])
for entry in allowlist:
    try:
        if address in ipaddress.ip_network(entry, strict=False):
            raise SystemExit(0)
    except ValueError:
        continue
raise SystemExit(1)
PY
  then
    fail "obsolete observer source ${forbidden_ip} is still allowlisted; remove stale/shared-pool observer /32 entries"
  fi
done

printf '==> canonical FastAPI TrueNAS observer credential\n'
docker exec -i \
  -e TRUENAS_OBSERVER_EXPECTED_USERNAME="${EXPECTED_USERNAME}" \
  "${CONTAINER}" /code/.venv/bin/python - <<'PY'
import os

from nabla.settings.homelab import TrueNASProviderSettings

settings = TrueNASProviderSettings()
expected_username = os.environ["TRUENAS_OBSERVER_EXPECTED_USERNAME"].strip()

print("username_variable =", settings.adapter_username_environment)
print("api_key_variable  =", settings.adapter_api_key_environment)
print("verify_ssl        =", settings.verify_ssl)
print(
    "ignored_username_variables =",
    ",".join(settings.shadowed_username_environments) or "<none>",
)
print(
    "ignored_api_key_variables  =",
    ",".join(settings.shadowed_api_key_environments) or "<none>",
)

if settings.adapter_username != expected_username:
    raise SystemExit(
        f"authenticated observer username is not the expected {expected_username!r}"
    )
if settings.adapter_username_environment != "TRUENAS_API_USERNAME":
    raise SystemExit("FastAPI must use canonical TRUENAS_API_USERNAME")
if settings.adapter_api_key_environment != "TRUENAS_API_KEY":
    raise SystemExit("FastAPI must use canonical TRUENAS_API_KEY")
if not settings.adapter_api_key:
    raise SystemExit("TRUENAS_API_KEY is missing")
if not settings.verify_ssl:
    raise SystemExit(
        "TRUENAS_API_VERIFY_SSL must be true for the hostname-validated homelab observer"
    )
PY

printf '==> TrueNAS HTTPS version discovery from container\n'
docker exec "${CONTAINER}" curl --fail --silent --show-error   "https://${TRUENAS_NAME}:${TRUENAS_PORT}/api/versions" |
  jq .

printf '==> authenticated TrueNAS WebSocket observer identity and calls\n'
docker exec -i \
  -e TRUENAS_OBSERVER_EXPECTED_USERNAME="${EXPECTED_USERNAME}" \
  "${CONTAINER}" /code/.venv/bin/python - <<'PY'
import os

from nabla.integrations.truenas_client import build_truenas_adapter

adapter = build_truenas_adapter()
if adapter is None:
    raise SystemExit("TrueNAS adapter is not configured")

expected_username = os.environ["TRUENAS_OBSERVER_EXPECTED_USERNAME"].strip()
identity = adapter._call("auth.me")
if not isinstance(identity, dict):
    raise SystemExit("auth.me returned an unexpected payload")

authenticated_username = str(identity.get("pw_name") or "")
if authenticated_username != expected_username:
    raise SystemExit(
        f"auth.me identity mismatch: expected {expected_username!r}, got {authenticated_username!r}"
    )

roles: set[str] = set()


def collect_roles(value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "roles" and isinstance(nested, list):
                roles.update(str(role) for role in nested)
            else:
                collect_roles(nested)
    elif isinstance(value, list):
        for nested in value:
            collect_roles(nested)


collect_roles(identity.get("privilege"))
if not roles:
    raise SystemExit("auth.me did not expose any effective RBAC roles")

dangerous_roles = sorted(
    role
    for role in roles
    if role in {"FULL_ADMIN", "SHARING_ADMIN", "REPLICATION_ADMIN"}
    or "_WRITE" in role
    or "_DELETE" in role
    or role.endswith("_FULL_CONTROL")
)
if dangerous_roles:
    raise SystemExit(
        "observer has write/admin roles and is not least-privilege: "
        + ",".join(dangerous_roles)
    )

version = adapter.system_version()
apps = adapter.list_apps()
scope = "broad_readonly" if "READONLY_ADMIN" in roles else "least_privilege_candidate"

print(f"authenticated_username={authenticated_username}")
print(f"rbac_scope={scope}")
print(f"roles={','.join(sorted(roles))}")
print(f"version={version}")
print(f"apps={len(apps)}")
PY

printf 'OK: TrueNAS observer source allowlist, credential selection and read-only API calls are valid\n'
