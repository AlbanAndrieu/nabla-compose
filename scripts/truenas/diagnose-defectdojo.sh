#!/usr/bin/env bash
# Read-only DefectDojo runtime, DNS and private ingress diagnostic.
set -euo pipefail
[[ "${1:---check}" == "--check" && $# -le 1 ]] || { echo "usage: $0 --check" >&2; exit 2; }
APP_HOST="172.17.0.24"
PORT="31085"
FQDN="defectdojo.int.albandrieu.com"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/diagnostic-ui.sh
source "${SCRIPT_DIR}/../lib/diagnostic-ui.sh"
diag_ui_init "${DIAG_COLOR:-auto}" "${DIAG_ICONS:-auto}" || exit 2
for cmd in docker curl dig jq ip; do
  command -v "${cmd}" >/dev/null 2>&1 || { echo "ERROR missing=${cmd}" >&2; exit 2; }
done
# Normalize untrusted HTTP metadata into a fixed vocabulary.
# This helper never displays Content-Type and does not treat HTTP status as readiness.
classify_html_probe() {
  local record="${1:-000|}" code mime
  IFS='|' read -r code mime <<<"${record}"
  [[ "${code}" =~ ^[0-9]{3}$ ]] || code=000
  case "${mime,,}" in
    text/html|text/html\;*) mime=html ;;
    '') mime=missing ;;
    *) mime=other ;;
  esac
  printf '%s|%s\n' "${code}" "${mime}"
}
# Summarize one safe next diagnostic per failed layer; no secret, raw DNS
# response, URL query, or response body is ever printed.
DD_CONTAINER_ABSENT=0
DD_ORIGIN_FAILED=0
DD_PRIVATE_DNS_FAILED=0
DD_HTTPS_FAILED=0
DD_PROXY_NETWORK_FAILED=0
diag_section '1/4' 'TrueNAS identity and Docker network (metadata only)'
if ip -o -4 addr show | grep -Eq '[[:space:]]172[.]17[.]0[.]24/[0-9]{1,2}[[:space:]]'; then
  diag_ok "TrueNAS LAN address present"
else
  diag_fail "TrueNAS LAN address absent"
fi
for container in defectdojo traefik; do
  if ! docker inspect --type container "${container}" >/dev/null 2>&1; then
    [[ "${container}" == defectdojo ]] && DD_CONTAINER_ABSENT=1
    diag_fail "container=${container} absent"
    continue
  fi
  state="$(docker inspect --type container --format '{{.State.Status}}' "${container}")"
  networks="$(docker inspect --type container --format '{{json .NetworkSettings.Networks}}' "${container}" | jq -r 'keys | join(",")')"
  printf 'container=%s state=%s networks=%s\n' "${container}" "${state}" "${networks}"
  [[ "${state}" == running ]] || diag_fail "container=${container} not running"
  if [[ ",${networks}," == *",traefik_network,"* ]]; then
    diag_ok "container=${container} on traefik_network"
  else
    DD_PROXY_NETWORK_FAILED=1
    diag_fail "container=${container} missing traefik_network"
  fi
done
if docker inspect --type container defectdojo >/dev/null 2>&1; then
  ports="$(docker port defectdojo 8080/tcp 2>/dev/null || true)"
  printf 'defectdojo_port=%s\n' "${ports:-absent}"
  [[ "${ports}" == "172.17.0.24:31085" ]] || diag_fail "unexpected DefectDojo host port binding"
fi
# Distinguish public-facing Nginx from the uWSGI application server.
if docker inspect --type container defectdojo-uwsgi >/dev/null 2>&1; then
  uwsgi_state="$(docker inspect --type container --format '{{.State.Status}}' defectdojo-uwsgi 2>/dev/null || true)"
  case "$uwsgi_state" in
    running) diag_ok 'DefectDojo uWSGI backend running (Django readiness not yet verified)' ;;
    *) diag_fail "DefectDojo uWSGI state=${uwsgi_state:-unknown}" ;;
  esac
else
  diag_fail 'DefectDojo uWSGI backend absent'
