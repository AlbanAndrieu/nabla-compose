#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/talos/lib/client-config.sh
source "${ROOT}/scripts/talos/lib/client-config.sh"
nabla_resolve_talos_client_config "${ROOT}"

MODE="--check"
TARGET="all"
for arg in "$@"; do
  case "${arg}" in
    --preflight | --status | --check | --apply) MODE="${arg}" ;;
    all | vault | falco | kubara) TARGET="${arg}" ;;
    -h | --help)
      cat <<'EOF'
Usage:
  bash scripts/talos/install-platform-tools.sh [--preflight|--status|--check|--apply] [all|vault|falco|kubara]

Modes:
  --preflight  read-only installation-readiness checks; planned absence is not a failure
  --status     read-only inventory; missing planned components are reported, installed unhealthy components fail
  --check      strict read-only health gate; selected components must be installed and healthy
  --apply      install/reconcile exactly one explicit target; "all" is intentionally rejected

Safety gates:
  * Vault apply proves TrueNAS CSI dynamic persistence/reclaim first.
  * Vault is never automatically initialized or unsealed by this script.
  * Vault enforces PSS Restricted; no privileged namespace exception is expected.
  * Falco uses a dedicated privileged PSA namespace but modern eBPF least-privilege mode.
  * Kubara apply is generate --helm --dry-run unless KUBARA_ALLOW_BOOTSTRAP=1.
  * No Kubernetes platform check depends on TrueNAS Docker bridge/IPAM subnets.

Environment:
  K8S_PLATFORM_SKIP_CSI_SMOKE=1  emergency-only skip of Vault's disposable CSI acceptance
  KUBARA_ALLOW_BOOTSTRAP=1       explicitly permit Kubara bootstrap
  KUBARA_CLUSTER_NAME=name       cluster name required with bootstrap permission
  KUBARA_WORKDIR=path            directory containing reviewed Kubara config.yaml
EOF
      exit 0
      ;;
    *)
      printf '❌ unknown argument: %s\n' "${arg}" >&2
      exit 2
      ;;
  esac
done

VERSIONS_FILE="${K8S_PLATFORM_VERSIONS_FILE:-${ROOT}/config/kubernetes-tools/versions.env}"
KUBARA_VERSION_FILE="${KUBARA_VERSION_FILE:-${ROOT}/config/kubara/VERSION}"
VAULT_VALUES="${VAULT_VALUES:-${ROOT}/kubernetes/platform-tools/vault-values.yaml}"
FALCO_VALUES="${FALCO_VALUES:-${ROOT}/kubernetes/platform-tools/falco-values.yaml}"
PSA_VERSION="${K8S_PLATFORM_PSA_VERSION:-v1.36}"
VAULT_NAMESPACE="${VAULT_NAMESPACE:-vault}"
FALCO_NAMESPACE="${FALCO_NAMESPACE:-falco}"
KUBARA_WORKDIR="${KUBARA_WORKDIR:-${ROOT}}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '⚠️  %s\n' "$*" >&2
}

info() {
  printf 'ℹ️  %s\n' "$*"
}

ok() {
  printf '✅ %s\n' "$*"
}

[[ -r "${VERSIONS_FILE}" ]] || fail "missing versions file: ${VERSIONS_FILE}"
[[ -r "${KUBARA_VERSION_FILE}" ]] || fail "missing Kubara version pin: ${KUBARA_VERSION_FILE}"
[[ -r "${VAULT_VALUES}" ]] || fail "missing Vault values: ${VAULT_VALUES}"
[[ -r "${FALCO_VALUES}" ]] || fail "missing Falco values: ${FALCO_VALUES}"
# shellcheck disable=SC1090
source "${VERSIONS_FILE}"
KUBARA_VERSION="$(tr -d '[:space:]' <"${KUBARA_VERSION_FILE}")"
export KUBECONFIG

for command in kubectl helm kubara jq grep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"

if [[ "${MODE}" == "--apply" && "${TARGET}" == "all" ]]; then
  fail "--apply requires an explicit target: vault, falco, or kubara"
fi

