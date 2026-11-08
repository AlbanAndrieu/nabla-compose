#!/usr/bin/env bash
# Compatibility wrapper for the security tooling Apps; the shared
# implementation is bootstrap-app-postgres.sh.
#   sudo bash scripts/truenas/bootstrap-security-tooling-postgres.sh [--check|--apply] <plumber|netbox|dependency-track|defectdojo>
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:---check}"
APP="${2:-}"
case "${APP}" in
plumber | netbox | dependency-track | defectdojo) ;;
*)
  printf 'ERROR: usage: %s [--check|--apply] <plumber|netbox|dependency-track|defectdojo>\n' "$0" >&2
  exit 1
  ;;
esac
exec bash "${SCRIPT_DIR}/bootstrap-app-postgres.sh" "${MODE}" "${APP}"
