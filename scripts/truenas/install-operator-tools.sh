#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"

TOOLS_ROOT="${TOOLS_ROOT:-/mnt/cpool/tools}"
TOOLS_BIN="${TOOLS_BIN:-${TOOLS_ROOT}/bin}"
TOOLS_DOWNLOADS="${TOOLS_DOWNLOADS:-${TOOLS_ROOT}/downloads}"
TOOLS_CACHE="${TOOLS_CACHE:-${TOOLS_ROOT}/cache}"
TOOLS_DATASET="${TOOLS_DATASET:-${TOOLS_ROOT#/mnt/}}"
KUBECTL_VERSION="${KUBECTL_VERSION:-v1.36.3}"
TALOS_VERSION="${TALOS_VERSION:-v1.13.9}"
PROFILE_FILE="${NABLA_OPERATOR_PROFILE:-${HOME}/.profile}"

TMP=""
STAGED=""

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

warn() {
  printf '⚠️  %s\n' "$*" >&2
}

ok() {
  printf '✅ %s\n' "$*"
}

cleanup() {
  local status=$?
  if [[ -n "${STAGED}" ]]; then
    rm -f -- "${STAGED}" 2>/dev/null || true
  fi
  if [[ -n "${TMP}" ]]; then
    rm -rf -- "${TMP}" 2>/dev/null || true
  fi
  exit "${status}"
}
trap cleanup EXIT INT TERM

usage() {
  cat <<'EOF'
Usage:
  bash scripts/truenas/install-operator-tools.sh --check
  bash scripts/truenas/install-operator-tools.sh --install
  bash scripts/truenas/install-operator-tools.sh --configure-path

Environment:
  TOOLS_ROOT        persistent dataset path (default: /mnt/cpool/tools)
  KUBECTL_VERSION   kubectl version (default: v1.36.3)
  TALOS_VERSION     talosctl version (default: v1.13.9)
  NABLA_OPERATOR_PROFILE profile updated by --configure-path (default: ~/.profile)
EOF
}

