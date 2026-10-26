#!/usr/bin/env bash
# One bounded, read-only evidence bundle for TrueNAS LAN operators.
set -euo pipefail

usage() {
  printf 'usage: bash %s [--observe-seconds 1..60] [--report-dir /private/path]\n' "$0"
}

SECONDS_WINDOW=20
REPORT_DIR="${HOME}/.local/state/nabla/observability"
while (($#)); do
  case "$1" in
    --observe-seconds)
      (($# >= 2)) || { usage >&2; exit 2; }
      SECONDS_WINDOW="$2"; shift 2 ;;
    --report-dir)
      (($# >= 2)) || { usage >&2; exit 2; }
      REPORT_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "${SECONDS_WINDOW}" =~ ^[0-9]+$ ]] &&
  ((SECONDS_WINDOW >= 1 && SECONDS_WINDOW <= 60)) || { usage >&2; exit 2; }

# Script can run from an alternate worktree and does not touch production.
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
[[ "${EUID}" -ne 0 ]] || { echo 'Run as the normal operator (not sudo).' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'Missing python3' >&2; exit 2; }
umask 077

echo '=== H-05 Prometheus + H-06 Akvorado ==='
echo 'Readonly; no service restart, repair or credentials.'
set +e
python3 "${REPO_ROOT}/scripts/truenas/collect-observability-evidence.py" \
  --check --scope all --observe-seconds "${SECONDS_WINDOW}" \
  --report-dir "${REPORT_DIR}"
result=$?
set -e
echo "observability_status_code=${result} (0=PASS;1=FAIL;2=UNVERIFIED)"
echo 'Akvorado ClickHouse rows require separate SQL evidence; batch counters alone are insufficient.'
exit "${result}"
