"""No-network checks for explicit central CrowdSec key reissue.

Tests never invoke --apply, so central bouncer state cannot be mutated.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/provision-crowdsec-pfsense-bouncer.sh"


@unittest.skipUnless(shutil.which("jq"), "jq needed for bouncer JSON")
class ProvisionUnusedBouncerTests(unittest.TestCase):
    def run_check(self, last_pull=None, existing_file=False):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            secrets = tmp / "runtime" / ".env.secrets"
            secrets.parent.mkdir()
            if existing_file:
                secrets.write_text("BOUNCER_KEY_PFSENSE_FIREWALL=EXISTING_SECRET\n")
                secrets.chmod(0o600)
            docker = tmp / "docker"
            docker.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  inspect) echo healthy ;;\n"
                "  exec)\n"
                "    if [ \"$5\" != list ]; then echo 'MUTATION_REQUESTED' >&2; exit 9; fi\n"
                "    printf '%s\\n' \"$FAKE_REGISTRATIONS\" ;;\n"
                "  *) echo 'UNEXPECTED_DOCKER_ACTION' >&2; exit 9 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            docker.chmod(0o700)
            env = os.environ.copy()
            env["PATH"] = directory + os.pathsep + env["PATH"]
            env["CROWDSEC_SECRET_FILE"] = str(secrets)
            value = "null" if last_pull is None else '"' + last_pull + '"'
            env["FAKE_REGISTRATIONS"] = '[{"name":"PFSENSE_FIREWALL","last_pull":' + value + '}]'
            return subprocess.run(
                ["bash", str(SCRIPT), "--check"],
                text=True, capture_output=True, cwd=ROOT,
                env=env, timeout=8,
            )

    def test_unused_registration_can_proceed_to_explicit_apply(self):
        r = self.run_check()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("credential_state=MISSING", r.stdout)
        self.assertIn("last_pull=<none>", r.stdout)
        self.assertNotIn("MUTATION_REQUESTED", r.stderr)

    def test_used_bouncer_cannot_be_rotated(self):
        r = self.run_check(last_pull="2026-10-27T21:00:00Z")
        self.assertEqual(r.returncode, 2)
        self.assertIn("NO_GO", r.stdout)

    def test_existing_runtime_credential_is_never_overwritten(self):
        r = self.run_check(existing_file=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("credential_state=EXISTS", r.stdout)

    def test_apply_requires_root_and_explicit_mode(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('mode=', source)
        self.assertIn('[[ "$mode" == --apply', source)
        self.assertIn('cscli bouncers add "$name" -o raw', source)
        self.assertIn('cscli bouncers delete "$name"', source)
        self.assertIn('ln -- "$tmp" "$file"', source)
        self.assertIn("BOUNCER_KEY_PFSENSE_FIREWALL=%s", source)
        self.assertNotIn("echo $key", source)
        self.assertNotIn('set -x\n', source)
        self.assertNotIn("ssh ", source)
        p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
