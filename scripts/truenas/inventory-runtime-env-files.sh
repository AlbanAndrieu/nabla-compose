#!/usr/bin/env bash
set -euo pipefail

DEEP=0
APP_FILTER=""
POOL="${NABLA_ZFS_POOL:-cpool}"
POOL_ROOT="${NABLA_POOL_ROOT:-/mnt/${POOL}}"
CANONICAL_ROOT="${NABLA_CANONICAL_ROOT:-${POOL_ROOT}/compose/nabla-compose}"
SECRETS_ROOT="${NABLA_SECRETS_ROOT:-${POOL_ROOT}/secrets}"

usage() {
  cat <<'USAGE'
usage: inventory-runtime-env-files.sh [--deep] [app]

Read-only, value-blind inventory of .env/.env.secrets runtime candidates.

  --deep  additionally report nested .env* candidates outside the canonical
          repository, canonical secrets tree, and direct /mnt/<pool>/<app>/ roots.
  app     optional repository/runtime application filter.

The command never reads or prints file contents. It reports only path,
classification, risk state, owner/group, mode, byte size and symlink target when relevant.
USAGE
}

while (($#)); do
  case "$1" in
    --deep)
      DEEP=1
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    --*)
      printf 'ERROR: unsupported option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
    *)
      if [[ -n "${APP_FILTER}" ]]; then
        printf 'ERROR: only one app filter is supported\n' >&2
        exit 2
      fi
      APP_FILTER="$1"
      ;;
  esac
  shift
done

if [[ -n "${APP_FILTER}" && ! "${APP_FILTER}" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  printf 'ERROR: invalid app filter: %s\n' "${APP_FILTER}" >&2
  exit 2
fi

if [[ "${EUID}" -ne 0 ]]; then
  printf 'ERROR: run with sudo so root-only runtime files are visible\n' >&2
  exit 1
fi

for command in find stat sort readlink basename; do
  command -v "${command}" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "${command}" >&2
    exit 1
  }
done

matches_app() {
  local app="$1"
  [[ -z "${APP_FILTER}" || "${app}" == "${APP_FILTER}" ]]
}

app_from_path() {
  local category="$1" path="$2" relative
  case "${category}" in
    canonical-runtime)
      relative="${path#"${SECRETS_ROOT}"/runtime/}"
      ;;
    canonical-bootstrap)
      relative="${path#"${SECRETS_ROOT}"/bootstrap/}"
      ;;
    repository-local)
      relative="${path#"${CANONICAL_ROOT}"/apps/}"
      ;;
    legacy-root | nested-candidate)
      relative="${path#"${POOL_ROOT}"/}"
      ;;
    *)
      relative="${path}"
      ;;
  esac
  printf '%s\n' "${relative%%/*}"
}

risk_state() {
  local category="$1" path="$2" owner="$3" mode="$4" size="$5" name
  name="$(basename "${path}")"

  if [[ "${name}" == ".env.secrets" || ( "${name}" == .env.*.secrets ) ]]; then
    if [[ "${size}" == "0" ]]; then
      printf 'EMPTY_SECRET\n'
      return
    fi
    if [[ "${category}" == "canonical-runtime" || "${category}" == "canonical-bootstrap" ]]; then
      if [[ "${owner}" == "root:root" && "${mode}" == "600" ]]; then
        printf 'OK_SECRET\n'
      else
        printf 'UNSAFE_SECRET\n'
      fi
      return
    fi
    if [[ "${category}" == "repository-local" ]]; then
      printf 'WORKTREE_SECRET\n'
      return
    fi
    if [[ "${owner}" != "root:root" || "${mode}" != "600" ]]; then
      printf 'UNSAFE_SECRET\n'
    else
      printf 'LEGACY_SECRET\n'
    fi
    return
  fi

  case "${category}" in
    canonical-runtime | canonical-bootstrap) printf 'OK_ENV\n' ;;
    repository-local) printf 'WORKTREE_ENV\n' ;;
    *) printf 'LEGACY_ENV\n' ;;
  esac
}

emit_file() {
  local category="$1" path="$2" app metadata owner mode size target="-" state
  [[ -e "${path}" || -L "${path}" ]] || return 0
  app="$(app_from_path "${category}" "${path}")"
  matches_app "${app}" || return 0

  if [[ -L "${path}" ]]; then
    target="$(readlink -f -- "${path}" 2>/dev/null || true)"
    [[ -n "${target}" ]] || target="unresolved"
  fi

  metadata="$(stat -Lc '%U:%G|%a|%s' -- "${path}" 2>/dev/null || stat -c '%U:%G|%a|%s' -- "${path}")"
  IFS='|' read -r owner mode size <<<"${metadata}"
  state="$(risk_state "${category}" "${path}" "${owner}" "${mode}" "${size}")"
  printf '%-20s %-24s %-16s %-16s %-5s %-12s %s' \
    "${category}" "${app}" "${state}" "${owner}" "${mode}" "${size}" "${path}"
  if [[ "${target}" != "-" ]]; then
    printf ' -> %s' "${target}"
  fi
  printf '\n'
}

emit_glob() {
  local category="$1"
  shift
  local path
  shopt -s nullglob
  for path in "$@"; do
    emit_file "${category}" "${path}"
  done
  shopt -u nullglob
}

printf '%-20s %-24s %-16s %-16s %-5s %-12s %s\n' \
  'CLASS' 'APP' 'STATE' 'OWNER' 'MODE' 'BYTES' 'PATH'
printf '%s\n' '------------------------------------------------------------------------------------------------------------------------------------------------'

emit_glob canonical-runtime \
  "${SECRETS_ROOT}"/runtime/*/.env \
  "${SECRETS_ROOT}"/runtime/*/.env.secrets \
  "${SECRETS_ROOT}"/runtime/*/.env.*.secrets \
  "${SECRETS_ROOT}"/runtime/*/.env.compose

emit_glob canonical-bootstrap \
  "${SECRETS_ROOT}"/bootstrap/*/.env \
  "${SECRETS_ROOT}"/bootstrap/*/.env.secrets \
  "${SECRETS_ROOT}"/bootstrap/*/.env.*.secrets \
  "${SECRETS_ROOT}"/bootstrap/*/.env.compose

emit_glob repository-local \
  "${CANONICAL_ROOT}"/apps/*/.env \
  "${CANONICAL_ROOT}"/apps/*/.env.secrets \
  "${CANONICAL_ROOT}"/apps/*/.env.*.secrets \
  "${CANONICAL_ROOT}"/apps/*/.env.compose

emit_glob legacy-root \
  "${POOL_ROOT}"/*/.env \
  "${POOL_ROOT}"/*/.env.secrets \
  "${POOL_ROOT}"/*/.env.*.secrets \
  "${POOL_ROOT}"/*/.env.compose

if ((DEEP)); then
  while IFS= read -r path; do
    case "${path}" in
      "${SECRETS_ROOT}"/* | "${CANONICAL_ROOT}"/apps/*)
        continue
        ;;
    esac
    relative="${path#"${POOL_ROOT}"/}"
    if [[ "${relative}" != */*/* ]]; then
      # Direct /mnt/<pool>/<app>/.env* candidates were already reported.
      continue
    fi
    emit_file nested-candidate "${path}"
  done < <(
    find "${POOL_ROOT}" -type f \
      \( -name '.env' -o -name '.env.secrets' -o -name '.env.*.secrets' -o -name '.env.compose' \) \
      -print 2>/dev/null | sort -u
  )
fi
