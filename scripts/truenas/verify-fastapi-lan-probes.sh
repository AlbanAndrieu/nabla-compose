#!/usr/bin/env bash
# Verify, without changing runtime settings, that TrueNAS runs LAN probes.
set -euo pipefail
case "${1:---check}" in
  --check) ;;
  -h|--help)
    printf 'Usage: bash scripts/truenas/verify-fastapi-lan-probes.sh --check\n'
    exit 0
    ;;
  *) printf 'ERROR: only --check is supported\n' >&2; exit 2 ;;
esac
(($# <= 1)) || { printf 'ERROR: extra arguments\n' >&2; exit 2; }
CONTAINER="${FASTAPI_SAMPLE_CONTAINER:-fastapi-sample}"
[[ "$CONTAINER" =~ ^[a-zA-Z0-9_.-]+$ ]] || { echo "Invalid container name" >&2; exit 2; }
if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
elif command -v sudo >/dev/null && sudo -n docker info >/dev/null 2>&1; then
    DOCKER=(sudo -n docker)
else
    echo "Docker unavailable (no privileges requested)" >&2
    exit 2
fi
"${DOCKER[@]}" inspect --type container "$CONTAINER" >/dev/null
# All environment inspection and API credentials remain inside the container.
# Only a short whitelist of diagnostic status fields reaches stdout.
"${DOCKER[@]}" exec -i "$CONTAINER" python - <<'PY'
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

mode = os.environ.get("FASTAPI_RUNTIME_MODE", "")
lan_flag = os.environ.get("HOMELAB_INTERNAL_PROBES_ENABLED", "").lower()
lan_enabled = lan_flag in ("true", "1", "yes", "on")
print("collector_mode=" + ("homelab" if mode == "homelab" else "not-homelab"))
print("lan_probes_environment=" + ("enabled" if lan_enabled else "disabled"))
if mode != "homelab" or not lan_enabled:
    print("result=configuration-mismatch; expected TrueNAS Compose homelab LAN observer")
    sys.exit(1)

key = os.environ.get("DIAGNOSTICS_ACCESS_KEY", "").strip()
headers = {"Accept": "application/json"}
if key:
    headers["X-Diagnostics-Key"] = key
request = Request("http://127.0.0.1:8080/api/homelab/health", headers=headers)
try:
    with urlopen(request, timeout=12) as response:
        payload = json.load(response)
except (HTTPError, URLError, ValueError, TimeoutError) as error:
    code = getattr(error, "code", None)
    print("result=api-unavailable" + (f" HTTP={code}" if code else ""))
    sys.exit(1)
except OSError:
    print("result=api-unavailable")
    sys.exit(1)

enabled = payload.get("internal_probes_enabled")
summary = payload.get("probe_summary") or {}
internal = summary.get("internal") or {}
eligible = internal.get("eligible", 0)
sampled = internal.get("sampled", 0)
completed = internal.get("completed", 0)
disabled = summary.get("internal_disabled_eligible_slots", 0)
print("lan_probes_payload=" + ("enabled" if enabled is True else "disabled-or-unknown"))
for key, value in (("eligible", eligible), ("sampled", sampled),
                   ("completed", completed), ("disabled_slots", disabled)):
    print(f"{key}={value if isinstance(value, int) and not isinstance(value, bool) else 'unknown'}")
if enabled is not True:
    print("result=collector-payload-disagrees-with-runtime")
    sys.exit(1)
if not isinstance(eligible, int) or isinstance(eligible, bool) or eligible <= 0:
    print("result=no-eligible-lan-services; no coverage proven")
    sys.exit(1)
if not isinstance(sampled, int) or isinstance(sampled, bool) or sampled <= 0:
    print("result=no-lan-sample; inspect collector policy and network")
    sys.exit(1)
if not isinstance(completed, int) or isinstance(completed, bool) or completed <= 0:
    print("result=no-completed-lan-probe; collection is not verified")
    sys.exit(1)
print("result=lan-sampling-observed; service health still requires individual evidence")
PY
