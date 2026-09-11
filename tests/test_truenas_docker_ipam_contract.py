from __future__ import annotations

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


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

        self.assertIn("current_target", script)
        self.assertIn("backed_by_docker", script)
        self.assertIn("existing Docker allocations inside the configured target pool are expected", script)
        self.assertIn("non-Docker TrueNAS route", script)

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
