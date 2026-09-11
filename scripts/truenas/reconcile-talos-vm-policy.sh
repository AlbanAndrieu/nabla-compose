#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
TARGET_AUTOSTART="${TALOS_VM_AUTOSTART:-true}"
TARGET_SHUTDOWN_TIMEOUT="${TALOS_VM_SHUTDOWN_TIMEOUT:-180}"
VM_NAMES=(taloscp01 taloswk01 taloswk02)

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/reconcile-talos-vm-policy.sh [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in midclt jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ "${TARGET_AUTOSTART}" == "true" ]] ||
  fail "steady-state Talos VM policy requires TALOS_VM_AUTOSTART=true"
[[ "${TARGET_SHUTDOWN_TIMEOUT}" =~ ^[0-9]+$ ]] ||
  fail "TALOS_VM_SHUTDOWN_TIMEOUT must be an integer"
((TARGET_SHUTDOWN_TIMEOUT >= 5 && TARGET_SHUTDOWN_TIMEOUT <= 300)) ||
  fail "TALOS_VM_SHUTDOWN_TIMEOUT must be between 5 and 300 seconds"

query="$(midclt call vm.query)"
changes=0

for name in "${VM_NAMES[@]}"; do
  row="$(
    jq -ce --arg name "${name}" '
      [.[] | select(.name == $name)] |
      if length == 1 then
        .[0] | {
          id, name, autostart, shutdown_timeout,
          state: (.status.state // "UNKNOWN")
        }
      elif length == 0 then error("VM not found: " + $name)
      else error("VM name is ambiguous: " + $name)
      end
    ' <<<"${query}"
  )" || fail "unable to resolve ${name}"

  id="$(jq -r '.id' <<<"${row}")"
  autostart="$(jq -r '.autostart' <<<"${row}")"
  shutdown_timeout="$(jq -r '.shutdown_timeout' <<<"${row}")"
  printf '%s\n' "${row}" | jq .

  if [[ "${autostart}" == "${TARGET_AUTOSTART}" &&
        "${shutdown_timeout}" == "${TARGET_SHUTDOWN_TIMEOUT}" ]]; then
    printf 'OK: %s VM boot/shutdown policy already matches target\n' "${name}"
    continue
  fi

  changes=$((changes + 1))
  if [[ "${MODE}" == "--check" ]]; then
    printf 'DRIFT: %s target autostart=%s shutdown_timeout=%s\n' \
      "${name}" "${TARGET_AUTOSTART}" "${TARGET_SHUTDOWN_TIMEOUT}"
    continue
  fi

  printf 'APPLY: %s id=%s autostart=%s shutdown_timeout=%s\n' \
    "${name}" "${id}" "${TARGET_AUTOSTART}" "${TARGET_SHUTDOWN_TIMEOUT}"
  midclt call vm.update "${id}" "$(
    jq -nc \
      --argjson autostart "${TARGET_AUTOSTART}" \
      --argjson timeout "${TARGET_SHUTDOWN_TIMEOUT}" \
      '{autostart:$autostart, shutdown_timeout:$timeout}'
  )" >/dev/null
done

if [[ "${MODE}" == "--check" ]]; then
  if ((changes)); then
    fail "${changes} Talos VM(s) differ from the steady-state boot policy; run --apply after review"
  fi
  printf 'SUCCESS: all Talos VMs have autostart=true and shutdown_timeout=%ss\n' \
    "${TARGET_SHUTDOWN_TIMEOUT}"
  exit 0
fi

post="$(midclt call vm.query)"
for name in "${VM_NAMES[@]}"; do
  jq -e \
    --arg name "${name}" \
    --argjson timeout "${TARGET_SHUTDOWN_TIMEOUT}" '
      [.[] | select(
        .name == $name and
        .autostart == true and
        .shutdown_timeout == $timeout
      )] | length == 1
    ' <<<"${post}" >/dev/null ||
    fail "${name}: VM policy did not persist after vm.update"
done

printf 'SUCCESS: Talos VM boot policy converged live; keep OpenTofu as the declarative source of truth.\n'
