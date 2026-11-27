#!/usr/bin/env bash
# Scan TrueNAS datasets with the ClamAV Custom App, a night-window App.
# Starts clamav when stopped and waits for clamd, holds the App against the
# night-window stop while scanning (restore-optional-apps.sh defers it), prunes
# scan logs older than 90 days, then puts the App back in its prior state.
# Prints only infected files, errors and a one-line summary.
# Exit 0 clean, 1 infected files, 2 error. Run as root through cron-notify.sh.
#   clamav-scan.sh exposed|full
set -uo pipefail

APP=clamav
CONTAINER=ix-clamav-clamav-1
LOCK="${NABLA_APP_LOCK_DIR:-/run/lock}/nabla-app-${APP}.lock"
HOST_LOGS=/mnt/cpool/logs
# What comes from outside: SMB/NFS shares, mail, uploads, ISOs. The monthly full scan covers the rest.
EXPOSED=(ftp share www workspace bababou jenkins-slave home iso bichon openclaw immich openwebui)

mode="${1:-}"
case "${mode}" in
  exposed) paths=("${EXPOSED[@]/#//scandir/}") ;;
  full) paths=(/scandir) ;;
  *)
    echo "usage: clamav-scan.sh exposed|full" >&2
    exit 2
    ;;
esac
((EUID == 0)) || {
  echo "❌ run as root on TrueNAS" >&2
  exit 2
}

exec 9>"${LOCK}"
flock -n 9 || {
  echo "❌ another job holds ${LOCK}" >&2
  exit 2
}
rm -f "${LOCK}.stop-pending"

app_state() {
  midclt call app.query "[[\"id\",\"=\",\"${APP}\"]]" '{"select":["state"]}' | jq -r '.[0].state // "ABSENT"'
}

finish() {
  find "${HOST_LOGS}" -maxdepth 1 -type f -name 'clamav-scan-*.log' -mtime +90 -delete 2>/dev/null
  # Put the App back: stopped if it was, or if the night window ended meanwhile.
  if [[ "${was}" == STOPPED || -e "${LOCK}.stop-pending" ]]; then
    midclt call -j app.stop "${APP}" >/dev/null 2>&1 || echo "⚠️ app.stop ${APP} failed"
  fi
  rm -f "${LOCK}.stop-pending"
  exit "$1"
}

was="$(app_state)"
case "${was}" in
  RUNNING | DEPLOYING) ;;
  STOPPED) midclt call -j app.start "${APP}" >/dev/null 2>&1 || {
    echo "❌ app.start ${APP} failed"
    finish 2
  } ;;
  *)
    echo "❌ App ${APP} is ${was}"
    exit 2
    ;;
esac

# CLAMD_STARTUP_TIMEOUT is 1800 s: loading the signatures takes minutes.
if ! docker exec "${CONTAINER}" clamdscan --ping 120:15 >/dev/null 2>&1; then
  echo "❌ clamd did not answer within 30 min"
  finish 2
fi

out="$(mktemp)"
trap 'rm -f "${out}"' EXIT
log="/mnt/logs/clamav-scan-${mode}-$(date +%Y-%m-%d_%H-%M).log"
started=${SECONDS}
docker exec "${CONTAINER}" clamdscan --multiscan --fdpass --infected --log="${log}" "${paths[@]}" >"${out}" 2>&1
rc=$?
elapsed=$((SECONDS - started))

grep -vE '^(-+ SCAN SUMMARY -+|Infected files:|Total errors:|Time:|Start Date:|End Date:)|^[[:space:]]*$' "${out}"
infected="$(sed -n 's/^Infected files: *//p' "${out}" | tail -1)"
errors="$(sed -n 's/^Total errors: *//p' "${out}" | tail -1)"
if [[ "$(docker inspect -f '{{.State.OOMKilled}}' "${CONTAINER}" 2>/dev/null)" == true ]]; then
  echo "💥 clamd OOM-killed (mem_limit 2g)"
fi
case "${rc}" in
  0) icon=✅ ;;
  1) icon=🦠 ;;
  *) icon=❌ ;;
esac
echo "${icon} ClamAV ${mode} : ${infected:-?} infecté(s), ${errors:-0} erreur(s), $((elapsed / 3600))h$(printf '%02d' $((elapsed % 3600 / 60))) (${log#/mnt/logs/})"
((rc <= 2)) || rc=2
finish "${rc}"
