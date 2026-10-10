#!/usr/bin/env bash
# Read-only aggregate of OpenClaw Gateway errors; never prints raw journal lines.
set -euo pipefail
usage() { echo "Usage: diagnose-openclaw-errors.sh [--since '2 hours ago' | --stdin]" >&2; }
mode=journal
since="2 hours ago"
case "${1:-}" in
  "") ;;
  --since) [[ $# -eq 2 ]] || { usage; exit 2; }; since="${2}" ;;
  --stdin) [[ $# -eq 1 ]] || { usage; exit 2; }; mode=stdin ;;
  *) usage; exit 2 ;;
esac
aggregate() {
  python3 "$(dirname -- "${BASH_SOURCE[0]}")/openclaw-error-aggregate.py"

}
if [[ "${mode}" == stdin ]]; then
  aggregate
else
  journalctl --user -u openclaw-gateway.service --since "${since}" --no-pager -o cat |
    aggregate
fi
