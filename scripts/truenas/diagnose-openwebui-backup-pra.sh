#!/usr/bin/env bash
set -euo pipefail

STRICT=false
case "${1:-}" in
  --check)
    STRICT=true
    ;;
  "")
    ;;
  -h|--help)
    cat <<'EOF'
Usage:
  sudo bash scripts/truenas/diagnose-openwebui-backup-pra.sh [--check]

Read-only OpenWebUI/OpenRAG backup and PRA preflight.

Checks:
- OpenWebUI persistent data path and owning ZFS dataset
- newest local ZFS snapshot age (12h target, 24h RPO hard limit)
- enabled PUSH replication/cloud-sync coverage
- recent successful replication/cloud-sync job evidence
- encryption signal for cloud-sync backup
- OpenRAG persistent paths required by the continuity objective
- OpenWebUI Pipelines named-volume persistence debt

--check turns missing/stale RPO evidence into a non-zero exit status.

Environment overrides:
  OPENWEBUI_DATA_DIR
  OPENRAG_ROOT
  SNAPSHOT_TARGET_SECONDS
  RPO_SECONDS
EOF
    exit 0
    ;;
  *)
    printf 'usage: %s [--check]\n' "$0" >&2
    exit 2
    ;;
esac

OPENWEBUI_DATA_DIR="${OPENWEBUI_DATA_DIR:-/mnt/cpool/openwebui/data}"
OPENRAG_ROOT="${OPENRAG_ROOT:-/mnt/cpool/compose/nabla-compose/apps/openrag}"
SNAPSHOT_TARGET_SECONDS="${SNAPSHOT_TARGET_SECONDS:-43200}"
RPO_SECONDS="${RPO_SECONDS:-86400}"

failures=0

fail_or_warn() {
  if [[ "${STRICT}" == true ]]; then
    printf '❌ %s\n' "$*" >&2
    failures=$((failures + 1))
  else
    printf '⚠️  %s\n' "$*" >&2
  fi
}

warn() {
  printf '⚠️  %s\n' "$*" >&2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || {
    printf 'ERROR: %s is required\n' "$1" >&2
    exit 1
  }
}

for command in zfs findmnt stat du date python3 midclt jq; do
  require_command "${command}"
done

if ! [[ "${SNAPSHOT_TARGET_SECONDS}" =~ ^[0-9]+$ ]] ||
  ! [[ "${RPO_SECONDS}" =~ ^[0-9]+$ ]]; then
  printf 'ERROR: snapshot/RPO thresholds must be integer seconds\n' >&2
  exit 2
fi

dataset_for_path() {
  local target="$1"
  zfs list -H -o name,mountpoint 2>/dev/null |
    awk -v target="${target}" '
      $2 != "-" && (target == $2 || index(target, $2 "/") == 1) {
        print length($2) "\t" $1 "\t" $2
      }
    ' |
    sort -rn |
    head -n 1 |
    cut -f2
}

latest_snapshot() {
  local dataset="$1"
  zfs list -H -t snapshot -o name -s creation -r "${dataset}" 2>/dev/null |
    tail -n 1
}

snapshot_epoch() {
  local snapshot="$1"
  zfs get -H -p -o value creation "${snapshot}" 2>/dev/null
}

age_seconds() {
  local epoch="$1"
  printf '%s\n' "$(( $(date +%s) - epoch ))"
}

format_age() {
  local seconds="$1"
  python3 - "${seconds}" <<'PY'
import sys

seconds = max(0, int(sys.argv[1]))
days, rem = divmod(seconds, 86400)
hours, rem = divmod(rem, 3600)
minutes, _ = divmod(rem, 60)
print(f"{days}d {hours}h {minutes}m")
PY
}

printf '=== OpenWebUI backup/PRA preflight (read-only) ===\n'
printf 'OpenWebUI data=%s\n' "${OPENWEBUI_DATA_DIR}"
printf 'OpenRAG root=%s\n' "${OPENRAG_ROOT}"
printf 'snapshot target=%ss RPO hard limit=%ss\n'   "${SNAPSHOT_TARGET_SECONDS}" "${RPO_SECONDS}"

printf '\n==> OpenWebUI persistent state\n'
if [[ ! -d "${OPENWEBUI_DATA_DIR}" ]]; then
  fail_or_warn "OpenWebUI data directory is missing: ${OPENWEBUI_DATA_DIR}"
  openwebui_dataset=""
else
  stat -c 'owner=%U group=%G mode=%a' "${OPENWEBUI_DATA_DIR}"
  du -sh "${OPENWEBUI_DATA_DIR}" 2>/dev/null || true
  printf 'mount source=%s\n'     "$(findmnt -n -o SOURCE -T "${OPENWEBUI_DATA_DIR}" 2>/dev/null || printf '<unknown>')"

  openwebui_dataset="$(dataset_for_path "${OPENWEBUI_DATA_DIR}")"
  if [[ -z "${openwebui_dataset}" ]]; then
    fail_or_warn "No ZFS dataset owns ${OPENWEBUI_DATA_DIR}"
  else
    printf 'dataset=%s\n' "${openwebui_dataset}"
  fi