cluster_check() {
  local nodes ready total
  kubectl get --raw='/readyz' >/dev/null || fail "Kubernetes API /readyz failed"
  nodes="$(kubectl get nodes -o json)"
  total="$(jq '.items | length' <<<"${nodes}")"
  ready="$(
    jq '[.items[] | select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))] | length' <<<"${nodes}"
  )"
  ((total >= 3)) || fail "expected at least 3 cluster nodes, found ${total}"
  [[ "${ready}" -eq "${total}" ]] ||
    fail "not all Kubernetes nodes are Ready: ${ready}/${total}"
  ok "Kubernetes API ready; nodes Ready=${ready}/${total}"
}

check_helm_version() {
  local actual
  actual="$(helm version --short | grep -oE '^v[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)"
  [[ "${actual}" == "${HELM_VERSION}" ]] ||
    fail "helm expected=${HELM_VERSION} actual=${actual:-unknown}; run install-k8s-platform-cli.sh"
  ok "helm ${HELM_VERSION}"
}

release_installed() {
  local namespace="$1"
  local release="$2"
  helm -n "${namespace}" status "${release}" >/dev/null 2>&1
}

ensure_namespace_psa() {
  local namespace="$1"
  local enforce="$2"
  local audit="$3"
  local warn_level="$4"

  kubectl create namespace "${namespace}" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
  kubectl label --overwrite namespace "${namespace}" \
    "pod-security.kubernetes.io/enforce=${enforce}" \
    "pod-security.kubernetes.io/enforce-version=${PSA_VERSION}" \
    "pod-security.kubernetes.io/audit=${audit}" \
    "pod-security.kubernetes.io/audit-version=${PSA_VERSION}" \
    "pod-security.kubernetes.io/warn=${warn_level}" \
    "pod-security.kubernetes.io/warn-version=${PSA_VERSION}" >/dev/null
  ok "namespace ${namespace}: PSA enforce=${enforce}, audit/warn=${audit}/${warn_level}, version=${PSA_VERSION}"
}

check_namespace_psa() {
  local namespace="$1"
  local expected_enforce="$2"
  local expected_audit="$3"
  local expected_warn="$4"
  local enforce audit warn_level enforce_version audit_version warn_version

  enforce="$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce}' 2>/dev/null || true)"
  audit="$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/audit}' 2>/dev/null || true)"
  warn_level="$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/warn}' 2>/dev/null || true)"
  enforce_version="$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/enforce-version}' 2>/dev/null || true)"
  audit_version="$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/audit-version}' 2>/dev/null || true)"
  warn_version="$(kubectl get namespace "${namespace}" -o jsonpath='{.metadata.labels.pod-security\.kubernetes\.io/warn-version}' 2>/dev/null || true)"

  [[ "${enforce}" == "${expected_enforce}" ]] ||
    fail "${namespace} PSA enforce=${enforce:-missing}, expected ${expected_enforce}"
  [[ "${audit}" == "${expected_audit}" ]] ||
    fail "${namespace} PSA audit=${audit:-missing}, expected ${expected_audit}"
  [[ "${warn_level}" == "${expected_warn}" ]] ||
    fail "${namespace} PSA warn=${warn_level:-missing}, expected ${expected_warn}"
  [[ "${enforce_version}" == "${PSA_VERSION}" && "${audit_version}" == "${PSA_VERSION}" && "${warn_version}" == "${PSA_VERSION}" ]] ||
    fail "${namespace} PSA versions must all be ${PSA_VERSION}"
  ok "${namespace} PSA enforce=${enforce}, audit=${audit}, warn=${warn_level}, version=${PSA_VERSION}"
}

helm_repo() {
  local name="$1"
  local url="$2"
  if helm repo list -o json 2>/dev/null | jq -e --arg name "${name}" '.[]? | select(.name == $name)' >/dev/null; then
    helm repo add "${name}" "${url}" --force-update >/dev/null
  else
    helm repo add "${name}" "${url}" >/dev/null
  fi
  helm repo update "${name}" >/dev/null
}

