#!/usr/bin/env bash
# Read-only CrowdSec AppSec WAF preflight. No secrets, bans, redeploys, or attacks.
set -euo pipefail
mode="${1:---check}"
case "${mode}" in
  --check)
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    cd "${root}"
    python3 -m pytest -q \
      tests/test_crowdsec_appsec_waf_contract.py \
      tests/test_traefik_crowdsec_bouncer_contract.py \
      tests/test_fastapi_traefik_canary_contract.py
    echo "appsec_static_contract=TESTED"
    ;;
  --runtime)
    if ! command -v docker >/dev/null 2>&1; then
      echo "appsec_runtime=NOT_VERIFIED_DOCKER_UNAVAILABLE"
      exit 2
    fi
    if ! docker inspect crowdsec >/dev/null 2>&1; then
      echo "appsec_runtime=NOT_VERIFIED_NO_CROWDSEC"
      exit 2
    fi
    # CrowdSec must never expose the internal WAF HTTP listener on the host.
    if docker port crowdsec 7422/tcp 2>/dev/null | grep -q .; then
      echo "appsec_exposure=NO_GO_HOST_PORT_PUBLISHED"
      exit 3
    fi
    echo "appsec_exposure=PASS_NOT_HOST_PUBLISHED"
    if ! docker inspect crowdsec --format '{{json .NetworkSettings.Networks}}' |
        grep -q '"traefik_network"'; then
      echo "appsec_network=NOT_VERIFIED_TRAEFIK_NETWORK"
      exit 2
    fi
    echo "appsec_network=PASS_TRAEFIK_NETWORK_JOINED"
    # Separate a failed cscli query from missing Hub collections; both are
    # non-mutating NO-GO states, not evidence that the WAF blocked traffic.
    if ! installed="$(docker exec crowdsec cscli collections list 2>/dev/null)"; then
      echo "appsec_collections=NOT_VERIFIED_CLI_ERROR"
      echo "appsec_next=inspect_crowdsec_cli_and_logs_readonly"
      exit 2
    fi
    missing=()
    for collection in crowdsecurity/appsec-virtual-patching crowdsecurity/appsec-generic-rules; do
      if ! grep -Fq -- "$collection" <<<"$installed"; then
        missing+=("$collection")
      fi
    done
    if ((${#missing[@]})); then
      echo "appsec_collections=NOT_VERIFIED_MISSING"
      printf "appsec_collections_missing=%s\n" "$(IFS=,; echo "${missing[*]}")"
      # Print only allowlisted COLLECTIONS state; never dump all env or secrets.
      declared="$(docker exec crowdsec printenv COLLECTIONS 2>/dev/null || true)"
      if [[ -z "$declared" ]]; then
        echo "appsec_runtime_collections_declaration=NOT_VERIFIED"
      else
        missing_declared=()
        for collection in "${missing[@]}"; do
          if [[ " $declared " != *" $collection "* ]]; then
            missing_declared+=("$collection")
          fi
        done
        if ((${#missing_declared[@]})); then
          echo "appsec_runtime_collections_declaration=MISSING_REQUIRED"
        else
          echo "appsec_runtime_collections_declaration=EXPECTED_PRESENT"
        fi
      fi
      echo "appsec_next=review_running_compose_and_redeploy_from_versioned_source_then_recheck"
      exit 2
    fi
    echo "appsec_collections=PASS_INSTALLED"
    unset installed missing
    # Read-only metrics can confirm processing; they cannot prove HTTP blocking.
    if docker exec crowdsec cscli metrics show appsec >/dev/null 2>&1; then
      echo "appsec_metrics=AVAILABLE_BLOCK_BEHAVIOR_NOT_VERIFIED"
    else
      echo "appsec_metrics=NOT_VERIFIED_NO_RUNTIME_EVIDENCE"
      exit 2
    fi
    echo "appsec_waf_request_block=NOT_VERIFIED_REQUIRES_CONTROLLED_CANARY_TEST"
    # Never infer a secure gateway from AppSec metrics. Current Traefik
    # :8080 API may expose the plugin-rendered LAPI key, and Prometheus
    # scrapes that endpoint. Gate the shared tunnel cutover until that
    # dashboard/metrics migration is independently accepted.
    if docker inspect traefik --format '{{json .Config.Cmd}}' 2>/dev/null |
        grep -q -- '--api.insecure=true'; then
      echo "traefik_dashboard=NO_GO_UNAUTHENTICATED_API"
      echo "appsec_public_cutover=NO_GO_TRAEFIK_ADMIN_BOUNDARY"
      exit 3
    fi
    echo "traefik_dashboard=NOT_VERIFIED_REQUIRE_AUTH_AND_METRICS_RECEIPT"
    ;;
  *)
    echo "Usage: ${0##*/} --check|--runtime"
    exit 2
    ;;
esac
