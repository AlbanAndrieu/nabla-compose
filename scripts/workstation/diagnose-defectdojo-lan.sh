#!/usr/bin/env bash
# Read-only LAN acceptance preflight: DNS -> HTTPS/Traefik -> HTTP response.
set -euo pipefail
host="${DEFECTDOJO_HOST:-defectdojo.int.albandrieu.com}"
resolver="${PFSENSE_DNS:-172.17.0.1}"
edge="${TRUENAS_EDGE:-172.17.0.24}"
for command in curl dig getent; do
  command -v "$command" >/dev/null || { echo "ERROR: missing $command" >&2; exit 2; }
done
case "${1:---check}" in --check) ;; *) echo "Usage: $0 --check" >&2; exit 2;; esac
echo "==> DNS through pfSense Unbound ($resolver)"
dig +time=3 +tries=1 +noall +answer @"$resolver" "$host" A
ip=$(dig +short +time=3 +tries=1 @"$resolver" "$host" A | grep -E '^[0-9]+(\.[0-9]+){3}$' | head -1 || true)
if [[ "$ip" != "$edge" ]]; then
  echo "FAIL: expected internal edge $edge, got ${ip:-no A record}" >&2
  exit 1
fi
echo "PASS: private DNS points to TrueNAS edge"
# A direct dig @pfSense answer is not the client's NSS/system resolver.
# Do not mark the browser path healthy just because --resolve bypasses DNS.
system_dns_ok=false
if system_answers="$(getent ahostsv4 "$host" 2>/dev/null)"; then
  if awk -v expected="$edge" '
    NF { count++; if ($1 != expected) unexpected=1 }
    END { exit !(count > 0 && !unexpected) }
  ' <<< "$system_answers"; then
    system_dns_ok=true
  fi
fi
if [[ "$system_dns_ok" == true ]]; then
  echo "PASS: workstation system resolver matches private TrueNAS edge"
else
  echo "WARN: CLIENT_PRIVATE_SPLIT_DNS_PATH: pfSense DNS works but system resolver does not" >&2
  echo "NEXT: compare resolvectl dns/domain eno1, NetworkManager and VPN/DoH; do not edit pfSense" >&2
fi
echo '==> HTTPS via explicit private edge with correct SNI and Host'
# Do not follow redirects or disclose response bodies, cookies or tokens.
code=$(curl -sS -k --connect-timeout 5 --max-time 12 --resolve "$host:443:$edge" -o /dev/null -w '%{http_code}' "https://$host/" ) || { echo "FAIL: TLS/HTTP transport error" >&2; exit 1; }
echo "HTTP status: $code"
case "$code" in
  200|301|302|303|307|308|401|403) echo 'PASS: route responds; authentication/application readiness still unverified' ;;
  404|502|503|504|000) echo "WARN: edge route or backend requires investigation ($code)"; exit 1 ;;
  *) echo "WARN: unexpected status $code; inspect route and backend"; exit 1 ;;
esac
echo '==> TLS certificate validation (system trust store)'
# curl without -k; a redirect is an acceptable HTTP response and does not invalidate TLS.
tls_result=$(curl -sS --connect-timeout 5 --max-time 12 --resolve "$host:443:$edge" -o /dev/null -w '%{ssl_verify_result} %{http_code}' "https://$host/" 2>/dev/null) || {
  echo 'FAIL: TLS handshake, trust verification, or HTTPS transport failed' >&2
  exit 1
}
read -r verify_code verified_http <<< "$tls_result"
if [[ "$verify_code" != 0 ]]; then
  echo "FAIL: TLS certificate verify result=$verify_code" >&2
  exit 1
fi
echo "PASS: TLS certificate trusted (HTTP $verified_http)"
echo '==> Redirect metadata (no cookies or authentication headers)'
# Show only whether redirect remains on the same origin, without leaking query parameters.
redirect=$(curl -sS --connect-timeout 5 --max-time 12 --resolve "$host:443:$edge" -o /dev/null -w '%{redirect_url}' "https://$host/")
if [[ -z "$redirect" ]]; then
  echo 'No redirect'
elif [[ "$redirect" == "https://$host/"* ]]; then
  echo 'Redirect: same HTTPS origin (path and query redacted)'
else
  echo 'WARN: redirect leaves expected HTTPS origin (destination redacted)'
fi
echo 'NOTE: HTTP response and TLS verified; application authentication, database and workers remain unverified.'
if [[ "$system_dns_ok" != true ]]; then
  echo 'FAIL: direct HTTPS works only with DNS override; workstation hostname resolution remains broken' >&2
  exit 1
fi