check_vault_storage_contract() {
  local provisioner default_class
  kubectl get csidriver csi.truenas.io >/dev/null 2>&1 ||
    fail "CSIDriver csi.truenas.io is missing"
  kubectl get storageclass nabla-truenas-nfs >/dev/null 2>&1 ||
    fail "StorageClass nabla-truenas-nfs is missing"
  provisioner="$(kubectl get storageclass nabla-truenas-nfs -o jsonpath='{.provisioner}')"
  [[ "${provisioner}" == "csi.truenas.io" ]] ||
    fail "StorageClass nabla-truenas-nfs provisioner=${provisioner:-missing}, expected csi.truenas.io"
  default_class="$(kubectl get storageclass nabla-truenas-nfs -o jsonpath='{.metadata.annotations.storageclass\.kubernetes\.io/is-default-class}' 2>/dev/null || true)"
  [[ "${default_class:-false}" != "true" ]] ||
    fail "nabla-truenas-nfs must remain non-default"
  bash "${ROOT}/scripts/talos/smoke-truenas-csi-nfs.sh" --check
  ok "Vault storage preflight: CSI driver/StorageClass/static health ready; dynamic bind/persistence/reclaim remains mandatory at --apply"
}

preflight_vault() {
  check_vault_storage_contract
  if release_installed "${VAULT_NAMESPACE}" vault; then
    info "Vault release already exists; use --check vault for strict runtime health"
  else
    info "Vault release not installed yet (planned); storage prerequisites are ready for the dynamic CSI gate"
  fi
}

render_vault() {
  helm template vault hashicorp/vault \
    --namespace "${VAULT_NAMESPACE}" \
    --version "${VAULT_CHART_VERSION}" \
    --skip-tests \
    -f "${VAULT_VALUES}"
}

template_vault() {
  render_vault >/dev/null
  ok "Vault chart ${VAULT_CHART_VERSION} renders with repository values"
}

server_dry_run_vault() {
  render_vault | kubectl apply --dry-run=server -f - >/dev/null
  ok "Vault rendered resources pass live API admission with PSS Restricted"
}

vault_status_json() {
  local output rc
  set +e
  output="$(kubectl -n "${VAULT_NAMESPACE}" exec vault-0 -- vault status -format=json 2>/dev/null)"
  rc=$?
  set -e
  if [[ -n "${output}" ]] && jq -e 'type == "object"' <<<"${output}" >/dev/null 2>&1; then
    printf '%s\n' "${output}"
    return 0
  fi
  return "${rc}"
}

check_vault() {
  local phase pvc_phase endpoint_count status initialized sealed
  release_installed "${VAULT_NAMESPACE}" vault ||
    fail "Vault Helm release not installed in ${VAULT_NAMESPACE}"
  check_namespace_psa "${VAULT_NAMESPACE}" restricted restricted restricted

  phase="$(kubectl -n "${VAULT_NAMESPACE}" get pod vault-0 -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "${phase}" == "Running" ]] || fail "vault-0 phase=${phase:-missing}"

  pvc_phase="$(kubectl -n "${VAULT_NAMESPACE}" get pvc data-vault-0 -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "${pvc_phase}" == "Bound" ]] || fail "Vault data PVC is ${pvc_phase:-missing}, expected Bound"
  ok "Vault pod Running and data PVC Bound"

  status="$(vault_status_json || true)"
  [[ -n "${status}" ]] || fail "vault status did not return JSON"
  initialized="$(jq -r '.initialized // false' <<<"${status}")"
  sealed="$(jq -r '.sealed // true' <<<"${status}")"

  if [[ "${initialized}" != "true" ]]; then
    warn "Vault is installed with persistent storage but is not initialized; initialize manually and protect recovery/unseal material outside Git"
    return 1
  fi
  if [[ "${sealed}" == "true" ]]; then
    warn "Vault is initialized but sealed; unseal it manually before declaring the service healthy"
    return 1
  fi

  endpoint_count="$(
    kubectl -n "${VAULT_NAMESPACE}" get endpointslice \
      -l kubernetes.io/service-name=vault \
      -o json 2>/dev/null |
      jq '[.items[].endpoints[]? | select(.conditions.ready == true)] | length'
  )"
  ((endpoint_count >= 1)) || fail "Vault Service has no ready endpoint"
  ok "Vault initialized, unsealed, and Service has ${endpoint_count} ready endpoint(s)"
}

