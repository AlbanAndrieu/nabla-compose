#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
printf 'WARNING: moved to scripts/workstation/verify-crowdsec-pfsense.sh\n' >&2
printf 'WARNING: run this check from the workstation; TrueNAS must not SSH to pfSense.\n' >&2
exec "${ROOT}/scripts/workstation/verify-crowdsec-pfsense.sh" "$@"
