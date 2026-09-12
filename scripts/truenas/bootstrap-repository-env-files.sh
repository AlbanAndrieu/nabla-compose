#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_FILTER="${2:-}"
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

usage() {
  cat <<'USAGE'
usage: bootstrap-repository-env-files.sh [--check|--apply|--finalize] [app]

  --check       read-only migration/status preview
  --apply       stage verified root-only canonical copies; keep old paths intact
  --finalize    replace byte-identical legacy paths with compatibility symlinks

The optional app argument scopes the operation to one repository app. Finalize
is intentionally separate from staging so operators can validate canonical
copies and service health before old paths are replaced.
USAGE
}

case "${MODE}" in
  --check | --apply | --finalize) ;;
  -h | --help)
    usage
    exit 0
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac

if [[ -n "${APP_FILTER}" && ! "${APP_FILTER}" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  fail "invalid app filter: ${APP_FILTER}"
fi

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

app_selected() {
  local app="$1"
  [[ -z "${APP_FILTER}" || "${app}" == "${APP_FILTER}" ]]
}

is_runtime_env_name() {
  case "$1" in
    .env | .env.secrets | .env.*.secrets | .env.compose) return 0 ;;
    *) return 1 ;;
  esac
}

canonical_env_file() {
  local app="$1" source="$2" kind="$3" name root
  name="$(basename "${source}")"
  if [[ "${kind}" == "implicit-local" && "${name}" == ".env" ]]; then
    name=".env.compose"
  fi
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
    app_selected "${app}" || continue
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
          print app "|" substr(line, RSTART, RLENGTH)
          next
        }
        if (match(line, /([.][\/])?[.]env([.][A-Za-z0-9._-]+)?/)) {
          print app "|" substr(line, RSTART, RLENGTH)
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
    if [[ "${MODE}" == "--check" || "${MODE}" == "--finalize" ]]; then
      printf '❌ canonical secrets dataset missing: %s\n' "${SECRETS_DATASET}"
      return 1
    fi
    payload="$(printf \
      '{"name":"%s","type":"FILESYSTEM","share_type":"GENERIC"}' \
      "${SECRETS_DATASET}")"
    midclt call pool.dataset.create "${payload}" >/dev/null
  fi

  if [[ ! -d "${SECRETS_ROOT}" ]]; then
    printf '❌ canonical secrets mountpoint missing: %s\n' "${SECRETS_ROOT}"
    return 1
  fi

  metadata="$(stat -c '%U:%G %a' "${SECRETS_ROOT}")"
  if [[ "${metadata}" != "root:root 700" ]]; then
    if [[ "${MODE}" == "--check" || "${MODE}" == "--finalize" ]]; then
      printf '❌ %s owner/mode=%s; expected root:root 700\n' \
        "${SECRETS_ROOT}" "${metadata}"
      return 1
    fi
    chown root:root "${SECRETS_ROOT}"
    chmod 700 "${SECRETS_ROOT}"
  fi

  if [[ "${MODE}" == "--check" || "${MODE}" == "--finalize" ]]; then
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
declare -A source_target=()
declare -A target_app=()
declare -A target_origin=()
declare -A target_primary_source=()
declare -A target_primary_kind=()

kind_priority() {
  case "$1" in
    declared) printf '10\n' ;;
    legacy-root) printf '20\n' ;;
    implicit-local) printf '30\n' ;;
    *) printf '90\n' ;;
  esac
}

register_target() {
  local app="$1" target="$2" origin="$3"
  target_app["${target}"]="${app}"
  if [[ -z "${target_origin["${target}"]:-}" ]]; then
    target_origin["${target}"]="${origin}"
  fi
}

register_source() {
  local app="$1" source="$2" kind="$3" target current current_kind new_priority current_priority
  target="$(canonical_env_file "${app}" "${source}" "${kind}")"
  source_app["${source}"]="${app}"
  source_kind["${source}"]="${kind}"
  source_target["${source}"]="${target}"
  register_target "${app}" "${target}" "${source}"

  current="${target_primary_source["${target}"]:-}"
  current_kind="${target_primary_kind["${target}"]:-}"
  if [[ -z "${current}" ]]; then
    target_primary_source["${target}"]="${source}"
    target_primary_kind["${target}"]="${kind}"
    return
  fi
  new_priority="$(kind_priority "${kind}")"
  current_priority="$(kind_priority "${current_kind}")"
  if ((new_priority < current_priority)); then
    target_primary_source["${target}"]="${source}"
    target_primary_kind["${target}"]="${kind}"
  fi
}

