#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
CANONICAL_ROOT="${NABLA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run with sudo so missing runtime env files can be created safely"
for command in git awk sort stat install dirname; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

discover_env_files() {
  local compose
  while IFS= read -r compose; do
    awk '
      function indent(line) {
        match(line, /^[[:space:]]*/)
        return RLENGTH
      }
      /^[[:space:]]*env_file:[[:space:]]*$/ {
        in_env = 1
        base = indent($0)
        next
      }
      in_env {
        if ($0 ~ /^[[:space:]]*$/) {
          next
        }
        current = indent($0)
        if (current <= base) {
          in_env = 0
          next
        }
        if (match($0, /\/mnt\/cpool\/[A-Za-z0-9._\/-]+\/\.env([.][A-Za-z0-9._-]+)?/)) {
          print substr($0, RSTART, RLENGTH)
        }
      }
    ' "${compose}"
  done < <(git ls-files 'apps/*/compose.yml')
}

mapfile -t env_files < <(discover_env_files | sort -u)

if ((${#env_files[@]} == 0)); then
  printf 'ℹ️  no absolute /mnt/cpool/.../.env* env_file declarations found.\n'
  exit 0
fi

missing=0
invalid=0
printf 'Repository-declared TrueNAS runtime env files:\n'
for env_file in "${env_files[@]}"; do
  parent="$(dirname "${env_file}")"
  if [[ ! -d "${parent}" ]]; then
    printf '❌ %s parent directory missing: %s\n' "${env_file}" "${parent}"
    invalid=$((invalid + 1))
    continue
  fi

  if [[ -e "${env_file}" && ! -f "${env_file}" ]]; then
    printf '❌ %s exists but is not a regular file\n' "${env_file}"
    invalid=$((invalid + 1))
    continue
  fi

  if [[ ! -f "${env_file}" ]]; then
    missing=$((missing + 1))
    if [[ "${MODE}" == "--check" ]]; then
      printf '❌ %s missing\n' "${env_file}"
      continue
    fi
    install -o root -g root -m 600 /dev/null "${env_file}"
    printf '✅ %s created root:root mode=0600 (empty; populate required values before deploy)\n' "${env_file}"
    continue
  fi

  metadata="$(stat -c '%U:%G %a' "${env_file}")"
  printf '✅ %s present owner/mode=%s (left unchanged)\n' "${env_file}" "${metadata}"
done

if [[ "${MODE}" == "--check" && ${missing} -gt 0 ]]; then
  printf '❌ %d repository-declared runtime env file(s) are missing.\n' "${missing}" >&2
  printf '   Apply with: sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply\n' >&2
  exit 1
fi

if ((invalid > 0)); then
  printf '❌ %d runtime env file path issue(s) remain.\n' "${invalid}" >&2
  exit 1
fi

printf '✅ repository-declared TrueNAS runtime env files are present (%d checked).\n' "${#env_files[@]}"
