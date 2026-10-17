#!/usr/bin/env bash
# Safe read-only YubiKey application inventory; ANSI colours when terminal supports them.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--help" ]]; then
  echo 'Usage: audit-yubikey-capabilities.sh [--serial SERIAL] [--challenge]'
  exit 0
fi
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != "dumb" ]]; then
  green=$'\033[32m'; yellow=$'\033[33m'; blue=$'\033[36m'; reset=$'\033[0m'
else green=''; yellow=''; blue=''; reset=''; fi
heading() { printf '\n%s🔐 %s%s\n' "${blue}" "$1" "${reset}"; }
ok() { printf '%s✅ %s%s\n' "${green}" "$1" "${reset}"; }
warn() { printf '%s⚠️  %s%s\n' "${yellow}" "$1" "${reset}"; }
heading 'YubiKey / KeePassXC'
bash "${here}/diagnose-yubikey-keepassxc.sh" "$@"
heading 'FIDO2'
if ykman fido info; then ok 'FIDO2 disponible'; else warn 'FIDO2 non accessible'; fi
heading 'PIV / certificats'
if piv="$(ykman piv info 2>&1)"; then
  # Redact the unique CHUID; dates/slots/fingerprints can still be identifying.
  printf '%s\n' "${piv}" | sed -E 's/^(CHUID:).*/\1 [REDACTED]/'
  ok 'PIV disponible'
else warn 'PIV non accessible'; fi
# ykman 5.8.0 has no `piv certificates list`; inventory is reported by piv info.
# Check certificate expiry without requiring a PIN and without revealing key material.
if command -v python3 >/dev/null && [[ -n "${piv:-}" ]]; then
  PIV_AUDIT_TEXT="${piv}" python3 - <<'PY'
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
heading 'Inventaire attendu : usage vs emplacement'
printf '%s\n' '✅ Confirmé : OTP slot 2 HMAC-SHA1 partagé entre YubiKeys pour KeePassXC (sans exporter la réponse)'
printf '%s\n' '✅ Confirmé : clé GPG logicielle RSA4096 [SC], sous-clé RSA4096 [E] ; signature et chiffrement/déchiffrement de test validés'
printf '%s\n' 'ℹ️ Carte de secours précédemment observée : OpenPGP signature/encryption/authentication [none] ; ne pas présumer que la carte présente est la même.'
printf '%s\n' '⚠️ Non validé : clés SSH stockées sur YubiKey, FIDO2 discoverable credentials, slots PIV SSH, ssh-agent ou PIV comme backend de SSH.'
printf '%s\n' '⚠️ Non validé : signature de commit Git, git-crypt et restauration PostgreSQL en conditions réelles.'
heading 'SSH local (aucune empreinte ni clé affichée)'
if command -v ssh-add >/dev/null 2>&1; then
  if ssh-add -l >/dev/null 2>&1; then
    ok 'SSH agent contient au moins une identité ; provenance YubiKey non démontrée'
  else
    warn 'Aucune identité SSH utilisable confirmée par ssh-add -l (ou agent inaccessible)'
  fi
fi
if command -v ssh-keygen >/dev/null 2>&1; then
  ok 'ssh-keygen disponible ; aucune opération de création/export de clé exécutée'
fi
heading 'OpenPGP : état des emplacements (lecture seule, valeurs masquées)'
if command -v gpg >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
  card="$(timeout 15 gpg --card-status 2>/dev/null || true)"
  if [[ "$card" == *'Application type .: OpenPGP'* ]]; then
    ok 'OpenPGP reconnu par scdaemon'
    for label in 'Signature key' 'Encryption key' 'Authentication key'; do
      if printf '%s\n' "$card" | grep -Eq "^$label[.[:space:]]*:[[:space:]]*\\[none\\]"; then
        printf 'ℹ️ %s: vide sur la carte connectée\n' "$label"
      elif printf '%s\n' "$card" | grep -Eq "^$label[.[:space:]]*:"; then
        printf 'ℹ️ %s: présent ou indéterminé (identifiant masqué)\n' "$label"
      else
        printf '⚠️ %s: non déterminé\n' "$label"
      fi
    done
  else
    warn 'Carte OpenPGP non accessible via GnuPG (absente, transport ou client)'
  fi
fi

heading 'Outils SSH / GPG / age / PAM / Keyring'
for tool in gpg ssh-keygen pamu2fcfg age age-plugin-yubikey secret-tool seahorse; do
  if command -v "${tool}" >/dev/null 2>&1; then ok "${tool} installé"; else warn "${tool} absent"; fi
done
heading 'SOPS / age : possibilité de clé matérielle (lecture seule)'
if command -v sops >/dev/null 2>&1; then
  ok 'sops installé ; vérifier la version et le support des destinataires age plugin'
else
  warn 'sops non trouvé dans PATH'
fi
if command -v age-plugin-yubikey >/dev/null 2>&1; then
  ok 'age-plugin-yubikey installé ; aucun slot provisionné automatiquement'
else
  warn 'age-plugin-yubikey absent : identité age matérielle non vérifiée'
fi
printf '%s\n' 'ℹ️ age X25519 existant de fastapi-sample : identité logicielle ; non importable telle quelle dans PIV.'
printf '%s\n' 'ℹ️ PIV 9A occupé, 9C/9D/9E non confirmés libres ; inventaire avant tout provisioning.'
printf '%s\n' 'ℹ️ Une identité age YubiKey serait un destinataire SOPS supplémentaire, jamais un remplacement sans tests.'

heading 'Sécurité'
warn 'Ne pas réinitialiser PIV : sauvegarder et examiner les usages du certificat expiré.'
ok 'Aucune opération de provisionnement ou modification PAM effectuée.'
printf '📚 Documentation : docs/workstation-yubikey-full-capabilities.md\n'
