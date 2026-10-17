#!/usr/bin/env bash
# Read-only guard before manual age-plugin-yubikey PIV slot 82 provisioning.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo 'Run with bash, never source' >&2; return 2
fi
set -euo pipefail
serial=''
while (( $# )); do
  case "$1" in
    --serial) (( $# >= 2 )) || exit 2; serial="$2"; shift 2 ;;
    --help|-h) echo 'Usage: bash scripts/workstation/preflight-age-yubikey-piv82.sh --serial SERIAL (READ ONLY)'; exit 0 ;;
    *) echo 'Unknown argument' >&2; exit 2 ;;
  esac
done
[[ "$serial" =~ ^[0-9]+$ ]] || { echo 'Explicit serial required' >&2; exit 2; }
command -v ykman >/dev/null || { echo 'ykman missing' >&2; exit 1; }
command -v age-plugin-yubikey >/dev/null || { echo 'age-plugin-yubikey missing' >&2; exit 1; }
connected="$(ykman list --serials | grep -E '^[0-9]+$' || true)"
[[ "$connected" == "$serial" ]] || { echo 'Connect exactly the selected single YubiKey' >&2; exit 2; }
info="$(ykman --device "$serial" piv keys info 82 2>&1)" || {
  echo 'PIV 82 info unavailable; fail closed' >&2; exit 1;
}
if ! grep -Eiq 'no key|not found|empty' <<< "$info"; then
  echo 'PIV slot 82 is not confirmed empty; refusing further guidance' >&2; exit 2
fi
echo 'PASS: selected single YubiKey and PIV 82 appears empty (read-only).'
echo 'Before any provisioning: keep OTP2 and PIV9A unchanged; never pass --force.'
echo 'Review age-plugin-yubikey --help and plan PIN=always, touch=always.'
echo 'Manual provisioning must be separately initiated and tested with synthetic data.'
