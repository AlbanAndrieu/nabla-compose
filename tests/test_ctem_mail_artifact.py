"""Offline contracts for GitHub App checkdmarc artifact retrieval."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import runpy
import sys
import unittest
from unittest.mock import patch
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
SECURITY = ROOT / "scripts/security"
sys.path.insert(0, str(SECURITY))
MOD = runpy.run_path(str(SECURITY / "pull-ctem-mail-artifact.py"))
T = datetime(2026, 11, 21, 8, tzinfo=timezone.utc)
SHA = "a" * 40


def scan_run(run_id=42, conclusion="success", status="completed", **kw):
    return {
        "name": "External attack surface (homelab)",
        "head_branch": "master",
        "head_sha": SHA,
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "event": "schedule",
        "created_at": (T - timedelta(days=1)).isoformat(),
        **kw,
    }


def artifact_zip(contents=b'{"checkdmarc":{}}', name="public-mail-deep.json"):
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        archive.writestr(name, contents)
    return output.getvalue()


class CtemMailGitHubArtifactTests(unittest.TestCase):
    def test_accept_exact_successful_recent_master(self):
        item = MOD["selected_run"]([scan_run()], now=T)
        self.assertEqual(item["id"], 42)

    def test_latest_failed_does_not_backtrack(self):
        with self.assertRaisesRegex(Exception, "LATEST_RUN_NOT_SUCCESSFUL"):
            MOD["selected_run"]([
                scan_run(41), scan_run(42, conclusion="failure")
            ], now=T)

    def test_refuses_stale_branch_or_wrong_workflow(self):
        for example in (
            dict(scan_run(), head_branch="feature"),
            dict(scan_run(), name="Another workflow"),
            dict(scan_run(), created_at=(T - timedelta(days=9)).isoformat()),
        ):
            with self.subTest(example=example), self.assertRaises(Exception):
                MOD["selected_run"]([example], now=T)

    def test_rejects_ambiguous_or_expired_artifact(self):
        good = {"name": "public-mail-deep-42", "expired": False,
                "id": 9, "size_in_bytes": 128}
        self.assertEqual(MOD["chosen_artifact"]([good], 42)["id"], 9)
        for rows in ([good, good], [{**good, "expired": True}],
                     [{**good, "name": "public-amass-summary-42"}]):
            with self.subTest(rows=rows), self.assertRaises(Exception):
                MOD["chosen_artifact"](rows, 42)

    def test_zip_rejects_extra_members_or_wrong_report(self):
        self.assertEqual(
            MOD["extract_report"](artifact_zip(contents=b"{}")), b"{}"
        )
        with self.assertRaises(Exception):
            MOD["extract_report"](artifact_zip(name="private-candidates.json"))
        buf = BytesIO()
        with ZipFile(buf, "w") as archive:
            archive.writestr("public-mail-deep.json", "{}")
            archive.writestr("raw.json", "secret")
        with self.assertRaises(Exception):
            MOD["extract_report"](buf.getvalue())

    def test_existing_scope_and_store_no_public_publish(self):
        runner = MOD["run"]
        api_calls = []
        def fake_meta(route, token):
            api_calls.append(route)
            if "/workflows/" in route:
                return {"workflow_runs": [scan_run()]}
            if route.endswith("/artifacts"):
                return {"artifacts": [{"name": "public-mail-deep-42",
                    "expired": False, "id": 9, "size_in_bytes": 400}]}
            return scan_run()
        def fake_api(route, token):
            api_calls.append(route)
            return artifact_zip()
        stored = []
        with patch.dict(runner.__globals__, {
            "installation_token": lambda repo: "fake Actions-read token",
            "metadata": fake_meta,
            "api": fake_api,
            "stage_report": lambda report, run_id, root, store: stored.append(
                (report, run_id, store)
            ) or "STORED",
        }):
            self.assertEqual(runner(True), "STORED")
        self.assertEqual(stored, [(b'{"checkdmarc":{}}', 42, True)])
        self.assertTrue(all("nabla-compose" in call for call in api_calls))
        self.assertTrue(all("external-attack-surface" in call
                            for call in api_calls if "/workflows/" in call))


if __name__ == "__main__":
    unittest.main()
