#!/usr/bin/env bash
# Read-only, redacted acceptance diagnostics for FastAPI Sample on TrueNAS.
set -uo pipefail

CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
API="${FASTAPI_SAMPLE_DIAG_API:-http://127.0.0.1:8091}"
CYCLES=3
INTERVAL=31

usage() {
    cat <<'HELP'
Usage: bash scripts/truenas/diagnose-fastapi-sample.sh [--cycles 1|2|3] [--interval 30..120]

Read-only: check Git/TrueNAS version, host-vs-container public HTTP timing,
Docker resolver, bounded health-board samples, and Gatus/Prometheus telemetry.
No environment values, credentials, HTTP bodies from public sites, response
headers, or container logs are printed. HTTP 302/403 is not origin proof.
HELP
}

while (($#)); do
    case "$1" in
        --cycles)
            [[ $# -ge 2 && "$2" =~ ^[123]$ ]] || { usage >&2; exit 2; }
            CYCLES="$2"; shift 2 ;;
        --interval)
            [[ $# -ge 2 && "$2" =~ ^[0-9]+$ && "$2" -ge 30 && "$2" -le 120 ]] || {
                usage >&2; exit 2;
            }
            INTERVAL="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

section() { printf '\n== %s ==\n' "$*"; }
ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }
has() { command -v "$1" >/dev/null 2>&1; }

for command in git docker curl jq; do
    has "${command}" || { warn "Missing dependency: ${command}"; exit 1; }
done
if [[ ! "${CONTAINER}" =~ ^[a-zA-Z0-9_.-]+$ ]]; then
    warn 'Unsafe FASTAPI_SAMPLE_CONTAINER name'; exit 2
fi
if [[ "${API}" != 'http://127.0.0.1:8091' && "${API}" != 'http://172.17.0.24:8091' ]]; then
    warn 'FASTAPI_SAMPLE_DIAG_API must be a known local TrueNAS address'; exit 2
fi
if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
elif has sudo && sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
else
    warn 'Docker unavailable or sudo permission denied'; exit 1
fi
run_docker() { "${DOCKER[@]}" "$@"; }

section '1/6 · Version, code et contexte'
if [[ -d /mnt/cpool/compose/nabla-compose/.git ]]; then
    cd /mnt/cpool/compose/nabla-compose || exit 1
    owner="$(stat -c '%U' . 2>/dev/null || true)"
    read_git() {
        if [[ "${EUID}" -eq 0 && -n "${owner}" && "${owner}" != root ]]; then
            sudo -u "${owner}" -H git "$@"
        else
            git "$@"
        fi
    }
    parent="$(read_git rev-parse --short HEAD 2>/dev/null || true)"
    pinned="$(read_git ls-files -s fastapi-sample 2>/dev/null | awk 'NR==1 {print $2}')"
    checkout="$(read_git -C fastapi-sample rev-parse HEAD 2>/dev/null || true)"
    printf 'nabla-compose: %s\n' "${parent:-unavailable}"
    printf 'fastapi-sample checkout: %s\n' "${checkout:-unavailable}"
    printf 'parent gitlink: %s\n' "${pinned:-unavailable}"
    if [[ -n "${checkout}" && -n "${pinned}" && "${checkout}" != "${pinned}" ]]; then
        warn 'Gitlink differs from checkout (expected after test deployment; do not auto-stage)'
    fi
else
    warn 'nabla-compose checkout missing: Git revision not collected'
fi
if [[ -f /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json ]]; then
    printf 'Canonical catalog candidates: '
    jq -cr '
      [.services[]? | select(.id == "languagetool" or .name == "Language Tool") |
        {id, name, external}] as $rows |
      {languagetool_entries: ($rows | length), entries: $rows}
    ' /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json ||
        warn 'Canonical catalog unavailable or invalid'
    printf 'Garage catalog entries: '
    jq -cr '[.services[]? | select((.id // "") | startswith("garage")) |
       {id, external, probePriority, deploymentUnitId}]' \
        /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json || true
fi
if has midclt; then
    (sudo -n midclt call app.query '[["id","=","sample"]]' 2>/dev/null || true) |
        jq -cr '.[]? | {app_id: .id, truenas_state: .state, app_chart_version: .version}' || true
fi
if ! run_docker inspect "${CONTAINER}" \
    --format 'container={{.Name}} state={{.State.Status}} image={{.Image}}' 2>/dev/null; then
    warn "Container ${CONTAINER} not found"; exit 1
fi
version_payload="$(curl -fsS --connect-timeout 3 --max-time 8 "${API}/v2/version" 2>/dev/null || true)"
if [[ -n "${version_payload}" ]] && jq -e . >/dev/null 2>&1 <<<"${version_payload}"; then
    jq -cr '{release_version, version, build_revision}' <<<"${version_payload}"
    if [[ "$(jq -r '.build_revision // empty' <<<"${version_payload}")" == '' ]]; then
        warn 'API build_revision missing; package version alone does not prove deployed Git commit'
    fi
else
    warn 'Version API unavailable; no runtime revision attestation'
fi

section '2/6 · Public HTTP timing: TrueNAS host vs Docker container'
for host in garage.albandrieu.com garage-admin.albandrieu.com fastapi-sample.fastapicloud.dev; do
    printf '%-12s %-39s ' HOST "${host}"
    curl -sS -o /dev/null --connect-timeout 5 --max-time 12 \
        -w 'HTTP=%{http_code} DNS=%{time_namelookup}s TCP=%{time_connect}s TLS=%{time_appconnect}s TOTAL=%{time_total}s\n' \
        "https://${host}/" 2>/dev/null || warn 'host request failed'
    printf '%-12s %-39s ' CONTAINER "${host}"
    run_docker exec "${CONTAINER}" curl -sS -o /dev/null \
        --connect-timeout 5 --max-time 12 \
        -w 'HTTP=%{http_code} DNS=%{time_namelookup}s TCP=%{time_connect}s TLS=%{time_appconnect}s TOTAL=%{time_total}s\n' \
        "https://${host}/" 2>/dev/null || warn 'container request failed'
done
printf 'Note: 302/403 often reflects Cloudflare Access; it does not establish origin reachability.\n'

section '3/6 · Container DNS metadata (no credentials)'
run_docker exec "${CONTAINER}" sh -c \
    'grep -E "^(nameserver |search |options |# ExtServers:)" /etc/resolv.conf' 2>/dev/null ||
    warn 'Cannot read resolver metadata'

section '4/6 · Health-board: bounded repeated samples'
for ((i=1; i<=CYCLES; i++)); do
    payload="$(curl -fsS --connect-timeout 3 --max-time 30 \
        "${API}/api/health-board" 2>/dev/null || true)"
    if [[ -z "${payload}" ]] || ! jq -e '.homelab | type == "object"' \
        >/dev/null 2>&1 <<<"${payload}"; then
        warn "Cycle ${i}/${CYCLES}: health-board unavailable or homelab section missing"
    else
        printf 'cycle=%s/%s ' "${i}" "${CYCLES}"
        jq -cr '
          .homelab as $h |
          {
            public: ($h.probe_summary.public // {} | {completed, timed_out, priority_source}),
            internal: ($h.probe_summary.internal // {} | {completed, timed_out, priority_source,
              coverage_percent: .evidence.coverage_percent}),
            garage_internal: [($h.internal_services // [])[] | select(.id == "garage" or .id == "garage-admin" or .id == "garage-webui") | .id],
            garage: [($h.services // [])[] | select(.id == "garage" or .id == "garage-admin" or .id == "garage-webui") |
              {id, state, internal_state, exposure_intent, unexpected_tunnel_route, probe_stale}]
          }' <<<"${payload}"
    fi
    if ((i<CYCLES)); then sleep "${INTERVAL}"; fi
done

section '5/6 · Prometheus/Gatus connectivity'
# shellcheck disable=SC2016 -- expansion happens inside the container
if run_docker exec "${CONTAINER}" sh -c \
    'test "${HOMELAB_PROMETHEUS_URL:-}" = "http://172.17.0.24:9090"' 2>/dev/null; then
    ok 'Expected HOMELAB_PROMETHEUS_URL configured (value not printed)'
else
    warn 'HOMELAB_PROMETHEUS_URL absent/different (value not printed)'
fi
if run_docker exec "${CONTAINER}" curl -fsS -o /dev/null --max-time 6 \
    http://172.17.0.24:9090/-/ready 2>/dev/null; then
    ok 'Prometheus /-/ready reachable'
else
    warn 'Prometheus /-/ready unavailable'
fi
rules="$(run_docker exec "${CONTAINER}" curl -fsSG --max-time 8 \
    --data-urlencode \
    'query=count by (__name__) ({__name__=~"nabla:telemetry:gatus_up|nabla:service:synthetic_probe_success|nabla:service:synthetic_probe_duration_seconds|nabla:service:synthetic_availability_ratio_5m"})' \
    http://172.17.0.24:9090/api/v1/query 2>/dev/null || true)"
if [[ -n "${rules}" ]] && jq -e '.status == "success"' >/dev/null 2>&1 <<<"${rules}"; then
    jq -cr '[.data.result[]? | {metric: .metric.__name__, series: .value[1]}]' <<<"${rules}"
else
    warn 'Prometheus query failed (missing rules or connection error)'
fi

section '6/6 · Passive container resource snapshot'
run_docker stats --no-stream --format \
    'container={{.Name}} CPU={{.CPUPerc}} MEM={{.MemUsage}} PIDs={{.PIDs}}' \
    "${CONTAINER}" 2>/dev/null || warn 'Docker stats unavailable'

printf '\nNEXT: compare the three cycles and public completed/timed_out against HTTP timings.\n'
printf 'Safety: no restart, no application configuration changes, no raw response headers or secrets.\n'
