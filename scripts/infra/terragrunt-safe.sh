#!/usr/bin/env bash
set -euo pipefail

if (($# < 2)); then
  echo "usage: $0 <infrastructure-dir> <terragrunt-args...>" >&2
  exit 2
fi

workdir="$1"
shift

if [[ ! -d "${workdir}" ]]; then
  echo "Infrastructure directory does not exist: ${workdir}" >&2
  exit 2
fi

for command in flock terragrunt; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required command: ${command}" >&2
    exit 1
  fi
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
lock_root="${XDG_RUNTIME_DIR:-${TMPDIR:-/tmp}}"
lock_file="${lock_root%/}/nabla-compose-terragrunt.lock"

exec 9>"${lock_file}"
if ! flock --nonblock 9; then
  echo "Another nabla-compose Terragrunt operation is already running on this host." >&2
  echo "Lock: ${lock_file}" >&2
  exit 1
fi

printf '🔒 local Terragrunt operator lock acquired: %s\n' "${lock_file}"
printf '📁 working directory: %s\n' "${workdir}"

cd "${repo_root}/${workdir}"
terragrunt "$@"
