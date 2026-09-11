#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
case "${MODE}" in
  --check | --apply) shift || true ;;
  *) printf 'ERROR: usage: %s [--check [APP...]] | [--apply APP...]\n' "$0" >&2; exit 1 ;;
esac

WAIT_SECONDS="${TRUENAS_APP_RECONCILE_WAIT_SECONDS:-300}"
MAX_APPLY_APPS="${TRUENAS_APP_RECONCILE_MAX_APPS:-6}"
ALLOW_IMAGE_UPDATES="${TRUENAS_APP_RECONCILE_ALLOW_IMAGE_UPDATES:-0}"
CALL_TIMEOUT="${TRUENAS_APP_RECONCILE_CALL_TIMEOUT:-45}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in midclt jq docker date timeout; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

if [[ "${MODE}" == "--apply" ]]; then
  (($# > 0)) || fail "--apply requires one or more explicit application names"
  (($# <= MAX_APPLY_APPS)) ||
    fail "refusing to reconcile $# apps in one batch; limit=${MAX_APPLY_APPS}"
fi

bounded_midclt() {
  timeout "${CALL_TIMEOUT}" midclt call "$@"
}

umask 077
stamp="$(date +%Y%m%d-%H%M%S)"
report="/tmp/truenas-app-reconcile-${stamp}.log"
before="/tmp/truenas-app-reconcile-${stamp}.before.json"
after="/tmp/truenas-app-reconcile-${stamp}.after.json"
exec > >(tee -a "${report}") 2>&1

bounded_midclt app.query >"${before}" ||
  fail "app.query timed out after ${CALL_TIMEOUT}s"
printf 'TrueNAS post-IPAM app reconciliation mode=%s report=%s\n' "${MODE}" "${report}"
jq -r 'group_by(.state) | map({state:.[0].state,count:length})' "${before}"

resolve_live() {
  local requested="$1"
  bounded_midclt app.query |
    jq -ce --arg app "${requested}" '
      [.[] | select(.id == $app or .name == $app)] |
      if length == 1 then
        .[0] | {
          id, name, state, action_required, error_reason,
          image_updates_available, upgrade_available
        }
      elif length == 0 then error("application not found: " + $app)
      else error("ambiguous application: " + $app)
      end
    '
}

print_networks() {
  local app_id="$1" entry network
  # Network detail is diagnostic only. app.get_instance can be slow while the
  # middleware is reconciling many Apps, so never fail a read-only check merely
  # because this optional expansion times out.
  if ! entry="$(bounded_midclt app.get_instance "${app_id}" 2>/dev/null)"; then
    printf '  WARN: app.get_instance timed out/unavailable; network detail skipped\n'
    return 0
  fi

  mapfile -t networks < <(
    jq -r '.active_workloads.networks[]?.Name // empty' <<<"${entry}" |
      sort -u
  )
  ((${#networks[@]})) || { printf '  networks: none reported\n'; return 0; }

  printf '  networks:\n'
  for network in "${networks[@]}"; do
    if docker network inspect "${network}" >/dev/null 2>&1; then
      docker network inspect "${network}" |
        jq -r '.[0] |
          "    \(.Name)\t" +
          ([.IPAM.Config[]?.Subnet // empty] | join(",")) +
          "\tendpoints=" + ((.Containers // {} | length) | tostring)'
    else
      printf '    %s\t(unavailable)\n' "${network}"
    fi
  done
}

wait_terminal() {
  local app_id="$1" deadline=$((SECONDS + WAIT_SECONDS)) state
  while ((SECONDS < deadline)); do
    if ! state="$(resolve_live "${app_id}" | jq -r '.state')"; then
      printf '  WARN: transient app.query timeout while waiting for %s\n' "${app_id}" >&2
      sleep 5
      continue
    fi
    case "${state}" in
      RUNNING | CRASHED | STOPPED | ERROR) printf '%s\n' "${state}"; return 0 ;;
      DEPLOYING | STOPPING) sleep 5 ;;
      *) fail "${app_id}: unexpected state ${state}" ;;
    esac
  done
  fail "${app_id}: no terminal state within ${WAIT_SECONDS}s"
}

if [[ "${MODE}" == "--check" && "$#" -eq 0 ]]; then
  printf '\nNon-converged applications:\n'
  jq -r '
    .[] |
    select(.state=="CRASHED" or .state=="DEPLOYING" or .state=="ERROR" or .state=="STOPPING") |
    [.id,.state,(.image_updates_available//false),(.action_required//false),(.error_reason//"-")] |
    @tsv
  ' "${before}" | sort -k2,2 -k1,1
  printf '\nREAD-ONLY: no application or network was modified.\n'
  exit 0
fi

for requested in "$@"; do
  resolved="$(resolve_live "${requested}")" ||
    fail "unable to resolve ${requested}; middleware call timed out or app is ambiguous"
  app_id="$(jq -r '.id' <<<"${resolved}")"
  state="$(jq -r '.state' <<<"${resolved}")"
  action_required="$(jq -r '.action_required // false' <<<"${resolved}")"
  image_updates="$(jq -r '.image_updates_available // false' <<<"${resolved}")"

  printf '\nAPP %s state=%s image_updates=%s action_required=%s\n' \
    "${app_id}" "${state}" "${image_updates}" "${action_required}"
  print_networks "${app_id}"
  [[ "${MODE}" == "--check" ]] && continue

  case "${state}" in
    RUNNING) printf '  SKIP: already RUNNING\n' ;;
    STOPPED) printf '  SKIP: STOPPED is never auto-started\n' ;;
    ERROR) fail "${app_id}: ERROR requires diagnosis; no redeploy attempted" ;;
    DEPLOYING | STOPPING)
      printf '  WAIT: already transitioning; no overlapping redeploy\n'
      state="$(wait_terminal "${app_id}")"
      [[ "${state}" == "RUNNING" ]] ||
        fail "${app_id}: transition ended in ${state}"
      ;;
    CRASHED)
      [[ "${action_required}" != "true" ]] ||
        fail "${app_id}: action_required=true; manual review required"
      if [[ "${image_updates}" == "true" && "${ALLOW_IMAGE_UPDATES}" != "1" ]]; then
        fail "${app_id}: image update available; app.redeploy pulls images. Review first or explicitly set TRUENAS_APP_RECONCILE_ALLOW_IMAGE_UPDATES=1"
      fi
      printf '  APPLY: app.redeploy %s\n' "${app_id}"
      bounded_midclt -j app.redeploy "${app_id}" ||
        fail "${app_id}: app.redeploy timed out/failed"
      state="$(wait_terminal "${app_id}")"
      [[ "${state}" == "RUNNING" ]] ||
        fail "${app_id}: redeploy ended in ${state}"
      printf '  OK: %s -> RUNNING\n' "${app_id}"
      print_networks "${app_id}"
      ;;
    *) fail "${app_id}: unsupported state ${state}" ;;
  esac
done

bounded_midclt app.query >"${after}" ||
  fail "final app.query timed out after ${CALL_TIMEOUT}s"
printf '\nApplication states after batch:\n'
jq -r 'group_by(.state) | map({state:.[0].state,count:length})' "${after}"
printf 'after=%s\n' "${after}"
printf 'SUCCESS: bounded reconciliation finished; no STOPPED app was started and no Docker network was pruned.\n'
