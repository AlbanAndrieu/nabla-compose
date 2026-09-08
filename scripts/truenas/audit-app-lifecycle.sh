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
declare -A tracked_runtime_ids=()

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
  tracked_runtime_ids["${runtime_id}"]=1

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

printf '\n🔎 repository applications missing from TrueNAS app.query\n'
if ((missing == 0)); then
  printf '✅ every repository-backed apps/*/compose.yml has a matching TrueNAS application\n'
else
  while IFS= read -r compose_path; do
    app="$(basename "$(dirname "${compose_path}")")"
    runtime_id="${app_alias[${app}]-${app}}"
    if [[ "${states[${runtime_id}]-MISSING}" == "MISSING" ]]; then
      printf 'MISSING: %-26s expected TrueNAS app %s\n' "${app}" "${runtime_id}"
    fi
  done < <(git -C "${ROOT}" ls-files 'apps/*/compose.yml' | sort)
fi

printf '\n🔎 TrueNAS applications without a repository apps/*/compose.yml owner\n'
runtime_only=0
tab="$(printf '\t')"
while IFS="${tab}" read -r runtime_id state; do
  [[ -n "${runtime_id}" ]] || continue
  if [[ -z "${tracked_runtime_ids[${runtime_id}]-}" ]]; then
    printf 'RUNTIME-ONLY: %-26s %-12s\n' "${runtime_id}" "${state}"
    runtime_only=$((runtime_only + 1))
  fi
done < <(jq -r '.[] | [(.id // .name), (.state // "UNKNOWN")] | @tsv' "${tmp}" | sort)

if ((runtime_only == 0)); then
  printf '✅ no runtime-only TrueNAS applications detected\n'
else
  printf 'Runtime-only TrueNAS applications: %d\n' "${runtime_only}"
fi

printf '\n🔎 Traefik legacy DDNS orphan\n'
if docker ps -a   --filter 'label=com.docker.compose.project=ix-traefik'   --filter 'label=com.docker.compose.service=ddns-updater'   --format '{{.Names}}' |
  grep -Fxq 'ddns-updater' &&
  grep -Fq 'container_name: ddns-updater-legacy'     "${ROOT}/apps/traefik/compose.yml"; then
  printf '❌ Traefik legacy DDNS orphan: remove container ddns-updater; repository service is profile-gated as ddns-updater-legacy\n' >&2
else
  printf '✅ no legacy ddns-updater orphan detected for ix-traefik\n'
fi

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
probe_warnings=0

function functional_ok {
  printf '✅ %s\n' "$*"
}

function functional_fail {
  printf '❌ %s\n' "$*" >&2
  probe_failures=$((probe_failures + 1))
}

function functional_warn {
  printf '⚠️ %s\n' "$*" >&2
  probe_warnings=$((probe_warnings + 1))
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

function probe_langfuse_init_contract_if_present {
  local file="/mnt/cpool/langfuse/.env.secrets"
  local -a present=()
  local variable

  if ! app_is_present langfuse || [[ ! -r "${file}" ]]; then
    return
  fi

  while IFS= read -r variable; do
    [[ -n "${variable}" ]] && present+=("${variable}")
  done < <(
    grep -E '^LANGFUSE_INIT_[A-Z0-9_]+=.' "${file}" 2>/dev/null |
      cut -d= -f1 |
      sort -u
  )

  if (("${#present[@]}" == 0)); then
    functional_ok "Langfuse init contract: no partial bootstrap variables configured"
    return
  fi

  local -a required=(
    LANGFUSE_INIT_ORG_ID
    LANGFUSE_INIT_ORG_NAME
    LANGFUSE_INIT_PROJECT_ID
    LANGFUSE_INIT_PROJECT_NAME
    LANGFUSE_INIT_PROJECT_PUBLIC_KEY
    LANGFUSE_INIT_PROJECT_SECRET_KEY
    LANGFUSE_INIT_USER_EMAIL
    LANGFUSE_INIT_USER_NAME
    LANGFUSE_INIT_USER_PASSWORD
  )

  local -a missing=()
  for variable in "${required[@]}"; do
    if ! grep -q "^${variable}=." "${file}"; then
      missing+=("${variable}")
    fi
  done

  if (("${#missing[@]}" == 0)); then
    functional_ok "Langfuse init contract: complete headless bootstrap set configured"
  else
    functional_fail "Langfuse init contract: partial LANGFUSE_INIT_* set; remove all bootstrap variables or configure the complete set"
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

function probe_clickhouse_config_mounts_if_running {
  local container

  if ! app_is_running clickhouse; then
    return
  fi

  container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "clickhouse" || /^ix-clickhouse-clickhouse-/ { print; exit }'
  )"

  if [[ -z "${container}" ]]; then
    functional_fail "ClickHouse config mounts: container not found"
    return
  fi

  # Incident guard: a TrueNAS Custom App with an incorrectly resolved relative
  # bind source can materialize prometheus.xml as a directory instead of a file.
  local path="/etc/clickhouse-server/config.d/prometheus.xml"
  if docker exec "${container}" test -f "${path}"; then
    functional_ok "ClickHouse config mount: ${path} is a file"
  else
    functional_fail "ClickHouse config mount: ${path} is not a regular file"
  fi
}

function probe_clickhouse_admin_grant_option_if_running {
  local container
  local grants

  if ! app_is_running clickhouse; then
    return
  fi

  container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "clickhouse" || /^ix-clickhouse-clickhouse-/ { print; exit }'
  )"

  if [[ -z "${container}" ]]; then
    functional_fail "ClickHouse admin delegation: container not found"
    return
  fi

  if ! grants="$(
    docker exec "${container}" sh -c '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "SHOW GRANTS FOR clickhouse"
    ' 2>/dev/null
  )"; then
    functional_fail "ClickHouse admin delegation: SHOW GRANTS failed"
    return
  fi

  if grep -Eq 'GRANT .*ALTER.* ON [*][.][*] TO clickhouse WITH GRANT OPTION' <<<"${grants}" &&
    grep -Eq 'GRANT CREATE USER,.* TO clickhouse WITH GRANT OPTION' <<<"${grants}"; then
    functional_ok "ClickHouse admin delegation: required WITH GRANT OPTION privileges present"
  else
    functional_fail "ClickHouse admin delegation: required delegable ALTER/access-management privileges missing"
  fi
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
    return
  fi

  local grants
  if ! grants="$(
    docker exec "${container}" sh -c '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "SHOW GRANTS FOR langfuse"
    ' 2>/dev/null
  )"; then
    functional_fail "ClickHouse Langfuse contract: SHOW GRANTS failed"
    return
  fi

  if grep -Eq 'ALTER SETTINGS.*ON langfuse[.][*] TO langfuse' <<<"${grants}"; then
    functional_ok "ClickHouse Langfuse contract: database-scoped ALTER SETTINGS present"
  else
    functional_fail "ClickHouse Langfuse contract: ALTER SETTINGS ON langfuse.* missing"
  fi
}

