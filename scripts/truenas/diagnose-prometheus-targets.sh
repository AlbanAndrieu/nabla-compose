#!/usr/bin/env bash
set -euo pipefail

STRICT=false
case "${1:-}" in
  --check)
    STRICT=true
    ;;
  "") ;;
  *)
    printf 'usage: %s [--check]\n' "$0" >&2
    exit 2
    ;;
esac

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"

CONTAINER="${PROMETHEUS_CONTAINER:-prometheus}"
CONFIG="${PROMETHEUS_CONFIG:-${ROOT}/apps/prometheus/prometheus.yml}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

failures=0
warn_or_fail() {
  if [[ "${STRICT}" == true ]]; then
    printf '❌ %s\n' "$*" >&2
    failures=$((failures + 1))
  else
    printf '⚠️  %s\n' "$*" >&2
  fi
}

for command in curl docker grep jq sha256sum sort comm awk sed stat; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
done
[[ -f "${CONFIG}" ]] || {
  printf 'ERROR: Prometheus config not found: %s\n' "${CONFIG}" >&2
  exit 1
}

# A RUNNING TrueNAS App can still contain a restarting Prometheus
# container. In that state, docker exec/promtool and target HTTP cannot
# provide useful evidence; summarize crash categories instead of repeating
# network failures or dumping secrets from raw logs.
runtime_status="$(docker inspect "${CONTAINER}" --format '{{.State.Status}}' 2>/dev/null || true)"
if [[ "${runtime_status}" != running ]]; then
  case "${runtime_status}" in
    restarting|exited|dead|created) ;;
    *) runtime_status='unknown' ;;
  esac
  printf '❌ Prometheus runtime=%s (config, permissions or startup error)\n' "${runtime_status}" >&2
  # Allowlisted metadata only: .State JSON can include sensitive Health.Log.Output.
  runtime_meta="$(docker inspect "${CONTAINER}" --format \
    'exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' \
    2>/dev/null || true)"
  if [[ "${runtime_meta}" =~ ^exit=[0-9]+[[:space:]]oom=(true|false)[[:space:]]restarts=[0-9]+$ ]]; then
    printf '  runtime %s\n' "${runtime_meta}" >&2
    if [[ "${runtime_meta}" == *'oom=true'* ]]; then
      printf '  likely cause: container OOMKilled; check resource limits privately\n' >&2
    fi
  fi
  # Metadata only; never read or modify TSDB blocks or the WAL.
  for storage_path in "${CONFIG}" /mnt/cpool/prometheus/data; do
    if [[ -e "${storage_path}" ]]; then
      stat -c '  host metadata: mode=%a uid=%u gid=%g type=%F' -- \
        "${storage_path}" >&2 || true
    else
      printf '  host metadata: expected path absent\n' >&2
    fi
  done
  # A repaired host mode cannot establish the bound path or effective access.
  # Do not print raw Docker mount sources or inspect environment variables.
  expected_source="$(cd -- "$(dirname -- "${CONFIG}")" && pwd -P)"
  mount_source="$(docker inspect "${CONTAINER}" --format \
    '{{range .Mounts}}{{if eq .Destination "/etc/prometheus"}}{{println .Source}}{{end}}{{end}}' 2>/dev/null || true)"
  if [[ -n "${mount_source}" && "${mount_source}" == "${expected_source}" ]]; then
    printf '  config_bind=match\n' >&2
  elif [[ -n "${mount_source}" ]]; then
    printf '  config_bind=mismatch (do not alter unrelated mount)\n' >&2
  else
    printf '  config_bind=unverified\n' >&2
  fi
  runtime_user="$(docker inspect "${CONTAINER}" --format \
    '{{.Config.User}}' 2>/dev/null || true)"
  if [[ "${runtime_user}" == "568:568" ]]; then
    printf '  container_identity=expected_568:568\n' >&2
  else
    printf '  container_identity=unexpected_or_unverified\n' >&2
  fi
  # A user namespace can remap container UID 568 to a different host UID.
  # Inspect only non-secret Docker security selectors (no Env or full JSON).
  userns_mode="$(docker inspect "${CONTAINER}" --format \
    '{{.HostConfig.UsernsMode}}' 2>/dev/null || true)"
  case "${userns_mode}" in
    host) printf '  docker_userns=host\n' >&2 ;;
    "") printf '  docker_userns=daemon_default_or_disabled\n' >&2 ;;
    *) printf '  docker_userns=custom\n' >&2 ;;
  esac
  if command -v docker >/dev/null 2>&1; then
    daemon_security="$(docker info --format '{{json .SecurityOptions}}' 2>/dev/null || true)"
    if [[ "${daemon_security}" == *userns* ]]; then
      printf '  daemon_userns=enabled\n' >&2
    elif [[ -n "${daemon_security}" ]]; then
      printf '  daemon_userns=not_advertised\n' >&2
    else
      printf '  daemon_userns=unverified\n' >&2
    fi
  fi
  if (( EUID == 0 )) && command -v setpriv >/dev/null 2>&1; then
    if setpriv --reuid 568 --regid 568 --clear-groups \
      /usr/bin/test -r "${CONFIG}"; then
      printf '  effective_host_config_read=ok\n' >&2
    else
      printf '  effective_host_config_read=denied\n' >&2
    fi
  else
    printf '  effective_host_config_read=unverified (sudo/setpriv required)\n' >&2
  fi
  # Config loading can fail on rules while mentioning --config.file in logs.
  # Read-only metadata and UID/GID 568 effective tests; no YAML contents.
  if (( EUID == 0 )) && command -v find >/dev/null 2>&1 \
      && command -v setpriv >/dev/null 2>&1; then
    rule_total=0
    rule_denied=0
    rule_dirs=0
    rule_dirs_denied=0
    if [[ -d "${expected_source}/rules" ]]; then
      while IFS= read -r -d '' rules_file; do
        rule_total=$((rule_total + 1))
        if ! setpriv --reuid 568 --regid 568 --clear-groups \
            /usr/bin/test -r "$rules_file"; then
          rule_denied=$((rule_denied + 1))
        fi
      done < <(find "${expected_source}/rules" -type f \
        \( -name '*.yml' -o -name '*.yaml' \) -print0 2>/dev/null || true)
      while IFS= read -r -d '' rules_dir; do
        rule_dirs=$((rule_dirs + 1))
        if ! setpriv --reuid 568 --regid 568 --clear-groups \
            /usr/bin/test -x "$rules_dir"; then
          rule_dirs_denied=$((rule_dirs_denied + 1))
        fi
      done < <(find "${expected_source}/rules" -type d -print0 2>/dev/null || true)
    fi
    printf '  rule_tree_access: files=%d denied=%d dirs=%d untraversable=%d\n' \
      "$rule_total" "$rule_denied" "$rule_dirs" "$rule_dirs_denied" >&2
    if ((rule_denied > 0 || rule_dirs_denied > 0)); then
      printf '  evidence=secondary_rules_access_denied_on_host\n' >&2
    fi
  else
    printf '  rule_tree_access=unverified (sudo/find/setpriv required)\n' >&2
  fi
  # chmod/chgrp update ctime, not mtime. Separate new log evidence from
  # stale errors in the historical 80-line Docker restart-loop tail.
  if command -v date >/dev/null 2>&1; then
    changed_epoch="$(stat -c '%Z' -- "${CONFIG}" 2>/dev/null || true)"
    if [[ "${changed_epoch}" =~ ^[0-9]+$ ]]; then
      changed_at="$(date -u -d "@${changed_epoch}" +'%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || true)"
      if [[ -n "${changed_at}" ]]; then
        docker logs --since "${changed_at}" --tail 80 "${CONTAINER}" 2>&1 |
          awk '{
              t=tolower($0); count++;
              if (t ~ /permission denied|operation not permitted/) permissions++;
              if (t ~ /open[[:space:]]+\/etc\/prometheus\/prometheus[.]yml/ && t ~ /permission denied/) config++;
              if (t ~ /\/etc\/prometheus\/rules\// && t ~ /permission denied/) rules++;
              if (t ~ /wal.*permission denied|tsdb.*permission denied|storage.*permission denied/) storage++;
            } END {
              printf "  since_config_change: sample=%d permissions=%d config=%d rules=%d storage=%d\n",
                count, permissions, config, rules, storage;
              if (count == 0)
                print "  evidence=not_enough_new_logs_after_config_change";
              else if (config > 0)
                print "  evidence=continuing_config_permission_denied";
              else if (permissions > 0)
                print "  evidence=other_permission_denied_after_config_change";
            }' >&2 || true
      fi
    fi
  fi
  if docker inspect "${CONTAINER}" >/dev/null 2>&1; then
    docker logs --tail 80 "${CONTAINER}" 2>&1 |
      awk -v denied_rules="${rule_denied:-0}" '{
          t=tolower($0); lines++;
          if (t ~ /permission denied|operation not permitted/) permissions++;
          if (t ~ /open[[:space:]]+\/etc\/prometheus\/prometheus[.]yml/ && t ~ /permission denied/) config_unreadable++;
          if (t ~ /\/etc\/prometheus\/rules\// && t ~ /permission denied/) rules_unreadable++;
          if (t ~ /yaml|parse error|invalid config|unknown field/) configuration++;
          if (t ~ /tsdb|corrupt|wal|storage/) storage++;
          if (t ~ /out of memory|oom/) memory++;
        } END {
          printf "  recent log categories: sample=%d permissions=%d parse=%d storage=%d oom=%d\n",
            lines,permissions,configuration,storage,memory;
          if (denied_rules > 0)
            printf "  root_cause=prometheus_rules_permission_denied (unreadable_host_rules=%d; scoped repair only)\n", denied_rules;
          else if (config_unreadable > 0)
            print "  root_cause=prometheus_config_permission_denied (check 568:568, parent traversal and ZFS ACL)";
          else if (rules_unreadable > 0)
            print "  root_cause=prometheus_rules_permission_denied (check rules directory and per-file 568:568 access)"
        }' >&2 || true
  fi
  printf '  Review privately: docker inspect %s --format "status={{.State.Status}} exit={{.State.ExitCode}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}"\n' "${CONTAINER}" >&2
  printf '  Preserve /mnt/cpool/prometheus/data; do not redeploy until crash cause is known.\n' >&2
  exit 1
