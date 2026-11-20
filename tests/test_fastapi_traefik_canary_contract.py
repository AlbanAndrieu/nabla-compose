"""Offline contract: a staged Traefik canary cannot silently cut over Tunnel."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FastapiTraefikCanaryContract(unittest.TestCase):
    def test_public_router_reuses_existing_crowdsec_and_ratelimit(self):
        app = (ROOT / "apps/sample/compose.yml").read_text(encoding="utf-8")
        traefik = (ROOT / "apps/traefik/dynamic/crowdsec.yml").read_text(encoding="utf-8")
        assert "middlewares=crowdsec@file,fastapi-sample-public-rate" in app
        assert "middlewares=crowdsec@file,fastapi-sample-hook-rate" in app
        assert "ratelimit.average=30" in app
        assert "ratelimit.burst=100" in app
        assert "ratelimit.average=2" in app
        assert "ratelimit.burst=10" in app
        assert "Path(`/webhooks/github`) && Method(`POST`)" in app
        assert 'traefik.http.routers.fastapi-sample.rule=Host(`sample.int.albandrieu.com`)' in app
        assert "crowdsec:" in traefik and "crowdsecMode: stream" in traefik

    def test_tunnel_stays_direct_by_default_and_tls_verification_is_not_skipped(self):
        tunnel = (ROOT / "terraform/cloudflare/tunnel.tofu").read_text(encoding="utf-8")
        vars = (ROOT / "terraform/cloudflare/variables.tofu").read_text(encoding="utf-8")
        assert 'variable "fastapi_sample_tunnel_via_traefik"' in vars
        assert "default     = false" in vars.split('variable "fastapi_sample_tunnel_via_traefik"', 1)[1]
        assert 'var.fastapi_sample_tunnel_via_traefik ? "https://172.17.0.24:443" : "http://172.17.0.24:8091"' in tunnel
        assert 'origin_server_name = var.fastapi_sample_tunnel_via_traefik ? "sample.int.albandrieu.com" : null' in tunnel
        assert 'http_host_header   = var.fastapi_sample_tunnel_via_traefik ? "fastapi-sample.albandrieu.com" : null' in tunnel
        assert "no_tls_verify = true" not in tunnel.split('hostname = "fastapi-sample.albandrieu.com"',1)[1].split("},",1)[0]


if __name__ == "__main__":
    unittest.main()
