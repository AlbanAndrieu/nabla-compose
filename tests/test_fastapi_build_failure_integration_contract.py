"""Checks the failure gate never exposes private BuildKit output to stdout."""
from pathlib import Path
import os
import subprocess
import tempfile
import time
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


    @staticmethod
    def _shell_function(name: str) -> str:
        script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
        anchor = name + "() {\n"
        start = script.index(anchor)
        end = script.index("\n}\n", start) + 3
        return script[start:end]

    def test_registry_quota_guard_hermetic(self):
        """Use mocked Docker access; never contact a daemon or registry."""
        function = self._shell_function("guard_dockerhub_base_build")
        harness = """
set -euo pipefail
fail() { exit 73; }
summary_ok() { :; }
summary_warn() { :; }
run_docker() {
    if [[ "$1" == info ]]; then return 0; fi
    if [[ "$1" == image && "${CACHE_HIT}" == true ]]; then return 0; fi
    return 1
}
dockerhub_cooldown_active() { [[ "${COOLDOWN_ACTIVE}" == true ]]; }
dockerhub_client_auth_configured() { [[ "${HAS_CLIENT_CONFIG}" == true ]]; }
"""
        cases = (
            (False, False, False, False, False, False, 73),  # avoid anonymous 429
            (False, True, False, False, False, False, 0),   # configured client
            (True, False, False, False, False, False, 0),   # local base
            (True, False, True, False, False, False, 73),   # --pull forces request
            (False, False, False, True, False, False, 0),  # explicit anonymous
            (True, False, False, False, True, False, 73),  # active cooldown
            (True, False, False, False, True, True, 0),    # explicit override
        )
        for cache, config, refresh, anonymous, active, override, expected in cases:
            with self.subTest(cache=cache, config=config, refresh=refresh,
                              anonymous=anonymous, active=active, override=override):
                env = {
                    **os.environ,
                    "CACHE_HIT": str(cache).lower(),
                    "HAS_CLIENT_CONFIG": str(config).lower(),
                    "REFRESH_BASE_IMAGES": str(refresh).lower(),
                    "ALLOW_ANONYMOUS_BASE_PULL": str(anonymous).lower(),
                    "COOLDOWN_ACTIVE": str(active).lower(),
                    "OVERRIDE_DOCKERHUB_COOLDOWN": str(override).lower(),
                }
                result = subprocess.run(
                    ["bash", "-c", harness + "\n" + function + "\nguard_dockerhub_base_build\n"],
                    env=env, capture_output=True, text=True, timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertNotIn("docker.io", result.stdout)
                self.assertNotIn("token", result.stdout.lower())

    def test_registry_cooldown_marker_owner_and_mode_hermetic(self):
        function = self._shell_function("dockerhub_cooldown_active")
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "dockerhub-429"
            marker.write_text(str(int(time.time())) + "\n")
            marker.chmod(0o600)
            harness = """
set -euo pipefail
fail() { exit 73; }
"""
            env = {
                **os.environ,
                "DOCKERHUB_RATE_MARKER": str(marker),
                "DOCKERHUB_COOLDOWN_SECONDS": "21600",
            }
            for mode, expected in ((0o600, 0), (0o644, 73)):
                with self.subTest(mode=oct(mode)):
                    marker.chmod(mode)
                    result = subprocess.run(
                        ["bash", "-c", harness + "\n" + function + "\ndockerhub_cooldown_active\n"],
                        env=env, capture_output=True, text=True, timeout=5,
                        check=False,
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)

    def test_dockerhub_auth_declaration_is_not_generic_config_presence(self):
        function = self._shell_function("dockerhub_client_auth_configured")
        cases = (
            ({}, False),
            ({"auths": {"ghcr.io": {"auth": "synthetic"}}}, False),
            ({"auths": {"https://index.docker.io/v1/": {}}}, False),
            ({"auths": {"https://index.docker.io/v1/": {"auth": "synthetic"}}}, True),
            ({"credHelpers": {"registry-1.docker.io": "pass"}}, True),
            ({"credsStore": "pass"}, True),
        )
        import json
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            for payload, expected in cases:
                with self.subTest(config=tuple(payload)):
                    config.write_text(json.dumps(payload))
                    config.chmod(0o600)
                    env = {**os.environ, "DOCKER_CONFIG": directory}
                    result = subprocess.run(
                        ["bash", "-c", (
                            "set -euo pipefail\n"
                            "DOCKER=(docker)\n" + function +
                            "\ndockerhub_client_auth_configured\n"
                        )],
                        env=env, capture_output=True, text=True,
                        timeout=5, check=False,
                    )
                    self.assertEqual(result.returncode == 0, expected, result.stderr)
                    self.assertEqual(result.stdout, "")

    def test_rate_limit_state_record_is_private(self):
        function = self._shell_function("record_dockerhub_429")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            marker = state / "dockerhub-429"
            env = {
                **os.environ,
                "DOCKERHUB_RATE_STATE_DIR": str(state),
                "DOCKERHUB_RATE_MARKER": str(marker),
            }
            result = subprocess.run(
                ["bash", "-c", (
                    "set -euo pipefail\n"
                    "fail() { exit 73; }\n"
                    "summary_warn() { :; }\n" +
                    function + "\nrecord_dockerhub_429\n"
                )],
                env=env, capture_output=True, text=True,
                timeout=5, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
            self.assertEqual(marker.stat().st_uid, os.getuid())
            self.assertLess(abs(int(marker.read_text().strip()) - int(time.time())), 5)
            self.assertEqual(result.stdout, "")

    def test_quota_guard_precedes_build_and_does_not_restart_services(self):
        script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
        start = script.index("if [[ \"${image_source}\" == \"local-build\" ]]; then")
        end = script.index("step '4/6'", start)
        block = script[start:end]
        self.assertLess(block.index("guard_dockerhub_base_build"),
                        block.index("build_fastapi_sample"))
        self.assertNotIn("system prune", block)
        self.assertNotIn("docker system", block)
        self.assertNotIn("run_docker rm", block)
        self.assertIn("FASTAPI_SAMPLE_ALLOW_ANONYMOUS_BASE_PULL", script)
        self.assertIn("FASTAPI_SAMPLE_OVERRIDE_DOCKERHUB_COOLDOWN", script)

    def test_release_registry_429_is_not_followed_by_build_fallback(self):
        script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text()
        self.assertIn("run_release_image_pull", script)
        self.assertIn("RELEASE_PULL_RATE_LIMITED", script)
        self.assertIn("Release registry returned HTTP 429; refusing fallback", script)
        start = script.index("build_fastapi_sample() {")
        end = script.index("run_midclt_job_quiet() {", start)
        block = script[start:end]
        self.assertIn('if ! dockerhub_429_in_log "${log}"', block)
        self.assertIn("record_dockerhub_429", block)
        self.assertNotIn("tail -n", block)



if __name__ == "__main__":
    unittest.main()
