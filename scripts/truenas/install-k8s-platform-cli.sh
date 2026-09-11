#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
ROOT="$(git rev-parse --show-toplevel)"
VERSIONS_FILE="${K8S_PLATFORM_VERSIONS_FILE:-${ROOT}/config/kubernetes-tools/versions.env}"
KUBARA_VERSION_FILE="${KUBARA_VERSION_FILE:-${ROOT}/config/kubara/VERSION}"
TOOLS_ROOT="${TOOLS_ROOT:-/mnt/cpool/tools}"
TOOLS_BIN="${TOOLS_BIN:-${TOOLS_ROOT}/bin}"
TOOLS_DOWNLOADS="${TOOLS_DOWNLOADS:-${TOOLS_ROOT}/downloads}"
TOOLS_CACHE="${TOOLS_CACHE:-${TOOLS_ROOT}/cache}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

ok() {
  printf '✅ %s\n' "$*"
}

usage() {
  cat <<'EOF'
Usage:
  bash scripts/truenas/install-k8s-platform-cli.sh --check
  sudo bash scripts/truenas/install-k8s-platform-cli.sh --install

Installs/checks the root-managed Kubernetes platform CLI dependencies under
/mnt/cpool/tools/bin. It intentionally does not use apt, mise, or the TrueNAS
appliance root filesystem for third-party package management.
EOF
}

case "${MODE}" in
  --check | --install) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unknown mode: ${MODE}"
    ;;
esac

[[ -r "${VERSIONS_FILE}" ]] || fail "missing versions file: ${VERSIONS_FILE}"
[[ -r "${KUBARA_VERSION_FILE}" ]] || fail "missing Kubara version pin: ${KUBARA_VERSION_FILE}"
# shellcheck disable=SC1090
source "${VERSIONS_FILE}"
KUBARA_VERSION="$(tr -d '[:space:]' <"${KUBARA_VERSION_FILE}")"

