#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
VERSION="${NABLA_BITWARDEN_CLI_VERSION:-2026.9.0}"
INSTALL_DIR="${NABLA_BITWARDEN_CLI_INSTALL_DIR:-${HOME}/.local/bin}"
BW_BIN="${NABLA_BITWARDEN_CLI_BIN:-${INSTALL_DIR}/bw}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    cat <<'EOF'
usage: bash scripts/truenas/bootstrap-bitwarden-cli.sh [--check|--apply]

Installs the pinned official Bitwarden Password Manager CLI into ~/.local/bin.
Run as the unprivileged operator; this script never modifies the TrueNAS OS.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the unprivileged operator, not root"

case "$(uname -m)" in
  x86_64 | amd64)
    asset="bw-linux-${VERSION}.zip"
    default_sha=""
    [[ "${VERSION}" != "2026.9.0" ]] ||
      default_sha="580c1deec8345b19dbac7f8b02babb6cc4fe250c69c567e29061f727f1e40768"
    ;;
  aarch64 | arm64)
    asset="bw-linux-arm64-${VERSION}.zip"
    default_sha=""
    [[ "${VERSION}" != "2026.9.0" ]] ||
      default_sha="3f474cc34b701a1cebdd486009870038b034343afb83095607422cdad4c3653a"
    ;;
  *) fail "unsupported architecture: $(uname -m)" ;;
esac

expected_sha="${NABLA_BITWARDEN_CLI_SHA256:-${default_sha}}"
[[ -n "${expected_sha}" ]] ||
  fail "no pinned SHA-256 for Bitwarden CLI ${VERSION}; set NABLA_BITWARDEN_CLI_SHA256 explicitly"

if [[ "${MODE}" == "--check" ]]; then
  [[ -x "${BW_BIN}" ]] || fail "Bitwarden CLI missing: ${BW_BIN}; run --apply"
  actual_version="$("${BW_BIN}" --version)"
  [[ "${actual_version}" == "${VERSION}" ]] ||
    fail "Bitwarden CLI version=${actual_version}; expected ${VERSION}"
  printf 'OK: Bitwarden CLI %s available at %s\n' "${actual_version}" "${BW_BIN}"
  exit 0
fi

for command in curl install mktemp python3 sha256sum uname; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

url="${NABLA_BITWARDEN_CLI_URL:-https://github.com/bitwarden/clients/releases/download/cli-v${VERSION}/${asset}}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT
archive="${tmp_dir}/${asset}"
extracted="${tmp_dir}/bw"

printf 'Downloading Bitwarden CLI %s for %s...\n' "${VERSION}" "$(uname -m)"
curl --fail --location --silent --show-error "${url}" -o "${archive}"
printf '%s  %s\n' "${expected_sha}" "${archive}" | sha256sum --check --status ||
  fail "Bitwarden CLI SHA-256 verification failed"

python3 - "${archive}" "${extracted}" <<'PY'
from pathlib import Path
import sys
import zipfile

archive = Path(sys.argv[1])
target = Path(sys.argv[2])
with zipfile.ZipFile(archive) as bundle:
    matches = [name for name in bundle.namelist() if Path(name).name == "bw"]
    if len(matches) != 1:
        raise SystemExit(f"expected one bw executable in archive, found {len(matches)}")
    target.write_bytes(bundle.read(matches[0]))
PY

install -d -m 700 "${INSTALL_DIR}"
install -m 755 "${extracted}" "${BW_BIN}"

actual_version="$("${BW_BIN}" --version)"
[[ "${actual_version}" == "${VERSION}" ]] ||
  fail "installed Bitwarden CLI version=${actual_version}; expected ${VERSION}"

printf 'OK: installed Bitwarden CLI %s at %s\n' "${actual_version}" "${BW_BIN}"
printf 'INFO: ensure %s is in PATH (bootstrap-dev-tools.sh --persist-shell-path can do this).\n' "${INSTALL_DIR}"
