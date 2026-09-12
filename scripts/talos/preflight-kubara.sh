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
VERSION_FILE="${KUBARA_VERSION_FILE:-${ROOT}/config/kubara/VERSION}"
HOST="${K8S_FASTAPI_SMOKE_HOST:-test.int.albandrieu.com}"
INGRESS_CLASS="${K8S_FASTAPI_SMOKE_INGRESS_CLASS:-traefik}"
MODE="${1:---pre-bootstrap}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/talos/preflight-kubara.sh [--pre-bootstrap|--post-bootstrap]

Modes:
  --pre-bootstrap  require a clean cluster with no Traefik IngressClass/workload
  --post-bootstrap require the intended Traefik IngressClass/controller/workload

This command is read-only. It validates the pinned Kubara CLI contract, Kubernetes
API readiness, ingress-controller ownership, and test.int.albandrieu.com host ownership.
EOF
}

case "${MODE}" in
  --pre-bootstrap | --post-bootstrap) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

for command in kubara kubectl jq grep; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ -s "${VERSION_FILE}" ]] || fail "Kubara version pin not found: ${VERSION_FILE}"
EXPECTED_VERSION="$(tr -d '[:space:]' <"${VERSION_FILE}")"
[[ "${EXPECTED_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
  fail "invalid Kubara version pin: ${EXPECTED_VERSION}"

[[ -s "${KUBECONFIG}" ]] || fail "kubeconfig not found: ${KUBECONFIG}"
export KUBECONFIG

version_output="$(KUBARA_UPDATE_CHECK=0 kubara --version 2>&1)"
version_pattern="(^|[^0-9])v?${EXPECTED_VERSION//./\\.}([^0-9]|$)"
grep -Eq "${version_pattern}" <<<"${version_output}" ||
  fail "Kubara version mismatch: expected ${EXPECTED_VERSION}, observed: ${version_output}"
printf '✅ Kubara CLI version pinned: %s\n' "${EXPECTED_VERSION}"

generate_help="$(KUBARA_UPDATE_CHECK=0 kubara generate --help 2>&1)"
grep -q -- '--helm' <<<"${generate_help}" ||
  fail "Kubara ${EXPECTED_VERSION} generate command does not expose --helm"
grep -q -- '--dry-run' <<<"${generate_help}" ||
  fail "Kubara ${EXPECTED_VERSION} generate command does not expose --dry-run"

bootstrap_help="$(KUBARA_UPDATE_CHECK=0 kubara bootstrap --help 2>&1)"
grep -q 'CLUSTER_NAME' <<<"${bootstrap_help}" ||
  fail "Kubara ${EXPECTED_VERSION} bootstrap command contract is unexpected"
printf '✅ Kubara CLI contract: generate --helm/--dry-run and bootstrap CLUSTER_NAME\n'

kubectl get --raw='/readyz' >/dev/null ||
  fail "Kubernetes API readyz failed"
printf '✅ Kubernetes API readyz\n'

ingress_json="$(kubectl get ingressclass -o json)"
traefik_class_count="$(
  jq --arg name "${INGRESS_CLASS}"     '[.items[] | select(.metadata.name == $name)] | length' <<<"${ingress_json}"
)"
traefik_controller_count="$(
  jq '[.items[] | select(((.spec.controller // "") | ascii_downcase | contains("traefik")))] | length'     <<<"${ingress_json}"
)"

workload_json="$(kubectl get deployment,daemonset --all-namespaces -o json)"
traefik_workloads="$(
  jq -r '
    [
      .items[]
      | select(
          (.metadata.name // "" | ascii_downcase | contains("traefik"))
          or (.metadata.labels // {} | tostring | ascii_downcase | contains("traefik"))
        )
      | "\(.kind)/\(.metadata.namespace)/\(.metadata.name)"
    ]
    | unique
    | .[]
  ' <<<"${workload_json}"
)"
traefik_workload_count="$(grep -c . <<<"${traefik_workloads}" || true)"

host_claims="$(
  kubectl get ingress --all-namespaces -o json |
    jq -r --arg host "${HOST}" '
      .items[]
      | select(any(.spec.rules[]?; .host == $host))
      | "\(.metadata.namespace)/\(.metadata.name)"
    '
)"
[[ -z "${host_claims}" ]] ||
  fail "Ingress host ${HOST} is already claimed by: ${host_claims}"
printf '✅ Ingress host is unclaimed: %s\n' "${HOST}"

case "${MODE}" in
  --pre-bootstrap)
    [[ "${traefik_class_count}" -eq 0 ]] ||
      fail "IngressClass ${INGRESS_CLASS} already exists before Kubara bootstrap"
    [[ "${traefik_controller_count}" -eq 0 ]] ||
      fail "a Traefik IngressClass controller already exists before Kubara bootstrap"
    [[ "${traefik_workload_count}" -eq 0 ]] ||
      fail "Traefik workload(s) already exist before Kubara bootstrap: ${traefik_workloads}"
    printf '✅ clean pre-bootstrap ingress state: no Traefik class/controller/workload\n'
    ;;
  --post-bootstrap)
    [[ "${traefik_class_count}" -eq 1 ]] ||
      fail "expected exactly one IngressClass named ${INGRESS_CLASS}, found ${traefik_class_count}"
    controller="$(
      jq -r --arg name "${INGRESS_CLASS}" '
        .items[]
        | select(.metadata.name == $name)
        | .spec.controller // ""
      ' <<<"${ingress_json}"
    )"
    [[ -n "${controller}" ]] ||
      fail "IngressClass ${INGRESS_CLASS} has no spec.controller"
    [[ "${traefik_controller_count}" -eq 1 ]] ||
      fail "expected exactly one Traefik IngressClass controller, found ${traefik_controller_count}"
    [[ "${traefik_workload_count}" -eq 1 ]] ||
      fail "expected exactly one Traefik deployment/daemonset, found ${traefik_workload_count}: ${traefik_workloads}"
    printf '✅ Kubara ingress bootstrap ownership: class=%s controller=%s workload=%s\n'       "${INGRESS_CLASS}" "${controller}" "${traefik_workloads}"
    ;;
esac
