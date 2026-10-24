#!/usr/bin/env bash
# Check-only topology and service-consumer contracts in an initialized worktree.
set -Eeuo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd -- "$root"
python -c 'import yaml, pytest' || { printf 'BLOCKED: worktree Python dependencies missing\n' >&2; exit 3; }
python scripts/generate-service-topology.py --check
python scripts/generate-service-consumers.py --check
python scripts/generate-catalog-v2-artifacts.py --check
python -m pytest -q tests/test_service_topology_generator.py tests/test_service_consumer_drift_diagnostic.py
bash scripts/agent-quality-gate.sh
