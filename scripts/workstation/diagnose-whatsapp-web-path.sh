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
echo '=== DNS answers: pfSense vs Quad9 (public domains only) ==='
# This checks resolver consistency; it does not prove the mobile uses either.
if command -v dig >/dev/null 2>&1; then
  for domain in web.whatsapp.com static.whatsapp.net; do
    for resolver in 172.17.0.1 9.9.9.9; do
      # +time=2 +tries=1 bounds DNS queries. Never inspect client DNS logs.
      response="$(dig +time=2 +tries=1 +noall +comments +answer A "${domain}" "@${resolver}" 2>/dev/null || true)"
      rcode="$(printf '%s\n' "${response}" | sed -nE 's/.*status: ([A-Z]+),.*/\1/p' | head -1)"
      count="$(printf '%s\n' "${response}" | awk '$4 == "A" {count++} END {print count + 0}')"
      case "${resolver}" in
        172.17.0.1) source=unbound ;;
        *) source=quad9 ;;
      esac
      printf 'dns_host=%s source=%s rcode=%s a_records=%s\n' \
        "${domain}" "${source}" "${rcode:-unknown}" "${count}"
    done
  done
else
  echo 'dns_comparison=NOT_RUN (dig unavailable)'
fi
echo '=== WhatsApp Web TLS/HTTPS path; unauthenticated headers only ==='
for domain in web.whatsapp.com static.whatsapp.net; do
  # HEAD response codes (including 403/405) only prove the reachable edge.
  # All network calls have an explicit bound. Do not follow redirects.
  for family in 4 6; do
    status="$(curl "-${family}" --silent --show-error --output /dev/null \
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