validate_root() {
  [[ "${TOOLS_ROOT}" == /* ]] || fail "TOOLS_ROOT must be an absolute path"
  [[ "${TOOLS_ROOT}" != *"/../"* && "${TOOLS_ROOT}" != */.. ]] ||
    fail "TOOLS_ROOT must not contain parent-directory traversal"
  case "${TOOLS_ROOT}" in
    /mnt/*) ;;
    *)
      fail "TOOLS_ROOT must live under /mnt on the persistent TrueNAS pool; refusing appliance/system path: ${TOOLS_ROOT}"
      ;;
  esac

  [[ "${TOOLS_BIN}" == "${TOOLS_ROOT}/"* ]] ||
    fail "TOOLS_BIN must remain inside TOOLS_ROOT"
  [[ "${TOOLS_DOWNLOADS}" == "${TOOLS_ROOT}/"* ]] ||
    fail "TOOLS_DOWNLOADS must remain inside TOOLS_ROOT"
  [[ "${TOOLS_CACHE}" == "${TOOLS_ROOT}/"* ]] ||
    fail "TOOLS_CACHE must remain inside TOOLS_ROOT"
  [[ "${TOOLS_DATASET}" == "${TOOLS_ROOT#/mnt/}" ]] ||
    fail "TOOLS_DATASET must map exactly to TOOLS_ROOT (${TOOLS_ROOT#/mnt/})"

  for path in "${TOOLS_ROOT}" "${TOOLS_BIN}" "${TOOLS_DOWNLOADS}" "${TOOLS_CACHE}"; do
    [[ ! -L "${path}" ]] || fail "refusing symlinked tools path: ${path}"
  done
}

dataset_payload() {
  midclt call pool.dataset.query "[[\"id\",\"=\",\"${TOOLS_DATASET}\"]]"
}

verify_dataset() {
  local payload
  local count
  local mountpoint

  payload="$(dataset_payload)" ||
    fail "cannot query TrueNAS dataset ${TOOLS_DATASET}"
  count="$(jq 'length' <<<"${payload}")"
  [[ "${count}" -eq 1 ]] ||
    fail "TrueNAS dataset ${TOOLS_DATASET} is missing"

  mountpoint="$(jq -r '.[0].mountpoint // empty' <<<"${payload}")"
  [[ "${mountpoint}" == "${TOOLS_ROOT}" ]] ||
    fail "dataset ${TOOLS_DATASET} mountpoint is ${mountpoint:-missing}, expected ${TOOLS_ROOT}"

  ok "TrueNAS dataset ${TOOLS_DATASET} mounted at ${TOOLS_ROOT}"
}

ensure_dataset() {
  local payload
  local count
  local create_payload

  payload="$(dataset_payload)" ||
    fail "cannot query TrueNAS dataset ${TOOLS_DATASET}"
  count="$(jq 'length' <<<"${payload}")"

  if [[ "${count}" -eq 0 ]]; then
    printf '🔧 creating persistent TrueNAS dataset %s\n' "${TOOLS_DATASET}"
    create_payload="$(
      jq -cn --arg name "${TOOLS_DATASET}" --arg comments "Persistent operator tools managed by nabla-compose" \
        '{name: $name, comments: $comments}'
    )"
    midclt call pool.dataset.create "${create_payload}" >/dev/null ||
      fail "cannot create ${TOOLS_DATASET}; grant DATASET_WRITE or create it once in the TrueNAS UI/API"
  elif [[ "${count}" -ne 1 ]]; then
    fail "unexpected dataset query result for ${TOOLS_DATASET}: ${count} matches"
  fi

  verify_dataset
}
require_tools_root_writable() {
  [[ -d "${TOOLS_ROOT}" ]] ||
    fail "tools dataset mountpoint is not a directory: ${TOOLS_ROOT}"
  [[ -w "${TOOLS_ROOT}" ]] ||
    fail "tools dataset is not writable by the current operator: ${TOOLS_ROOT}; configure its owner/ACL once through the TrueNAS UI/API"
}
require_root_install() {
  [[ "${EUID}" -eq 0 ]] ||
    fail "--install must run as root; the non-root Talos/Kubernetes operator must not be able to replace client binaries"
}

secure_root_managed_layout() {
  install -d -o root -g root -m 0755 "${TOOLS_ROOT}" "${TOOLS_BIN}"
  install -d -o root -g root -m 0700 "${TOOLS_DOWNLOADS}" "${TOOLS_CACHE}"
}

detect_arch() {
  local machine
  machine="$(uname -m)"
  case "${machine}" in
    x86_64)
      printf 'amd64\n'
      ;;
    aarch64 | arm64)
      printf 'arm64\n'
      ;;
    *)
      fail "unsupported architecture: ${machine}"
      ;;
  esac
}

validate_version() {
  local label="$1"
  local version="$2"
  [[ "${version}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
    fail "${label} version must use vMAJOR.MINOR.PATCH, got: ${version}"
}

require_commands() {
  local command
  for command in "$@"; do
    command -v "${command}" >/dev/null 2>&1 ||
      fail "${command} is required"
  done
}

binary_version() {
  local tool="$1"
  local binary="$2"
  local output=""

  [[ -x "${binary}" ]] || return 1

  case "${tool}" in
    kubectl)
      output="$("${binary}" version --client --output=json 2>/dev/null || true)"
      sed -nE 's/.*"gitVersion"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/p' <<<"${output}" |
        head -n 1
      ;;
    talosctl)
      output="$("${binary}" version --client 2>/dev/null || true)"
      sed -nE 's/^[[:space:]]*(Tag|Version):[[:space:]]*(v?[0-9]+\.[0-9]+\.[0-9]+).*$/\2/p' <<<"${output}" |
        head -n 1
      ;;
    *)
      return 1
      ;;
  esac
}

tool_matches() {
  local tool="$1"
  local expected="$2"
  local binary="${TOOLS_BIN}/${tool}"
  local actual=""

  actual="$(binary_version "${tool}" "${binary}" || true)"
  [[ -n "${actual}" && "${actual}" == "${expected}" ]]
}

download_file() {
  local url="$1"
  local destination="$2"

  curl \
    --fail \
    --location \
    --silent \
    --show-error \
    --retry 5 \
    --retry-delay 1 \
    --retry-all-errors \
    --connect-timeout 10 \
    --max-time 300 \
    --output "${destination}" \
    "${url}"
}

validate_sha256() {
  local sha="$1"
  [[ "${sha}" =~ ^[0-9a-fA-F]{64}$ ]]
}

verify_sha256() {
  local file="$1"
  local expected="$2"
  local actual

  validate_sha256 "${expected}" || fail "invalid SHA256 value for ${file}"
  actual="$(sha256sum "${file}" | awk '{print $1}')"
  [[ "${actual}" == "${expected}" ]] ||
    fail "SHA256 mismatch for $(basename -- "${file}")"
}

install_atomically() {
  local tool="$1"
  local source="$2"
  local expected_version="$3"
  local staged="${TOOLS_BIN}/.${tool}.new.$$"
  local actual=""

  STAGED="${staged}"
  install -m 0755 "${source}" "${staged}"

  actual="$(binary_version "${tool}" "${staged}" || true)"
  [[ "${actual}" == "${expected_version}" ]] ||
    fail "${tool} downloaded binary reports ${actual:-unknown}, expected ${expected_version}"

  mv -f -- "${staged}" "${TOOLS_BIN}/${tool}"
  STAGED=""
  ok "${tool} ${expected_version} installed at ${TOOLS_BIN}/${tool}"
}

install_kubectl() {
  local arch="$1"
  local checksum_url
  local binary_url
  local checksum_file="${TMP}/kubectl.sha256"
  local binary_file="${TMP}/kubectl"
  local expected_sha

  checksum_url="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl.sha256"
  binary_url="https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl"

  printf '🔎 validating kubectl asset %s linux/%s\n' "${KUBECTL_VERSION}" "${arch}"
  if ! download_file "${checksum_url}" "${checksum_file}"; then
    fail "kubectl ${KUBECTL_VERSION} is not published for linux/${arch}: ${checksum_url}"
  fi

  expected_sha="$(tr -d '[:space:]' <"${checksum_file}")"
  validate_sha256 "${expected_sha}" ||
    fail "kubectl checksum payload is invalid for ${KUBECTL_VERSION} linux/${arch}"

  if ! download_file "${binary_url}" "${binary_file}"; then
    fail "kubectl binary download failed after checksum validation: ${binary_url}"
  fi

  verify_sha256 "${binary_file}" "${expected_sha}"
  install_atomically kubectl "${binary_file}" "${KUBECTL_VERSION}"
}

install_talosctl() {
  local arch="$1"
  local asset="talosctl-linux-${arch}"
  local release_root="https://github.com/siderolabs/talos/releases/download/${TALOS_VERSION}"
  local checksum_file="${TMP}/talos-sha256sum.txt"
  local binary_file="${TMP}/${asset}"
  local expected_sha

  printf '🔎 validating talosctl asset %s linux/%s\n' "${TALOS_VERSION}" "${arch}"
  if ! download_file "${release_root}/sha256sum.txt" "${checksum_file}"; then
    fail "Talos release checksum manifest is unavailable: ${TALOS_VERSION}"
  fi

  expected_sha="$(
    awk -v asset="${asset}" '
      {
        name = $2
        sub(/^\*/, "", name)
        if (name == asset) {
          print $1
          exit
        }
      }
    ' "${checksum_file}"
  )"

  validate_sha256 "${expected_sha}" ||
    fail "checksum absent for ${asset} in Talos ${TALOS_VERSION}"

  if ! download_file "${release_root}/${asset}" "${binary_file}"; then
    fail "talosctl binary download failed after checksum validation: ${release_root}/${asset}"
  fi

  verify_sha256 "${binary_file}" "${expected_sha}"
  install_atomically talosctl "${binary_file}" "${TALOS_VERSION}"
}

