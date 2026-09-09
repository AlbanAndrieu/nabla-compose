#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" &&
      "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" &&
      ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}"     "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
NETWORK="${FASTAPI_SAMPLE_OBSERVER_NETWORK:-sample-observer}"
EXPECTED_SOURCE_IP="${FASTAPI_SAMPLE_OBSERVER_IP:-}"
LEGACY_SOURCE_IP="${FASTAPI_SAMPLE_LEGACY_OBSERVER_IP:-172.16.55.9}"
FAILED_CANDIDATE_IP="${FASTAPI_SAMPLE_FAILED_OBSERVER_IP:-172.16.56.9}"
TRUENAS_NAME="${TRUENAS_NAME:-truenas.albandrieu.com}"
TRUENAS_PORT="${TRUENAS_PORT:-7000}"
EXPECTED_USERNAME="${TRUENAS_OBSERVER_EXPECTED_USERNAME:-fastapi_observer}"
MODE="${1:---local}"
LOCAL_BASE_URL="${TRUENAS_OBSERVER_LOCAL_BASE_URL:-http://127.0.0.1:8091}"
CLOUD_BASE_URL="${TRUENAS_OBSERVER_CLOUD_BASE_URL:-https://fastapi-sample.fastapicloud.dev}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARN: %s\n' "$*" >&2
}

case "${MODE}" in
  --local | --compare-cloud) ;;
  *) fail "usage: sudo bash scripts/security/verify-truenas-observer-access.sh [--local|--compare-cloud]" ;;
esac

for command in docker jq midclt python3 curl mktemp; do
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

privilege = identity.get("privilege")
if not isinstance(privilege, dict):
    raise SystemExit("auth.me did not expose the expected privilege object")

raw_roles = privilege.get("roles")
if isinstance(raw_roles, dict):
    roles = set(map(str, raw_roles.keys()))
elif isinstance(raw_roles, (list, tuple, set, frozenset)):
    roles = set(map(str, raw_roles))
elif isinstance(raw_roles, str):
    roles = {raw_roles} if raw_roles else set()
else:
    roles = set()

if not roles:
    raise SystemExit(
        "auth.me privilege.roles is present in an unsupported shape: "
        + type(raw_roles).__name__
    )

dangerous_roles = sorted(
    filter(
        lambda role: (
            role in {"FULL_ADMIN", "SHARING_ADMIN", "REPLICATION_ADMIN"}
            or "_WRITE" in role
            or "_DELETE" in role
            or role.endswith("_FULL_CONTROL")
        ),
        roles,
    )
)
if dangerous_roles:
    raise SystemExit(
        "observer has write/admin roles and is not least-privilege: "
        + ",".join(dangerous_roles)
    )

version = adapter.system_version()
apps = adapter.list_apps()
if "APPS_READ" not in roles and "READONLY_ADMIN" not in roles:
    raise SystemExit(
        "observer identity has neither APPS_READ nor READONLY_ADMIN: "
        + ",".join(sorted(roles))
    )

scope = "broad_readonly" if "READONLY_ADMIN" in roles else "apps_read"

print(f"authenticated_username={authenticated_username}")
print(f"rbac_scope={scope}")
print(f"roles={','.join(sorted(roles))}")
print(f"version={version}")
print(f"apps={len(apps)}")
PY

printf 'OK: TrueNAS observer source allowlist, credential selection and read-only API calls are valid\n'

