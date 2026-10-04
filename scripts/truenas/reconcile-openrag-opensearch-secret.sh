#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
OPENRAG_SECRET_FILE="${OPENRAG_SECRET_FILE:-/mnt/cpool/openrag/.env.secrets}"
OPENSEARCH_ENV_FILE="${OPENSEARCH_ENV_FILE:-/mnt/cpool/compose/nabla-compose/apps/opensearch/.env}"

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    printf 'usage: sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh [--check|--apply]\n'
    exit 0
    ;;
  *)
    fail "unknown mode: ${MODE}"
    ;;
esac

require_root "run as root on TrueNAS"
require_commands awk install mktemp stat grep

[[ -f "${OPENSEARCH_ENV_FILE}" ]] ||
  fail "OpenSearch env authority missing: ${OPENSEARCH_ENV_FILE}"
[[ -f "${OPENRAG_SECRET_FILE}" ]] ||
  fail "OpenRAG secret file missing: ${OPENRAG_SECRET_FILE}"

read_key() {
  local file="$1" key="$2"
  awk -F= -v key="${key}" '
    $1 == key {
      sub(/^[^=]*=/, "")
      print
      exit
    }
  ' "${file}"
}

authority_password="$(read_key "${OPENSEARCH_ENV_FILE}" OPENSEARCH_PASSWORD)"
openrag_password="$(read_key "${OPENRAG_SECRET_FILE}" OPENSEARCH_PASSWORD)"

[[ -n "${authority_password}" ]] ||
  fail "OpenSearch authority has empty/missing OPENSEARCH_PASSWORD"

if [[ -n "${openrag_password}" && "${openrag_password}" == "${authority_password}" ]]; then
  ok "OpenRAG OPENSEARCH_PASSWORD matches the OpenSearch runtime authority"
  exit 0
fi

if [[ "${MODE}" == "--check" ]]; then
  if [[ -z "${openrag_password}" ]]; then
    fail "OpenRAG OPENSEARCH_PASSWORD is missing/empty"
  fi
  fail "OpenRAG OPENSEARCH_PASSWORD differs from the OpenSearch runtime authority"
fi

tmp="$(mktemp /mnt/cpool/openrag/.env.secrets.tmp.XXXXXX)"
trap 'rm -f "${tmp}"' EXIT

awk -F= '
  $1 != "OPENSEARCH_PASSWORD" { print }
' "${OPENRAG_SECRET_FILE}" >"${tmp}"
printf 'OPENSEARCH_PASSWORD=%s\n' "${authority_password}" >>"${tmp}"

install -o root -g root -m 600 "${tmp}" "${OPENRAG_SECRET_FILE}"
rm -f "${tmp}"
trap - EXIT

unset authority_password openrag_password
ok "OpenRAG OPENSEARCH_PASSWORD reconciled without printing it"