function probe_sentry_snuba_clickhouse_if_running {
  local snuba_container
  local clickhouse_host
  local clickhouse_port
  local contract
  local clickhouse_user
  local clickhouse_database
  local table_count

  if ! app_is_running sentry; then
    printf 'SKIP: Sentry/Snuba ClickHouse contract app state is %s\n' "${states[sentry]-MISSING}"
    return
  fi

  snuba_container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "snuba-api" || /(^|-)snuba-api(-|$)/ { print; exit }'
  )"

  if [[ -z "${snuba_container}" ]]; then
    functional_fail "Sentry is RUNNING but no running Snuba API container was found"
    return
  fi

  clickhouse_host="$(
    docker inspect "${snuba_container}" \
      --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
      sed -n 's/^CLICKHOUSE_HOST=//p' |
      tail -n 1
  )"
  clickhouse_port="$(
    docker inspect "${snuba_container}" \
      --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
      sed -n 's/^CLICKHOUSE_PORT=//p' |
      tail -n 1
  )"

  clickhouse_host="${clickhouse_host:-clickhouse}"
  clickhouse_port="${clickhouse_port:-9000}"

  if docker exec "${snuba_container}" \
    python3 -c \
      'import socket, sys; s = socket.create_connection((sys.argv[1], int(sys.argv[2])), 3); s.close()' \
      "${clickhouse_host}" "${clickhouse_port}" >/dev/null 2>&1; then
    functional_ok "Sentry/Snuba -> ClickHouse TCP ${clickhouse_host}:${clickhouse_port}"
  else
    functional_fail "Sentry/Snuba -> ClickHouse TCP failed (${clickhouse_host}:${clickhouse_port})"
    return
  fi

  if ! contract="$(
    docker exec -i "${snuba_container}" python3 - 2>/dev/null <<'PY'
import os
from clickhouse_driver import Client

client = Client(
    host=os.environ.get("CLICKHOUSE_HOST", "clickhouse"),
    port=int(os.environ.get("CLICKHOUSE_PORT", "9000")),
    user=os.environ.get("CLICKHOUSE_USER", "default"),
    password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
    database=os.environ.get("CLICKHOUSE_DATABASE", "default"),
)
user, database = client.execute("SELECT currentUser(), currentDatabase()")[0]
tables = client.execute(
    "SELECT count() FROM system.tables WHERE database = currentDatabase()"
)[0][0]
print(f"{user}|{database}|{tables}")
PY
  )"; then
    functional_fail "Sentry/Snuba -> ClickHouse authenticated query failed"
    return
  fi

  IFS='|' read -r clickhouse_user clickhouse_database table_count <<<"${contract}"
  if [[ "${clickhouse_user}" != "sentry" || "${clickhouse_database}" != "sentry" ]]; then
    functional_fail "Sentry/Snuba ClickHouse identity expected sentry|sentry, got ${clickhouse_user}|${clickhouse_database}"
    return
  fi

  if [[ ! "${table_count}" =~ ^[0-9]+$ ]] || ((table_count < 1)); then
    functional_fail "Sentry/Snuba ClickHouse schema has no tables in database sentry"
    return
  fi

  functional_ok "Sentry/Snuba ClickHouse auth: user=sentry database=sentry tables=${table_count}"
}

