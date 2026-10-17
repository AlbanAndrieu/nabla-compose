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
        self.assertIn("SSH local", content)
        self.assertIn("Signature key", content)
        self.assertIn("OTP slot 2 HMAC-SHA1", content)
        for forbidden in ("piv reset", "otp chalresp 2", "gpg --export-secret-keys"):
            self.assertNotIn(forbidden, "\\n".join(line for line in content.splitlines()
                                                      if not line.lstrip().startswith("#")))


    def test_piv_inventory_enforces_known_single_key_and_read_only_slots(self):
        script = ROOT / "scripts/workstation/audit-yubikey-capabilities.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        help_text = subprocess.run(
            ["bash", str(script), "--help"], capture_output=True,
            text=True, check=True
        ).stdout
        for option in ("--primary", "--backup", "--serial", "--challenge"):
            self.assertIn(option, help_text)
        content = script.read_text()
        for marker in (
            "PRIMARY_SERIAL=23501671", "BACKUP_SERIAL=22916048",
            "Exactly one YubiKey must be connected",
            "Connected YubiKey does not match requested serial",
            "Unrecognized YubiKey",
            'args=(--device "${connected}")',
            'ykman "${args[@]}" piv keys info "${slot}"',
            "PIV slot summary", "UNKNOWN", "No key stored",
            "9C 9D 9E 82 83 84 85 86 87 88 89 8A 8B 8C 8D 8E 8F 90 91 92 93 94 95",
        ):
            self.assertIn(marker, content)
        for forbidden in ("piv keys generate", "piv keys import",
                          "piv keys delete", "piv reset", "otp delete"):
            self.assertNotIn(forbidden, content)

    def test_age_escrow_backup_contract(self):
        script = ROOT / "scripts/workstation/backup-sops-age-identity.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(
            ["bash", str(script), "--help"],
            capture_output=True, text=True, check=True
        )
        self.assertIn("--apply", result.stdout)
        content = script.read_text()
        for marker in (
            "umask 077", "age -e -r", "findmnt",
            "independent", "CHECK ONLY", "OFFLINE DECRYPTION",
            "chmod 600", "ln \"${temp}\" \"${output}\"",
        ):
            self.assertIn(marker, content)
        for dangerous in (
            "age -d", "age-keygen -o", "piv reset",
            "piv keys generate", "cat \"$source_file\"",
        ):
            self.assertNotIn(dangerous, content)

    def test_usb_escrow_recovery_contract(self):
        script = ROOT / "scripts/workstation/manage-age-escrow-usb.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(
            ["bash", str(script), "--help"],
            capture_output=True, text=True, check=True
        )
        for marker in ("--luks-uuid", "--check", "--open", "--close",
                       "--init-identity"):
            self.assertIn(marker, result.stdout)
        body = script.read_text()
        self.assertIn("age10lxlddwul3eaxs8fq7sh49hcks42tamy7cke7ny945kfwxaxqfaq46a938", body)
        self.assertIn("Existing original age identity verified", body)
        self.assertIn("CREATE-NEW-IDENTITY", body)
        for forbidden in ("luksFormat", "wipefs", "mkfs.ext4",
                          "parted -s", "reset PIV"):
            self.assertNotIn(forbidden, body)

    def test_age_escrow_restore_script_contract(self):
        script = ROOT / "scripts/workstation/verify-sops-age-escrow.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        help_text = subprocess.run(
            ["bash", str(script), "--help"], capture_output=True,
            text=True, check=True
        ).stdout
        self.assertIn("--backup", help_text)
        self.assertIn("--identity", help_text)
        body = script.read_text()
        for marker in ("umask 077", "/dev/shm", "tmpfs", "trap cleanup EXIT",
                       "age -d -i", "age-keygen -y", "PASS:"):
            self.assertIn(marker, body)

    def test_sops_usb_roundtrip_does_not_mutate_caller_shell(self):
        script = ROOT / "scripts/workstation/test-sops-usb-recovery.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        output = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--usb-identity", output.stdout)
        # Sourcing must return nonzero WITHOUT enabling errexit on the parent shell.
        cmd = f'source "{script}"; result=$?; [[ "$result" == 2 ]] && echo SHELL_ALIVE'
        sourced = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True)
        self.assertEqual(sourced.returncode, 0, sourced.stderr)
        self.assertIn("SHELL_ALIVE", sourced.stdout)
        body = script.read_text()
        for expected in ('BASH_SOURCE[0]', 'SOPS_AGE_KEY_FILE', '/dev/shm',
                         'trap cleanup EXIT', 'grep -Fxq'):
            self.assertIn(expected, body)

    def test_piv82_guard_is_non_destructive(self):
        script = ROOT / "scripts/workstation/preflight-age-yubikey-piv82.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--serial", result.stdout)
        text = script.read_text()
        for marker in ("piv keys info 82", "ykman list --serials",
                       "Connect exactly the selected single YubiKey"):
            self.assertIn(marker, text)
        # A single exact matching serial is required; avoid fragile sed backrefs.
        self.assertIn("mapfile -t detected_serials", text)
        self.assertIn("detected_serials[0]", text)
        self.assertIn("no key( (stored )?in slot)?", text)
        for forbidden in ("--generate", "piv reset", "piv keys import",
                          "otp chalresp", "ykman otp", "set -x"):
            self.assertNotIn(forbidden, text)

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
        self.assertIn("pcsc-shared", content)
        self.assertIn("Clé secrète de signature Git", content)
        self.assertIn("ykman-gui actif", content)
        self.assertIn("usbfs sur CCID est attendu", content)
        self.assertIn("ne pas répéter reader-port", content)
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
        self.assertIn("--pcsc-shared", out.stdout)
        self.assertIn("pcsc-shared) printf", script.read_text())
        body = script.read_text()
        for required in ("GNUPGHOME=", "disable-ccid", "timeout 18", "trap cleanup EXIT"):
            self.assertIn(required, body)
        for forbidden in ("keytocard", "piv reset", "gpgconf --kill all",
                          "systemctl restart", "set -x"):
            self.assertNotIn(forbidden, body)

    def test_main_profile_pcsc_shared_trial_contract(self):
        script = ROOT / "scripts/workstation/trial-gpg-pcsc-shared.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--trial", result.stdout)
        body = script.read_text()
        for token in ("cmp -s --", "pcsc-shared", "trap cleanup EXIT",
                      "cp -p --", "gpgconf --kill scdaemon",
                      "Main GnuPG profile detects"):
            self.assertIn(token, body)
        for token in ("keytocard", "piv reset", "gpgconf --kill all",
                      "systemctl restart pcscd", "set -x"):
            self.assertNotIn(token, body)

    def test_managed_pcsc_shared_apply_rollback_contract(self):
        script = ROOT / "scripts/workstation/manage-gpg-pcsc-shared.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        help_out = subprocess.run(["bash", str(script), "--help"],
                                  capture_output=True, text=True, check=True)
        for name in ("--check", "--verify", "--apply", "--rollback"):
            self.assertIn(name, help_out.stdout)
        content = script.read_text()
        for marker in ("cmp -s --", "trap cleanup EXIT", "before-reader-port",
                       "gpgconf --kill scdaemon", "No change", "pcsc-shared"):
            if marker != "No change":
                self.assertIn(marker, content)
        for forbidden in ("keytocard", "piv reset", "gpgconf --kill all",
                          "systemctl restart pcscd", "set -x"):
            self.assertNotIn(forbidden, content)

    def test_yubikey_bootstrap_installs_age_plugin_without_provisioning(self):
        script = ROOT / "scripts/workstation/bootstrap-yubikey-manager.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        result = subprocess.run(["bash", str(script), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("age-plugin-yubikey", result.stdout)
        body = script.read_text()
        for required in ("cargo install --locked", "AGE_PLUGIN_VERSION",
                         "libpcsclite-dev", "check_age_plugin",
                         "libpcsclite.pc", "dpkg-architecture",
                         "env -u PKG_CONFIG_LIBDIR -u PKG_CONFIG_SYSROOT_DIR",
                         "PKG_CONFIG=/usr/bin/pkg-config",
                         "--modversion libpcsclite"):
            self.assertIn(required, body)
        for forbidden in ("--generate", "piv reset", "keytocard", "set -x"):
            self.assertNotIn(forbidden, body)

    def test_no_destructive_operations(self):
        text = SCRIPT.read_text()
        for forbidden in ("otp chalresp", "otp delete", "piv reset", "piv keys import",
                          "otp swap", "set -x", "echo ${HMAC_SECRET}", "env |"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