status_vault() {
  if ! release_installed "${VAULT_NAMESPACE}" vault; then
    info "Vault: NOT_INSTALLED (planned; use --preflight vault before installation)"
    return 0
  fi
  check_vault
}

apply_vault() {
  if [[ "${K8S_PLATFORM_SKIP_CSI_SMOKE:-0}" != "1" ]]; then
    printf '🔎 proving CSI dynamic provisioning, cross-node persistence and reclaim before installing Vault\n'
    bash "${ROOT}/scripts/talos/smoke-truenas-csi-nfs.sh" --apply
  else
    warn "K8S_PLATFORM_SKIP_CSI_SMOKE=1 bypasses the disposable CSI acceptance gate; use only after an already-proven storage incident review"
  fi

  ensure_namespace_psa "${VAULT_NAMESPACE}" restricted restricted restricted
  helm_repo hashicorp https://helm.releases.hashicorp.com
  template_vault
  server_dry_run_vault
  helm upgrade --install vault hashicorp/vault \
    --namespace "${VAULT_NAMESPACE}" \
    --version "${VAULT_CHART_VERSION}" \
    -f "${VAULT_VALUES}" \
    --wait=false

  printf '🔎 waiting for vault-0 to reach Running; it may remain NotReady until manual initialization/unseal\n'
  for _ in $(seq 1 90); do
    [[ "$(kubectl -n "${VAULT_NAMESPACE}" get pod vault-0 -o jsonpath='{.status.phase}' 2>/dev/null || true)" == "Running" ]] && break
    sleep 2
  done
  [[ "$(kubectl -n "${VAULT_NAMESPACE}" get pod vault-0 -o jsonpath='{.status.phase}' 2>/dev/null || true)" == "Running" ]] ||
    fail "vault-0 did not reach Running"

  local pvc_phase
  pvc_phase="$(kubectl -n "${VAULT_NAMESPACE}" get pvc data-vault-0 -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  [[ "${pvc_phase}" == "Bound" ]] ||
    fail "Vault data PVC is ${pvc_phase:-missing}, expected Bound after install"

  ok "Vault chart installed with PSS Restricted and persistent storage; automatic initialization/unseal is intentionally disabled"
  printf 'ℹ️  next manual gate: kubectl -n %q exec vault-0 -- vault status\n' "${VAULT_NAMESPACE}"
}

version_at_least_5_8() {
  local version="$1"
  local major minor
  major="$(sed -nE 's/^([0-9]+).*/\1/p' <<<"${version}")"
  minor="$(sed -nE 's/^[0-9]+[.]([0-9]+).*/\1/p' <<<"${version}")"
  [[ -n "${major}" && -n "${minor}" ]] || return 1
  ((major > 5 || (major == 5 && minor >= 8)))
}

preflight_falco() {
  local nodes node kernel failures=0
  nodes="$(kubectl get nodes -o json)"
  while IFS=$'\t' read -r node kernel; do
    [[ -n "${node}" ]] || continue
    if version_at_least_5_8 "${kernel}"; then
      ok "Falco modern eBPF kernel gate: ${node}=${kernel}"
    else
      printf '❌ Falco modern eBPF requires kernel >=5.8; %s=%s\n' "${node}" "${kernel:-unknown}" >&2
      failures=$((failures + 1))
    fi
  done < <(jq -r '.items[] | [.metadata.name, .status.nodeInfo.kernelVersion] | @tsv' <<<"${nodes}")
  [[ "${failures}" -eq 0 ]] || return 1

  if release_installed "${FALCO_NAMESPACE}" falco; then
    info "Falco release already exists; use --check falco for runtime/eBPF/metrics health"
  else
    info "Falco release not installed yet (planned); modern eBPF load/BTF support will be proven by DaemonSet rollout"
  fi
}

render_falco() {
  helm template falco falcosecurity/falco \
    --namespace "${FALCO_NAMESPACE}" \
    --version "${FALCO_CHART_VERSION}" \
    --skip-tests \
    -f "${FALCO_VALUES}"
}

