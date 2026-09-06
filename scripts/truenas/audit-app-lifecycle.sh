#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

for command in curl docker git jq midclt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

tmp="$(mktemp)"
trap 'rm -f "${tmp}"' EXIT
midclt call app.query >"${tmp}"

declare -A states=()
while IFS=$'\t' read -r app_id state; do
  [[ -n "${app_id}" ]] || continue
  states["${app_id}"]="${state}"
done < <(jq -r '.[] | [(.id // .name), (.state // "UNKNOWN")] | @tsv' "${tmp}")

declare -A app_alias=(
  [2fauth]="twofactor-auth"
  [elasticsearch]="elastic-search"
  [homeassistant]="home-assistant"
  [reactive]="reactive-resume"
)

running=0
stopped=0
crashed=0
deploying=0
missing=0
other=0

printf '🔎 repository-backed TrueNAS application inventory\n'
printf '%-26s %-26s %-12s\n' "REPOSITORY APP" "TRUENAS APP" "STATE"
printf '%-26s %-26s %-12s\n' "--------------------------" "--------------------------" "------------"

while IFS= read -r compose_path; do
  app="$(basename "$(dirname "${compose_path}")")"
  runtime_id="${app_alias[${app}]-${app}}"
  state="${states[${runtime_id}]-MISSING}"

  printf '%-26s %-26s %-12s\n' "${app}" "${runtime_id}" "${state}"

  case "${state}" in
    RUNNING)
      ((running += 1))
      ;;
    STOPPED)
      ((stopped += 1))
      ;;
    CRASHED)
      ((crashed += 1))
      ;;
    DEPLOYING)
      ((deploying += 1))
      ;;
    MISSING)
      ((missing += 1))
      ;;
    *)
      ((other += 1))
      ;;
  esac
done < <(git -C "${ROOT}" ls-files 'apps/*/compose.yml' | sort)

printf '\nSummary: RUNNING=%d STOPPED=%d CRASHED=%d DEPLOYING=%d MISSING=%d OTHER=%d\n' \
  "${running}" "${stopped}" "${crashed}" "${deploying}" "${missing}" "${other}"

printf '\n🔎 problematic Docker container states\n'
problematic="$(
  docker ps -a --format '{{.Names}}\t{{.Status}}\t{{.Image}}' |
    awk 'BEGIN { IGNORECASE=1 } /Restarting|unhealthy|Dead|Created/ || (/Exited \(/ && $0 !~ /Exited \(0\)/)'
)"

if [[ -n "${problematic}" ]]; then
  printf '%s\n' "${problematic}"
else
  printf '✅ no restarting, unhealthy, non-zero exited, dead or created containers detected\n'
fi


functional_failures=0

functional_ok() {
  printf '✅ %s\n' "$*"
}

functional_fail() {
  printf '❌ %s\n' "$*" >&2
  ((functional_failures += 1))
}

app_is_running() {
  local app_id="$1"
  [[ "${states[${app_id}]-MISSING}" == "RUNNING" ]]
}

probe_http_if_running() {
  local app_id="$1"
  local label="$2"
  local url="$3"

  if ! app_is_running "${app_id}"; then
    printf 'SKIP: %s app state is %s\n' "${label}" "${states[${app_id}]-MISSING}"
    return
  fi

  if curl --fail --silent --show-error --max-time 8 "${url}" >/dev/null; then
    functional_ok "${label}"
  else
    functional_fail "${label}: HTTP probe failed (${url})"
  fi
}

probe_intranet_tcp_if_running() {
  local app_id="$1"
  local label="$2"
  local host="$3"
  local port="$4"

  if ! app_is_running "${app_id}"; then
    printf 'SKIP: %s app state is %s\n' "${label}" "${states[${app_id}]-MISSING}"
    return
  fi

  if ! docker ps --format '{{.Names}}' | grep -Fxq mongo; then
    functional_fail "${label}: mongo probe container is not running"
    return
  fi

  if ! docker exec mongo getent hosts "${host}" >/dev/null 2>&1; then
    functional_fail "${label}: Docker DNS cannot resolve ${host} on intranet"
    return
  fi

  if docker exec mongo bash -lc "timeout 3 bash -c '</dev/tcp/${host}/${port}'" >/dev/null 2>&1; then
    functional_ok "${label}: Docker DNS + TCP/${port}"
  else
    functional_fail "${label}: TCP/${port} is unreachable from intranet"
  fi
}

printf '\n🔎 functional service checks\n'
probe_http_if_running bichon "Bichon HTTP/15630" "http://172.17.0.24:15630/"
probe_http_if_running gatus "Gatus health" "http://172.17.0.24:8085/health"
probe_http_if_running influxdb "InfluxDB health" "http://127.0.0.1:31055/health"
probe_http_if_running graylog "Graylog load-balancer status" "http://172.17.0.24:9003/api/system/lbstatus"
probe_http_if_running homarr "Homarr HTTP/30100" "http://172.17.0.24:30100/"
probe_http_if_running langflow "Langflow health_check" "http://172.17.0.24:7860/health_check"

probe_intranet_tcp_if_running redis "Redis internal service" redis 6379
probe_intranet_tcp_if_running opensearch "OpenSearch internal service" opensearch 9200

if app_is_running minio; then
  if ! app_is_running influxdb; then
    functional_fail "MinIO internal service: InfluxDB probe container is not running"
  elif docker exec influxdb curl --fail --silent --show-error --max-time 8 \
    http://minio:9000/minio/health/live >/dev/null 2>&1; then
    functional_ok "MinIO internal DNS + HTTP/9000"
  else
    functional_fail "MinIO internal DNS or HTTP/9000 health failed"
  fi
else
  printf 'SKIP: MinIO app state is %s\n' "${states[minio]-MISSING}"
fi

if ((functional_failures > 0)); then
  printf '\n❌ functional verification failed: %d probe(s) failed\n' "${functional_failures}" >&2
  exit 1
fi

printf '\n✅ functional verification passed\n'
