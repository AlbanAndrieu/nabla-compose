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
[[ "${serial}" =~ ^[0-9]+$ ]] || { echo 'Explicit serial required' >&2; exit 2; }
command -v ykman >/dev/null || { echo 'ykman missing' >&2; exit 1; }
command -v age-plugin-yubikey >/dev/null || { echo 'age-plugin-yubikey missing' >&2; exit 1; }
# Parse ykman one serial per line without fragile sed replacement escaping.
mapfile -t detected_serials < <(ykman list --serials | grep -E '^[[:space:]]*[0-9]+[[:space:]]*$' | tr -d '[:space:]' || true)
if (( ${#detected_serials[@]} != 1 )) || [[ "${detected_serials[0]:-}" != "$serial" ]]; then
  echo "Expected exactly one YubiKey matching requested serial; detected count: ${#detected_serials[@]}" >&2
  echo 'Run ykman list --serials and verify the current checkout is on the PR branch.' >&2
  exit 2
fi
# ykman commonly returns nonzero for an EMPTY retired slot, e.g. "No key in slot 82".
# An empty-slot error is an expected safe result; all other errors fail closed.
if info="$(ykman --device "${serial}" piv keys info 82 2>&1)"; then
  if ! grep -Eiq 'no key( in slot)?|not found|empty' <<< "${info}"; then
    echo 'PIV slot 82 contains a key or is not confirmed empty; do not overwrite.' >&2
    exit 2
  fi
else
  if ! grep -Eiq 'no key( (stored )?in slot)?|no key present|slot 82.*empty' <<< "${info}"; then
    echo 'PIV 82 info unavailable for an unknown reason (e.g. PCSC/permission); fail closed.' >&2
    echo 'Diagnostic: confirm one YubiKey, then try ykman --device SERIAL piv keys info 82.' >&2
    exit 1
  fi
fi
echo 'PASS: selected single YubiKey and PIV 82 appears empty (read-only).'
echo 'Before any provisioning: keep OTP2 and PIV9A unchanged; never pass --force.'
echo 'Review age-plugin-yubikey --help and plan PIN=always, touch=always.'
echo 'Manual provisioning must be separately initiated and tested with synthetic data.'
