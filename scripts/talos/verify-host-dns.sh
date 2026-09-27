#!/usr/bin/env bash
set -euo pipefail

TALOSCTL="${NABLA_TALOSCTL:-/mnt/cpool/tools/bin/talosctl}"
TALOSCONFIG="${NABLA_TALOSCONFIG:-${HOME}/.config/nabla/talos/talosconfig}"
ENDPOINT="${NABLA_TALOS_ENDPOINT:-172.17.0.50}"
EXPECTED_DNS="${NABLA_TALOS_EXPECTED_DNS:-172.17.0.1}"
NODES=(172.17.0.50 172.17.0.51 172.17.0.52)

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -x "${TALOSCTL}" ]] || fail "talosctl not executable: ${TALOSCTL}"
[[ -r "${TALOSCONFIG}" ]] || fail "talosconfig not readable: ${TALOSCONFIG}"

for node in "${NODES[@]}"; do
  printf '=== Talos DNS %s ===\n' "${node}"

  resolver_out="$(
    TALOSCONFIG="${TALOSCONFIG}" "${TALOSCTL}"       --endpoints "${ENDPOINT}"       --nodes "${node}"       get resolvers
  )"
  printf '%s\n' "${resolver_out}"

  resolver_list="$(
    awk 'NR > 1 && $3 == "ResolverStatus" {print $6; exit}' <<<"${resolver_out}"
  )"
  [[ "${resolver_list}" == "[\"${EXPECTED_DNS}\"]" ]] ||
    fail "${node}: resolver drift expected=[\"${EXPECTED_DNS}\"] observed=${resolver_list:-MISSING}"

  upstream_out="$(
    TALOSCONFIG="${TALOSCONFIG}" "${TALOSCTL}"       --endpoints "${ENDPOINT}"       --nodes "${node}"       get dnsupstream
  )"
  printf '%s\n' "${upstream_out}"

  awk -v expected="${EXPECTED_DNS}:53" '
    NR > 1 && $3 == "DNSUpstream" && $6 == "true" && $7 == expected {
      found=1
    }
    END { exit(found ? 0 : 1) }
  ' <<<"${upstream_out}" ||
    fail "${node}: expected healthy DNS upstream ${EXPECTED_DNS}:53"

  printf 'OK: %s uses healthy DNS upstream %s:53\n' "${node}" "${EXPECTED_DNS}"
done

echo "SUCCESS: Talos host DNS is independent from TrueNAS-hosted Pi-hole"
