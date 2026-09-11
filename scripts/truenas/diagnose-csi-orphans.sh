#!/usr/bin/env bash
set -euo pipefail

# Keep interactive diagnostics compact while preserving full CI/non-TTY output.
if [[ "${NABLA_DIAGNOSTIC_WRAPPED:-0}" != "1" && "${DIAGNOSTIC_FULL_OUTPUT:-0}" != "1" && ( -t 1 || "${DIAGNOSTIC_COMPACT_OUTPUT:-0}" == "1" ) ]]; then
  NABLA_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  NABLA_DIAGNOSTIC_WRAPPER="$(dirname -- "${NABLA_SCRIPT_DIR}")/run-diagnostic.sh"
  exec "${NABLA_DIAGNOSTIC_WRAPPER}" \
    "${NABLA_SCRIPT_DIR}/$(basename -- "${BASH_SOURCE[0]}")" "$@"
fi

fail() {
  printf '❌ %s\n' "$*" >&2
  exit 1
}

warn() {
  printf 'WARN: %s\n' "$*"
}

ok() {
  printf 'OK: %s\n' "$*"
}

mode="${1:---check}"
[[ "${mode}" == "--check" ]] || fail "usage: $(basename "$0") [--check]"

for command in jq midclt timeout zfs; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

CSI_PARENT="${TRUENAS_CSI_DATASET:-cpool/k8s/csi}"
CSI_DRIVER="${TRUENAS_CSI_DRIVER:-csi.truenas.io}"
KUBECTL_BIN="${NABLA_KUBECTL:-kubectl}"
KUBECTL_TIMEOUT_SECONDS="${CSI_ORPHAN_KUBECTL_TIMEOUT_SECONDS:-8}"
MAX_DATASETS="${CSI_ORPHAN_MAX_DATASETS:-100}"

