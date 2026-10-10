#!/usr/bin/env bash
# Read-only DSOMM state and repository-assessment import preflight.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_ROOT="${DSOMM_STATE_ROOT:-/mnt/cpool/dsomm/state}"
SITE_SOURCE="${DSOMM_SITE_ALBAN_ASSESSMENT:-https://raw.githubusercontent.com/AlbanAndrieu/nabla-site-alban/master/nabla-dsomm-assessment.json}"

printf '==> DSOMM reviewed source and persisted UI state\n'
python3 "${ROOT}/scripts/dsomm/validate-seed.py"
for name in model.yaml team-progress.yaml team-evidence.yaml; do
  target="${STATE_ROOT}/${name}"
  if [[ -f "${target}" && ! -L "${target}" ]]; then
    stat -c 'runtime_file=%n bytes=%s mode=%a owner=%U:%G' -- "${target}"
  else
    printf 'WARNING: missing or unsafe runtime_file=%s\n' "${target}"
  fi
done

printf '\n==> Runtime progress and evidence counts (no evidence content)\n'
python3 - "${STATE_ROOT}" <<'PY'
from pathlib import Path
import sys
import yaml

root = Path(sys.argv[1])
for filename, key in (("team-progress.yaml", "progress"), ("team-evidence.yaml", "evidence")):
    path = root / filename
    if not path.is_file() or path.is_symlink():
        print(f"{filename}: unavailable")
        continue
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        print(f"{filename}: invalid/unreadable")
        continue
    record = data.get(key) if isinstance(data, dict) else None
    print(f"{filename}: activities={len(record) if isinstance(record, dict) else 'invalid'}")
PY

printf '\n==> Public UI/asset reachability (no mutation)\n'
if command -v curl >/dev/null 2>&1; then
  curl -sS -o /dev/null --connect-timeout 3 --max-time 8 -w 'dsomm_root_http=%{http_code}\n' 'http://172.17.0.24:31088/' || true
fi

printf '\n==> Site Alban repository assessment producer\n'
python3 "${ROOT}/scripts/dsomm/aggregate-repository-assessments.py" \
  --source "AlbanAndrieu/nabla-site-alban=${SITE_SOURCE}" --check
printf 'INFO: --check is read-only. Repository JSON is not automatically imported into browser/localStorage or team-progress.yaml.\n'
