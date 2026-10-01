#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

# Shared compact/full diagnostic bootstrap.
# shellcheck source=scripts/lib/diagnostic.sh
source "$(dirname -- "${SCRIPT_DIR}")/lib/diagnostic.sh"
nabla_diagnostic_maybe_wrap "${BASH_SOURCE[0]}" "$@"

MODE="${1:---check}"
REQUIRE_RUNNING="${TALOS_REQUIRE_RUNNING:-true}"
VM_NAMES=(taloscp01 taloswk01 taloswk02)

case "${MODE}" in
  --check) ;;
  *)
    fail "usage: bash scripts/truenas/verify-talos-vm-autostart.sh --check"
    ;;
esac

require_commands midclt jq

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
