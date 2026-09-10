#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
CONTAINER="${SCRUTINY_WORKSTATION_COLLECTOR_CONTAINER:-scrutiny}"
EXPECTED_ENDPOINT="${SCRUTINY_WORKSTATION_API_ENDPOINT:-http://172.17.0.24:31054}"
EXPECTED_HOST_ID="${SCRUTINY_WORKSTATION_HOST_ID:-albandrieu}"
EXPECTED_VERSION="${SCRUTINY_WORKSTATION_EXPECTED_VERSION:-0.9.3}"
EXPECTED_IMAGE="${SCRUTINY_WORKSTATION_EXPECTED_IMAGE:-ghcr.io/analogj/scrutiny:v0.9.3-collector}"
SUMMARY_WAIT_ATTEMPTS="${SCRUTINY_WORKSTATION_SUMMARY_WAIT_ATTEMPTS:-20}"
SUMMARY_WAIT_DELAY="${SCRUTINY_WORKSTATION_SUMMARY_WAIT_DELAY_SECONDS:-3}"
SUMMARY_MAX_TIME="${SCRUTINY_WORKSTATION_SUMMARY_MAX_TIME_SECONDS:-35}"

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

case "${MODE}" in
--check | --submit) ;;
*) fail "usage: bash scripts/observability/verify-scrutiny-workstation-collector.sh [--check|--submit]" ;;
esac

for command in curl docker grep jq sleep; do
    command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

docker inspect "${CONTAINER}" >/dev/null 2>&1 ||
    fail "collector container not found: ${CONTAINER}"

state="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}')"
[[ "${state}" == "running" ]] ||
    fail "${CONTAINER} is not running (state=${state})"

image="$(docker inspect "${CONTAINER}" --format '{{.Config.Image}}')"
version_raw="$(docker exec "${CONTAINER}" /opt/scrutiny/bin/scrutiny-collector-metrics --version 2>&1 || true)"
version="$(grep -Eo '[0-9]+\.[0-9]+\.[0-9]+' <<<"${version_raw}" | head -n1 || true)"

if [[ "${version}" != "${EXPECTED_VERSION}" || "${image}" != "${EXPECTED_IMAGE}" ]]; then
    compose_project="$(docker inspect "${CONTAINER}" --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || true)"
    compose_workdir="$(docker inspect "${CONTAINER}" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)"
    compose_files="$(docker inspect "${CONTAINER}" --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)"

    printf 'ERROR: workstation Scrutiny collector version/image mismatch\n' >&2
    printf '  container=%s\n' "${CONTAINER}" >&2
    printf '  image=%s\n' "${image}" >&2
    printf '  detected_version=%s\n' "${version:-unknown}" >&2
    printf '  expected_version=%s\n' "${EXPECTED_VERSION}" >&2
    printf '  expected_image=%s\n' "${EXPECTED_IMAGE}" >&2
    printf '  compose_project=%s\n' "${compose_project:-unknown}" >&2
    printf '  compose_workdir=%s\n' "${compose_workdir:-unknown}" >&2
    printf '  compose_files=%s\n' "${compose_files:-unknown}" >&2
    fail "pin/recreate the workstation collector with ${EXPECTED_IMAGE} before submitting to the v${EXPECTED_VERSION} server"
fi

printf '✅ workstation collector version=%s image=%s\n' "${version}" "${image}"

mapfile -t env_lines < <(
    docker inspect "${CONTAINER}" --format '{{range .Config.Env}}{{println .}}{{end}}' |
        grep -E '^(COLLECTOR_API_ENDPOINT|COLLECTOR_HOST_ID)=' || true
)

endpoint=""
host_id=""
for line in "${env_lines[@]}"; do
    case "${line}" in
    COLLECTOR_API_ENDPOINT=*) endpoint="${line#COLLECTOR_API_ENDPOINT=}" ;;
    COLLECTOR_HOST_ID=*) host_id="${line#COLLECTOR_HOST_ID=}" ;;
    esac
done

endpoint="${endpoint%/}"
expected_endpoint="${EXPECTED_ENDPOINT%/}"