fi

echo '=== Prometheus config drift ==='
host_hash="$(sha256sum "${CONFIG}" | awk '{print $1}')"
if container_config="$(docker exec "${CONTAINER}" sh -c 'cat /etc/prometheus/prometheus.yml' 2>/dev/null)"; then
  container_hash="$(printf '%s\n' "${container_config}" | sha256sum | awk '{print $1}')"
  printf 'host      sha256=%s\n' "${host_hash}"
  printf 'container sha256=%s\n' "${container_hash}"
  if [[ "${host_hash}" == "${container_hash}" ]]; then
    echo '✅ host and mounted Prometheus config match'
  else
    warn_or_fail 'host Prometheus config differs from the file visible inside the container; a single-file bind mount may still reference the pre-git-pull inode. Recreate/redeploy the Prometheus container before relying on HUP.'
  fi
else
  warn_or_fail "cannot read /etc/prometheus/prometheus.yml from container ${CONTAINER}"
fi

echo
echo '=== promtool on running container ==='
prom_config_status=invalid_or_unverified
if docker exec "${CONTAINER}" promtool check config /etc/prometheus/prometheus.yml; then
  prom_config_status=passed
  echo '✅ running-container Prometheus config is syntactically valid'
else
  warn_or_fail 'promtool rejected the config visible inside the running container'
