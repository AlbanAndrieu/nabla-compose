#!/usr/bin/env bash
set -euo pipefail

ZONE_ID="${CF_ZONE_ID:-}"
API_TOKEN="${CLOUDFLARE_API_TOKEN:-}"
ALLOWLIST_FILE="${PUBLIC_INT_DNS_ALLOWLIST:-config/public-int-dns-exceptions.txt}"

command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || {
  echo "jq is required" >&2
  exit 1
}

[[ -n "${ZONE_ID}" ]] || {
  echo "CF_ZONE_ID is required" >&2
  exit 2
}
[[ -n "${API_TOKEN}" ]] || {
  echo "CLOUDFLARE_API_TOKEN is required" >&2
  exit 2
}
[[ -r "${ALLOWLIST_FILE}" ]] || {
  printf 'Allowlist is not readable: %s\n' "${ALLOWLIST_FILE}" >&2
  exit 2
}

payload="$(
  curl --fail --silent --show-error --max-time 45 \
    -H "Authorization: Bearer ${API_TOKEN}" \
    "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?per_page=500"
)"

success="$(jq -r '.success // false' <<<"${payload}")"
[[ "${success}" == "true" ]] || {
  jq -r '.errors[]? | [.code, .message] | @tsv' <<<"${payload}" >&2
  exit 2
}

records="$(
  jq -r '
    .result[]
    | select(.name | endswith(".int.albandrieu.com"))
    | [
        .id,
        .type,
        .name,
        .content,
        ((.proxied // false) | tostring)
      ]
    | @tsv
  ' <<<"${payload}"
)"

if [[ -z "${records}" ]]; then
  echo "✅ No public *.int.albandrieu.com DNS record exists in Cloudflare."
  exit 0
fi

declare -A allowed=()
while IFS= read -r host; do
  host="${host%%#*}"
  host="${host//[[:space:]]/}"
  [[ -n "${host}" ]] || continue
  allowed["${host}"]=1
done <"${ALLOWLIST_FILE}"

echo "Public Cloudflare *.int.albandrieu.com records:"
unexpected=0
while IFS=$'\t' read -r record_id record_type host content proxied; do
  [[ -n "${host}" ]] || continue
  status="UNEXPECTED"
  if [[ -n "${allowed[${host}]:-}" ]]; then
    status="TEMPORARY-EXCEPTION"
  else
    unexpected=$((unexpected + 1))
  fi
  printf '  %-20s %-5s %-45s -> %-32s proxied=%-5s %s\n' \
    "${record_id}" "${record_type}" "${host}" "${content}" "${proxied}" "${status}"
done <<<"${records}"

if ((unexpected > 0)); then
  printf '\n❌ Found %d unexpected public .int DNS record(s).\n' "${unexpected}" >&2
  echo "Remove them from Cloudflare or add only a reviewed, temporary exception." >&2
  exit 3
fi

echo
echo "⚠️ Only reviewed temporary public .int DNS exceptions remain."
