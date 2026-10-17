#!/usr/bin/env bash
# Read-only split-DNS / Cloudflare-publication / ingress-path diagnostic.
set -euo pipefail
[[ "${1:---check}" == "--check" && $# -le 1 ]] || { echo "usage: $0 --check" >&2; exit 2; }
for cmd in dig curl; do command -v "$cmd" >/dev/null || { echo "missing $cmd" >&2; exit 2; }; done
failed=0
check() {
  local name="$1" expected="$2" resolver="$3" answer
  answer="$(dig +time=2 +tries=1 +short @"$resolver" "$name" A 2>/dev/null | grep -E '^[0-9]+(\.[0-9]+){3}$' | sort -u | paste -sd, -)" || answer=""
  printf 'dns=%s name=%s A=%s\n' "$resolver" "$name" "${answer:-none}"
  if [[ "$answer" != "$expected" ]]; then
    printf 'FAIL expected=%s\n' "${expected:-none}"
    failed=$((failed+1))
  fi
}
echo '==> Private namespace: DefectDojo must not be public'
check defectdojo.int.albandrieu.com 172.17.0.24 172.17.0.24
check defectdojo.int.albandrieu.com 172.17.0.24 172.17.0.1
check defectdojo.int.albandrieu.com '' 1.1.1.1
echo '==> Public exception: Hello (observe without changing exposure)'
for resolver in 172.17.0.24 172.17.0.1 1.1.1.1; do
  answer="$(dig +time=2 +tries=1 +short @"$resolver" hello.int.albandrieu.com A 2>/dev/null || true)"
  printf 'dns=%s name=hello.int.albandrieu.com A=%s\n' "$resolver" "${answer:-none}"
done
echo '==> Direct private Traefik HTTPS with validated certificate'
code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 10 --resolve defectdojo.int.albandrieu.com:443:172.17.0.24 https://defectdojo.int.albandrieu.com/ 2>/dev/null)" || code=000
printf 'defectdojo_private_https=%s\n' "$code"
case "$code" in 200|301|302|303|307|308|401|403) ;; *) failed=$((failed+1));; esac
echo '==> Cloudflare API inventory (optional; uses existing protected audit)'
if [[ -n "${CF_ZONE_ID:-}" && -n "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  bash scripts/security/audit-public-int-dns.sh || failed=$((failed+1))
else
  echo 'SKIP authenticated Cloudflare inventory: CF_ZONE_ID/CLOUDFLARE_API_TOKEN not both present'
  echo 'Public DNS queries are not a complete Cloudflare zone inventory.'
fi
printf 'summary failures=%d\n' "$failed"
((failed == 0))
