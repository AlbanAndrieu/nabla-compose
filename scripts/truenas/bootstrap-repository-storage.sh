#!/usr/bin/env bash
set -euo pipefail

MODE="${1:---check}"
APP_FILTER="${2:-}"
POOL="${NABLA_ZFS_POOL:-cpool}"
CANONICAL_MOUNT="/mnt/${POOL}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

case "${MODE}" in
  --check | --apply) ;;
  *) fail "usage: $0 [--check|--apply] [app]" ;;
esac

if [[ -n "${APP_FILTER}" && ! "${APP_FILTER}" =~ ^[a-z0-9][a-z0-9._-]*$ ]]; then
  fail "invalid app filter: ${APP_FILTER}"
fi

[[ "${EUID}" -eq 0 ]] ||
  fail "run with sudo so TrueNAS datasets can be inspected/created"
for command in git sort zfs zpool midclt find grep; do
  command -v "${command}" >/dev/null 2>&1 ||
    fail "${command} is required"
done

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"
zpool list -H "${POOL}" >/dev/null 2>&1 ||
  fail "ZFS pool ${POOL} does not exist"

app_selected() {
  local app="$1"
  [[ -z "${APP_FILTER}" || "${app}" == "${APP_FILTER}" ]]
}

# Dataset creation must describe application storage, not every host path that
# happens to be mounted somewhere. In particular code-server mounts several
# sibling paths as operator workspaces; those references must not create an
# otherwise unnecessary dataset for the sibling application.
discover_persistent_mounts() {
  local app compose line trimmed source relative root

  while IFS= read -r compose; do
    app="${compose#apps/}"
    app="${app%%/*}"
    app_selected "${app}" || continue

    while IFS= read -r line; do
      trimmed="${line#"${line%%[![:space:]]*}"}"
      [[ -z "${trimmed}" || "${trimmed}" == \#* ]] && continue

      source=""
      if [[ "${trimmed}" =~ ^-[[:space:]]*\"?(${CANONICAL_MOUNT}/[A-Za-z0-9._/-]+): ]]; then
        source="${BASH_REMATCH[1]}"
      elif [[ "${trimmed}" =~ ^source:[[:space:]]*\"?(${CANONICAL_MOUNT}/[A-Za-z0-9._/-]+)\"?([[:space:]]*#.*)?$ ]]; then
        source="${BASH_REMATCH[1]}"
      fi

      [[ -n "${source}" ]] || continue
      relative="${source#"${CANONICAL_MOUNT}"/}"
      root="${relative%%/*}"

      # code-server exposes sibling datasets as workspaces. Only its own
      # cpool/code storage is authoritative for dataset creation.
      if [[ "${app}" == "code" && "${root}" != "code" ]]; then
        continue
      fi

      printf '%s|%s\n' "${app}" "${root}"
    done < "${compose}"
  done < <(git ls-files 'apps/*/compose.yml')
}

dataset_preset() {
  case "$1" in
    compose | logs | model | secrets | iso | k8s | k8s/*) printf 'GENERIC\n' ;;
    *) printf 'APPS\n' ;;
  esac
}

declare -A declared_paths=()
declare -A app_owned_roots=()

while IFS='|' read -r app root; do
  [[ -n "${app}" && -n "${root}" ]] || continue
  app_owned_roots["${root}"]=1
  declared_paths["${root}"]="$(dataset_preset "${root}")"
done < <(discover_persistent_mounts | sort -u)

# These datasets are repository-owned platform prerequisites rather than Docker
# Compose bind mounts. Keep them explicit so a full bootstrap can reconstruct
# the TrueNAS control/storage hierarchy used by Vaultwarden materialization,
# Talos VM disks, Kubernetes NFS/CSI, and the pinned Talos installation ISO.
if [[ -z "${APP_FILTER}" ]]; then
  declared_paths["secrets"]="GENERIC"
  declared_paths["k8s"]="GENERIC"
  declared_paths["k8s/talos-vms"]="GENERIC"
  declared_paths["k8s/nfs"]="GENERIC"
  declared_paths["k8s/csi"]="GENERIC"
  declared_paths["iso"]="GENERIC"
fi

if ((${#declared_paths[@]} == 0)); then
  if [[ -n "${APP_FILTER}" ]]; then
    printf 'ℹ️  app %s declares no application-owned %s/<dataset> bind mounts.\n' \
      "${APP_FILTER}" "${CANONICAL_MOUNT}"
    exit 0
  fi
  fail "no repository-owned TrueNAS datasets discovered"
fi

dataset_is_empty() {
  local mountpoint="$1"
  [[ -d "${mountpoint}" ]] || return 1
  ! find "${mountpoint}" -mindepth 1 -maxdepth 1 -print -quit |
    grep -q .
}

apps_preset_matches() {
  local dataset="$1" acltype aclmode atime
  acltype="$(zfs get -H -o value acltype "${dataset}" 2>/dev/null || true)"
  aclmode="$(zfs get -H -o value aclmode "${dataset}" 2>/dev/null || true)"
  atime="$(zfs get -H -o value atime "${dataset}" 2>/dev/null || true)"

  [[ "${acltype}" =~ ^(nfsv4|nfs4)$ ]] &&
    [[ "${aclmode}" == "passthrough" ]] &&
    [[ "${atime}" == "off" ]]
}

create_dataset() {
  local dataset="$1" preset="$2" payload
  payload="$(printf \
    '{"name":"%s","type":"FILESYSTEM","share_type":"%s"}' \
    "${dataset}" "${preset}")"
  midclt call pool.dataset.create "${payload}" >/dev/null
}

missing=0
preset_warnings=0
if [[ -n "${APP_FILTER}" ]]; then
  printf 'Repository-owned TrueNAS dataset roots (%s, app=%s):\n' \
    "${POOL}" "${APP_FILTER}"
else
  printf 'Repository-owned TrueNAS datasets (%s; apps + platform prerequisites):\n' \
    "${POOL}"
fi

while IFS= read -r relative; do
  dataset="${POOL}/${relative}"
  mount_root="${CANONICAL_MOUNT}/${relative}"
  preset="${declared_paths["${relative}"]}"

  if ! zfs list -H -o name "${dataset}" >/dev/null 2>&1; then
    missing=$((missing + 1))
    if [[ "${MODE}" == "--check" ]]; then
      printf '❌ %-32s missing expected-preset=%s\n' \
        "${dataset}" "${preset}"
      continue
    fi

    printf 'Creating missing dataset %s preset=%s...\n' \
      "${dataset}" "${preset}"
    create_dataset "${dataset}" "${preset}"
    zfs list -H -o name "${dataset}" >/dev/null 2>&1 ||
      fail "dataset ${dataset} was not visible after creation"
  fi

  mountpoint="$(zfs get -H -o value mountpoint "${dataset}")"
  [[ "${mountpoint}" == "${mount_root}" ]] ||
    fail "dataset ${dataset} mounted at ${mountpoint}, expected ${mount_root}"

  empty="no"
  if dataset_is_empty "${mountpoint}"; then
    empty="yes"
  fi

  if [[ "${preset}" == "APPS" ]] && ! apps_preset_matches "${dataset}"; then
    preset_warnings=$((preset_warnings + 1))
    printf '⚠️  %-32s mountpoint=%s empty=%s expected-preset=APPS; properties differ\n' \
      "${dataset}" "${mountpoint}" "${empty}"
  else
    printf '✅ %-32s mountpoint=%s empty=%s preset=%s\n' \
      "${dataset}" "${mountpoint}" "${empty}" "${preset}"
  fi
done < <(printf '%s\n' "${!declared_paths[@]}" | sort)

if [[ "${MODE}" == "--check" && ${missing} -gt 0 ]]; then
  printf '❌ %d repository-owned dataset(s) are missing.\n' \
    "${missing}" >&2
  printf '   Apply with: sudo bash scripts/truenas/bootstrap-repository-storage.sh --apply%s\n' \
    "${APP_FILTER:+ ${APP_FILTER}}" >&2
  exit 1
fi

# Global inventory reports unowned empty direct-child datasets. App-scoped
# checks deliberately omit this unrelated cleanup inventory so one service
# deployment stays bounded.
if [[ -z "${APP_FILTER}" ]]; then
  declare -A owned_top_level=()
  while IFS= read -r relative; do
    root="${relative%%/*}"
    owned_top_level["${root}"]=1
  done < <(printf '%s\n' "${!declared_paths[@]}" | sort -u)

  printf 'Empty direct child datasets not owned by repository application/platform storage:\n'
  orphan_empty=0
  while IFS=$'\t' read -r dataset mountpoint; do
    [[ "${dataset}" == "${POOL}" ]] && continue
    root="${dataset#"${POOL}"/}"
    [[ "${root}" == */* ]] && continue
    [[ -n "${owned_top_level[${root}]:-}" ]] && continue
    [[ "${mountpoint}" == "${CANONICAL_MOUNT}/"* ]] || continue

    if dataset_is_empty "${mountpoint}"; then
      orphan_empty=$((orphan_empty + 1))
      printf '⚠️  %-32s empty=yes; review before deletion\n' "${dataset}"
    fi
  done < <(zfs list -H -o name,mountpoint -d 1 "${POOL}")

  if ((orphan_empty == 0)); then
    printf '✅ none\n'
  fi
fi

if ((preset_warnings > 0)); then
  printf '⚠️  %d application dataset(s) differ from the TrueNAS Apps preset.\n' \
    "${preset_warnings}"
  printf '   Do not recreate non-empty datasets automatically; review empty candidates first.\n'
fi

printf '✅ repository-owned TrueNAS datasets are present (%d checked).\n' \
  "${#declared_paths[@]}"
