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
probe_langfuse_init_contract_if_present

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
probe_clickhouse_config_mounts_if_running
probe_clickhouse_admin_grant_option_if_running
probe_clickhouse_langfuse_contract_if_present
probe_ntopng_clickhouse_contract_if_running
probe_langfuse_worker_clickhouse_credentials_if_running
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
