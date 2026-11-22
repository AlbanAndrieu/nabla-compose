"""Offline contract: Nexus private ingress is opt-in and LAN-only."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps/nexus/compose.yml"
RUNBOOK = ROOT / "docs/runbooks/nexus-private-dns-ingress.md"


class NexusPrivateIngressContract(unittest.TestCase):
    def test_private_router_is_enabled_with_env_rollback(self):
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('traefik.enable: "${NEXUS_PRIVATE_INGRESS_ENABLED:-true}"', text)
        self.assertIn('Host(`nexus.int.albandrieu.com`)', text)
        self.assertIn("traefik.http.routers.nexus-private.entrypoints: websecure", text)
        self.assertIn("traefik.http.routers.nexus-private.service: nexus-private", text)
        self.assertIn("traefik.http.routers.nexus-private.middlewares: nexus-private-lan-only", text)
        self.assertIn('traefik.http.middlewares.nexus-private-lan-only.ipallowlist.sourcerange: "172.17.0.0/24,192.168.1.0/24"', text)
        self.assertNotIn("ipallowlist.ipstrategy.depth", text)
        self.assertNotIn("ipallowlist.ipstrategy.excludedips", text)
        self.assertIn('traefik.http.services.nexus-private.loadbalancer.server.port: "8081"', text)
        self.assertIn("traefik.http.services.nexus-private.loadbalancer.server.scheme: http", text)
        self.assertIn("traefik.docker.network: traefik_network", text)
        self.assertIn('networks: ["traefik_network"]', text)

    def test_public_router_is_crowdsec_bounced_and_tunnel_gated(self):
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('traefik.http.routers.nexus-public.rule: "Host(`nexus.albandrieu.com`)"', text)
        self.assertIn('traefik.http.routers.nexus-public.middlewares: crowdsec@file', text)
        self.assertIn('traefik.http.routers.nexus-public.tls: "true"', text)
        # The public router never carries the LAN allowlist: its socket peer is cloudflared.
        self.assertNotIn("nexus-public.middlewares: nexus-private-lan-only", text)
        tunnel = (ROOT / "terraform/cloudflare/tunnel.tofu").read_text(encoding="utf-8")
        self.assertIn('service = var.nexus_tunnel_via_traefik ? "https://traefik:443" : "http://172.17.0.24:8081"', tunnel)
        self.assertIn('origin_server_name = var.nexus_tunnel_via_traefik ? "nexus.int.albandrieu.com" : null', tunnel)
        variables = (ROOT / "terraform/cloudflare/variables.tofu").read_text(encoding="utf-8")
        block = variables.split('variable "nexus_tunnel_via_traefik"', 1)[1].split("}", 1)[0]
        self.assertIn("default     = true", block)

    def test_tofu_reaches_nexus_over_the_lan(self):
        hcl = (ROOT / "infrastructure/nexus/terragrunt.hcl").read_text(encoding="utf-8")
        self.assertIn('get_env("NEXUS_URL", "https://nexus.int.albandrieu.com")', hcl)

    def test_readonly_runbook_never_bypasses_tls_or_exposes_public_int(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("dig +tries=1 +time=2 @172.17.0.24", text)
        self.assertIn("R7000", text)
        self.assertIn("pfSense retiré", text)
        self.assertIn("certificat", text)
        self.assertIn("--resolve nexus.int.albandrieu.com:443:172.17.0.24", text)
        self.assertIn("NEXUS_PRIVATE_INGRESS_ENABLED=false", text)
        self.assertNotIn("curl -k", text)
        self.assertNotIn("midclt call -j app.redeploy", text)


    def test_real_wan_acl_is_not_inferred_from_hairpin_404(self):
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("WAN_REJECTION_NOT_VERIFIED", runbook)
        self.assertIn("nexus-albandrieu.int.albandrieu.com", runbook)
        self.assertIn("nexus.int.albandrieu.com", runbook)
        self.assertIn("test de refus WAN", runbook)
        self.assertIn("Source externe indépendante", runbook)
        self.assertIn("s3.int.albandrieu.com", runbook)
        self.assertIn("Traefik", runbook)

    def test_timeout_is_transport_unknown_not_missing_nexus_record(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("Gate 0 — transport LAN avant DNS et Nexus", text)
        self.assertIn("LAN_TRANSPORT_UNVERIFIED", text)
        self.assertIn("ip -4 route get 172.17.0.1", text)
        self.assertIn("ip -4 route get 172.17.0.24", text)
        self.assertIn("172.17.0.24:443", text)
        self.assertIn("ip neigh show to 172.17.0.24", text)
        self.assertIn("aucune négociation exploitable", text)
        self.assertIn("NXDOMAIN", text)
        self.assertIn("Suspendre", text)


    def test_just_recipe_fails_closed_if_module_missing(self):
        justfile = (ROOT / "justfile").read_text(encoding="utf-8")
        recipe = justfile.split("nexus-private-ingress-test:\n", 1)
        self.assertEqual(len(recipe), 2)
        commands = recipe[1].split("\n\n", 1)[0]
        self.assertIn("test -f tests/test_nexus_private_ingress_contract.py", commands)
        self.assertIn("python3 tests/test_nexus_private_ingress_contract.py -v", commands)
        self.assertNotIn("unittest discover", commands)



if __name__ == "__main__":
    unittest.main()
