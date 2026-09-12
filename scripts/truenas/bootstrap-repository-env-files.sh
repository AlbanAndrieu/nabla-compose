#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
POOL="${NABLA_ZFS_POOL:-cpool}"
CANONICAL_ROOT="${NABLA_CANONICAL_ROOT:-/mnt/cpool/compose/nabla-compose}"
SECRETS_DATASET="${NABLA_SECRETS_DATASET:-${POOL}/secrets}"
SECRETS_ROOT="${NABLA_SECRETS_ROOT:-/mnt/${POOL}/secrets}"
RUNTIME_ROOT="${NABLA_RUNTIME_ENV_ROOT:-${SECRETS_ROOT}/runtime}"
BOOTSTRAP_ROOT="${NABLA_BOOTSTRAP_ENV_ROOT:-${SECRETS_ROOT}/bootstrap}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply]" ;;
esac

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so runtime env materializations remain root-only"
for command in git awk sort stat install dirname basename cmp readlink ln rm \
  mkdir chown chmod midclt zfs; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
[[ "${ROOT}" == "${CANONICAL_ROOT}" ]] ||
  fail "run from canonical TrueNAS checkout ${CANONICAL_ROOT}; current checkout is ${ROOT}"
cd "${CANONICAL_ROOT}"

is_runtime_env_name() {
  case "$1" in
    .env | .env.secrets | .env.*.secrets) return 0 ;;
    *) return 1 ;;
  esac
}

canonical_env_file() {
  local app="$1" source="$2" name root
  name="$(basename "${source}")"
  if [[ "${app}" == "vaultwarden" ]]; then
    root="${BOOTSTRAP_ROOT}/${app}"
  else
    root="${RUNTIME_ROOT}/${app}"
  fi
  printf '%s/%s\n' "${root}" "${name}"
}

discover_declared_env_files() {
  local compose app
  while IFS= read -r compose; do
    app="${compose#apps/}"
    app="${app%%/*}"
    awk -v app="${app}" '
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
        if ($0 ~ /^[[:space:]]*#/ || $0 ~ /^[[:space:]]*$/) {
          next
        }
        current = indent($0)
        if (current <= base) {
          in_env = 0
          next
        }
        line = $0
        sub(/[[:space:]]+#.*/, "", line)
        if (match(line, /\/mnt\/cpool\/[A-Za-z0-9._\/-]+\/\.env([.][A-Za-z0-9._-]+)?/)) {
          print app "|" substr(line, RSTART, RLENGTH) "|declared"
          next
        }
        if (match(line, /([.][\/])?[.]env([.][A-Za-z0-9._-]+)?/)) {
          print app "|" substr(line, RSTART, RLENGTH) "|declared-relative"
        }
      }
    ' "${compose}"
  done < <(git ls-files 'apps/*/compose.yml')
}

check_private_directory() {
  local path="$1" metadata
  if [[ ! -d "${path}" ]]; then
    printf '❌ private runtime directory missing: %s\n' "${path}"
    return 1
  fi
  metadata="$(stat -c '%U:%G %a' "${path}")"
  if [[ "${metadata}" != "root:root 700" ]]; then
    printf '❌ %s owner/mode=%s; expected root:root 700\n' \
      "${path}" "${metadata}"
    return 1
  fi
}

