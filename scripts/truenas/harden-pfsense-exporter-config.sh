#!/usr/bin/env bash
set -euo pipefail

RUNTIME_CONFIG="${PFSENSE_EXPORTER_CONFIG:-/mnt/cpool/prometheus/secrets/pfsense-exporter.yml}"
ROOT="$(git rev-parse --show-toplevel)"
TEMPLATE="${ROOT}/apps/prometheus/pfsense-exporter.example.yml"

fail() {
	printf 'ERROR: %s\n' "$*" >&2
	exit 1
}

[[ "${EUID}" -eq 0 ]] ||
	fail "run with sudo so the runtime config remains root-owned mode 0600"

for command in python3 git; do
	command -v "${command}" >/dev/null 2>&1 ||
		fail "${command} is required"
done

[[ -f "${RUNTIME_CONFIG}" ]] ||
	fail "runtime config must be a regular file: ${RUNTIME_CONFIG}"
[[ -s "${RUNTIME_CONFIG}" ]] ||
	fail "runtime config is empty: ${RUNTIME_CONFIG}"
[[ -f "${TEMPLATE}" ]] ||
	fail "reviewed template is missing: ${TEMPLATE}"

python3 - "${RUNTIME_CONFIG}" "${TEMPLATE}" <<'PY'
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

runtime = Path(sys.argv[1])
template = Path(sys.argv[2])

current = runtime.read_text(encoding="utf-8")
match = re.search(
    r"^[ \t]*key:[ \t]*[\"']?([^\"'\r\n]+)[\"']?[ \t]*$",
    current,
    flags=re.MULTILINE,
)
if not match:
    raise SystemExit("runtime config has no usable key field")

key = match.group(1).strip()
placeholder = "REPLACE_WITH_DEDICATED_PFSENSE_EXPORTER_API_KEY"
reviewed = template.read_text(encoding="utf-8")
if reviewed.count(placeholder) != 1:
    raise SystemExit("reviewed template must contain exactly one API-key placeholder")

updated = reviewed.replace(placeholder, key)

fd, raw_tmp = tempfile.mkstemp(
    prefix=".pfsense-exporter.",
    suffix=".yml",
    dir=str(runtime.parent),
    text=True,
)
tmp = Path(raw_tmp)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(updated)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.chown(tmp, 0, 0)
    os.replace(tmp, runtime)
finally:
    if tmp.exists():
        tmp.unlink()

# Fail closed on the intended low-impact contract without printing the key.
result = runtime.read_text(encoding="utf-8")
required = (
    "timeout: 8",
    "max_collector_concurrency: 1",
    "      - system",
    "      - gateways",
    "      - service",
)
missing = [item for item in required if item not in result]
if missing:
    raise SystemExit("hardened runtime config is missing expected low-impact settings")
PY

printf 'OK: pfSense exporter runtime config hardened without printing the API key\n'
printf '    scrape pressure is controlled by Prometheus (300s) and collectors are serialized\n'
scripts/truenas/audit-app-lifecycle.sh:1858:1: `}` can only be used to close a block
Unable to find image 'mvdan/shfmt:v3.13.1@sha256:f22f3936140be1ba02d493b5d2b91d0e8b4af93fd903e7f46c477822bca4a3be' locally
docker.io/mvdan/shfmt@sha256:f22f3936140be1ba02d493b5d2b91d0e8b4af93fd903e7f46c477822bca4a3be: Pulling from mvdan/shfmt
5b958e81722e: Pulling fs layer
5b958e81722e: Verifying Checksum
5b958e81722e: Download complete
5b958e81722e: Pull complete
Digest: sha256:f22f3936140be1ba02d493b5d2b91d0e8b4af93fd903e7f46c477822bca4a3be
Status: Downloaded newer image for mvdan/shfmt@sha256:f22f3936140be1ba02d493b5d2b91d0e8b4af93fd903e7f46c477822bca4a3be
