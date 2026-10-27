"""Hermetic TrueNAS candidate bouncer key: no secret output/network/mutation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/check-crowdsec-candidate-bouncer.sh"


class CandidateBouncerAuthTests(unittest.TestCase):
    def check_auth(self, payload, mode=0o600, http=200, env_name=None, env_value=None):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            secret = directory / ".env.secrets"
            secret.write_text(payload, encoding="utf-8")
            secret.chmod(mode)
            fake_curl = directory / "curl"
            fake_curl.write_text(
                '#!/bin/sh\ncat >/dev/null\nprintf "%s" "${FAKE_CURL_CODE:-200}"\n',
                encoding="utf-8",
            )
            fake_curl.chmod(0o700)
            env = dict(os.environ)
            env.update({
                "PATH": str(directory) + os.pathsep + os.environ["PATH"],
                "CROWDSEC_SECRET_FILE": str(secret),
                "CROWDSEC_CENTRAL_LAPI_URL": "http://127.0.0.1:8084",
                "FAKE_CURL_CODE": str(http),
                "CROWDSEC_CURL_BIN": str(fake_curl),
            })
            cmd = ["bash", str(SCRIPT)]
            if env_name is not None:
                cmd.extend(["--env", env_name])
                if env_value is not None:
                    env[env_name] = env_value
                else:
                    env.pop(env_name, None)
            return subprocess.run(
                cmd,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=6,
            )

    def test_accepted_candidate_key(self):
        r = self.check_auth("BOUNCER_KEY_PFSENSE_FIREWALL=TEST_TOKEN_NEVER_ECHO\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("central_candidate_auth=ACCEPTED", r.stdout)
        self.assertNotIn("TEST_TOKEN_NEVER_ECHO", r.stdout + r.stderr)

    def test_quoted_candidate_keys_are_supported(self):
        for value in ('"TEST_TOKEN_NEVER_ECHO"', "'TEST_TOKEN_NEVER_ECHO'"):
            with self.subTest(value_style=value[0]):
                result = self.check_auth("BOUNCER_KEY_PFSENSE_FIREWALL=" + value + "\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("central_candidate_auth=ACCEPTED", result.stdout)
                self.assertNotIn("TEST_TOKEN_NEVER_ECHO", result.stdout + result.stderr)

    def test_existing_exported_crowdsec_bouncer_key_authenticates(self):
        result = self.check_auth("", env_name="CROWDSEC_BOUNCER_API_KEY", env_value="TEST_TOKEN_NEVER_ECHO")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("central_candidate_auth=ACCEPTED", result.stdout)
        self.assertIn("central_candidate_identity=UNVERIFIED", result.stdout)
        self.assertNotIn("TEST_TOKEN_NEVER_ECHO", result.stdout + result.stderr)

    def test_traefik_bouncer_candidate_is_separate(self):
        result = self.check_auth("", env_name="BOUNCER_KEY_TRAEFIK", env_value="TRAEFIK_TEST_NEVER_ECHO")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("central_candidate_identity=UNVERIFIED", result.stdout)
        self.assertNotIn("TRAEFIK_TEST_NEVER_ECHO", result.stdout + result.stderr)

    def test_machine_password_is_not_accepted_as_bouncer_key(self):
        result = self.check_auth("", env_name="CROWDSEC_LOCAL_API_PASSWORD", env_value="MACHINE_PASSWORD")
        self.assertEqual(result.returncode, 2)
        self.assertIn("NO_GO_UNSUPPORTED_ENV_NAME", result.stdout)

    def test_missing_exported_key_is_reported_without_leak(self):
        result = self.check_auth("", env_name="CROWDSEC_BOUNCER_API_KEY", env_value=None)
        self.assertEqual(result.returncode, 2)
        self.assertIn("NO_GO_ENV_UNSET_OR_NOT_EXPORTED", result.stdout)

    def test_rejected_candidate_key(self):
        r = self.check_auth("BOUNCER_KEY_PFSENSE_FIREWALL=TEST_TOKEN_NEVER_ECHO\n", http=403)
        self.assertEqual(r.returncode, 1)
        self.assertIn("central_candidate_auth=REJECTED", r.stdout)
        self.assertNotIn("TEST_TOKEN_NEVER_ECHO", r.stdout + r.stderr)

    def test_restrictive_permissions_required(self):
        r = self.check_auth("BOUNCER_KEY_PFSENSE_FIREWALL=TEST_TOKEN_NEVER_ECHO\n", mode=0o644)
        self.assertEqual(r.returncode, 2)
        self.assertIn("NO_GO_SECRET_PERMISSIONS", r.stdout)

    def test_invalid_duplicate_or_escaped_values_fail_closed(self):
        for payload in (
            "BOUNCER_KEY_PFSENSE_FIREWALL=SECRET\nBOUNCER_KEY_PFSENSE_FIREWALL=OTHER\n",
            'BOUNCER_KEY_PFSENSE_FIREWALL=INVALID"VALUE\n',
            "BOUNCER_KEY_PFSENSE_FIREWALL=INVALID\\VALUE\n",
        ):
            with self.subTest(payload_type=len(payload)):
                r = self.check_auth(payload)
                self.assertEqual(r.returncode, 2)
                self.assertIn("NO_GO_INVALID_SECRET_FORMAT", r.stdout)

    def test_transport_is_a_mock_not_a_live_localhost_probe(self):
        # Deliberately supply a localhost URL with no listening service.
        # The injected executable must return its synthetic status directly.
        result = self.check_auth(
            "BOUNCER_KEY_PFSENSE_FIREWALL=TEST_TOKEN_NEVER_ECHO\\n", http=403
        )
        self.assertIn("central_candidate_auth=REJECTED", result.stdout)
        self.assertNotIn("Failed to connect", result.stderr)

    def test_shell_syntax_and_no_mutation(self):
        syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"${CURL_BIN}" --config -', source)
        self.assertIn("CROWDSEC_CURL_BIN", source)
        self.assertNotIn("curl -H", source)
        for forbidden in ("cscli bouncers add", "cscli bouncers delete", "service crowdsec", "docker restart", "pfctl -T", "midclt call"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
