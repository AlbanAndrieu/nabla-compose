"""Offline contracts: dated HAProxy snapshot and cross-layer expected exposure."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/pfsense/audit-haproxy-ingress.py"
SNAPSHOT = ROOT / "docs/evidence/pfsense/haproxy-2026-10-27.generated.redacted.cfg"
POLICY = ROOT / "config/ingress-access-policy.json"

spec = importlib.util.spec_from_file_location("nabla_haproxy_policy", SCRIPT)
assert spec and spec.loader
audit_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_module)


class PfsenseHaproxyPolicyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY.read_text(encoding="utf-8"))
        cls.source = SNAPSHOT.read_text(encoding="utf-8")

    def test_snapshot_is_redacted_and_generated_not_deploy_source(self):
        self.assertIn("Generated on: 2026-10-27 20:47", self.source)
        self.assertIn("acl", self.source)
        self.assertIn("s3", self.source)
        self.assertIn("vault", self.source)
        self.assertIn("http-request deny deny_status 403", self.source)
        self.assertNotIn("82.66.4.247", self.source)
        self.assertNotIn("80.15.4.233", self.source)
        self.assertNotIn("main_Web_HTTPS.crt_list", self.source)

    def test_nexus_denied_in_generated_snapshot(self):
        r = audit_module.audit(self.source, self.policy, {})
        hosts = {h["hostname"]: h for h in r["hosts"]}
        self.assertEqual(hosts["nexus.int.albandrieu.com"]["haproxy"], "DECLARED_DENY_NOT_WAN_PROOF")
        self.assertTrue(hosts["nexus.int.albandrieu.com"]["deny_lines"])
        self.assertFalse(r["wan_request_verified"])
        self.assertTrue(r["wildcard_int_to_traefik"])

    def test_vault_deny_missing_not_marked_pass(self):
        r = audit_module.audit(self.source, self.policy, {})
        hosts = {h["hostname"]: h for h in r["hosts"]}
        self.assertEqual(hosts["vault.int.albandrieu.com"]["haproxy"], "VIOLATION_NO_EXPLICIT_DENY")
        self.assertEqual(hosts["vaultwarden.int.albandrieu.com"]["haproxy"], "VIOLATION_NO_EXACT_ACL")
        self.assertGreaterEqual(r["requires_attention"], 3)

    def test_s3_private_requires_explicit_deny(self):
        r = audit_module.audit(self.source, self.policy, {})
        hosts = {h["hostname"]: h for h in r["hosts"]}
        self.assertEqual(hosts["s3.int.albandrieu.com"]["haproxy"], "VIOLATION_NO_EXPLICIT_DENY")
        self.assertEqual(hosts["hello.int.albandrieu.com"]["haproxy"], "DECLARED_ALLOW")
        self.assertEqual(self.policy["hosts"][3]["intent"], "private")

    def test_public_s3_dns_is_policy_violation_not_exception(self):
        evidence = {"public_dns": {"s3.int.albandrieu.com": "present"}}
        r = audit_module.audit(self.source, self.policy, evidence)
        hosts = {h["hostname"]: h for h in r["hosts"]}
        self.assertEqual(hosts["s3.int.albandrieu.com"]["other_layers"]["public_dns"], "VIOLATION")

    def test_generated_tabs_are_parsed_for_nexus_vault_s3(self):
        # Historical regression: pfSense uses tabs for ACL separation.
        acl_lines = [line for line in self.source.splitlines() if line.lstrip().startswith("acl")]
        self.assertTrue(any("\\t" in x for x in acl_lines))
        r = audit_module.audit(self.source, self.policy, {})
        hosts = {h["hostname"]: h for h in r["hosts"]}
        self.assertIn("nexus", hosts["nexus.int.albandrieu.com"]["acl_names"])
        self.assertIn("vault", hosts["vault.int.albandrieu.com"]["acl_names"])
        self.assertIn("s3", hosts["s3.int.albandrieu.com"]["acl_names"])

    def test_other_layers_unknown_not_success(self):
        r = audit_module.audit(self.source, self.policy, {})
        for h in r["hosts"]:
            for value in h["other_layers"].values():
                self.assertNotEqual(value, "PASS")

    def test_detects_removed_nexus_deny_and_capture_order(self):
        modified = self.source.replace(
            "http-request deny deny_status 403  if  nexus aclcrt_main_Web_HTTPS",
            "# simulated removed deny", 1,
        )
        hosts = {h["hostname"]: h for h in audit_module.audit(modified, self.policy, {})["hosts"]}
        self.assertEqual(hosts["nexus.int.albandrieu.com"]["haproxy"], "VIOLATION_NO_EXPLICIT_DENY")
        lines = self.source.splitlines()
        capture_idx = next(i for i, x in enumerate(lines) if x.strip().startswith("http-request set-var(txn.txnhost)"))
        deny_idx = next(i for i, x in enumerate(lines) if x.strip().startswith("http-request deny deny_status 403"))
        lines[capture_idx], lines[deny_idx] = lines[deny_idx], lines[capture_idx]
        hosts = {h["hostname"]: h for h in audit_module.audit("\n".join(lines), self.policy, {})["hosts"]}
        self.assertEqual(hosts["nexus.int.albandrieu.com"]["haproxy"], "VIOLATION_HOST_CAPTURE_ORDER")

    def test_present_cloudflare_tunnel_is_a_private_violation(self):
        e = {"cloudflare_tunnel": {"vault.int.albandrieu.com": "present"}}
        hosts = {h["hostname"]: h for h in audit_module.audit(self.source, self.policy, e)["hosts"]}
        self.assertEqual(hosts["vault.int.albandrieu.com"]["other_layers"]["cloudflare_tunnel"], "VIOLATION")

    def test_critical_drift_stable_across_redaction(self):
        a = audit_module.critical_rules(self.source, "main_Web_HTTPS")
        self.assertTrue(a)
        replaced = self.source.replace("PUBLIC_IP_REDACTED", "82.66.4.247")
        b = audit_module.critical_rules(replaced, "main_Web_HTTPS")
        self.assertEqual(a, b)
        removed = self.source.replace("http-request deny deny_status 403  if  nexus aclcrt_main_Web_HTTPS", "")
        self.assertNotEqual(a, audit_module.critical_rules(removed, "main_Web_HTTPS"))

    def test_redaction_sanitizes_wan_ips_and_certificate_paths(self):
        raw = "bind 82.66.4.247:443 ssl crt-list /var/etc/haproxy/foo.crt_list\nacl office src 80.15.4.233\n"
        safe = audit_module.redacted(raw)
        self.assertNotIn("82.66.4.247", safe)
        self.assertNotIn("80.15.4.233", safe)
        self.assertNotIn("foo.crt_list", safe)
        self.assertIn("PUBLIC_IP_REDACTED", safe)

    def test_missing_frontend_fails_closed(self):
        report = audit_module.audit("frontend unrelated\n  mode http\n", self.policy, {})
        self.assertFalse(report["frontend_found"])
        self.assertEqual(report["error"], "FRONTEND_NOT_FOUND")

    def test_cli_readonly_snapshot_json_and_strict_violation(self):
        command = [sys.executable, str(SCRIPT)]
        r = subprocess.run(command, text=True, capture_output=True, cwd=ROOT, timeout=5)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("WAN", r.stdout.upper() if "WAN" in r.stdout.upper() else r.stdout)
        s = subprocess.run(command + ["--strict"], text=True, capture_output=True, cwd=ROOT, timeout=5)
        self.assertEqual(s.returncode, 2)

    def test_live_ssh_and_config_mutation_are_never_automatic(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("BatchMode=yes", source)
        self.assertIn("cat /var/etc/haproxy/haproxy.cfg", source)
        for forbidden in ("service haproxy restart", "pfctl -f", "app.redeploy", "midclt call -j"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
