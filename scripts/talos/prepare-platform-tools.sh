#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
MODE="${1:---summary}"
KUBARA_WORKDIR="${KUBARA_WORKDIR:-${ROOT}}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

info() {
  printf 'ℹ️  %s\n' "$*"
}

ok() {
  printf '✅ %s\n' "$*"
}

warn() {
  printf '⚠️  %s\n' "$*" >&2
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/talos/prepare-platform-tools.sh [--summary|--strict]

Modes:
  --summary  read-only preparation report. Planned absence is not a failure.
  --strict   read-only final health gate. Vault, Falco and Kubara must all pass.

This script never mutates Kubernetes, Helm releases, Talos, TrueNAS, Docker,
network interfaces or routes. It deliberately remains independent from the
TrueNAS Docker/IPAM migration.

A successful --summary does NOT prove the dynamic CSI acceptance required by
Vault. That gate remains scripts/talos/smoke-truenas-csi-nfs.sh --apply.
EOF
}

case "${MODE}" in
  --summary | --strict) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

for script in \
  scripts/talos/validate-cluster.sh \
  scripts/talos/diagnose-security-posture.sh \
  scripts/talos/install-platform-tools.sh \
  scripts/talos/smoke-truenas-csi-nfs.sh; do
  [[ -x "${ROOT}/${script}" || -r "${ROOT}/${script}" ]] ||
    fail "required repository script missing: ${script}"
done

printf '🔎 Kubernetes/Talos base health\n'
DIAGNOSTIC_FULL_OUTPUT=1 bash "${ROOT}/scripts/talos/validate-cluster.sh"
ok "cluster validation, including effective PSA/PSS posture, passed"

if [[ "${MODE}" == "--strict" ]]; then
  printf '\n🔎 Strict platform tool health\n'
  KUBARA_WORKDIR="${KUBARA_WORKDIR}" \
    bash "${ROOT}/scripts/talos/install-platform-tools.sh" --check all
  ok "Vault, Falco and Kubara strict health gate passed"
  exit 0
fi

printf '\n🔎 Installation readiness\n'
preflight_rc=0
KUBARA_WORKDIR="${KUBARA_WORKDIR}" \
  bash "${ROOT}/scripts/talos/install-platform-tools.sh" --preflight all || preflight_rc=$?

printf '\n🔎 Current platform inventory\n'
status_rc=0
KUBARA_WORKDIR="${KUBARA_WORKDIR}" \
  bash "${ROOT}/scripts/talos/install-platform-tools.sh" --status all || status_rc=$?

printf '\n📋 Security-first installation plan\n'
if [[ "${preflight_rc}" -eq 0 ]]; then
  ok "static platform prerequisites are ready"
else
  warn "one or more static installation prerequisites are not ready; inspect the preflight output above"
fi

printf '⛔ Vault: BLOCKED_BY_CSI_ACCEPTANCE until the dynamic PVC/persistence/reclaim smoke succeeds\n'
if [[ "${preflight_rc}" -eq 0 ]]; then
  printf '✅ Falco: PREFLIGHT_READY; installation is independent from TrueNAS Docker/IPAM\n'
else
  printf '⚠️  Falco: inspect the eBPF/kernel preflight before installation\n'
fi

if [[ -f "${KUBARA_WORKDIR}/config.yaml" ]]; then
  printf '✅ Kubara: CONFIG_PRESENT; generation remains dry-run-first\n'
else
  printf '⏸️  Kubara: GATED_CONFIG_MISSING (%s/config.yaml)\n' "${KUBARA_WORKDIR}"
fi

cat <<'EOF'

Next sequence:
1. CSI: resume dynamic PVC provisioning diagnosis and require bind + cross-node persistence + reclaim acceptance.
2. Vault: install only after that dynamic CSI gate is green; never auto-init or expose recovery/unseal material.
3. Falco: install after its Talos/eBPF preflight; keep its privileged PSA namespace as a narrowly scoped runtime-sensor exception.
4. Kubara: keep generation dry-run-first; bootstrap only from reviewed config.yaml and reviewed Traefik exposure.
5. After installation, rerun this command with --strict.
EOF

if [[ "${status_rc}" -ne 0 ]]; then
  warn "at least one already-installed component is unhealthy; this is different from a planned NOT_INSTALLED state"
fi

# Summary mode intentionally accepts planned absence. It fails only when static
# installation prerequisites are not ready. Dynamic CSI acceptance is reported
# as a separate blocking gate and is never inferred from --check.
[[ "${preflight_rc}" -eq 0 ]] || exit "${preflight_rc}"
ok "platform preparation summary completed without cluster mutation"
