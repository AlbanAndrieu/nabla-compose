"""CrowdSec AppSec WAF canary is isolated, fails closed and remains opt-in.

Offline deterministic contracts only; neither deployment nor detection
results should be inferred from these tests.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CROWDSEC = ROOT / "apps/crowdsec/compose.yml"
MIDDLEWARE = ROOT / "apps/traefik/dynamic/crowdsec.yml"
ACQUIS = ROOT / "apps/crowdsec/acquis.d/appsec.yaml"
SAMPLE = ROOT / "apps/sample/compose.yml"
TUNNEL = ROOT / "terraform/cloudflare/tunnel.tofu"


def test_appsec_acquisition_is_internal_and_versioned_hub():
    crowdsec = yaml.safe_load(CROWDSEC.read_text(encoding="utf-8"))["services"]["crowdsec"]
    aquis = yaml.safe_load(ACQUIS.read_text(encoding="utf-8"))
    collections = set(crowdsec["environment"]["COLLECTIONS"].split())
    assert {"crowdsecurity/appsec-virtual-patching", "crowdsecurity/appsec-generic-rules"} <= collections
    assert aquis == {
        "source": "appsec",
        "name": "fastapi-traefik-appsec",
        "listen_addr": "0.0.0.0:7422",
        "appsec_configs": ["crowdsecurity/appsec-default", "nabla/fastapi-canary"],
        "labels": {"type": "appsec"},
    }
    # No other process sees an AppSec host port, only Docker traffic.
    assert not any(":7422" in str(p) or str(p).endswith(":7422") for p in crowdsec["ports"])
    assert crowdsec["networks"] == ["default", "traefik_network"]
    assert crowdsec["image"] == "crowdsecurity/crowdsec:v1.8.1"
    assert crowdsec["mem_limit"] == "384m"  # Monitor before cutover; no blind resource increase
    assert "./acquis.d:/etc/crowdsec/acquis.d:ro" in crowdsec["volumes"]
    assert "./appsec-rules/nabla:/etc/crowdsec/appsec-rules/nabla:ro" in crowdsec["volumes"]
    assert "./appsec-configs/nabla:/etc/crowdsec/appsec-configs/nabla:ro" in crowdsec["volumes"]
    assert not any(str(x).startswith("traefik.") for x in crowdsec.get("labels", []))


def test_appsec_profile_is_separate_and_credentials_aligned():
    middlewares = yaml.safe_load(MIDDLEWARE.read_text(encoding="utf-8"))["http"]["middlewares"]
    regular = middlewares["crowdsec"]["plugin"]["bouncer"]
    appsec = middlewares["crowdsec-appsec"]["plugin"]["bouncer"]
    for shared in (
        "enabled", "crowdsecMode", "updateIntervalSeconds", "updateMaxFailure",
        "streamStartupBlock", "httpTimeoutSeconds", "crowdsecLapiScheme",
        "crowdsecLapiHost", "crowdsecLapiKey",
    ):
        assert regular[shared] == appsec[shared]
    assert appsec["crowdsecMode"] == "stream"
    assert appsec["crowdsecAppsecEnabled"] is True
    assert appsec["crowdsecAppsecScheme"] == "http"
    assert appsec["crowdsecAppsecHost"] == "crowdsec:7422"
    assert appsec["crowdsecAppsecFailureBlock"] is True
    assert appsec["crowdsecAppsecUnreachableBlock"] is True
    assert appsec["crowdsecAppsecUnreadableBodyBlock"] is True
    assert appsec["crowdsecLapiKey"] == '{{ env "CROWDSEC_BOUNCER_LAPI_KEY" }}'
    assert "crowdsecAppsecEnabled" not in regular
    assert "appsec" not in str(regular.get("crowdsecMode", "")).lower()


def test_appsec_only_on_public_fastapi_canary_without_tunnel_cutover():
    sample = yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))["services"]["fastapi-sample"]
    labels = {x.split("=", 1)[0]: x.split("=", 1)[1] for x in sample["labels"] if "=" in x}
    assert labels["traefik.http.routers.fastapi-sample-public.middlewares"].startswith("crowdsec-appsec@file,")
    assert labels["traefik.http.routers.fastapi-sample-hook.middlewares"].startswith("crowdsec-appsec@file,")
    assert "crowdsec" not in labels.get("traefik.http.routers.fastapi-sample.middlewares", "")
    assert labels["traefik.http.routers.fastapi-sample.rule"] == "Host(`sample.int.albandrieu.com`)"
    tunnel = TUNNEL.read_text(encoding="utf-8")
    assert 'service = var.fastapi_sample_tunnel_via_traefik ? "https://traefik:443" : "http://172.17.0.24:8091"' in tunnel
    # Per-field ternaries: the direct :8091 route keeps null TLS name and Host header.
    assert 'origin_server_name = var.fastapi_sample_tunnel_via_traefik ? "sample.int.albandrieu.com" : null' in tunnel
    assert 'http_host_header   = var.fastapi_sample_tunnel_via_traefik ? "fastapi-sample.albandrieu.com" : null' in tunnel
    variables = (ROOT / "terraform/cloudflare/variables.tofu").read_text(encoding="utf-8")
    assert 'variable "fastapi_sample_tunnel_via_traefik"' in variables
    assert "default     = false" in variables.split('variable "fastapi_sample_tunnel_via_traefik"', 1)[1]



def test_appsec_canary_rule_blocks_only_one_get_path():
    rule = yaml.safe_load(
        (ROOT / "apps/crowdsec/appsec-rules/nabla/fastapi-canary.yaml").read_text(encoding="utf-8")
    )
    config = yaml.safe_load(
        (ROOT / "apps/crowdsec/appsec-configs/nabla/fastapi-canary.yaml").read_text(encoding="utf-8")
    )
    assert rule["name"] == config["name"] == "nabla/fastapi-canary"
    assert config["inband_rules"] == ["nabla/fastapi-canary"]
    assert config["default_remediation"] == "ban"
    conditions = rule["rules"]
    assert len(conditions) == 1
    exact = conditions[0]["and"]
    assert len(exact) == 2
    assert exact[0] == {"zones": ["METHOD"], "match": {"type": "equals", "value": "GET"}}
    assert exact[1] == {
        "zones": ["URI"],
        "match": {"type": "equals", "value": "/__nabla_appsec_canary_7de17a3fb1134292"},
    }
    assert "HEADERS" not in str(rule)
    assert "BODY" not in str(rule)
