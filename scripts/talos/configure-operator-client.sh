#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
TOOLS_BIN="${TOOLS_BIN:-/mnt/cpool/tools/bin}"
CONFIG_DIR="${NABLA_TALOS_CONFIG_DIR:-${HOME}/.config/nabla/talos}"
PROFILE_FILE="${NABLA_OPERATOR_PROFILE:-${HOME}/.profile}"
TALOSCONFIG_PATH="${CONFIG_DIR}/talosconfig"
KUBECONFIG_PATH="${CONFIG_DIR}/kubeconfig"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
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
  bash scripts/talos/configure-operator-client.sh --apply
  bash scripts/talos/configure-operator-client.sh --check

Run this script as the non-root Talos/Kubernetes operator (for this homelab:
albandrieu), after root has installed kubectl/talosctl in /mnt/cpool/tools/bin.

--apply creates the private config directory and idempotently configures PATH,
TALOSCONFIG and KUBECONFIG in ~/.profile. It never creates or copies credential
files.

--check requires the two credential files to exist with mode 0600 and verifies
that kubectl/talosctl are executable by the current operator.
EOF
}

require_non_root_operator() {
  [[ "${EUID}" -ne 0 ]] ||
    fail "run this client configuration as the non-root operator, not root"
}

ensure_profile_line() {
  local line="$1"

  if grep -Fqx "${line}" "${PROFILE_FILE}" 2>/dev/null; then
    return
  fi
  printf '%s\n' "${line}" >>"${PROFILE_FILE}"
}

check_private_file() {
  local label="$1"
  local path="$2"
  local mode
  local owner_uid

  [[ -s "${path}" ]] || fail "${label} not found: ${path}"
  [[ ! -L "${path}" ]] || fail "${label} must not be a symlink: ${path}"

  mode="$(stat -c '%a' "${path}")"
  owner_uid="$(stat -c '%u' "${path}")"
  [[ "${mode}" == "600" ]] ||
    fail "${label} must be mode 0600 (current: ${mode})"
  [[ "${owner_uid}" -eq "${EUID}" ]] ||
    fail "${label} must be owned by the current operator UID ${EUID} (current: ${owner_uid})"
  ok "${label} is private and operator-owned: ${path}"
}

case "${MODE}" in
  --apply | --check) ;;
  --help | -h)
    usage
    exit 0
    ;;
  *)
    usage >&2
    fail "unsupported mode: ${MODE}"
    ;;
esac

require_non_root_operator

for command in install grep stat; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

[[ "${CONFIG_DIR}" == "${HOME}/"* ]] ||
  fail "NABLA_TALOS_CONFIG_DIR must stay inside the current operator HOME"
[[ "${PROFILE_FILE}" == "${HOME}/"* ]] ||
  fail "NABLA_OPERATOR_PROFILE must stay inside the current operator HOME"

if [[ "${MODE}" == "--apply" ]]; then
  install -d -m 0700 "${CONFIG_DIR}"
  if [[ ! -e "${PROFILE_FILE}" ]]; then
    install -m 0600 /dev/null "${PROFILE_FILE}"
  fi
  [[ ! -L "${PROFILE_FILE}" ]] || fail "refusing symlinked profile: ${PROFILE_FILE}"

  ensure_profile_line '# nabla-compose Talos/Kubernetes operator'
  ensure_profile_line 'export PATH="/mnt/cpool/tools/bin:$PATH"'
  ensure_profile_line 'export TALOSCONFIG="$HOME/.config/nabla/talos/talosconfig"'
  ensure_profile_line 'export KUBECONFIG="$HOME/.config/nabla/talos/kubeconfig"'

  ok "operator profile configured in ${PROFILE_FILE}"
  ok "private Talos config directory ready: ${CONFIG_DIR}"
  printf 'ℹ️  copy talosconfig and kubeconfig into %s, chmod 0600, then reload: . %q\n'     "${CONFIG_DIR}" "${PROFILE_FILE}"
  exit 0
fi

[[ -d "${CONFIG_DIR}" ]] || fail "operator config directory not found: ${CONFIG_DIR}"
dir_mode="$(stat -c '%a' "${CONFIG_DIR}")"
[[ "${dir_mode}" == "700" ]] || fail "${CONFIG_DIR} must be mode 0700 (current: ${dir_mode})"

for tool in kubectl talosctl; do
  if [[ -x "${TOOLS_BIN}/${tool}" ]]; then
    ok "${tool} executable at ${TOOLS_BIN}/${tool}"
  else
    fail "${tool} is not executable at ${TOOLS_BIN}/${tool}"
  fi
done

check_private_file "talosconfig" "${TALOSCONFIG_PATH}"
check_private_file "kubeconfig" "${KUBECONFIG_PATH}"

case ":${PATH}:" in
  *":${TOOLS_BIN}:"*) ok "PATH contains ${TOOLS_BIN}" ;;
  *) warn "current shell PATH does not contain ${TOOLS_BIN}; reload ${PROFILE_FILE}" ;;
esac

ok "Talos/Kubernetes operator client configuration is ready"
