#!/usr/bin/env bash
# Read-only login page acceptance. Pin LAN edge while preserving TLS SNI.
set -euo pipefail
[[ $# == 1 && $1 == --check ]] || { echo 'usage: check-defectdojo-login-lan.sh --check' >&2; exit 2; }
readonly HOST='defectdojo.int.albandrieu.com'
readonly EDGE='172.17.0.24'
readonly URL="https://${HOST}/login?next=/"
command -v curl >/dev/null 2>&1 || { echo 'UNVERIFIED: curl unavailable'; exit 2; }
record="$(curl --noproxy '*' --silent --show-error --output /dev/null \
  --connect-timeout 3 --max-time 12 --max-redirs 0 \
  --resolve "${HOST}:443:${EDGE}" \
  --write-out '%{http_code}|%{content_type}|%{ssl_verify_result}' \
  "${URL}" 2>/dev/null)" || { echo 'UNVERIFIED: TLS/connect unavailable'; exit 2; }
IFS='|' read -r http mime tls <<< "${record}"
[[ "${http}" =~ ^[0-9]{3}$ && "${tls}" =~ ^[0-9]+$ ]] || { echo 'UNVERIFIED: malformed probe response'; exit 2; }
case "${mime,,}" in text/html|text/html\;*) content=html;; *) content=unverified;; esac
printf 'defectdojo_login_http=%s tls_verify=%s content=%s\n' "${http}" "${tls}" "${content}"
if [[ "${tls}" != 0 ]]; then echo 'FAIL: TLS verification failed'; exit 1; fi
if [[ "${http}" == 200 && "${content}" == html ]]; then
  echo 'PASS: login HTML served over verified HTTPS (authentication not tested)'
  exit 0
fi
case "${http}" in
  30[12378]) echo 'UNVERIFIED: login redirects; destination intentionally not followed'; exit 2 ;;
  401|403) echo 'UNVERIFIED: authentication boundary responded; login page inaccessible anonymously'; exit 2 ;;
  *) echo 'FAIL: private HTTPS login not served'; exit 1 ;;
esac
