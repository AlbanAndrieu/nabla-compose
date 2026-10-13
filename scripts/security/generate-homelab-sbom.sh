#!/usr/bin/env bash
# Pin an image digest and produce PRIVATE Syft CycloneDX + Trivy SCA artifacts.
set -euo pipefail
set +x
MODE="${1:---check}"
IMAGE="${2:-}"
SERVICE="${NABLA_SBOM_SERVICE_ID:-}"
DIR="${NABLA_SBOM_OUTPUT_DIR:-/mnt/cpool/security/sbom}"
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
case "${MODE}" in --check|--apply) ;; *) fail "usage: bash ${0} [--check|--apply] image@sha256:digest" ;; esac
[[ "${IMAGE}" =~ ^[a-zA-Z0-9._:/-]+@sha256:[a-f0-9]{64}$ ]] ||
  fail "image reference must use immutable @sha256:<64-hex> digest"
[[ "${SERVICE}" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || fail "set NABLA_SBOM_SERVICE_ID"
[[ "${DIR}" == /* && ! -L "${DIR}" ]] || fail "output dir must be absolute and not symlink"
command -v syft >/dev/null || fail "pinned syft CLI is required"
command -v trivy >/dev/null || fail "pinned trivy CLI is required"
command -v jq >/dev/null || fail "jq required"
printf 'CHECK: image digest pinned; service=%s; output private=%s\n' "${SERVICE}" "${DIR}"
if [[ "${MODE}" == --check ]]; then
  printf 'INFO: no image pull, scan, output or network call\n'
  exit 0
fi
[[ "${NABLA_SBOM_APPROVED:-}" == YES ]] || fail "NABLA_SBOM_APPROVED=YES required"
[[ "${EUID}" != 0 ]] || fail "run scanner under an unprivileged dedicated user, not root"
[[ -d "${DIR}" && -w "${DIR}" ]] || fail "create a private writable output directory with correct ACL first"
[[ "$(stat -c %a "${DIR}")" == 700 ]] || fail "output directory must be mode 0700"
umask 077
digest="${IMAGE##*@sha256:}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
prefix="${DIR}/${SERVICE}-${digest}-${stamp}"
sbom="${prefix}.cdx.json"
report="${prefix}.trivy.json"
[[ ! -e "${sbom}" && ! -e "${report}" ]] || fail "artifacts exist: use a new immutable image or archive existing reports"
syft "${IMAGE}" -o "cyclonedx-json=${sbom}" >/dev/null ||
  fail "Syft SBOM generation failed"
trivy image --quiet --scanners vuln --format json --output "${report}" "${IMAGE}" ||
  fail "Trivy SCA failed"
jq -e '.bomFormat=="CycloneDX"' "${sbom}" >/dev/null || fail "invalid CycloneDX SBOM"
jq -e 'has("Results")' "${report}" >/dev/null || fail "invalid Trivy report"
chmod 600 "${sbom}" "${report}"
sha256sum "${sbom}" "${report}" | sed "s#${DIR}/##g"
printf 'OK: private SBOM and scan generated; import Trivy report in a separate explicit approval step\n'
