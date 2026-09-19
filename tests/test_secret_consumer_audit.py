from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "secrets" / "audit_consumers.py"
SPEC = importlib.util.spec_from_file_location("audit_consumers", MODULE)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class SecretConsumerAuditTests(unittest.TestCase):
    def test_secret_variable_classifier_is_segment_aware(self) -> None:
        self.assertTrue(audit.is_secret_variable("REDIS_AUTH"))
        self.assertTrue(audit.is_secret_variable("LITELLM_MASTER_KEY"))
        self.assertTrue(audit.is_secret_variable("WEBUI_SECRET_KEY"))
        self.assertFalse(audit.is_secret_variable("TWOFAUTH_UID"))
        self.assertFalse(audit.is_secret_variable("ENABLE_API_KEY_AUTH"))

    def test_static_scan_never_reads_runtime_secret_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "demo").mkdir(parents=True)
            compose = root / "apps" / "demo" / "compose.yml"
            compose.write_text(
                """services:
  demo:
    env_file:
      - /mnt/cpool/demo/.env.secrets
    environment:
      DEMO_PASSWORD: ${DEMO_PASSWORD:-changeme}
""",
                encoding="utf-8",
            )

            original = audit.git_tracked_compose_files
            audit.git_tracked_compose_files = lambda _: [compose]
            try:
                report = audit.scan(
                    root,
                    {
                        "items": [],
                    },
                )
            finally:
                audit.git_tracked_compose_files = original

        self.assertEqual(len(report["legacyEnvFiles"]), 1)
        self.assertEqual(len(report["unmanagedSecretVariables"]), 1)
        self.assertEqual(len(report["insecureDefaults"]), 1)

    def test_catalog_evidence_is_not_counted_as_runtime_env_debt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "sample").mkdir(parents=True)
            compose = root / "apps" / "sample" / "compose.yml"
            compose.write_text(
                """services:
  sample:
    x-nabla:
      relations:
        - target: redis
          evidence:
            - apps/sample/compose.yml:/mnt/cpool/sample/.env.secrets:REDIS_URL
    env_file:
      - /mnt/cpool/sample/.env.secrets
""",
                encoding="utf-8",
            )

            original = audit.git_tracked_compose_files
            audit.git_tracked_compose_files = lambda _: [compose]
            try:
                report = audit.scan(root, {"items": []})
            finally:
                audit.git_tracked_compose_files = original

        self.assertEqual(
            report["legacyEnvFiles"],
            [
                "sample|/mnt/cpool/sample/.env.secrets|apps/sample/compose.yml:9"
            ],
        )

    def test_absolute_repository_env_path_is_not_double_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "opensearch").mkdir(parents=True)
            compose = root / "apps" / "opensearch" / "compose.yml"
            compose.write_text(
                """services:
  opensearch:
    env_file:
      - /mnt/cpool/compose/nabla-compose/apps/opensearch/.env
""",
                encoding="utf-8",
            )

            original = audit.git_tracked_compose_files
            audit.git_tracked_compose_files = lambda _: [compose]
            try:
                report = audit.scan(root, {"items": []})
            finally:
                audit.git_tracked_compose_files = original

        self.assertEqual(
            report["legacyEnvFiles"],
            [
                "opensearch|/mnt/cpool/compose/nabla-compose/apps/opensearch/.env|apps/opensearch/compose.yml:4"
            ],
        )

    def test_nonsecret_canonical_dotenv_does_not_require_vault_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "sample").mkdir(parents=True)
            compose = root / "apps" / "sample" / "compose.yml"
            compose.write_text(
                """services:
  sample:
    env_file:
      - /mnt/cpool/secrets/runtime/sample/.env
      - /mnt/cpool/secrets/runtime/sample/.env.secrets
""",
                encoding="utf-8",
            )

            original = audit.git_tracked_compose_files
            audit.git_tracked_compose_files = lambda _: [compose]
            try:
                report = audit.scan(root, {"items": []})
            finally:
                audit.git_tracked_compose_files = original

        self.assertEqual(
            report["canonicalRuntimeWithoutManifest"],
            [
                "sample|/mnt/cpool/secrets/runtime/sample/.env.secrets|apps/sample/compose.yml:5"
            ],
        )

    def test_absolute_evidence_path_is_not_secret_file_debt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "apps" / "sentry").mkdir(parents=True)
            compose = root / "apps" / "sentry" / "compose.yml"
            compose.write_text(
                """services:
  sentry:
    x-nabla:
      relations:
        - target: redis
          evidence:
            - /mnt/cpool/sentry/.env.secrets:RELAY_REDIS_URL
    env_file:
      - /mnt/cpool/sentry/.env.secrets
""",
                encoding="utf-8",
            )

            original = audit.git_tracked_compose_files
            audit.git_tracked_compose_files = lambda _: [compose]
            try:
                report = audit.scan(root, {"items": []})
            finally:
                audit.git_tracked_compose_files = original

        self.assertEqual(
            report["legacyEnvFiles"],
            ["sentry|/mnt/cpool/sentry/.env.secrets|apps/sentry/compose.yml:9"],
        )
        self.assertEqual(report["specialHostSecretFiles"], [])

    def test_baseline_ratchet_ignores_harmless_line_moves(self) -> None:
        current = {
            "legacyEnvFiles": [
                "demo|/mnt/cpool/demo/.env.secrets|apps/demo/compose.yml:42"
            ]
        }
        baseline = {
            "schemaVersion": 1,
            "legacyEnvFiles": [
                "demo|/mnt/cpool/demo/.env.secrets|apps/demo/compose.yml:7"
            ],
        }

        self.assertEqual(audit.compare_baseline(current, baseline), [])


    def test_baseline_comparison_is_a_two_way_ratchet(self) -> None:
        current = {
            "legacyEnvFiles": ["demo|/mnt/cpool/demo/.env.secrets|apps/demo/compose.yml:3"],
        }
        baseline = {
            "schemaVersion": 1,
            "legacyEnvFiles": ["old|/mnt/cpool/old/.env|apps/old/compose.yml:3"],
        }
        errors = audit.compare_baseline(current, baseline)
        self.assertEqual(len(errors), 2)
        self.assertIn("new debt", errors[0] + errors[1])
        self.assertIn("baseline is stale", errors[0] + errors[1])


if __name__ == "__main__":
    unittest.main()