template_falco() {
  render_falco >/dev/null
  ok "Falco chart ${FALCO_CHART_VERSION} renders with repository values"
}

server_dry_run_falco() {
  render_falco | kubectl apply --dry-run=server -f - >/dev/null
  ok "Falco rendered resources pass live API admission in the dedicated privileged namespace"
}

falco_metrics() {
  kubectl get --raw="/api/v1/namespaces/${FALCO_NAMESPACE}/services/http:falco-metrics:8765/proxy/metrics"
}

check_falco() {
  local desired ready total_nodes actual endpoint_count metrics
  release_installed "${FALCO_NAMESPACE}" falco ||
    fail "Falco Helm release not installed in ${FALCO_NAMESPACE}"
  check_namespace_psa "${FALCO_NAMESPACE}" privileged restricted restricted

  desired="$(kubectl -n "${FALCO_NAMESPACE}" get daemonset falco -o jsonpath='{.status.desiredNumberScheduled}' 2>/dev/null || true)"
  ready="$(kubectl -n "${FALCO_NAMESPACE}" get daemonset falco -o jsonpath='{.status.numberReady}' 2>/dev/null || true)"
  total_nodes="$(kubectl get nodes -o json | jq '.items | length')"
  [[ -n "${desired}" && "${desired}" -eq "${total_nodes}" && "${ready}" == "${desired}" ]] ||
    fail "Falco DaemonSet Ready=${ready:-0}/${desired:-0}; expected coverage=${total_nodes} nodes"
  ok "Falco DaemonSet Ready=${ready}/${desired}; all Kubernetes nodes covered"

  actual="$(
    kubectl -n "${FALCO_NAMESPACE}" exec daemonset/falco -- falco --version 2>/dev/null |
      grep -oE '[0-9]+\.[0-9]+\.[0-9]+' |
      head -n 1
  )"
  [[ "${actual}" == "${FALCO_APP_VERSION}" ]] ||
    fail "Falco runtime expected=${FALCO_APP_VERSION} actual=${actual:-unknown}"
  ok "Falco runtime ${actual}"

  kubectl -n "${FALCO_NAMESPACE}" get service falco-metrics >/dev/null 2>&1 ||
    fail "Falco metrics Service is missing"
  endpoint_count="$(
    kubectl -n "${FALCO_NAMESPACE}" get endpointslice \
      -l kubernetes.io/service-name=falco-metrics \
      -o json 2>/dev/null |
      jq '[.items[].endpoints[]? | select(.conditions.ready == true)] | length'
  )"
  ((endpoint_count >= 1)) || fail "Falco metrics Service has no ready endpoints"

  metrics="$(falco_metrics 2>/dev/null || true)"
  [[ -n "${metrics}" ]] || fail "Falco /metrics returned no payload through Kubernetes Service proxy"
  grep -Eq '(^# (HELP|TYPE) )|(^falco_[A-Za-z0-9_:]+)' <<<"${metrics}" ||
    fail "Falco /metrics payload is not recognizable Prometheus exposition"
  ok "Falco metrics endpoint responds through Kubernetes Service proxy (${endpoint_count} ready endpoint(s))"
}

status_falco() {
  if ! release_installed "${FALCO_NAMESPACE}" falco; then
    info "Falco: NOT_INSTALLED (planned; use --preflight falco before installation)"
    return 0
  fi
  check_falco
}

apply_falco() {
  preflight_falco
  ensure_namespace_psa "${FALCO_NAMESPACE}" privileged restricted restricted
  helm_repo falcosecurity https://falcosecurity.github.io/charts
  template_falco
  server_dry_run_falco
  helm upgrade --install falco falcosecurity/falco \
    --namespace "${FALCO_NAMESPACE}" \
    --version "${FALCO_CHART_VERSION}" \
    -f "${FALCO_VALUES}" \
    --wait \
    --timeout 5m
  kubectl -n "${FALCO_NAMESPACE}" rollout status daemonset/falco --timeout=180s
  check_falco
}

