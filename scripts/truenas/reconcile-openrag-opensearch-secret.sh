#!/usr/bin/env bash
# Metadata-only, read-only equality check. Never reconcile secrets automatically.
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "${SCRIPT_DIR}/../lib/common.sh"

case "${1:---check}" in
  --check) ;;
  --apply)
    fail 'Legacy --apply disabled. Review canonical Vaultwarden materialization and staged env migration; do not overwrite an existing OpenRAG key.' ;;
  -h|--help)
    printf 'usage: sudo bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check\n'
    exit 0 ;;
  *) fail 'only --check is supported' ;;
esac
(($# <= 1)) || fail 'unexpected arguments'
require_root 'run as root on TrueNAS to read protected credentials'
require_commands awk stat grep
legacy="/mnt/cpool/compose/nabla-compose/apps/opensearch/.env"
canonical="/mnt/cpool/secrets/runtime/opensearch/.env"
canonical_secret="/mnt/cpool/secrets/runtime/opensearch/.env.secrets"
openrag="${OPENRAG_SECRET_FILE:-/mnt/cpool/openrag/.env.secrets}"

# Override exists for a privately reviewed staged source; no automatic rewrite.
if [[ -n "${OPENSEARCH_ENV_FILE:-}" ]]; then
  sources=("${OPENSEARCH_ENV_FILE}")
  source_kind='operator_selected'
else
  sources=("$canonical" "$canonical_secret" "$legacy")
  source_kind='declarative_candidates'
fi

is_private() {
  local path="$1" mode uid
  [[ -f "$path" && -r "$path" ]] || return 1
  mode="$(stat -Lc '%a' -- "$path" 2>/dev/null)" || return 1
  uid="$(stat -Lc '%u' -- "$path" 2>/dev/null)" || return 1
  [[ "$uid" == 0 && ( "$mode" == 600 || "$mode" == 400 || "$mode" == 640 ) ]]
}
read_key() {
  local file="$1" name="$2"
  awk -F= -v name="$name" '
    $1 == name {
      count++
      sub(/^[^=]*=/, "")
      if (length($0)) value=$0
    }
    END {
      if (count == 1 && length(value)) print value
      else exit 1
    }
  ' "$file"
}
[[ -f "$openrag" && -r "$openrag" ]] || fail 'OpenRAG runtime secret unavailable'
if ! is_private "$openrag"; then fail 'OpenRAG runtime secret has unsafe ownership or mode'; fi
openrag_pass="$(read_key "$openrag" OPENSEARCH_PASSWORD)" ||
  fail 'OpenRAG OPENSEARCH_PASSWORD absent, empty or duplicated'

resolved=0
matching=0
authority=''
for item in "${sources[@]}"; do
  [[ -e "$item" ]] || continue
  resolved=$((resolved + 1))
  if ! is_private "$item"; then
    fail 'OpenSearch secret candidate has unsafe ownership or mode; no value read'
  fi
  candidate="$(read_key "$item" OPENSEARCH_PASSWORD)" ||
    fail 'OpenSearch candidate has missing, empty or duplicate OPENSEARCH_PASSWORD'
  if [[ -n "$authority" && "$authority" != "$candidate" ]]; then
    fail 'OpenSearch canonical and legacy secret candidates disagree; do not rotate or restart'
  fi
  authority="$candidate"
  if [[ "$candidate" == "$openrag_pass" ]]; then matching=$((matching + 1)); fi
  unset candidate
done
if ((resolved == 0)); then
  printf 'opensearch_authority=UNAVAILABLE checked_sources=%s\n' "$source_kind"
  fail 'No reviewed OpenSearch credential file exists in the canonical runtime or legacy paths'
fi
printf 'opensearch_credential_candidates=%d source_selection=%s\n' "$resolved" "$source_kind"
if ((matching != resolved)); then
  fail 'OpenRAG OPENSEARCH_PASSWORD differs from available OpenSearch credential candidates'
fi
printf 'OK: OpenRAG OPENSEARCH_PASSWORD equals the existing file candidate(s)\n'
printf 'WARNING: runtime OpenSearch password still unverified; stored TrueNAS Compose / effective credential must be separately attested\n'
unset authority openrag_pass
