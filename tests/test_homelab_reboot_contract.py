from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "scripts/truenas/plan-app-lifecycle-order.py"
REBOOT = ROOT / "scripts/truenas/reboot-homelab.sh"
RUNBOOK = ROOT / "docs/homelab-reboot-runbook.md"
CATALOG = ROOT / "catalog/catalog-info.yaml"
STATIC_TOPOLOGY = ROOT / "catalog/service-topology.static.json"
VM_POLICY = ROOT / "scripts/truenas/reconcile-talos-vm-policy.sh"
IPAM = ROOT / "scripts/truenas/migrate-docker-address-pool.sh"
APP_RECONCILE = ROOT / "scripts/truenas/reconcile-apps-after-ipam.sh"
ORPHAN_SHIMS = ROOT / "scripts/truenas/diagnose-docker-orphan-shims.sh"
GHOST_RECOVERY = ROOT / "scripts/truenas/recover-app-after-docker-ghost.sh"
RECOVERY_REBOOT = ROOT / "scripts/truenas/recovery-reboot-homelab.sh"
DOCKER_LIB = ROOT / "scripts/lib/docker.sh"
DOCKER_STORAGE_AUDIT = ROOT / "scripts/truenas/audit-docker-storage-debt.sh"
REBOOT_ARCHIVE = ROOT / "scripts/truenas/archive-reboot-evidence.sh"


