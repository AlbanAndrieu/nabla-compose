#!/usr/bin/env bash
# Reconcile TrueNAS periodic snapshot tasks with config/truenas/snapshot-tasks.json.
# The policy declares retention classes (datasets x schedules) and datasets that
# must never be snapshotted. --plan (default) changes nothing. --apply also needs
# NABLA_SNAPSHOT_APPLY_APPROVED=yes and only CREATES missing tasks for datasets
# that exist: no update, no delete, no snapshot destroyed.
# A task matches on dataset + naming_schema; a differing lifetime/schedule is
# reported as drift. An existing task covering a noSnapshot dataset is reported
# for a manual fix (exclude it or delete the task after review).
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
desired="${NABLA_SNAPSHOT_TASKS:-${root}/config/truenas/snapshot-tasks.json}"
# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

mode="${1:---plan}"
case "${mode}" in
  --plan | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/reconcile-snapshot-tasks.sh [--plan|--apply]" ;;
esac
if [[ "${mode}" == "--apply" && "${NABLA_SNAPSHOT_APPLY_APPROVED:-}" != "yes" ]]; then
  fail "--apply also requires NABLA_SNAPSHOT_APPLY_APPROVED=yes"
fi
[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in midclt jq zfs; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

# Expand classes into middleware payloads: one task per dataset and schedule.
tasks="$(jq -c '
  .schedules as $s
  | [.classes[] as $c | $c.datasets[] as $d | $c.schedules[] as $k
     | {dataset: $d, recursive: true} + $s[$k]]
  | .[]' "${desired}")"
no_snapshot="$(jq -c '[.noSnapshot[].dataset]' "${desired}")"
existing="$(midclt call pool.snapshottask.query)"
datasets="$(zfs list -H -o name -t filesystem,volume | jq -R -s -c 'split("\n") | map(select(length > 0))')"

section "Snapshot tasks (${mode#--})"
missing=0
absent=0
drift=0
while IFS= read -r task; do
  dataset="$(jq -r '.dataset' <<<"${task}")"
  label="$(jq -r '"\(.dataset) \(.naming_schema) keep=\(.lifetime_value)\(.lifetime_unit)"' <<<"${task}")"
  if ! jq -e --arg d "${dataset}" 'any(.[]; . == $d)' <<<"${datasets}" >/dev/null; then
    absent=$((absent + 1))
    warn "absent: ${label} (dataset not found; skipped, fix the policy or create the dataset)"
    continue
  fi
  match="$(jq -c --argjson t "${task}" \
    'map(select(.dataset == $t.dataset and .naming_schema == $t.naming_schema)) | first // empty' <<<"${existing}")"
  if [[ -z "${match}" ]]; then
    missing=$((missing + 1))
    if [[ "${mode}" == "--apply" ]]; then
      midclt call pool.snapshottask.create "${task}" >/dev/null
      ok "created: ${label}"
    else
      warn "missing: ${label} (would be created by --apply)"
    fi
  elif jq -e --argjson t "${task}" \
    '.lifetime_value == $t.lifetime_value and .lifetime_unit == $t.lifetime_unit and .recursive == $t.recursive
      and ([.schedule.minute, .schedule.hour, .schedule.dom, .schedule.month, .schedule.dow]
        == [$t.schedule.minute, $t.schedule.hour, $t.schedule.dom, $t.schedule.month, $t.schedule.dow])' \
    <<<"${match}" >/dev/null; then
    ok "present: ${label}"
  else
    drift=$((drift + 1))
    warn "drift: ${label} differs from ${desired#"${root}"/} (not changed, fix by hand)"
  fi
done <<<"${tasks}"

section "Datasets that must not be snapshotted"
covered=0
while IFS=$'\t' read -r task_id task_dataset excluded_dataset; do
  [[ -n "${task_id}" ]] || continue
  covered=$((covered + 1))
  warn "task ${task_id} on ${task_dataset} covers ${excluded_dataset} (add it to the task exclude list or delete the task after review)"
done < <(jq -r --argjson n "${no_snapshot}" --argjson ds "${datasets}" '
  .[] as $t
  | $n[] as $x
  | select(any($ds[]; . == $x))
  | select($x == $t.dataset
      or ($t.recursive and ($x | startswith($t.dataset + "/"))
          and (any(($t.exclude // [])[]; . == $x) | not)))
  | [$t.id, $t.dataset, $x] | @tsv' <<<"${existing}")
((covered > 0)) || ok "no existing task covers a noSnapshot dataset"

section "Summary"
printf 'missing=%d absent=%d drift=%d covering-no-snapshot=%d\n' "${missing}" "${absent}" "${drift}" "${covered}"
if [[ "${mode}" == "--plan" && "${missing}" -gt 0 ]]; then
  warn "${missing} task(s) to create: NABLA_SNAPSHOT_APPLY_APPROVED=yes sudo bash $0 --apply"
elif ((absent + drift + covered > 0)); then
  warn "policy reconciled with findings to review (${mode#--})"
else
  ok "snapshot tasks reconciled (${mode#--})"
fi
