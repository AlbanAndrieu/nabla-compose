#!/usr/bin/env bash
# Read-only workstation HTTPS/DNS comparison for a Wi-Fi WhatsApp incident.
# Never reads browser cookies, WhatsApp messages, session keys or browser storage.
set -euo pipefail
case "${1:-}" in
  --check) [[ $# -eq 1 ]] || exit 2 ;;
  --help|-h) echo "Usage: $0 --check"; exit 0 ;;
  *) echo "Usage: $0 --check" >&2; exit 2 ;;
esac
echo '=== Workstation resolver (public destination only) ==='
if command -v resolvectl >/dev/null 2>&1; then
  resolvectl dns 2>/dev/null | head -8 || true
elif command -v nmcli >/dev/null 2>&1; then
  nmcli -g IP4.DNS,IP6.DNS device show 2>/dev/null | head -8 || true
fi
if ! command -v curl >/dev/null 2>&1; then
  echo 'FAIL curl=missing'; exit 2
fi
echo '=== WhatsApp Web TLS/HTTPS path; unauthenticated headers only ==='
for domain in web.whatsapp.com static.whatsapp.net; do
  # HEAD response codes (including 403/405) only prove the reachable edge.
  # All network calls have an explicit bound. Do not follow redirects.
  for family in 4 6; do
    status="$(curl "-$family" --silent --show-error --output /dev/null \
      --head --max-redirs 0 --connect-timeout 3 --max-time 7 \
      --write-out '%{http_code} connect=%{time_connect} tls=%{time_appconnect} total=%{time_total}' \
      "https://${domain}/" 2>/dev/null)" && state=reachable || state=unavailable
    echo "host=${domain} ipv${family} transport=${state} response=${status:-none}"
  done
done
echo '=== Diagnostic boundaries ==='
echo 'HTTP 403/405 may be a normal edge response; this does not prove WhatsApp messaging.'
echo 'Compare this output when connected to the affected Wi-Fi and a second trusted network.'
echo 'Browser DevTools Network can identify failing wss/HTTPS calls but do not export HAR with cookies/tokens.'
