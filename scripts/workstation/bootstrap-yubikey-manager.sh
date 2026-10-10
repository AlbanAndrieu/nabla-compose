#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
VERSION="${NABLA_YKMAN_VERSION:-5.8.0}"
BIN_DIR="${HOME}/.local/bin"
LINK="${BIN_DIR}/ykman"
SYSTEM_YKMAN="/usr/bin/ykman"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check|--apply) ;;
  -h|--help)
    cat <<'EOF'
usage: bash scripts/workstation/bootstrap-yubikey-manager.sh [--check|--apply]

Install the distro-packaged YubiKey Manager CLI on an Ubuntu/Debian workstation.
Ubuntu Resolute currently ships yubikey-manager 5.9.2, avoiding local pyscard
compilation. ~/.local/bin/ykman points to /usr/bin/ykman so a stale
/usr/local/bin/ykman cannot shadow the packaged executable.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the normal workstation user, not root"

check_install() {
  [[ -x "${SYSTEM_YKMAN}" ]] || return 1
  actual="$("${SYSTEM_YKMAN}" --version 2>/dev/null | awk '{print $NF}')"
  [[ "${actual}" == "${VERSION}" ]] || {
    printf 'ERROR: packaged ykman version=%s expected=%s\n' "${actual:-<unknown>}" "${VERSION}" >&2
    return 1
  }
  [[ -L "${LINK}" ]] || return 1
  [[ "$(readlink -f "${LINK}")" == "${SYSTEM_YKMAN}" ]] || return 1
}

report_path() {
  printf 'canonical=%s link=%s\n' "${SYSTEM_YKMAN}" "${LINK}"
  type -a ykman 2>/dev/null || true
  if [[ -x /usr/local/bin/ykman ]] && ! /usr/local/bin/ykman --version >/dev/null 2>&1; then
    printf 'WARNING: stale broken launcher remains at /usr/local/bin/ykman; it is intentionally not deleted.\n' >&2
  fi
}

if [[ "${MODE}" == "--check" ]]; then
  report_path
  check_install || fail "packaged ykman ${VERSION} is not ready; run --apply"
  printf 'OK: YubiKey Manager %s ready at %s\n' "${VERSION}" "${SYSTEM_YKMAN}"
  exit 0
fi

command -v apt-get >/dev/null 2>&1 ||
  fail "apt-get is required on this workstation path"
sudo apt-get update
sudo apt-get install -y --no-install-recommends yubikey-manager pcscd libu2f-udev

[[ -x "${SYSTEM_YKMAN}" ]] ||
  fail "package installation completed but ${SYSTEM_YKMAN} is missing"
actual="$("${SYSTEM_YKMAN}" --version 2>/dev/null | awk '{print $NF}')"
[[ "${actual}" == "${VERSION}" ]] ||
  fail "distribution package installed ykman ${actual:-<unknown>}; expected ${VERSION}"

install -d -m 700 "${BIN_DIR}"
ln -sfn "${SYSTEM_YKMAN}" "${LINK}"
check_install || fail "packaged ykman failed post-install self-check"

printf 'OK: installed YubiKey Manager %s from the workstation distribution\n' "${VERSION}"
printf 'INFO: export PATH="%s:$PATH"; hash -r\n' "${BIN_DIR}"
report_path
