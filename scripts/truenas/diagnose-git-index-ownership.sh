#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

ROOT="${1:-/mnt/cpool/compose/nabla-compose}"
[[ -d "${ROOT}/.git" ]] || {
  printf 'ERROR: not a Git checkout: %s\n' "${ROOT}" >&2
  exit 2
}

printf '==> Repository metadata ownership\n'
printf 'operator=%s uid=%s gid=%s\n' "$(id -un)" "$(id -u)" "$(id -g)"
stat -c 'git_dir owner=%U group=%G mode=%a path=%n' "${ROOT}/.git"
if [[ -e "${ROOT}/.git/index" ]]; then
  stat -c 'git_index owner=%U group=%G mode=%a mtime=%y path=%n' "${ROOT}/.git/index"
fi

printf '\n==> Root-owned Git index files\n'
found=0
while IFS= read -r index; do
  found=1
  stat -c 'root_owned_index owner=%U group=%G mode=%a mtime=%y path=%n' "${index}"
done < <(find "${ROOT}/.git" -type f -name index -user root -print 2>/dev/null)
if ((found == 0)); then
  printf 'OK: no root-owned index file found under %s/.git\n' "${ROOT}"
fi

printf '\n==> Scheduled Git-capable processes (read-only)\n'
for scope in /etc/crontab /etc/cron.d; do
  [[ -e "${scope}" ]] || continue
  if [[ -d "${scope}" ]]; then
    grep -RInE '(^|[[:space:]])(sudo[[:space:]]+)?git([[:space:]]|$)|nabla-compose|scripts/cron\.sh' "${scope}" 2>/dev/null || true
  else
    grep -nE '(^|[[:space:]])(sudo[[:space:]]+)?git([[:space:]]|$)|nabla-compose|scripts/cron\.sh' "${scope}" 2>/dev/null || true
  fi
done
if command -v systemctl >/dev/null 2>&1; then
  systemctl list-timers --all --no-pager 2>/dev/null |
    grep -Ei 'git|nabla|compose|cron' || true
fi

printf '\n==> Recent sudo/git journal evidence\n'
if command -v journalctl >/dev/null 2>&1; then
  journalctl --since '-24 hours' --no-pager 2>/dev/null |
    grep -Ei 'sudo.*git|COMMAND=.*git|nabla-compose|\.git/index' |
    tail -n 80 || true
else
  printf 'INFO: journalctl unavailable\n'
fi

printf '\nThis diagnostic is read-only. Repair only the exact root-owned index files after reviewing the evidence; never recursively chown the checkout and never run sudo git.\n'
