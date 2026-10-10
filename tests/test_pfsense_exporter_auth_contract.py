from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-pfsense-exporter-auth.sh"
HARDENER = ROOT / "scripts/truenas/harden-pfsense-exporter-config.sh"


def curl_bash_env(tmp: Path, marker: Path, status: str) -> Path:
    """Mock curl in non-interactive Bash without executing a noexec tmp shim."""
    bash_env = tmp / "bash-env"
    bash_env.write_text(
        "curl() {\n"
        f"  touch {marker}\n"
        f'  printf "%s" "{status}"\n'
        "}\n",
        encoding="utf-8",
    )
    return bash_env


class PfSenseExporterAuthContractTests(unittest.TestCase):
    def test_diagnostic_is_fail_fast_and_secret_safe(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        mode = SCRIPT.stat().st_mode

        self.assertTrue(mode & stat.S_IXUSR)
        self.assertIn("/mnt/cpool/prometheus/secrets/pfsense-exporter.yml", text)
        self.assertIn("/api/v2/status/services", text)
        self.assertEqual(text.count("curl --silent"), 1)
        self.assertIn('--header "@${HEADER_FILE}"', text)
        self.assertIn("exactly one authenticated request", text)
        self.assertIn("response body and key are suppressed", text)
        self.assertIn("HTTP 401", text)
        self.assertIn("HTTP 403", text)
        self.assertNotIn('echo "$key"', text)

    def test_hardener_rejects_placeholder_key(self) -> None:
        text = HARDENER.read_text(encoding="utf-8")
        self.assertIn(
            "if not key or key == placeholder:",
            text,
        )
        self.assertIn(
            "runtime config still contains an empty/placeholder API key",
            text,
        )

    def test_runtime_key_is_never_printed_and_401_is_fail_fast(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            config = tmp / "config.yml"
            marker = tmp / "curl-called"
            secret = "SUPERSECRET-CONTRACT-KEY"

            config.write_text(
                "targets:\n"
                '  - host: "172.17.0.1"\n'
                "    port: 10443\n"
                '    scheme: "https"\n'
                '    auth_method: "key"\n'
                f'    key: "{secret}"\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PFSENSE_EXPORTER_CONFIG"] = str(config)
            env["BASH_ENV"] = str(curl_bash_env(tmp, marker, "401"))

            result = subprocess.run(
                [str(SCRIPT)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 4)
            self.assertTrue(marker.exists())
            output = result.stdout + result.stderr
            self.assertIn("HTTP 401", output)
            self.assertNotIn(secret, output)

    def test_placeholder_fails_before_any_http_request(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            config = tmp / "config.yml"
            marker = tmp / "curl-called"

            config.write_text(
                "targets:\n"
                '  - host: "172.17.0.1"\n'
                "    port: 10443\n"
                '    scheme: "https"\n'
                '    auth_method: "key"\n'
                '    key: "REPLACE_WITH_DEDICATED_PFSENSE_EXPORTER_API_KEY"\n',
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["PFSENSE_EXPORTER_CONFIG"] = str(config)
            env["BASH_ENV"] = str(curl_bash_env(tmp, marker, "200"))

            result = subprocess.run(
                [str(SCRIPT)],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertIn(
                "empty/placeholder API key",
                result.stdout + result.stderr,
            )


if __name__ == "__main__":
    unittest.main()
