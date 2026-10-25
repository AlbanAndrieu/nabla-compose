#!/usr/bin/env bash
# APISIX isolated operations. Default is non-mutating; no CI or implicit deploy.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
file="$root/apps/apisix/compose.yml"
# Rollback and metadata diagnostics work without a retained gateway key.
# Compose requires a nonempty interpolation value for *down* as well;
# the fixed placeholder is not a credential and never starts a service.
if [[ "${#}" -ne 1 ]]; then
  echo "Usage: $0 {up|smoke|check|down}" >&2
  exit 2
fi
case "${1}" in
  up|smoke)
    if [[ -z "${APISIX_KEY:-}" || "${#APISIX_KEY}" -lt 24 ||
          "${#APISIX_KEY}" -gt 256 || "$APISIX_KEY" =~ [[:space:][:cntrl:]] ]]; then
      echo "BLOCKED: APISIX_KEY must contain 24-256 non-whitespace, printable characters" >&2
      exit 2
    fi
    ;;
  check|down)
    : "${APISIX_KEY:=apisix-cleanup-placeholder-not-a-live-key}"
    export APISIX_KEY
    ;;
  *)
    echo "Usage: $0 {up|smoke|check|down}" >&2
    exit 2
    ;;
esac
case "${1:-}" in
  up)
    docker compose -f "$file" --profile apisix config --quiet
    docker compose -f "$file" --profile apisix up -d
    ;;
  smoke)
    docker compose -f "$file" --profile apisix exec -T -e APISIX_KEY echo python - <<'PY'
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

# Ignore inherited proxy settings; only the isolated Docker network is trusted.
opener = build_opener(ProxyHandler({}))
url = "http://apisix:9080/health"
def request(path, key=None, method="GET"):
    headers = {"X-Nabla-APISIX-Key": key} if key else {}
    try:
        with opener.open(Request(path, headers=headers, method=method), timeout=3) as response:
            return response.status, response.read()
    except HTTPError as failure:
        return failure.code, b""

for _ in range(30):
    try:
        status, _ = request(url)
        break
    except URLError:
        time.sleep(1)
else:
    raise SystemExit("APISIX did not start within the bounded preflight")
assert status == 401, f"without credential expected 401: {status}"
status, body = request(url, os.environ["APISIX_KEY"])
assert status == 200 and b"APISIX healthy" in body, f"credential expected 200: {status}"
status, _ = request("http://apisix:9080/missing", os.environ["APISIX_KEY"])
assert status == 404, f"unknown route expected 404: {status}"
status, _ = request(url, os.environ["APISIX_KEY"], method="POST")
assert status in (404, 405), f"POST must not match GET-only route: {status}"
print("APISIX_SMOKE_PASS: 401, 200, 404 and invalid method")
PY
    ;;
  check)
    # Metadata only. HTTP authentication and proxy routing require smoke.
    if ! docker compose -f "$file" --profile apisix config --quiet >/dev/null; then
      printf '%s\n' 'apisix_config=unverified' >&2
      exit 2
    fi
    rc=0
    for service in apisix echo; do
      if ! container_id="$(docker compose -f "$file" --profile apisix ps -q "$service" 2>/dev/null)"; then
        printf 'service=%s runtime=unverified http=not_checked\n' "$service"
        if ((rc == 0)); then rc=2; fi
        continue
      fi
      if [[ ! "$container_id" =~ ^[0-9a-f]{12,64}$ ]]; then
        printf 'service=%s runtime=not_deployed_or_ambiguous http=not_checked\n' "$service"
        if ((rc == 0)); then rc=2; fi
        continue
      fi
      if ! metadata="$(docker inspect --format '{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null)"; then
        printf 'service=%s runtime=unverified http=not_checked\n' "$service"
        if ((rc == 0)); then rc=2; fi
        continue
      fi
      IFS='|' read -r runtime health <<<"$metadata"
      case "$runtime:$health" in
        running:healthy|running:none)
          printf 'service=%s runtime=running health=%s http=not_checked\n' "$service" "$health"
          ;;
        running:unhealthy|exited:*|dead:*|restarting:*)
          printf 'service=%s runtime=failed http=not_checked\n' "$service"
          rc=1
          ;;
        *)
          printf 'service=%s runtime=unverified http=not_checked\n' "$service"
          if ((rc == 0)); then rc=2; fi
          ;;
      esac
    done
    exit "$rc"
    ;;
  down)
    docker compose -f "$file" --profile apisix down
    ;;
  *)
    echo "Usage: $0 {up|smoke|check|down}" >&2
    exit 2
    ;;
esac
