"""Offline contract: Nexus private ingress is opt-in and LAN-only."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "apps/nexus/compose.yml"
RUNBOOK = ROOT / "docs/runbooks/nexus-private-dns-ingress.md"


class NexusPrivateIngressContract(unittest.TestCase):
    def test_private_router_remains_opt_in_and_explicit(self):
        text = COMPOSE.read_text(encoding="utf-8")
        self.assertIn('traefik.enable: "${NEXUS_PRIVATE_INGRESS_ENABLED:-false}"', text)
        self.assertIn('Host(`nexus.int.albandrieu.com`)', text)
        self.assertIn("traefik.http.routers.nexus-private.entrypoints: websecure", text)
        self.assertIn("traefik.http.routers.nexus-private.service: nexus-private", text)
        self.assertIn('traefik.http.services.nexus-private.loadbalancer.server.port: "8081"', text)
        self.assertIn("traefik.http.services.nexus-private.loadbalancer.server.scheme: http", text)
        self.assertIn("traefik.docker.network: traefik_network", text)
        self.assertIn('networks: ["traefik_network"]', text)
        self.assertNotIn("Host(`nexus.albandrieu.com`)", text)

    def test_readonly_runbook_never_bypasses_tls_or_exposes_public_int(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("dig +tries=1 +time=2 @172.17.0.24", text)
        self.assertIn("dig +tries=1 +time=2 @172.17.0.1", text)
        self.assertIn("--resolve nexus.int.albandrieu.com:443:172.17.0.24", text)
        self.assertIn("NEXUS_PRIVATE_INGRESS_ENABLED=false", text)
        self.assertNotIn("curl -k", text)
        self.assertNotIn("midclt call -j app.redeploy", text)


    def test_real_wan_acl_is_not_inferred_from_hairpin_404(self):
        runbook = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("WAN_REJECTION_NOT_VERIFIED", runbook)
        self.assertIn("nexus-albandrieu.int.albandrieu.com", runbook)
        self.assertIn("nexus.int.albandrieu.com", runbook)
        self.assertIn("Gate 9 — HAProxy réel", runbook)
        self.assertIn("http-request deny deny_status 403", runbook)
        self.assertIn("s3.int.albandrieu.com", runbook)
        self.assertIn("Traefik", runbook)

    def test_timeout_is_transport_unknown_not_missing_nexus_record(self):
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("Gate 0 — transport LAN avant DNS et Nexus", text)
        self.assertIn("LAN_TRANSPORT_UNVERIFIED", text)
        self.assertIn("ip -4 route get 172.17.0.1", text)
        self.assertIn("ip -4 route get 172.17.0.24", text)
        self.assertIn('nc -z -v -w 2 "$host" "$port"', text)
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
