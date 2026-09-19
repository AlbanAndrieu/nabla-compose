from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "scripts" / "secrets"
sys.path.insert(0, str(SECRETS))
MODULE = SECRETS / "import_dotenv_to_bitwarden.py"
SPEC = importlib.util.spec_from_file_location("import_dotenv_to_bitwarden_safe", MODULE)
assert SPEC and SPEC.loader
legacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(legacy)


class LegacySecretImportTests(unittest.TestCase):
    def test_dotenv_parser_does_not_execute_shell_syntax(self) -> None:
        parsed = legacy.parse_dotenv(
            "TOKEN='literal$(whoami)'\nPASSWORD=plain-value\n"
        )
        self.assertEqual(parsed["TOKEN"], "literal$(whoami)")
        self.assertEqual(parsed["PASSWORD"], "plain-value")

    def test_collect_values_uses_manifest_keys_without_process_env(self) -> None:
        spec = {
            "app": "demo",
            "secrets": [
                {
                    "env": "DEMO_PASSWORD",
                    "importEnv": "LEGACY_DEMO_PASSWORD",
                    "field": "DEMO_PASSWORD",
                }
            ],
        }
        values, supplied = legacy.collect_values(
            spec,
            {"DEMO_PASSWORD": "secret-value"},
        )
        self.assertEqual(values, {"DEMO_PASSWORD": "secret-value"})
        self.assertEqual(supplied, {"LEGACY_DEMO_PASSWORD"})

    @mock.patch.object(legacy.subprocess, "run")
    @mock.patch.object(legacy.Path, "is_file", side_effect=PermissionError)
    def test_root_file_read_tolerates_inaccessible_parent(
        self,
        _is_file: mock.Mock,
        run: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["sudo", "cat"],
            returncode=0,
            stdout="DEMO_PASSWORD=secret\n",
            stderr="",
        )

        value = legacy.read_root_bounded(
            Path("/mnt/cpool/secrets/runtime/demo/.env.secrets")
        )

        self.assertEqual(value, "DEMO_PASSWORD=secret\n")
        self.assertEqual(run.call_args.args[0][:3], ["sudo", "cat", "--"])

    @mock.patch.object(legacy.subprocess, "run")
    @mock.patch.object(legacy.os, "access", return_value=False)
    def test_root_file_read_strips_bw_session(
        self,
        _access: mock.Mock,
        run: mock.Mock,
    ) -> None:
        run.return_value = subprocess.CompletedProcess(
            args=["sudo", "cat"],
            returncode=0,
            stdout="DEMO_PASSWORD=secret\n",
            stderr="",
        )
        with mock.patch.dict(
            legacy.os.environ,
            {"BW_SESSION": "session-secret", "PATH": "/usr/bin:/bin"},
            clear=True,
        ):
            legacy.read_root_bounded(Path("/mnt/cpool/demo/.env.secrets"))

        child_env = run.call_args.kwargs["env"]
        self.assertNotIn("BW_SESSION", child_env)
        self.assertNotIn("session-secret", run.call_args.args[0])

    def test_explicit_app_bounded_legacy_path_survives_compose_cutover(self) -> None:
        manifest = {"items": []}
        with mock.patch.object(
            legacy,
            "allowed_legacy_paths",
            return_value=[],
        ):
            selected = legacy.choose_input(
                manifest,
                "sample",
                Path("/mnt/cpool/sample/.env.secrets"),
            )

        self.assertEqual(selected, Path("/mnt/cpool/sample/.env.secrets"))
        self.assertFalse(
            legacy.approved_app_env_path(
                "sample",
                Path("/mnt/cpool/other/.env.secrets"),
            )
        )

    @mock.patch.object(legacy.audit_consumers, "scan")
    @mock.patch.object(legacy.Path, "exists", side_effect=PermissionError)
    def test_legacy_path_discovery_tolerates_root_only_canonical_parent(
        self,
        _exists: mock.Mock,
        scan: mock.Mock,
    ) -> None:
        scan.return_value = {
            "legacyEnvFiles": [
                "sample|/mnt/cpool/sample/.env.secrets|apps/sample/compose.yml:68"
            ]
        }

        allowed = legacy.allowed_legacy_paths({"items": []}, "sample")

        self.assertEqual(allowed, [Path("/mnt/cpool/sample/.env.secrets")])

    def test_existing_item_payload_can_preserve_missing_optional_values(self) -> None:
        spec = {
            "app": "demo",
            "item": "nabla/prod/demo",
            "secrets": [
                {
                    "env": "OPTIONAL_TOKEN",
                    "importEnv": "DEMO_OPTIONAL_TOKEN",
                    "field": "OPTIONAL_TOKEN",
                    "allowEmpty": True,
                }
            ],
        }
        existing = {
            "id": "item-id",
            "name": "nabla/prod/demo",
            "folderId": "folder",
            "fields": [
                {"name": "OPTIONAL_TOKEN", "value": "keep-me", "type": 1}
            ],
        }
        payload = legacy.importer.make_item(
            app_spec=spec,
            folder_id="folder",
            values={"OPTIONAL_TOKEN": ""},
            existing=existing,
            supplied_source_names=set(),
        )
        field = next(
            item for item in payload["fields"] if item["name"] == "OPTIONAL_TOKEN"
        )
        self.assertEqual(field["value"], "keep-me")


if __name__ == "__main__":
    unittest.main()