function probe_sentry_runtime_mesh_if_running {
  local project="ix-sentry"
  local taskbroker
  local taskworker
  local relay
  local sentry_web
  local snuba_api
  local nginx
  local networks
  local relay_redis_url
  local redis_target
  local redis_hostport
  local redis_host
  local redis_port
  local redis_db
  local binding

  if ! app_is_running sentry; then
    printf 'SKIP: Sentry runtime mesh app state is %s\n' "${states[sentry]-MISSING}"
    return
  fi

  taskbroker="$(
    docker ps --filter "label=com.docker.compose.project=${project}" \
      --filter 'label=com.docker.compose.service=taskbroker' \
      --format '{{.Names}}' | head -n 1
  )"
  taskworker="$(
    docker ps --filter "label=com.docker.compose.project=${project}" \
      --filter 'label=com.docker.compose.service=sentry-taskworker' \
      --format '{{.Names}}' | head -n 1
  )"
  relay="$(
    docker ps --filter "label=com.docker.compose.project=${project}" \
      --filter 'label=com.docker.compose.service=relay' \
      --format '{{.Names}}' | head -n 1
  )"
  sentry_web="$(
    docker ps --filter "label=com.docker.compose.project=${project}" \
      --filter 'label=com.docker.compose.service=sentry-web' \
      --format '{{.Names}}' | head -n 1
  )"
  snuba_api="$(
    docker ps --filter "label=com.docker.compose.project=${project}" \
      --filter 'label=com.docker.compose.service=snuba-api' \
      --format '{{.Names}}' | head -n 1
  )"
  nginx="$(
    docker ps --filter "label=com.docker.compose.project=${project}" \
      --filter 'label=com.docker.compose.service=nginx' \
      --format '{{.Names}}' | head -n 1
  )"

  if [[ -z "${taskbroker}" || -z "${taskworker}" || -z "${relay}" || -z "${sentry_web}" || -z "${snuba_api}" || -z "${nginx}" ]]; then
    functional_fail "Sentry runtime mesh: one or more required runtime containers are missing"
    return
  fi

  networks="$(docker inspect "${taskbroker}" --format '{{json .NetworkSettings.Networks}}' 2>/dev/null)"
  if jq -e 'has("intranet") and ([keys[] | select(endswith("_sentry"))] | length > 0)' \
    <<<"${networks}" >/dev/null; then
    functional_ok "Sentry Taskbroker networks: sentry + intranet"
  else
    functional_fail "Sentry Taskbroker networks: must join sentry + intranet"
  fi

  if docker logs --since 2m "${taskbroker}" 2>&1 |
    grep -Eqi "Failed to resolve 'kafka:9092'|Host resolution failure|KafkaError.*Resolve"; then
    functional_fail "Sentry Taskbroker -> Kafka: recent DNS/resolve failure"
  else
    functional_ok "Sentry Taskbroker -> Kafka: no recent DNS/resolve failure"
  fi

  if docker exec "${taskworker}" python3 -c \
    'import socket; s=socket.create_connection(("taskbroker",50051),3); s.close()' \
    >/dev/null 2>&1; then
    functional_ok "Sentry Taskworker -> Taskbroker DNS + TCP/50051"
  else
    functional_fail "Sentry Taskworker -> Taskbroker DNS/TCP failed"
  fi

  if docker exec "${sentry_web}" python3 -c \
    'import socket; s=socket.create_connection(("kafka",9092),3); s.close()' \
    >/dev/null 2>&1; then
    functional_ok "Sentry Web -> Kafka DNS + TCP/9092"
  else
    functional_fail "Sentry Web -> Kafka DNS/TCP failed"
  fi

  if docker exec "${sentry_web}" python3 -c \
    'import socket; s=socket.create_connection(("redis",6379),3); s.close()' \
    >/dev/null 2>&1; then
    functional_ok "Sentry Web -> Redis DNS + TCP/6379"
  else
    functional_fail "Sentry Web -> Redis DNS/TCP failed"
  fi

  if docker exec "${snuba_api}" python3 -c \
    'import socket; s=socket.create_connection(("kafka",9092),3); s.close()' \
    >/dev/null 2>&1; then
    functional_ok "Snuba API -> Kafka DNS + TCP/9092"
  else
    functional_fail "Snuba API -> Kafka DNS/TCP failed"
  fi

  if docker exec "${snuba_api}" python3 -c \
    'import socket; s=socket.create_connection(("redis",6379),3); s.close()' \
    >/dev/null 2>&1; then
    functional_ok "Snuba API -> Redis DNS + TCP/6379"
  else
    functional_fail "Snuba API -> Redis DNS/TCP failed"
  fi

  networks="$(docker inspect "${relay}" --format '{{json .NetworkSettings.Networks}}' 2>/dev/null)"
  if jq -e 'has("intranet")' <<<"${networks}" >/dev/null; then
    functional_ok "Sentry Relay network: intranet attached"
  else
    functional_fail "Sentry Relay network: intranet missing"
  fi

  relay_redis_url="$(
    docker inspect "${relay}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
      sed -n 's/^RELAY_REDIS_URL=//p' |
      tail -n 1
  )"

  if [[ -z "${relay_redis_url}" ]]; then
    functional_fail "Sentry Relay -> Redis: RELAY_REDIS_URL missing"
  else
    redis_target="${relay_redis_url#*://}"
    redis_hostport="${redis_target%%/*}"
    redis_hostport="${redis_hostport##*@}"
    redis_db="${redis_target#*/}"
    redis_host="${redis_hostport%:*}"
    redis_port="${redis_hostport##*:}"

    if [[ "${redis_host}" == "redis" && "${redis_port}" == "6379" && "${redis_db}" == "3" ]]; then
      functional_ok "Sentry Relay -> Redis URL target: redis:6379/3"
    else
      functional_fail "Sentry Relay -> Redis URL target must be redis:6379/3"
    fi
  fi

  if docker logs --since 2m "${relay}" 2>&1 |
    grep -Eqi 'could not initialize redis client|failed to interact with the redis pool'; then
    functional_fail "Sentry Relay -> Redis: recent client initialization failure"
  else
    functional_ok "Sentry Relay -> Redis: no recent client initialization failure"
  fi

  networks="$(docker inspect "${nginx}" --format '{{json .NetworkSettings.Networks}}' 2>/dev/null)"
  if jq -e 'has("intranet") and ([keys[] | select(endswith("_sentry"))] | length > 0)' \
    <<<"${networks}" >/dev/null; then
    functional_ok "Sentry NGINX networks: intranet + sentry"
  else
    functional_fail "Sentry NGINX networks: must join intranet + sentry"
  fi

  if docker exec "${nginx}" sh -c 'nc -z -w 3 sentry-web 9000' >/dev/null 2>&1; then
    functional_ok "Sentry NGINX -> Web DNS + TCP/9000"
  else
    functional_fail "Sentry NGINX -> Web DNS/TCP failed"
  fi

  if docker exec "${nginx}" sh -c 'nc -z -w 3 relay 3000' >/dev/null 2>&1; then
    functional_ok "Sentry NGINX -> Relay DNS + TCP/3000"
  else
    functional_fail "Sentry NGINX -> Relay DNS/TCP failed"
  fi

  binding="$(
    docker inspect "${nginx}" \
      --format '{{with (index .NetworkSettings.Ports "80/tcp")}}{{range .}}{{println .HostIp ":" .HostPort}}{{end}}{{end}}' \
      2>/dev/null |
      tr -d ' '
  )"
  if grep -Fxq '172.17.0.24:9005' <<<"${binding}"; then
    functional_ok "Sentry NGINX host publish: 172.17.0.24:9005 -> 80/tcp active"
  else
    functional_fail "Sentry NGINX host publish is not active on 172.17.0.24:9005"
  fi

  if docker exec "${nginx}" wget -qO- http://127.0.0.1/_health/ 2>/dev/null |
    grep -q 'ok'; then
    functional_ok "Sentry NGINX -> Web health"
  else
    functional_fail "Sentry NGINX -> Web health failed"
  fi
}

