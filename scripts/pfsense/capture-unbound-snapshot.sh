#!/usr/bin/env bash
# Capture one bounded, redacted Unbound report in a private workstation folder.
# No service writes or restarts on pfSense; only the existing read-only SSH probe.
set -euo pipefail
usage() { printf 'Usage: %s --check\n' "$0"; }
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  --check) [[ $# -eq 1 ]] || { usage >&2; exit 2; } ;;
  *) usage >&2; exit 2 ;;
esac

umask 077
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
state_dir="${PFSENSE_UNBOUND_SNAPSHOT_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/nabla/pfsense-unbound}"

if [[ -L "$state_dir" ]]; then
  echo 'ERROR: snapshot_directory_is_symlink' >&2
  exit 72
fi
mkdir -p -m 700 -- "$state_dir"
[[ -d "$state_dir" && -O "$state_dir" && ! -L "$state_dir" ]] || {
  echo 'ERROR: snapshot_directory_not_private' >&2
  exit 72
}
chmod 700 -- "$state_dir"

filename="$(mktemp "$state_dir/unbound-$(date +%Y%m%dT%H%M%S%z).XXXXXXXX.log")"
cleanup() { rm -f -- "$filename"; }
trap cleanup ERR INT TERM

if ! PFSENSE_OUTPUT=verbose bash "$script_dir/diagnose-unbound-restart-cause.sh" --check > "$filename"; then
  echo 'ERROR: snapshot_collection_failed' >&2
  exit 70
fi
if ! grep -Eq '^pfSense_time=[0-9]{4}-[0-9]{2}-[0-9]{2}T' "$filename" ||
   ! grep -Eq '^unbound_pid=[0-9]+ started_local=' "$filename" ||
   ! grep -Fq 'End of read-only Unbound restart triage' "$filename" ||
   grep -Eq '(ERROR: (lifecycle_classifier_failed|feed_log_classifier_failed)|EVIDENCE INCOMPLETE)' "$filename"; then
  echo 'ERROR: snapshot_missing_required_evidence' >&2
  exit 70
fi
bytes="$(wc -c < "$filename")"
if ((bytes > 524288)); then
  echo 'ERROR: snapshot_exceeds_512_KiB_limit' >&2
  exit 70
fi
trap - ERR INT TERM
printf 'snapshot_saved=%s\n' "$filename"
echo 'snapshot_scope=WORKSTATION_ONLY_REDACTED_READONLY'
echo 'snapshot_retention=MANUAL_DELETE_AFTER_COMPARISON'
