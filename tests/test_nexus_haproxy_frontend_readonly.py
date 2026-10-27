"""Offline tests of the portable, read-only pfSense HAProxy frontend inspector."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/inspect-nexus-haproxy-frontend.sh"
AWK = ROOT / "scripts/pfsense/inspect-nexus-haproxy-frontend.awk"

CONFIG = """\
frontend fWeb_HTTPS
    bind 82.66.4.247:443 ssl crt /etc/secret.pem
    acl int var(txn.txnhost) -m end -i .int.albandrieu.com
    http-request deny deny_status 403 if legacy_only
    use_backend old_traefik if int
frontend main_Web_HTTPS
    bind 82.66.4.247:443 ssl crt /etc/secret.pem
    http-request set-var(txn.txnhost) req.hdr(host),lower
    acl nexus-albandrieu var(txn.txnhost) -m str -i nexus-albandrieu.int.albandrieu.com
    acl int var(txn.txnhost) -m end -i .int.albandrieu.com
    acl aclcrt_main_Web_HTTPS var(txn.txnhost) -m found
    acl nexus_private_wan var(txn.txnhost) -m str -i nexus.int.albandrieu.com
    http-request deny deny_status 403 if nexus_private_wan
    http-request set-header Authorization Bearer TOP_SECRET_DO_NOT_OUTPUT
    use_backend prod_front-traefik-https_ipvANY if int aclcrt_main_Web_HTTPS
    default_backend default_safe
backend prod_front-traefik-https_ipvANY
    server truenas 172.17.0.24:443 ssl verify none password DO_NOT_OUTPUT
backend nexus-albandrieu_ipvANY
    mode http
    server nexus 172.17.0.24:8081 check ssl verify none password NEXUS_SECRET_DO_NOT_OUTPUT
"""


class NexusHaproxyFrontendReadonly(unittest.TestCase):
    def run_script(self, config=CONFIG, *args):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "haproxy.cfg"
            cfg.write_text(config, encoding="utf-8")
            return subprocess.run(
                ["bash", str(SCRIPT), "--fixture", str(cfg), *args],
                cwd=ROOT, text=True, capture_output=True, timeout=5
            )

    def test_default_renamed_frontend(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("frontend=main_Web_HTTPS", r.stdout)
        self.assertIn("nexus.int.albandrieu.com", r.stdout)
        self.assertIn("nexus-albandrieu.int.albandrieu.com", r.stdout)
        self.assertIn("type=http_rule", r.stdout)
        self.assertIn("type=backend_route", r.stdout)
        self.assertIn("wan_rejection=NOT_VERIFIED", r.stdout)
        self.assertNotIn("old_traefik", r.stdout)
        self.assertNotIn("legacy_only", r.stdout)

    def test_missing_frontend_fails_closed(self):
        r = self.run_script("frontend fWeb_HTTPS\n  use_backend old_traefik\n")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("frontend 'main_Web_HTTPS' not found", r.stdout)

    def test_old_frontend_only_with_explicit_override(self):
        r = self.run_script(CONFIG, "--frontend", "fWeb_HTTPS")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("frontend=fWeb_HTTPS", r.stdout)
        self.assertNotIn("nexus_private_wan", r.stdout)

    def test_never_prints_cert_header_or_backend_secrets(self):
        r = self.run_script()
        self.assertEqual(r.returncode, 0, r.stderr)
        for secret in ("TOP_SECRET_DO_NOT_OUTPUT", "DO_NOT_OUTPUT", "secret.pem", "172.17.0.24:443"):
            self.assertNotIn(secret, r.stdout)

    def test_invalid_frontend_is_rejected(self):
        r = self.run_script(CONFIG, "--frontend", "main_Web_HTTPS;whoami")
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid HAProxy frontend name", r.stderr)

    def test_named_nexus_backend_target_only_and_no_secrets(self):
        r = self.run_script(CONFIG, "--backend", "nexus-albandrieu_ipvANY")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("backend=nexus-albandrieu_ipvANY", r.stdout)
        self.assertIn("backend_mode=http", r.stdout)
        self.assertIn("backend_server=nexus target=172.17.0.24:8081", r.stdout)
        self.assertNotIn("NEXUS_SECRET_DO_NOT_OUTPUT", r.stdout)
        self.assertNotIn("verify none", r.stdout)

    def test_missing_named_backend_fails_closed(self):
        r = self.run_script(CONFIG, "--backend", "not_defined")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("backend 'not_defined' not found", r.stdout)

    def test_invalid_backend_is_rejected(self):
        r = self.run_script(CONFIG, "--backend", "nexus;reboot")
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid HAProxy backend name", r.stderr)

    def test_current_nexus_route_uses_traefik_not_missing_legacy_backend(self):
        # Model the current 27/10 HAProxy route: Nexus goes to Traefik,
        # whereas the previously referenced direct backend is gone.
        current = CONFIG.replace(
            "use_backend prod_front-traefik-https_ipvANY if int aclcrt_main_Web_HTTPS",
            "use_backend prod_front-traefik-https_ipvANY if nexus aclcrt_main_Web_HTTPS",
        ).split('backend nexus-albandrieu_ipvANY', 1)[0]
        result = self.run_script(current, "--backend", "prod_front-traefik-https_ipvANY")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nexus_declared_backend=prod_front-traefik-https_ipvANY", result.stdout)
        self.assertIn("backend_server=truenas target=172.17.0.24:443", result.stdout)
        self.assertIn("wan_rejection=NOT_VERIFIED", result.stdout)
        stale = self.run_script(current, "--backend", "nexus-albandrieu_ipvANY")
        self.assertNotEqual(stale.returncode, 0)
        self.assertIn("backend 'nexus-albandrieu_ipvANY' not found", stale.stdout)

    def test_shell_parses_and_no_runtime_mutations(self):
        shell = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("midclt call", shell)
        self.assertNotIn("service haproxy restart", shell)
        self.assertNotIn("pfctl -f", shell)
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True, timeout=5)
        self.assertIn('active && $1 == "acl" {', AWK.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
