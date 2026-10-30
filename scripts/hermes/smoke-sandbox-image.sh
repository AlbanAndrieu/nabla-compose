#!/usr/bin/env bash
set -euo pipefail

# Builds hermes-homelab-sandbox locally and proves it works under the same
# constraints as the hermes-homelab-offline SandboxTemplate: read-only rootfs,
# no network, UID 1000, all capabilities dropped, tmpfs /workspace and /tmp.
# Usage: bash scripts/hermes/smoke-sandbox-image.sh [image-tag]

ROOT="$(git rev-parse --show-toplevel)"
# shellcheck source=scripts/lib/common.sh
source "${ROOT}/scripts/lib/common.sh"

IMAGE="${1:-hermes-homelab-sandbox:smoke}"
CONTEXT="${ROOT}/kubernetes/hermes-sandbox/image"

require_commands docker

section "Building ${IMAGE}"
docker build --pull --tag "${IMAGE}" "${CONTEXT}"

section "Running offline checks with SandboxTemplate constraints"
docker run --rm \
  --network none \
  --read-only \
  --user 1000:1000 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /workspace:rw,exec,size=256m,uid=1000,gid=1000 \
  --tmpfs /tmp:rw,size=128m,uid=1000,gid=1000 \
  "${IMAGE}" \
  bash -euo pipefail -c '
    [[ "$(id -u):$(id -g)" == "1000:1000" ]] || { echo "unexpected identity $(id)"; exit 1; }
    if command -v kubectl >/dev/null || command -v docker >/dev/null; then
      echo "kubectl or docker CLI must be absent"; exit 1
    fi
    if touch /usr/local/bin/should-fail 2>/dev/null; then
      echo "rootfs is writable"; exit 1
    fi
    cd /workspace
    git init -q repo && cd repo
    printf "services:\n  web:\n    image: busybox:1.37.0\n    command: [\"sleep\", \"1\"]\n" > compose.yml
    docker-compose -f compose.yml config --quiet --no-interpolate
    printf "check:\n\ttrue\n" > justfile
    just check
    pre-commit --version
  '

ok "hermes-homelab-sandbox works offline as UID 1000 on a read-only rootfs"
