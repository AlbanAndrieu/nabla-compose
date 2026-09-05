#!/usr/bin/env bash
set -euo pipefail
umask 077

ROOT="$(git rev-parse --show-toplevel)"
CLUSTER_NAME="${TALOS_CLUSTER_NAME:-nabla-talos}"
ENDPOINT="${TALOS_CONTROL_PLANE_ENDPOINT:-}"
VERSION_FILE="${ROOT}/config/talos/VERSION"
[[ -r "${VERSION_FILE}" ]] || {
  echo "missing Talos version file: ${VERSION_FILE}" >&2
  exit 1
}
TALOS_VERSION="${TALOS_VERSION:-$(<"${VERSION_FILE}")}"
INSTALL_DISK="${TALOS_INSTALL_DISK:-/dev/vda}"
OUTPUT_DIR="${TALOS_OUTPUT_DIR:-${ROOT}/.talos/generated}"
OVERWRITE="${TALOS_OVERWRITE:-false}"

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

command -v talosctl >/dev/null 2>&1 || fail "talosctl is required"

[[ -n "${ENDPOINT}" ]] || fail "TALOS_CONTROL_PLANE_ENDPOINT is required (for example https://10.0.0.10:6443)"
[[ "${ENDPOINT}" =~ ^https://[^[:space:]]+:6443$ ]] || fail "TALOS_CONTROL_PLANE_ENDPOINT must use https:// and port 6443"
[[ "${CLUSTER_NAME}" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]] || fail "TALOS_CLUSTER_NAME contains unsupported characters"
[[ "${TALOS_VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "TALOS_VERSION must be a full release such as v1.13.9"
[[ "${INSTALL_DISK}" == /dev/* ]] || fail "TALOS_INSTALL_DISK must be an absolute /dev path"
[[ "${OVERWRITE}" == "true" || "${OVERWRITE}" == "false" ]] || fail "TALOS_OVERWRITE must be true or false"

if [[ "${OUTPUT_DIR}" != /* ]]; then
  OUTPUT_DIR="${ROOT}/${OUTPUT_DIR}"
fi

case "${OUTPUT_DIR}" in
  "${ROOT}/.talos" | "${ROOT}/.talos/"*) ;;
  *) fail "TALOS_OUTPUT_DIR must stay below ${ROOT}/.talos so generated secrets remain Git-ignored" ;;
esac

mkdir -p "${OUTPUT_DIR}"
chmod 700 "${OUTPUT_DIR}"

git -C "${ROOT}" check-ignore -q "${OUTPUT_DIR}" || fail "${OUTPUT_DIR} is not ignored by Git"

SECRETS_FILE="${OUTPUT_DIR}/secrets.yaml"
CONTROL_PLANE_FILE="${OUTPUT_DIR}/controlplane.yaml"
WORKER_FILE="${OUTPUT_DIR}/worker.yaml"
TALOSCONFIG_FILE="${OUTPUT_DIR}/talosconfig"
GENERATED_FILES=("${CONTROL_PLANE_FILE}" "${WORKER_FILE}" "${TALOSCONFIG_FILE}")

existing_config=false
for generated_file in "${GENERATED_FILES[@]}"; do
  if [[ -e "${generated_file}" ]]; then
    existing_config=true
    if [[ "${OVERWRITE}" != "true" ]]; then
      fail "${generated_file} already exists; set TALOS_OVERWRITE=true to regenerate configs with the existing secrets"
    fi
  fi
done

if [[ "${existing_config}" == "true" && ! -f "${SECRETS_FILE}" ]]; then
  fail "generated configs exist but secrets.yaml is missing; restore the original cluster secrets instead of generating a new PKI"
fi

if [[ ! -f "${SECRETS_FILE}" ]]; then
  printf '🔐 Generating Talos %s cluster secrets...\n' "${TALOS_VERSION}"
  talosctl gen secrets \
    --talos-version "${TALOS_VERSION}" \
    --output-file "${SECRETS_FILE}"
  chmod 600 "${SECRETS_FILE}"
else
  printf '🔐 Reusing existing cluster secrets: %s\n' "${SECRETS_FILE}"
fi

GEN_ARGS=(
  gen config
  "${CLUSTER_NAME}"
  "${ENDPOINT}"
  --with-secrets "${SECRETS_FILE}"
  --talos-version "${TALOS_VERSION}"
  --install-disk "${INSTALL_DISK}"
  --output "${OUTPUT_DIR}"
  --with-docs=false
  --with-examples=false
)

if [[ "${OVERWRITE}" == "true" ]]; then
  GEN_ARGS+=(--force)
fi

printf '⚙️  Generating Talos machine configurations in %s...\n' "${OUTPUT_DIR}"
talosctl "${GEN_ARGS[@]}"
chmod 600 "${GENERATED_FILES[@]}"

printf '✅ Validating generated control-plane configuration...\n'
talosctl validate --config "${CONTROL_PLANE_FILE}" --mode metal --strict
printf '✅ Validating generated worker configuration...\n'
talosctl validate --config "${WORKER_FILE}" --mode metal --strict

cat <<EOF
✅ Talos configuration generated locally.

Cluster:       ${CLUSTER_NAME}
Endpoint:      ${ENDPOINT}
Talos version: ${TALOS_VERSION}
Install disk:  ${INSTALL_DISK}
Output:        ${OUTPUT_DIR}

No node was contacted and no configuration was applied.
Before any apply-config, boot each VM into Talos maintenance mode and verify the target disk, for example:
  talosctl get disks --insecure --nodes <NODE_IP>
EOF