check_kubara_cli() {
  local actual
  actual="$(
    KUBARA_UPDATE_CHECK=0 kubara --version 2>/dev/null |
      grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' |
      head -n 1 |
      sed 's/^v//'
  )"
  [[ "${actual}" == "${KUBARA_VERSION}" ]] ||
    fail "Kubara expected=${KUBARA_VERSION} actual=${actual:-unknown}"
  ok "Kubara CLI ${actual}"
}

check_kubara() {
  local ingress_count
  check_kubara_cli
  ingress_count="$(kubectl get ingressclass traefik --ignore-not-found -o name | wc -l | tr -d ' ')"
  if [[ "${ingress_count}" -eq 0 ]]; then
    bash "${ROOT}/scripts/talos/preflight-kubara.sh" --pre-bootstrap
  else
    bash "${ROOT}/scripts/talos/preflight-kubara.sh" --post-bootstrap
  fi
}

preflight_kubara() {
  check_kubara
  if [[ -f "${KUBARA_WORKDIR}/config.yaml" ]]; then
    ok "Kubara reviewed config present: ${KUBARA_WORKDIR}/config.yaml"
  else
    warn "Kubara config not present at ${KUBARA_WORKDIR}/config.yaml; generation/bootstrap remains intentionally gated"
  fi
}

status_kubara() {
  check_kubara
  if [[ -f "${KUBARA_WORKDIR}/config.yaml" ]]; then
    info "Kubara: CLI_READY config=present"
  else
    info "Kubara: CLI_READY config=missing bootstrap=GATED"
  fi
}

apply_kubara() {
  check_kubara
  [[ -f "${KUBARA_WORKDIR}/config.yaml" ]] ||
    fail "Kubara config missing: ${KUBARA_WORKDIR}/config.yaml; prepare/review the cluster intent before generation"
  (
    cd "${KUBARA_WORKDIR}"
    KUBARA_UPDATE_CHECK=0 kubara generate --helm --dry-run
  )
  ok "Kubara Helm generation dry-run succeeded without mutating generated files"

  if [[ "${KUBARA_ALLOW_BOOTSTRAP:-0}" != "1" ]]; then
    info "Kubara bootstrap intentionally not executed. Review generated Traefik exposure first."
    return
  fi
  [[ -n "${KUBARA_CLUSTER_NAME:-}" ]] ||
    fail "KUBARA_CLUSTER_NAME is required when KUBARA_ALLOW_BOOTSTRAP=1"
  (
    cd "${KUBARA_WORKDIR}"
    KUBARA_UPDATE_CHECK=0 kubara bootstrap "${KUBARA_CLUSTER_NAME}"
  )
  bash "${ROOT}/scripts/talos/preflight-kubara.sh" --post-bootstrap
}

cluster_check
check_helm_version

failures=0
run_target() {
  local name="$1"
  local action="$2"
  if ! ("${action}"); then
    printf '❌ %s validation failed\n' "${name}" >&2
    failures=$((failures + 1))
  fi
}

action_for() {
  local name="$1"
  case "${MODE}:${name}" in
    --preflight:vault) printf '%s\n' preflight_vault ;;
    --preflight:falco) printf '%s\n' preflight_falco ;;
    --preflight:kubara) printf '%s\n' preflight_kubara ;;
    --status:vault) printf '%s\n' status_vault ;;
    --status:falco) printf '%s\n' status_falco ;;
    --status:kubara) printf '%s\n' status_kubara ;;
    --check:vault) printf '%s\n' check_vault ;;
    --check:falco) printf '%s\n' check_falco ;;
    --check:kubara) printf '%s\n' check_kubara ;;
    --apply:vault) printf '%s\n' apply_vault ;;
    --apply:falco) printf '%s\n' apply_falco ;;
    --apply:kubara) printf '%s\n' apply_kubara ;;
    *) fail "unsupported mode/target: ${MODE}/${name}" ;;
  esac
}

case "${TARGET}" in
  all)
    for name in vault falco kubara; do
      run_target "${name}" "$(action_for "${name}")"
    done
    ;;
  vault | falco | kubara)
    "$(action_for "${TARGET}")"
    ;;
esac

[[ "${failures}" -eq 0 ]] || fail "${failures} platform tool check(s) failed"
ok "Kubernetes platform tools target=${TARGET} mode=${MODE} completed"
