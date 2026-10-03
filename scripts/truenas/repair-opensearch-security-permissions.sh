#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
DATA_DIR="${NABLA_OPENSEARCH_SECURITY_DATA_DIR:-/mnt/cpool/opensearch-security/data}"
EXPECTED_UID="${NABLA_OPENSEARCH_SECURITY_UID:-1000}"
EXPECTED_GID="${NABLA_OPENSEARCH_SECURITY_GID:-1000}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
usage:
  sudo bash scripts/truenas/repair-opensearch-security-permissions.sh --check
  sudo bash scripts/truenas/repair-opensearch-security-permissions.sh --apply

Ensures the bind-mounted OpenSearch Security datastore is recursively owned by
UID/GID 1000, matching docker.io/opensearchproject/opensearch:2.19.5.
EOF
    exit 0
    ;;
  *) fail "unsupported mode: ${MODE}" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root"
[[ "${EXPECTED_UID}" =~ ^[0-9]+$ ]] || fail "invalid expected UID"
[[ "${EXPECTED_GID}" =~ ^[0-9]+$ ]] || fail "invalid expected GID"

if [[ "${MODE}" == "--apply" ]]; then
  install -d -o "${EXPECTED_UID}" -g "${EXPECTED_GID}" -m 0750 "${DATA_DIR}"
  chown -R "${EXPECTED_UID}:${EXPECTED_GID}" "${DATA_DIR}"
  chmod 0750 "${DATA_DIR}"
fi

[[ -d "${DATA_DIR}" ]] || fail "data directory missing: ${DATA_DIR}"

owner="$(stat -c '%u:%g' "${DATA_DIR}")"
[[ "${owner}" == "${EXPECTED_UID}:${EXPECTED_GID}" ]] ||
  fail "${DATA_DIR}: owner=${owner}, expected=${EXPECTED_UID}:${EXPECTED_GID}"

mismatch="$(
  find "${DATA_DIR}" -xdev     \( ! -uid "${EXPECTED_UID}" -o ! -gid "${EXPECTED_GID}" \)     -print -quit
)"
[[ -z "${mismatch}" ]] ||
  fail "ownership mismatch remains under ${DATA_DIR}: ${mismatch}"

printf 'OK: OpenSearch Security storage owner=%s:%s path=%s\n'   "${EXPECTED_UID}" "${EXPECTED_GID}" "${DATA_DIR}"
