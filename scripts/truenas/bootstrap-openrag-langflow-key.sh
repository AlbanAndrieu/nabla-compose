#!/usr/bin/env bash
set -euo pipefail

LANGFLOW_CONTAINER="${LANGFLOW_CONTAINER:-langflow}"
OPENRAG_SECRET_FILE="${OPENRAG_SECRET_FILE:-/mnt/cpool/openrag/.env.secrets}"
LANGFLOW_KEY_NAME="${LANGFLOW_KEY_NAME:-openrag-global}"
rotate=false

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

if [[ "${1:-}" == "--rotate" ]]; then
  rotate=true
elif [[ -n "${1:-}" ]]; then
  fail "usage: sudo bash scripts/truenas/bootstrap-openrag-langflow-key.sh [--rotate]"
fi

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so the OpenRAG secret file remains root-owned"

for command in docker curl awk grep install mktemp; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

docker ps --format '{{.Names}}' |
  grep -Fxq "${LANGFLOW_CONTAINER}" ||
  fail "Langflow container is not running: ${LANGFLOW_CONTAINER}"

curl --fail --silent --show-error --max-time 8   http://172.17.0.24:7860/health_check >/dev/null ||
  fail "Langflow is not ready; require /health_check HTTP 200 before key bootstrap"

validate_key() {
  local key="$1"

  printf 'header = "x-api-key: %s"\n' "${key}" |
    curl --config -       --fail       --silent       --show-error       --max-time 8       http://172.17.0.24:7860/api/v1/users/whoami       >/dev/null
}

existing_key=""
if [[ -r "${OPENRAG_SECRET_FILE}" ]]; then
  existing_key="$(
    awk -F= '
      /^LANGFLOW_KEY=/ {
        sub(/^[^=]*=/, "")
        print
      }
    ' "${OPENRAG_SECRET_FILE}" |
      tail -n 1
  )"
  existing_key="${existing_key%\"}"
  existing_key="${existing_key#\"}"
  existing_key="${existing_key%\'}"
  existing_key="${existing_key#\'}"
fi

if [[ -n "${existing_key}" && "${rotate}" != "true" ]]; then
  if validate_key "${existing_key}"; then
    printf 'OK: existing OpenRAG LANGFLOW_KEY is accepted by global Langflow\n'
    exit 0
  fi
  fail "existing LANGFLOW_KEY is rejected; rerun with --rotate to replace it"
fi

new_key="$(
  docker exec -i "${LANGFLOW_CONTAINER}" python - "${LANGFLOW_KEY_NAME}" <<'PY'
import os
import sys

import requests

base = "http://127.0.0.1:7860"
name = sys.argv[1]
username = os.environ.get("LANGFLOW_SUPERUSER", "langflow")
password = os.environ.get("LANGFLOW_SUPERUSER_PASSWORD", "")

if not password:
    raise SystemExit("LANGFLOW_SUPERUSER_PASSWORD is empty inside Langflow")

session = requests.Session()

ready = session.get(f"{base}/health_check", timeout=8)
ready.raise_for_status()

login = session.post(
    f"{base}/api/v1/login",
    data={"username": username, "password": password},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=8,
)
login.raise_for_status()
token = login.json()["access_token"]

created = session.post(
    f"{base}/api/v1/api_key/",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    json={"name": name},
    timeout=8,
)
created.raise_for_status()
api_key = created.json()["api_key"]

whoami = session.get(
    f"{base}/api/v1/users/whoami",
    headers={"x-api-key": api_key},
    timeout=8,
)
whoami.raise_for_status()

print(api_key, end="")
PY
)"

[[ -n "${new_key}" ]] ||
  fail "Langflow returned an empty API key"

validate_key "${new_key}" ||
  fail "new Langflow API key failed validation"

secret_dir="$(dirname -- "${OPENRAG_SECRET_FILE}")"
install -d -o root -g root -m 700 "${secret_dir}"

tmp="$(mktemp "${secret_dir}/.env.secrets.tmp.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
chmod 600 "${tmp}"

if [[ -r "${OPENRAG_SECRET_FILE}" ]]; then
  awk '!/^LANGFLOW_KEY=/' "${OPENRAG_SECRET_FILE}" >"${tmp}"
fi

printf 'LANGFLOW_KEY=%s\n' "${new_key}" >>"${tmp}"
install -o root -g root -m 600 "${tmp}" "${OPENRAG_SECRET_FILE}"

unset new_key existing_key

printf 'OK: dedicated OpenRAG LANGFLOW_KEY stored in %s without printing it\n'   "${OPENRAG_SECRET_FILE}"
