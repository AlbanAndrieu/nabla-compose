"""Checks the failure gate never exposes private BuildKit output to stdout."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BuildFailureIntegrationContract(unittest.TestCase):
    def test_deployment_only_runs_classifier_on_failed_build(self):
        script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
        beginning = script.index("build_fastapi_sample() {")
        ending = script.index("run_midclt_job_quiet() {", beginning)
        block = script[beginning:ending]
        self.assertIn("if run_build_attempt", block)
        self.assertIn("diag_fail 'FastAPI Sample image build failed; existing runtime was preserved.'", block)
        self.assertIn("classify-fastapi-build-failure.py", block)
        self.assertIn('--check --failure-shape --log "${log}"', block)
        self.assertIn('return "${rc}"', block)
        self.assertNotIn('cat "${log}"', block)
        self.assertNotIn('tail -n "${BUILD_LOG_TAIL}" "${log}"', block)

    def test_gate_does_not_remove_running_container_or_retry_on_classification(self):
        script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
        beginning = script.index("diag_fail 'FastAPI Sample image build failed; existing runtime was preserved.'")
        ending = script.index("run_midclt_job_quiet() {", beginning)
        block = script[beginning:ending]
        self.assertNotIn("run_docker rm", block)
        self.assertNotIn("build_args+=", block)
        self.assertNotIn("run_build_attempt", block)
        self.assertIn('diag_info "Private Docker build evidence:', block)

    def test_roadmap_and_runbook_keep_same_gate(self):
        roadmap = (ROOT / "docs/roadmap.md").read_text()
        runbook = (ROOT / "docs/runbooks/fastapi-truenas-build-failure-20261027.md").read_text()
        self.assertIn("Échec du build FastAPI TrueNAS #380", roadmap)
        self.assertIn("classify-fastapi-build-failure.py", runbook)
        self.assertIn("l'ancien conteneur a été préservé", runbook)
        self.assertIn("Ne pas utiliser cat, tail, grep", runbook)


if __name__ == "__main__":
    unittest.main()