fi

printf '\n==> Local recovery point\n'
latest_snapshot_name=""
latest_snapshot_age=""
if [[ -n "${openwebui_dataset:-}" ]]; then
  latest_snapshot_name="$(latest_snapshot "${openwebui_dataset}")"
fi

if [[ -z "${latest_snapshot_name}" ]]; then
  fail_or_warn "No ZFS snapshot found for OpenWebUI dataset"
else
  latest_snapshot_epoch="$(snapshot_epoch "${latest_snapshot_name}")"
  if ! [[ "${latest_snapshot_epoch}" =~ ^[0-9]+$ ]]; then
    fail_or_warn "Could not determine creation time for ${latest_snapshot_name}"
  else
    latest_snapshot_age="$(age_seconds "${latest_snapshot_epoch}")"
    printf 'latest snapshot=%s age=%s\n'       "${latest_snapshot_name}" "$(format_age "${latest_snapshot_age}")"

    if ((latest_snapshot_age > RPO_SECONDS)); then
      fail_or_warn "Latest local snapshot is older than the 24h RPO limit"
    elif ((latest_snapshot_age > SNAPSHOT_TARGET_SECONDS)); then
      warn "Latest local snapshot is within RPO but older than the 12h safety target"
    else
      printf '✅ local snapshot age is within the 12h target\n'
    fi
  fi
fi

printf '\n==> OpenRAG continuity state\n'
openrag_required_paths=(
  "${OPENRAG_ROOT}/openrag-documents"
  "${OPENRAG_ROOT}/config"
  "${OPENRAG_ROOT}/data"
  "${OPENRAG_ROOT}/flows/backup"
)

for path in "${openrag_required_paths[@]}"; do
  if [[ -e "${path}" ]]; then
    dataset="$(dataset_for_path "${path}")"
    printf '✅ %s dataset=%s\n' "${path}" "${dataset:-<unresolved>}"
  else
    fail_or_warn "Required OpenRAG recovery path is missing: ${path}"
  fi
done

if [[ -e "${OPENRAG_ROOT}/keys" ]]; then
  printf '✅ sensitive OpenRAG keys path exists (contents not displayed)\n'
else
  fail_or_warn "Sensitive OpenRAG keys path is missing: ${OPENRAG_ROOT}/keys"
fi

printf '\n==> Independent backup configuration\n'
replication_json="$(midclt call replication.query 2>/dev/null || printf '[]')"
cloudsync_json="$(midclt call cloudsync.query 2>/dev/null || printf '[]')"
jobs_json="$(midclt call core.get_jobs 2>/dev/null || printf '[]')"

backup_result="$(
  jq -n     --argjson replication "${replication_json}"     --argjson cloudsync "${cloudsync_json}"     --argjson jobs "${jobs_json}"     '{replication:$replication,cloudsync:$cloudsync,jobs:$jobs}' |
    python3 - "${openwebui_dataset:-}" "${OPENWEBUI_DATA_DIR}" "${RPO_SECONDS}" <<'PY'
import datetime as dt
import json
import sys
from typing import Any

dataset = sys.argv[1]
data_path = sys.argv[2]
rpo_seconds = int(sys.argv[3])
payload = json.load(sys.stdin)
replication = payload.get("replication") or []
cloudsync = payload.get("cloudsync") or []
jobs = payload.get("jobs") or []


def source_covers(source: str, wanted: str) -> bool:
    return bool(source) and (wanted == source or wanted.startswith(source + "/"))


def path_covers(source: str, wanted: str) -> bool:
    source = source.rstrip("/")
    wanted = wanted.rstrip("/")
    return bool(source) and (wanted == source or wanted.startswith(source + "/"))


def job_finished_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict) and "$date" in value:
        raw = value["$date"]
        if isinstance(raw, (int, float)):
            return float(raw) / 1000.0
        value = raw
    if isinstance(value, (int, float)):
        value = float(value)
        return value / 1000.0 if value > 10_000_000_000 else value
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def job_mentions(job: dict[str, Any], task_id: int) -> bool:
    arguments = job.get("arguments") or []
    return any(str(item) == str(task_id) for item in arguments)


now = dt.datetime.now(dt.timezone.utc).timestamp()

replication_candidates: list[dict[str, Any]] = []
if dataset:
    source_pool = dataset.split("/", 1)[0]
    for task in replication:
        if not isinstance(task, dict):
            continue
        if task.get("enabled") is False or task.get("direction") != "PUSH":
            continue
        sources = task.get("source_datasets") or []
        if not any(source_covers(str(source), dataset) for source in sources):
            continue
        transport = str(task.get("transport") or "")
        target = str(task.get("target_dataset") or "")
        target_pool = target.split("/", 1)[0] if target else ""
        independent = transport not in {"", "LOCAL"} or (
            bool(target_pool) and target_pool != source_pool
        )
        task = dict(task)
        task["_independent"] = independent
        replication_candidates.append(task)

