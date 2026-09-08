#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" &&
      "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" &&
      ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

MODE="${1:---check}"
REQUIRE_RUNNING="${TALOS_REQUIRE_RUNNING:-true}"
VM_NAMES=(taloscp01 taloswk01 taloswk02)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check) ;;
  *)
    fail "usage: bash scripts/truenas/verify-talos-vm-autostart.sh --check"
    ;;
esac

for command in midclt jq; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

payload="$(midclt call vm.query)"
failures=0

for name in "${VM_NAMES[@]}"; do
  count="$(
    jq --arg name "${name}" '[.[] | select(.name == $name)] | length' <<<"${payload}"
  )"
  if [[ "${count}" -ne 1 ]]; then
    printf '❌ %s expected exactly once, found %s\n' "${name}" "${count}" >&2
    failures=$((failures + 1))
    continue
  fi

  row="$(
    jq -c --arg name "${name}" '
      .[]
      | select(.name == $name)
      | {
          id,
          name,
          autostart,
          state: (.status.state // "UNKNOWN"),
          domain_state: (.status.domain_state // "UNKNOWN")
        }
    ' <<<"${payload}"
  )"
  autostart="$(jq -r '.autostart' <<<"${row}")"
  state="$(jq -r '.state' <<<"${row}")"

  printf '%s\n' "${row}" | jq .

  if [[ "${autostart}" != "true" ]]; then
    printf '❌ %s autostart is %s\n' "${name}" "${autostart}" >&2
    failures=$((failures + 1))
  fi

  if [[ "${REQUIRE_RUNNING}" == "true" && "${state}" != "RUNNING" ]]; then
    printf '❌ %s state is %s\n' "${name}" "${state}" >&2
    failures=$((failures + 1))
  fi
done

[[ "${failures}" -eq 0 ]] ||
  fail "Talos VM persistence gate failed with ${failures} issue(s)"

printf '✅ Talos VM persistence gate: all VMs autostart=true'
if [[ "${REQUIRE_RUNNING}" == "true" ]]; then
  printf ' and RUNNING'
fi
printf '\n'
