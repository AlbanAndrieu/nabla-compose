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
ORPHAN_SHIMS = ROOT / "scripts/truenas/diagnose-docker-orphan-shims.sh"
DOCKER_LIB = ROOT / "scripts/lib/docker.sh"


class HomelabRebootContractTests(unittest.TestCase):
    def test_shell_helpers_pass_bash_syntax(self) -> None:
        for path in (REBOOT, VM_POLICY, IPAM, APP_RECONCILE, ORPHAN_SHIMS, DOCKER_LIB):
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

    def test_system_ready_is_case_normalized(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("truenas_ready()", text)
        self.assertIn("tr '[:upper:]' '[:lower:]'", text)
        self.assertNotIn(
            '[[ "$(midclt_bounded system.ready)" == "true" ]]',
            text,
        )

    def test_prepare_is_resumable_without_recapturing_manifest(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("--continue-prepare", text)
        self.assertIn("PREPARING", text)
        self.assertIn("guard_no_incomplete_prepare", text)
        self.assertIn("continue_prepare()", text)
        self.assertIn("never rerun --prepare", text)
        self.assertIn("Continuing preserved reboot manifest", text)

    def test_continue_prepare_reports_saved_explicit_resume_set(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn('[[ -f "${dir}/explicit-resume.txt" ]]', text)
        self.assertIn("mapfile -t saved_explicit_resume", text)
        self.assertIn('explicit_resume="${saved_explicit_resume[*]}"', text)

    def test_interrupted_prepare_fixture_keeps_frozen_resume_membership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            services = {
                "services": [
                    {
                        "id": "postgres",
                        "runtime": {"provider": "truenas-app", "appId": "postgres"},
                    },
                    {
                        "id": "n8n",
                        "runtime": {"provider": "truenas-app", "appId": "n8n"},
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
                    }
                ]
            }
            frozen_apps = [
                {"id": "postgres", "state": "RUNNING"},
                {"id": "n8n", "state": "RUNNING"},
            ]
            partially_stopped_apps = [
                {"id": "postgres", "state": "STOPPED"},
                {"id": "n8n", "state": "RUNNING"},
            ]

            (root / "services.json").write_text(
                json.dumps(services), encoding="utf-8"
            )
            (root / "topology.json").write_text(
                json.dumps(topology), encoding="utf-8"
            )

            def selected_apps(name: str, apps: list[dict[str, str]]) -> list[str]:
                path = root / name
                path.write_text(json.dumps(apps), encoding="utf-8")
                result = subprocess.run(
                    [
                        "python3",
                        str(PLANNER),
                        "--apps",
                        str(path),
                        "--states",
                        "RUNNING,DEPLOYING",
                        "--services",
                        str(root / "services.json"),
                        "--topology",
                        str(root / "topology.json"),
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)["selected_apps"]

            self.assertEqual(
                selected_apps("apps-before.json", frozen_apps),
                ["n8n", "postgres"],
            )
            self.assertEqual(
                selected_apps(
                    "runtime-after-partial-stop.json", partially_stopped_apps
                ),
                ["n8n"],
            )

        text = REBOOT.read_text(encoding="utf-8")
        start = text.index('if [[ "${MODE}" == --continue-prepare ]]')
        end = text.index('state_dir="$(latest_state_dir)"', start)
        continuation = text[start:end]
        self.assertIn('validate_prepare_manifest "${state_dir}"', continuation)
        self.assertIn('continue_prepare "${state_dir}"', continuation)
        self.assertNotIn("midclt_bounded app.query >", continuation)
        self.assertNotIn("make_plans ", continuation)

    def test_failed_app_stop_reports_probable_orphan_shim(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("diagnose_app_runtime", text)
        self.assertIn("probable orphaned containerd shim", text)
        self.assertIn("Running/Restarting but pid=0", text)
        self.assertIn("diagnose-docker-orphan-shims.sh", text)

    def test_operator_acceptance_is_a_strict_sidecar(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")

        self.assertIn("--accept-deferred", text)
        self.assertIn("NABLA_REBOOT_ACCEPTANCE_NOTE", text)
        self.assertIn("operator-acceptance.json", text)
        self.assertIn("not part of frozen resume membership", text)
        self.assertIn("annotations are immutable", text)
        self.assertIn("appsBeforeSha256", text)
        self.assertIn("resumePlanSha256", text)
        self.assertIn("resumeAppsSha256", text)
        self.assertIn('strictVerification: "unchanged"', text)
        self.assertIn(
            "strict --verify still evaluates every saved App",
            text,
        )
        self.assertIn(
            'NABLA_REBOOT_STATE_ROOT="${STATE_ROOT}" bash "${RESUME_RECONCILER}" --check',
            text,
        )

    def test_runbook_documents_deferred_operator_acceptance(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")

        self.assertIn("--accept-deferred", text)
        self.assertIn("operator-acceptance.json", text)
        self.assertIn("does not make `--verify` pass", text)
        self.assertIn("frozen `resume-apps.txt`", text)

    def test_orphan_shim_recovery_is_narrow(self) -> None:
        text = ORPHAN_SHIMS.read_text(encoding="utf-8")
        guard = DOCKER_LIB.read_text(encoding="utf-8")
        self.assertIn("--recover", text)
        self.assertIn("docker_orphan_shim_recovery_guard", text)
        self.assertIn('[[ "${pid}" == "0" ]]', guard)
        self.assertIn("expected exactly one containerd shim", guard)
        self.assertIn("docker update --restart=no", text)
        self.assertIn('kill -TERM "${shim_pid}"', text)
        self.assertIn('kill -KILL "${shim_pid}"', text)
        self.assertNotIn("docker kill", text)
        self.assertNotIn("pkill", text)
        self.assertNotIn("killall", text)
        self.assertNotIn("systemctl restart docker", text)
        self.assertNotIn("systemctl restart containerd", text)

    def test_orphan_shim_guard_fixture_fails_closed(self) -> None:
        def run_guard(
            running: str,
            restarting: str,
            pid: str,
            shim_count: str,
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        'source "$1"; '
                        'docker_orphan_shim_recovery_guard '
                        '"$2" "$3" "$4" "$5" test-container'
                    ),
                    "_",
                    str(DOCKER_LIB),
                    running,
                    restarting,
                    pid,
                    shim_count,
                ],
                text=True,
                capture_output=True,
                check=False,
            )

        safe = run_guard("true", "false", "0", "1")
        self.assertEqual(safe.returncode, 0, safe.stderr)

        live_pid = run_guard("true", "false", "42", "1")
        self.assertNotEqual(live_pid.returncode, 0)
        self.assertIn("live init PID 42 exists", live_pid.stderr)

        for shim_count in ("0", "2"):
            ambiguous_shim = run_guard("true", "false", "0", shim_count)
            self.assertNotEqual(ambiguous_shim.returncode, 0)
            self.assertIn("expected exactly one containerd shim", ambiguous_shim.stderr)

        not_ghost = run_guard("false", "false", "0", "1")
        self.assertNotEqual(not_ghost.returncode, 0)
        self.assertIn("not in a running/restarting ghost state", not_ghost.stderr)

    def test_runbook_does_not_promote_preexisting_crashed_apps(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("Safe default behavior preserves Apps that were already `STOPPED`", text)
        self.assertIn("CRASHED -> STOPPED", text)
        self.assertIn("must not be promoted into the healthy resume set", text)
        self.assertIn("resume-plan.json", text)

    def test_runbook_documents_partial_prepare_recovery(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("--continue-prepare", text)
        self.assertIn("Running=true", text)
        self.assertIn("Pid=0", text)
        self.assertIn("containerd-shim-runc-v2", text)
        self.assertIn("do not rerun `--prepare`", text)

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
