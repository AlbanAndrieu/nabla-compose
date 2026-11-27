#!/usr/bin/env bash
# Submit SCA scan privately, with explicit approval and zero response-body logging.
set -euo pipefail
set +x

MODE="${1:---check}"
REPORT="${2:-}"
SCAN_TYPE="${DEFECTDOJO_SCAN_TYPE:-Trivy Scan}"
ZAP_IMPORT_PROFILE="${DEFECTDOJO_ZAP_IMPORT_PROFILE:-minimal}"
SERVICE_ID="${DEFECTDOJO_SERVICE_ID:-}"
ENGAGEMENT="${DEFECTDOJO_ENGAGEMENT_ID:-}"
TOKEN_FILE="${DEFECTDOJO_IMPORT_TOKEN_FILE:-/mnt/cpool/secrets/runtime/defectdojo/import-token}"
API="http://172.17.0.24:31085/api/v2/reimport-scan/"
TRANSPORT=(--proto '=http')
# FastAPI native image imports use verified TLS/SNI at the existing LAN ingress.
if [[ "${SERVICE_ID}" == fastapi-sample-image || "${SERVICE_ID}" == ctem-mail || "${ZAP_IMPORT_PROFILE}" == private-native ]]; then
  API="https://defectdojo.int.albandrieu.com/api/v2/reimport-scan/"
  TRANSPORT=(--proto '=https' --resolve 'defectdojo.int.albandrieu.com:443:172.17.0.24')