ensure_secrets_root() {
  local payload metadata
  if ! zfs list -H -o name "${SECRETS_DATASET}" >/dev/null 2>&1; then
    if [[ "${MODE}" == "--check" ]]; then
      printf '❌ canonical secrets dataset missing: %s\n' "${SECRETS_DATASET}"
      return 1
    fi
    payload="$(printf \
      '{"name":"%s","type":"FILESYSTEM","share_type":"GENERIC"}' \
      "${SECRETS_DATASET}")"
    midclt call pool.dataset.create "${payload}" >/dev/null
  fi

  [[ -d "${SECRETS_ROOT}" ]] || fail "missing secrets mountpoint ${SECRETS_ROOT}"
  metadata="$(stat -c '%U:%G %a' "${SECRETS_ROOT}")"
  if [[ "${metadata}" != "root:root 700" ]]; then
    if [[ "${MODE}" == "--check" ]]; then
      printf '❌ %s owner/mode=%s; expected root:root 700\n' \
        "${SECRETS_ROOT}" "${metadata}"
      return 1
    fi
    chown root:root "${SECRETS_ROOT}"
    chmod 700 "${SECRETS_ROOT}"
  fi

  if [[ "${MODE}" == "--check" ]]; then
    check_private_directory "${RUNTIME_ROOT}" || return 1
    check_private_directory "${BOOTSTRAP_ROOT}" || return 1
    return 0
  fi

  mkdir -p "${RUNTIME_ROOT}" "${BOOTSTRAP_ROOT}"
  chown root:root "${RUNTIME_ROOT}" "${BOOTSTRAP_ROOT}"
  chmod 700 "${RUNTIME_ROOT}" "${BOOTSTRAP_ROOT}"
}

declare -A source_app=()
declare -A source_kind=()

