#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"
BASE="${NABLA_YKMAN_HOME:-${HOME}/.local/share/nabla-tools/yubikey-manager-${VERSION}}"
BIN_DIR="${HOME}/.local/bin"
YKM="${BASE}/bin/ykman"
LINK="${BIN_DIR}/ykman"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check|--apply) ;;
  -h|--help)
    cat <<'EOF'
usage: bash scripts/truenas/bootstrap-yubikey-manager.sh [--check|--apply]

Install pinned YubiKey Manager CLI in an isolated user virtualenv.
This does not modify TrueNAS system Python or install OS packages.
A physical YubiKey still must be visible to TrueNAS for management commands.
Yubico OTP typed through an SSH terminal does not require device passthrough.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the unprivileged TrueNAS operator, not root"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

check_install() {
  [[ -x "${YKM}" ]] || return 1
  "${BASE}/bin/python" -c 'import ykman; import ykman._cli.__main__' >/dev/null 2>&1 || return 1
  actual="$("${YKM}" --version 2>/dev/null | awk '{print $1}')"
  [[ "${actual}" == "${VERSION}" ]] || return 1
  [[ -L "${LINK}" || -x "${LINK}" ]] || return 1
  return 0
}

if [[ "${MODE}" == "--check" ]]; then
  check_install || fail "isolated ykman ${VERSION} is not ready; run --apply"
  printf 'OK: isolated YubiKey Manager %s ready at %s\n' "${VERSION}" "${YKM}"
  exit 0
fi

python3 -m venv "${BASE}" || fail "python venv creation failed; do not apt/pip-install into the TrueNAS system Python"
"${BASE}/bin/python" -m pip install --disable-pip-version-check --upgrade pip >/dev/null
"${BASE}/bin/python" -m pip install --disable-pip-version-check "yubikey-manager==${VERSION}"
install -d -m 700 "${BIN_DIR}"
ln -sfn "${YKM}" "${LINK}"
check_install || fail "installed ykman failed self-check"
printf 'OK: installed isolated YubiKey Manager %s at %s\n' "${VERSION}" "${YKM}"
printf 'INFO: ensure ~/.local/bin precedes /usr/local/bin in PATH for this shell.\n'
printf 'INFO: device-management commands require the USB/HID/CCID device to be visible to TrueNAS.\n'
