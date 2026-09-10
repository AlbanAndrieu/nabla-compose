#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" && "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" && ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"
CONTROL_PLANE_IP="${TALOS_CONTROL_PLANE_IP:-172.17.0.50}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

for command in talosctl kubectl grep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${TALOSCONFIG}" ]] || fail "Talos config not found: ${TALOSCONFIG}"
[[ -s "${KUBECONFIG}" ]] || fail "Kubeconfig not found: ${KUBECONFIG}"
export TALOSCONFIG KUBECONFIG

printf '🔎 Talos Pod Security Admission configuration on %s\n' "${CONTROL_PLANE_IP}"
if ! admission_yaml="$(
  talosctl -n "${CONTROL_PLANE_IP}" \
    get admissioncontrolconfigs.kubernetes.talos.dev \
    admission-control \
    -o yaml
)"; then
  fail "cannot read Talos admission-control configuration"
fi
printf '%s\n' "${admission_yaml}"

if grep -Eq '(^|[[:space:]])enforce:[[:space:]]*"?restricted"?([[:space:]]|$)' <<<"${admission_yaml}"; then
  ok "cluster default PSA enforcement is restricted"
elif grep -Eq '(^|[[:space:]])enforce:[[:space:]]*"?baseline"?([[:space:]]|$)' <<<"${admission_yaml}"; then
  ok "cluster default PSA enforcement is baseline (Talos default); restricted remains the hardening target"
else
  fail "cluster default PSA enforcement is weaker than the expected baseline/restricted posture"
fi

for mode in audit warn; do
  if grep -Eq "(^|[[:space:]])${mode}:[[:space:]]*\"?restricted\"?([[:space:]]|$)" <<<"${admission_yaml}"; then
    ok "cluster default PSA ${mode}=restricted"
  else
    fail "cluster default PSA ${mode} is not restricted"
  fi
done

printf '\n🔎 Namespace Pod Security labels (blank ENFORCE means inherit Talos defaults)\n'
kubectl get namespaces \
  -o custom-columns='NAMESPACE:.metadata.name,ENFORCE:.metadata.labels.pod-security\.kubernetes\.io/enforce,ENFORCE_VERSION:.metadata.labels.pod-security\.kubernetes\.io/enforce-version,AUDIT:.metadata.labels.pod-security\.kubernetes\.io/audit,WARN:.metadata.labels.pod-security\.kubernetes\.io/warn'

printf '\n🔎 Namespaces inheriting the Talos default PSA policy\n'
kubectl get namespaces \
  --selector='!pod-security.kubernetes.io/enforce' \
  -o custom-columns='NAMESPACE:.metadata.name' \
  --no-headers || true

printf '\n🔎 Explicit privileged namespace overrides\n'
privileged_namespaces="$(
  kubectl get namespaces \
    -l pod-security.kubernetes.io/enforce=privileged \
    -o custom-columns='NAMESPACE:.metadata.name' \
    --no-headers
)"
if [[ -n "${privileged_namespaces}" ]]; then
  printf '%s\n' "${privileged_namespaces}"
  printf '⚠️  every privileged namespace is a security boundary: restrict RBAC and document the justification\n'
else
  printf '<none>\n'
fi

printf '\n✅ Talos/Kubernetes Pod Security posture collected successfully\n'
