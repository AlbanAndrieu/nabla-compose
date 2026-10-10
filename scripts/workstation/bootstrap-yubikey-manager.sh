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
usage: bash scripts/workstation/bootstrap-yubikey-manager.sh [--check|--apply]

Install pinned YubiKey Manager CLI with uv in an isolated tool environment.
On Debian/Ubuntu workstations, --apply installs the native PC/SC build/runtime
prerequisites required by pyscard when they are missing.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the normal workstation user, not root"

resolve_uv() {
  if command -v uv >/dev/null 2>&1; then
    UV_CMD=(uv)
  elif command -v mise >/dev/null 2>&1; then
    UV_CMD=(mise --no-config exec uv@latest -- uv)
  else
    fail "uv or mise is required; install/bootstrap uv first"
  fi
}

native_prereqs_ready() {
  command -v pkg-config >/dev/null 2>&1 || return 1
  command -v swig >/dev/null 2>&1 || return 1
  pkg-config --exists libpcsclite 2>/dev/null || return 1
  return 0
}

report_native_prereqs() {
  command -v pkg-config >/dev/null 2>&1 ||
    printf 'MISSING: pkg-config\n' >&2
  command -v swig >/dev/null 2>&1 ||
    printf 'MISSING: swig\n' >&2
  if command -v pkg-config >/dev/null 2>&1; then
    pkg-config --exists libpcsclite 2>/dev/null ||
      printf 'MISSING: pkg-config module libpcsclite\n' >&2
    pkg-config --cflags libpcsclite 2>/dev/null |
      sed 's/^/pcsc_cflags=/' >&2 || true
  fi
}

install_native_prereqs() {
  native_prereqs_ready && return 0
  command -v apt-get >/dev/null 2>&1 ||
    fail "missing PC/SC development prerequisites and no apt-get is available"
  printf 'Installing workstation-only PC/SC prerequisites for pyscard...\n'
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends \
    libpcsclite-dev pcscd pkg-config swig
  if ! native_prereqs_ready; then
    report_native_prereqs
    fail "PC/SC prerequisites still incomplete after package installation"
  fi
}

resolve_uv
BIN_DIR="$("${UV_CMD[@]}" tool dir --bin)"
YKM="${BIN_DIR}/ykman"

report_path() {
  resolved="$(command -v ykman 2>/dev/null || true)"
  printf 'ykman_path=%s canonical=%s\n' "${resolved:-<missing>}" "${YKM}"
  if [[ -n "${resolved}" ]] && ! "${resolved}" --version >/dev/null 2>&1; then
    printf 'WARNING: current PATH resolves to a broken ykman launcher: %s\n' "${resolved}" >&2
    printf 'INFO: prepend %s to PATH; the global launcher is intentionally not deleted.\n' "${BIN_DIR}" >&2
  fi
}

check_install() {
  [[ -x "${YKM}" ]] || return 1
  actual="$("${YKM}" --version 2>/dev/null | awk '{print $1}')"
  [[ "${actual}" == "${VERSION}" ]] || return 1
}

if [[ "${MODE}" == "--check" ]]; then
  report_path
  if ! native_prereqs_ready; then
    printf 'WARNING: workstation PC/SC development prerequisites are incomplete\n' >&2
    report_native_prereqs
  fi
  check_install || fail "isolated ykman ${VERSION} is not ready; run --apply"
  printf 'OK: isolated YubiKey Manager %s ready at %s\n' "${VERSION}" "${YKM}"
  exit 0
fi

install_native_prereqs
"${UV_CMD[@]}" tool install --force --python "${PYTHON_VERSION}" "yubikey-manager==${VERSION}"
check_install || fail "uv-installed ykman failed self-check"
printf 'OK: installed YubiKey Manager %s with managed Python %s\n' "${VERSION}" "${PYTHON_VERSION}"
printf 'INFO: export PATH="%s:$PATH"; hash -r\n' "${BIN_DIR}"
report_path