class HomelabRebootContractTests(unittest.TestCase):
    def test_truenas_pra_catalog_matches_reviewed_targets_and_evidence(self) -> None:
        with CATALOG.open(encoding="utf-8") as stream:
            entities = [
                document
                for document in yaml.safe_load_all(stream)
                if isinstance(document, dict)
            ]
        truenas = next(
            entity
            for entity in entities
            if entity.get("kind") == "Resource"
            and entity.get("metadata", {}).get("name") == "truenas"
        )
        annotations = truenas["metadata"]["annotations"]

        self.assertEqual(annotations["albandrieu.com/bia-mtpd"], "PT4H")
        self.assertEqual(annotations["albandrieu.com/bia-rto"], "PT1H")
        self.assertEqual(annotations["albandrieu.com/bia-rpo"], "PT1H")
        self.assertEqual(
            annotations["albandrieu.com/pra-status"],
            "tested-with-deviation",
        )
        self.assertEqual(
            annotations["albandrieu.com/pra-recovery-result"],
            "passed-after-manual-power-cycle",
        )
        self.assertEqual(
            annotations["albandrieu.com/pra-rto-result"],
            "target-breached",
        )
        self.assertEqual(
            annotations["albandrieu.com/pra-rpo-result"],
            "not-exercised",
        )
        self.assertEqual(
            annotations["albandrieu.com/pra-runbook"],
            "docs/homelab-reboot-runbook.md",
        )

    def test_runbook_documents_truenas_pra_targets_and_deviations(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")

        for expected in (
            "RTO | 1 hour",
            "RPO | 1 hour",
            "target breached",
            "not exercised",
            "passed-after-manual-power-cycle",
            "software reboot mechanism itself is accepted",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertRegex(
            text,
            r"selected recovery point no\s+older than one hour",
        )

    def test_cloudflared_has_explicit_truenas_runtime_mapping(self) -> None:
        topology = json.loads(STATIC_TOPOLOGY.read_text(encoding="utf-8"))
        cloudflared = next(
            node for node in topology["nodes"] if node.get("id") == "cloudflared"
        )

        self.assertEqual(
            cloudflared["runtime"],
            {"provider": "truenas-app", "appId": "cloudflared"},
        )
        self.assertEqual(
            cloudflared["lifecycle"],
            {"phase": "applications", "priority": 50},
        )

    def test_shell_helpers_pass_bash_syntax(self) -> None:
        for path in (
            REBOOT,
            VM_POLICY,
            IPAM,
            APP_RECONCILE,
            ORPHAN_SHIMS,
            GHOST_RECOVERY,
            RECOVERY_REBOOT,
            DOCKER_STORAGE_AUDIT,
            REBOOT_ARCHIVE,
            DOCKER_LIB,
        ):
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

    def test_post_reboot_waits_for_docker_initialization(self) -> None:
        text = IPAM.read_text(encoding="utf-8")
        self.assertIn("TRUENAS_DOCKER_POST_BOOT_WAIT_SECONDS", text)
        self.assertIn("TRUENAS_DOCKER_CLI_TIMEOUT_SECONDS", text)
        self.assertIn("wait_runtime_ready", text)
        self.assertIn("docker.status entered terminal state", text)
        self.assertIn("docker network ls timed out", text)
        self.assertIn("TRUENAS_DOCKER_POST_BOOT_HEARTBEAT_SECONDS", text)
        self.assertIn("764 images", text)
        self.assertIn("7408 overlay2 directories", text)
        self.assertIn("525 GiB", text)
        self.assertIn("No App is started by this wait", text)
        self.assertIn("elapsed=%ss", text)

    def test_reboot_preflight_captures_docker_storage_debt_before_shutdown(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        bundle = (
            ROOT / "scripts/truenas/materialize-reboot-bundle.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("NABLA_DOCKER_STORAGE_AUDIT", text)
        self.assertIn("docker_storage_debt_preflight", text)
        self.assertIn("docker-storage-debt-before.txt", text)
        self.assertIn("audit-docker-storage-debt.sh", bundle)

    def test_docker_storage_debt_audit_is_read_only(self) -> None:
        text = DOCKER_STORAGE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("--check", text)
        self.assertIn("--deep", text)
        self.assertIn("overlay2_dirs", text)
        self.assertIn("docker system df -v", text)
        self.assertIn("docker system prune", text)
        self.assertIn("docker network prune", text)
        self.assertIn("NABLA_DOCKER_AUDIT_WARN_OVERLAY_DIRS", text)
        self.assertIn("NABLA_DOCKER_AUDIT_WARN_IMAGES", text)
        self.assertIn("NABLA_DOCKER_AUDIT_WARN_USED_GIB", text)
        self.assertNotIn("docker image prune", text)
        self.assertNotIn("docker container prune", text)
        self.assertNotIn("docker builder prune", text)

    def test_post_reboot_waits_for_talos_autostart_and_kubernetes(self) -> None:
        recovery = RECOVERY_REBOOT.read_text(encoding="utf-8")
        normal = REBOOT.read_text(encoding="utf-8")
        self.assertIn("NABLA_RECOVERY_VM_WAIT_SECONDS", recovery)
        self.assertIn("NABLA_RECOVERY_TALOS_API_WAIT_SECONDS", recovery)
        self.assertIn("NABLA_RECOVERY_K8S_WAIT_SECONDS", recovery)
        self.assertIn("wait_talos_vms_running", recovery)
        self.assertIn("wait_talos_apis", recovery)
        self.assertIn("NABLA_REBOOT_VM_START_WAIT_SECONDS", normal)
        self.assertIn("wait_talos_vms_running", normal)

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

    def test_preflight_accepts_only_all_running_or_all_stopped_talos_vms(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("talos_vms_all_in_state STOPPED", text)
        self.assertIn("talos_vms_all_in_state RUNNING", text)
        self.assertIn("all Talos VMs are already STOPPED", text)
        self.assertIn("mixed/unexpected", text)
        self.assertIn("control plane is STOPPED while a worker is RUNNING", text)
        self.assertIn("supported TrueNAS vm.start API", text)
        self.assertIn("shutdown-only preparation", text)
        self.assertIn("unavailable-talOS-vms-preexisting-stopped", text)
        self.assertIn("SKIP Talos node %s VM=%s already STOPPED", text)

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
        end = text.index('\nfi\n\nstate_dir="$(latest_state_dir)"', start)
        continuation = text[start:end]
        self.assertIn('validate_prepare_manifest "${state_dir}"', continuation)
        self.assertIn('continue_prepare "${state_dir}"', continuation)
        self.assertNotIn("midclt_bounded app.query >", continuation)
        self.assertNotIn("make_plans ", continuation)

    def test_resume_temp_state_preserves_frozen_apps_snapshot(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        start = text.index("run_resume_reconciler()")
        end = text.index("\n}\n", start)
        block = text[start:end]

        self.assertIn(
            'cp "${dir}/apps-before.json" "${tmp_state}/apps-before.json"',
            block,
        )
        self.assertIn(
            'cp "${dir}/boot-id-before" "${tmp_state}/boot-id-before"',
            block,
        )
        self.assertIn(
            'cp "${effective}" "${tmp_state}/resume-plan.json"',
            block,
        )
        self.assertIn(
            'NABLA_REBOOT_STATE_ROOT="${tmp_root}"',
            block,
        )

    def test_resume_bundle_hotfix_is_explicit_and_auditable(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")

        self.assertIn("NABLA_REBOOT_ALLOW_BUNDLE_HOTFIX", text)
        self.assertIn("NABLA_REBOOT_HOTFIX_NOTE", text)
        self.assertIn("resume-bundle-hotfix.json", text)
        self.assertIn("preparedIdentity", text)
        self.assertIn("resumeIdentity", text)
        self.assertIn(
            'validate_or_record_resume_bundle_identity "${state_dir}"',
            text,
        )
        self.assertIn(
            "bundle identity changed since --prepare",
            text,
        )

    def test_failed_app_stop_reports_probable_orphan_shim(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("diagnose_app_runtime", text)
        self.assertIn("probable orphaned containerd shim", text)
        self.assertIn("Running/Restarting but pid=0", text)
        self.assertIn("diagnose-docker-orphan-shims.sh", text)

    def test_stale_reboot_manifest_fails_closed(self) -> None:
        reboot = REBOOT.read_text(encoding="utf-8")
        reconciler = (
            ROOT / "scripts/truenas/reconcile-reboot-resume.sh"
        ).read_text(encoding="utf-8")
        for text in (reboot, reconciler):
            self.assertIn("NABLA_REBOOT_MAX_MANIFEST_AGE_SECONDS", text)
            self.assertIn("172800", text)
            self.assertIn("stale reboot manifest", text)
            self.assertIn("apps-before.json", text)
            self.assertIn("stat -c %Y", text)

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

    def test_normal_reboot_can_auto_recover_exact_app_ghosts(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")
        self.assertIn("NABLA_REBOOT_AUTO_RECOVER_GHOSTS", text)
        self.assertIn("NABLA_APP_GHOST_RECOVERY_HELPER", text)
        self.assertIn("recover-app-after-docker-ghost.sh", text)
        self.assertIn("bounded App-scoped Docker ghost recovery", text)

    def test_recovery_reboot_transaction_is_fail_closed(self) -> None:
        text = RECOVERY_REBOOT.read_text(encoding="utf-8")
        for mode in (
            "--prepare",
            "--continue",
            "--status",
            "--reboot",
            "--post-reboot-check",
            "--resume-safe",
            "--resume-reviewed",
        ):
            self.assertIn(mode, text)
        self.assertIn("READY_TO_REBOOT", text)
        self.assertIn("resume-safe.txt", text)
        self.assertIn("resume-review.txt", text)
        self.assertIn("resume-approved.txt", text)
        self.assertIn("docker_zero_gate", text)
        self.assertIn("all_apps_stopped", text)
        self.assertIn("shutdown --wait", text)
        self.assertIn("172.17.0.51 172.17.0.52 172.17.0.50", text)
        self.assertNotIn("docker kill", text)
        self.assertNotIn("systemctl restart docker", text)
        self.assertNotIn("systemctl restart containerd", text)
        self.assertNotIn("shutdown --force", text)

    def test_bundle_contains_recovery_transaction_helpers(self) -> None:
        text = (ROOT / "scripts/truenas/materialize-reboot-bundle.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("recover-app-after-docker-ghost.sh", text)
        self.assertIn("recovery-reboot-homelab.sh", text)
        self.assertIn("READY_TO_REBOOT", text)

    def test_app_scoped_ghost_recovery_fails_closed(self) -> None:
        text = GHOST_RECOVERY.read_text(encoding="utf-8")
        self.assertIn("--recover-app", text)
        self.assertIn("NABLA_GHOST_RECOVERY_ALLOW_ACTIVE", text)
        self.assertIn("refuse active App recovery", text)
        self.assertIn("app.stop", text)
        self.assertIn("diagnose-docker-orphan-shims.sh", text)
        self.assertIn("ambiguous zero/multiple-shim ghosts", text)
        self.assertIn("no exact one-shim ghost is safely recoverable", text)
        self.assertIn("label=com.docker.compose.project=ix-", text)
        self.assertNotIn("systemctl restart docker", text)
        self.assertNotIn("systemctl restart containerd", text)
        self.assertNotIn("pkill", text)
        self.assertNotIn("killall", text)

    def test_runbook_documents_fast_post_reboot_ghost_recovery(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("Fast post-reboot ghost recovery procedure", text)
        self.assertIn("apps-before-cleanup.json", text)
        self.assertIn("resume-candidates.txt", text)
        self.assertIn("recover-app-after-docker-ghost.sh", text)
        self.assertIn("stop_order", text)

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
        self.assertIn("Normal pre-existing `STOPPED` Apps remain stopped.", text)
        self.assertIn(
            "Pre-existing `CRASHED`/`ERROR` Apps must not be promoted into the healthy",
            text,
        )
        self.assertIn("resume-plan.json", text)

    def test_runbook_documents_partial_prepare_recovery(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn("--continue-prepare", text)
        self.assertIn("Running=true", text)
        self.assertIn("Pid=0", text)
        self.assertIn("containerd-shim-runc-v2", text)
        self.assertIn("do not run a fresh `--prepare`", text)

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


    def test_successful_verify_persists_archive_gate(self) -> None:
        text = REBOOT.read_text(encoding="utf-8")

        self.assertIn('>"${state_dir}/boot-id-after"', text)
        self.assertIn("VERIFIED", text)
        self.assertIn(
            'record_prepare_history "${state_dir}" verified',
            text,
        )
        self.assertIn(
            "homelab reboot lifecycle acceptance passed. manifest=%s",
            text,
        )

    def test_reboot_evidence_archive_is_immutable_and_runtime_read_only(self) -> None:
        text = REBOOT_ARCHIVE.read_text(encoding="utf-8")
        bundle = (
            ROOT / "scripts/truenas/materialize-reboot-bundle.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("--check | --apply", text)
        self.assertIn("reboot transaction is not VERIFIED", text)
        self.assertIn("boot-id-before", text)
        self.assertIn("boot-id-after", text)
        self.assertIn("ARCHIVE-MANIFEST.json", text)
        self.assertIn("SHA256SUMS", text)
        self.assertIn("operator-acceptance.json", text)
        self.assertIn("resume-bundle-hotfix.json", text)
        self.assertIn("immutable Git source commit", text)
        self.assertIn("No reboot archive or recovery bundle was deleted", text)
        self.assertIn("archive-reboot-evidence.sh", bundle)
        self.assertNotIn("docker network prune", text)
        self.assertNotIn("zfs destroy", text)
        self.assertNotIn("midclt ", text)
        self.assertNotIn("kubectl ", text)
        self.assertNotIn("systemctl ", text)


if __name__ == "__main__":
    unittest.main()
