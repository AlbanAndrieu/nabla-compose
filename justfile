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

# Read-only repository policy check for external skills and TrueNAS/Talos decisions.
# No dependency installation, networking, containers or GitHub Actions.
agent-skills-check:
    python3 -m py_compile scripts/quality/check-agent-skill-precedence.py tests/test_agent_skill_precedence_contract.py
    python3 -m unittest discover -s tests -p 'test_agent_skill_precedence_contract.py' -v
    python3 scripts/quality/check-agent-skill-precedence.py

# Read-only Backstage v2 / icon parity check. Pass --site-generated separately
# when the sibling website checkout is available (no network fetch).
catalog-convergence-check:
    python3 -m py_compile scripts/quality/check-site-catalog-convergence.py tests/test_site_catalog_convergence_contract.py
    python3 -m unittest discover -s tests -p 'test_site_catalog_convergence_contract.py' -v
    python3 scripts/quality/check-site-catalog-convergence.py

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
    python3 -m pytest -q tests/test_hermes_opus_routing_contract.py tests/test_hermes_litellm_budget_contract.py tests/test_hermes_contract.py tests/test_hermes_preflight.py tests/test_hermes_cloud_credential_preflight.py

# OpenClaw cron SecretRef contract: no Gateway, network, token or stored plan required.
openclaw-cron-secret-plan-test:
    python3 -m py_compile scripts/workstation/diagnose-openclaw-secrets-plan.py tests/test_openclaw_secrets_plan_diagnostic.py
    python3 -m unittest discover -s tests -p 'test_openclaw_secrets_plan_diagnostic.py' -v

# Native OpenClaw dry-run and redaction. Fail closed if dotenv scrub would occur.
# Pure offline regressions: no pfSense access or GitHub Actions.
pfsense-unbound-wifi-test:
    bash -n scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh
    bash -n scripts/pfsense/audit-posture.sh
    bash -n scripts/workstation/diagnose-whatsapp-web-path.sh
    python3 -m unittest discover -s tests -p 'test_pfsense_unbound_whatsapp_contract.py' -v
    python3 -m unittest discover -s tests -p 'test_pfsense_pflow_posture_contract.py' -v

# Read-only probes run on a workstation that can reach pfSense via SSH.
pfsense-unbound-check:
    bash scripts/pfsense/diagnose-pfblocker-unbound-whatsapp.sh --check

# Read-only WhatsApp Web IPv4/IPv6 edge path, with no browser-session access.
whatsapp-web-path-check:
    bash scripts/workstation/diagnose-whatsapp-web-path.sh --check

# Operator-only: requires private cron-plan.json on the Ubuntu workstation.
openclaw-cron-secret-plan-check:
    python3 scripts/workstation/diagnose-openclaw-secrets-plan.py

# Compare two native dry-runs, with ephemeral owner-private no-scrub plan.
# Read-only for OpenClaw runtime; exit 2 is expected while scrub remains unsafe.
openclaw-cron-secret-plan-compare:
    python3 scripts/workstation/diagnose-openclaw-secrets-plan.py --compare-no-scrub

# Print operator commands only. Does not contact TrueNAS or start migrations.
migration-20261024-commands:
    bash scripts/truenas/finish-migrations-20261024.sh --next-commands

# Explicit local-only consolidation of the five review gates.
# The script stops on first failed recipe; no GitHub Actions or TrueNAS apply.
migration-20261024-local-gates:
    bash scripts/truenas/finish-migrations-20261024.sh --local-gates

# Offline migration, FastAPI LAN collector and Akvorado regressions.
# No TrueNAS mutation or GitHub Actions.
migration-20261024-test:
    bash -n scripts/truenas/finish-migrations-20261024.sh
    bash -n scripts/truenas/diagnose-sentry-consumers.sh
    bash -n scripts/truenas/verify-fastapi-lan-probes.sh
    python3 -m pytest -q tests/test_finish_migrations_20261024.py tests/test_sentry_consumers_diagnostic.py tests/test_fastapi_lan_probe_contract.py tests/test_akvorado_flow_deltas.py tests/test_akvorado_flow_diagnostic.py tests/test_akvorado_static_ifindex_contract.py tests/test_openrag_secret_migration_metadata.py

# Maintained runtime/version review is read-only, no registry or paid Actions.
upgrade-runtime-audit:
    python3 scripts/quality/audit-supported-runtimes.py

