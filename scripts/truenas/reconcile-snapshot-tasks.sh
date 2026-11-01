#!/usr/bin/env bash
# Reconcile TrueNAS periodic snapshot tasks with config/truenas/snapshot-tasks.json.
# --plan (default) changes nothing. --apply also needs NABLA_SNAPSHOT_APPLY_APPROVED=yes
# and only CREATES missing tasks: no update, no delete, no snapshot destroyed.
# A task matches on dataset + naming_schema; a differing lifetime/schedule is reported as drift.
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
for command in midclt jq; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

existing="$(midclt call pool.snapshottask.query)"
section "Snapshot tasks (${mode#--})"
missing=0
while IFS= read -r task; do
  label="$(jq -r '"\(.dataset) \(.naming_schema)"' <<<"${task}")"
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
    warn "drift: ${label} differs from ${desired#"${root}"/} (not changed, fix by hand)"
  fi
done < <(jq -c '.[]' "${desired}")

section "Summary"
if [[ "${mode}" == "--plan" && "${missing}" -gt 0 ]]; then
  warn "${missing} task(s) to create: NABLA_SNAPSHOT_APPLY_APPROVED=yes sudo bash $0 --apply"
else
  ok "snapshot tasks reconciled (${mode#--})"
fi
