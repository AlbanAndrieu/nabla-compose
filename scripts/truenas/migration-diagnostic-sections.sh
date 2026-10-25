# shellcheck shell=bash
# Sourced read-only check registry for finish-migrations-20261024.sh.
# Requires run_check, record, plan_wave, SESSION_DIR from the guarded caller.
# No CLI parser, apply/restart implementation or standalone entrypoint.
# shellcheck shell=bash

check_section() {
  case "$1" in
    platform)
      run_check platform-health bash scripts/truenas/check-homelab-services.sh
      run_check docker-orphan-shims bash scripts/truenas/diagnose-docker-orphan-shims.sh --check
      run_check pihole-dns-sync bash scripts/truenas/verify-pihole-dns-sync.sh
      run_check shared-data bash scripts/truenas/diagnose-shared-data-services.sh
      ;;
    migrations)
      run_check supported-runtime-audit python3 scripts/quality/audit-supported-runtimes.py --strict-eol
      run_check live-language-patches python3 scripts/truenas/audit-live-language-runtimes.py --check
      run_check migration-manifest python3 scripts/security/check-migration-readiness.py --check
      run_check secrets-runtime bash scripts/truenas/bootstrap-repository-runtime.sh --check
      run_check sentry-system-secret bash scripts/truenas/reconcile-sentry-system-secret.sh --check
      run_check sentry-migrator-secret bash scripts/truenas/reconcile-sentry-migrator-credential.sh --check
      run_check openrag-opensearch-secret bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
      run_check defectdojo-preflight bash scripts/truenas/preflight-defectdojo.sh
      run_check openwebui-pra bash scripts/truenas/diagnose-openwebui-backup-pra.sh --check
      ;;
    catalog)
      plan_wave core || true
      plan_wave gatus || true
      plan_wave deferred || true
      ;;
    services)
      # Three independent layers: TrueNAS lifecycle, Docker health, semantic HTTP.
      # No arbitrary credentials, response bodies or raw logs on stdout.
      run_check functional-readiness python3 scripts/truenas/diagnose-service-readiness.py --check --strict --color never --icons never
      run_check gatus bash scripts/truenas/diagnose-gatus.sh
      run_check sentry bash scripts/truenas/diagnose-sentry.sh --check
      run_check defectdojo bash scripts/truenas/diagnose-defectdojo.sh --check
      run_check cyberbro bash scripts/truenas/diagnose-cyberbro.sh
      run_check prometheus bash scripts/truenas/diagnose-prometheus-targets.sh --check
      run_check app-states bash scripts/truenas/triage-post-reboot-apps.sh
      ;;
    ai)
      # Dependency readiness is a separate gate from Langflow/Docling ingestion.
      # A frontend stuck CREATED is a functional blocker, not an App outage.
      run_check openrag-startup bash scripts/truenas/diagnose-openrag-startup.sh --check
      run_check openrag-dependencies bash scripts/truenas/diagnose-openrag-dependencies.sh --check
      run_check hermes-native bash scripts/truenas/diagnose-hermes-agent.sh --check
      # Required runtime secrets and actual failed Apps are blocking.
      run_check ai-runtime-recovery python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict
      # Anthropic and OpenAI are opt-in cloud upstreams, not prerequisites
      # for the existing local LiteLLM service. Report lack as WARN only.
      if python3 scripts/truenas/check-litellm-hermes-credentials.py --check >"${SESSION_DIR}/litellm-provider-keys.log" 2>&1; then
        record litellm-provider-keys PASS "${SESSION_DIR}/litellm-provider-keys.log"
      else
        record litellm-provider-keys WARN "${SESSION_DIR}/litellm-provider-keys.log"
      fi
      ;;
    critical)
      # Five independent read-only diagnostics; do not stop at first failure.
      # run_check writes private 0600 evidence and the summary remains bounded.
      for service in prometheus openrag sentry akvorado defectdojo; do
        check_section "$service"
      done
      ;;
    prometheus)
      # A TrueNAS App RUNNING does not prove its main container is running.
      run_check prometheus-targets bash scripts/truenas/diagnose-prometheus-targets.sh --check
      run_check prometheus-config-access bash scripts/truenas/repair-prometheus-config-access.sh --check
      run_check prometheus-rules-access bash scripts/truenas/repair-prometheus-rules-access.sh --check
      ;;
    openrag)
      # Legacy secret comparator is strictly read-only here; it cannot
      # determine whether the Vaultwarden materialization is ready.
      run_check openrag-startup bash scripts/truenas/diagnose-openrag-startup.sh --check
      run_check openrag-dependencies bash scripts/truenas/diagnose-openrag-dependencies.sh --check
      run_check ai-runtime-recovery python3 scripts/truenas/diagnose-ai-secret-recovery.py --check --strict
      run_check openrag-opensearch-legacy-secret bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
      run_check openrag-env-migration bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
      run_check openrag-backstage-bundle python3 scripts/check-service-migration-bundle.py --app openrag
      ;;
    defectdojo)
      # Observe Django/uWSGI + Nginx HTML origin, internal DNS and Traefik SNI.
      # Never initialize Django or alter PostgreSQL while diagnosing UI.
      run_check defectdojo-preflight bash scripts/truenas/preflight-defectdojo.sh
      run_check defectdojo-private-ingress bash scripts/truenas/diagnose-defectdojo.sh --check
      ;;
    sentry)
      # Read-only consumer state plus guarded Sentry recovery preflight.
      run_check sentry-consumers bash scripts/truenas/diagnose-sentry-consumers.sh --check
      run_check sentry-recovery-preflight bash scripts/truenas/recover-sentry-deploying.sh --check
      ;;
    akvorado)
      # Read-only proof that the orchestrator sees the reviewed static provider
      # file; SHA equality does not mean the running process reloaded it.
      run_check akvorado-config bash scripts/truenas/diagnose-akvorado-config.sh --check
      # Counter snapshots only. A fresh ClickHouse batch is not a SQL-row proof.
      run_check akvorado-blocked python3 scripts/truenas/diagnose-akvorado-flow.py --strict --fail-on-blocked --observe-seconds 20
      run_check akvorado-fresh-inserts python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 20
      ;;
    observability)
      # Runtime truth requires fresh probes, not a TrueNAS App RUNNING flag.
      run_check prometheus-targets bash scripts/truenas/diagnose-prometheus-targets.sh --check
      run_check prometheus-config-access bash scripts/truenas/repair-prometheus-config-access.sh --check
      run_check prometheus-rules-access bash scripts/truenas/repair-prometheus-rules-access.sh --check
      run_check openrag-readiness bash scripts/truenas/diagnose-openrag-dependencies.sh --check
      run_check akvorado-fresh-inserts python3 scripts/truenas/diagnose-akvorado-flow.py --strict --require-inserts --observe-seconds 20
      ;;
    secrets)
      # Metadata and filesystem checks only; never print raw env or BW_SESSION.
      run_check canonical-secret-files bash scripts/truenas/bootstrap-repository-runtime.sh --check
      run_check first-wave-env bash scripts/truenas/accept-runtime-env-first-wave.sh --check all
      run_check openrag-env-migration bash scripts/truenas/bootstrap-repository-env-files.sh --check openrag
      run_check akvorado-env-migration bash scripts/truenas/bootstrap-repository-env-files.sh --check akvorado
      run_check openrag-backstage-bundle python3 scripts/check-service-migration-bundle.py --app openrag
      run_check openrag-opensearch-secret bash scripts/truenas/reconcile-openrag-opensearch-secret.sh --check
      if command -v bw >/dev/null 2>&1 && [[ -n "${BW_SESSION:-}" ]]; then
        run_check vaultwarden-inventory python3 scripts/secrets/inventory_vaultwarden.py --json
      else
        record vaultwarden-inventory SKIP 'BW_SESSION or Bitwarden CLI unavailable on this host'
      fi
      ;;
    convergence)
      # No browser fetching or runtime mutation. Generators run in --check mode.
      run_check canonical-service-icons python3 scripts/quality/check-site-catalog-convergence.py
      run_check agent-skill-precedence python3 scripts/quality/check-agent-skill-precedence.py
      run_check backstage-generated-contract python3 scripts/generate-catalog-v2-artifacts.py --check
      run_check service-topology-generated-contract python3 scripts/generate-service-topology.py --check
      ;;
    lan)
      # Verify only the LAN collector; never enable internal probes from Cloud.
      if [[ -f scripts/truenas/verify-fastapi-lan-probes.sh ]]; then
        run_check fastapi-lan-probes bash scripts/truenas/verify-fastapi-lan-probes.sh --check
      else
        record fastapi-lan-probes SKIP 'LAN verification script missing from this checkout'
      fi
      ;;
    talos)
      if command -v kubectl >/dev/null 2>&1 && command -v talosctl >/dev/null 2>&1; then
        run_check talos-cluster bash scripts/talos/validate-cluster.sh
        run_check talos-supported-upgrade python3 scripts/talos/preflight-supported-upgrade.py --check
        run_check truenas-csi bash scripts/talos/smoke-truenas-csi-nfs.sh --check
      else
        record talos-cluster SKIP "kubectl/talosctl unavailable on TrueNAS; use an authorized workstation"
        record truenas-csi SKIP "kubectl/talosctl unavailable on TrueNAS; use an authorized workstation"
      fi
      ;;
  esac
}
