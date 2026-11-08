# shellcheck shell=bash
# Declarative dataset profiles (config/truenas/dataset-profiles.json): ZFS
# properties, a pool-relative quota and a directory tree beyond the TrueNAS
# APPS preset. Sourced by scripts/truenas/bootstrap-repository-storage.sh.
#
# Caller contract: POOL, CANONICAL_MOUNT, MODE (--check|--apply),
# PROFILES_FILE and a fail() function. reconcile_profile increments the global
# profile_drift; it mutates only in --apply, through the TrueNAS middleware for
# properties and with `install -d` (no chmod, inherited NFSv4 ACL kept).

profile_drift=0

pool_size_bytes() {
  zfs get -Hp -o value used,available "${POOL}" | awk '{total += $1} END {printf "%.0f\n", total}'
}

middleware_value() {
  local property="$1" value="$2"
  case "${property}" in
    compression | atime) printf '%s\n' "${value^^}" ;;
    recordsize) printf '%s\n' "${value^^}" ;;
    *) printf '%s\n' "${value}" ;;
  esac
}

reconcile_profile() {
  local relative="$1" dataset="${POOL}/$1" mount_root="${CANONICAL_MOUNT}/$1"
  local profile property wanted current percent desired current_quota owner directory payload
  profile="$(jq -c --arg ds "${relative}" '.datasets[$ds]' "${PROFILES_FILE}")"

  if ! zfs list -H -o name "${dataset}" >/dev/null 2>&1; then
    printf 'ℹ️  %-32s profile pending: dataset not created yet\n' "${dataset}"
    return 0
  fi

  payload="{}"
  while IFS=$'\t' read -r property wanted; do
    current="$(zfs get -H -o value "${property}" "${dataset}")"
    if [[ "${current,,}" != "${wanted,,}" ]]; then
      profile_drift=$((profile_drift + 1))
      printf '⚠️  %-32s %s=%s expected %s\n' "${dataset}" "${property}" "${current}" "${wanted}"
      payload="$(jq -c --arg k "${property}" --arg v "$(middleware_value "${property}" "${wanted}")" \
        '. + {($k): $v}' <<<"${payload}")"
    fi
  done < <(jq -r '.properties // {} | to_entries[] | "\(.key)\t\(.value)"' <<<"${profile}")

  percent="$(jq -r '.quotaPercentOfPool // empty' <<<"${profile}")"
  if [[ -n "${percent}" ]]; then
    [[ "${percent}" =~ ^[1-9][0-9]?$ ]] || fail "${relative}: quotaPercentOfPool must be 1-99"
    desired=$(($(pool_size_bytes) * percent / 100 / 1073741824 * 1073741824))
    current_quota="$(zfs get -Hp -o value quota "${dataset}")"
    if ((current_quota == 0 || current_quota - desired > 1073741824 || desired - current_quota > 1073741824)); then
      profile_drift=$((profile_drift + 1))
      printf '⚠️  %-32s quota=%s expected %s%% of %s = %s GiB\n' \
        "${dataset}" "${current_quota}" "${percent}" "${POOL}" "$((desired / 1073741824))"
      payload="$(jq -c --argjson q "${desired}" '. + {quota: $q}' <<<"${payload}")"
    fi
  fi

  if [[ "${payload}" != "{}" && "${MODE}" == "--apply" ]]; then
    printf 'Updating %s through the middleware: %s\n' "${dataset}" "${payload}"
    midclt call pool.dataset.update "${dataset}" "${payload}" >/dev/null
  fi

  owner="$(jq -r '.owner // "568:568"' <<<"${profile}")"
  [[ "${owner}" =~ ^[0-9]+:[0-9]+$ ]] || fail "${relative}: owner must be uid:gid"
  while IFS= read -r directory; do
    [[ "${directory}" =~ ^[a-z0-9][a-z0-9/_-]*$ && "${directory}" != *..* ]] ||
      fail "${relative}: invalid directory ${directory}"
    if [[ -d "${mount_root}/${directory}" ]] &&
      [[ "$(stat -c '%u:%g' "${mount_root}/${directory}")" == "${owner}" ]]; then
      continue
    fi
    profile_drift=$((profile_drift + 1))
    printf '⚠️  %-32s directory %s missing or not owned by %s\n' "${dataset}" "${directory}" "${owner}"
    if [[ "${MODE}" == "--apply" ]]; then
      install -d -o "${owner%%:*}" -g "${owner##*:}" "${mount_root}/${directory}"
    fi
  done < <(jq -r '.directories // [] | .[]' <<<"${profile}")
}
