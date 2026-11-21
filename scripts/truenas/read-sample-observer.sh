#!/usr/bin/env bash
# Read-only keyed GET on FastAPI Sample's TrueNAS observer, run as root on the host.
# Since fastapi-sample #447 /api/homelab/status and /health answer 401 without
# X-Diagnostics-Key. The key comes from the runtime file and reaches curl only
# through a header file descriptor: never argv, never stdout.
set -euo pipefail

# shellcheck source=../lib/secrets.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/secrets.sh"

SECRETS_FILE="${SAMPLE_SECRETS_FILE:-/mnt/cpool/secrets/runtime/fastapisample/.env.secrets}"
BASE_URL="${SAMPLE_URL:-http://172.17.0.24:8091}"
path="${1:-/api/homelab/status}"

if [[ ! "${path}" =~ ^/api/[A-Za-z0-9/_.?=\&-]*$ ]]; then
  printf 'usage: sudo bash %s [/api/<read-only path>]\n' "$0" >&2
  exit 2
fi

secrets_assert_file "${SECRETS_FILE}" DIAGNOSTICS_ACCESS_KEY
key="$(secrets_get_value "${SECRETS_FILE}" DIAGNOSTICS_ACCESS_KEY)"
curl --fail --silent --show-error --max-time 30 \
  --header @<(secrets_curl_headers X-Diagnostics-Key "${key}") \
  "${BASE_URL}${path}"
