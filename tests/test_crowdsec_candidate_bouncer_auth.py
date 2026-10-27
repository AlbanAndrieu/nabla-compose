"""Hermetic TrueNAS candidate bouncer key: no secret output/network/mutation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/check-crowdsec-candidate-bouncer.sh"


class CandidateBouncerAuthTests(unittest.TestCase):
    def check_auth(self, payload, mode=0o600, http=200):
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
            })
            return subprocess.run(
                ["bash", str(SCRIPT)],
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

    def test_shell_syntax_and_no_mutation(self):
        syntax = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("curl --config -", source)
        self.assertNotIn("curl -H", source)
        for forbidden in ("cscli bouncers add", "cscli bouncers delete", "service crowdsec", "docker restart", "pfctl -T", "midclt call"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
