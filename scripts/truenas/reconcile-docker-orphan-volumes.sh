#!/usr/bin/env bash
# Plan, then remove reviewed orphan (dangling) Docker volumes on TrueNAS, one by one.
#
#   sudo bash scripts/truenas/reconcile-docker-orphan-volumes.sh --plan
#   sudo NABLA_VOLUME_PURGE_APPROVED=yes \
#     bash scripts/truenas/reconcile-docker-orphan-volumes.sh --apply PLAN.tsv
#
# --plan (default) is read-only: it classifies every dangling volume and writes a
# root-only TSV plan (action, name, bytes, age_days, project, volume). Only rows
# whose action starts with "candidate:" are ever removed:
#   candidate:anonymous     unlabeled 64-hex volume, small and older than the minimum age
#   candidate:removed-app   compose project ix-<app> whose TrueNAS App is no longer installed
#   keep:installed-app      project of an installed App (a STOPPED App has no containers)
#   review:*                large, recent, unsized or named volumes: decide by hand
# --apply re-checks that each candidate is still dangling, then runs
# `docker volume rm` without --force. Never `docker volume prune`.
set -euo pipefail

# shellcheck source=../lib/common.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/../lib/common.sh"

MODE="${1:---plan}"
PLAN="${2:-${NABLA_VOLUME_PLAN:-/var/tmp/nabla-docker-orphan-volumes.tsv}}"
APP_CONFIGS="${NABLA_APP_CONFIGS_DIR:-/mnt/.ix-apps/app_configs}"
MAX_BYTES="${NABLA_VOLUME_CANDIDATE_MAX_BYTES:-104857600}"
MIN_AGE_DAYS="${NABLA_VOLUME_CANDIDATE_MIN_AGE_DAYS:-7}"
DU_TIMEOUT="${NABLA_VOLUME_DU_TIMEOUT_SECONDS:-10}"

case "${MODE}" in
  --plan | --apply) ;;
  *) fail "usage: sudo bash scripts/truenas/reconcile-docker-orphan-volumes.sh [--plan [PLAN]|--apply PLAN]" ;;
esac
[[ "${EUID}" -eq 0 ]] || fail "run as root on TrueNAS"
for command in docker du stat timeout; do
  command -v "${command}" >/dev/null 2>&1 || fail "${command} is required"
done

dangling_names() {
  timeout 300 docker volume ls -q --filter dangling=true
}

if [[ "${MODE}" == "--apply" ]]; then
  [[ "${NABLA_VOLUME_PURGE_APPROVED:-}" == "yes" ]] || fail "--apply also requires NABLA_VOLUME_PURGE_APPROVED=yes"
  [[ -f "${PLAN}" ]] || fail "plan not found: ${PLAN} (run --plan and review it first)"
  still_dangling="$(dangling_names)"
  section "Remove reviewed orphan volumes"
  removed=0
  skipped=0
  failed=0
  while IFS=$'\t' read -r action name _; do
    [[ "${action}" == candidate:* ]] || continue
    if ! grep -qxF -- "${name}" <<<"${still_dangling}"; then
      skipped=$((skipped + 1))
      warn "skipped ${name}: no longer dangling"
      continue
    fi
    if docker volume rm -- "${name}" >/dev/null; then
      removed=$((removed + 1))
    else
      failed=$((failed + 1))
      warn "failed: ${name}"
    fi
  done <"${PLAN}"
  printf 'removed=%s skipped=%s failed=%s\n' "${removed}" "${skipped}" "${failed}"
  ((failed == 0)) || fail "some volumes were not removed"
  ok "orphan volumes removed; rerun --plan to compare"
  exit 0
fi

section "Orphan Docker volumes (plan, read-only)"
now="$(date +%s)"
umask 077
tmp_plan="$(mktemp "${PLAN}.XXXXXX")"
trap 'rm -f "${tmp_plan}"' EXIT

timeout 300 docker volume ls --filter dangling=true \
  --format '{{.Name}}\t{{.Mountpoint}}\t{{.Label "com.docker.compose.project"}}\t{{.Label "com.docker.compose.volume"}}' |
  while IFS=$'\t' read -r name mountpoint project volume; do
    [[ -n "${name}" ]] || continue
    bytes="$(timeout "${DU_TIMEOUT}" du -sxb -- "${mountpoint}" 2>/dev/null | cut -f1 || true)"
    created="$(stat -c %Y -- "${mountpoint%/_data}" 2>/dev/null || printf '%s' "${now}")"
    age_days=$(((now - created) / 86400))
    if [[ -n "${project}" ]]; then
      app="${project#ix-}"
      if [[ "${project}" == ix-* && -d "${APP_CONFIGS}/${app}" ]]; then
        action="keep:installed-app"
      elif [[ "${project}" == ix-* ]]; then
        action="candidate:removed-app"
      else
        action="review:foreign-project"
      fi
    elif [[ ! "${name}" =~ ^[0-9a-f]{64}$ ]]; then
      action="review:named"
    elif [[ ! "${bytes}" =~ ^[0-9]+$ ]]; then
      action="review:unsized"
    elif ((bytes > MAX_BYTES)); then
      action="review:large"
    elif ((age_days < MIN_AGE_DAYS)); then
      action="review:recent"
    else
      action="candidate:anonymous"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\n' "${action}" "${name}" "${bytes:-unknown}" "${age_days}" "${project:--}" "${volume:--}"
  done | sort >"${tmp_plan}"

mv -f "${tmp_plan}" "${PLAN}"
trap - EXIT
chmod 0600 "${PLAN}"

printf 'plan: %s\n' "${PLAN}"
printf 'by action (count bytes):\n'
awk -F '\t' '{ n[$1]++; if ($3 ~ /^[0-9]+$/) b[$1] += $3 }
  END { for (a in n) printf "  %-24s %5d %s\n", a, n[a], b[a] + 0 }' "${PLAN}" | sort
printf 'largest volumes (action bytes name project):\n'
awk -F '\t' '$3 ~ /^[0-9]+$/ { print $1, $3, $2, $5 }' "${PLAN}" | sort -k2,2nr | head -15 | sed 's/^/  /'
info "nothing removed; review the plan, delete rows to keep, then run --apply with NABLA_VOLUME_PURGE_APPROVED=yes"
