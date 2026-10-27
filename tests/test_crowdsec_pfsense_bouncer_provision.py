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
            # The original external Docker fake fails on TrueNAS mounts
            # that disallow executing temporary files. Use shell functions
            # in the Bash interpreter which sources the unchanged script.
            # Stub timeout too: an external timeout cannot invoke a function.
            mock = """docker() {
  case "$1" in
    inspect)
      [[ "$#" == 4 && "$2" == crowdsec && "$3" == --format ]] || {
        printf 'UNEXPECTED_DOCKER_INSPECT\\n' >&2; return 9;
      }
      printf 'healthy\\n'
      ;;
    exec)
      [[ "$#" == 7 && "$2" == crowdsec && "$3" == cscli &&
         "$4" == bouncers && "$5" == list && "$6" == -o &&
         "$7" == json ]] || {
        printf 'MUTATION_REQUESTED\\n' >&2; return 9;
      }
      printf '%s\\n' "$FAKE_REGISTRATIONS"
      ;;
    *) printf 'MUTATION_REQUESTED\\n' >&2; return 9 ;;
  esac
}
timeout() {
  [[ "$#" -ge 3 && ( "$1" == 10 || "$1" == 12 ) &&
     "$2" == docker ]] || {
    printf 'UNEXPECTED_TIMEOUT\\n' >&2; return 9;
  }
  shift 2
  docker "$@"
}
script="$1"
shift
source "$script" "$@"
"""
            env = os.environ.copy()
            env["CROWDSEC_SECRET_FILE"] = str(secrets)
            env["CROWDSEC_CONTAINER"] = "crowdsec"  # Isolate host-specific settings.
            value = "null" if last_pull is None else '"' + last_pull + '"'
            env["FAKE_REGISTRATIONS"] = '[{"name":"PFSENSE_FIREWALL","last_pull":' + value + '}]'
            return subprocess.run(
                ["bash", "-c", mock, "crowdsec-docker-mock", str(SCRIPT), "--check"],
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

    def test_check_mode_never_executes_external_docker(self):
        source = Path(__file__).read_text(encoding="utf-8")
        self.assertIn('source "$script" "$@"', source)
        self.assertIn('"$2" == docker', source)
        self.assertIn("MUTATION_REQUESTED", source)
        self.assertNotRegex(source, r"(?m)^\s+docker\s*=\s*tmp\s*/")

    def test_apply_requires_root_and_explicit_mode(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('mode=', source)
        self.assertIn('[[ "$mode" == --apply', source)
        self.assertIn("openssl rand -hex 32", source)
        self.assertIn('cscli bouncers add PFSENSE_FIREWALL --key "$candidate"', source)
        self.assertIn('cscli bouncers delete "$name"', source)
        self.assertNotIn('key="$(timeout 12 docker exec', source)
        self.assertLess(source.index('ln -- "$tmp" "$file"'), source.index('cscli bouncers delete "$name"'))
        self.assertIn("credential_state=STAGED", source)
        self.assertIn('ln -- "$tmp" "$file"', source)
        self.assertIn("BOUNCER_KEY_PFSENSE_FIREWALL=%s", source)
        self.assertNotIn("echo $key", source)
        self.assertNotIn('set -x\n', source)
        self.assertNotIn("ssh ", source)
        p = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)


if __name__ == "__main__":
    unittest.main()
