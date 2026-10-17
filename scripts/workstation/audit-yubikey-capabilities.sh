#!/usr/bin/env bash
# Safe read-only YubiKey application inventory; ANSI colours when terminal supports them.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--help" ]]; then
  echo 'Usage: audit-yubikey-capabilities.sh [--serial SERIAL] [--challenge]'
  exit 0
fi
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != "dumb" ]]; then
  green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; blue=$'\033[36m'; reset=$'\033[0m'
else green=''; yellow=''; red=''; blue=''; reset=''; fi
heading() { printf '\n%s🔐 %s%s\n' "$blue" "$1" "$reset"; }
ok() { printf '%s✅ %s%s\n' "$green" "$1" "$reset"; }
warn() { printf '%s⚠️  %s%s\n' "$yellow" "$1" "$reset"; }
heading 'YubiKey / KeePassXC'
bash "$here/diagnose-yubikey-keepassxc.sh" "$@"
heading 'FIDO2'
if ykman fido info; then ok 'FIDO2 disponible'; else warn 'FIDO2 non accessible'; fi
heading 'PIV / certificats'
if piv="$(ykman piv info 2>&1)"; then
  # Redact the unique CHUID; dates/slots/fingerprints can still be identifying.
  printf '%s\n' "$piv" | sed -E 's/^(CHUID:).*/\1 [REDACTED]/'
  ok 'PIV disponible'
else warn 'PIV non accessible'; fi
# ykman 5.8.0 has no `piv certificates list`; inventory is reported by piv info.
# Check certificate expiry without requiring a PIN and without revealing key material.
if command -v python3 >/dev/null && [[ -n "${piv:-}" ]]; then
  PIV_AUDIT_TEXT="$piv" python3 - <<'PY'
import datetime
import os
import re
text = os.environ["PIV_AUDIT_TEXT"]
now = datetime.datetime.now(datetime.timezone.utc)
for block in re.split(r"(?=Slot [0-9A-Fa-f]{2} \()", text):
    slot = re.search(r"Slot ([0-9A-Fa-f]{2})", block)
    expiry = re.search(r"Not after:\s*(\d{4}-\d\d-\d\dT\S+)", block)
    if slot and expiry:
        try:
            expires = datetime.datetime.fromisoformat(expiry.group(1))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=datetime.timezone.utc)
            status = "EXPIRED ⚠️" if expires < now else "VALID ✅"
            print(f"Certificate PIV slot {slot.group(1)}: {status} ({expires.date()})")
        except ValueError:
            print(f"Certificate PIV slot {slot.group(1)}: unknown expiry")
PY
fi
heading 'OpenPGP'
if ykman openpgp info; then ok 'OpenPGP disponible'; else warn 'OpenPGP non accessible'; fi
heading 'OATH'
if ykman oath info; then ok 'OATH disponible'; else warn 'OATH non accessible'; fi
heading 'Outils SSH / GPG / age / PAM / Keyring'
for tool in gpg ssh-keygen pamu2fcfg age age-plugin-yubikey secret-tool seahorse; do
  if command -v "$tool" >/dev/null 2>&1; then ok "$tool installé"; else warn "$tool absent"; fi
done
heading 'Sécurité'
warn 'Ne pas réinitialiser PIV : sauvegarder et examiner les usages du certificat expiré.'
ok 'Aucune opération de provisionnement ou modification PAM effectuée.'
printf '📚 Documentation : docs/workstation-yubikey-full-capabilities.md\n'