function probe_fastapi_sample_sentry_if_running {
  local container
  local env

  if ! app_is_running sample; then
    printf 'SKIP: FastAPI Sample Sentry app state is %s\n' "${states[sample]-MISSING}"
    return
  fi

  container="$(
    docker ps --filter 'label=com.docker.compose.project=ix-sample' \
      --filter 'label=com.docker.compose.service=fastapi-sample' \
      --format '{{.Names}}' | head -n 1
  )"
  if [[ -z "${container}" ]]; then
    container="$(docker ps --format '{{.Names}}' | awk '$0 == "fastapi-sample" { print; exit }')"
  fi

  if [[ -z "${container}" ]]; then
    functional_fail "FastAPI Sample Sentry: runtime container not found"
    return
  fi

  env="$(docker inspect "${container}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null)"

  if grep -q '^SENTRY_LOCAL_DSN=.' <<<"${env}"; then
    functional_ok "FastAPI Sample Sentry: SENTRY_LOCAL_DSN configured"
  else
    functional_fail "FastAPI Sample Sentry: SENTRY_LOCAL_DSN missing"
  fi

  if grep -Fxq 'SENTRY_ENVIRONMENT=homelab' <<<"${env}"; then
    functional_ok "FastAPI Sample Sentry: environment=homelab"
  else
    functional_fail "FastAPI Sample Sentry: SENTRY_ENVIRONMENT must be homelab"
  fi

  if grep -Fxq 'SENTRY_AI_INTEGRATIONS_ENABLED=true' <<<"${env}"; then
    functional_ok "FastAPI Sample Sentry: MCP/AI SDK integrations enabled"
  else
    functional_fail "FastAPI Sample Sentry: SENTRY_AI_INTEGRATIONS_ENABLED must be true"
  fi

  if docker exec "${container}" python3 -c \
    'import socket; s=socket.create_connection(("172.17.0.24",9005),3); s.close()' \
    >/dev/null 2>&1; then
    functional_ok "FastAPI Sample -> Sentry edge TCP/9005"
  else
    functional_fail "FastAPI Sample -> Sentry edge TCP/9005 failed"
  fi

  if docker exec "${container}" python3 -c \
    'import urllib.request; urllib.request.urlopen("http://172.17.0.24:9005/_health/",timeout=3).read()' \
    >/dev/null 2>&1; then
    functional_ok "FastAPI Sample -> Sentry edge health"
  else
    functional_fail "FastAPI Sample -> Sentry edge health failed"
  fi

  if [[ -n "${SENTRY_ACCESS_TOKEN:-}" ]]; then
    local sentry_api_body
    local sentry_api_status

    sentry_api_body="$(mktemp)"
    sentry_api_status="$(
      curl \
        --silent \
        --show-error \
        --max-time 5 \
        --output "${sentry_api_body}" \
        --write-out '%{http_code}' \
        --header "Authorization: Bearer ${SENTRY_ACCESS_TOKEN}" \
        http://172.17.0.24:9005/api/0/organizations/ || true
    )"

    if [[ "${sentry_api_status}" == "200" ]] && jq -e 'type == "array"' "${sentry_api_body}" >/dev/null 2>&1; then
      functional_ok "Sentry MCP API token: direct LAN /api/0/organizations/ accepted"
    elif [[ "${sentry_api_status}" == "401" || "${sentry_api_status}" == "403" ]]; then
      functional_fail "Sentry MCP API token: rejected by direct LAN API (HTTP ${sentry_api_status}); use a User Auth Token with inspect scopes"
    else
      functional_fail "Sentry MCP API token: direct LAN API returned unexpected HTTP ${sentry_api_status}"
    fi

    rm -f "${sentry_api_body}"

    if [[ -n "${CF_ACCESS_CLIENT_ID:-}" || -n "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
      local sentry_public_body
      local sentry_public_headers
      local sentry_public_status

      if [[ -z "${CF_ACCESS_CLIENT_ID:-}" || -z "${CF_ACCESS_CLIENT_SECRET:-}" ]]; then
        functional_fail "Sentry public Access: CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET must be provided together"
      else
        sentry_public_body="$(mktemp)"
        sentry_public_headers="$(mktemp)"
        sentry_public_status="$(
          curl \
            --silent \
            --show-error \
            --max-time 8 \
            --output "${sentry_public_body}" \
            --dump-header "${sentry_public_headers}" \
            --write-out '%{http_code}' \
            --header "Authorization: Bearer ${SENTRY_ACCESS_TOKEN}" \
            --header "CF-Access-Client-Id: ${CF_ACCESS_CLIENT_ID}" \
            --header "CF-Access-Client-Secret: ${CF_ACCESS_CLIENT_SECRET}" \
            https://sentry.albandrieu.com/api/0/organizations/ || true
        )"

        if [[ "${sentry_public_status}" == "200" ]] && jq -e 'type == "array"' "${sentry_public_body}" >/dev/null 2>&1; then
          functional_ok "Sentry public Access: Cloudflare Service Auth + Sentry User Auth accepted"
        elif [[ "${sentry_public_status}" == "302" ]] && grep -Eqi 'cloudflareaccess\.com/cdn-cgi/access/login' "${sentry_public_headers}"; then
          functional_fail "Sentry public Access: Cloudflare Service Auth policy did not accept the service token"
        elif [[ "${sentry_public_status}" == "401" || "${sentry_public_status}" == "403" ]]; then
          functional_fail "Sentry public Access: Cloudflare passed but Sentry rejected the User Auth Token (HTTP ${sentry_public_status})"
        else
          functional_fail "Sentry public Access: unexpected HTTP ${sentry_public_status}"
        fi

        rm -f "${sentry_public_body}" "${sentry_public_headers}"
      fi
    else
      printf 'SKIP: Sentry public Cloudflare Service Auth check (CF_ACCESS_CLIENT_ID/SECRET not exported)\n'
    fi
  else
    printf 'SKIP: Sentry MCP API token check (SENTRY_ACCESS_TOKEN is not exported)\n'
  fi
}

