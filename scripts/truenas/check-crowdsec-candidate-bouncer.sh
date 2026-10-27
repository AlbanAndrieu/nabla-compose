#!/usr/bin/env bash
# Read-only candidate-key authentication against TrueNAS central CrowdSec LAPI.
# No key on argv or output, no service/repository/PF mutations.
set -euo pipefail
SECRET_FILE="${CROWDSEC_SECRET_FILE:-/mnt/cpool/secrets/runtime/crowdsec/.env.secrets}"
LAPI="${CROWDSEC_CENTRAL_LAPI_URL:-http://172.17.0.24:8084}"
if [[ ! -r "${SECRET_FILE}" ]]; then
  echo 'central_candidate_auth=NO_GO_MISSING_SECRET_FILE'
  exit 2
fi
mode="$(stat -c %a -- "${SECRET_FILE}" 2>/dev/null || true)"
if [[ "${mode}" != '600' ]]; then
  echo 'central_candidate_auth=NO_GO_SECRET_PERMISSIONS'
  exit 2
fi
if [[ ! "${LAPI}" =~ ^http://[A-Za-z0-9.:-]+$ ]]; then
  echo 'central_candidate_auth=NO_GO_INVALID_LAPI_URL'
  exit 2
fi
command -v curl >/dev/null || { echo 'central_candidate_auth=NOT_VERIFIED_NO_CURL'; exit 2; }
key="$(awk '
  /^BOUNCER_KEY_PFSENSE_FIREWALL=/ {
    sub(/^[^=]*=/, "")
    sub(/\r$/, "")
    first=substr($0,1,1)
    last=substr($0,length($0),1)
    single=sprintf("%c",39)
    if (length($0)>=2 && first==last && (first=="\"" || first==single))
      $0=substr($0,2,length($0)-2)
    print
  }
' "${SECRET_FILE}")"
# Reject unsupported quoting, invalid multiline values or injection into
# curl config syntax; standard CrowdSec tokens use printable ASCII.
if [[ -z "${key}" || "${key}" == *$'\n'* || "${key}" == *$'\r'* || "${key}" == *'"'* || "${key}" == *'\'* || "${key}" =~ [[:cntrl:]] ]]; then
  unset key
  echo 'central_candidate_auth=NO_GO_INVALID_SECRET_FORMAT'
  exit 2
fi
http_code="$(
  {
    printf 'url = "%s/v1/decisions?ip=192.0.2.1"\n' "${LAPI}"
    printf 'header = "X-Api-Key: %s"\n' "${key}"
    printf 'output = "/dev/null"\n'
    printf 'silent\nshow-error\nconnect-timeout = 3\nmax-time = 8\n'
    printf 'write-out = "%%{http_code}"\n'
  } | curl --config -
)" || {
  unset key
  echo 'central_candidate_auth=NOT_VERIFIED_TRANSPORT'
  exit 1
}
unset key
case "${http_code}" in
  200) echo 'central_candidate_auth=ACCEPTED'; exit 0 ;;
  401|403) echo 'central_candidate_auth=REJECTED'; exit 1 ;;
  *) echo "central_candidate_auth=NOT_VERIFIED_HTTP_${http_code}"; exit 1 ;;
esac