fi

diag_section '2/4' 'Private HTTP API (no credentials)'
http="$(curl --noproxy '*' --silent --show-error --output /dev/null --write-out '%{http_code}' --connect-timeout 3 --max-time 8 "http://${APP_HOST}:${PORT}/api/v2/" 2>/dev/null)" || http="000"
printf 'api_http=%s\n' "${http}"
if [[ "${http}" != 000 ]]; then
  diag_ok "LAN API HTTP transport reachable; not a UI readiness proof"
else
  diag_fail "LAN HTTP endpoint unreachable"
fi
if [[ "${http}" == 403 || "${http}" == 401 ]]; then
  diag_ok "unauthenticated API access rejected"
else
  diag_warn "unauthenticated API status=${http}; review access policy"
fi
# /api/v2/ returning 403 only proves that the API is reachable.
# The UI must independently return HTML or an expected login redirect.
ui_probe="$(curl --noproxy '*' --silent --show-error --output /dev/null \
  --write-out '%{http_code}|%{content_type}' --connect-timeout 3 --max-time 8 \
  "http://${APP_HOST}:${PORT}/" 2>/dev/null)" || ui_probe="000|"
IFS='|' read -r ui_http ui_mime <<<"$(classify_html_probe "${ui_probe}")"
printf 'ui_origin_http=%s ui_mime=%s\n' "${ui_http}" "${ui_mime}"
case "${ui_http}" in
  200)
    if [[ "${ui_mime}" == html ]]; then
      diag_ok 'DefectDojo HTML origin responds'
    else
      diag_fail 'DefectDojo origin returned HTTP 200 without HTML Content-Type'
    fi ;;
  301|302|303|307|308) diag_ok 'DefectDojo HTML origin responds with redirect (destination not verified)' ;;
  401|403) diag_fail "HTML origin access denied (HTTP ${ui_http})" ;;
  000) diag_fail 'DefectDojo HTML origin unreachable' ;;
  404|5??) diag_fail "DefectDojo HTML origin returns HTTP ${ui_http}" ;;
  *) diag_warn "Unexpected HTML origin HTTP ${ui_http}" ;;
esac
case "${ui_http}" in
  200) [[ "${ui_mime}" == html ]] || DD_ORIGIN_FAILED=1 ;;
  301|302|303|307|308) ;;
  *) DD_ORIGIN_FAILED=1 ;;
esac
if [[ "$http" != 000 && "$ui_http" == 000 ]]; then
  printf 'evidence=api_reachable_but_ui_origin_unavailable\n'
fi
diag_section '3/4' 'Split DNS A records'
for resolver in 172.17.0.24 172.17.0.1 1.1.1.1; do
  # An empty answer is NOT evidence of private DNS when the DNS RCODE
  # is SERVFAIL/REFUSED, or the resolver serves stale cached data.
  if ! dns_packet="$(dig +time=2 +tries=1 +noall +comments +answer @"${resolver}" "${FQDN}" A 2>/dev/null)"; then
    printf 'dns_server=%s query=failed\n' "${resolver}"
    [[ "${resolver}" != 1.1.1.1 ]] && DD_PRIVATE_DNS_FAILED=1
    diag_fail "DNS resolver ${resolver} unavailable; no assertion about public exposure"
    continue
  fi
  dns_status="$(printf '%s\n' "${dns_packet}" |
    sed -nE 's/^;; .*status: ([A-Z]+),.*/\1/p' | head -n 1)"
  case "${dns_status}" in
    NOERROR|NXDOMAIN) ;;
    *)
      printf 'dns_server=%s query=invalid_response status=%s\n' "${resolver}" "${dns_status:-UNKNOWN}"
      [[ "${resolver}" != 1.1.1.1 ]] && DD_PRIVATE_DNS_FAILED=1
      diag_fail "DNS resolver ${resolver} returned an unverified response status"
      continue ;;
  esac
  if printf '%s\n' "${dns_packet}" | grep -Eq '^;; EDE: 3([[:space:]]|$)'; then
    printf 'dns_server=%s query=stale_answer\n' "${resolver}"
    [[ "${resolver}" != 1.1.1.1 ]] && DD_PRIVATE_DNS_FAILED=1
    diag_fail "DNS resolver ${resolver} served stale data; no current DNS acceptance"
    continue
  fi
  response="$(printf '%s\n' "${dns_packet}" |
    awk '$4 == "A" {print $5}' | sort -u | paste -sd, -)"
  printf 'dns_server=%s A=%s\n' "${resolver}" "${response:-none}"
  if [[ "${resolver}" == 1.1.1.1 ]]; then
    if [[ -z "${response}" ]]; then
      diag_ok "no public A record"
    else
      diag_fail "public A record present"
    fi
  elif [[ "${response}" == "${APP_HOST}" ]]; then
    diag_ok "private DNS on ${resolver}"
  else
    DD_PRIVATE_DNS_FAILED=1
    diag_fail "private DNS missing/mismatched on ${resolver}"
  fi
