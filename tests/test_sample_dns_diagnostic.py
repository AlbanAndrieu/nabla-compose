"""Local-first Sample DNS regression: no real DNS, Docker or firewall calls."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ingress/diagnose-sample-dns.sh"
TRUENAS_DIAG = ROOT / "scripts/truenas/diagnose-fastapi-sample.sh"


class SampleDnsDiagnosticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="sample-dns-test-")
        self.addCleanup(self.temp.cleanup)
        self.bin = Path(self.temp.name)
        programs = {
            "dig": """#!/bin/sh
host=''; server=''; type=''
for arg in "$@"; do
  case "$arg" in
    @*) server="$(echo "$arg" | cut -c2-)" ;;
    sample.*) host="$arg" ;;
    A|AAAA|HTTPS) type="$arg" ;;
  esac
done
[ "$type" = A ] || exit 0
case "$host" in
  sample.int.albandrieu.com) echo 172.17.0.24 ;;
  sample.albandrieu.com)
    if [ "$server" = 172.17.0.24 ] && [ "$MOCK_BAD_PIHOLE" = 1 ]; then
      echo 172.17.0.24
    else
      echo 188.114.96.2
    fi ;;
esac
""",
            "getent": """#!/bin/sh
case "$2" in
  sample.albandrieu.com)
    printf '%s STREAM sample.albandrieu.com\\n' "${MOCK_SYSTEM_IP:-188.114.96.2}" ;;
  sample.int.albandrieu.com)
    [ "${MOCK_PRIVATE_SYS:-good}" = good ] &&
      printf '172.17.0.24 STREAM sample.int.albandrieu.com\\n'
    ;;
esac
""",
            "docker": """#!/bin/sh
case "$1" in
  info) exit 0 ;;
  inspect) [ "$MOCK_MISSING_PIHOLE" != 1 ] ;;
  exec) [ "$MOCK_OVERRIDE" = 1 ] && echo /etc/pihole/pihole.toml; exit 0 ;;
esac
""",
            "sudo": "#!/bin/sh\nexit 1\n",
            "systemctl": """#!/bin/sh
[ "$2" = NetworkManager ] && echo active || echo inactive
""",
            "nmcli": """#!/bin/sh
case "$*" in
  *DHCP4.OPTION*) echo 'DHCP4.OPTION[5]: domain_name_servers = 172.17.0.1' ;;
  *"-g GENERAL.CONNECTION"*) echo 'Wired connection' ;;
  *"connection show Wired connection"*)
    if [ "${MOCK_EMPTY_NM_FIELDS:-0}" != 1 ]; then
      echo 'ipv4.dns: 9.9.9.9,149.112.112.112'
      echo 'ipv4.ignore-auto-dns: yes'
    fi ;;
  *) echo 'GENERAL.CONNECTION: Wired connection' ;;
esac
""",
            "resolvectl": """#!/bin/sh
[ "$1" = dns ] && echo "Link 2 (eno1): ${MOCK_ACTIVE_DNS:-172.17.0.1}"
""",
        }
        for program, text in programs.items():
            path = self.bin / program
            path.write_text(text, encoding="utf-8")
            path.chmod(0o755)

    def run_dns(self, *args: str, **changes: str) -> subprocess.CompletedProcess[str]:
        env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}
        env.update(changes)
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            capture_output=True, text=True, env=env, timeout=10, check=False,
        )

    def test_clean_external_and_internal_views(self) -> None:
        outcome = self.run_dns("--check")
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertIn("sample_dns_summary failures=0", outcome.stdout)

    def test_wrong_pihole_record_detected_without_exposing_secrets(self) -> None:
        outcome = self.run_dns(
            "--truenas", MOCK_BAD_PIHOLE="1", MOCK_OVERRIDE="1",
            MOCK_SYSTEM_IP="172.17.0.24",
        )
        self.assertEqual(outcome.returncode, 1)
        self.assertIn("pihole_override_source=/etc/pihole/pihole.toml", outcome.stdout)
        self.assertIn("bypasses Cloudflare/ECH", outcome.stdout)
        self.assertIn("sample_dns_summary failures=2", outcome.stdout)
        self.assertIn("EVIDENCE: Pi-hole local record explains", outcome.stdout)

    def test_dhcp_correct_but_workstation_active_dns_is_quad9(self) -> None:
        outcome = self.run_dns(
            "--workstation", MOCK_ACTIVE_DNS="9.9.9.9 149.112.112.112",
        )
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertIn("domain_name_servers = 172.17.0.1", outcome.stdout)
        self.assertIn("DNS differs from pfSense", outcome.stdout)
        self.assertIn("NetworkManager", outcome.stdout)
        self.assertIn("ipv4.ignore-auto-dns: yes", outcome.stdout)
        self.assertIn("SKIP: Pi-hole container configuration requires --truenas", outcome.stdout)
        self.assertNotIn("Pi-hole container", outcome.stdout.split("SKIP:")[0])

    def test_quad9_only_does_not_prove_private_int_resolution(self) -> None:
        outcome = self.run_dns(
            "--workstation", MOCK_ACTIVE_DNS="9.9.9.9 149.112.112.112",
            MOCK_PRIVATE_SYS="missing",
        )
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertIn("Quad9/public DNS alone is not sufficient", outcome.stdout)
        self.assertIn("DNS differs from pfSense", outcome.stdout)
        self.assertIn("sample_dns_summary failures=0 warnings=2", outcome.stdout)

    def test_check_mode_never_attempts_local_truenas_docker(self) -> None:
        result = self.run_dns("--check", MOCK_MISSING_PIHOLE="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKIP: Pi-hole container configuration requires --truenas", result.stdout)
        self.assertIn("sample_dns_summary failures=0 warnings=0", result.stdout)

    def test_truenas_mode_reports_unavailable_local_pihole(self) -> None:
        result = self.run_dns("--truenas", MOCK_MISSING_PIHOLE="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Pi-hole container 'pihole' unavailable", result.stdout)
        self.assertIn("sample_dns_summary failures=0 warnings=1", result.stdout)

    def test_empty_nmcli_dns_fields_are_reported_not_silenced(self) -> None:
        result = self.run_dns("--workstation", MOCK_EMPTY_NM_FIELDS="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("active_nm_profile=Wired connection", result.stdout)
        self.assertIn("NetworkManager active profile DNS properties returned no data", result.stdout)
        self.assertIn("sample_dns_summary failures=0 warnings=1", result.stdout)

    def test_script_is_read_only_and_hooked_into_main_diagnostic(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        truenas = TRUENAS_DIAG.read_text(encoding="utf-8")
        for banned in ("docker restart", "docker stop", "docker rm",
                       "resolvectl dns eno1", "nmcli connection modify",
                       "pihole restart"):
            self.assertNotIn(banned, source)
        self.assertIn("ingress/diagnose-sample-dns.sh", truenas)
        self.assertEqual(truenas.count("section '"), 7)
        for target in (SCRIPT, TRUENAS_DIAG):
            outcome = subprocess.run(
                ["bash", "-n", str(target)], capture_output=True,
                text=True, check=False,
            )
            self.assertEqual(outcome.returncode, 0, outcome.stderr)


if __name__ == "__main__":
    unittest.main()
