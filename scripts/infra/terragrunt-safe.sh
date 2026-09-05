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

for command in flock terragrunt; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

joined_args=" $* "
if [[ "${joined_args}" == *" apply "* ]] && { [[ "${joined_args}" == *" run-all "* ]] || [[ "${joined_args}" == *" --all "* ]]; }; then
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

cd "${target_dir}"
terragrunt "$@"
