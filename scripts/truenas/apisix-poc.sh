#!/usr/bin/env bash
# Explicit opt-in POC operations. Never invoked by quality gates.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
file="$root/apps/apisix/compose.yml"
: "${APISIX_POC_KEY:?provide APISIX_POC_KEY only in the calling shell}"
if [ "${#APISIX_POC_KEY}" -lt 24 ]; then
  echo "BLOCKED: APISIX_POC_KEY must be at least 24 characters" >&2
  exit 2
fi
case "${1:-}" in
  up)
    docker compose -f "$file" --profile poc config --quiet
    docker compose -f "$file" --profile poc up -d
    ;;
  smoke)
    docker compose -f "$file" --profile poc exec -T -e APISIX_POC_KEY echo python - <<'PY'
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

url = "http://apisix:9080/poc/health"
def request(path, key=None, method="GET"):
    headers = {"X-Nabla-POC-Key": key} if key else {}
    try:
        with urlopen(Request(path, headers=headers, method=method), timeout=3) as response:
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
status, body = request(url, os.environ["APISIX_POC_KEY"])
assert status == 200 and b"APISIX POC healthy" in body, f"credential expected 200: {status}"
status, _ = request("http://apisix:9080/missing", os.environ["APISIX_POC_KEY"])
assert status == 404, f"unknown route expected 404: {status}"
status, _ = request(url, os.environ["APISIX_POC_KEY"], method="POST")
assert status != 200, f"method violation: {status}"
print("APISIX_POC_SMOKE_PASS: 401, 200, 404 and invalid method")
PY
    ;;
  down)
    docker compose -f "$file" --profile poc down
    ;;
  *)
    echo "Usage: $0 {up|smoke|down}" >&2
    exit 2
    ;;
esac
