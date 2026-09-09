#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
INFLUX_HOST="${SCRUTINY_INFLUX_HOST:-http://127.0.0.1:31055}"
INFLUX_ORG="${SCRUTINY_INFLUX_ORG:-nabla}"
BASE_BUCKET="${SCRUTINY_INFLUX_BUCKET:-scrutiny}"
SECRET_FILE="${SCRUTINY_SECRET_FILE:-/mnt/cpool/scrutiny/.env.secrets}"
ROTATE="${SCRUTINY_TOKEN_ROTATE:-0}"
TOKEN_SCOPE_VERSION="2"
AUTH_DESCRIPTION="scrutiny - runtime token v2"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/bootstrap-scrutiny-influxdb.sh [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"
for command in curl jq install stat mktemp sed head; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

if ! health="$(curl -fsS --connect-timeout 3 --max-time 8 "${INFLUX_HOST}/health")"; then
  printf 'InfluxDB health probe failed at %s; collecting runtime evidence...\n' "${INFLUX_HOST}" >&2
  if [[ -x scripts/truenas/diagnose-influxdb.sh ]]; then
    bash scripts/truenas/diagnose-influxdb.sh --check >&2 || true
  fi
  fail "InfluxDB is not healthy at ${INFLUX_HOST}"
fi
jq -e '(.status == "pass") or (.status == "ok") or (.status == "ready")' >/dev/null <<<"${health}" ||
  fail "InfluxDB health payload is not passing"

auth_get() {
  local token="$1"
  local path="$2"
  curl -fsS     --connect-timeout 3     --max-time 10     -H "Authorization: Token ${token}"     "${INFLUX_HOST}${path}"
}

org_id_for_token() {
  local token="$1"
  auth_get "${token}" "/api/v2/orgs?org=${INFLUX_ORG}" |
    jq -r '.orgs[0].id // empty'
}

bucket_id() {
  local token="$1"
  local org_id="$2"
  local name="$3"
  auth_get "${token}" "/api/v2/buckets?orgID=${org_id}&name=${name}" |
    jq -r --arg name "${name}" '.buckets[]? | select(.name == $name) | .id' |
    head -n1
}

task_id() {
  local token="$1"
  local org_id="$2"
  local name="$3"
  auth_get "${token}" "/api/v2/tasks?orgID=${org_id}&limit=100" |
    jq -r --arg name "${name}" '.tasks[]? | select(.name == $name) | .id' |
    head -n1
}

validate_restricted_token() {
  local token="$1"
  local org_id
  local name

  org_id="$(org_id_for_token "${token}")"
  [[ -n "${org_id}" ]] || fail "Scrutiny token cannot read organization ${INFLUX_ORG}"

  for name in     "${BASE_BUCKET}"     "${BASE_BUCKET}_weekly"     "${BASE_BUCKET}_monthly"     "${BASE_BUCKET}_yearly"; do
    [[ -n "$(bucket_id "${token}" "${org_id}" "${name}")" ]] ||
      fail "Scrutiny token cannot read bucket ${name}"
  done

  for name in tsk-weekly-aggr tsk-monthly-aggr tsk-yearly-aggr; do
    [[ -n "$(task_id "${token}" "${org_id}" "${name}")" ]] ||
      fail "Scrutiny token cannot read task ${name}"
  done
}

scrutiny_authorization_ids() {
  local token="$1"
  local org_id="$2"

  auth_get "${token}" "/api/v2/authorizations?orgID=${org_id}&limit=100" |
    jq -r --arg description "${AUTH_DESCRIPTION}" '
      .authorizations[]?
      | select(
          .description == $description
          or .description == "scrutiny - restricted scope token"
        )
      | .id
    '
}

if [[ "${MODE}" == "--check" ]]; then
  [[ -s "${SECRET_FILE}" ]] ||
    fail "missing Scrutiny secret file: ${SECRET_FILE}; run --apply with INFLUXDB_ADMIN_TOKEN"
  [[ "$(stat -c '%a' "${SECRET_FILE}")" == "600" ]] ||
    fail "${SECRET_FILE} must be mode 0600"
  token="$(sed -n 's/^SCRUTINY_WEB_INFLUXDB_TOKEN=//p' "${SECRET_FILE}" | head -n1)"
  scope_version="$(sed -n 's/^SCRUTINY_INFLUXDB_TOKEN_SCOPE_VERSION=//p' "${SECRET_FILE}" | head -n1)"
  [[ -n "${token}" ]] || fail "SCRUTINY_WEB_INFLUXDB_TOKEN is missing from ${SECRET_FILE}"
  [[ "${scope_version}" == "${TOKEN_SCOPE_VERSION}" ]] ||
    fail "Scrutiny token scope is legacy or unknown; rotate it with SCRUTINY_TOKEN_ROTATE=1 and INFLUXDB_ADMIN_TOKEN"
  validate_restricted_token "${token}"
  printf '✅ Scrutiny InfluxDB bootstrap: org=%s bucket=%s token=VALID scope=v%s\n'     "${INFLUX_ORG}" "${BASE_BUCKET}" "${TOKEN_SCOPE_VERSION}"
  exit 0
fi

[[ -n "${INFLUXDB_ADMIN_TOKEN:-}" ]] ||
  fail "INFLUXDB_ADMIN_TOKEN is required for --apply and is never printed"

existing_token=""
if [[ -f "${SECRET_FILE}" ]]; then
  existing_token="$(sed -n 's/^SCRUTINY_WEB_INFLUXDB_TOKEN=//p' "${SECRET_FILE}" | head -n1)"
fi
if [[ -n "${existing_token}" && "${ROTATE}" != "1" ]]; then
  fail "${SECRET_FILE} already contains SCRUTINY_WEB_INFLUXDB_TOKEN; set SCRUTINY_TOKEN_ROTATE=1 only for an intentional token rotation"
fi
unset existing_token

admin_token="${INFLUXDB_ADMIN_TOKEN}"
org_id="$(org_id_for_token "${admin_token}")"
[[ -n "${org_id}" ]] || fail "operator token cannot resolve InfluxDB organization ${INFLUX_ORG}"

create_bucket_if_missing() {
  local name="$1"
  local id
  id="$(bucket_id "${admin_token}" "${org_id}" "${name}")"
  if [[ -n "${id}" ]]; then
    printf '%s\n' "${id}"
    return 0
  fi

  curl -fsS     --connect-timeout 3     --max-time 10     -X POST "${INFLUX_HOST}/api/v2/buckets"     -H "Authorization: Token ${admin_token}"     -H "Content-Type: application/json"     --data-binary "$(jq -cn       --arg name "${name}"       --arg orgID "${org_id}"       '{name:$name,orgID:$orgID,retentionRules:[]}')" |
    jq -r '.id'
}

create_task_if_missing() {
  local name="$1"
  local id
  local flux
  local response_file
  local http_code
  local message

  id="$(task_id "${admin_token}" "${org_id}" "${name}")"
  if [[ -n "${id}" ]]; then
    printf '%s\n' "${id}"
    return 0
  fi

  # Scrutiny historical BYO-InfluxDB docs used "yield now()" as a
  # placeholder. InfluxDB 2.9 rejects that Flux with HTTP 400. Keep the task
  # inert but syntactically valid; Scrutiny replaces it during startup.
  printf -v flux \
    'option task = {name: "%s", every: 1y}\n\nfrom(bucket: "%s")\n  |> range(start: -1m)\n  |> limit(n: 1)' \
    "${name}" "${BASE_BUCKET}"
  response_file="$(mktemp)"
  http_code="$(
    curl -sS \
      --connect-timeout 3 \
      --max-time 10 \
      -o "${response_file}" \
      -w '%{http_code}' \
      -X POST "${INFLUX_HOST}/api/v2/tasks" \
      -H "Authorization: Token ${admin_token}" \
      -H "Content-Type: application/json" \
      --data-binary "$(jq -cn \
        --arg orgID "${org_id}" \
        --arg flux "${flux}" \
        '{orgID:$orgID,flux:$flux,status:"inactive"}')"
  )" || {
    rm -f "${response_file}"
    fail "InfluxDB task create request failed for ${name}"
  }

  if [[ ! "${http_code}" =~ ^2 ]]; then
    message="$(jq -r '.message // .error // .err // "unknown error"' "${response_file}" 2>/dev/null || cat "${response_file}")"
    rm -f "${response_file}"
    fail "InfluxDB task create failed for ${name}: HTTP ${http_code}: ${message}"
  fi

  jq -r '.id' "${response_file}"
  rm -f "${response_file}"
}