[[ "${MAX_DATASETS}" =~ ^[1-9][0-9]*$ ]] || fail "CSI_ORPHAN_MAX_DATASETS must be a positive integer"
[[ "${KUBECTL_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]] || fail "CSI_ORPHAN_KUBECTL_TIMEOUT_SECONDS must be a positive integer"

if ! sudo zfs list -H -o name "${CSI_PARENT}" >/dev/null 2>&1; then
  fail "TrueNAS CSI parent dataset is unavailable: ${CSI_PARENT}"
fi

nfs_json="$(mktemp)"
pv_json="$(mktemp)"
va_json="$(mktemp)"
trap 'rm -f "${nfs_json}" "${pv_json}" "${va_json}"' EXIT

sudo midclt call sharing.nfs.query >"${nfs_json}"

kubernetes_state="unavailable"
if command -v "${KUBECTL_BIN}" >/dev/null 2>&1; then
  if timeout "${KUBECTL_TIMEOUT_SECONDS}" "${KUBECTL_BIN}" get pv -o json >"${pv_json}" 2>/dev/null && \
     timeout "${KUBECTL_TIMEOUT_SECONDS}" "${KUBECTL_BIN}" get volumeattachment -o json >"${va_json}" 2>/dev/null; then
    kubernetes_state="available"
  else
    warn "Kubernetes inventory unavailable; CSI datasets can only be classified as candidates, not definitive orphans"
  fi
else
  warn "${KUBECTL_BIN} is unavailable; CSI datasets can only be classified as candidates, not definitive orphans"
fi

mapfile -t datasets < <(
  sudo zfs list -H -t filesystem -o name -r "${CSI_PARENT}" 2>/dev/null |
    awk -v prefix="${CSI_PARENT}/pvc-" 'index($0, prefix) == 1' |
    head -n "${MAX_DATASETS}"
)

printf '🔎 TrueNAS CSI dynamic dataset inventory\n'
printf '   parent=%s driver=%s kubernetes=%s\n' "${CSI_PARENT}" "${CSI_DRIVER}" "${kubernetes_state}"
printf '   NOTE: the TrueNAS UI is not authoritative for CSI pvc-* datasets; use zfs/middleware inventory.\n'

if ((${#datasets[@]} == 0)); then
  ok "no dynamic CSI pvc-* datasets exist below ${CSI_PARENT}"
  exit 0
fi

orphan_count=0
candidate_count=0
referenced_count=0

printf '%-42s %-9s %-7s %-7s %-5s %-5s %-5s %-9s\n' \
  "DATASET" "MOUNTED" "PV" "ATTACH" "NFS" "SNAP" "USED" "STATE"

for dataset in "${datasets[@]}"; do
  leaf="${dataset##*/}"
  mountpoint="$(sudo zfs get -H -o value mountpoint "${dataset}")"
  mounted="$(sudo zfs get -H -o value mounted "${dataset}")"
  used="$(sudo zfs get -H -o value used "${dataset}")"
  snapshot_count="$(sudo zfs list -H -t snapshot -o name -r "${dataset}" 2>/dev/null | wc -l | tr -d ' ')"
  nfs_count="$(
    jq --arg path "${mountpoint}" \
      '[.[] | select((.path? == $path) or (((.paths? // []) | index($path)) != null))] | length' \
      "${nfs_json}"
  )"

  pv_count="?"
  attachment_count="?"
  state="CANDIDATE"

  if [[ "${kubernetes_state}" == "available" ]]; then
    pv_count="$(
      jq --arg dataset "${dataset}" --arg driver "${CSI_DRIVER}" \
        '[.items[] | select(.spec.csi.driver == $driver and .spec.csi.volumeHandle == $dataset)] | length' \
        "${pv_json}"
    )"
    attachment_count="$(
      jq --arg pv "${leaf}" \
        '[.items[] | select(.spec.source.persistentVolumeName == $pv)] | length' \
        "${va_json}"
    )"

    if ((pv_count == 0 && attachment_count == 0)); then
      state="ORPHAN"
      orphan_count=$((orphan_count + 1))
    else
      state="REFERENCED"
      referenced_count=$((referenced_count + 1))
    fi
  else
    candidate_count=$((candidate_count + 1))
  fi

  printf '%-42s %-9s %-7s %-7s %-5s %-5s %-5s %-9s\n' \
    "${leaf}" "${mounted}" "${pv_count}" "${attachment_count}" "${nfs_count}" \
    "${snapshot_count}" "${used}" "${state}"

  if [[ "${state}" == "ORPHAN" ]]; then
    warn "CSI orphan: ${dataset} has no Kubernetes PV or VolumeAttachment reference; nfs_shares=${nfs_count} snapshots=${snapshot_count} mounted=${mounted} mountpoint=${mountpoint}"

    if [[ "${mounted}" == "no" && -d "${mountpoint}" ]]; then
      warn "orphan mountpoint remains as a directory while the ZFS dataset is unmounted: ${mountpoint}"
    fi

    if command -v findmnt >/dev/null 2>&1; then
      findmnt_result="$(sudo findmnt -rn -M "${mountpoint}" -o TARGET,SOURCE,FSTYPE 2>/dev/null || true)"
      [[ -z "${findmnt_result}" ]] || printf '   host-mount: %s\n' "${findmnt_result}"
    fi

    if command -v fuser >/dev/null 2>&1; then
      printf '   fuser evidence for %s:\n' "${mountpoint}"
      sudo fuser -vm "${mountpoint}" 2>&1 || true
    fi

    if command -v lsns >/dev/null 2>&1 && command -v nsenter >/dev/null 2>&1 && command -v findmnt >/dev/null 2>&1; then
      namespace_hits=0
      while read -r pid; do
        [[ "${pid}" =~ ^[0-9]+$ ]] || continue
        namespace_mount="$(
          sudo nsenter -t "${pid}" -m findmnt -rn -M "${mountpoint}" -o TARGET,SOURCE,FSTYPE 2>/dev/null || true
        )"
        if [[ -n "${namespace_mount}" ]]; then
          printf '   mount-namespace pid=%s: %s\n' "${pid}" "${namespace_mount}"
          namespace_hits=$((namespace_hits + 1))
        fi
      done < <(sudo lsns -t mnt -n -o PID 2>/dev/null | awk '!seen[$1]++' | head -n 200)
      ((namespace_hits == 0)) && printf '   mount-namespace: no secondary reference detected\n'
    fi
  fi
done

printf '\nCSI dataset summary: referenced=%d orphan=%d candidate=%d total=%d\n' \
  "${referenced_count}" "${orphan_count}" "${candidate_count}" "${#datasets[@]}"

if ((orphan_count > 0)); then
  warn "${orphan_count} definitive CSI orphan dataset(s) detected; do not trust a successful pool.dataset.delete response without verifying dataset absence"
elif ((candidate_count > 0)); then
  warn "${candidate_count} CSI dataset candidate(s) require Kubernetes correlation before cleanup"
else
  ok "all dynamic CSI datasets have live Kubernetes references"
fi
