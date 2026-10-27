#!/usr/bin/env bash
# Read-only candidate-key authentication against TrueNAS central CrowdSec LAPI.
# No key on argv or output, no service/repository/PF mutations.
# --env probes an exported existing key WITHOUT creating a registration.
set -euo pipefail
SECRET_FILE="${CROWDSEC_SECRET_FILE:-/mnt/cpool/secrets/runtime/crowdsec/.env.secrets}"
LAPI="${CROWDSEC_CENTRAL_LAPI_URL:-http://172.17.0.24:8084}"
SOURCE='runtime'
KEY_ENV=''
if (($#)); then
  if [[ "$#" == 2 && "$1" == '--env' ]]; then
    SOURCE='environment'
    KEY_ENV="$2"
    case "$KEY_ENV" in
      CROWDSEC_BOUNCER_API_KEY|BOUNCER_KEY_PFSENSE_FIREWALL|BOUNCER_KEY_TRAEFIK) ;;
      *) echo 'central_candidate_auth=NO_GO_UNSUPPORTED_ENV_NAME'; exit 2 ;;
    esac
  else
    echo 'Usage: bash check-crowdsec-candidate-bouncer.sh [--env CROWDSEC_BOUNCER_API_KEY|BOUNCER_KEY_PFSENSE_FIREWALL|BOUNCER_KEY_TRAEFIK]'
    exit 2
  fi
fi
if [[ ! "$LAPI" =~ ^http://[A-Za-z0-9.:-]+$ ]]; then
  echo 'central_candidate_auth=NO_GO_INVALID_LAPI_URL'
  exit 2
fi
# Explicit executable path for hermetic tests. Production uses the normal
# resolved curl; no mock is enabled unless the invoking environment sets it.
CURL_BIN="${CROWDSEC_CURL_BIN:-curl}"
command -v "${CURL_BIN}" >/dev/null 2>&1 || {
  echo 'central_candidate_auth=NOT_VERIFIED_NO_CURL'
  exit 2
}

if [[ "$SOURCE" == 'environment' ]]; then
  # Must run in the invoking shell's exported environment, NOT through sudo
  # (sudo commonly drops these keys). Never print candidate values.
  key="${!KEY_ENV:-}"
  if [[ -z "$key" ]]; then
    echo 'central_candidate_auth=NO_GO_ENV_UNSET_OR_NOT_EXPORTED'
    exit 2
  fi
else
  if [[ ! -r "$SECRET_FILE" ]]; then
    echo 'central_candidate_auth=NO_GO_MISSING_SECRET_FILE'
    exit 2
  fi
  mode="$(stat -c %a -- "$SECRET_FILE" 2>/dev/null || true)"
  if [[ "$mode" != '600' ]]; then
    echo 'central_candidate_auth=NO_GO_SECRET_PERMISSIONS'
    exit 2
  fi
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
  ' "$SECRET_FILE")"
fi
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
  } | "${CURL_BIN}" --config -
)" || {
  unset key
  echo 'central_candidate_auth=NOT_VERIFIED_TRANSPORT'
  exit 1
}
unset key
case "${http_code}" in
  200)
    echo 'central_candidate_auth=ACCEPTED'
    if [[ "$SOURCE" == environment ]]; then echo 'central_candidate_identity=UNVERIFIED; authentication alone does not identify the registered bouncer'; fi
    exit 0 ;;

  401|403) echo 'central_candidate_auth=REJECTED'; exit 1 ;;
  *) echo "central_candidate_auth=NOT_VERIFIED_HTTP_${http_code}"; exit 1 ;;
esac