base_id="$(create_bucket_if_missing "${BASE_BUCKET}")"
weekly_id="$(create_bucket_if_missing "${BASE_BUCKET}_weekly")"
monthly_id="$(create_bucket_if_missing "${BASE_BUCKET}_monthly")"
yearly_id="$(create_bucket_if_missing "${BASE_BUCKET}_yearly")"
weekly_task="$(create_task_if_missing tsk-weekly-aggr)"
monthly_task="$(create_task_if_missing tsk-monthly-aggr)"
yearly_task="$(create_task_if_missing tsk-yearly-aggr)"

permissions="$(jq -cn --arg orgID "${org_id}" '
  [
    {action:"read",resource:{type:"orgs",id:$orgID}},
    {action:"read",resource:{type:"buckets",orgID:$orgID}},
    {action:"write",resource:{type:"buckets",orgID:$orgID}},
    {action:"read",resource:{type:"tasks",orgID:$orgID}},
    {action:"write",resource:{type:"tasks",orgID:$orgID}}
  ]')"

# Scrutiny v0.9.3 can create/delete/rename temporary <bucket>_new buckets during
# its WWN -> UUID migration and can recreate downsampling tasks when missing.
# InfluxDB models these capabilities at organization scope. Keeping orgID on
# bucket/task resources avoids all-access/operator privileges while allowing
# the upstream migration to complete.

