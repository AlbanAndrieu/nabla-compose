#!/usr/bin/env bash
# Read-only DefectDojo runtime, DNS and private ingress diagnostic.
set -euo pipefail
[[ "${1:---check}" == "--check" && $# -le 1 ]] || { echo "usage: $0 --check" >&2; exit 2; }
APP_HOST="172.17.0.24"
PORT="31085"
FQDN="defectdojo.int.albandrieu.com"
errors=0
warnings=0
ok() { printf 'OK %s\n' "$*"; }
fail() { printf 'FAIL %s\n' "$*"; errors=$((errors+1)); }
warn() { printf 'WARN %s\n' "$*"; warnings=$((warnings+1)); }
for cmd in docker curl dig jq ip; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR missing=$cmd" >&2; exit 2; }
done
printf '%s\n' '==> TrueNAS identity and Docker network (metadata only)'
if ip -o -4 addr show | grep -Eq '[[:space:]]172[.]17[.]0[.]24/[0-9]{1,2}[[:space:]]'; then
  ok "TrueNAS LAN address present"
else
  fail "TrueNAS LAN address absent"
fi
for container in defectdojo traefik; do
  if ! docker inspect --type container "$container" >/dev/null 2>&1; then
    fail "container=$container absent"
    continue
  fi
  state="$(docker inspect --type container --format '{{.State.Status}}' "$container")"
  networks="$(docker inspect --type container --format '{{json .NetworkSettings.Networks}}' "$container" | jq -r 'keys | join(",")')"
  printf 'container=%s state=%s networks=%s\n' "$container" "$state" "$networks"
  [[ "$state" == running ]] || fail "container=$container not running"
  if [[ ",$networks," == *",traefik_network,"* ]]; then
    ok "container=$container on traefik_network"
  else
    fail "container=$container missing traefik_network"
  fi
done
if docker inspect --type container defectdojo >/dev/null 2>&1; then
  ports="$(docker port defectdojo 8080/tcp 2>/dev/null || true)"
  printf 'defectdojo_port=%s\n' "${ports:-absent}"
  [[ "$ports" == "172.17.0.24:31085" ]] || fail "unexpected DefectDojo host port binding"
fi
printf '%s\n' '==> Private HTTP API (no credentials)'
http="$(curl --noproxy '*' --silent --show-error --output /dev/null --write-out '%{http_code}' --connect-timeout 3 --max-time 8 "http://${APP_HOST}:${PORT}/api/v2/" 2>/dev/null)" || http="000"
printf 'api_http=%s\n' "$http"
[[ "$http" != 000 ]] && ok "LAN HTTP endpoint reachable" || fail "LAN HTTP endpoint unreachable"
[[ "$http" == 403 || "$http" == 401 ]] && ok "unauthenticated API access rejected" || warn "unauthenticated API status=$http; review access policy"
printf '%s\n' '==> Split DNS A records'
for resolver in 172.17.0.24 172.17.0.1 1.1.1.1; do
  response="$(dig +time=2 +tries=1 +noall +answer @"$resolver" "$FQDN" A 2>/dev/null | awk '$4 == "A" {print $5}' | sort -u | paste -sd, -)" || response=""
  printf 'dns_server=%s A=%s\n' "$resolver" "${response:-none}"
  if [[ "$resolver" == 1.1.1.1 ]]; then
    [[ -z "$response" ]] && ok "no public A record" || fail "public A record present"
  else
    [[ "$response" == "$APP_HOST" ]] && ok "private DNS on $resolver" || fail "private DNS missing/mismatched on $resolver"
  fi
done
printf '%s\n' '==> Traefik HTTPS with SNI (no TLS bypass)'
headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT
code="$(curl --noproxy '*' --silent --show-error --output /dev/null --dump-header "$headers" --write-out '%{http_code}' --connect-timeout 3 --max-time 10 --resolve "$FQDN:443:$APP_HOST" "https://$FQDN/" 2>/dev/null)" || code="000"
printf 'https_http=%s\n' "$code"
case "$code" in
  000) fail "HTTPS transport or TLS verification failed" ;;
  404) fail "Traefik route returned 404 (router may be absent)" ;;
  200|301|302|303|307|308|401|403) ok "HTTPS router responds with HTTP $code" ;;
  *) warn "HTTPS returned HTTP $code" ;;
esac
printf 'summary failures=%d warnings=%d\n' "$errors" "$warnings"
((errors == 0))
