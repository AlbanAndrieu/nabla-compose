#!/usr/bin/env bash
# TrueNAS hourly Cron entrypoint for approved bounded active CTEM discovery.
# A single run produces one private candidate JSON and one counts-only report.
set -euo pipefail
umask 077

MODE="${1:---check}"
ROOT=/mnt/cpool/compose/nabla-compose
STORE=/mnt/cpool/ctem/amass
BINARY="${STORE}/bin/amass"
REPORTS="${STORE}/reports"
COMPOSE="${ROOT}/config/security/ctem/amass-job.compose.yml"

if [[ "${MODE}" == --check ]]; then
  echo "CHECK: Amass v5.1.3; Docker namespace, no host port 4000 binding"
  echo "CHECK: TrueNAS dataset /mnt/cpool/ctem/amass, reports private 0700"
  echo "CHECK: active DNS/TLS/web probes on reviewed domain scope, only ports 80/443"
  echo "CHECK: PostgreSQL assetdb uses existing TrueNAS App, verify-full TLS"
  echo "CHECK: no probe, docker, remote API or filesystem mutation"
  exit 0
fi
if [[ "${MODE}" != --run || ${EUID} -ne 0 ]]; then
  echo "REJECTED: usage --check or root --run" >&2
  exit 2
fi
if [[ "${CTEM_AMASS_ACTIVE_APPROVED:-}" != YES ]]; then
  echo "REJECTED: CTEM_AMASS_ACTIVE_APPROVED=YES required for active probes" >&2
  exit 2
fi
SECRET=/mnt/cpool/secrets/runtime/ctem-amass/.env.secrets
if [[ ! -f "${SECRET}" || -L "${SECRET}" || "$(stat -c '%u:%a' "${SECRET}")" != "0:600" ]]; then
  echo "REJECTED: PostgreSQL CTEM env must be root-owned 0600" >&2
  exit 2
fi
if [[ -L "${ROOT}" || ! -f "${COMPOSE}" ||
      -L "${STORE}" || -L "${BINARY}" || ! -f "${BINARY}" ||
      ! -x "${BINARY}" || -L "${REPORTS}" || ! -d "${REPORTS}" ]]; then
  echo "REJECTED: missing or unsafe CTEM installation" >&2
  exit 2
fi
# Only root should see passive-discovery candidate assets. Do not print them.
if [[ "$(stat -c '%u:%a' "${REPORTS}")" != "0:700" ]]; then
  echo "REJECTED: report directory must be owned by root, mode 0700" >&2
  exit 2
fi
exec 9>"${REPORTS}/.ctem-amass.lock"
if ! flock -n 9; then
  echo "REJECTED: CTEM discovery already running" >&2
  exit 75
fi
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
echo "ctem_amass=STARTED; timestamp=${timestamp}; candidates_private=true"
# Never expose the private inventory to GitHub artifacts or a public web route.
rc=0
timeout 14m docker compose \
  --project-directory "${ROOT}/config/security/ctem" \
  --file "${COMPOSE}" \
  --profile manual run --rm --no-deps --pull never ctem-amass \
  --amass /tools/amass \
  --mode active \
  --output "/reports/summary-${timestamp}.json" \
  --private-output "/reports/candidates-${timestamp}.json" || rc=$?

summary="${REPORTS}/summary-${timestamp}.json"
if [[ -f "${summary}" ]]; then
  # Print only counts/status in the existing TrueNAS Cron mail, never candidates.
  python3 - "${summary}" "${REPORTS}/summary-latest.json" <<'PY'
import json
import os
from pathlib import Path
import sys
source, latest = map(Path, sys.argv[1:])
data = json.loads(source.read_text(encoding="utf-8"))
if data.get("schema_version") != 1 or data.get("scanner") != "amass":
    raise SystemExit("REJECTED: invalid Amass summary")
counts = data.get("counts")
if not isinstance(counts, dict) or any(type(x) is not int for x in counts.values()):
    raise SystemExit("REJECTED: invalid Amass counts")
print(f"ctem_amass_status={data.get('status', 'INCOMPLETE')}; "
      f"assets_count={sum(counts.values())}; "
      f"mode={data.get('scan_mode')}")
tmp = latest.with_name(latest.name + f".tmp-{os.getpid()}")
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as out:
    json.dump(data, out, sort_keys=True)
    out.write("\n")
os.replace(tmp, latest)
PY
  # The dedicated role can insert only minimized receipts into assetdb.ctem.
  # A failed receipt must NOT be logged as a successful publication.
  if [[ "${CTEM_REPORT_STORE_APPROVED:-}" == YES ]]; then
    python3 "${ROOT}/scripts/security/store-ctem-summary.py" \
      --kind amass --input "${summary}" --apply || rc=3
  else
    echo "ctem_storage=PRIVATE_FILE_ONLY; shared-postgresql insertion not enabled"
  fi
fi
if ((rc != 0)); then
  echo "ctem_amass=INCOMPLETE; exit=${rc}; no automatic DefectDojo finding" >&2
  exit "${rc}"
fi
echo "ctem_amass=COMPLETE; summary persisted privately; no candidate names logged"