: "${HELM_VERSION:?HELM_VERSION missing from ${VERSIONS_FILE}}"
[[ "${HELM_VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
  fail "HELM_VERSION must be vMAJOR.MINOR.PATCH"
[[ "${KUBARA_VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
  fail "Kubara pin must be MAJOR.MINOR.PATCH"

case "${TOOLS_ROOT}" in
  /mnt/*) ;;
  *) fail "TOOLS_ROOT must live on a persistent TrueNAS dataset below /mnt" ;;
esac
[[ ! -L "${TOOLS_ROOT}" && ! -L "${TOOLS_BIN}" ]] ||
  fail "refusing symlinked persistent tools path"

detect_arch() {
  case "$(uname -m)" in
    x86_64) printf 'amd64\n' ;;
    aarch64 | arm64) printf 'arm64\n' ;;
    *) fail "unsupported architecture: $(uname -m)" ;;
  esac
}

download() {
  local url="$1"
  local output="$2"
  curl --fail --location --silent --show-error \
    --retry 5 --retry-delay 1 --retry-all-errors \
    --connect-timeout 10 --max-time 300 \
    --output "${output}" "${url}"
}

verify_sha256() {
  local file="$1"
  local expected="$2"
  local actual
  [[ "${expected}" =~ ^[0-9a-fA-F]{64}$ ]] ||
    fail "invalid checksum for $(basename -- "${file}")"
  actual="$(sha256sum "${file}" | awk '{print $1}')"
  [[ "${actual}" == "${expected}" ]] ||
    fail "SHA256 mismatch for $(basename -- "${file}")"
}

helm_version() {
  [[ -x "${TOOLS_BIN}/helm" ]] || return 1
  "${TOOLS_BIN}/helm" version --short 2>/dev/null |
    grep -oE '^v[0-9]+\.[0-9]+\.[0-9]+' |
    head -n 1
}

kubara_version() {
  [[ -x "${TOOLS_BIN}/kubara" ]] || return 1
  KUBARA_UPDATE_CHECK=0 "${TOOLS_BIN}/kubara" --version 2>/dev/null |
    grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' |
    head -n 1 |
    sed 's/^v//'
}

check_kubara_contract() {
  local generate_help bootstrap_help
  generate_help="$(KUBARA_UPDATE_CHECK=0 "${TOOLS_BIN}/kubara" generate --help 2>&1)"
  grep -q -- '--helm' <<<"${generate_help}" ||
    fail "Kubara ${KUBARA_VERSION} generate does not expose --helm"
  grep -q -- '--dry-run' <<<"${generate_help}" ||
    fail "Kubara ${KUBARA_VERSION} generate does not expose --dry-run"

  bootstrap_help="$(KUBARA_UPDATE_CHECK=0 "${TOOLS_BIN}/kubara" bootstrap --help 2>&1)"
  grep -q 'CLUSTER_NAME' <<<"${bootstrap_help}" ||
    fail "Kubara ${KUBARA_VERSION} bootstrap contract is unexpected"
  ok "Kubara CLI contract supports generate --helm/--dry-run and bootstrap CLUSTER_NAME"
}

check_tools() {
  local actual
  actual="$(helm_version || true)"
  [[ "${actual}" == "${HELM_VERSION}" ]] ||
    fail "helm expected=${HELM_VERSION} actual=${actual:-missing} path=${TOOLS_BIN}/helm"
  ok "helm ${HELM_VERSION} present"

  actual="$(kubara_version || true)"
  [[ "${actual}" == "${KUBARA_VERSION}" ]] ||
    fail "kubara expected=${KUBARA_VERSION} actual=${actual:-missing} path=${TOOLS_BIN}/kubara"
  ok "kubara ${KUBARA_VERSION} present"
  check_kubara_contract
}

install_helm() {
  local arch="$1"
  local tmp="$2"
  local asset="helm-${HELM_VERSION}-linux-${arch}.tar.gz"
  local url="https://get.helm.sh/${asset}"
  local archive="${tmp}/${asset}"
  local checksum="${tmp}/${asset}.sha256sum"
  local expected
  local extracted

  download "${url}.sha256sum" "${checksum}"
  expected="$(awk 'NR == 1 {print $1}' "${checksum}")"
  download "${url}" "${archive}"
  verify_sha256 "${archive}" "${expected}"

  tar -xzf "${archive}" -C "${tmp}"
  extracted="${tmp}/linux-${arch}/helm"
  [[ -x "${extracted}" ]] || fail "helm archive did not contain linux-${arch}/helm"
  install -m 0755 "${extracted}" "${TOOLS_BIN}/.helm.new"
  [[ "$("${TOOLS_BIN}/.helm.new" version --short | grep -oE '^v[0-9]+\.[0-9]+\.[0-9]+' | head -n 1)" == "${HELM_VERSION}" ]] ||
    fail "staged Helm version mismatch"
  mv -f "${TOOLS_BIN}/.helm.new" "${TOOLS_BIN}/helm"
  ok "helm ${HELM_VERSION} installed atomically"
}

install_kubara() {
  local arch="$1"
  local tmp="$2"
  local release_root="https://github.com/kubara-io/kubara/releases/download/v${KUBARA_VERSION}"
  local asset="kubara_${KUBARA_VERSION}_linux_${arch}.tar.gz"
  local checksums="${tmp}/kubara_${KUBARA_VERSION}_checksums.txt"
  local archive="${tmp}/${asset}"
  local expected
  local extracted

  download "${release_root}/kubara_${KUBARA_VERSION}_checksums.txt" "${checksums}"
  expected="$(
    awk -v asset="${asset}" '
      {
        name = $2
        sub(/^\*/, "", name)
        if (name == asset) {
          print $1
          exit
        }
      }
    ' "${checksums}"
  )"
  [[ -n "${expected}" ]] || fail "Kubara checksum not found for ${asset}"
  download "${release_root}/${asset}" "${archive}"
  verify_sha256 "${archive}" "${expected}"

  tar -xzf "${archive}" -C "${tmp}/kubara"
  extracted="$(find "${tmp}/kubara" -type f -name kubara -perm -u+x -print -quit)"
  [[ -n "${extracted}" ]] || fail "Kubara archive did not contain an executable kubara"
  install -m 0755 "${extracted}" "${TOOLS_BIN}/.kubara.new"
  [[ "$(KUBARA_UPDATE_CHECK=0 "${TOOLS_BIN}/.kubara.new" --version 2>/dev/null | grep -oE 'v?[0-9]+\.[0-9]+\.[0-9]+' | head -n 1 | sed 's/^v//')" == "${KUBARA_VERSION}" ]] ||
    fail "staged Kubara version mismatch"
  mv -f "${TOOLS_BIN}/.kubara.new" "${TOOLS_BIN}/kubara"
  ok "kubara ${KUBARA_VERSION} installed atomically"
}

if [[ "${MODE}" == "--check" ]]; then
  check_tools
  exit 0
fi

[[ "${EUID}" -eq 0 ]] ||
  fail "--install must run as root; operator users may execute --check but must not replace trusted binaries"

for command in curl sha256sum tar awk grep find install mv mktemp; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

install -d -o root -g root -m 0755 "${TOOLS_ROOT}" "${TOOLS_BIN}"
install -d -o root -g root -m 0700 "${TOOLS_DOWNLOADS}" "${TOOLS_CACHE}"
tmp="$(mktemp -d "${TOOLS_CACHE}/k8s-platform-cli.XXXXXX")"
trap 'rm -rf -- "${tmp}"; rm -f -- "${TOOLS_BIN}/.helm.new" "${TOOLS_BIN}/.kubara.new"' EXIT
install -d -m 0700 "${tmp}/kubara"

arch="$(detect_arch)"
printf 'ℹ️  installing root-managed CLI tools for linux/%s under %s\n' "${arch}" "${TOOLS_BIN}"

if [[ "$(helm_version || true)" != "${HELM_VERSION}" ]]; then
  install_helm "${arch}" "${tmp}"
else
  ok "helm ${HELM_VERSION} already installed"
fi

if [[ "$(kubara_version || true)" != "${KUBARA_VERSION}" ]]; then
  install_kubara "${arch}" "${tmp}"
else
  ok "kubara ${KUBARA_VERSION} already installed"
fi

check_tools