function probe_ntopng_clickhouse_contract_if_running {
  local clickhouse_container
  local ntopng_container
  local secret_file="/mnt/cpool/ntopng/.env.secrets"
  local password
  local edition
  local metadata
  local grants

  if ! app_is_running ntopng; then
    printf 'SKIP: ntopng ClickHouse contract app state is %s\n' "${states[ntopng]-MISSING}"
    return
  fi

  if ! app_is_running clickhouse; then
    functional_fail "ntopng ClickHouse contract: ClickHouse app is not RUNNING"
    return
  fi

  if [[ ! -r "${secret_file}" ]]; then
    functional_fail "ntopng ClickHouse contract: ${secret_file} is not readable"
    return
  fi

  password="$(sed -n 's/^NTOPNG_CLICKHOUSE_PASSWORD=//p' "${secret_file}" | tail -n 1)"
  password="$(normalize_env_value "${password}")"
  if [[ ! "${password}" =~ ^[0-9a-fA-F]{64}$ ]]; then
    functional_fail "ntopng ClickHouse contract: NTOPNG_CLICKHOUSE_PASSWORD must be 64 hexadecimal characters"
    return
  fi

  ntopng_container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "ntopng" || /^ix-ntopng-ntopng-/ { print; exit }'
  )"

  if [[ -z "${ntopng_container}" ]]; then
    functional_fail "ntopng ClickHouse contract: ntopng container not found"
    return
  fi

  if docker inspect "${ntopng_container}" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
    grep -q '^NTOPNG_CLICKHOUSE_PASSWORD='; then
    functional_fail "ntopng ClickHouse contract: password exposed in Docker Config.Env"
    return
  else
    functional_ok "ntopng ClickHouse contract: password absent from Docker Config.Env"
  fi

  if docker exec "${ntopng_container}" test -s /run/secrets/ntopng_runtime_env 2>/dev/null; then
    functional_ok "ntopng ClickHouse contract: runtime secret mounted"
  else
    functional_fail "ntopng ClickHouse contract: runtime secret mount missing or empty"
    return
  fi

  if docker exec "${ntopng_container}" test -s /etc/ntopng.license 2>/dev/null; then
    functional_ok "ntopng ClickHouse contract: Enterprise license file mounted"
  else
    functional_fail "ntopng ClickHouse contract: /etc/ntopng.license missing or empty"
    return
  fi

  if ! edition="$(
    docker exec "${ntopng_container}" ntopng -V 2>&1 |
      sed -n 's/^Edition:[[:space:]]*//p' |
      head -n 1
  )"; then
    functional_fail "ntopng ClickHouse contract: unable to determine ntopng edition"
    return
  fi

  case "${edition}" in
    Enterprise\ M*|Enterprise\ L*|Enterprise\ XL*|Enterprise\ XXL*)
      functional_ok "ntopng ClickHouse contract: supported Enterprise edition detected"
      ;;
    *)
      functional_fail "ntopng ClickHouse contract: Enterprise M-or-higher edition required"
      return
      ;;
  esac

  if docker exec "${ntopng_container}" sh -c '
    test -f /run/nabla-ntopng.conf &&
      test "$(stat -c %a /run/nabla-ntopng.conf)" = 600
  ' 2>/dev/null; then
    functional_ok "ntopng ClickHouse contract: ephemeral config is a mode-0600 file"
  else
    functional_fail "ntopng ClickHouse contract: ephemeral config missing or not mode 0600"
    return
  fi

  if docker top "${ntopng_container}" -eo args 2>/dev/null |
    grep -Fq -f <(printf '%s\n' "${password}"); then
    functional_fail "ntopng ClickHouse contract: password is exposed in process argv"
    return
  else
    functional_ok "ntopng ClickHouse contract: password absent from process argv"
  fi

  clickhouse_container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "clickhouse" || /^ix-clickhouse-clickhouse-/ { print; exit }'
  )"

  if [[ -z "${clickhouse_container}" ]]; then
    functional_fail "ntopng ClickHouse contract: ClickHouse container not found"
    return
  fi

  if ! metadata="$(
    docker exec "${clickhouse_container}" sh -c '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "
          SELECT concat(
            toString((SELECT count() FROM system.databases WHERE name = '"'"'ntopng'"'"')),
            '"'"'|'"'"',
            toString((SELECT count() FROM system.users WHERE name = '"'"'ntopng'"'"'))
          )
        "
    ' 2>/dev/null
  )"; then
    functional_fail "ntopng ClickHouse contract: metadata query failed"
    return
  fi

  if [[ "${metadata}" != "1|1" ]]; then
    functional_fail "ntopng ClickHouse contract: expected dedicated database/user ntopng (got ${metadata})"
    return
  fi

  if ! grants="$(
    docker exec "${clickhouse_container}" sh -c '
      clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "SHOW GRANTS FOR ntopng"
    ' 2>/dev/null
  )"; then
    functional_fail "ntopng ClickHouse contract: SHOW GRANTS failed"
    return
  fi

  if grep -F ' ON *.* TO ntopng' <<<"${grants}" |
    grep -Fvq 'GRANT USAGE ON *.* TO ntopng'; then
    functional_fail "ntopng ClickHouse contract: global *.* privileges are forbidden"
    return
  fi

  if grep -Eq 'GRANT ALL( PRIVILEGES)? ON ntopng[.][*] TO ntopng' <<<"${grants}"; then
    functional_fail "ntopng ClickHouse contract: ALL ON ntopng.* is broader than required"
    return
  fi

  local grant_check
  if ! grant_check="$(
    NTOPNG_CLICKHOUSE_PASSWORD="${password}" docker exec \
      -e NTOPNG_CLICKHOUSE_PASSWORD \
      "${clickhouse_container}" sh -c '
        clickhouse-client \
          --user ntopng \
          --password "$NTOPNG_CLICKHOUSE_PASSWORD" \
          --database ntopng \
          --query "CHECK GRANT SELECT, INSERT, TRUNCATE, CREATE TABLE, DROP TABLE, ALTER ON ntopng.*"
      ' 2>/dev/null
  )"; then
    functional_fail "ntopng ClickHouse contract: dedicated credentials or CHECK GRANT failed"
    return
  fi

  if [[ "${grant_check}" == "1" ]]; then
    functional_ok "ntopng ClickHouse contract: required database-scoped DML/DDL grants present"
  else
    functional_fail "ntopng ClickHouse contract: required database-scoped DML/DDL grants missing"
  fi
}

