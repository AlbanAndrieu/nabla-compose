#!/usr/bin/env bash
set -euo pipefail

IMAGE="${AUTOKUMA_IMAGE:-ghcr.io/bigboot/autokuma:2.0.0}"
RUNTIME_DIR="${AUTOKUMA_RUNTIME_DIR:-/mnt/cpool/secrets/runtime/autokuma}"
SECRET_FILE="${AUTOKUMA_SECRET_FILE:-${RUNTIME_DIR}/.env.secrets}"
URL="${AUTOKUMA__KUMA__URL:-${UPTIME_KUMA_URL:-}}"
USERNAME="${AUTOKUMA__KUMA__USERNAME:-${UPTIME_KUMA_USERNAME:-}}"
TLS_VERIFY=true

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/bootstrap-autokuma-token.sh \
    --url <uptime-kuma-url> \
    --username <uptime-kuma-user> \
    [--tls-no-verify]

The password is requested interactively without echo. The resulting JWT is
stored in /mnt/cpool/secrets/runtime/autokuma/.env.secrets and is never printed.
The Uptime Kuma endpoint remains non-secret Compose configuration.
EOF
}

while (($# > 0)); do
  case "$1" in
    --url)
      (($# >= 2)) || fail "--url requires a value"
      URL="$2"
      shift 2
      ;;
    --username)
      (($# >= 2)) || fail "--username requires a value"
      USERNAME="$2"
      shift 2
      ;;
    --tls-no-verify)
      TLS_VERIFY=false
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      fail "unknown option: $1"
      ;;
  esac
done

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so the token file remains root-owned mode 0600"

for command in docker jq grep; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

[[ -n "${URL}" ]] ||
  fail "Uptime Kuma URL is required (--url or UPTIME_KUMA_URL)"
[[ -n "${USERNAME}" ]] ||
  fail "Uptime Kuma username is required (--username or UPTIME_KUMA_USERNAME)"
[[ "${URL}" != *$'\n'* && "${USERNAME}" != *$'\n'* ]] ||
  fail "URL/username must not contain newlines"

read -r -s -p "Uptime Kuma password for ${USERNAME}: " password
printf '\n'
[[ -n "${password}" ]] || fail "password must not be empty"

args=(
  run --rm
  --network intranet
  --entrypoint /usr/local/bin/kuma
  "${IMAGE}"
  --url "${URL}"
  --format json
)
if [[ "${TLS_VERIFY}" == "false" ]]; then
  args+=(--tls-no-verify)
fi
args+=(login "${USERNAME}" "${password}")

printf 'Requesting an Uptime Kuma JWT through the bundled kuma CLI...\n'
response="$(docker "${args[@]}")" || {
  unset password
  fail "Uptime Kuma login failed"
}
unset password

token="$(jq -er '.token | select(type == "string" and length > 0)' <<<"${response}")" ||
  fail "login succeeded without a usable JWT token"
unset response

install -d -o root -g root -m 700 "${RUNTIME_DIR}"
tmp="$(mktemp "${RUNTIME_DIR}/.env.secrets.XXXXXX")"
trap 'rm -f "${tmp:-}"' EXIT

if [[ -f "${SECRET_FILE}" ]]; then
  # Remove legacy URL/token/TLS entries before writing the canonical auth state.
  grep -Ev '^(AUTOKUMA__KUMA__(URL|AUTH_TOKEN|TLS__VERIFY))=' "${SECRET_FILE}" >"${tmp}" || true
fi

{
  printf 'AUTOKUMA__KUMA__AUTH_TOKEN=%s\n' "${token}"
  printf 'AUTOKUMA__KUMA__TLS__VERIFY=%s\n' "${TLS_VERIFY}"
} >>"${tmp}"
unset token

chown root:root "${tmp}"
chmod 600 "${tmp}"
mv -f "${tmp}" "${SECRET_FILE}"
trap - EXIT

grep -q '^AUTOKUMA__KUMA__AUTH_TOKEN=.' "${SECRET_FILE}" ||
  fail "JWT token was not persisted"
printf 'OK: AutoKuma JWT + TLS policy stored in %s without printing credentials\n' \
  "${SECRET_FILE}"
