#!/usr/bin/env bash
set -euo pipefail

SCRUTINY_URL="${SCRUTINY_URL:-http://172.17.0.24:31054}"
EXPECTED_HOSTS="${SCRUTINY_EXPECTED_COLLECTOR_HOSTS:-truenas albandrieu}"
MAX_AGE_SECONDS="${SCRUTINY_COLLECTOR_MAX_AGE_SECONDS:-86400}"
SUMMARY_ATTEMPTS="${SCRUTINY_SUMMARY_ATTEMPTS:-3}"
SUMMARY_MAX_TIME="${SCRUTINY_SUMMARY_MAX_TIME_SECONDS:-35}"
SUMMARY_RETRY_DELAY="${SCRUTINY_SUMMARY_RETRY_DELAY_SECONDS:-2}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

for command in curl jq date awk mktemp rm sleep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ "${MAX_AGE_SECONDS}" =~ ^[0-9]+$ ]] ||
  fail "SCRUTINY_COLLECTOR_MAX_AGE_SECONDS must be an integer"
[[ "${SUMMARY_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]] ||
  fail "SCRUTINY_SUMMARY_ATTEMPTS must be a positive integer"
[[ "${SUMMARY_MAX_TIME}" =~ ^[1-9][0-9]*$ ]] ||
  fail "SCRUTINY_SUMMARY_MAX_TIME_SECONDS must be a positive integer"

fetch_summary() {
  local tmp
  local http_code
  local curl_status
  local attempt
  local transient_failures=0

  tmp="$(mktemp)"
  trap 'rm -f "${tmp}"' RETURN

  for ((attempt = 1; attempt <= SUMMARY_ATTEMPTS; attempt++)); do
    set +e
    http_code="$(
      curl -sS \
        --connect-timeout 3 \
        --max-time "${SUMMARY_MAX_TIME}" \
        -o "${tmp}" \
        -w '%{http_code}' \
        "${SCRUTINY_URL%/}/api/summary"
    )"
    curl_status=$?
    set -e

    if [[ "${curl_status}" -eq 0 && "${http_code}" == "200" ]] &&
      jq -e '.success == true and (.data.summary | type == "object")' >/dev/null 2>&1 <"${tmp}"; then
      if ((transient_failures > 0)); then
        printf '⚠️  Scrutiny /api/summary recovered after %s transient failure(s)\n' \
          "${transient_failures}" >&2
      fi
      cat "${tmp}"
      return 0
    fi

    transient_failures=$((transient_failures + 1))
    printf '⚠️  Scrutiny /api/summary attempt %s/%s failed: curl_exit=%s http=%s\n' \
      "${attempt}" "${SUMMARY_ATTEMPTS}" "${curl_status}" "${http_code:-000}" >&2

    if ((attempt < SUMMARY_ATTEMPTS)); then
      sleep "${SUMMARY_RETRY_DELAY}"
    fi
  done

  return 1
}

summary="$(fetch_summary)" ||
  fail "Scrutiny /api/summary did not converge after ${SUMMARY_ATTEMPTS} attempt(s)"

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
    printf '❌ collector host_id=%s has %s device(s) but no SMART collector timestamp\n' \
      "${host_id}" "${device_count}" >&2
    failures=$((failures + 1))
    continue
  fi

  if ! latest_epoch="$(date -d "${latest_date}" +%s 2>/dev/null)"; then
    printf '❌ collector host_id=%s returned an unparsable collector timestamp: %s\n' \
      "${host_id}" "${latest_date}" >&2
    failures=$((failures + 1))
    continue
  fi

  age=$((now_epoch - latest_epoch))
  if ((age < 0)); then
    age=0
  fi

  if ((age > MAX_AGE_SECONDS)); then
    printf '❌ collector host_id=%s SMART data is stale: age=%ss max=%ss latest=%s\n' \
      "${host_id}" "${age}" "${MAX_AGE_SECONDS}" "${latest_date}" >&2
    failures=$((failures + 1))
    continue
  fi

  ok "collector host_id=${host_id} devices=${device_count} latest_age=${age}s"
done

[[ "${failures}" -eq 0 ]] ||
  fail "Scrutiny collector acceptance found ${failures} issue(s)"

ok "Scrutiny collector acceptance passed for: ${EXPECTED_HOSTS}"
