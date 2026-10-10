#!/usr/bin/env bash
# shellcheck shell=bash
set -euo pipefail

MODE="--check"
ROOT="/mnt/cpool/compose/nabla-compose"
for arg in "$@"; do
  case "${arg}" in
    --check|--repair) MODE="${arg}" ;;
    /*) ROOT="${arg}" ;;
    *) printf 'ERROR: unknown argument: %s\n' "${arg}" >&2; exit 2 ;;
  esac
done
# Repair is opt-in and performed from the normal operator account.
if [[ "${MODE}" == "--repair" ]]; then
  [[ "$(id -un)" == "albandrieu" ]] || {
    printf 'ERROR: run --repair as albandrieu, without sudo\n' >&2; exit 1;
  }
fi
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

printf '\n==> Main index access\n'
index="${ROOT}/.git/index"
if [[ ! -f "${index}" || -L "${index}" ]]; then
  printf 'ERROR: missing or symlinked main Git index\n' >&2
  exit 1
fi
if [[ "${MODE}" == "--repair" ]]; then
  # Only the main index. No recursive ownership change or submodule mutation.
  # Verify the checkout path and avoid repairing an unexpected target.
  [[ "${ROOT}" == "/mnt/cpool/compose/nabla-compose" ]] || {
    printf 'ERROR: repair limited to canonical TrueNAS checkout\n' >&2; exit 1;
  }
  sudo chown albandrieu:apps -- "${index}"
  sudo chmod 600 -- "${index}"
  printf 'OK: main Git index repaired to albandrieu:apps 0600\n'
fi
if [[ -w "${index}" && -w "${ROOT}/.git" ]]; then
  printf 'OK: main index and Git directory writable\n'
else
  printf 'WARNING: main index or Git directory not writable\n' >&2
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

printf '\nDefault --check is read-only. --repair adjusts only the main Git index to albandrieu:apps 0600; never recursively chown or run Git as root.\n'