while IFS='|' read -r app declared kind; do
  [[ -n "${app}" && -n "${declared}" ]] || continue
  if [[ "${declared}" == /* ]]; then
    source="${declared}"
  else
    source="${CANONICAL_ROOT}/apps/${app}/${declared#./}"
  fi
  source_app["${source}"]="${app}"
  source_kind["${source}"]="${kind}"
done < <(discover_declared_env_files | sort -u)

# Include ignored local env files that are not explicit env_file entries. This
# catches historical implicit Compose .env files such as Vaultwarden's while
# keeping examples/templates out of the runtime migration.
shopt -s nullglob
for local_env in "${CANONICAL_ROOT}"/apps/*/.env \
  "${CANONICAL_ROOT}"/apps/*/.env.secrets \
  "${CANONICAL_ROOT}"/apps/*/.env.*.secrets; do
  [[ -f "${local_env}" || -L "${local_env}" ]] || continue
  name="$(basename "${local_env}")"
  is_runtime_env_name "${name}" || continue
  app="${local_env#"${CANONICAL_ROOT}"/apps/}"
  app="${app%%/*}"
  source_app["${local_env}"]="${app}"
  source_kind["${local_env}"]="implicit-local"
done

# Existing root-level TrueNAS env files are migration inputs. A declared path
# wins when an app folder name differs from its historical dataset name.
for legacy_env in /mnt/"${POOL}"/*/.env \
  /mnt/"${POOL}"/*/.env.secrets \
  /mnt/"${POOL}"/*/.env.*.secrets; do
  [[ -f "${legacy_env}" || -L "${legacy_env}" ]] || continue
  [[ "${legacy_env}" == "${SECRETS_ROOT}/"* ]] && continue
  [[ -n "${source_app["${legacy_env}"]:-}" ]] && continue
  name="$(basename "${legacy_env}")"
  is_runtime_env_name "${name}" || continue
  app="${legacy_env#/mnt/"${POOL}"/}"
  app="${app%%/*}"
  source_app["${legacy_env}"]="${app}"
  source_kind["${legacy_env}"]="legacy-root"
done
shopt -u nullglob

if ((${#source_app[@]} == 0)); then
  printf 'ℹ️  no repository/runtime env materializations discovered.\n'
  exit 0
fi

if ! ensure_secrets_root; then
  exit 1
fi

pending=0
invalid=0
printf 'Canonical TrueNAS runtime env materializations:\n'
while IFS= read -r source; do
  app="${source_app["${source}"]}"
  kind="${source_kind["${source}"]}"
  canonical="$(canonical_env_file "${app}" "${source}")"
  canonical_parent="$(dirname "${canonical}")"

  if [[ "${source}" == "${canonical}" ]]; then
    if [[ ! -f "${canonical}" ]]; then
      pending=$((pending + 1))
      if [[ "${MODE}" == "--check" ]]; then
        printf '❌ %s missing app=%s\n' "${canonical}" "${app}"
        continue
      fi
      mkdir -p "${canonical_parent}"
      chown root:root "${canonical_parent}"
      chmod 700 "${canonical_parent}"
      install -o root -g root -m 600 /dev/null "${canonical}"
    fi
  elif [[ -L "${source}" ]]; then
    resolved="$(readlink -f "${source}" || true)"
    if [[ "${resolved}" != "${canonical}" ]]; then
      printf '❌ %s symlink target=%s expected=%s\n' \
        "${source}" "${resolved:-unresolved}" "${canonical}"
      invalid=$((invalid + 1))
      continue
    fi
  elif [[ -f "${source}" ]]; then
    pending=$((pending + 1))
    if [[ -f "${canonical}" ]] && ! cmp -s "${source}" "${canonical}"; then
      printf '❌ migration conflict: %s and %s differ\n' \
        "${source}" "${canonical}"
      invalid=$((invalid + 1))
      continue
    fi
    if [[ "${MODE}" == "--check" ]]; then
      printf '⚠️  %s app=%s kind=%s -> %s migration-required\n' \
        "${source}" "${app}" "${kind}" "${canonical}"
      continue
    fi
    mkdir -p "${canonical_parent}"
    chown root:root "${canonical_parent}"
    chmod 700 "${canonical_parent}"
    if [[ ! -f "${canonical}" ]]; then
      install -o root -g root -m 600 "${source}" "${canonical}"
      cmp -s "${source}" "${canonical}" ||
        fail "copy verification failed for ${source}"
    fi
    rm -f "${source}"
    ln -s "${canonical}" "${source}"
  else
    pending=$((pending + 1))
    if [[ "${MODE}" == "--check" ]]; then
      printf '❌ %s missing; canonical target=%s app=%s\n' \
        "${source}" "${canonical}" "${app}"
      continue
    fi
    mkdir -p "${canonical_parent}"
    chown root:root "${canonical_parent}"
    chmod 700 "${canonical_parent}"
    if [[ ! -f "${canonical}" ]]; then
      install -o root -g root -m 600 /dev/null "${canonical}"
    fi
    source_parent="$(dirname "${source}")"
    [[ -d "${source_parent}" ]] ||
      fail "legacy env parent missing: ${source_parent}"
    ln -s "${canonical}" "${source}"
  fi

  if [[ ! -f "${canonical}" ]]; then
    printf '❌ canonical env file missing after reconciliation: %s\n' \
      "${canonical}"
    invalid=$((invalid + 1))
    continue
  fi

  metadata="$(stat -c '%U:%G %a' "${canonical}")"
  if [[ "${metadata}" != "root:root 600" ]]; then
    if [[ "${MODE}" == "--check" ]]; then
      printf '❌ %s owner/mode=%s expected=root:root 600\n' \
        "${canonical}" "${metadata}"
      invalid=$((invalid + 1))
      continue
    fi
    chown root:root "${canonical}"
    chmod 600 "${canonical}"
    metadata="root:root 600"
  fi

  if [[ "${source}" == "${canonical}" ]]; then
    printf '✅ %s app=%s owner/mode=%s\n' \
      "${canonical}" "${app}" "${metadata}"
  else
    printf '✅ %s app=%s -> %s owner/mode=%s\n' \
      "${source}" "${app}" "${canonical}" "${metadata}"
  fi
done < <(printf '%s\n' "${!source_app[@]}" | sort)

if [[ "${MODE}" == "--check" && ${pending} -gt 0 ]]; then
  printf '❌ %d env materialization(s) still require canonical migration.\n' \
    "${pending}" >&2
  printf '   Apply with: sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply\n' >&2
  exit 1
fi

if ((invalid > 0)); then
  printf '❌ %d runtime env materialization issue(s) remain.\n' \
    "${invalid}" >&2
  exit 1
fi

printf '✅ runtime env materializations are centralized under %s.\n' \
  "${SECRETS_ROOT}"
