#!/usr/bin/env bash
# Read-only, redacted acceptance diagnostics for FastAPI Sample on TrueNAS.
set -uo pipefail

CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
API="${FASTAPI_SAMPLE_DIAG_API:-http://127.0.0.1:8091}"
CYCLES=3
INTERVAL=31
COLOR_MODE=auto
ICON_MODE=auto
EXPECTED_SHA=''
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"

usage() {
    cat <<'HELP'
Usage: bash scripts/truenas/diagnose-fastapi-sample.sh [--cycles 1|2|3] [--interval 30..120]
       [--color auto|always|never] [--icons auto|always|never]
       [--expected-sha <40-hex-commit>]

By default, ANSI color is enabled only on a terminal. With a tee pipe use
--color always and strip ANSI from the archived log, or use --color never.
NO_COLOR disables ANSI color even when --color always is requested.

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
        --color)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            COLOR_MODE="$2"; shift 2 ;;
        --color=*) COLOR_MODE="${1#*=}"; shift ;;
        --icons)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            ICON_MODE="$2"; shift 2 ;;
        --icons=*) ICON_MODE="${1#*=}"; shift ;;
        --expected-sha)
            [[ $# -ge 2 ]] || { usage >&2; exit 2; }
            EXPECTED_SHA="$2"; shift 2 ;;
        --expected-sha=*) EXPECTED_SHA="${1#*=}"; shift ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

diag_ui_init "${COLOR_MODE}" "${ICON_MODE}" || exit 2
if [[ -n "${EXPECTED_SHA}" && ! "${EXPECTED_SHA}" =~ ^[0-9a-fA-F]{40}$ ]]; then
    printf 'Invalid --expected-sha; provide a full 40-character Git SHA\n' >&2
    exit 2
fi
section() { diag_section "$1" "$2"; }
ok() { diag_ok "$*"; }
warn() { diag_warn "$*"; }
unknown() { diag_unknown "$*"; }
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
    diag_info 'Accès Docker direct : aucune élévation sudo nécessaire'
elif has sudo && sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
    diag_info 'Accès Docker via sudo -n autorisé sans mot de passe'
else
    warn 'Accès Docker indisponible. Aucun mot de passe sudo demandé.'
    exit 1
fi
run_docker() { "${DOCKER[@]}" "$@"; }

section '1/6' 'Version, code et contexte'
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
        warn 'Gitlink différent du checkout (test staging ; ne pas git add automatiquement)'
    else
        ok 'Gitlink et checkout du sous-module concordants'
    fi
    if [[ -n "${EXPECTED_SHA}" && "${checkout}" != "${EXPECTED_SHA}" ]]; then
        warn "Révision staging différente de --expected-sha : ${checkout:-unknown}"
    elif [[ -n "${EXPECTED_SHA}" ]]; then
        ok 'Révision Git du checkout conforme à --expected-sha'
    else
        master="$(read_git -C fastapi-sample rev-parse origin/master 2>/dev/null || true)"
        if [[ -n "${master}" && "${checkout}" == "${master}" ]]; then
            diag_info 'Le checkout correspond à origin/master : une PR ouverte n’est pas nécessairement déployée'
        fi
    fi
else
    warn 'nabla-compose checkout missing: Git revision not collected'
fi
if [[ -f /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json ]]; then
    printf 'Canonical catalog candidates: '
    candidate_count="$(jq -er '
      [.services[]? | select(.id == "languagetool" or .name == "Language Tool")] | length
    ' /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json 2>/dev/null || true)"
    if [[ "${candidate_count}" =~ ^[0-9]+$ ]]; then
        printf 'LanguageTool entries=%s\n' "${candidate_count}"
        if [[ "${candidate_count}" == 1 ]]; then
            ok 'LanguageTool : pas de doublon dans le catalogue local'
        else
            warn 'LanguageTool : vérifier identités et exposition dans le catalogue canonique'
        fi
    else
        unknown 'Catalogue local illisible ; identité LanguageTool non vérifiée'
    fi
    printf 'Garage catalog entries: '
    jq -cr '[.services[]? | select((.id // "") | startswith("garage")) |
       {id, external, probePriority, deploymentUnitId}]' \
        /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json || true
    garage_ranked="$(jq -r '[.services[]? | select((.id // "") | startswith("garage")) |
      select(.probePriority != null)] | length' \
      /mnt/cpool/compose/nabla-compose/catalog/homelab-services.json 2>/dev/null || true)"
    if [[ "${garage_ranked}" == 0 ]]; then
        warn 'Garage : aucun probePriority publié dans le catalogue local'
    else
        ok "Garage : ${garage_ranked:-unknown} rang(s) publiés dans le catalogue local"
    fi
