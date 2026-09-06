#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

function fail {
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
      running=$((running + 1))
      ;;
    STOPPED)
      stopped=$((stopped + 1))
      ;;
    CRASHED)
      crashed=$((crashed + 1))
      ;;
    DEPLOYING)
      deploying=$((deploying + 1))
      ;;
    MISSING)
      missing=$((missing + 1))
      ;;
    *)
      other=$((other + 1))
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


probe_failures=0

function functional_ok {
  printf '✅ %s\n' "$*"
}

function functional_fail {
  printf '❌ %s\n' "$*" >&2
  probe_failures=$((probe_failures + 1))
}

function app_is_running {
  local app_id="$1"
  [[ "${states[${app_id}]-MISSING}" == "RUNNING" ]]
}

function app_is_present {
  local app_id="$1"
  [[ "${states[${app_id}]-MISSING}" != "MISSING" ]]
}

function probe_http_if_running {
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

function probe_intranet_tcp_if_running {
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

function probe_secret_if_present {
  local app_id="$1"
  local label="$2"
  local file="$3"
  local variable="$4"

  if ! app_is_present "${app_id}"; then
    return
  fi

  if [[ -r "${file}" ]] && grep -q "^${variable}=." "${file}"; then
    functional_ok "${label}: ${variable} configured"
  else
    functional_fail "${label}: ${variable} missing or empty in ${file}"
  fi
}

function normalize_env_value {
  local value="$1"
  local first
  local last

  if (("${#value}" >= 2)); then
    first="${value:0:1}"
    last="${value: -1}"
    if [[ "${first}" == '"' && "${last}" == '"' ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "${first}" == "'" && "${last}" == "'" ]]; then
      value="${value:1:${#value}-2}"
    fi
  fi

  printf '%s' "${value}"
}

function probe_secret_min_length_if_present {
  local app_id="$1"
  local label="$2"
  local file="$3"
  local variable="$4"
  local minimum_length="$5"
  local value

  if ! app_is_present "${app_id}"; then
    return
  fi

  if [[ ! -r "${file}" ]]; then
    functional_fail "${label}: ${file} is not readable"
    return
  fi

  value="$(sed -n "s/^${variable}=//p" "${file}" | tail -n 1)"
  value="$(normalize_env_value "${value}")"
  if (("${#value}" >= minimum_length)); then
    functional_ok "${label}: ${variable} length contract satisfied"
  else
    functional_fail "${label}: ${variable} must be at least ${minimum_length} characters"
  fi
}

function probe_secret_regex_if_present {
  local app_id="$1"
  local label="$2"
  local file="$3"
  local variable="$4"
  local regex="$5"
  local value

  if ! app_is_present "${app_id}"; then
    return
  fi

  if [[ ! -r "${file}" ]]; then
    functional_fail "${label}: ${file} is not readable"
    return
  fi

  value="$(sed -n "s/^${variable}=//p" "${file}" | tail -n 1)"
  value="$(normalize_env_value "${value}")"
  if [[ "${value}" =~ ^${regex}$ ]]; then
    functional_ok "${label}: ${variable} format contract satisfied"
  else
    functional_fail "${label}: ${variable} has an invalid format"
  fi
}


function probe_legacy_secret_name {
  local label="$1"
  local file="$2"
  local legacy_variable="$3"
  local required_variable="$4"

  if [[ ! -r "${file}" ]]; then
    return
  fi

  if grep -q "^${legacy_variable}=." "${file}" &&
    ! grep -q "^${required_variable}=." "${file}"; then
    functional_fail "${label}: ${legacy_variable} must be renamed to ${required_variable}"
  fi
}

function probe_clickhouse_runtime_if_running {
  local container
  local result
  local version
  local timezone
  local database

  if ! app_is_running clickhouse; then
    printf 'SKIP: ClickHouse SQL runtime app state is %s\n' "${states[clickhouse]-MISSING}"
    return
  fi

  container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "clickhouse" || /^ix-clickhouse-clickhouse-/ { print; exit }'
  )"

  if [[ -z "${container}" ]]; then
    functional_fail "ClickHouse SQL runtime: container not found"
    return
  fi

  if ! result="$(
    docker exec "${container}" sh -c '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "SELECT concat(version(), '"'"'|'"'"', timezone(), '"'"'|'"'"', currentDatabase())"
    ' 2>/dev/null
  )"; then
    functional_fail "ClickHouse SQL runtime: query failed"
    return
  fi

  IFS='|' read -r version timezone database <<<"${result}"
  if [[ "${timezone}" != "UTC" ]]; then
    functional_fail "ClickHouse SQL runtime: timezone is ${timezone}, expected UTC"
    return
  fi

  functional_ok "ClickHouse SQL runtime: version=${version} timezone=${timezone} database=${database}"
}

