#!/usr/bin/env bash
# Read-only, fail-closed operator plan for YubiKey PIV82 external age enrollment.
# Deliberately no apply path; two-phase provisioning must be executed manually.
if [[ "${BASH_SOURCE[0]}" != "$0" ]]; then
  echo 'Run using bash, never source.' >&2; return 2
fi
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/shell-status.sh"
serial=''
while (($#)); do
  case "$1" in
    --serial) (($# > 1)) || exit 2; serial="$2"; shift 2 ;;
    --help|-h) printf '%s\n' 'Usage: bash scripts/workstation/plan-age-yubikey-piv82-enrollment.sh --serial 22916048|23501671'; exit 0 ;;
    *) nabla_status error 'Unknown option'; exit 2 ;;
  esac
done
case "$serial" in
  22916048) label='yubikey-5-nabla backup' ;;
  23501671) label='yubikey-5-nabla principal' ;;
  *) nabla_status error 'Unexpected serial: only inventoried devices are supported'; exit 2 ;;
esac
for command in ykman age-plugin-yubikey; do
  command -v "$command" >/dev/null || { nabla_status error "Missing dependency: $command"; exit 1; }
done
mapfile -t attached < <(ykman list --serials | grep -E '^[[:space:]]*[0-9]+[[:space:]]*$' | tr -d '[:space:]' || true)
if (( ${#attached[@]} != 1 )) || [[ "${attached[0]:-}" != "$serial" ]]; then
  nabla_status error 'Connect only the explicitly selected YubiKey'; exit 2
fi
piv="$(ykman --device "$serial" piv info)" || { nabla_status error 'Unable to read PIV status'; exit 1; }
grep -Eq 'Management key algorithm:[[:space:]]*AES256' <<< "$piv" || {
  nabla_status error 'PIV management key is not confirmed AES256'; exit 2;
}
if ! grep -Fq 'Management key is stored on the YubiKey, protected by PIN.' <<< "$piv"; then
  nabla_status error 'Protected management-key configuration not confirmed'; exit 2
fi
slot_info="$(ykman --device "$serial" piv keys info 82 2>&1)" && code=0 || code=$?
# Match the same exact observed response as the hardware inventory, including RETIRED1.
empty_slot_pattern='^[[:space:]]*(ERROR:[[:space:]]*)?No key stored in slot 82[[:space:]]*\(RETIRED1\)[.]?[[:space:]]*
  nabla_status error 'Slot PIV 82 is occupied or its empty state cannot be proven'; exit 2
fi
nabla_status ok "Read-only gate passed for selected serial $serial; PIV82 is empty, AES256 management key preserved"
nabla_status info "PIV PIN vault label: LastPass '$label' (never disclose the value)"
nabla_status warn 'PREPARATION ONLY: writing an irreversible on-card P-256 key needs a separate manual approval'
nabla_status info 'Manual key operation, after independent review: ykman --device SERIAL piv keys generate --algorithm ECCP256 --pin-policy ALWAYS --touch-policy ALWAYS 82 OUTPUT_PUBLIC.pem'
nabla_status warn 'The second phase MUST create a plugin-compatible certificate with subject O=age-plugin-yubikey, OU=0.5.1 and policy OID 1.3.6.1.4.1.41482.3.8 = 03 02'
nabla_status warn 'Do not generate before the certificate phase is independently validated; a slot filled without usable cert may require recovery'
nabla_status info 'Verify by age-plugin-yubikey --list-all and a synthetic age encrypt/decrypt; preserve OTP2, PIV9A, AES256 and software SOPS recovery'
exit 0

if (( code > 1 )) || ! grep -Eiq "$empty_slot_pattern" <<< "$slot_info"; then
  nabla_status error 'Slot PIV 82 is occupied or its empty state cannot be proven'; exit 2
fi
nabla_status ok "Read-only gate passed for selected serial $serial; PIV82 is empty, AES256 management key preserved"
nabla_status info "PIV PIN vault label: LastPass '$label' (never disclose the value)"
nabla_status warn 'PREPARATION ONLY: writing an irreversible on-card P-256 key needs a separate manual approval'
nabla_status info 'Manual key operation, after independent review: ykman --device SERIAL piv keys generate --algorithm ECCP256 --pin-policy ALWAYS --touch-policy ALWAYS 82 OUTPUT_PUBLIC.pem'
nabla_status warn 'The second phase MUST create a plugin-compatible certificate with subject O=age-plugin-yubikey, OU=0.5.1 and policy OID 1.3.6.1.4.1.41482.3.8 = 03 02'
nabla_status warn 'Do not generate before the certificate phase is independently validated; a slot filled without usable cert may require recovery'
nabla_status info 'Verify by age-plugin-yubikey --list-all and a synthetic age encrypt/decrypt; preserve OTP2, PIV9A, AES256 and software SOPS recovery'
exit 0
