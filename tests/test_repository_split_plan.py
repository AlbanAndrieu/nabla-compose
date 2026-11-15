"""Offline, no-Git contract for migration planner categories."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE=Path(__file__).resolve().parents[1]/"scripts/ops/plan-repository-split.py"
s=importlib.util.spec_from_file_location("repo_split",FILE)
mod=importlib.util.module_from_spec(s)
s.loader.exec_module(mod)

class PlanTests(unittest.TestCase):
    def test_excluded_secret_and_server_paths(self):
        self.assertEqual(mod.classify("secrets.env.sops"),"excluded_secret_or_crypto_policy")
        self.assertEqual(mod.classify("apps/litellm/config.yaml"),"retain_compose_server")
        self.assertEqual(mod.classify("scripts/truenas/smoke-yubikey.py"),"retain_compose_server")

    def test_candidate_paths_do_not_auto_migrate(self):
        self.assertEqual(mod.classify("scripts/workstation/inspect-yubikey-readonly.py"),"candidate_yubikey_review")
        self.assertEqual(mod.classify("ops/openclaw-workstation/runtime-contract.json"),"candidate_openclaw_target_review")
        self.assertEqual(mod.classify("scripts/workstation/diagnose-openclaw.sh"),"candidate_openclaw_target_review")
        self.assertEqual(mod.classify("apps/openclaw/compose.yml"),"retain_compose_service")

    def test_pfsense_and_crosshost_scripts_need_owner_review(self):
        self.assertEqual(
            mod.classify("scripts/pfsense/diagnose-recover.sh"),
            "candidate_pfsense_target_review",
        )
        self.assertEqual(
            mod.classify("scripts/workstation/observe-crowdsec-pf-decision.py"),
            "candidate_crosshost_boundary_review",
        )
        self.assertEqual(
            mod.classify("scripts/workstation/preflight-truenas-litellm-openclaw.py"),
            "candidate_openclaw_target_review",
        )
        self.assertEqual(
            mod.classify("scripts/workstation/repair-user-toolchain.sh"),
            "candidate_ansible_workstation_review",
        )

    def test_summary_never_authorizes_copy(self):
        report=mod.summarize(["apps/litellm/config.yaml","scripts/workstation/inspect-yubikey.py"],
                             "yubikey-test:\n    echo test\n\nopenclaw-plan:\n    echo plan\n")
        self.assertFalse(report["copy_or_delete_authorized"])
        self.assertEqual(report["destination_access"],"not_checked_offline")
        self.assertEqual(len(report["declared_destination_repos"]),3)
        self.assertEqual(report["proposed_pfsense_repository"], "AlbanAndrieu/nabla-pfsense")
        self.assertEqual(report["submodule_policy"], "only_when_consumed_as_pinned_runtime_dependency")
        self.assertIn("rollback", report["extraction_preconditions"])
        self.assertEqual(report["recipe_groups"]["total"],2)
        self.assertEqual(report["recipe_groups"]["yubikey"],1)
        self.assertEqual(report["candidate_groups"]["candidate_yubikey_review"],1)


    def test_openclaw_reference_inventory_is_read_only_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            documents = {
                "justfile": "check:\n    python3 scripts/workstation/check-openclaw-runtime-alignment.py\n",
                "ops/openclaw-workstation/systemd/30.conf.example": (
                    "ExecStartPre=check-openclaw-runtime-alignment.py\n"
                ),
                "docs/.env.secrets": "SECRET=do-not-emit check-openclaw-runtime-alignment.py",
                "docs/large.md": "check-openclaw-runtime-alignment.py" * 30000,
                "scripts/workstation/check-openclaw-runtime-alignment.py": "private source",
            }
            for name, content in documents.items():
                candidate = root / name
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(content, encoding="utf-8")
            result = mod.openclaw_consumer_inventory(root, list(documents))
            self.assertEqual(result["schema"], "nabla-openclaw-consumers/v1")
            self.assertFalse(result["removal_authorized"])
            self.assertEqual(result["submodule_parity"], "NOT_VERIFIED")
            self.assertEqual(result["skipped_files"], 1)
            record = result["scripts"][0]
            self.assertTrue(record["compose_tracked"])
            self.assertEqual(record["reference_files"], 2)
            self.assertEqual(
                {ref["kind"] for ref in record["references"]},
                {"recipe", "systemd"},
            )
            self.assertNotIn("do-not-emit", json.dumps(result))
            self.assertEqual((root / "justfile").read_text(encoding="utf-8"), documents["justfile"])

    def test_reference_inventory_does_not_infer_missing_submodule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "tests/test_consumers.py"
            source.parent.mkdir()
            source.write_text("openclaw-heartbeat-gitops.py", encoding="utf-8")
            result = mod.openclaw_consumer_inventory(
                root, ["tests/test_consumers.py", "docs/missing.md"]
            )
            self.assertFalse(result["scripts"][2]["compose_tracked"])
            self.assertEqual(result["scripts"][2]["reference_files"], 1)
            self.assertEqual(result["skipped_files"], 1)


    def test_external_symlink_cannot_be_read_as_consumer(self):
        with tempfile.TemporaryDirectory() as directory, \
                tempfile.TemporaryDirectory() as outside_directory:
            root = Path(directory)
            secret = Path(outside_directory) / "secret.md"
            secret.write_text(
                "SECRET=outside-data check-openclaw-runtime-alignment.py",
                encoding="utf-8",
            )
            link = root / "docs/outside.md"
            link.parent.mkdir(parents=True)
            link.symlink_to(secret)
            result = mod.openclaw_consumer_inventory(
                root, ["docs/outside.md"]
            )
            self.assertEqual(result["skipped_files"], 1)
            self.assertEqual(result["scripts"][0]["reference_files"], 0)
            self.assertNotIn("outside-data", json.dumps(result))


    def test_openclaw_cli_contract_reports_flag_drift_without_executing(self):
        with tempfile.TemporaryDirectory() as compose, tempfile.TemporaryDirectory() as openclaw:
            name = mod.SHARED_OPENCLAW_SCRIPTS[0]
            for root, value in ((compose, "--check"), (openclaw, "--apply")):
                path = Path(root) / "scripts/workstation" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'p.add_argument("{value}")\n', encoding="utf-8")
            report = mod.compare_openclaw_cli_contracts(Path(compose), Path(openclaw))
            record = report["scripts"][0]
            self.assertFalse(record["static_options_equal"])
            self.assertFalse(record["source_identical"])
            self.assertEqual(report["behavioral_parity"], "NOT_VERIFIED")
            self.assertFalse(report["removal_authorized"])

    def test_matching_options_do_not_claim_behavioral_parity(self):
        with tempfile.TemporaryDirectory() as compose, tempfile.TemporaryDirectory() as openclaw:
            name = mod.SHARED_OPENCLAW_SCRIPTS[0]
            for root, value in ((compose, "print(1)"), (openclaw, "print(2)")):
                path = Path(root) / "scripts/workstation" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('p.add_argument("--check")\n' + value + "\n", encoding="utf-8")
            record = mod.compare_openclaw_cli_contracts(Path(compose), Path(openclaw))["scripts"][0]
            self.assertTrue(record["static_options_equal"])
            self.assertFalse(record["source_identical"])

    def test_cli_contract_rejects_symlinks_and_missing_sources(self):
        with (tempfile.TemporaryDirectory() as compose,
              tempfile.TemporaryDirectory() as openclaw,
              tempfile.TemporaryDirectory() as outside):
            name = mod.SHARED_OPENCLAW_SCRIPTS[0]
            private = Path(outside) / "secret.py"
            private.write_text('SECRET = "do-not-emit"\n', encoding="utf-8")
            link = Path(openclaw) / "scripts/workstation" / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(private)
            report = mod.compare_openclaw_cli_contracts(Path(compose), Path(openclaw))
            record = report["scripts"][0]
            self.assertIsNone(record["source_identical"])
            self.assertIsNone(record["static_options_equal"])
            self.assertEqual(record["openclaw"]["status"], "UNREADABLE")
            self.assertNotIn("do-not-emit", json.dumps(report))


    def test_static_option_semantics_drift_is_not_silent(self):
        with tempfile.TemporaryDirectory() as compose, tempfile.TemporaryDirectory() as openclaw:
            name = mod.SHARED_OPENCLAW_SCRIPTS[0]
            for root, action in ((compose, "store_true"), (openclaw, "store_false")):
                source = Path(root) / "scripts/workstation" / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(
                    'parser.add_argument("--check", action="' + action + '")\\n',
                    encoding="utf-8",
                )
            report = mod.compare_openclaw_cli_contracts(Path(compose), Path(openclaw))
            row = report["scripts"][0]
            self.assertTrue(row["static_options_equal"])
            self.assertFalse(row["static_option_shapes_equal"])
            self.assertEqual(row["compose"]["option_shapes"][0]["semantics"]["action"], "store_true")
            self.assertEqual(row["openclaw"]["option_shapes"][0]["semantics"]["action"], "store_false")
            self.assertEqual(report["behavioral_parity"], "NOT_VERIFIED")

    def test_static_type_and_required_drift(self):
        with tempfile.TemporaryDirectory() as compose, tempfile.TemporaryDirectory() as openclaw:
            name = mod.SHARED_OPENCLAW_SCRIPTS[0]
            for root, typed, required in ((compose, "int", "True"), (openclaw, "str", "False")):
                source = Path(root) / "scripts/workstation" / name
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text(
                    'parser.add_argument("--top", type=' + typed +
                    ', required=' + required + ')\\n',
                    encoding="utf-8",
                )
            row = mod.compare_openclaw_cli_contracts(Path(compose), Path(openclaw))["scripts"][0]
            self.assertTrue(row["static_options_equal"])
            self.assertFalse(row["static_option_shapes_equal"])

    def test_no_sensitive_defaults_or_help_in_cli_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            name = mod.SHARED_OPENCLAW_SCRIPTS[0]
            source = root / "scripts/workstation" / name
            source.parent.mkdir(parents=True)
            source.write_text(
                'parser.add_argument("--token", default="private-secret", help="private-detail")\\n',
                encoding="utf-8",
            )
            report = mod._cli_snapshot(root, name)
            self.assertEqual(report["status"], "READ")
            self.assertNotIn("private-secret", json.dumps(report))
            self.assertNotIn("private-detail", json.dumps(report))
            self.assertEqual(report["option_shapes"][0]["flags"], ["--token"])

if __name__=="__main__":
    unittest.main()