function probe_langfuse_worker_clickhouse_credentials_if_running {
  local container

  if ! app_is_running langfuse; then
    return
  fi

  container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "langfuse-worker" || /^ix-langfuse-langfuse-worker-/ { print; exit }'
  )"

  if [[ -z "${container}" ]]; then
    functional_fail "Langfuse worker ClickHouse auth: container not found"
    return
  fi

  if docker exec "${container}" node -e '
    const user = process.env.CLICKHOUSE_USER;
    const password = process.env.CLICKHOUSE_PASSWORD;
    const database = process.env.CLICKHOUSE_DB || "default";
    const baseUrl = process.env.CLICKHOUSE_URL;

    if (!user || !password || !baseUrl) {
      process.stderr.write("missing ClickHouse runtime environment\n");
      process.exit(1);
    }

    const query = encodeURIComponent("SELECT concat(currentUser(), '\''|'\'', currentDatabase())");
    const url =
      baseUrl.replace(/\/$/, "") +
      "/?database=" +
      encodeURIComponent(database) +
      "&query=" +
      query;
    const authorization =
      "Basic " + Buffer.from(user + ":" + password).toString("base64");

    fetch(url, { headers: { Authorization: authorization } })
      .then(async (response) => {
        const body = (await response.text()).trim();
        if (!response.ok) {
          process.stderr.write("ClickHouse HTTP " + response.status + "\n");
          process.exit(1);
        }
        if (body !== user + "|" + database) {
          process.stderr.write("unexpected ClickHouse identity: " + body + "\n");
          process.exit(1);
        }
      })
      .catch((error) => {
        process.stderr.write(String(error) + "\n");
        process.exit(1);
      });
  ' >/dev/null 2>&1; then
    functional_ok "Langfuse worker ClickHouse auth: runtime credentials accepted"
  else
    functional_fail "Langfuse worker ClickHouse auth: effective CLICKHOUSE_USER/PASSWORD/DB rejected"
  fi
}


