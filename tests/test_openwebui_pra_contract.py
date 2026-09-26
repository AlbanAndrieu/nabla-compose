from __future__ import annotations

from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def _documents(path: str) -> list[dict]:
    with (ROOT / path).open(encoding="utf-8") as stream:
        return [
            document
            for document in yaml.safe_load_all(stream)
            if isinstance(document, dict)
        ]


def _entity(path: str, name: str) -> dict:
    for document in _documents(path):
        metadata = document.get("metadata")
        if isinstance(metadata, dict) and metadata.get("name") == name:
            return document
    raise AssertionError(f"{path}: missing entity {name}")


class OpenWebUiPraContractTests(unittest.TestCase):
    def test_openwebui_bia_matches_reviewed_continuity_targets(self) -> None:
        entity = _entity("apps/openwebui/catalog-info.yaml", "openwebui")
        metadata = entity["metadata"]
        labels = metadata["labels"]
        annotations = metadata["annotations"]

        self.assertEqual(labels["albandrieu.com/operational-state"], "active")
        self.assertEqual(
            labels["albandrieu.com/operational-criticality"],
            "medium",
        )
        self.assertEqual(
            labels["albandrieu.com/business-criticality"],
            "high",
        )
        self.assertEqual(labels["albandrieu.com/bia-scope"], "direct")

        self.assertEqual(annotations["albandrieu.com/bia-mtpd"], "P7D")
        self.assertEqual(annotations["albandrieu.com/bia-rto"], "P1D")
        self.assertEqual(annotations["albandrieu.com/bia-rpo"], "P1D")
        self.assertEqual(annotations["albandrieu.com/bia-status"], "provisional")
        self.assertEqual(
            annotations["albandrieu.com/bia-mbco"],
            "openwebui-ui-with-litellm-and-openrag-required-on-lan-public-tunnel-optional",
        )
        for dimension in ("confidentiality", "integrity", "privacy"):
            self.assertEqual(
                annotations[f"albandrieu.com/bia-impact-{dimension}"],
                "high",
            )

    def test_openwebui_minimum_service_dependencies_are_declared(self) -> None:
        entity = _entity("apps/openwebui/catalog-info.yaml", "openwebui")
        dependencies = set(entity["spec"].get("dependsOn", []))

        self.assertIn("component:default/litellm", dependencies)
        self.assertIn("component:default/openrag-backend", dependencies)
        self.assertNotIn("resource:default/cloudflare-tunnel", dependencies)

        litellm = _entity("apps/litellm/catalog-info.yaml", "litellm")
        openrag = _entity("apps/openrag/catalog-info.yaml", "openrag-backend")
        gpu_ref = "resource:default/gpu-openai-compatible-inference"
        self.assertIn(gpu_ref, set(litellm["spec"].get("dependsOn", [])))
        self.assertIn(gpu_ref, set(openrag["spec"].get("dependsOn", [])))

    def test_public_tunnel_is_desired_but_not_continuity_critical(self) -> None:
        compose = (ROOT / "apps/openwebui/compose.yml").read_text(
            encoding="utf-8"
        )
        runbook = (ROOT / "docs/openwebui-backup-pra.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("open-webui.albandrieu.com", compose)
        self.assertIn(
            "gatewayRef: resource:default/cloudflare-tunnel",
            compose,
        )
        self.assertIn("access:\n            required: true", compose)
        self.assertIn("not** part of the\nminimum continuity objective", runbook)
        self.assertIn("LAN without Cloudflare", runbook)

    def test_pra_requires_backup_evidence_not_same_pool_snapshot_only(self) -> None:
        runbook = (ROOT / "docs/openwebui-backup-pra.md").read_text(
            encoding="utf-8"
        )
        diagnostic = (
            ROOT / "scripts/truenas/diagnose-openwebui-backup-pra.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("every **12 hours**", runbook)
        self.assertRegex(runbook, r"at\s+least daily")
        self.assertIn("not** an independent\nbackup", runbook)
        self.assertIn(
            'RPO_SECONDS="${RPO_SECONDS:-86400}"',
            diagnostic,
        )
        self.assertIn(
            'SNAPSHOT_TARGET_SECONDS="${SNAPSHOT_TARGET_SECONDS:-43200}"',
            diagnostic,
        )
        self.assertIn("replication.query", diagnostic)
        self.assertIn("cloudsync.query", diagnostic)

    def test_restore_acceptance_covers_configuration_rag_ui_and_gpu(self) -> None:
        runbook = (ROOT / "docs/openwebui-backup-pra.md").read_text(
            encoding="utf-8"
        )

        required = (
            "restore duration <= 1 day (RTO)",
            "restored recovery point age <= 1 day (RPO)",
            "OpenWebUI UI is usable from the LAN",
            "LiteLLM request succeeds",
            "OpenRAG retrieval succeeds",
            "GPU-backed OpenAI-compatible inference request succeeds",
            "critical configuration is present",
            "If recovery is not complete after 3 days",
            "7-day DMTP",
        )
        for text in required:
            with self.subTest(text=text):
                self.assertIn(text, runbook)


if __name__ == "__main__":
    unittest.main()