check_tools() {
  local failures=0
  local actual

  if tool_matches kubectl "${KUBECTL_VERSION}"; then
    ok "kubectl ${KUBECTL_VERSION} present"
  else
    actual="$(binary_version kubectl "${TOOLS_BIN}/kubectl" || true)"
    printf '❌ kubectl expected=%s actual=%s path=%s\n' \
      "${KUBECTL_VERSION}" "${actual:-missing}" "${TOOLS_BIN}/kubectl" >&2
    failures=$((failures + 1))
  fi

  if tool_matches talosctl "${TALOS_VERSION}"; then
    ok "talosctl ${TALOS_VERSION} present"
  else
    actual="$(binary_version talosctl "${TOOLS_BIN}/talosctl" || true)"
    printf '❌ talosctl expected=%s actual=%s path=%s\n' \
      "${TALOS_VERSION}" "${actual:-missing}" "${TOOLS_BIN}/talosctl" >&2
    failures=$((failures + 1))
  fi

  case ":${PATH}:" in
    *":${TOOLS_BIN}:"*)
      ok "PATH contains ${TOOLS_BIN}"
      ;;
    *)
      warn "PATH does not contain ${TOOLS_BIN}; run --configure-path and reload the shell"
      ;;
  esac

  [[ "${failures}" -eq 0 ]] || fail "${failures} operator tool check(s) failed"
}

