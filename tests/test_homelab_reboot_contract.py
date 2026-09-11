from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "scripts/truenas/plan-app-lifecycle-order.py"
REBOOT = ROOT / "scripts/truenas/reboot-homelab.sh"
RUNBOOK = ROOT / "docs/homelab-reboot-runbook.md"
VM_POLICY = ROOT / "scripts/truenas/reconcile-talos-vm-policy.sh"
IPAM = ROOT / "scripts/truenas/migrate-docker-address-pool.sh"
APP_RECONCILE = ROOT / "scripts/truenas/reconcile-apps-after-ipam.sh"


class HomelabRebootContractTests(unittest.TestCase):
    def test_shell_helpers_pass_bash_syntax(self) -> None:
        for path in (REBOOT, VM_POLICY, IPAM, APP_RECONCILE):
            result = subprocess.run(
                ["bash", "-n", str(path)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")

    def test_ipam_check_filters_address_families(self) -> None:
        text = IPAM.read_text(encoding="utf-8")
        self.assertIn("if network.version != target.version:", text)
        self.assertIn("--post-reboot-check", text)
        self.assertIn("10.200.0.0/16", text)

    def test_talos_policy_is_autostart_and_graceful(self) -> None:
        vars_text = (ROOT / "terraform/truenas/variables.tofu").read_text()
        vm_text = (ROOT / "terraform/truenas/talos-vms.tofu").read_text()
        helper = VM_POLICY.read_text()
        self.assertIn('variable "talos_vm_autostart"', vars_text)
        self.assertIn('variable "talos_vm_shutdown_timeout"', vars_text)
        self.assertIn("default     = 180", vars_text)
        self.assertIn(
            "shutdown_timeout      = var.talos_vm_shutdown_timeout",
            vm_text,
        )
        self.assertIn("autostart             = var.talos_vm_autostart", vm_text)
        self.assertIn("midclt call vm.update", helper)
        self.assertNotIn("vm.poweroff", helper)

    def test_reboot_orchestrator_avoids_forced_shutdown_and_prune(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("app.stop", text)
        self.assertIn("app.start", text)
        self.assertIn("--post-reboot-check", text)
        self.assertIn("NABLA_REBOOT_RESUME_STOPPED_APPS", text)
        self.assertNotIn("docker network prune", text)
        self.assertNotIn("vm.poweroff", text)
        self.assertNotIn("shutdown --force", text)

    def test_talos_calls_use_explicit_control_plane_endpoint(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn(
            'TALOS_ENDPOINT="${NABLA_TALOS_ENDPOINT:-172.17.0.50}"',
            text,
        )
        self.assertIn('--endpoints "${TALOS_ENDPOINT}"', text)
        self.assertIn(
            "Talos API %s failed target=%s endpoint=%s",
            text,
        )
        self.assertNotIn('version --nodes "${node}" >/dev/null', text)

    def test_runbook_does_not_promote_preexisting_crashed_apps(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn('$before_state == "RUNNING"', text)
        self.assertIn('$before_state == "DEPLOYING"', text)
        self.assertIn("CRASHED -> STOPPED", text)

    def test_app_reconcile_network_detail_is_best_effort(self) -> None:
        text = APP_RECONCILE.read_text(encoding="utf-8")
        self.assertIn(
            "app.get_instance timed out/unavailable; network detail skipped",
            text,
        )
        self.assertIn("TRUENAS_APP_RECONCILE_CALL_TIMEOUT", text)

    def test_planner_orders_dependency_and_reverses_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            apps = [
                {"id": "postgres", "state": "RUNNING"},
                {"id": "n8n", "state": "RUNNING"},
                {"id": "disabled", "state": "STOPPED"},
                {"id": "unmapped", "state": "RUNNING"},
            ]
            services = {
                "services": [
                    {
                        "id": "postgres",
                        "runtime": {
                            "provider": "truenas-app",
                            "appId": "postgres",
                        },
                    },
                    {
                        "id": "n8n",
                        "runtime": {
                            "provider": "truenas-app",
                            "appId": "n8n",
                        },
                    },
                ]
            }
            topology = {
                "relations": [
                    {
                        "source": "n8n",
                        "target": "postgres",
                        "type": "dependsOn",
                        "strength": "required",
                        "evidence": ["test"],
                    }
                ]
            }
            for name, payload in (
                ("apps.json", apps),
                ("services.json", services),
                ("topology.json", topology),
            ):
                (tmp_path / name).write_text(json.dumps(payload))

            result = subprocess.run(
                [
                    "python3",
                    str(PLANNER),
                    "--apps",
                    str(tmp_path / "apps.json"),
                    "--services",
                    str(tmp_path / "services.json"),
                    "--topology",
                    str(tmp_path / "topology.json"),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertLess(
                plan["start_order"].index("postgres"),
                plan["start_order"].index("n8n"),
            )
            self.assertLess(
                plan["stop_order"].index("n8n"),
                plan["stop_order"].index("postgres"),
            )
            self.assertNotIn("disabled", plan["selected_apps"])
            self.assertEqual(["unmapped"], plan["unmapped_apps"])


if __name__ == "__main__":
    unittest.main()
