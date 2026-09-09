#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
INFLUX_HOST="${SCRUTINY_INFLUX_HOST:-http://127.0.0.1:31055}"
INFLUX_ORG="${SCRUTINY_INFLUX_ORG:-nabla}"
BASE_BUCKET="${SCRUTINY_INFLUX_BUCKET:-scrutiny}"
SECRET_FILE="${SCRUTINY_SECRET_FILE:-/mnt/cpool/scrutiny/.env.secrets}"
ROTATE="${SCRUTINY_TOKEN_ROTATE:-0}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/bootstrap-scrutiny-influxdb.sh [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo"
for command in curl jq install stat mktemp; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

health="$(curl -fsS --connect-timeout 3 --max-time 8 "${INFLUX_HOST}/health")" ||
  fail "InfluxDB is not healthy at ${INFLUX_HOST}"
jq -e '(.status == "pass") or (.status == "ok") or (.status == "ready")'   >/dev/null <<<"${health}" ||
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

if [[ "${MODE}" == "--check" ]]; then
  [[ -s "${SECRET_FILE}" ]] ||
    fail "missing Scrutiny secret file: ${SECRET_FILE}; run --apply with INFLUXDB_ADMIN_TOKEN"
  [[ "$(stat -c '%a' "${SECRET_FILE}")" == "600" ]] ||
    fail "${SECRET_FILE} must be mode 0600"
  token="$(sed -n 's/^SCRUTINY_WEB_INFLUXDB_TOKEN=//p' "${SECRET_FILE}" | head -n1)"
  [[ -n "${token}" ]] || fail "SCRUTINY_WEB_INFLUXDB_TOKEN is missing from ${SECRET_FILE}"
  validate_restricted_token "${token}"
  printf '✅ Scrutiny InfluxDB bootstrap: org=%s bucket=%s token=VALID\n'     "${INFLUX_ORG}" "${BASE_BUCKET}"
  exit 0
fi

[[ -n "${INFLUXDB_ADMIN_TOKEN:-}" ]] ||
  fail "INFLUXDB_ADMIN_TOKEN is required for --apply and is never printed"

if [[ -e "${SECRET_FILE}" && "${ROTATE}" != "1" ]]; then
  fail "${SECRET_FILE} already exists; set SCRUTINY_TOKEN_ROTATE=1 only for an intentional token rotation"
fi

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
  id="$(task_id "${admin_token}" "${org_id}" "${name}")"
  if [[ -n "${id}" ]]; then
    printf '%s\n' "${id}"
    return 0
  fi

  flux="option task = {name: \"${name}\", every: 1y}\nyield now()"
  curl -fsS     --connect-timeout 3     --max-time 10     -X POST "${INFLUX_HOST}/api/v2/tasks"     -H "Authorization: Token ${admin_token}"     -H "Content-Type: application/json"     --data-binary "$(jq -cn       --arg orgID "${org_id}"       --arg flux "${flux}"       '{orgID:$orgID,flux:$flux}')" |
    jq -r '.id'
}

base_id="$(create_bucket_if_missing "${BASE_BUCKET}")"
weekly_id="$(create_bucket_if_missing "${BASE_BUCKET}_weekly")"
monthly_id="$(create_bucket_if_missing "${BASE_BUCKET}_monthly")"
yearly_id="$(create_bucket_if_missing "${BASE_BUCKET}_yearly")"
weekly_task="$(create_task_if_missing tsk-weekly-aggr)"
monthly_task="$(create_task_if_missing tsk-monthly-aggr)"
yearly_task="$(create_task_if_missing tsk-yearly-aggr)"

permissions="$(jq -cn   --arg orgID "${org_id}"   --arg base "${base_id}"   --arg weekly "${weekly_id}"   --arg monthly "${monthly_id}"   --arg yearly "${yearly_id}"   --arg weeklyTask "${weekly_task}"   --arg monthlyTask "${monthly_task}"   --arg yearlyTask "${yearly_task}" '
  [
    {action:"read",resource:{type:"orgs"}},
    {action:"read",resource:{type:"tasks"}},
    {action:"write",resource:{type:"tasks",id:$weeklyTask,orgID:$orgID}},
    {action:"write",resource:{type:"tasks",id:$monthlyTask,orgID:$orgID}},
    {action:"write",resource:{type:"tasks",id:$yearlyTask,orgID:$orgID}},
    {action:"read",resource:{type:"buckets",id:$base,orgID:$orgID}},
    {action:"write",resource:{type:"buckets",id:$base,orgID:$orgID}},
    {action:"read",resource:{type:"buckets",id:$weekly,orgID:$orgID}},
    {action:"write",resource:{type:"buckets",id:$weekly,orgID:$orgID}},
    {action:"read",resource:{type:"buckets",id:$monthly,orgID:$orgID}},
    {action:"write",resource:{type:"buckets",id:$monthly,orgID:$orgID}},
    {action:"read",resource:{type:"buckets",id:$yearly,orgID:$orgID}},
    {action:"write",resource:{type:"buckets",id:$yearly,orgID:$orgID}}
  ]')"

authorization="$(
  curl -fsS     --connect-timeout 3     --max-time 10     -X POST "${INFLUX_HOST}/api/v2/authorizations"     -H "Authorization: Token ${admin_token}"     -H "Content-Type: application/json"     --data-binary "$(jq -cn       --arg orgID "${org_id}"       --arg description "scrutiny - restricted scope token"       --argjson permissions "${permissions}"       '{orgID:$orgID,description:$description,permissions:$permissions}')"
)"
restricted_token="$(jq -r '.token // empty' <<<"${authorization}")"
[[ -n "${restricted_token}" ]] || fail "InfluxDB did not return the new Scrutiny token"

install -d -m 0750 "$(dirname "${SECRET_FILE}")"
umask 077
printf 'SCRUTINY_WEB_INFLUXDB_TOKEN=%s\n' "${restricted_token}" >"${SECRET_FILE}"
chmod 600 "${SECRET_FILE}"
unset restricted_token authorization permissions admin_token INFLUXDB_ADMIN_TOKEN

token="$(sed -n 's/^SCRUTINY_WEB_INFLUXDB_TOKEN=//p' "${SECRET_FILE}" | head -n1)"
validate_restricted_token "${token}"
unset token

printf '✅ Scrutiny InfluxDB bootstrap complete: org=%s bucket=%s secret=%s mode=0600\n'   "${INFLUX_ORG}" "${BASE_BUCKET}" "${SECRET_FILE}"
