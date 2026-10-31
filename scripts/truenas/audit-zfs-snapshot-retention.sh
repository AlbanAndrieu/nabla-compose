#!/usr/bin/env bash
# Read-only audit of ZFS snapshot retention on TrueNAS: periodic snapshot tasks,
# replication tasks, and per-dataset coverage, age and space held by snapshots.
# No snapshot, task or property is created, changed or destroyed.
set -euo pipefail

MAX_AGE_SECONDS="${NABLA_RETENTION_MAX_AGE_SECONDS:-93600}"
EXCLUDE_REGEX="${NABLA_RETENTION_EXCLUDE_REGEX:-^boot-pool|/ix-apps|/\.system|/\.ix-}"
CRITICAL="${NABLA_RETENTION_CRITICAL:-cpool/backup}"

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

case "${1:---check}" in
  --check) ;;
  *) fail "usage: sudo bash scripts/truenas/audit-zfs-snapshot-retention.sh [--check]" ;;
esac

[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in midclt jq zfs awk numfmt; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done
[[ "${MAX_AGE_SECONDS}" =~ ^[0-9]+$ ]] || fail "NABLA_RETENTION_MAX_AGE_SECONDS must be integer seconds"

now="$(date +%s)"
findings=0

section "Periodic snapshot tasks"
# dataset<TAB>recursive<TAB>enabled<TAB>lifetime<TAB>schedule<TAB>excludes
tasks="$(midclt call pool.snapshottask.query | jq -r '.[] | [
  .dataset, .recursive, .enabled,
  "\(.lifetime_value) \(.lifetime_unit)",
  "\(.schedule.minute) \(.schedule.hour) \(.schedule.dom) \(.schedule.month) \(.schedule.dow)",
  (.exclude | join(","))
] | @tsv')"
if [[ -z "${tasks}" ]]; then
  warn "no periodic snapshot task"
  findings=$((findings + 1))
else
  printf '%s\n' "${tasks}" | awk -F'\t' '{printf "  %-40s recursive=%-5s enabled=%-5s keep=%-10s cron=\"%s\" exclude=%s\n", $1, $2, $3, $4, $5, ($6 == "" ? "-" : $6)}'
fi

section "Replication tasks"
replications="$(midclt call replication.query | jq -r '.[] | [
  .name, .direction, .transport, (.source_datasets | join(",")), .target_dataset,
  .retention_policy, .enabled
] | @tsv')"
if [[ -z "${replications}" ]]; then
  warn "no replication task: no copy of any snapshot outside this TrueNAS"
  findings=$((findings + 1))
else
  printf '%s\n' "${replications}" | awk -F'\t' '{printf "  %s %s/%s %s -> %s retention=%s enabled=%s\n", $1, $2, $3, $4, $5, $6, $7}'
fi

section "Datasets: coverage, newest snapshot age, space held by snapshots"
covered() {
  local dataset="$1" task_dataset recursive enabled
  while IFS=$'\t' read -r task_dataset recursive enabled _; do
    [[ "${enabled}" == "true" ]] || continue
    [[ "${dataset}" == "${task_dataset}" ]] && return 0
    [[ "${recursive}" == "true" && "${dataset}" == "${task_dataset}/"* ]] && return 0
  done <<<"${tasks}"
  return 1
}

# dataset<TAB>count<TAB>newest creation epoch
snapshot_stats="$(zfs list -H -p -t snapshot -o name,creation |
  awk -F'\t' '{split($1, part, "@"); count[part[1]]++; if ($2 > newest[part[1]]) newest[part[1]] = $2}
    END {for (d in count) printf "%s\t%d\t%d\n", d, count[d], newest[d]}')"

while IFS=$'\t' read -r dataset held; do
  [[ "${dataset}" =~ ${EXCLUDE_REGEX} ]] && continue
  stats="$(awk -F'\t' -v d="${dataset}" '$1 == d {print $2 "\t" $3}' <<<"${snapshot_stats}")"
  count="${stats%%$'\t'*}"
  newest="${stats##*$'\t'}"
  [[ -n "${stats}" ]] || { count=0; newest=0; }
  held_human="$(numfmt --to=iec "${held}")"
  if ! covered "${dataset}"; then
    if [[ ",${CRITICAL}," == *",${dataset},"* ]]; then
      warn "${dataset}: CRITICAL dataset without snapshot task (${count} snapshots, ${held_human})"
      findings=$((findings + 1))
    else
      info "${dataset}: no snapshot task (${count} snapshots, ${held_human})"
    fi
    continue
  fi
  if [[ "${count}" -eq 0 ]]; then
    warn "${dataset}: covered by a task but has no snapshot"
    findings=$((findings + 1))
  elif ((now - newest > MAX_AGE_SECONDS)); then
    warn "${dataset}: newest snapshot is $(((now - newest) / 3600)) h old (> $((MAX_AGE_SECONDS / 3600)) h)"
    findings=$((findings + 1))
  else
    ok "${dataset}: ${count} snapshots, newest $(((now - newest) / 3600)) h old, ${held_human} held"
  fi
done < <(zfs list -H -p -t filesystem,volume -o name,usedbysnapshots)

section "Summary"
if ((findings == 0)); then
  ok "retention audit: no finding (read-only)"
else
  warn "retention audit: ${findings} finding(s) (read-only, nothing changed)"
fi
