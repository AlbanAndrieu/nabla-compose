#!/usr/bin/env bash
# Copy historical local OpenClaw backups to the approved NFS target.
set -euo pipefail
umask 077
SRC="${HOME}/Backups/openclaw"
DST="/media/backup/lab/infra/openclaw"
MOUNT="/media/backup/lab"
SOURCE="nabla:/mnt/cpool/backup/lab"
# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"
[[ -d "${SRC}" ]] || fail "Source absente : ${SRC}"
actual="$(findmnt -T "${DST}" -no TARGET,SOURCE,FSTYPE)" || fail "Montage NFS introuvable"
[[ "${actual}" == "${MOUNT} ${SOURCE} nfs4" ]] || fail "Montage inattendu : ${actual}"
section "OpenClaw · transfert vérifié vers NFS"
info "Destination : ${DST}"
install -d -m 700 "${DST}/archives" "${DST}/sqlite" "${DST}/recovery"
section "Copie des snapshots SQLite"
if [[ -d "${SRC}/sqlite" ]]; then
  rsync -a --no-owner --no-group --ignore-existing -- "${SRC}/sqlite/" "${DST}/sqlite/"
  rsync -acn --no-owner --no-group --out-format='%n' -- "${SRC}/sqlite/" "${DST}/sqlite/" |
    { if IFS= read -r line; then fail "Différence SQLite : ${line}"; fi; }
fi
section "Copie et contrôle SHA-256 des archives"
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
  ok "${name} · SHA-256 identique"
done
ok "Transfert terminé, aucune source supprimée"
warn "NFS et tar.gz ne garantissent pas le chiffrement ; manifeste WORM non activé"