fi
# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"
case "${MODE}" in --check|--apply) ;; *) fail "usage: bash $0 [--check|--apply] /absolute/report.json" ;; esac
[[ -n "${REPORT}" && -f "${REPORT}" && ! -L "${REPORT}" && "${REPORT}" == /* ]] || fail "report must be an absolute regular path"
size="$(stat -c %s "${REPORT}")"
MAX_REPORT_BYTES=10000000
[[ "${ZAP_IMPORT_PROFILE}" != private-native ]] || MAX_REPORT_BYTES=100000000
(( size > 0 && size <= MAX_REPORT_BYTES )) || fail "report size outside the configured profile limit"
[[ "${SERVICE_ID}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || fail "DEFECTDOJO_SERVICE_ID required"
[[ "${ENGAGEMENT}" =~ ^[1-9][0-9]*$ ]] || fail "existing DEFECTDOJO_ENGAGEMENT_ID required (no auto-create)"
case "${ZAP_IMPORT_PROFILE}" in minimal|private-native) ;; *) fail "unsupported ZAP evidence profile" ;; esac
case "${SCAN_TYPE}" in
  "Trivy Scan"|"CodeQL Scan"|"Semgrep JSON Report"|"Nuclei Scan"|"ZAP Scan"|"Generic Findings Import") ;;
  *) fail "unsupported parser; verify in the installed edition" ;;
esac
VALIDATE_OPTIONS=()
if [[ "${ZAP_IMPORT_PROFILE}" == private-native ]]; then
  [[ "${SCAN_TYPE}" == "ZAP Scan" && "${SERVICE_ID}" == nabla-site-alban ]] ||
    fail "private native ZAP is restricted to nabla-site-alban/ZAP Scan"
  PRIVATE_ZAP_DIR=/mnt/cpool/defectdojo/private-zap/site-alban
  [[ "${REPORT}" == "${PRIVATE_ZAP_DIR}/"*".xml" ]] ||
    fail "private native ZAP XML must be staged in the dedicated TrueNAS inbox"
  [[ "$(realpath -e -- "${REPORT}")" == "${REPORT}" ]] || fail "native ZAP path must be canonical"
  [[ -d "${PRIVATE_ZAP_DIR}" && ! -L "${PRIVATE_ZAP_DIR}" ]] || fail "private ZAP inbox missing"
  [[ "$(stat -c %u:%g "${PRIVATE_ZAP_DIR}")" == 0:0 && "$(stat -c %a "${PRIVATE_ZAP_DIR}")" == 700 ]] ||
    fail "private ZAP inbox must be root:root 0700"
  [[ "$(stat -c %u:%g "${REPORT}")" == 0:0 && "$(stat -c %a "${REPORT}")" == 600 ]] ||
    fail "native ZAP report must be root:root 0600"
  VALIDATE_OPTIONS+=(--private-zap-native)
fi
python3 "$(dirname -- "${BASH_SOURCE[0]}")/validate-defectdojo-report.py" \
  --service "${SERVICE_ID}" --scan-type "${SCAN_TYPE}" --report "${REPORT}" "${VALIDATE_OPTIONS[@]}"
REPORT_MIME="application/json"
if [[ "${SCAN_TYPE}" == "ZAP Scan" ]]; then
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
if [[ "${ZAP_IMPORT_PROFILE}" == private-native ]]; then
  [[ "${DEFECTDOJO_PRIVATE_ZAP_APPROVED:-}" == YES ]] ||
    fail "private native ZAP evidence requires DEFECTDOJO_PRIVATE_ZAP_APPROVED=YES"
fi
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
response_tmp="$(mktemp)"
trap 'rm -f "$config" "$response_tmp"' EXIT
printf 'header = "Authorization: Token %s"\n' "${token}" > "${config}"
unset token

# Preserve API response on TrueNAS: HTTP accepted is not necessarily processed.
RECEIPT_FILE="$(printenv DEFECTDOJO_IMPORT_RECEIPT_FILE || true)"
if [[ -n "${RECEIPT_FILE}" ]]; then
  [[ "${ZAP_IMPORT_PROFILE}" == private-native ]] || fail "receipt mode reserved for private-native ZAP"
  if [[ ! "${RECEIPT_FILE}" =~ ^/mnt/cpool/defectdojo/private-zap/site-alban/runs/[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}/defectdojo-response(-retry-[a-f0-9]{8})?[.]json$ ]]; then
    fail "receipt path outside the private archive"
  fi
  [[ ! -e "${RECEIPT_FILE}" && ! -L "${RECEIPT_FILE}" ]] || fail "receipt already exists"
  receipt_dir="$(dirname -- "${RECEIPT_FILE}")"
  [[ -d "${receipt_dir}" && ! -L "${receipt_dir}" ]] || fail "receipt directory invalid"
  [[ "$(stat -c %u:%g "${receipt_dir}")" == 0:0 && "$(stat -c %a "${receipt_dir}")" == 700 ]] ||
    fail "receipt directory must be root:root 0700"
fi

http="$(curl --config "${config}" --silent --show-error \
  --noproxy '*' "${TRANSPORT[@]}" --max-redirs 0 \
  --connect-timeout 5 --max-time 180 \
  --output "${response_tmp}" --write-out '%{http_code}' \
  --request POST "${API}" \
  --form-string "engagement=${ENGAGEMENT}" \
  --form-string "scan_type=${SCAN_TYPE}" \
  --form-string "test_title=nabla-${SERVICE_ID}-${SCAN_TYPE}" \
  --form-string "minimum_severity=Info" \
  --form-string "verified=false" \
  --form-string "active=true" \
  --form-string "background_import=false" \
  --form-string "auto_create_context=false" \
  --form-string "close_old_findings=false" \
  --form "file=@${REPORT};type=${REPORT_MIME}")" || fail "private upload transport failed"

if [[ -n "${RECEIPT_FILE}" ]]; then
  [[ -s "${response_tmp}" ]] || fail "empty DefectDojo response; report retained"
  cp --no-clobber -- "${response_tmp}" "${RECEIPT_FILE}"
  chmod 0600 "${RECEIPT_FILE}"
fi
[[ "${http}" == 200 || "${http}" == 201 || "${http}" == 202 ]] ||
  fail "DefectDojo API returned HTTP ${http}; private response retained when configured"

if [[ -n "${RECEIPT_FILE}" ]]; then
  python3 - "${RECEIPT_FILE}" <<'PY'
import json
from pathlib import Path
import sys
try:
    obj = json.loads(Path(sys.argv[1]).read_text(encoding="utf8"))
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    test_id = obj.get("test_id", obj.get("test", "unknown"))
    asynchronous = obj.get("background_import", False)
    state = obj.get("status", "SYNCHRONOUS_OR_UNKNOWN")
    approved = {"Processed", "Processing", "Failed", "Post Processing - Deduplication",
                "Post Processing - False Positive History"}
    print("RECEIPT: test_id=%s background_import=%s status=%s" %
          (test_id if isinstance(test_id, int) else "unknown",
           asynchronous is True, state if state in approved else "unverified"))
except (ValueError, OSError):
    print("RECEIPT: response unreadable; API accepted but status must be checked")
PY
fi
printf 'API_ACCEPTED: DefectDojo HTTP %s; verify findings and background Test status\n' "${http}"
