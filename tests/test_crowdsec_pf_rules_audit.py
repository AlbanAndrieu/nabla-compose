"""Offline regression tests for read-only loaded PF rule audit."""
from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/audit-crowdsec-pf-rules.py"
SPEC = importlib.util.spec_from_file_location("crowdsec_pf_rules_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

INFO = "Status: Enabled for 0 days 01:24:39\n"
BLOCK = 'block drop in log quick inet from <crowdsec_blacklists> to any label "crowdsec"\n'
BLOCK_IF = 'block drop in quick on vmx0 inet from <crowdsec_blacklists> to any\n'


class RuleAuditContracts(unittest.TestCase):
    def test_sample_crowdsec_root_rule_is_loaded(self):
        res = MODULE.audit(INFO, BLOCK, "", None, True)
        self.assertEqual("BLOCK_RULE_LOADED", res["status"])
        self.assertEqual("1", res["root_ipv4_block_quick_in"])
        self.assertEqual("NOT_VERIFIED", res["packet_block"])

    def test_pf_disabled_refuses_success(self):
        with self.assertRaises(MODULE.AuditUnknown):
            MODULE.audit("Status: Disabled\n", BLOCK, "", None, True)

    def test_pf_unknown_refuses_success(self):
        with self.assertRaises(MODULE.AuditUnknown):
            MODULE.audit("State Table: 0\n", BLOCK, "", None, True)

    def test_empty_table_declaration_is_not_enforcement(self):
        res = MODULE.audit(INFO, "table <crowdsec_blacklists> persist\n", "", None, True)
        self.assertEqual("NO_CROWDSEC_IPV4_RULE_OBSERVED", res["status"])

    def test_comment_is_not_enforcement(self):
        res = MODULE.audit(INFO, "# " + BLOCK, "", None, True)
        self.assertEqual("NO_CROWDSEC_IPV4_RULE_OBSERVED", res["status"])

    def test_pass_rule_does_not_count_as_block(self):
        res = MODULE.audit(INFO, "pass in quick from <crowdsec_blacklists> to any\n",
                           "", None, True)
        self.assertEqual("TABLE_REFERENCED_NO_QUICK_IN_BLOCK", res["status"])

    def test_nonquick_rule_is_not_acceptance(self):
        res = MODULE.audit(INFO, "block drop in from <crowdsec_blacklists> to any\n",
                           "", None, True)
        self.assertEqual("TABLE_REFERENCED_NO_QUICK_IN_BLOCK", res["status"])

    def test_outbound_block_is_not_inbound_proof(self):
        res = MODULE.audit(INFO, "block drop out quick from <crowdsec_blacklists> to any\n",
                           "", None, True)
        self.assertEqual("TABLE_REFERENCED_NO_QUICK_IN_BLOCK", res["status"])

    def test_destination_only_match_not_a_source_block(self):
        res = MODULE.audit(INFO, "block in quick from any to <crowdsec_blacklists>\n",
                           "", None, True)
        self.assertEqual("TABLE_REFERENCED_NO_QUICK_IN_BLOCK", res["status"])

    def test_anchor_only_never_proves_root_rule_reachable(self):
        res = MODULE.audit(INFO, 'anchor "somepackage"\n', BLOCK, None, True)
        self.assertEqual("ANCHOR_BLOCK_RULE_REACHABILITY_NOT_VERIFIED", res["status"])

    def test_unavailable_anchors_does_not_claim_absence(self):
        res = MODULE.audit(INFO, 'anchor "somepackage"\n', None, None, True)
        self.assertEqual("ROOT_RULE_ABSENT_ANCHORS_UNKNOWN", res["status"])
        self.assertEqual("NOT_VERIFIED", res["anchor_coverage"])

    def test_ipv6_is_counted_separately(self):
        res = MODULE.audit(INFO,
            "block drop in quick inet6 from <crowdsec6_blacklists> to any\n",
            "", None, True)
        self.assertEqual("1", res["root_ipv6_block_quick_in"])
        self.assertEqual("NO_CROWDSEC_IPV4_RULE_OBSERVED", res["status"])

    def test_rule_number_prefix_is_parsed(self):
        res = MODULE.audit(INFO, "@83 " + BLOCK, "", None, True)
        self.assertEqual("BLOCK_RULE_LOADED", res["status"])

    def test_wan_explicit_interface_matches_candidate_not_packet_proof(self):
        res = MODULE.audit(INFO, BLOCK_IF, "", "vmx0", True)
        self.assertEqual("1", res["wan_compatible_root_rule"])
        self.assertEqual("NOT_VERIFIED", res["packet_block"])

    def test_wan_other_interface_not_matching(self):
        res = MODULE.audit(INFO, BLOCK_IF, "", "igb1", True)
        self.assertEqual("0", res["wan_compatible_root_rule"])

    def test_global_rule_compatible_with_wan_but_not_packet_proof(self):
        res = MODULE.audit(INFO, BLOCK, "", "vmx0", True)
        self.assertEqual("1", res["wan_compatible_root_rule"])
        self.assertEqual("NOT_VERIFIED", res["packet_block"])

    def test_offline_fixture_never_claims_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            info = Path(folder) / "info.txt"
            rules = Path(folder) / "rules.txt"
            info.write_text(INFO)
            rules.write_text(BLOCK)
            p = subprocess.run(
                [sys.executable, str(SCRIPT), "--info-file", str(info),
                 "--rules-file", str(rules)],
                capture_output=True, text=True, timeout=7)
            self.assertEqual(0, p.returncode, p.stderr)
            self.assertIn("source=OFFLINE", p.stdout)
            self.assertIn("packet_block=NOT_VERIFIED", p.stdout)

    def test_ssh_injection_is_rejected(self):
        with self.assertRaises(MODULE.AuditUnknown):
            MODULE.ssh_read("-oProxyCommand=evil", 0, "pfctl -sr")

    def test_ssh_stderr_is_not_disclosed(self):
        p = subprocess.CompletedProcess(
            args=["ssh"], returncode=1, stdout=b"", stderr=b"API_KEY=DO_NOT_PRINT")
        with patch.object(MODULE.subprocess, "run", return_value=p):
            with self.assertRaises(MODULE.AuditUnknown) as caught:
                MODULE.ssh_read("home.example.test", 0, "pfctl -sr")
        self.assertNotIn("DO_NOT_PRINT", str(caught.exception))

    def test_no_mutating_pf_commands(self):
        source = SCRIPT.read_text()
        self.assertIn('"pfctl -sr"', source)
        self.assertIn('"pfctl -s info"', source)
        self.assertNotIn("pfctl -f ", source)
        self.assertNotIn("pfctl -T add", source)
        self.assertNotIn("pfctl -T flush", source)
        self.assertNotIn("cscli decisions add", source)

    def test_real_probe_ssh_transport_is_bounded(self):
        class FakeProcess:
            returncode = 0
            stdout = INFO.encode()
            stderr = b""
        with patch.object(MODULE.subprocess, "run", return_value=FakeProcess()) as stub:
            output = MODULE.ssh_read("home.example.test", 0, "pfctl -s info")
        self.assertEqual(INFO, output)
        command = stub.call_args.args[0]
        self.assertIn("BatchMode=yes", command)
        self.assertEqual("pfctl -s info", command[-1])
        self.assertEqual(22, stub.call_args.kwargs["timeout"])


if __name__ == "__main__":
    unittest.main()
