#!/usr/bin/env bash
# Read-only aggregate of OpenClaw Gateway errors; never prints raw journal lines.
set -euo pipefail
# Add emoji/color only for interactive operator output; preserve machine-readable pipes.
if [[ -z "${OPENCLAW_STYLE_ACTIVE:-}" && -z "${NO_COLOR+x}" && "${OPENCLAW_COLOR:-auto}" != never && ( -t 1 || "${OPENCLAW_COLOR:-auto}" == always ) ]]; then
  export OPENCLAW_STYLE_ACTIVE=1
  bash "${BASH_SOURCE[0]}" "$@" | python3 "$(dirname -- "${BASH_SOURCE[0]}")/openclaw-terminal-style.py"
  exit "${PIPESTATUS[0]}"
fi
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
