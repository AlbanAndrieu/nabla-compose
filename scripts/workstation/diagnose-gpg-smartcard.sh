#!/usr/bin/env bash
# Read-only GnuPG smartcard transport triage; never restart services or edit config.
set -euo pipefail
export LC_ALL=C
green=''; yellow=''; cyan=''; host_only=false
if [[ -t 1 && -z "${NO_COLOR:-}" && "${TERM:-dumb}" != dumb ]]; then
  green=$'\033[32m'; yellow=$'\033[33m'; cyan=$'\033[36m'; reset=$'\033[0m'
else reset=''; fi
heading() { printf '\n%s🔐 %s%s\n' "${cyan}" "$1" "${reset}"; }
warn() { printf '%s⚠️  %s%s\n' "${yellow}" "$1" "${reset}"; }
ok() { printf '%s✅ %s%s\n' "${green}" "$1" "${reset}"; }
case "${1:---check}" in
  --check) ;;
  --host-only) host_only=true ;;
  -h|--help) echo 'Usage: bash scripts/workstation/diagnose-gpg-smartcard.sh [--check|--host-only]'; exit 0 ;;
  *) echo 'Unknown option' >&2; exit 2 ;;
esac
heading 'Contexte GnuPG (sans secrets)'
for tool in gpg gpgconf gpg-connect-agent ykman systemctl; do
  if command -v "${tool}" >/dev/null; then ok "${tool} présent"; else warn "${tool} absent"; fi
done
if command -v gpg >/dev/null; then gpg --version | head -n 2; fi
if command -v gpgconf >/dev/null; then
  printf 'GPG homedir: %s\n' "$(gpgconf --list-dirs homedir)"
fi
heading 'Services utilisateur et PCSC'
if command -v systemctl >/dev/null; then
  for unit in pcscd.socket pcscd.service; do
    printf '%s: ' "${unit}"
    systemctl is-active "${unit}" 2>/dev/null || true
  done
  printf 'gpg-agent user: '
  systemctl --user is-active gpg-agent.service 2>/dev/null || true
fi
heading 'Configuration effective (noms de directives seulement)'
cfg="${GNUPGHOME:-${HOME}/.gnupg}/scdaemon.conf"
if [[ -r "${cfg}" ]]; then
  for setting in disable-ccid pcsc-driver reader-port; do
    if grep -Eq "^[[:space:]]*${setting}([[:space:]]|$)" "${cfg}"; then
      if [[ "${setting}" == pcsc-driver || "${setting}" == reader-port ]]; then
        warn "${setting} défini (valeur masquée)"
      else ok "${setting} défini"; fi
    else warn "${setting} absent"; fi
  done
else warn 'scdaemon.conf absent ou non lisible'; fi
heading 'Mode de diagnostic'
if "${host_only}"; then
  ok 'Mode host-only : vérification GPG/PCSC sans carte';
elif ! command -v ykman >/dev/null 2>&1 && ! { command -v lsusb >/dev/null 2>&1 && lsusb -d 1050: 2>/dev/null | grep -q '1050:'; }; then
  warn 'Aucune YubiKey détectée localement. Contrôle matériel ignoré (utiliser --host-only sur TrueNAS).'
  host_only=true
fi
if "${host_only}"; then
  printf '✅ Contrôle serveur terminé; pas de test OpenPGP matériel attendu.\n'
  exit 0
fi
heading 'Interfaces'
if command -v ykman >/dev/null; then
  ykman list --serials || true
  ykman openpgp info || warn 'Applet OpenPGP inaccessible à ykman'
fi
if command -v gpg-connect-agent >/dev/null; then
  # scdaemon may be auto-started by SCD; no key material is requested.
  result="$(printf 'SCD GETINFO version\n/bye\n' | timeout 8 gpg-connect-agent 2>&1 || true)"
  if [[ "${result}" == *'D '* && "${result}" == *'OK'* ]]; then
    ok 'scdaemon répond à GETINFO version'
  else warn 'scdaemon ne répond pas correctement à GETINFO'; fi
fi
heading 'Sélection PC/SC et isolation du lecteur'
if command -v gpg-connect-agent >/dev/null && command -v timeout >/dev/null; then
  for scd_command in 'SCD GETINFO reader_list' 'SCD SERIALNO'; do
    probe="$(printf '%s\n/bye\n' "${scd_command}" | timeout 8 gpg-connect-agent 2>&1 || true)"
    # Never print device serials or raw smartcard IDs.
    if [[ "${probe}" == *'ERR '* ]]; then
      warn "${scd_command}: refusé ou lecteur inaccessible"
    elif [[ "${scd_command}" == 'SCD GETINFO reader_list' && "${probe}" == *'card or a reader'* ]]; then
      warn 'scdaemon retourne un message sans lecteur exploitable; OK confirme seulement le protocole'
    elif [[ "${probe}" == *'OK'* ]]; then
      ok "${scd_command}: requête acceptée (données masquées)"
    else
      warn "${scd_command}: résultat non exploitable"
    fi
  done
fi
if command -v pcsc_scan >/dev/null 2>&1 && command -v timeout >/dev/null; then
  scan="$(timeout 4 pcsc_scan -n 2>&1 || true)"
  if [[ "${scan}" == *'Yubico'* || "${scan}" == *'YubiKey'* ]]; then
    ok 'Lecteur YubiKey visible par PC/SC'
  elif [[ "${scan}" == *'No readers found'* ]]; then
    warn 'PC/SC : aucun lecteur détecté'
  else
    warn 'PC/SC : présence du lecteur non confirmée'
  fi
else
  warn 'pcsc_scan absent : installer pcsc-tools sur la workstation si nécessaire'
fi
heading 'Conflits potentiels et état scdaemon'
if command -v pgrep >/dev/null 2>&1; then
  scd_count="$(pgrep -u "$(id -u)" -xc scdaemon 2>/dev/null || true)"
  printf 'Instances scdaemon utilisateur : %s\n' "${scd_count:-0}"
fi
if command -v gpgconf >/dev/null 2>&1; then
  gpgconf --check-programs 2>/dev/null | awk -F: '$1 ~ /scdaemon/ { if ($3 == "1") print "⚠️ scdaemon signale une erreur de programme"; else print "ℹ️ scdaemon référencé dans GnuPG" }' || true
fi
if [[ -r "${cfg}" ]] && grep -Eq '^[[:space:]]*disable-ccid([[:space:]]|$)' "${cfg}" && ! grep -Eq '^[[:space:]]*reader-port([[:space:]]|$)' "${cfg}"; then
  warn 'disable-ccid présent mais reader-port absent : piste connue GnuPG T4998 (PC/SC No such device)'
  printf 'ℹ️ Examiner https://dev.gnupg.org/T4998 ; ne pas écrire reader-port automatiquement.\n'
fi
warn 'Piste : scdaemon/PCSC, sélection de lecteur ou accès concurrent; aucune modification automatique'
heading 'Diagnostic matériel GPG (sans sortie brute)'
if command -v gpg >/dev/null; then
  if output="$(timeout 15 gpg --card-status 2>&1)"; then
    ok 'GnuPG détecte la carte OpenPGP'
  elif [[ "${output}" == *'No such device'* ]]; then
    warn 'GnuPG: No such device — vérifier scdaemon/PCSC et conflits CCID'
  else
    warn 'GnuPG ne détecte pas la carte (sortie volontairement masquée)'
  fi
fi
printf '\n📚 Procédure et rollback : docs/workstation-yubikey-gpg-vault-roadmap.md\n'
echo 'Aucune clé, aucun PIN, service ou fichier de configuration modifié.'