function probe_clickhouse_langfuse_contract_if_present {
  local container
  local result

  if ! app_is_present langfuse || ! app_is_running clickhouse; then
    return
  fi

  container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "clickhouse" || /^ix-clickhouse-clickhouse-/ { print; exit }'
  )"

  if [[ -z "${container}" ]]; then
    functional_fail "ClickHouse Langfuse contract: container not found"
    return
  fi

  if ! result="$(
    docker exec "${container}" sh -c '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "
          SELECT concat(
            toString((SELECT count() FROM system.databases WHERE name = '"'"'langfuse'"'"')),
            '"'"'|'"'"',
            toString((SELECT count() FROM system.users WHERE name = '"'"'langfuse'"'"'))
          )
        "
    ' 2>/dev/null
  )"; then
    functional_fail "ClickHouse Langfuse contract: metadata query failed"
    return
  fi

  if [[ "${result}" == "1|1" ]]; then
    functional_ok "ClickHouse Langfuse contract: dedicated database/user present"
  else
    functional_fail "ClickHouse Langfuse contract: expected database/user langfuse (got ${result})"
  fi
}

function probe_log_absence_if_running {
  local app_id="$1"
  local label="$2"
  local container="$3"
  local pattern="$4"

  if ! app_is_running "${app_id}"; then
    return
  fi

  if docker logs --since 5m "${container}" 2>&1 | grep -Fq "${pattern}"; then
    functional_fail "${label}: recent log contains '${pattern}'"
  else
    functional_ok "${label}: no matching error in the last 5 minutes"
  fi
}

printf '\n🔎 runtime secret contracts\n'
probe_secret_if_present homarr "Homarr secrets" /mnt/cpool/homarr/.env.secrets SECRET_ENCRYPTION_KEY
probe_secret_if_present langflow "Langflow secrets" /mnt/cpool/langflow/.env.secrets LANGFLOW_SUPERUSER_PASSWORD
probe_secret_if_present clickhouse "ClickHouse secrets" /mnt/cpool/clickhouse/.env.secrets CLICKHOUSE_PASSWORD
probe_secret_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets DATABASE_URL
probe_secret_regex_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets DATABASE_URL 'postgresql://langfuse:.+@172[.]17[.]0[.]24:5432/langfuse([?].*)?'
probe_secret_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets CLICKHOUSE_PASSWORD
probe_secret_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets REDIS_AUTH
probe_secret_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets SALT
probe_secret_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets ENCRYPTION_KEY
probe_secret_if_present langfuse "Langfuse secrets" /mnt/cpool/langfuse/.env.secrets NEXTAUTH_SECRET
probe_secret_if_present scrutiny "Scrutiny secrets" /mnt/cpool/scrutiny/.env.secrets SCRUTINY_WEB_INFLUXDB_TOKEN
probe_secret_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_PASSWORD_SECRET
probe_secret_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_ROOT_PASSWORD_SHA2
probe_secret_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_MONGODB_URI
probe_secret_min_length_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_PASSWORD_SECRET 16
probe_secret_regex_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_ROOT_PASSWORD_SHA2 '[0-9a-fA-F]{64}'
probe_legacy_secret_name "Homarr secrets" /mnt/cpool/homarr/.env.secrets HOMARR_ENCRYPTION_KEY SECRET_ENCRYPTION_KEY

printf '\n🔎 functional service checks\n'
probe_http_if_running bichon "Bichon HTTP/15630" "http://172.17.0.24:15630/"
probe_log_absence_if_running bichon "Bichon OAuth2 encryption" bichon "Decryption failed, likely due to incorrect encryption key or corrupted data"
probe_http_if_running gatus "Gatus health" "http://172.17.0.24:8085/health"
probe_http_if_running influxdb "InfluxDB health" "http://127.0.0.1:31055/health"
probe_http_if_running graylog "Graylog load-balancer status" "http://172.17.0.24:9003/api/system/lbstatus"
probe_http_if_running homarr "Homarr HTTP/30100" "http://172.17.0.24:30100/"
probe_http_if_running langflow "Langflow health_check" "http://172.17.0.24:7860/health_check"
probe_http_if_running clickhouse "ClickHouse HTTP/ping" "http://172.17.0.24:8123/ping"
probe_clickhouse_runtime_if_running
probe_clickhouse_langfuse_contract_if_present
probe_http_if_running sentry "Sentry health" "http://172.17.0.24:9005/_health/"
probe_http_if_running langfuse "Langfuse web + database" "http://172.17.0.24:3000/api/public/health?failIfDatabaseUnavailable=true"
probe_http_if_running langfuse "Langfuse worker" "http://127.0.0.1:3030/api/health"

probe_intranet_tcp_if_running mongo "MongoDB internal service" mongo 27017
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

if ((probe_failures > 0)); then
  printf '\n❌ functional verification failed: %d probe(s) failed\n' "${probe_failures}" >&2
  exit 1
fi

printf '\n✅ functional verification passed\n'
