#!/usr/bin/env bash
set -euo pipefail

RUNTIME_CONFIG="${PFSENSE_EXPORTER_CONFIG:-/mnt/cpool/prometheus/secrets/pfsense-exporter.yml}"
PFSENSE_URL="${PFSENSE_EXPORTER_AUTH_URL:-https://172.17.0.1:10443}"
ENDPOINT="${PFSENSE_EXPORTER_AUTH_ENDPOINT:-/api/v2/status/services}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

for command in python3 curl mktemp; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -f "${RUNTIME_CONFIG}" ]] || fail "runtime config must be a regular file: ${RUNTIME_CONFIG}"
[[ -s "${RUNTIME_CONFIG}" ]] || fail "runtime config is empty: ${RUNTIME_CONFIG}"
[[ -r "${RUNTIME_CONFIG}" ]] || fail "runtime config is not readable; run with sudo if it is root-owned mode 0600"

umask 077
HEADER_FILE="$(mktemp /tmp/pfsense-exporter-auth.XXXXXX)"
cleanup() {
  rm -f "${HEADER_FILE}"
}
trap cleanup EXIT HUP INT TERM

python3 - "${RUNTIME_CONFIG}" "${HEADER_FILE}" <<'PY'
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

runtime = Path(sys.argv[1])
header = Path(sys.argv[2])
text = runtime.read_text(encoding="utf-8")
match = re.search(
    r"^[ \t]*key:[ \t]*[\"']?([^\"'\r\n]+)[\"']?[ \t]*$",
    text,
    flags=re.MULTILINE,
)
if not match:
    raise SystemExit("runtime config has no usable key field")

key = match.group(1).strip()
placeholder = "REPLACE_WITH_DEDICATED_PFSENSE_EXPORTER_API_KEY"
if not key or key == placeholder:
    raise SystemExit("runtime config still contains an empty/placeholder API key")
if "\n" in key or "\r" in key:
    raise SystemExit("runtime API key contains an invalid newline")

fd = os.open(header, os.O_WRONLY | os.O_TRUNC)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    handle.write(f"X-API-Key: {key}\n")
os.chmod(header, 0o600)
PY

url="${PFSENSE_URL%/}${ENDPOINT}"
printf 'INFO: pfSense exporter auth preflight endpoint=%s\n' "${ENDPOINT}"
printf 'INFO: exactly one authenticated request will be sent; response body and key are suppressed\n'

set +e
status="$(
  curl --silent --show-error --insecure \
    --connect-timeout 3 --max-time 8 \
    --output /dev/null \
    --write-out '%{http_code}' \
    --header "@${HEADER_FILE}" \
    "${url}"
)"
curl_rc=$?
set -e

if [[ "${curl_rc}" -ne 0 ]]; then
  printf 'ERROR: pfSense exporter auth preflight transport failed curl_exit=%s; no retry performed\n' "${curl_rc}" >&2
  exit 3
fi

case "${status}" in
  200)
    printf 'OK: pfSense exporter runtime key is accepted and authorized for %s\n' "${ENDPOINT}"
    ;;
  401)
    printf 'ERROR: pfSense exporter runtime key was rejected (HTTP 401); stop repeated scrapes and reconcile/rotate the runtime key before retrying\n' >&2
    exit 4
    ;;
  403)
    printf 'ERROR: pfSense exporter runtime key authenticated but is not authorized for %s (HTTP 403)\n' "${ENDPOINT}" >&2
    exit 5
    ;;
  *)
    printf 'ERROR: pfSense exporter auth preflight returned unexpected HTTP %s for %s\n' "${status}" "${ENDPOINT}" >&2
    exit 6
    ;;
esac
