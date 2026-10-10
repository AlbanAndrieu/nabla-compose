#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
VERSION="${NABLA_YKMAN_VERSION:-5.9.2}"
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
DOCKERFILE="${ROOT}/tools/yubikey-manager/Dockerfile"
IMAGE="${NABLA_YKMAN_IMAGE:-local/nabla-ykman:${VERSION}}"
BIN_DIR="${HOME}/.local/bin"
WRAPPER="${BIN_DIR}/ykman"

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

case "${MODE}" in
  --check|--apply) ;;
  -h|--help)
    cat <<'EOF'
usage: bash scripts/truenas/bootstrap-yubikey-manager.sh [--check|--apply]

Build an isolated containerized ykman CLI for TrueNAS. Native build dependencies
exist only inside the image; the TrueNAS host Python/package database is not
modified. Device-management commands still require explicit USB device exposure.
EOF
    exit 0
    ;;
  *) fail "unknown mode: ${MODE}" ;;
esac

[[ "${EUID}" -ne 0 ]] || fail "run as the unprivileged TrueNAS operator, not root"
command -v docker >/dev/null 2>&1 || fail "docker is required"
[[ -f "${DOCKERFILE}" ]] || fail "missing ${DOCKERFILE}"

resolve_docker() {
  if docker info >/dev/null 2>&1; then
    DOCKER_CMD=(docker)
  elif command -v sudo >/dev/null 2>&1 && sudo -n docker info >/dev/null 2>&1; then
    DOCKER_CMD=(sudo docker)
  elif command -v sudo >/dev/null 2>&1; then
    printf 'INFO: Docker socket requires privilege; sudo authentication may be requested once.\n'
    sudo docker info >/dev/null
    DOCKER_CMD=(sudo docker)
  else
    fail "Docker socket is not accessible and sudo is unavailable"
  fi
}

resolve_docker

check_image() {
  "${DOCKER_CMD[@]}" image inspect "${IMAGE}" >/dev/null 2>&1 || return 1
  actual="$("${DOCKER_CMD[@]}" run --rm "${IMAGE}" --version 2>/dev/null | awk '{print $1}')"
  [[ "${actual}" == "${VERSION}" ]]
}

write_wrapper() {
  install -d -m 700 "${BIN_DIR}"
  cat >"${WRAPPER}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec sudo docker run --rm "${IMAGE}" "\$@"
EOF
  chmod 700 "${WRAPPER}"
}

if [[ "${MODE}" == "--check" ]]; then
  check_image || fail "containerized ykman ${VERSION} is not ready; run --apply"
  [[ -x "${WRAPPER}" ]] || fail "ykman wrapper missing: ${WRAPPER}; run --apply"
  printf 'OK: containerized YubiKey Manager %s ready via %s\n' "${VERSION}" "${WRAPPER}"
  printf 'INFO: wrapper has no host USB passthrough by default.\n'
  exit 0
fi

"${DOCKER_CMD[@]}" build \
  --build-arg "YKMAN_VERSION=${VERSION}" \
  -t "${IMAGE}" \
  -f "${DOCKERFILE}" \
  "${ROOT}/tools/yubikey-manager"

check_image || fail "containerized ykman failed self-check"
write_wrapper
printf 'OK: built containerized YubiKey Manager %s as %s\n' "${VERSION}" "${IMAGE}"
printf 'INFO: export PATH="%s:$PATH"; hash -r\n' "${BIN_DIR}"
printf 'INFO: no TrueNAS OS package, compiler or system Python was modified.\n'
