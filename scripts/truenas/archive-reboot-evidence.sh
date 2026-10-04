set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

MODE="${1:---check}"
STATE_ROOT="${NABLA_REBOOT_STATE_ROOT:-/mnt/cpool/var/nabla/reboot}"
ARCHIVE_ROOT="${NABLA_REBOOT_ARCHIVE_ROOT:-/mnt/cpool/var/nabla/reboot-archive}"
SOURCE_DIR="${NABLA_REBOOT_ARCHIVE_SOURCE_DIR:-}"

usage() {
  cat <<'EOF'
usage:
  sudo bash scripts/truenas/archive-reboot-evidence.sh [--check|--apply]

Archives only a successfully VERIFIED normal reboot transaction. The helper is
evidence-only: it never changes Docker, TrueNAS Apps, Kubernetes, ZFS or the
source transaction, and it never deletes an older archive.
EOF
}

case "${MODE}" in
  --check | --apply) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

require_root "run as root on TrueNAS"
require_commands install mktemp sha256sum jq date readlink cmp mv rm basename chmod

case "${ARCHIVE_ROOT}" in
  /mnt/cpool/var/nabla/*) ;;
  *) fail "archive root must stay under /mnt/cpool/var/nabla: ${ARCHIVE_ROOT}" ;;
esac

[[ -d "${STATE_ROOT}" ]] || fail "normal reboot state root is missing: ${STATE_ROOT}"
state_root_real="$(readlink -f "${STATE_ROOT}")"

if [[ -z "${SOURCE_DIR}" ]]; then
  [[ -f "${STATE_ROOT}/latest" ]] ||
    fail "normal reboot latest pointer is missing: ${STATE_ROOT}/latest"
  SOURCE_DIR="$(cat "${STATE_ROOT}/latest")"
fi

[[ -d "${SOURCE_DIR}" ]] || fail "reboot transaction directory is missing: ${SOURCE_DIR}"
source_real="$(readlink -f "${SOURCE_DIR}")"
case "${source_real}" in
  "${state_root_real}"/*) ;;
  *) fail "refusing archive source outside normal reboot state root: ${source_real}" ;;
esac

required_files=(
  phase
  boot-id-before
  boot-id-after
  apps-before.json
  vms-before.json
  docker-config-before.json
  docker-networks-before.txt
  kubernetes-nodes-before.json
  shutdown-plan.json
  resume-plan.json
  resume-apps.txt
  intentional-stopped.txt
  preexisting-failed.txt
  orchestrator-identity.txt
  prepare-history.log
  docker-storage-debt-before.txt
)
optional_files=(
  explicit-resume.txt
  operator-acceptance.json
  resume-bundle-hotfix.json
  resume-order-history.log
  resume-plan-effective.json
)

validate_source() {
  local file before after identity

  [[ "$(cat "${source_real}/phase" 2>/dev/null || true)" == "VERIFIED" ]] ||
    fail "reboot transaction is not VERIFIED: ${source_real}"

  for file in "${required_files[@]}"; do
    [[ -f "${source_real}/${file}" ]] ||
      fail "verified reboot evidence is incomplete: missing ${file}"
    [[ ! -L "${source_real}/${file}" ]] ||
      fail "refusing symlinked reboot evidence: ${file}"
  done

  before="$(cat "${source_real}/boot-id-before")"
  after="$(cat "${source_real}/boot-id-after")"
  [[ -n "${before}" && -n "${after}" && "${before}" != "${after}" ]] ||
    fail "boot-id evidence does not prove a reboot"

  identity="$(cat "${source_real}/orchestrator-identity.txt")"
  [[ -n "${identity//[[:space:]]/}" ]] ||
    fail "orchestrator identity is empty"

  for file in     apps-before.json     vms-before.json     docker-config-before.json     kubernetes-nodes-before.json     shutdown-plan.json     resume-plan.json; do
    jq -e . "${source_real}/${file}" >/dev/null ||
      fail "invalid JSON evidence: ${file}"
  done

  for file in operator-acceptance.json resume-bundle-hotfix.json; do
    if [[ -e "${source_real}/${file}" ]]; then
      [[ -f "${source_real}/${file}" && ! -L "${source_real}/${file}" ]] ||
        fail "invalid optional reboot evidence path: ${file}"
      jq -e . "${source_real}/${file}" >/dev/null ||
        fail "invalid JSON evidence: ${file}"
    fi
  done
}

validate_source

selected_files=("${required_files[@]}")
for file in "${optional_files[@]}"; do
  [[ -f "${source_real}/${file}" ]] && selected_files+=("${file}")
done

archive_name="$(basename "${source_real}")"
final="${ARCHIVE_ROOT}/${archive_name}"
files_json="$(
  printf '%s\n' "${selected_files[@]}" |
    jq -R . |
    jq -s .
)"

printf 'Verified reboot evidence archive\n'
printf 'source=%s\n' "${source_real}"
printf 'destination=%s\n' "${final}"
printf 'files=%s\n' "${#selected_files[@]}"
printf 'boot-before=%s\n' "$(cat "${source_real}/boot-id-before")"
printf 'boot-after=%s\n' "$(cat "${source_real}/boot-id-after")"

if [[ "${MODE}" == "--check" ]]; then
  printf 'READY: verified evidence can be archived without runtime mutation.\n'
  exit 0
fi

install -d -m 0700 "${ARCHIVE_ROOT}"

if [[ -e "${final}" ]]; then
  [[ -d "${final}" ]] || fail "archive destination exists and is not a directory: ${final}"
  [[ -f "${final}/SHA256SUMS" && -f "${final}/ARCHIVE-MANIFEST.json" ]] ||
    fail "existing archive is incomplete: ${final}"
  (cd "${final}" && sha256sum --quiet -c SHA256SUMS) ||
    fail "existing archive checksum verification failed: ${final}"
  jq -e --argjson files "${files_json}" '.files == $files'     "${final}/ARCHIVE-MANIFEST.json" >/dev/null ||
    fail "existing archive file inventory differs from verified source"
  for file in "${selected_files[@]}"; do
    cmp -s "${source_real}/${file}" "${final}/${file}" ||
      fail "verified source changed after archive creation: ${file}"
  done
  ok "verified existing immutable reboot archive ${final}"
  exit 0
fi

stage="$(mktemp -d "${ARCHIVE_ROOT}/.${archive_name}.tmp.XXXXXX")"
trap 'rm -rf "${stage}"' EXIT
chmod 0700 "${stage}"

for file in "${selected_files[@]}"; do
  install -m 0600 "${source_real}/${file}" "${stage}/${file}"
done

identity="$(cat "${source_real}/orchestrator-identity.txt")"
source_commit="${identity%% *}"
jq -n   --arg archivedAt "$(date -Iseconds)"   --arg sourceDirectory "${source_real}"   --arg bootIdBefore "$(cat "${source_real}/boot-id-before")"   --arg bootIdAfter "$(cat "${source_real}/boot-id-after")"   --arg orchestratorIdentity "${identity}"   --arg sourceCommit "${source_commit}"   --argjson files "${files_json}"   '{
    schemaVersion: 1,
    status: "VERIFIED",
    archivedAt: $archivedAt,
    sourceDirectory: $sourceDirectory,
    sourceCommit: $sourceCommit,
    bootIdBefore: $bootIdBefore,
    bootIdAfter: $bootIdAfter,
    orchestratorIdentity: $orchestratorIdentity,
    files: $files
  }' >"${stage}/ARCHIVE-MANIFEST.json"
chmod 0600 "${stage}/ARCHIVE-MANIFEST.json"

(
  cd "${stage}"
  sha256sum "${selected_files[@]}" ARCHIVE-MANIFEST.json >SHA256SUMS
  chmod 0600 SHA256SUMS
  sha256sum --quiet -c SHA256SUMS
)

mv "${stage}" "${final}"
trap - EXIT
chmod 0700 "${final}"

ok "archived VERIFIED reboot evidence: ${final}"
printf 'No reboot archive or recovery bundle was deleted; retention remains operator-reviewed.\n'
