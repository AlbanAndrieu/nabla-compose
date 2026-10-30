"""Read-only path contract for Compose's staged OpenClaw submodule migration.

The sandbox is intentionally NOT moved yet: TrueNAS may still reference its
Compose include path. A subsequent change must prove the runtime callers.
"""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]
MOVED = ROOT / "ops/openclaw-workstation"
OLD = ROOT / "apps/openclaw/workstation"
SANDBOX = ROOT / "apps/openclaw"

EXPECTED_POLICY_FILES = {
    "BACKUP.md",
    "HEARTBEAT-RESTORED.candidate.md",
    "HEARTBEAT-SCRATCH.template.md",
    "HEARTBEAT.md",
    "LEGACY_HEARTBEAT_RECOVERY.md",
    "MORNING_BRIEFING.md",
    "NFS-BACKUP.md",
    "cron/daily-tech-news-digest.message.md",
    "cron/daily-tech-news-digest.policy.json",
    "heartbeat-restoration.policy.json",
    "runtime-contract.json",
    "systemd/30-nabla-runtime-alignment.conf.example",
    "systemd/nabla-openclaw-rate-limit-evidence.service",
    "systemd/nabla-openclaw-rate-limit-evidence.timer",
}
EXPECTED_SANDBOX = {
    "compose.yml", "Dockerfile", "catalog-info.yaml", "test-docker.sh",
}
SOURCE_CONSUMERS = (
    "scripts/workstation/apply-openclaw-heartbeat-scratch.py",
    "scripts/workstation/check-openclaw-runtime-alignment.py",
    "scripts/workstation/openclaw-heartbeat-gitops.py",
    "scripts/workstation/openclaw_runtime_paths.py",
    "scripts/workstation/reconcile-openclaw-digest-cron.py",
    "tests/test_openclaw_digest_gitops_policy.py",
    "tests/test_openclaw_heartbeat_legacy_recovery_contract.py",
    "tests/test_openclaw_heartbeat_restoration.py",
    "tests/test_openclaw_recovery_gates.py",
    "tests/test_openclaw_runtime_paths.py",
)


class RelocationContract(unittest.TestCase):
    def test_no_workstation_files_remain_in_apps(self):
        self.assertFalse(OLD.exists())

    def test_expected_files_moved_without_loss(self):
        self.assertEqual(
            {str(p.relative_to(MOVED)) for p in MOVED.rglob("*") if p.is_file()},
            EXPECTED_POLICY_FILES,
        )

    def test_sandbox_is_kept_in_place_until_runtime_proven(self):
        self.assertEqual(
            {p.name for p in SANDBOX.iterdir() if p.is_file()},
            EXPECTED_SANDBOX,
        )

    def test_all_active_python_consumers_use_new_policy_root(self):
        for rel in SOURCE_CONSUMERS:
            with self.subTest(path=rel):
                source = (ROOT / rel).read_text(encoding="utf-8")
                self.assertNotIn("apps/openclaw/workstation", source)
                self.assertIn("ops/openclaw-workstation", source)

    def test_policy_refs_repointed_without_activating_heartbeat(self):
        hb = json.loads(
            (MOVED / "heartbeat-restoration.policy.json").read_text(encoding="utf-8")
        )
        cron = json.loads(
            (MOVED / "cron/daily-tech-news-digest.policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            hb["source"], "ops/openclaw-workstation/LEGACY_HEARTBEAT_RECOVERY.md"
        )
        self.assertEqual(
            cron["message_source"],
            "ops/openclaw-workstation/cron/daily-tech-news-digest.message.md",
        )
        self.assertEqual(hb["deployment"], "candidate_not_applied")
        self.assertTrue(all(x["enabled"] is False for x in hb["recovered_capabilities"]))


if __name__ == "__main__":
    unittest.main()
