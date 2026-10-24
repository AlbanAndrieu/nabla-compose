#!/usr/bin/env bash
# Read-only PIV F9 inventory. No PIN, key generation, card write, or trust assertion.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  printf 'Run with bash; do not source.\n' >&2
  return 2
fi
set -euo pipefail
umask 077

usage() {
  printf 'Usage: bash scripts/workstation/inspect-age-yubikey-f9-chain.sh --serial 22916048|23501671\n'
  printf 'Read-only: exports public F9 certificate to a private temporary directory.\n'
}
if [[ "${1:-}" == '--help' || "${1:-}" == '-h' ]]; then usage; exit 0; fi
if [[ $# -ne 2 || "$1" != '--serial' ]]; then usage >&2; exit 2; fi
serial="$2"
case "$serial" in 22916048|23501671) ;; *) printf 'NO-GO: unknown serial\n' >&2; exit 2 ;; esac
for cmd in ykman openssl mktemp; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    printf 'NO-GO: required tool missing: %s\n' "$cmd" >&2
    exit 3
  fi
done
if ! inventory="$(ykman list --serials 2>/dev/null)"; then
  printf 'NO-GO: unable to enumerate YubiKeys\n' >&2
  exit 3
fi
mapfile -t attached < <(printf '%s\n' "$inventory" | grep -E '^[[:space:]]*[0-9]+[[:space:]]*$' | tr -d '[:space:]' || true)
if (( ${#attached[@]} != 1 )) || [[ "${attached[0]:-}" != "$serial" ]]; then
  printf 'NO-GO: connect only the selected YubiKey\n' >&2
  exit 3
fi
# Firmware version is public metadata, not an authentication secret.
if ! info="$(ykman --device "$serial" info 2>/dev/null)"; then
  printf 'NO-GO: unable to read device information\n' >&2
  exit 3
fi
firmware="$(printf '%s\n' "$info" | sed -nE 's/^[[:space:]]*Firmware version:[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+)[[:space:]]*$/\1/p')"
if [[ -z "$firmware" ]]; then
  printf 'NO-GO: firmware version is unrecognized\n' >&2
  exit 3
fi
private_dir="$(mktemp -d "${TMPDIR:-/tmp}/nabla-f9-public.XXXXXXXX")" || exit 3
trap 'rm -rf -- "$private_dir"' EXIT
cert="$private_dir/f9-public.pem"
# PIV certificate export is read-only on the YubiKey, and requires no PIN.
if ! ykman --device "$serial" piv certificates export --format PEM f9 - >"$cert" 2>/dev/null; then
  printf 'NO-GO: cannot export public factory-attestation F9 certificate\n' >&2
  exit 3
fi
if [[ ! -s "$cert" ]] || ! openssl x509 -in "$cert" -noout -subject -issuer -dates >/dev/null 2>&1; then
  printf 'NO-GO: F9 response is not an X.509 certificate\n' >&2
  exit 3
fi
fingerprint="$(openssl x509 -in "$cert" -noout -fingerprint -sha256 2>/dev/null)" || exit 3
case "$fingerprint" in *SHA256\ Fingerprint=*|*sha256\ Fingerprint=*) ;; *)
  printf 'NO-GO: F9 fingerprint unavailable\n' >&2; exit 3;;
esac
printf 'PASS: read-only F9 certificate inspection on YubiKey %s\n' "$serial"
printf 'INFO: firmware %s\n' "$firmware"
printf '%s\n' "$fingerprint"
printf 'WARN: F9 certificate fingerprint is NOT the Yubico root fingerprint\n'
printf 'WARN: factory trust, PIV82 attestation and AES256 authentication are NOT verified\n'
printf 'NO-GO: do not provision PIV82 or change SOPS recipients\n'
