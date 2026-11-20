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
    installed="$(docker exec crowdsec cscli collections list 2>/dev/null || true)"
    if ! grep -q 'crowdsecurity/appsec-virtual-patching' <<<"${installed}" ||
       ! grep -q 'crowdsecurity/appsec-generic-rules' <<<"${installed}"; then
      echo "appsec_collections=NOT_VERIFIED"
      exit 2
    fi
    echo "appsec_collections=PASS_INSTALLED"
    unset installed
    # Read-only metrics can confirm processing; they cannot prove HTTP blocking.
    if docker exec crowdsec cscli metrics show appsec >/dev/null 2>&1; then
      echo "appsec_metrics=AVAILABLE_BLOCK_BEHAVIOR_NOT_VERIFIED"
    else
      echo "appsec_metrics=NOT_VERIFIED_NO_RUNTIME_EVIDENCE"
      exit 2
    fi
    echo "appsec_waf_request_block=NOT_VERIFIED_REQUIRES_CONTROLLED_CANARY_TEST"
    ;;
  *)
    echo "Usage: ${0##*/} --check|--runtime"
    exit 2
    ;;
esac
