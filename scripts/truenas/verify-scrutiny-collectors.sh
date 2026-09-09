#!/usr/bin/env bash
set -euo pipefail

SCRUTINY_URL="${SCRUTINY_URL:-http://172.17.0.24:31054}"
EXPECTED_HOSTS="${SCRUTINY_EXPECTED_COLLECTOR_HOSTS:-truenas albandrieu}"
MAX_AGE_SECONDS="${SCRUTINY_COLLECTOR_MAX_AGE_SECONDS:-86400}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

for command in curl jq date awk; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ "${MAX_AGE_SECONDS}" =~ ^[0-9]+$ ]] ||
  fail "SCRUTINY_COLLECTOR_MAX_AGE_SECONDS must be an integer"

summary="$(
  curl -fsS     --connect-timeout 3     --max-time 15     "${SCRUTINY_URL%/}/api/summary"
)"

jq -e '.success == true and (.data.summary | type == "object")' >/dev/null <<<"${summary}" ||
  fail "Scrutiny /api/summary did not return a successful summary object"

printf 'Scrutiny collector inventory:\n'
jq -r '
  .data.summary
  | to_entries[]
  | [
      (.value.device.host_id // "missing"),
      (.value.device.device_name // "unknown"),
      (.value.device.model_name // "unknown"),
      (.value.smart.collector_date // "missing")
    ]
  | @tsv
' <<<"${summary}" |
  awk -F '\t' '{printf "  host=%-12s device=%-12s model=%-24s collector_date=%s\n", $1, $2, $3, $4}'

now_epoch="$(date +%s)"
failures=0

for host_id in ${EXPECTED_HOSTS}; do
  host_rows="$(
    jq -c --arg host "${host_id}" '
      [
        .data.summary
        | to_entries[]
        | .value
        | select((.device.host_id // "") == $host)
      ]
    ' <<<"${summary}"
  )"
  device_count="$(jq 'length' <<<"${host_rows}")"

  if [[ "${device_count}" -lt 1 ]]; then
    printf '❌ collector host_id=%s has no registered devices\n' "${host_id}" >&2
    failures=$((failures + 1))
    continue
  fi

  latest_date="$(
    jq -r '
      [
        .[]
        | .smart.collector_date // empty
        | select(. != "")
      ]
      | sort
      | last // empty
    ' <<<"${host_rows}"
  )"

  if [[ -z "${latest_date}" ]]; then
    printf '❌ collector host_id=%s has %s device(s) but no SMART collector timestamp\n'       "${host_id}" "${device_count}" >&2
    failures=$((failures + 1))
    continue
  fi

  if ! latest_epoch="$(date -d "${latest_date}" +%s 2>/dev/null)"; then
    printf '❌ collector host_id=%s returned an unparsable collector timestamp: %s\n'       "${host_id}" "${latest_date}" >&2
    failures=$((failures + 1))
    continue
  fi

  age=$((now_epoch - latest_epoch))
  if ((age < 0)); then
    age=0
  fi

  if ((age > MAX_AGE_SECONDS)); then
    printf '❌ collector host_id=%s SMART data is stale: age=%ss max=%ss latest=%s\n'       "${host_id}" "${age}" "${MAX_AGE_SECONDS}" "${latest_date}" >&2
    failures=$((failures + 1))
    continue
  fi

  ok "collector host_id=${host_id} devices=${device_count} latest_age=${age}s"
done

[[ "${failures}" -eq 0 ]] ||
  fail "Scrutiny collector acceptance found ${failures} issue(s)"

ok "Scrutiny collector acceptance passed for: ${EXPECTED_HOSTS}"
