#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${FASTAPI_SAMPLE_URL:-https://fastapi-sample.fastapicloud.dev}"
SICKZ_URL="${BASE_URL%/}/sickz"
DIAGNOSTICS_KEY="${FASTAPI_SAMPLE_DIAGNOSTICS_KEY:-}"

command -v curl >/dev/null 2>&1 || {
  echo "curl is required" >&2
  exit 1
}
command -v jq >/dev/null 2>&1 || {
  echo "jq is required" >&2
  exit 1
}

curl_args=(--fail --silent --show-error --max-time 45)
if [[ -n "${DIAGNOSTICS_KEY}" ]]; then
  curl_args+=(-H "X-Diagnostics-Key: ${DIAGNOSTICS_KEY}")
fi

payload="$(curl "${curl_args[@]}" "${SICKZ_URL}")"

observer_configured="$(jq -r '.cloudflare_observer_configured // false' <<<"${payload}")"
observer_error="$(jq -r '.cloudflare_observer_error // empty' <<<"${payload}")"
access_error="$(jq -r '.cloudflare_access_observer_error // empty' <<<"${payload}")"

if [[ "${observer_configured}" != "true" ]]; then
  echo "❌ FastAPI Sample Cloudflare observer is not configured." >&2
  exit 2
fi
if [[ -n "${observer_error}" || -n "${access_error}" ]]; then
  printf '❌ Cloudflare observer error: tunnel=%s access=%s\n'     "${observer_error:-none}" "${access_error:-none}" >&2
  exit 2
fi

echo "Cloudflare Tunnel/Access policy mismatches:"
jq -r '
  .checks
  | to_entries[]
  | select(.value.policy_status == "fail" or .value.policy_status == "warn")
  | select(
      (.value.policy_detail // "" | test("Cloudflare|Tunnel|Access"; "i"))
      or (.value.cloudflare_access_required == true)
      or (.value.cloudflare_tunnel_observed == true)
    )
  | [
      (.value.name // .key),
      (.value.policy_status // "unknown"),
      (.value.policy_detail // "no detail")
    ]
  | @tsv
' <<<"${payload}" |
  awk -F '\t' '{printf "  %-32s %-6s %s\n", $1, $2, $3}'

missing="$(
  jq -r '
    .checks
    | to_entries[]
    | select(.value.cloudflare_access_required == true)
    | select(
        (
          (.value.cloudflare_access_observed // false) != true
          and (.value.cloudflare_access_signal // false) != true
        )
        or (
          (.value.cloudflare_access_observed // false) == true
          and ((.value.cloudflare_access_policy_decisions // []) | length) == 0
        )
      )
    | .value.name // .key
  ' <<<"${payload}"
)"

public="$(
  jq -r '
    .checks
    | to_entries[]
    | select(.value.cloudflare_access_required == true)
    | select(.value.cloudflare_access_public == true)
    | .value.name // .key
  ' <<<"${payload}"
)"

if [[ -n "${missing}" ]]; then
  echo
  echo "❌ Access-required services with neither API-observed policy nor HTTP Access enforcement:"
  printf '  - %s\n' "${missing//
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  printf '  - %s\n' "${public//
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n'/
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  sed 's/^/  - /' <<<"${public}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n  - '}"
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  sed 's/^/  - /' <<<"${public}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n'/
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n'/
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  sed 's/^/  - /' <<<"${public}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n  - '}"
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  sed 's/^/  - /' <<<"${public}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n  - '}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n'/
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  sed 's/^/  - /' <<<"${public}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
\n  - '}"
fi

if [[ -n "${public}" ]]; then
  echo
  echo "❌ Access-required services with broad public/bypass policy:"
  sed 's/^/  - /' <<<"${public}"
fi

if [[ -n "${missing}" || -n "${public}" ]]; then
  exit 3
fi

echo
echo "✅ No missing or broadly public Cloudflare Access policy detected by FastAPI Sample."