function probe_pyroscope_fastapi_profile {
  local pyroscope_container
  local fastapi_container
  local fastapi_env
  local now_ms
  local start_ms
  local labels
  local series
  local render

  pyroscope_container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "pyroscope" { print; exit }'
  )"

  if [[ -z "${pyroscope_container}" ]]; then
    functional_fail "Pyroscope runtime: repository-managed container pyroscope is not running"
    return
  fi

  if ! curl --fail --silent --show-error --max-time 8     http://172.17.0.24:4040/ready >/dev/null; then
    functional_fail "Pyroscope runtime: /ready is not HTTP 200"
    return
  fi
  functional_ok "Pyroscope runtime: /ready HTTP 200"

  fastapi_container="$(
    docker ps --format '{{.Names}}' |
      awk '$0 == "fastapi-sample" { print; exit }'
  )"

  if [[ -z "${fastapi_container}" ]]; then
    printf 'SKIP: Pyroscope FastAPI profile contract (fastapi-sample container is not running)\n'
    return
  fi

  fastapi_env="$(docker inspect "${fastapi_container}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null)"
  if grep -Fxq 'PYROSCOPE_SERVER_ADDRESS=http://172.17.0.24:4040' <<<"${fastapi_env}"; then
    functional_ok "FastAPI Sample -> Pyroscope endpoint configured"
  else
    functional_fail "FastAPI Sample -> Pyroscope endpoint must be http://172.17.0.24:4040"
    return
  fi

  now_ms="$(date +%s)000"
  start_ms="$((now_ms - 900000))"

  if ! labels="$(
    curl --fail --silent --show-error --max-time 8       --header 'Content-Type: application/json'       --data "{
        \"start\": ${start_ms},
        \"end\": ${now_ms},
        \"name\": \"service_name\"
      }"       http://172.17.0.24:4040/querier.v1.QuerierService/LabelValues
  )"; then
    functional_fail "Pyroscope query: service_name LabelValues request failed"
    return
  fi

  if jq -e '.names | index("fastapi-sample") != null' <<<"${labels}" >/dev/null; then
    functional_ok "Pyroscope query: service_name=fastapi-sample observed in last 15m"
  else
    functional_fail "Pyroscope query: service_name=fastapi-sample absent in last 15m"
    return
  fi

  if ! series="$(
    curl --fail --silent --show-error --max-time 8       --header 'Content-Type: application/json'       --header 'Accept: */*; allow-utf8-labelnames=true'       --data "{
        \"start\": ${start_ms},
        \"end\": ${now_ms},
        \"matchers\": [\"{service_name=\\\"fastapi-sample\\\"}\"],
        \"labelNames\": [\"service_name\", \"__profile_type__\", \"__name__\"]
      }"       http://172.17.0.24:4040/querier.v1.QuerierService/Series
  )"; then
    functional_fail "Pyroscope query: FastAPI profile Series request failed"
    return
  fi

  if jq -e '
    any(
      .labelsSet[]?.labels[]?;
      .name == "__profile_type__" and
      .value == "process_cpu:cpu:nanoseconds:cpu:nanoseconds"
    )
  ' <<<"${series}" >/dev/null; then
    functional_ok "Pyroscope query: FastAPI CPU profile series present"
  else
    functional_fail "Pyroscope query: FastAPI CPU profile series missing"
    return
  fi

  if ! render="$(
    curl --fail --silent --show-error --max-time 8 --get       --data-urlencode 'query=process_cpu:cpu:nanoseconds:cpu:nanoseconds{service_name="fastapi-sample"}'       --data-urlencode 'from=now-15m'       http://172.17.0.24:4040/pyroscope/render
  )"; then
    functional_fail "Pyroscope query: FastAPI CPU flamegraph render failed"
    return
  fi

  if jq -e '
    (.flamebearer.names | length) > 0 and
    any(.timeline.samples[]?; . > 0)
  ' <<<"${render}" >/dev/null; then
    functional_ok "Pyroscope query: FastAPI CPU flamegraph contains recent samples"
  else
    functional_fail "Pyroscope query: FastAPI CPU flamegraph has no recent samples"
  fi
}



