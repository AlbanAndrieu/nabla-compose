# Canonical short commands for local-first repository work.
# This coexists with the legacy Makefile; nothing here calls its default Docker build.
set shell := ["bash", "-euo", "pipefail", "-c"]

# List documented tasks without running any build or deployment.
default:
    @just --list

# Install the existing canonical Git hooks.
hooks:
    mise run hooks

# Show bounded branch/change context and suggested repository skills.
context:
    mise run agent-context

# Cheap Git-only safety gate before dependency/setup work.
preflight:
    mise run agent-preflight

# Dependency-free syntax-only fallback for disconnected development (L1, not publication).
offline:
    bash scripts/agent-offline-check.sh

# Fast iterative local-first loop: autofix + changed-file contracts only.
loop:
    mise run agent-loop

# Full local quality gate without publishing.
quality:
    mise run agent-quality

# Apply deterministic local fixes and generated artifacts.
fix:
    mise run agent-fix

# Strict full local publication gate.
pre-push:
    mise run agent-pre-push

# Strict validation without pushing or merging.
publish:
    mise run agent-publish

# Read-only post-reboot FastAPI/TrueNAS dependency orchestration.
truenas-fastapi-check:
    python3 scripts/truenas/diagnose-fastapi-integrations.py

# Fast, offline manifest hygiene gate, including duplicate hooks/repos.
# Mirrors Bababou's local-first workflow; does not install hooks or start CI.
precommit-config-test:
    python3 -m py_compile scripts/quality/check-precommit-config.py
    python3 scripts/quality/check-precommit-config.py
    python3 -m pytest -q tests/test_precommit_integrity.py

# Bababou parity: offline local quality-gate contracts, not hosted Actions.
quality-contracts-test:
    bash -n scripts/quality-gate.sh
    python3 -m py_compile scripts/quality/check-precommit-config.py
    python3 scripts/quality/check-precommit-config.py
    python3 -m pytest -q tests/test_precommit_integrity.py tests/test_quality_gate_content_scope.py

# Validate Anthropic-first Hermes route and scoped LiteLLM budgets offline.
# No upstream LLM call, TrueNAS restart, API key or Actions minutes.
hermes-opus-routing-test:
    python3 -m py_compile scripts/truenas/check-litellm-hermes-credentials.py
    python3 -m pytest -q tests/test_hermes_opus_routing_contract.py tests/test_hermes_litellm_budget_contract.py tests/test_hermes_poc_contract.py tests/test_hermes_poc_preflight.py tests/test_hermes_cloud_credential_preflight.py

# Temporary 24 October migration runbook checks; mocks midclt and App changes.
# No actual TrueNAS, Kubernetes, cloud model request or paid GitHub CI.
migration-20261024-test:
    bash -n scripts/truenas/finish-migrations-20261024.sh
    python3 -m pytest -q tests/test_finish_migrations_20261024.py

# Offline TrueNAS restart planning tests. Never contacts TrueNAS or invokes Actions.
# Requires a locally installed pytest; no package install, runner, or deployment.
truenas-catalog-v2-test:
    python3 -m py_compile scripts/truenas/plan-catalog-v2-restart.py scripts/truenas/restart-catalog-v2-apps.py scripts/truenas/catalog_v2_restart_dependencies.py scripts/secrets/inventory_vaultwarden.py
    python3 -m pytest -q tests/test_catalog_v2_restart_plan.py tests/test_catalog_v2_restart_waves.py tests/test_catalog_v2_restart_dependencies.py tests/test_catalog_v2_core_guard.py tests/test_vaultwarden_inventory_contract.py

# Read-only local contracts for Actions usage and budget reporting; no hosted runners.
actions-usage-test:
    python3 -m py_compile scripts/github-actions-usage.py
    python3 -m pytest -q tests/test_github_actions_usage.py

# Original repository quality gate, kept separate from the agent-first path.
quality-gate:
    mise run quality

# Refresh/review dagger.lock explicitly before running the PoC.
dagger-sync:
    mise run dagger-sync

# List the bounded experimental Dagger checks; this is not the publication gate.
dagger-list:
    mise run dagger-list

# Run the experimental ShellCheck + Biome Dagger PoC.
dagger-poc:
    mise run dagger-poc

# Run the native reference checks used for Dagger parity.
dagger-native-parity:
    mise run dagger-native-parity

# Benchmark warm native-vs-Dagger paths without clearing shared caches.
dagger-bench:
    mise run dagger-bench

# Test this justfile and the Betterleaks toolchain contracts.
tooling-test:
    python -m unittest tests.test_dev_tooling_contract -v

# Scan current files for secrets; findings are redacted, not sent to providers.
secrets:
    betterleaks dir . --config .gitleaks.toml --redact

# Inspect staged changes only (same target as Pre-commit).
secrets-staged:
    betterleaks git . --pre-commit --staged --config .gitleaks.toml --redact

# Full Git history scan, explicitly opt-in due to cost.
secrets-history:
    betterleaks git . --config .gitleaks.toml --redact

# Legacy Makefile is deliberately retained.
make-help:
    make help

# Generate outside-in Synthetic Open Schema YAML from the exposure catalog.
sos-generate:
    python scripts/generate-synthetic-open-schema.py

# Validate the deterministic SOS generator contract without network probes.
sos-test:
    python -m pytest -q tests/test_synthetic_open_schema_generation.py