old_auth_ids="$(scrutiny_authorization_ids "${admin_token}" "${org_id}" || true)"

authorization="$(
  curl -fsS     --connect-timeout 3     --max-time 10     -X POST "${INFLUX_HOST}/api/v2/authorizations"     -H "Authorization: Token ${admin_token}"     -H "Content-Type: application/json"     --data-binary "$(jq -cn       --arg orgID "${org_id}"       --arg description "${AUTH_DESCRIPTION}"       --argjson permissions "${permissions}"       '{orgID:$orgID,description:$description,permissions:$permissions}')"
)"
restricted_token="$(jq -r '.token // empty' <<<"${authorization}")"
new_auth_id="$(jq -r '.id // empty' <<<"${authorization}")"
[[ -n "${restricted_token}" ]] || fail "InfluxDB did not return the new Scrutiny token"
[[ -n "${new_auth_id}" ]] || fail "InfluxDB did not return the new Scrutiny authorization id"

# Validate before replacing the runtime secret. This avoids cutting over to a
# token that cannot even read the expected Scrutiny resources.
validate_restricted_token "${restricted_token}"

install -d -m 0750 "$(dirname "${SECRET_FILE}")"
secret_tmp="$(mktemp "$(dirname "${SECRET_FILE}")/.env.secrets.XXXXXX")"
umask 077
{
  printf 'SCRUTINY_WEB_INFLUXDB_TOKEN=%s\n' "${restricted_token}"
  printf 'SCRUTINY_INFLUXDB_TOKEN_SCOPE_VERSION=%s\n' "${TOKEN_SCOPE_VERSION}"
  printf 'SCRUTINY_INFLUXDB_AUTH_ID=%s\n' "${new_auth_id}"
} >"${secret_tmp}"
chmod 600 "${secret_tmp}"
mv -f "${secret_tmp}" "${SECRET_FILE}"
chmod 600 "${SECRET_FILE}"

# Revoke previous Scrutiny authorizations only after the new token is validated
# and durably installed. Failure to revoke is reported but does not invalidate
# the working replacement token.
while IFS= read -r old_auth_id; do
  [[ -n "${old_auth_id}" ]] || continue
  [[ "${old_auth_id}" != "${new_auth_id}" ]] || continue
  if curl -fsS     --connect-timeout 3     --max-time 10     -X DELETE "${INFLUX_HOST}/api/v2/authorizations/${old_auth_id}"     -H "Authorization: Token ${admin_token}" >/dev/null; then
    printf 'Revoked superseded Scrutiny InfluxDB authorization %s\n' "${old_auth_id}"
  else
    printf 'WARNING: unable to revoke superseded Scrutiny authorization %s\n' "${old_auth_id}" >&2
  fi
done <<<"${old_auth_ids}"

unset restricted_token authorization permissions old_auth_ids new_auth_id admin_token INFLUXDB_ADMIN_TOKEN

token="$(sed -n 's/^SCRUTINY_WEB_INFLUXDB_TOKEN=//p' "${SECRET_FILE}" | head -n1)"
validate_restricted_token "${token}"
unset token

printf '✅ Scrutiny InfluxDB bootstrap complete: org=%s bucket=%s secret=%s mode=0600 scope=v%s\n'   "${INFLUX_ORG}" "${BASE_BUCKET}" "${SECRET_FILE}" "${TOKEN_SCOPE_VERSION}"
