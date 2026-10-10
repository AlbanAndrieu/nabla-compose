#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"
PYTHON_VERSION="${NABLA_YKMAN_PYTHON_VERSION:-3.13}"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check|--apply) ;;
  -h|--help)
    cat <<'EOF'
usage: bash scripts/truenas/bootstrap-yubikey-manager.sh [--check|--apply]

Install pinned YubiKey Manager CLI through uv using a managed Python 3.13.
This avoids TrueNAS system Python/ensurepip and never invokes apt or system pip.
Physical YubiKey management still requires the USB/HID/CCID device to be
visible to TrueNAS; OTP typed through an SSH terminal does not.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the unprivileged TrueNAS operator, not root"

resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    UV_CMD=(uv)
  elif command -v mise >/dev/null 2>&1; then
    UV_CMD=(mise --no-config exec uv@latest -- uv)
  else
    fail "uv or mise is required; run the repository TrueNAS dev-tools bootstrap first"
  fi
}

resolve_uv
BIN_DIR="$("${UV_CMD[@]}" tool dir --bin)"
YKM="${BIN_DIR}/ykman"

check_install() {
  [[ -x "${YKM}" ]] || return 1
  actual="$("${YKM}" --version 2>/dev/null | awk '{print $1}')"
  [[ "${actual}" == "${VERSION}" ]] || return 1
}

if [[ "${MODE}" == "--check" ]]; then
  check_install || fail "isolated ykman ${VERSION} is not ready; run --apply"
  printf 'OK: isolated YubiKey Manager %s ready at %s\n' "${VERSION}" "${YKM}"
  exit 0
fi

"${UV_CMD[@]}" tool install --force --python "${PYTHON_VERSION}" "yubikey-manager==${VERSION}"
check_install || fail "uv-installed ykman failed self-check"
printf 'OK: installed YubiKey Manager %s with uv-managed Python %s\n' "${VERSION}" "${PYTHON_VERSION}"
printf 'INFO: export PATH="%s:$PATH"; hash -r\n' "${BIN_DIR}"
printf 'INFO: no TrueNAS OS package or system Python was modified.\n'