done
diag_section '4/4' 'Traefik HTTPS with SNI (no TLS bypass)'
headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT
https_probe="$(curl --noproxy '*' --silent --show-error --output /dev/null --dump-header "${headers}" --write-out '%{http_code}|%{content_type}' --connect-timeout 3 --max-time 10 --resolve "${FQDN}:443:${APP_HOST}" "https://${FQDN}/" 2>/dev/null)" || https_probe="000|"
IFS='|' read -r code https_mime <<<"$(classify_html_probe "${https_probe}")"
printf 'https_http=%s https_mime=%s\n' "${code}" "${https_mime}"
case "${code}" in
  000) diag_fail "HTTPS transport or TLS verification failed" ;;
  404) diag_fail "Traefik route returned 404 (router may be absent)" ;;
  200)
    if [[ "${https_mime}" == html ]]; then
      diag_ok 'HTTPS router serves HTML'
    else
      diag_fail 'HTTPS router returned HTTP 200 without HTML Content-Type'
    fi ;;
  301|302|303|307|308) diag_ok "HTTPS router redirects with HTTP ${code} (destination not verified)" ;;
  401|403) diag_fail "HTTPS browser access denied (HTTP ${code})" ;;
  *) diag_warn "HTTPS returned HTTP ${code}" ;;
esac
case "${code}" in
  000|404|401|403|5??) DD_HTTPS_FAILED=1 ;;
  200) [[ "${https_mime}" == html ]] || DD_HTTPS_FAILED=1 ;;
esac
diag_section '' 'DefectDojo remediation hints (diagnostics only)'
if (( DD_CONTAINER_ABSENT > 0 )); then
  diag_info 'NEXT origin: inspect TrueNAS app.query defectdojo and deployment state; never reinitialize PostgreSQL'
fi
if (( DD_ORIGIN_FAILED > 0 )); then
  diag_info 'NEXT origin: check Nginx/uWSGI containers and LAN :31085 before modifying DNS or Traefik'
fi
if (( DD_PROXY_NETWORK_FAILED > 0 )); then
  diag_info 'NEXT proxy: reconcile only DefectDojo frontend attachment to traefik_network with reviewed compose'
fi
if (( DD_PRIVATE_DNS_FAILED > 0 )); then
  diag_info 'NEXT DNS: verify Pi-hole A record and pfSense Unbound forward/reachability; never publish a public A record'
fi
if (( DD_HTTPS_FAILED > 0 )); then
  diag_info 'NEXT HTTPS: verify Traefik router labels, SNI and TLS without changing Django or credentials'
fi
if (( DD_CONTAINER_ABSENT + DD_ORIGIN_FAILED + DD_PROXY_NETWORK_FAILED + DD_PRIVATE_DNS_FAILED + DD_HTTPS_FAILED == 0 )); then
  diag_info 'NEXT client: compare workstation DNS, browser proxy and redirects; runtime failure not reproduced'
fi
diag_info 'READ_ONLY: no app restart, DNS edit, database migration or secret read'
diag_summary
((DIAG_FAILURES == 0))