fi

echo
echo '=== Active scrape targets ==='
TARGETS_JSON="${TMP_DIR}/targets.json"
if ! curl --fail --silent --show-error --max-time 10 \
  "${PROMETHEUS_URL}/api/v1/targets?state=active" >"${TARGETS_JSON}"; then
  warn_or_fail "Prometheus active-target API unavailable"
else
  # Service health and target health are separate signals: a reachable
  # Prometheus API with validated configuration can have failing exporters.
  read -r total_up total_not_up < <(jq -r '
    [(.data.activeTargets // [])[]?.health // "unknown"] as $states
    | "\($states | map(select(. == "up")) | length) \($states | map(select(. != "up")) | length)"
  ' "${TARGETS_JSON}")
  printf 'prometheus_runtime=running config_validation=%s target_up=%s target_not_up=%s\n' \
    "$prom_config_status" "$total_up" "$total_not_up"
  if ((total_not_up > 0)); then
    printf 'evidence=collector_targets_degraded_not_prometheus_startup\n'
  fi

  # Compact and redacted: scrapeUrl and lastError may include tokens,
  # private IPs, credentials or server messages. Never print these fields.
  jq -r '
    [.data.activeTargets[]? | {job: (.labels.job // "<missing-job>"),
                               health: (.health // "unknown")}] |
    group_by(.job)[] |
    "\(.[0].job) targets=\(length) up=\(map(select(.health == "up")) | length) not_up=\(map(select(.health != "up")) | length)"
  ' "${TARGETS_JSON}" | sort

  grep -E '^[[:space:]]*-[[:space:]]+job_name:[[:space:]]*' "${CONFIG}" |
    sed -E "s/.*job_name:[[:space:]]*['\"]?([^'\"[:space:]]+)['\"]?.*/\\1/" |
    sort -u >"${TMP_DIR}/expected-jobs.txt"
  jq -r '.data.activeTargets[]?.labels.job // empty' "${TARGETS_JSON}" |
    sort -u >"${TMP_DIR}/live-jobs.txt"

  comm -23 "${TMP_DIR}/expected-jobs.txt" "${TMP_DIR}/live-jobs.txt" >"${TMP_DIR}/missing-jobs.txt"
  if [[ -s "${TMP_DIR}/missing-jobs.txt" ]]; then
    printf 'Expected scrape jobs with no active target:\n' >&2
    sed 's/^/  - /' "${TMP_DIR}/missing-jobs.txt" >&2
    warn_or_fail 'one or more declared Prometheus jobs are absent from the live target inventory'
  else
    echo '✅ every declared Prometheus job has at least one active target'
  fi

  jq -r '
    .data.activeTargets[]?
    | select((.health // "unknown") != "up")
    | [(.labels.job // "<missing-job>"), (.health // "unknown")]
    | @tsv
  ' "${TARGETS_JSON}" >"${TMP_DIR}/unhealthy-targets.tsv"
  if [[ -s "${TMP_DIR}/unhealthy-targets.tsv" ]]; then
    printf 'Unhealthy targets (job and health only):\n' >&2
    sed 's/^/  /' "${TMP_DIR}/unhealthy-targets.tsv" >&2
    warn_or_fail 'one or more Prometheus targets are not UP'
  else
    echo '✅ all active Prometheus targets are UP'
  fi
fi

echo
if ((failures > 0)); then
  printf 'FAILED: %d Prometheus validation problem(s)\n' "${failures}" >&2
  exit 1
fi

echo 'OK: Prometheus config/target diagnostic completed read-only'
