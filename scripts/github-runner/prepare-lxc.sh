#!/usr/bin/env bash
set -euo pipefail

# Prepare a TrueNAS LXC for a future GitHub Actions self-hosted runner.
# This script deliberately does NOT register the runner, start it, install a
# service, or accept a GitHub registration token.

RUNNER_VERSION="${RUNNER_VERSION:-2.336.0}"
RUNNER_USER="${RUNNER_USER:-github-runner}"
INSTALL_DIR="${INSTALL_DIR:-/opt/actions-runner}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this preparation script as root inside the LXC." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64)
    RUNNER_ARCH="x64"
    DEFAULT_SHA256="04cf0be1aff4c3ec3554466c39124ca250e3effd8873bb7e8d68535aa9505d5d"
    ;;
  aarch64 | arm64)
    RUNNER_ARCH="arm64"
    DEFAULT_SHA256="58b758e420b87093fbd4bfddd368074960053e2f1388f01848c82624b90f27d1"
    ;;
  *)
    echo "Unsupported architecture: $(uname -m)" >&2
    exit 1
    ;;
esac

if [[ "${RUNNER_VERSION}" != "2.336.0" && -z "${RUNNER_SHA256:-}" ]]; then
  echo "Set RUNNER_SHA256 when overriding RUNNER_VERSION." >&2
  exit 1
fi

RUNNER_SHA256="${RUNNER_SHA256:-${DEFAULT_SHA256}}"
RUNNER_ARCHIVE="actions-runner-linux-${RUNNER_ARCH}-${RUNNER_VERSION}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/${RUNNER_ARCHIVE}"

apt-get update
apt-get install --yes --no-install-recommends \
  ca-certificates \
  curl \
  git \
  jq \
  tar
rm -rf /var/lib/apt/lists/*

if ! id "${RUNNER_USER}" >/dev/null 2>&1; then
  useradd \
    --system \
    --home-dir "${INSTALL_DIR}" \
    --create-home \
    --shell /usr/sbin/nologin \
    "${RUNNER_USER}"
fi

if [[ -e "${INSTALL_DIR}/config.sh" ]]; then
  echo "${INSTALL_DIR} already contains a runner installation; leaving it untouched."
  exit 0
fi

mkdir -p "${INSTALL_DIR}"
work_dir="$(mktemp -d)"
trap 'rm -rf "${work_dir}"' EXIT

curl --fail --location --silent --show-error \
  "${RUNNER_URL}" \
  --output "${work_dir}/${RUNNER_ARCHIVE}"

echo "${RUNNER_SHA256}  ${work_dir}/${RUNNER_ARCHIVE}" | sha256sum --check

tar -xzf "${work_dir}/${RUNNER_ARCHIVE}" -C "${INSTALL_DIR}"
"${INSTALL_DIR}/bin/installdependencies.sh"
chown -R "${RUNNER_USER}:${RUNNER_USER}" "${INSTALL_DIR}"

cat <<EOF
✅ GitHub Actions runner files are prepared in ${INSTALL_DIR}.

The runner is intentionally NOT activated:
- config.sh has not been executed;
- no GitHub registration token has been used;
- run.sh is not running;
- no systemd service has been installed;
- TrueNAS LXC Autostart must remain disabled until you explicitly decide to enable it.

See docs/github-actions-runner-lxc.md for the manual activation procedure and security constraints.
EOF
