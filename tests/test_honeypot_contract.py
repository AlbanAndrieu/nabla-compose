"""Offline contract of the public Project Honey Pot App (login.albandrieu.com)."""
from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps/honeypot"


class HoneypotContract(unittest.TestCase):
    def test_only_the_docker_pool_may_set_the_reported_client_address(self):
        conf = (APP / "apache/honeypot.conf").read_text(encoding="utf-8")
        self.assertRegex(conf, r"(?m)^RemoteIPHeader CF-Connecting-IP$")
        # cloudflared reaches the App from the TrueNAS Docker pool; a LAN client
        # (172.17.0.0/24) must never be able to forge the address sent to Project Honey Pot.
        proxies = re.findall(r"(?m)^RemoteIP(?:Internal|Trusted)Proxy\s+(.+)$", conf)
        self.assertEqual(proxies, ["10.200.0.0/16", "172.16.56.0/24"])

    def test_public_route_stays_isolated_and_hardened(self):
        service = yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))["services"]["honeypot"]
        public = [r for r in service["x-nabla"]["exposure"] if r["visibility"] == "public"]
        self.assertEqual([r["hostnames"] for r in public], [["login.albandrieu.com"]])
        self.assertEqual(public[0]["riskAcceptance"]["status"], "accepted")
        # A probe on / would report the observer itself to Project Honey Pot.
        self.assertEqual(public[0]["probePath"], "/healthz")
        self.assertEqual(service["networks"], ["default", "traefik_network"])
        networks = yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))["networks"]
        self.assertTrue(networks["traefik_network"]["external"])
        self.assertTrue(service["read_only"])
        self.assertEqual(service["cap_drop"], ["ALL"])
        self.assertTrue(all(mount.endswith(":ro") for mount in service["volumes"]))


    def test_cloudflare_switch_and_dedicated_protected_router(self):
        compose = yaml.safe_load((APP / "compose.yml").read_text(encoding="utf-8"))
        service = compose["services"]["honeypot"]
        labels = service["labels"]
        assert labels["traefik.enable"] == "true"
        assert labels["traefik.docker.network"] == "traefik_network"
        assert labels["traefik.http.routers.honeypot-public.rule"] == "Host(`login.albandrieu.com`)"
        assert labels["traefik.http.middlewares.honeypot-tunnel-peer.ipallowlist.sourcerange"] == "10.200.2.0/24"
        for router in ("honeypot-public", "honeypot-login-attempt"):
            assert labels[f"traefik.http.routers.{router}.middlewares"].startswith(
                "honeypot-tunnel-peer,crowdsec-appsec@file,"
            )
            assert labels[f"traefik.http.routers.{router}.tls"] == "true"
        assert "Path(`/login`) && Method(`POST`)" in labels[
            "traefik.http.routers.honeypot-login-attempt.rule"
        ]
        assert labels["traefik.http.services.honeypot.loadbalancer.server.port"] == "8080"
        assert "./apache/static:/opt/honeypot/static:ro" in service["volumes"]
        tf = ROOT / "terraform/cloudflare"
        variables = (tf / "variables.tofu").read_text(encoding="utf-8")
        block = variables.split('variable "honeypot_tunnel_via_traefik" {', 1)[1]
        assert "default     = false" in block.split("}", 1)[0]
        tunnel = (tf / "tunnel.tofu").read_text(encoding="utf-8")
        fragment = tunnel.split('hostname = "login.albandrieu.com"', 1)[1].split("},", 1)[0]
        assert 'var.honeypot_tunnel_via_traefik ? "https://traefik:443" : "http://172.17.0.24:31090"' in fragment
        assert 'origin_server_name = var.honeypot_tunnel_via_traefik ? "traefik.int.albandrieu.com" : null' in fragment
        assert 'http_host_header   = var.honeypot_tunnel_via_traefik ? "login.albandrieu.com" : null' in fragment
        assert "no_tls_verify" not in fragment

    def test_decoy_never_submits_credentials_or_logs_query_strings(self):
        html = (APP / "apache/static/login.html").read_text(encoding="utf-8")
        assert '<form method="post" action="/login"' in html
        assert 'type="password"' in html
        assert 'name=' not in html.split("<form", 1)[1].split("</form>", 1)[0]
        assert "N'utilisez pas d'identifiants" in html
        conf = (APP / "apache/honeypot.conf").read_text(encoding="utf-8")
        assert 'Alias /login /opt/honeypot/static/login.html' in conf
        assert "<LimitExcept GET HEAD>" in conf
        assert "Require all denied" in conf
        assert "LogFormat \"%a %t %m %U %H %>s %b\" honeypot_metadata" in conf
        assert "CustomLog ${APACHE_LOG_DIR}/access.log combined" not in conf

    def test_login_burst_scenario_remains_explicitly_unmounted(self):
        scenario = yaml.safe_load(
            (ROOT / "apps/crowdsec/scenarios/nabla/honeypot-login-burst.yaml").read_text(encoding="utf-8")
        )
        assert scenario["name"] == "nabla/honeypot-login-burst"
        assert scenario["type"] == "leaky"
        assert scenario["capacity"] == 5
        assert "evt.Meta.http_verb == 'POST'" in scenario["filter"]
        assert "evt.Meta.http_path == '/login'" in scenario["filter"]
        assert "honeypot-login-attempt" in scenario["filter"]
        assert scenario["labels"]["remediation"] is True
        crowdsec = yaml.safe_load(
            (ROOT / "apps/crowdsec/compose.yml").read_text(encoding="utf-8")
        )["services"]["crowdsec"]
        assert not any("/scenarios/nabla" in str(mount) for mount in crowdsec["volumes"])


if __name__ == "__main__":
    unittest.main()
