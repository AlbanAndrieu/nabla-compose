from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/diagnose-yubikey-keepassxc.sh"


class YubiKeyKeepassDiagnosticContract(unittest.TestCase):
    def test_bash_parses(self):
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

    def test_help_does_not_require_hardware(self):
        result = subprocess.run(["bash", str(SCRIPT), "--help"], capture_output=True, text=True, check=True)
        self.assertIn("--verify-secret", result.stdout)

    def test_inventory_script_contract(self):
        audit = ROOT / "scripts/workstation/audit-yubikey-capabilities.sh"
        subprocess.run(["bash", "-n", str(audit)], check=True)
        help_result = subprocess.run(["bash", str(audit), "--help"],
                                     capture_output=True, text=True, check=True)
        self.assertIn("--serial", help_result.stdout)
        content = audit.read_text()
        self.assertNotIn("ykman piv certificates list", content.split("# ykman 5.8.0")[0])
        self.assertIn("CHUID: [REDACTED]", content.replace('\\1 [REDACTED]', 'CHUID: [REDACTED]'))
        self.assertIn("NO_COLOR", content)
        self.assertIn("EXPIRED", content)
        for forbidden in ("piv reset", "otp chalresp 2", "gpg --export-secret-keys"):
            self.assertNotIn(forbidden, "\\n".join(line for line in content.splitlines()
                                                      if not line.lstrip().startswith("#")))


    def test_gpg_smartcard_triage_read_only(self):
        script = ROOT / "scripts/workstation/diagnose-gpg-smartcard.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--check", result.stdout)
        self.assertIn("--host-only", result.stdout)
        self.assertIn("host_only=true", script.read_text())
        content = script.read_text()
        self.assertIn("gpg --card-status", content)
        self.assertIn("disable-ccid", content)
        for forbidden in ("piv reset", "keytocard", "rm -rf", "gpg --delete-secret-key",
                          "gpgconf --kill", "systemctl stop", "set -x"):
            self.assertNotIn(forbidden, content)

    def test_reader_port_plan_is_read_only(self):
        script = ROOT / "scripts/workstation/plan-gpg-reader-port.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--check", result.stdout)
        content = script.read_text()
        self.assertIn("before-reader-port", content)
        self.assertIn("pcsc_scan", content)
        for forbidden in ("gpgconf --kill", "keytocard", "piv reset",
                          "systemctl restart", ">> ${cfg}", "sudo "):
            self.assertNotIn(forbidden, content)

    def test_transactional_reader_port_trial_safety(self):
        script = ROOT / "scripts/workstation/test-gpg-reader-port.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--apply", result.stdout)
        body = script.read_text()
        for expected in ("cmp -s", "trap cleanup EXIT", "changed=true",
                         "gpgconf --kill scdaemon", "cp -p --", "Card inserted"):
            self.assertIn(expected, body)
        for forbidden in ("keytocard", "piv reset", "gpgconf --kill all",
                          "systemctl restart pcscd", "set -x"):
            self.assertNotIn(forbidden, body)

    def test_isolated_gpg_transport_comparison_contract(self):
        script = ROOT / "scripts/workstation/compare-gpg-card-transports.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        out = subprocess.run(["bash", str(script), "--help"],
                             capture_output=True, text=True, check=True)
        self.assertIn("--run", out.stdout)
        body = script.read_text()
        for required in ("GNUPGHOME=", "disable-ccid", "timeout 18", "trap cleanup EXIT"):
            self.assertIn(required, body)
        for forbidden in ("keytocard", "piv reset", "gpgconf --kill all",
                          "systemctl restart", "set -x"):
            self.assertNotIn(forbidden, body)

    def test_no_destructive_operations(self):
        text = SCRIPT.read_text()
        for forbidden in ("otp chalresp", "otp delete", "piv reset", "piv keys import",
                          "otp swap", "set -x", "echo ${HMAC_SECRET}", "env |"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