# Local-only contracts for platform pins, PHP/Python runtime detection and Talos safety.
upgrade-runtime-test:
    python3 -m py_compile scripts/quality/audit-supported-runtimes.py scripts/talos/preflight-supported-upgrade.py scripts/truenas/audit-live-language-runtimes.py
    python3 -m pytest -q tests/test_supported_runtime_policy.py tests/test_talos_supported_upgrade.py tests/test_live_language_runtime_audit.py

# Inventory running TrueNAS container interpreter patches without image pulls/restarts.
truenas-live-language-audit:
    python3 scripts/truenas/audit-live-language-runtimes.py --check

# Requires authenticated Talos and Kubernetes CLI; this does not upgrade nodes.
talos-upgrade-preflight:
    python3 scripts/talos/preflight-supported-upgrade.py --check

# Fast operator-acknowledged upgrade paths; check prints immutable hashes only.
fast-talos-plan image:
    python3 scripts/talos/fast-batch-upgrade.py --check --installer-image "{{image}}"

fast-truenas-plan scope="applications" parallel="6":
    python3 scripts/truenas/fast-bulk-redeploy-apps.py --check --scope "{{scope}}" --parallel "{{parallel}}"

fast-maintenance-test:
    python3 -m py_compile scripts/talos/fast-batch-upgrade.py scripts/truenas/fast-bulk-redeploy-apps.py
    python3 -m pytest -q tests/test_fast_batch_talos_upgrade.py tests/test_fast_bulk_truenas_redeploy.py

# Read-only, redacted AI service recovery: no secret values, no deployments.
truenas-ai-recovery-check:
    sudo python3 scripts/truenas/diagnose-ai-secret-recovery.py --check

truenas-ai-recovery-test:
    python3 -m py_compile scripts/truenas/diagnose-ai-secret-recovery.py
    python3 -m pytest -q tests/test_ai_secret_recovery_diagnostic.py

# Functional acceptance: TrueNAS state + Docker health + semantic HTTP/PromQL.
# Fail nonzero if an App is BLOCKED, DEGRADED or UNKNOWN, even when TrueNAS
# app.query returns RUNNING. Use the nonblocking report for status-only review.
truenas-readiness-check:
    sudo python3 scripts/truenas/diagnose-service-readiness.py --check --strict

truenas-readiness-report:
    sudo python3 scripts/truenas/diagnose-service-readiness.py --check

truenas-readiness-test:
    python3 -m py_compile scripts/truenas/diagnose-service-readiness.py
    python3 -m pytest -q tests/test_service_readiness_diagnostic.py tests/test_compact_ops_diagnostics.py tests/test_gatus_api_diagnostic.py tests/test_prometheus_config_access_repair.py tests/test_openrag_dependencies_diagnostic.py tests/test_prometheus_rules_access_repair.py

# Read-only OpenRAG backend/frontend/Langflow/OpenSearch dependency diagnosis.
truenas-openrag-dependencies-check:
    sudo bash scripts/truenas/diagnose-openrag-dependencies.sh --check

truenas-openrag-dependencies-test:
    python3 -m pytest -q tests/test_openrag_dependencies_diagnostic.py

# Read-only host preflight; --apply remains a separate, explicit operator action.
truenas-prometheus-config-check:
    sudo bash scripts/truenas/repair-prometheus-config-access.sh --check

# Rule-tree check is read-only; repair demands explicit approval and unchanged count.
truenas-prometheus-rules-check:
    sudo bash scripts/truenas/repair-prometheus-rules-access.sh --check

truenas-prometheus-rules-test:
    bash -n scripts/truenas/repair-prometheus-rules-access.sh
    python3 -m pytest -q tests/test_prometheus_rules_access_repair.py

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

# Read-only public/private DNS check on any host (no local Docker inspection).
sample-dns:
    bash scripts/ingress/diagnose-sample-dns.sh --check

# TrueNAS variant: inspect local Pi-hole container configuration, read-only.
sample-dns-truenas:
    bash scripts/ingress/diagnose-sample-dns.sh --truenas

# Run from the workstation (NetworkManager + active DNS/DHCP evidence).
sample-dns-workstation:
    bash scripts/ingress/diagnose-sample-dns.sh --workstation

# Offline mock-contracts, no real DNS or Docker requests.
sample-dns-test:
    python3 -m unittest discover -s tests -p test_sample_dns_diagnostic.py -v