configure_path() {
  local marker="# nabla-compose TrueNAS operator tools"

  if [[ "${EUID}" -eq 0 ]]; then
    warn "--configure-path is configuring root only; run scripts/talos/configure-operator-client.sh --apply as the non-root operator for Talos/Kubernetes use"
  fi
  local export_line="export PATH=\"${TOOLS_BIN}:\$PATH\""

  [[ "${PROFILE_FILE}" == "${HOME}/"* || "${PROFILE_FILE}" == "${HOME}" ]] ||
    fail "profile path must stay inside HOME: ${PROFILE_FILE}"

  if [[ -e "${PROFILE_FILE}" && -L "${PROFILE_FILE}" ]]; then
    fail "refusing symlinked profile: ${PROFILE_FILE}"
  fi

  if [[ ! -e "${PROFILE_FILE}" ]]; then
    install -m 0600 /dev/null "${PROFILE_FILE}"
  fi

  if grep -Fqx "${export_line}" "${PROFILE_FILE}" 2>/dev/null; then
    ok "PATH already configured in ${PROFILE_FILE}"
    return
  fi

  {
    printf '\n%s\n' "${marker}"
    printf '%s\n' "${export_line}"
  } >>"${PROFILE_FILE}"

  ok "PATH configured in ${PROFILE_FILE}"
  printf 'ℹ️  reload with: . %q\n' "${PROFILE_FILE}"
}

validate_root
validate_version "kubectl" "${KUBECTL_VERSION}"
validate_version "talosctl" "${TALOS_VERSION}"

case "${MODE}" in
  --check)
    require_commands uname sed head
    ARCH="$(detect_arch)"
    [[ -n "${ARCH}" ]] || fail "architecture detection returned an empty value"
    printf 'ℹ️  tools root=%s dataset=%s arch=%s\n' "${TOOLS_ROOT}" "${TOOLS_DATASET}" "${ARCH}"
    if command -v midclt >/dev/null 2>&1 &&
      command -v jq >/dev/null 2>&1 &&
      dataset_payload >/dev/null 2>&1; then
      verify_dataset
    else
      [[ -d "${TOOLS_ROOT}" ]] || fail "tools root is missing: ${TOOLS_ROOT}"
      printf 'ℹ️  dataset API check unavailable to the current account; root install remains the authoritative dataset validation\n'
    fi
    if [[ -w "${TOOLS_ROOT}" ]]; then
      ok "current account can update ${TOOLS_ROOT}"
    else
      printf 'ℹ️  %s is read-only for the current account; this is expected for a non-root operator\n' "${TOOLS_ROOT}"
    fi
    if [[ "${EUID}" -ne 0 && -w "${TOOLS_BIN}" ]]; then
      fail "non-root operator can modify ${TOOLS_BIN}; restore root:root 0755 ownership before trusting kubectl/talosctl"
    elif [[ "${EUID}" -ne 0 ]]; then
      ok "non-root operator cannot replace binaries in ${TOOLS_BIN}"
    fi
    check_tools
    ;;
  --install)
    require_root_install
    require_commands uname curl sha256sum awk sed head tr install mv rm basename mktemp midclt jq
    ARCH="$(detect_arch)"
    [[ -n "${ARCH}" ]] || fail "architecture detection returned an empty value"

    ensure_dataset
    require_tools_root_writable
    secure_root_managed_layout
    TMP="$(mktemp -d "${TOOLS_DOWNLOADS}/operator-tools.XXXXXX")"

    printf 'ℹ️  tools root=%s dataset=%s arch=%s\n' "${TOOLS_ROOT}" "${TOOLS_DATASET}" "${ARCH}"

    if tool_matches kubectl "${KUBECTL_VERSION}"; then
      ok "kubectl ${KUBECTL_VERSION} already installed; skipping"
    else
      install_kubectl "${ARCH}"
    fi

    if tool_matches talosctl "${TALOS_VERSION}"; then
      ok "talosctl ${TALOS_VERSION} already installed; skipping"
    else
      install_talosctl "${ARCH}"
    fi

    check_tools
    ;;
  --configure-path)
    require_commands grep install
    configure_path
    ;;
  --help | -h)
    usage
    ;;
  *)
    usage >&2
    fail "unsupported mode: ${MODE}"
    ;;
esac
