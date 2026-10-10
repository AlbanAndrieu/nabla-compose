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

if [[ "${MODE}" == "--repair" ]]; then
  [[ "$(id -un)" == "albandrieu" ]] || {
    printf 'ERROR: run --repair as albandrieu, without sudo\n' >&2
    exit 1
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
  [[ "${ROOT}" == "/mnt/cpool/compose/nabla-compose" ]] || {
    printf 'ERROR: repair limited to canonical TrueNAS checkout\n' >&2
    exit 1
  }

  git_group="$(stat -c '%G' -- "${ROOT}/.git")"
  [[ -n "${git_group}" ]] || {
    printf 'ERROR: cannot determine canonical .git group\n' >&2
    exit 1
  }

  printf '\n==> Repair root-owned Git index files\n'
  repair_count=0
  while IFS= read -r -d '' root_index; do
    [[ -f "${root_index}" && ! -L "${root_index}" ]] || {
      printf 'ERROR: refusing unsafe index path: %s\n' "${root_index}" >&2
      exit 1
    }
    before_mode="$(stat -c '%a' -- "${root_index}")"
    printf 'repair_index path=%s mode=%s target_owner=albandrieu:%s\n' \
      "${root_index}" "${before_mode}" "${git_group}"
    sudo chown -- "albandrieu:${git_group}" "${root_index}"
    after_mode="$(stat -c '%a' -- "${root_index}")"
    [[ "${after_mode}" == "${before_mode}" ]] || {
      printf 'ERROR: index mode changed unexpectedly for %s: %s -> %s\n' \
        "${root_index}" "${before_mode}" "${after_mode}" >&2
      exit 1
    }
    repair_count=$((repair_count + 1))
  done < <(find "${ROOT}/.git" -type f -name index -user root -print0 2>/dev/null)

  if ((repair_count == 0)); then
    printf 'OK: no root-owned Git index required repair\n'
  else
    printf 'OK: repaired %s root-owned Git index file(s); file modes preserved\n' "${repair_count}"
  fi
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

printf '\nDefault --check is read-only. --repair changes ownership only for root-owned Git index files under the canonical .git tree, preserves each file mode, never recursively chowns, resets, cleans or runs Git as root.\n'
