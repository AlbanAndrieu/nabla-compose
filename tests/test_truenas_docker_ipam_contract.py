from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POOL_CHECK = ROOT / "scripts/truenas/check-docker-address-pool.py"


class TrueNASDockerIPAMContractTests(unittest.TestCase):
    def test_migration_target_and_post_reboot_gate_are_explicit(self) -> None:
        script = (ROOT / "scripts/truenas/migrate-docker-address-pool.sh").read_text()

        self.assertIn("10.200.0.0/16", script)
        self.assertIn("--post-reboot-check", script)
        self.assertIn("docker.config persists target IPv4 pool", script)
        self.assertIn("Docker service and TrueNAS middleware agree on RUNNING", script)
        self.assertIn("EXPECTED_BR0_CIDR", script)
        self.assertIn("sample-observer", script)
        self.assertIn("Docker bridge allocation", script)

    def test_migration_check_is_idempotent_after_target_allocation(self) -> None:
        script = (ROOT / "scripts/truenas/migrate-docker-address-pool.sh").read_text()
        helper = POOL_CHECK.read_text()

        self.assertIn('"${SCRIPT_DIR}/check-docker-address-pool.py"', script)
        self.assertIn("current_target", script + helper)
        self.assertIn("backed_by_docker", helper)
        self.assertIn("existing Docker allocations inside the configured target pool are expected", helper)
        self.assertIn("non-Docker TrueNAS route", helper)

    def _check_pool(self, routes: list, networks: list, current_target: bool) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory() as temp:
            routes_file = Path(temp) / "routes.json"
            networks_file = Path(temp) / "networks.json"
            routes_file.write_text(json.dumps(routes))
            networks_file.write_text(json.dumps(networks))
            return subprocess.run(
                [sys.executable, str(POOL_CHECK), "10.200.0.0/16", "24", "172.17.0.0/24 10.20.0.0/24",
                 str(routes_file), str(networks_file), str(current_target).lower()],
                text=True, capture_output=True, check=False,
            )

    def test_pool_check_accepts_disjoint_target(self) -> None:
        result = self._check_pool([{"dst": "default"}, {"dst": "172.17.0.0/24", "dev": "br0"}], [], False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK: target provides 256 possible /24 Docker network allocations", result.stdout)

    def test_pool_check_rejects_docker_overlap_before_migration(self) -> None:
        networks = [{"Name": "legacy", "IPAM": {"Config": [{"Subnet": "10.200.3.0/24"}]}}]
        result = self._check_pool([], networks, False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target overlaps existing Docker network(s): legacy=10.200.3.0/24", result.stderr)

    def test_pool_check_is_idempotent_and_ignores_ipv6_after_migration(self) -> None:
        networks = [{"Name": "app", "IPAM": {"Config": [{"Subnet": "10.200.3.0/24"}, {"Subnet": "fdd0::/64"}]}}]
        routes = [{"dst": "10.200.3.0/24", "dev": "br-1234"}]
        result = self._check_pool(routes, networks, True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("existing Docker allocations inside the configured target pool are expected", result.stdout)

    def test_pool_check_rejects_non_docker_route(self) -> None:
        result = self._check_pool([{"dst": "10.200.9.0/24", "dev": "eth1"}], [], True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-Docker TrueNAS route(s): 10.200.9.0/24 dev=eth1", result.stderr)

    def test_network_audit_is_read_only_and_protects_shared_networks(self) -> None:
        script = (
            ROOT / "scripts/truenas/audit-docker-network-migration.sh"
        ).read_text()

        self.assertIn("protected-shared", script)
        self.assertIn("intranet", script)
        self.assertIn("traefik_network", script)
        self.assertIn("sample-observer", script)
        self.assertIn("nabla-security", script)
        self.assertIn("secrets-backend", script)
        self.assertIn("legacy-active", script)
        self.assertIn("legacy-empty", script)
        self.assertIn("ENDPOINT_NAMES", script)
        self.assertIn("CLEANUP_GATE", script)
        self.assertIn("blocked-protected", script)
        self.assertIn("blocked-live-endpoints", script)
        self.assertIn("owner-review-required", script)
        self.assertIn('item.get("Containers") or {}', script)
        self.assertIn('com.docker.compose.project', script)
        self.assertIn("never authorizes deletion", script)
        self.assertNotIn("docker network prune", script)
        self.assertNotIn("docker network rm", script)

    def test_shell_scripts_pass_bash_syntax(self) -> None:
        for relative in (
            "scripts/truenas/migrate-docker-address-pool.sh",
            "scripts/truenas/audit-docker-network-migration.sh",
        ):
            result = subprocess.run(
                ["bash", "-n", str(ROOT / relative)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{relative}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
