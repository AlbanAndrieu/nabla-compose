#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check) ;;
  *) fail "usage: sudo bash scripts/truenas/check-observability-exporter-conflicts.sh --check" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so Docker listener ownership is visible"

for command in docker jq midclt ss; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

printf 'TrueNAS observability exporter conflict preflight (read-only)\n\n'

printf '==> TrueNAS native reporting/exporter configuration\n'
reporting_json="$(midclt call reporting.exporters.query 2>/dev/null || printf '[]')"
if jq -e 'type == "array"' >/dev/null 2>&1 <<<"${reporting_json}"; then
  count="$(jq 'length' <<<"${reporting_json}")"
  printf 'configured_reporting_exporters=%s\n' "${count}"
  if [[ "${count}" -gt 0 ]]; then
    jq -r '
      .[]
      | [
          (.id // "-"),
          (.name // "-"),
          ((.enabled // false) | tostring),
          (.attributes.exporter_type // .type // "unknown"),
          (.attributes.destination_ip // "-"),
          ((.attributes.destination_port // "-") | tostring)
        ]
      | @tsv
    ' <<<"${reporting_json}" |
      awk 'BEGIN {print "id\tname\tenabled\ttype\tdestination\tport"} {print}'
  fi
else
  printf 'WARN: reporting.exporters.query did not return a JSON array\n'
fi

if command -v systemctl >/dev/null 2>&1; then
  printf 'netdata_service=%s\n' "$(systemctl is-active netdata 2>/dev/null || true)"
fi

printf '\n==> Existing Docker observability/exporter containers\n'
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' |
  grep -Ei 'statsd|exporter|netdata|prometheus|kafka' || true

printf '\n==> Relevant host listeners\n'
listeners="$(ss -H -lntup 2>/dev/null || true)"
for port in 8125 9125 9102 9308; do
  printf -- '-- port %s --\n' "${port}"
  matches="$(awk -v port=":${port}" '$5 ~ (port "$") {print}' <<<"${listeners}")"
  if [[ -n "${matches}" ]]; then
    printf '%s\n' "${matches}"
  else
    printf 'FREE\n'
  fi
done

printf '\n==> Docker host-port ownership\n'
docker_ports="$(docker ps --format '{{.Names}}\t{{.Ports}}')"
for port in 9102 9308; do
  printf -- '-- host port %s --\n' "${port}"
  matches="$(grep -E "(^|[, ])([^, ]+:)?${port}->" <<<"${docker_ports}" || true)"
  if [[ -n "${matches}" ]]; then
    printf '%s\n' "${matches}"
  else
    printf 'no Docker publisher\n'
  fi
done

printf '\n==> Shared intranet identities\n'
if docker network inspect intranet >/dev/null 2>&1; then
  docker network inspect intranet |
    jq -r '.[0].Containers // {} | to_entries[] | [.value.Name, .value.IPv4Address] | @tsv' |
    grep -Ei 'statsd|exporter|netdata|prometheus|kafka' || true
else
  printf 'WARN: Docker network intranet is missing\n'
fi

conflicts=0

if grep -Eq '(^|[, ])([^, ]+:)?9102->' <<<"${docker_ports}" &&
  ! grep -Ei 'statsd-exporter.*9102->' <<<"${docker_ports}" >/dev/null; then
  printf 'CONFLICT: host port 9102 is already published by a non-StatsD-exporter container\n' >&2
  conflicts=$((conflicts + 1))
fi

if grep -Eq '(^|[, ])([^, ]+:)?9308->' <<<"${docker_ports}" &&
  ! grep -Ei 'kafka-exporter.*9308->' <<<"${docker_ports}" >/dev/null; then
  printf 'CONFLICT: host port 9308 is already published by a non-Kafka-exporter container\n' >&2
  conflicts=$((conflicts + 1))
fi

if awk '$5 ~ /:9125$/ {found=1} END {exit !found}' <<<"${listeners}"; then
  printf 'WARN: host port 9125 already has a listener. The proposed StatsD input is Docker-internal only, so this is not automatically a conflict, but identify the existing listener before deployment.\n'
fi

if awk '$5 ~ /:8125$/ {found=1} END {exit !found}' <<<"${listeners}"; then
  printf 'INFO: host port 8125 already has a listener. Check whether this is Netdata/another StatsD receiver before adding redundant telemetry.\n'
fi

printf '\nREAD-ONLY: no Apps, containers, listeners or reporting exporters were changed.\n'
if [[ "${conflicts}" -gt 0 ]]; then
  fail "${conflicts} exporter host-port conflict(s) detected"
fi
printf '✅ no conflicting Docker publishers detected on proposed exporter ports 9102/9308\n'