function probe_openrag_runtime_if_present {
  local backend="openrag-backend"
  local frontend="openrag-frontend"
  local collective

  if ! app_is_present openrag; then
    printf 'SKIP: OpenRAG runtime app is MISSING\n'
    return
  fi

  if ! docker ps --format '{{.Names}}' | grep -Fxq "${backend}"; then
    functional_fail "OpenRAG backend: container is not running (TrueNAS state ${states[openrag]-UNKNOWN})"
    return
  fi

  if ! docker ps --format '{{.Names}}' | grep -Fxq "${frontend}"; then
    functional_fail "OpenRAG frontend: container is not running (TrueNAS state ${states[openrag]-UNKNOWN})"
    return
  fi

  if docker inspect "${frontend}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
    grep -Fxq 'LANGFLOW_HOST=langflow'; then
    functional_ok "OpenRAG frontend: shared Langflow hostname configured"
  else
    functional_fail "OpenRAG frontend: LANGFLOW_HOST must be langflow; stale/default openrag-langflow keeps collective health degraded"
  fi

  if docker inspect "${frontend}" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null |
    grep -Fxq 'LANGFLOW_HEALTH_PATH=/health_check'; then
    functional_ok "OpenRAG frontend: Langflow health path configured"
  else
    functional_fail "OpenRAG frontend: LANGFLOW_HEALTH_PATH must be /health_check"
  fi

  if docker exec "${backend}" curl --fail --silent --show-error --max-time 8     http://127.0.0.1:8000/health >/dev/null; then
    functional_ok "OpenRAG backend: /health HTTP 200"
  else
    functional_fail "OpenRAG backend: /health failed"
  fi

  if docker exec "${backend}" curl --fail --silent --show-error --max-time 8     http://127.0.0.1:8000/search/health >/dev/null; then
    functional_ok "OpenRAG backend: OpenSearch readiness HTTP 200"
  else
    functional_fail "OpenRAG backend: /search/health failed; verify opensearch DNS/TLS/password"
  fi

  if collective="$(curl --fail --silent --show-error --max-time 8     http://172.17.0.24:31060/health/collective_health 2>/dev/null)" &&
    jq -e '
      .status == "ok" and
      .pods.backend.alive == true and
      .pods.langflow.alive == true
    ' <<<"${collective}" >/dev/null; then
    functional_ok "OpenRAG frontend: collective backend + Langflow health HTTP 200"
  else
    functional_fail "OpenRAG frontend: collective health failed; inspect backend/Langflow resolution before redeploy loops"
  fi

  if docker exec "${backend}" sh -lc '
    url="${DOCLING_SERVE_URL:-http://host.docker.internal:5001}"
    curl --fail --silent --show-error --max-time 8 "${url%/}/health" >/dev/null
  ' >/dev/null 2>&1; then
    functional_ok "OpenRAG ingestion: Docling health reachable"
  else
    functional_warn "OpenRAG ingestion: Docling is not reachable; UI/search may run but document ingestion is incomplete"
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
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets SENTRY_SECRET_KEY
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets SENTRY_DB_PASSWORD
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets SENTRY_REDIS_PASSWORD
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets REDIS_PASSWORD
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets RELAY_REDIS_URL
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets RELAY_ID
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets RELAY_PUBLIC_KEY
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets RELAY_SECRET_KEY
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets CLICKHOUSE_PASSWORD
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets CLICKHOUSE_READONLY_PASSWORD
probe_secret_if_present sentry "Sentry secrets" /mnt/cpool/sentry/.env.secrets CLICKHOUSE_TRACE_PASSWORD
probe_secret_if_present sentry "Sentry migrator secrets" /mnt/cpool/sentry/.env.migrator.secrets CLICKHOUSE_PASSWORD
probe_secret_if_present sentry "Sentry migrator secrets" /mnt/cpool/sentry/.env.migrator.secrets CLICKHOUSE_READONLY_PASSWORD
probe_secret_if_present sentry "Sentry migrator secrets" /mnt/cpool/sentry/.env.migrator.secrets CLICKHOUSE_TRACE_PASSWORD
probe_secret_if_present scrutiny "Scrutiny secrets" /mnt/cpool/scrutiny/.env.secrets SCRUTINY_WEB_INFLUXDB_TOKEN
probe_secret_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_PASSWORD_SECRET
probe_secret_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_ROOT_PASSWORD_SHA2
probe_secret_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_MONGODB_URI
probe_secret_min_length_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_PASSWORD_SECRET 16
probe_secret_regex_if_present graylog "Graylog secrets" /mnt/cpool/graylog/.env.secrets GRAYLOG_ROOT_PASSWORD_SHA2 '[0-9a-fA-F]{64}'
probe_legacy_secret_name "Homarr secrets" /mnt/cpool/homarr/.env.secrets HOMARR_ENCRYPTION_KEY SECRET_ENCRYPTION_KEY
probe_langfuse_init_contract_if_present

printf '\n🔎 functional service checks\n'
probe_http_if_running bichon "Bichon HTTP/15630" "http://172.17.0.24:15630/"
probe_log_absence_if_running bichon "Bichon OAuth2 encryption" bichon "Decryption failed, likely due to incorrect encryption key or corrupted data"
probe_http_if_running gatus "Gatus health" "http://172.17.0.24:8085/health"
probe_http_if_running influxdb "InfluxDB health" "http://127.0.0.1:31055/health"
probe_http_if_running graylog "Graylog load-balancer status" "http://172.17.0.24:9003/api/system/lbstatus"
probe_pyroscope_fastapi_profile
probe_http_if_running homarr "Homarr HTTP/30100" "http://172.17.0.24:30100/"
probe_http_if_running langflow "Langflow health_check" "http://172.17.0.24:7860/health_check"
probe_openrag_runtime_if_present
probe_http_if_running clickhouse "ClickHouse HTTP/ping" "http://172.17.0.24:8123/ping"
probe_clickhouse_runtime_if_running
probe_clickhouse_config_mounts_if_running
probe_clickhouse_admin_grant_option_if_running
probe_clickhouse_langfuse_contract_if_present
probe_sentry_snuba_clickhouse_if_running
probe_sentry_runtime_mesh_if_running
probe_fastapi_sample_sentry_if_running
probe_ntopng_clickhouse_contract_if_running
probe_langfuse_worker_clickhouse_credentials_if_running
probe_http_if_running sentry "Sentry web health" "http://172.17.0.24:9005/_health/"
probe_http_if_running langfuse "Langfuse web + database" "http://172.17.0.24:3000/api/public/health?failIfDatabaseUnavailable=true"
probe_http_if_running langfuse "Langfuse worker" "http://127.0.0.1:3030/api/health"

probe_intranet_tcp_if_running mongo "MongoDB internal service" mongo 27017
probe_intranet_tcp_if_running redis "Redis internal service" redis 6379
probe_intranet_tcp_if_running kafka "Kafka internal service" kafka 9092
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
  printf '\n❌ functional verification failed: %d probe(s) failed, %d warning(s)\n' \
    "${probe_failures}" "${probe_warnings}" >&2
  exit 1
fi

if ((probe_warnings > 0)); then
  printf '\n⚠️ functional verification passed with %d warning(s)\n' "${probe_warnings}"
else
  printf '\n✅ functional verification passed\n'
fi
