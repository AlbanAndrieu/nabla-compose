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
Python 3.13 is requested explicitly to avoid the current pyscard/Python 3.14
source-build path. No system Python package or global ykman launcher is removed.
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
  check_install || fail "isolated ykman ${VERSION} is not ready; run --apply"
  printf 'OK: isolated YubiKey Manager %s ready at %s\n' "${VERSION}" "${YKM}"
  exit 0
fi

"${UV_CMD[@]}" tool install --force --python "${PYTHON_VERSION}" "yubikey-manager==${VERSION}"
check_install || fail "uv-installed ykman failed self-check"
printf 'OK: installed YubiKey Manager %s with managed Python %s\n' "${VERSION}" "${PYTHON_VERSION}"
printf 'INFO: export PATH="%s:$PATH"; hash -r\n' "${BIN_DIR}"
report_path