fi
if has midclt; then
    app_query='[["id","=","sample"]]'
    app_payload=''
    if app_payload="$(midclt call app.query "${app_query}" 2>/dev/null)" &&
        jq -e 'type == "array"' >/dev/null 2>&1 <<<"${app_payload}"; then
        diag_info 'Middleware TrueNAS accessible sans sudo'
    elif has sudo &&
        app_payload="$(sudo -n midclt call app.query "${app_query}" 2>/dev/null)" &&
        jq -e 'type == "array"' >/dev/null 2>&1 <<<"${app_payload}"; then
        diag_info 'Middleware TrueNAS accessible via sudo -n sans invite'
    else
        app_payload=''
        unknown 'Middleware TrueNAS non accessible en lecture seule (aucun prompt sudo)'
    fi
    if [[ -n "${app_payload}" ]]; then
        jq -cr '.[]? | {app_id: .id, truenas_state: .state, app_chart_version: .version}' \
            <<<"${app_payload}"
        if ! jq -e 'length > 0' >/dev/null 2>&1 <<<"${app_payload}"; then
            unknown 'Application sample absente de la réponse TrueNAS middleware'
        fi
    fi
fi
if ! run_docker inspect "${CONTAINER}" \
    --format 'container={{.Name}} state={{.State.Status}} image={{.Image}}' 2>/dev/null; then
    warn "Container ${CONTAINER} not found"; exit 1
fi
version_payload="$(curl -fsS --connect-timeout 3 --max-time 8 "${API}/v2/version" 2>/dev/null || true)"
if [[ -n "${version_payload}" ]] && jq -e . >/dev/null 2>&1 <<<"${version_payload}"; then
    jq -cr '{release_version, version, build_revision}' <<<"${version_payload}"
    if [[ "$(jq -r '.build_revision // empty' <<<"${version_payload}")" == '' ]]; then
        unknown 'API build_revision=null : la version du paquet ne prouve pas le SHA du binaire'
    else
        ok 'API build_revision disponible (provenance applicative déclarée)'
    fi
else
    warn 'Version API unavailable; no runtime revision attestation'
fi

section '2/6' 'HTTP public : comparaison hôte / conteneur'
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
diag_info 'HTTP 302/403 : route Cloudflare Access, pas preuve de santé ou d’accès anonyme à l’origine.'

section '3/6' 'Résolution DNS du conteneur (sans secrets)'
run_docker exec "${CONTAINER}" sh -c \
    'grep -E "^(nameserver |search |options |# ExtServers:)" /etc/resolv.conf' 2>/dev/null ||
    warn 'Cannot read resolver metadata'

section '4/6' 'Health-board : trois cycles bornés'
for ((i=1; i<=CYCLES; i++)); do
    payload="$(curl -fsS --connect-timeout 3 --max-time 30 \
        "${API}/api/health-board" 2>/dev/null || true)"
    if [[ -z "${payload}" ]] || ! jq -e '.homelab | type == "object"' \
        >/dev/null 2>&1 <<<"${payload}"; then
        warn "Cycle ${i}/${CYCLES} : health-board indisponible ou section homelab absente"
    else
        ok "Cycle ${i}/${CYCLES} : réponse homelab reçue"
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
        public_completed="$(jq -r '.homelab.probe_summary.public.completed // 0' <<<"${payload}")"
        public_timed_out="$(jq -r '.homelab.probe_summary.public.timed_out // 0' <<<"${payload}")"
        internal_ids="$(jq -r '[.homelab.internal_services[]? |
          select(.id == "garage" or .id == "garage-admin" or .id == "garage-webui")] | length' <<<"${payload}")"
        if [[ "${public_timed_out}" =~ ^[0-9]+$ ]] && ((public_timed_out > 0)); then
            warn "Cycle ${i} : sondes publiques ${public_completed} terminées / ${public_timed_out} expirées"
        else
            ok "Cycle ${i} : aucune échéance de sonde publique rapportée"
        fi
        if [[ "${internal_ids}" == 3 ]]; then
            ok "Garage LAN : 3/3 composants présents dans internal_services"
        else
            warn "Garage LAN : ${internal_ids}/3 composants sondés (déploiement #342 à confirmer)"
        fi
    fi
    if ((i<CYCLES)); then sleep "${INTERVAL}"; fi
done

section '5/6' 'Contrat Prometheus / Gatus'
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
    for metric in nabla:telemetry:gatus_up \
        nabla:service:synthetic_probe_success \
        nabla:service:synthetic_probe_duration_seconds \
        nabla:service:synthetic_availability_ratio_5m; do
        if jq -e --arg name "${metric}" '[.data.result[]? |
            select(.metric.__name__ == $name)] | length > 0' \
            >/dev/null 2>&1 <<<"${rules}"; then
            ok "Prometheus : échantillons présents pour ${metric}"
        else
            unknown "Prometheus : aucune série courante retournée pour ${metric}"
        fi
    done
else
    warn 'Prometheus query failed (missing rules or connection error)'
fi

section '6/6' 'Ressources Docker : instantané passif'
run_docker stats --no-stream --format \
    'container={{.Name}} CPU={{.CPUPerc}} MEM={{.MemUsage}} PIDs={{.PIDs}}' \
    "${CONTAINER}" 2>/dev/null || warn 'Docker stats unavailable'

diag_summary
diag_info 'Comparer les 3 cycles et les expirations publiques aux temps HTTP, sans augmenter le budget de 4 s.'
diag_info 'Lecture seule : aucun redémarrage, aucune modification de configuration, aucun secret.'
