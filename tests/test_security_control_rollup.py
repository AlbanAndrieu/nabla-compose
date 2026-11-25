"""Offline tests for value-blind GitHub security rollup."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "scripts/security/report-github-controls.py"
spec = importlib.util.spec_from_file_location("security_evidence", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
NOW = datetime(2026, 11, 26, tzinfo=timezone.utc)


def run(conclusion="success", age=1):
    return {"id": 123, "head_branch": "master", "event": "schedule",
            "status": "completed", "conclusion": conclusion,
            "updated_at": (NOW - timedelta(hours=age)).isoformat()}


class TestRollup(unittest.TestCase):
    def test_success_never_means_scan_or_import_confirmed(self):
        def fetch(url):
            if "/artifacts?" in url:
                return {"artifacts": [{"name": "nuclei-public-123",
                                       "expired": False}]}
            return {"workflow_runs": [run()]}
        report = module.build_report(fetch, NOW)
        self.assertEqual(report["totals"]["CI_SUCCESS"], len(module.CONTROLS))
        self.assertTrue(all(not r["scan_validated"] and r["findings"] is None
                            and r["defectdojo_import"] == "NOT_VERIFIED"
                            for r in report["controls"]))

    def test_newest_failure_overrides_old_success(self):
        result = module.build_report(
            lambda url: {"workflow_runs": [run("failure"), run("success", 30)]},
            NOW)
        self.assertEqual(result["totals"]["CI_FAILED"], len(module.CONTROLS))

    def test_cancelled_is_incomplete(self):
        result = module.build_report(
            lambda url: {"workflow_runs": [run("cancelled", 300)]}, NOW)
        self.assertEqual(result["totals"]["INCOMPLETE"], len(module.CONTROLS))
        self.assertEqual(result["controls"][0]["freshness"], "STALE")

    def test_api_failure_is_unknown_not_down(self):
        def fail(url):
            raise ValueError("unavailable")
        result = module.build_report(fail, NOW)
        self.assertEqual(result["totals"]["UNVERIFIED"],
                         len(module.CONTROLS) + len(module.PRIVATE))

    def test_no_run_is_not_zero_findings(self):
        result = module.build_report(lambda url: {"workflow_runs": []}, NOW)
        self.assertEqual(result["totals"]["NOT_RUN"], len(module.CONTROLS))
        self.assertTrue(all(r["findings"] is None for r in result["controls"]))

    def test_html_escapes_control_labels(self):
        result = module.build_report(lambda url: {"workflow_runs": []}, NOW)
        result["controls"][0]["id"] = "<script>bad</script>"
        html = module.render_html(result)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