while IFS='|' read -r app declared; do
  [[ -n "${app}" && -n "${declared}" ]] || continue
  if [[ "${declared}" == /* ]]; then
    source="${declared}"
  else
    source="${CANONICAL_ROOT}/apps/${app}/${declared#./}"
  fi

  if [[ "${source}" == "${SECRETS_ROOT}/"* ]]; then
    target="${source}"
  else
    target="$(canonical_env_file "${app}" "${source}" "declared")"
  fi
  register_target "${app}" "${target}" "${source}"

  if [[ "${source}" != "${target}" ]]; then
    if [[ -f "${source}" || -L "${source}" ]]; then
      register_source "${app}" "${source}" "declared"
    fi
  fi
done < <(discover_declared_env_files | sort -u)

# Repository-local env files are Compose interpolation materializations unless
# they are already declared through env_file. Give project .env a distinct
# canonical name (.env.compose) so it can never collide with a service env_file
# named .env for the same application.
shopt -s nullglob
for local_env in "${CANONICAL_ROOT}"/apps/*/.env \
  "${CANONICAL_ROOT}"/apps/*/.env.secrets \
  "${CANONICAL_ROOT}"/apps/*/.env.*.secrets; do
  [[ -f "${local_env}" || -L "${local_env}" ]] || continue
  [[ -n "${source_app["${local_env}"]:-}" ]] && continue
  name="$(basename "${local_env}")"
  is_runtime_env_name "${name}" || continue
  app="${local_env#"${CANONICAL_ROOT}"/apps/}"
  app="${app%%/*}"
  app_selected "${app}" || continue
  register_source "${app}" "${local_env}" "implicit-local"
done

# Existing top-level TrueNAS env files are migration inputs. An explicit
# env_file declaration wins over this fallback classification.
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
  app_selected "${app}" || continue
  register_source "${app}" "${legacy_env}" "legacy-root"
done
shopt -u nullglob

if ((${#target_app[@]} == 0 && ${#source_app[@]} == 0)); then
  printf 'ℹ️  no repository/runtime env materializations discovered.\n'
  exit 0
fi

root_issue=0
if ! ensure_secrets_root; then
  if [[ "${MODE}" != "--check" ]]; then
    exit 1
  fi
  root_issue=1
  printf 'ℹ️  continuing read-only migration preview despite missing/noncanonical secrets root.\n'
fi

stage_required=0
finalize_pending=0
invalid=0
missing_required=0
printf 'Canonical TrueNAS runtime env materializations:\n'

# Validate all sources that converge on the same canonical target before any
# write. This prevents two historical .env files from being merged silently.
while IFS= read -r target; do
  primary="${target_primary_source["${target}"]:-}"
  [[ -n "${primary}" ]] || continue
  while IFS= read -r source; do
    [[ "${source_target["${source}"]}" == "${target}" ]] || continue
    [[ "${source}" == "${primary}" ]] && continue
    if [[ -f "${source}" && -f "${primary}" ]] && ! cmp -s "${source}" "${primary}"; then
      printf '❌ migration conflict: multiple sources differ for %s: %s <> %s\n' \
        "${target}" "${primary}" "${source}"
      invalid=$((invalid + 1))
    fi
  done < <(printf '%s\n' "${!source_app[@]}" | sort)
done < <(printf '%s\n' "${!target_app[@]}" | sort)

if ((invalid > 0)); then
  printf '❌ %d migration source conflict(s) must be resolved before staging.\n' \
    "${invalid}" >&2
  exit 1
fi

while IFS= read -r target; do
  app="${target_app["${target}"]}"
  primary="${target_primary_source["${target}"]:-}"
  target_parent="$(dirname "${target}")"

  if [[ ! -f "${target}" ]]; then
    if [[ -z "${primary}" ]]; then
      printf '❌ %s missing app=%s; no existing source can stage it (declared from %s)\n' \
        "${target}" "${app}" "${target_origin["${target}"]}"
      missing_required=$((missing_required + 1))
      continue
    fi

    stage_required=$((stage_required + 1))
    if [[ "${MODE}" == "--check" ]]; then
      printf '⚠️  %s app=%s source=%s -> stage-required\n' \
        "${target}" "${app}" "${primary}"
      continue
    fi
    if [[ "${MODE}" == "--finalize" ]]; then
      printf '❌ %s is not staged; run --apply first\n' "${target}"
      invalid=$((invalid + 1))
      continue
    fi

    mkdir -p "${target_parent}"
    chown root:root "${target_parent}"
    chmod 700 "${target_parent}"
    install -o root -g root -m 600 "${primary}" "${target}"
    cmp -s "${primary}" "${target}" ||
      fail "copy verification failed for ${primary} -> ${target}"
    printf '✅ %s app=%s staged from %s; legacy path left intact\n' \
      "${target}" "${app}" "${primary}"
  fi

  if [[ ! -f "${target}" ]]; then
    continue
  fi

  metadata="$(stat -c '%U:%G %a' "${target}")"
  if [[ "${metadata}" != "root:root 600" ]]; then
    if [[ "${MODE}" == "--check" || "${MODE}" == "--finalize" ]]; then
      printf '❌ %s owner/mode=%s expected=root:root 600\n' \
        "${target}" "${metadata}"
      invalid=$((invalid + 1))
    else
      chown root:root "${target}"
      chmod 600 "${target}"
      metadata="root:root 600"
    fi
  fi

done < <(printf '%s\n' "${!target_app[@]}" | sort)

# Report or finalize historical paths only after canonical copies exist.
while IFS= read -r source; do
  app="${source_app["${source}"]}"
  kind="${source_kind["${source}"]}"
  target="${source_target["${source}"]}"

  if [[ -L "${source}" ]]; then
    resolved="$(readlink -f "${source}" || true)"
    if [[ "${resolved}" == "${target}" ]]; then
      printf '✅ %s app=%s kind=%s -> %s compatibility-link\n' \
        "${source}" "${app}" "${kind}" "${target}"
    else
      printf '❌ %s symlink target=%s expected=%s\n' \
        "${source}" "${resolved:-unresolved}" "${target}"
      invalid=$((invalid + 1))
    fi
    continue
  fi

  [[ -f "${source}" ]] || continue
  if [[ ! -f "${target}" ]]; then
    continue
  fi
  if ! cmp -s "${source}" "${target}"; then
    printf '❌ migration conflict: %s differs from staged target %s\n' \
      "${source}" "${target}"
    invalid=$((invalid + 1))
    continue
  fi

  if [[ "${MODE}" == "--finalize" ]]; then
    rm -f "${source}"
    ln -s "${target}" "${source}"
    printf '✅ %s app=%s kind=%s -> %s finalized compatibility-link\n' \
      "${source}" "${app}" "${kind}" "${target}"
  else
    finalize_pending=$((finalize_pending + 1))
    printf '⚠️  %s app=%s kind=%s -> %s staged; finalize pending\n' \
      "${source}" "${app}" "${kind}" "${target}"
  fi
done < <(printf '%s\n' "${!source_app[@]}" | sort)

status=0
if ((root_issue > 0)); then
  status=1
fi
if [[ "${MODE}" == "--check" && ${stage_required} -gt 0 ]]; then
  printf '❌ %d canonical env materialization(s) still require staging.\n' \
    "${stage_required}" >&2
  printf '   Stage copies without replacing old paths: sudo bash scripts/truenas/bootstrap-repository-runtime.sh --apply\n' >&2
  status=1
fi
if ((missing_required > 0)); then
  printf '❌ %d declared runtime env materialization(s) have no recoverable source.\n' \
    "${missing_required}" >&2
  status=1
fi
if ((invalid > 0)); then
  printf '❌ %d runtime env migration issue(s) remain.\n' "${invalid}" >&2
  status=1
fi
if ((status > 0)); then
  exit 1
fi

if ((finalize_pending > 0)); then
  printf '⚠️  %d staged legacy path(s) remain intact. Finalize one service only after its canonical Compose/runtime path is accepted.\n' \
    "${finalize_pending}"
  printf '   Example: sudo bash scripts/truenas/bootstrap-repository-env-files.sh --finalize scanopy\n'
fi
printf '✅ runtime env canonical copies are consistent under %s.\n' "${SECRETS_ROOT}"
