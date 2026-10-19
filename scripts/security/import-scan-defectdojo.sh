#!/usr/bin/env bash
# Submit SCA scan privately, with explicit approval and zero response-body logging.
set -euo pipefail
set +x

MODE="${1:---check}"
REPORT="${2:-}"
SCAN_TYPE="${DEFECTDOJO_SCAN_TYPE:-Trivy Scan}"
SERVICE_ID="${DEFECTDOJO_SERVICE_ID:-}"
ENGAGEMENT="${DEFECTDOJO_ENGAGEMENT_ID:-}"
TOKEN_FILE="${DEFECTDOJO_IMPORT_TOKEN_FILE:-/mnt/cpool/secrets/runtime/defectdojo/import-token}"
API="http://172.17.0.24:31085/api/v2/reimport-scan/"
# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"
case "${MODE}" in --check|--apply) ;; *) fail "usage: bash $0 [--check|--apply] /absolute/report.json" ;; esac
[[ -n "${REPORT}" && -f "${REPORT}" && ! -L "${REPORT}" && "${REPORT}" == /* ]] || fail "report must be an absolute regular path"
size="$(stat -c %s "${REPORT}")"
(( size > 0 && size <= 10000000 )) || fail "size must be within 1..10000000 bytes"
[[ "${SERVICE_ID}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || fail "DEFECTDOJO_SERVICE_ID required"
[[ "${ENGAGEMENT}" =~ ^[1-9][0-9]*$ ]] || fail "existing DEFECTDOJO_ENGAGEMENT_ID required (no auto-create)"
case "${SCAN_TYPE}" in
  "Trivy Scan"|"CodeQL Scan"|"Semgrep JSON Report"|"Nuclei Scan"|"Zed Attack Proxy") ;;
  *) fail "unsupported parser; verify in the installed edition" ;;
esac
python3 "$(dirname -- "${BASH_SOURCE[0]}")/validate-defectdojo-report.py" \
  --service "${SERVICE_ID}" --scan-type "${SCAN_TYPE}" --report "${REPORT}"
REPORT_MIME="application/json"
if [[ "${SCAN_TYPE}" == "Zed Attack Proxy" ]]; then
  [[ "${REPORT}" == *.xml ]] || fail "ZAP report must use .xml extension"
  REPORT_MIME="application/xml"
fi
printf 'CHECK: private API only; service=%s engagement=%s scan=%s\n' "${SERVICE_ID}" "${ENGAGEMENT}" "${SCAN_TYPE}"
printf 'CHECK: auto_create_context=false close_old_findings=false verified=false\n'
if [[ "${MODE}" == --check ]]; then
  printf 'INFO: dry-run, no network request or secret read\n'
  exit 0
fi
[[ "${EUID}" == 0 && "${DEFECTDOJO_IMPORT_APPROVED:-}" == YES ]] || fail "root and DEFECTDOJO_IMPORT_APPROVED=YES required"
command -v curl >/dev/null || fail "curl required"
# Fail closed outside the canonical TrueNAS host: the API is bound to its LAN
# address, not to loopback. Dataset presence alone does not prove host identity.
[[ -d /mnt/cpool/compose/nabla-compose ]] ||
  fail "import only from TrueNAS host; no remote fallback to a public endpoint"
command -v ip >/dev/null || fail "ip command required to confirm TrueNAS LAN identity"
ip -o -4 addr show | grep -Eq '[[:space:]]172[.]17[.]0[.]24/([0-9]{1,2})[[:space:]]' ||
  fail "TrueNAS LAN address 172.17.0.24 not assigned on this host"
[[ -f "${TOKEN_FILE}" && ! -L "${TOKEN_FILE}" && -s "${TOKEN_FILE}" ]] || fail "token file missing"
[[ "$(stat -c %u:%g "${TOKEN_FILE}")" == 0:0 && "$(stat -c %a "${TOKEN_FILE}")" == 600 ]] ||
  fail "token file must be root:root 0600"
token="$(<"${TOKEN_FILE}")"
[[ "${token}" =~ ^[a-zA-Z0-9_-]{24,}$ ]] || fail "invalid token format"
umask 077
config="$(mktemp)"
trap 'rm -f "$config"' EXIT
printf 'header = "Authorization: Token %s"\n' "${token}" > "${config}"
unset token
http="$(curl --config "${config}" --silent --show-error \
  --noproxy '*' --proto '=http' --max-redirs 0 \
  --connect-timeout 5 --max-time 90 \
  --output /dev/null --write-out '%{http_code}' \
  --request POST "${API}" \
  --form-string "engagement=${ENGAGEMENT}" \
  --form-string "scan_type=${SCAN_TYPE}" \
  --form-string "test_title=nabla-${SERVICE_ID}-${SCAN_TYPE}" \
  --form-string "minimum_severity=Info" \
  --form-string "verified=false" \
  --form-string "active=true" \
  --form-string "auto_create_context=false" \
  --form-string "close_old_findings=false" \
  --form "file=@${REPORT};type=${REPORT_MIME}")" || fail "private upload transport failed"
[[ "${http}" == 200 || "${http}" == 201 || "${http}" == 202 ]] || fail "import HTTP ${http} (response suppressed)"
printf 'OK: DefectDojo accepted upload HTTP %s; verify scan processing in private UI\n' "${http}"