if [[ "${MODE}" == "--compare-cloud" ]]; then
  printf '==> comparing TrueNAS observer visibility with FastAPI Cloud baseline\n'
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "${tmpdir}"' EXIT

  local_status="${tmpdir}/local.json"
  cloud_status="${tmpdir}/cloud.json"
  local_version="${tmpdir}/local-version.json"
  cloud_version="${tmpdir}/cloud-version.json"

  curl --fail --silent --show-error \
    --connect-timeout 3 \
    --max-time 35 \
    "${LOCAL_BASE_URL%/}/api/homelab/status" >"${local_status}"
  curl --fail --silent --show-error \
    --connect-timeout 3 \
    --max-time 35 \
    "${CLOUD_BASE_URL%/}/api/homelab/status" >"${cloud_status}"

  curl --fail --silent --show-error \
    --connect-timeout 3 \
    --max-time 10 \
    "${LOCAL_BASE_URL%/}/v2/version" >"${local_version}" || printf '{}' >"${local_version}"
  curl --fail --silent --show-error \
    --connect-timeout 3 \
    --max-time 10 \
    "${CLOUD_BASE_URL%/}/v2/version" >"${cloud_version}" || printf '{}' >"${cloud_version}"

  validate_status() {
    local label="$1"
    local status_file="$2"
    local configured
    local reachable
    local stale
    local credentials
    local credential_mode

    configured="$(jq -r '.runtime.configured // false' "${status_file}")"
    reachable="$(jq -r '.runtime.reachable // false' "${status_file}")"
    stale="$(jq -r '.runtime.stale // false' "${status_file}")"
    credentials="$(jq -r '.providerCredentials.truenas.configured // false' "${status_file}")"
    credential_mode="$(jq -r '.providerCredentials.truenas.credential_mode // "missing"' "${status_file}")"

    if [[ "${configured}" != "true" || "${reachable}" != "true" ||
      "${stale}" == "true" || "${credentials}" != "true" ||
      "${credential_mode}" != "dedicated_observer" ]]; then
      printf '%s observer status:\n' "${label}"
      jq '{
        checkedAt,
        catalogRevision,
        runtime: {
          configured: .runtime.configured,
          reachable: .runtime.reachable,
          stale: .runtime.stale,
          error: .runtime.error,
          appCount: (.runtime.apps | length)
        },
        credentials: .providerCredentials.truenas
      }' "${status_file}"
      fail "${label} observer unhealthy: configured=${configured} reachable=${reachable} stale=${stale} credentials=${credentials} credential_mode=${credential_mode}"
    fi
  }

  validate_status "TrueNAS-local FastAPI" "${local_status}"
  validate_status "FastAPI Cloud" "${cloud_status}"

  local_catalog="$(jq -r '.catalogRevision // empty' "${local_status}")"
  cloud_catalog="$(jq -r '.catalogRevision // empty' "${cloud_status}")"
  local_fastapi_version="$(jq -r '.release_version // .version // "unknown"' "${local_version}")"
  cloud_fastapi_version="$(jq -r '.release_version // .version // "unknown"' "${cloud_version}")"
  if [[ -n "${local_catalog}" && -n "${cloud_catalog}" && "${local_catalog}" != "${cloud_catalog}" ]]; then
    printf 'Catalog comparison blocked:\n'
    printf '  local FastAPI version : %s\n' "${local_fastapi_version}"
    printf '  cloud FastAPI version : %s\n' "${cloud_fastapi_version}"
    printf '  local catalogRevision : %s\n' "${local_catalog}"
    printf '  cloud catalogRevision : %s\n' "${cloud_catalog}"
    fail "catalog revisions differ; align FastAPI catalog-schema compatibility/cache state and redeploy before comparing observer identities"
  fi

  local_ids="$(jq -cS '[.runtime.apps[]?.app_id] | sort' "${local_status}")"
  cloud_ids="$(jq -cS '[.runtime.apps[]?.app_id] | sort' "${cloud_status}")"
  if [[ "${local_ids}" != "${cloud_ids}" ]]; then
    printf 'Local app ids:\n'
    printf '%s\n' "${local_ids}" | jq .
    printf 'Cloud app ids:\n'
    printf '%s\n' "${cloud_ids}" | jq .
    fail "TrueNAS app inventory differs between fastapi_observer and the FastAPI Cloud baseline"
  fi

  state_drift="$(
    jq -n \
      --slurpfile local "${local_status}" \
      --slurpfile cloud "${cloud_status}" '
        ($local[0].runtime.apps | map({key: .app_id, value: .state}) | from_entries) as $local_states
        | ($cloud[0].runtime.apps | map({key: .app_id, value: .state}) | from_entries) as $cloud_states
        | [
            ($local_states | keys[]) as $id
            | select($local_states[$id] != $cloud_states[$id])
            | {
                app_id: $id,
                local: $local_states[$id],
                cloud: $cloud_states[$id]
              }
          ]
      '
  )"

  if [[ "$(jq 'length' <<<"${state_drift}")" -gt 0 ]]; then
    warn "runtime state changed between observations; complete inventory visibility still matches"
    printf '%s\n' "${state_drift}" | jq .
  fi

  printf 'Local observer summary:\n'
  jq '{
    checkedAt,
    catalogRevision,
    appCount: (.runtime.apps | length),
    driftSummary,
    truenasCredentialMode: .providerCredentials.truenas.credential_mode
  }' "${local_status}"

  printf 'FastAPI Cloud baseline summary:\n'
  jq '{
    checkedAt,
    catalogRevision,
    appCount: (.runtime.apps | length),
    driftSummary,
    truenasCredentialMode: .providerCredentials.truenas.credential_mode
  }' "${cloud_status}"

  printf 'NOTE: Cloud credential_mode proves canonical variable selection, not the configured username value.\n'
  printf '      Treat this as capability parity; change Cloud username + dedicated API key together before the final production smoke.\n'
  printf 'OK: fastapi_observer has parity with the FastAPI Cloud TrueNAS inventory baseline\n'
  printf '    Keep the Cloud runtime on albandrieu until this comparison is green, then switch it to fastapi_observer and rerun production smoke.\n'
fi
