#!/usr/bin/env bash
# Copy historical local OpenClaw backups to the approved NFS target.
set -euo pipefail
umask 077
SRC="${HOME}/Backups/openclaw"
DST="/media/backup/lab/infra/openclaw"
MOUNT="/media/backup/lab"
SOURCE="nabla:/mnt/cpool/backup/lab"
color=0
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then color=1; fi
say() {
  local code="$1"; shift
  if (( color )); then printf '\033[%sm%s\033[0m\n' "${code}" "$*"
  else printf '%s\n' "$*"; fi
}
fail() { say '31' "❌ $*" >&2; exit 1; }
[[ -d "${SRC}" ]] || fail "Source absente : ${SRC}"
actual="$(findmnt -T "${DST}" -no TARGET,SOURCE,FSTYPE)" || fail "Montage NFS introuvable"
[[ "${actual}" == "${MOUNT} ${SOURCE} nfs4" ]] || fail "Montage inattendu : ${actual}"
say '36' "🔐 OpenClaw · transfert vérifié vers NFS"
say '34' "📂 Destination : ${DST}"
install -d -m 700 "${DST}/archives" "${DST}/sqlite" "${DST}/recovery"
say '36' "🗃️  Copie des snapshots SQLite"
if [[ -d "${SRC}/sqlite" ]]; then
  rsync -a --no-owner --no-group --ignore-existing -- "${SRC}/sqlite/" "${DST}/sqlite/"
  rsync -acn --no-owner --no-group --out-format='%n' -- "${SRC}/sqlite/" "${DST}/sqlite/" |
    { if IFS= read -r line; then printf '❌ Différence SQLite : %s\n' "${line}" >&2; exit 1; fi; }
fi
say '36' "📦 Copie et contrôle SHA-256 des archives"
shopt -s nullglob
archives=("${SRC}"/*.tar.gz)
for source_file in "${archives[@]}"; do
  name="${source_file##*/}"
  dest_file="${DST}/archives/${name}"
  if [[ ! -e "${dest_file}" ]]; then
    cp --no-clobber -- "${source_file}" "${dest_file}"
  fi
  [[ -f "${dest_file}" && ! -L "${dest_file}" ]] || fail "Archive cible invalide : ${name}"
  a="$(sha256sum -- "${source_file}")"; a="${a%% *}"
  b="$(sha256sum -- "${dest_file}")"; b="${b%% *}"
  [[ "${a}" == "${b}" ]] || fail "Empreinte différente : ${name}"
  say '32' "✅ ${name} · SHA-256 identique"
done
say '32' "✅ Transfert terminé, aucune source supprimée"
say '33' "⚠️  NFS et tar.gz ne garantissent pas le chiffrement ; manifeste WORM non activé"