cloud_candidates: list[dict[str, Any]] = []
for task in cloudsync:
    if not isinstance(task, dict):
        continue
    if task.get("enabled") is False or task.get("direction") != "PUSH":
        continue
    source = str(task.get("path") or "")
    task_dataset = str(task.get("dataset") or "")
    if not (
        path_covers(source, data_path)
        or (dataset and source_covers(task_dataset, dataset))
    ):
        continue
    cloud_candidates.append(task)

candidate_ids: list[tuple[str, int, bool]] = []
for task in replication_candidates:
    task_id = task.get("id")
    if isinstance(task_id, int):
        candidate_ids.append(("replication", task_id, bool(task["_independent"])))
for task in cloud_candidates:
    task_id = task.get("id")
    if isinstance(task_id, int):
        candidate_ids.append(("cloudsync", task_id, True))

fresh_success = False
for kind, task_id, independent in candidate_ids:
    relevant = [
        job
        for job in jobs
        if isinstance(job, dict)
        and job.get("state") == "SUCCESS"
        and kind in str(job.get("method") or "").lower()
        and job_mentions(job, task_id)
    ]
    finished = [
        epoch
        for epoch in (job_finished_epoch(job.get("time_finished")) for job in relevant)
        if epoch is not None
    ]
    age = None if not finished else max(0, int(now - max(finished)))
    print(
        f"task kind={kind} id={task_id} independent={str(independent).lower()} "
        f"last_success_age_seconds={age if age is not None else 'unknown'}"
    )
    if independent and age is not None and age <= rpo_seconds:
        fresh_success = True

for task in cloud_candidates:
    if not bool(task.get("encryption")):
        print(
            f"warning cloudsync id={task.get('id')} covers sensitive OpenWebUI "
            "data but client-side encryption is not enabled"
        )

independent_configured = any(
    independent for _, _, independent in candidate_ids
)

print(
    "SUMMARY "
    f"independent_configured={str(independent_configured).lower()} "
    f"fresh_success={str(fresh_success).lower()} "
    f"replication_candidates={len(replication_candidates)} "
    f"cloud_candidates={len(cloud_candidates)}"
)
PY
)"

printf '%s\n' "${backup_result}"
summary_line="$(grep '^SUMMARY ' <<<"${backup_result}" | tail -n 1 || true)"

if [[ -z "${summary_line}" ]]; then
  fail_or_warn "Could not evaluate independent backup configuration"
else
  if ! grep -q 'independent_configured=true' <<<"${summary_line}"; then
    fail_or_warn "No independent PUSH replication/cloud-sync task covers OpenWebUI data"
  fi
  if ! grep -q 'fresh_success=true' <<<"${summary_line}"; then
    fail_or_warn "No successful independent backup within the 24h RPO is evidenced"
  fi
fi

if grep -q '^warning cloudsync ' <<<"${backup_result}"; then
  fail_or_warn "Sensitive OpenWebUI cloud backup is present without client-side encryption"
fi

printf '\n==> Pipelines persistence\n'
if command -v docker >/dev/null 2>&1; then
  mapfile -t pipeline_volumes < <(
    docker volume ls       --filter 'label=com.docker.compose.project=openwebui'       --format '{{.Name}}' 2>/dev/null |
      grep -E '(^|_)pipelines$' || true
  )
  if (("${#pipeline_volumes[@]}" == 0)); then
    warn "OpenWebUI Pipelines named volume was not discovered; verify after deployment"
  else
    for volume in "${pipeline_volumes[@]}"; do
      mountpoint="$(
        docker volume inspect "${volume}"           --format '{{.Mountpoint}}' 2>/dev/null || true
      )"
      printf 'pipeline volume=%s mountpoint=%s\n'         "${volume}" "${mountpoint:-<unknown>}"
      if [[ "${mountpoint}" != /mnt/* ]]; then
        warn "Pipelines volume is not on an explicit /mnt dataset; keep migration/backup debt open"
      fi
    done
  fi
else
  warn "docker unavailable; Pipelines named-volume persistence was not checked"
fi

printf '\n==> PRA acceptance reminder\n'
cat <<'EOF'
Minimum continuity objective:
  OpenWebUI UI on LAN
  + LiteLLM
  + OpenRAG
  + one OpenAI-compatible GPU inference provider

Cloudflare Tunnel is not a PRA blocker.

Targets:
  RTO: 1 day
  Recovery escalation: 3 days
  DMTP/MTPD: 7 days
  RPO objective: 1 day

A local snapshot on the same pool is a recovery point, not an independent
backup against TrueNAS/pool loss.
EOF

if ((failures > 0)); then
  printf 'FAILED: %d OpenWebUI backup/PRA preflight problem(s)\n'     "${failures}" >&2
  exit 1
fi

printf 'OK: OpenWebUI backup/PRA preflight completed read-only\n'
