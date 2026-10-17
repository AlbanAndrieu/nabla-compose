#!/usr/bin/env bash
# Offline quality gate. No YubiKey, PIN, management key or provisioning required.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf '%s\n' 'Execute using bash, never source.' >&2
  return 2
fi
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"
# shellcheck source=scripts/workstation/shell-status.sh
source "$script_dir/shell-status.sh"
if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
  printf 'Usage: bash scripts/workstation/verify-age-yubikey-offline.sh\n'
  exit 0
fi
if (($#)); then
  nabla_status error 'Unexpected arguments'; exit 2
fi
for required in python3 openssl bash; do
  command -v "$required" >/dev/null || { nabla_status error "Missing $required"; exit 1; }
done
nabla_status info 'Running offline YubiKey security contracts; no hardware required'
python3 -m py_compile "$repo_root/tests/test_yubikey_keepassxc_diagnostic_contract.py"
python3 -m unittest discover -s "$repo_root/tests" -p 'test_yubikey_keepassxc_diagnostic_contract.py' -v
nabla_status ok 'Offline test suite passed'
nabla_status warn 'Not a hardware GO: AES256 compatible certificate install and real decrypt remain unverified'
