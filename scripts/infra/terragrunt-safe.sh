#!/usr/bin/env bash
set -euo pipefail

if (($# < 2)); then
  echo "usage: $0 <infrastructure-dir> <terragrunt-args...>" >&2
  exit 2
fi

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
workdir="$1"
shift
target_dir="${repo_root}/${workdir}"

if [[ ! -d "${target_dir}" ]]; then
  echo "Infrastructure directory does not exist: ${target_dir}" >&2
  exit 2
fi

# The Garage state backend reads AWS_*; an interactive shell often carries other
# AWS keys or a profile (403 on HeadObject), so the dedicated keys win when set.
if [[ -n "${GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID:-}" && -n "${GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY:-}" ]]; then
  export AWS_ACCESS_KEY_ID="${GARAGE_OPENTOFU_AWS_ACCESS_KEY_ID}"
  export AWS_SECRET_ACCESS_KEY="${GARAGE_OPENTOFU_AWS_SECRET_ACCESS_KEY}"
  unset AWS_PROFILE AWS_SESSION_TOKEN
fi

for command in flock terragrunt; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

joined_args=" $* "
is_apply=false
if [[ "${joined_args}" == *" apply "* ]]; then
  is_apply=true
fi

if [[ "${is_apply}" == "true" ]] && { [[ "${joined_args}" == *" run-all "* ]] || [[ "${joined_args}" == *" --all "* ]]; }; then
  echo "Refusing repository-wide Terragrunt apply while Garage state has no distributed lock." >&2
  echo "Apply one infrastructure unit at a time after reviewing its plan." >&2
  exit 1
fi

lock_root="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
lock_file="${lock_root%/}/nabla-compose-terragrunt.lock"

exec 9>"${lock_file}"
if ! flock --nonblock 9; then
  echo "Another nabla-compose Terragrunt operation is already running on this host." >&2
  echo "Lock: ${lock_file}" >&2
  exit 1
fi

printf '🔒 local Terragrunt operator lock acquired: %s\n' "${lock_file}"
printf '⚠️  this lock is host-local; do not run another writer from CI or another workstation\n'
printf '📁 working directory: %s\n' "${workdir}"

if [[ "${is_apply}" == "true" ]]; then
  backup_script="${repo_root}/scripts/infra/backup-garage-state.sh"
  if [[ ! -x "${backup_script}" ]]; then
    echo "State backup guard is missing or not executable: ${backup_script}" >&2
    exit 1
  fi
  "${backup_script}" "${workdir}"
fi

cd "${target_dir}"
terragrunt "$@"