[[ "${endpoint}" == "${expected_endpoint}" ]] ||
    fail "COLLECTOR_API_ENDPOINT=${endpoint:-<missing>} expected=${expected_endpoint}"
[[ -n "${host_id}" ]] || fail "COLLECTOR_HOST_ID is missing"
[[ "${host_id}" == "${EXPECTED_HOST_ID}" ]] ||
    fail "COLLECTOR_HOST_ID=${host_id} expected=${EXPECTED_HOST_ID}; override SCRUTINY_WORKSTATION_HOST_ID only if this identity is intentional"

curl -fsS --connect-timeout 3 --max-time 8 "${expected_endpoint}/api/health" >/dev/null ||
    fail "Scrutiny Web/API is not reachable from workstation at ${expected_endpoint}"

scan="$(docker exec "${CONTAINER}" smartctl --scan-open 2>&1 || true)"
[[ -n "${scan}" ]] || fail "smartctl sees no devices inside ${CONTAINER}"
printf '%s\n' "${scan}"

if [[ "${MODE}" == "--submit" ]]; then
    set +e
    submission_output="$(
        docker exec "${CONTAINER}" /opt/scrutiny/bin/scrutiny-collector-metrics run 2>&1
    )"
    submission_status=$?
    set -e
    printf '%s\n' "${submission_output}"
    [[ "${submission_status}" -eq 0 ]] ||
        fail "workstation collector command failed (exit=${submission_status})"

    grep -q 'Collecting smartctl results for' <<<"${submission_output}" ||
        fail "collector exited successfully but collected no SMART payloads; inspect API registration compatibility and collector version"

    registered=false
    summary=""
    transient_summary_failures=0
    for ((attempt = 1; attempt <= SUMMARY_WAIT_ATTEMPTS; attempt++)); do
        set +e
        summary="$(
            curl -fsS --connect-timeout 3 --max-time "${SUMMARY_MAX_TIME}" \
                "${expected_endpoint}/api/summary" 2>/dev/null
        )"
        summary_status=$?
        set -e

        if [[ "${summary_status}" -eq 0 && -n "${summary}" ]]; then
            if jq -e --arg host "${EXPECTED_HOST_ID}" '
                [
                    .data.summary
                    | to_entries[]
                    | .value
                    | select((.device.host_id // "") == $host)
                ]
                | length > 0
            ' >/dev/null 2>&1 <<<"${summary}"; then
                registered=true
                break
            fi
        else
            transient_summary_failures=$((transient_summary_failures + 1))
            printf '⚠️  transient Scrutiny /api/summary failure after submission: attempt=%s/%s curl_exit=%s\n' \
                "${attempt}" "${SUMMARY_WAIT_ATTEMPTS}" "${summary_status}" >&2
        fi

        sleep "${SUMMARY_WAIT_DELAY}"
    done

    if ((transient_summary_failures > 0)) && [[ "${registered}" == "true" ]]; then
        printf '⚠️  Scrutiny /api/summary recovered after %s transient failure(s)\n' \
            "${transient_summary_failures}" >&2
    fi

    if [[ "${registered}" != "true" ]]; then
        printf 'Server-side Scrutiny hosts currently visible:\n' >&2
        if [[ -n "${summary}" ]]; then
            jq -r '
                [
                    .data.summary
                    | to_entries[]
                    | .value.device.host_id // "missing"
                ]
                | unique[]
            ' <<<"${summary}" 2>/dev/null >&2 || true
        fi
        fail "SMART submission exited 0 but host_id=${EXPECTED_HOST_ID} never appeared in ${expected_endpoint}/api/summary"
    fi

    device_count="$(
        jq -r --arg host "${EXPECTED_HOST_ID}" '
            [
                .data.summary
                | to_entries[]
                | .value
                | select((.device.host_id // "") == $host)
            ]
            | length
        ' <<<"${summary}"
    )"
    printf '✅ workstation SMART submission ingested by server: host_id=%s devices=%s\n' \
        "${EXPECTED_HOST_ID}" "${device_count}"
fi

printf '✅ workstation Scrutiny collector: container=%s endpoint=%s host_id=%s devices=VISIBLE\n' \
    "${CONTAINER}" "${endpoint}" "${host_id}"
