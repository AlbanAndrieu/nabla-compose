#!/usr/bin/env bash
# Read-only LAN acceptance preflight: DNS -> HTTPS/Traefik -> HTTP response.
set -euo pipefail
host="${DEFECTDOJO_HOST:-defectdojo.int.albandrieu.com}"
resolver="${PFSENSE_DNS:-172.17.0.1}"
edge="${TRUENAS_EDGE:-172.17.0.24}"
for command in curl dig; do
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
echo '==> HTTPS via explicit private edge with correct SNI and Host'
# Do not follow redirects or disclose response bodies, cookies or tokens.
code=$(curl -sS -k --connect-timeout 5 --max-time 12 --resolve "$host:443:$edge" -o /dev/null -w '%{http_code}' "https://$host/" ) || { echo "FAIL: TLS/HTTP transport error" >&2; exit 1; }
echo "HTTP status: $code"
case "$code" in
  200|301|302|303|307|308|401|403) echo 'PASS: route responds; authentication/application readiness still unverified' ;;
  404|502|503|504|000) echo "WARN: edge route or backend requires investigation ($code)"; exit 1 ;;
  *) echo "WARN: unexpected status $code; inspect route and backend"; exit 1 ;;
esac
echo 'NOTE: --resolve uses -k only for routing preflight; independently verify trusted TLS certificate before acceptance.'
