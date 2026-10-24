#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Git hooks export GIT_DIR: with it, --show-toplevel returns the current
# directory (scripts/quality) in a worktree. Rediscover the repository.
unset GIT_DIR GIT_WORK_TREE
# Resolve exactly one root path: the previous 'cmd || cd && pwd' printed
# both Git's root and pwd on success due to shell operator precedence.
if ROOT="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel 2>/dev/null)"; then
  :
else
  ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi
cd "${ROOT}"

# Check-only contract: never rewrite generated configuration during a quality gate.
# Always choose Python with repository dependencies, not an arbitrary system Python.
python_with_deps="$ROOT/scripts/quality/python-with-repo-deps.sh"
bash "$python_with_deps" scripts/generate-service-consumers.py --check
bash "$python_with_deps" scripts/truenas/render-autokuma-monitors.py --validate-only
bash "$python_with_deps" -m unittest -v \
  tests.test_homarr_sync \
  tests.test_autokuma_materialization \
  tests.test_service_consumers_status_contract \
  tests.test_service_topology_generator
printf 'PASS: Homarr/Gatus/AutoKuma consumer projections and unit tests match committed sources\n'
