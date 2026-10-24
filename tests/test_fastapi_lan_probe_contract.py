"""Offline contracts for the TrueNAS LAN observer command (no network)."""
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/verify-fastapi-lan-probes.sh"


def simulate(payload, *, flag="true", mode="homelab"):
    """Execute only the embedded Python against a fake localhost response."""
    script = SOURCE.read_text(encoding="utf-8")
    python_source = script.split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    output = StringIO()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, *_args):
            return json.dumps(payload).encode("utf-8")

    with (
        patch.dict(os.environ, {
            "FASTAPI_RUNTIME_MODE": mode,
            "HOMELAB_INTERNAL_PROBES_ENABLED": flag,
        }, clear=True),
        patch("urllib.request.urlopen", return_value=Response()),
        redirect_stdout(output),
    ):
        try:
            exec(compile(python_source, str(SOURCE), "exec"), {"__name__": "__main__"})
            return 0, output.getvalue()
        except SystemExit as error:
            return error.code, output.getvalue()


def data(*, eligible=86, sampled=2, completed=2, enabled=True):
    return {
        "internal_probes_enabled": enabled,
        "probe_summary": {
            "internal": {
                "eligible": eligible,
                "sampled": sampled,
                "completed": completed,
            },
        },
    }


class LanProbeContract(unittest.TestCase):
    def test_read_only_shell_parses_and_help_needs_no_docker(self):
        self.assertEqual(subprocess.run(
            ["bash", "-n", str(SOURCE)], check=False,
        ).returncode, 0)
        result = subprocess.run(
            ["bash", str(SOURCE), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check", result.stdout)

    def test_disabled_env_does_not_prove_lan(self):
        code, out = simulate(data(), flag="false")
        self.assertEqual(code, 1)
        self.assertIn("configuration-mismatch", out)

    def test_zero_samples_are_not_healthy(self):
        code, out = simulate(data(sampled=0, completed=0))
        self.assertEqual(code, 1)
        self.assertIn("no-lan-sample", out)

    def test_zero_completed_probes_are_not_healthy(self):
        code, out = simulate(data(completed=0))
        self.assertEqual(code, 1)
        self.assertIn("no-completed-lan-probe", out)

    def test_no_eligible_target_does_not_prove_coverage(self):
        code, out = simulate(data(eligible=0, sampled=0, completed=0))
        self.assertEqual(code, 1)
        self.assertIn("no-eligible-lan-services", out)

    def test_boolean_is_not_an_integer_measurement(self):
        code, out = simulate(data(eligible=True))
        self.assertEqual(code, 1)
        self.assertIn("no-eligible-lan-services", out)

    def test_one_completed_sample_is_evidence_not_functional_health(self):
        code, out = simulate(data(eligible=86, sampled=2, completed=1))
        self.assertEqual(code, 0)
        self.assertIn("lan-sampling-observed", out)
        self.assertNotIn("healthy", out.lower())

    def test_collector_runtime_and_payload_must_agree(self):
        code, out = simulate(data(enabled=False))
        self.assertEqual(code, 1)
        self.assertIn("collector-payload-disagrees", out)


if __name__ == "__main__":
    unittest.main()
