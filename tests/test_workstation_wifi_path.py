"""Hermetic workstation Wi-Fi/DNS path diagnosis tests: no network required."""
from pathlib import Path
import importlib.util
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/diagnose-wifi-path.py"
spec = importlib.util.spec_from_file_location("nabla_wifi_path", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(*, wifi=False, wifi_connected=True, pf_dns=True, public_dns=True,
            system_dns=True, active="172.17.0.1", dhcp="172.17.0.1"):
    calls = []
    interface = "wlp2s0" if wifi else "eno1"

    def runner(args):
        args = tuple(args)
        calls.append(args)
        if args[:4] == ("ip", "-4", "route", "get"):
            return True, f"1.1.1.1 via 172.17.0.1 dev {interface} src 172.17.0.57"
        if args[0] == "nmcli":
            if "GENERAL.TYPE" in args:
                return True, "wifi" if wifi else "ethernet"
            if "DHCP4.OPTION" in args:
                return True, f"DHCP4.OPTION[5]: domain_name_servers = {dhcp}"
        if args[0] == "resolvectl":
            return True, f"Link 2 ({interface}): {active}"
        if args[0] == "iw":
            return True, (
                "Connected to 02:01:02:03:04:05 (on wlp2s0)\n"
                "\tSSID: VERY_PRIVATE_WIFI_NAME\n\tsignal: -63 dBm\n\tfreq: 5180\n"
                if wifi_connected else "Not connected.\n"
            )
        if args[0] == "dig":
            dns = next((a[1:] for a in args if a.startswith("@")), None)
            name = args[-2]
            if name.endswith(".int.albandrieu.com"):
                return True, "172.17.0.24"
            if dns == "172.17.0.1":
                return pf_dns, "93.184.215.14" if pf_dns else ""
            if dns == "9.9.9.9":
                return public_dns, "93.184.215.14" if public_dns else ""
        if args[0] == "getent":
            return system_dns, "93.184.215.14 STREAM example.org" if system_dns else ""
        return False, ""

    return runner, calls


class WifiPathTest(unittest.TestCase):
    def test_wired_vantage_cannot_certify_phone_wifi(self):
        runner, calls = fixture()
        data = module.snapshot(runner=runner, connect=lambda *_: True)
        self.assertEqual(data["diagnosis"], "NO_FAILURE_DURING_SAMPLE")
        self.assertEqual(data["vantage"], "wired_or_unknown")
        self.assertTrue(data["wifi_client_not_tested"])
        self.assertEqual(data["wifi_radio"], "NOT_OBSERVED")
        self.assertFalse(any(command[0] == "iw" for command in calls))

    def test_confirmed_wifi_radio_disconnected(self):
        runner, _ = fixture(wifi=True, wifi_connected=False)
        data = module.snapshot(runner=runner, connect=lambda *_: True)
        self.assertEqual(data["diagnosis"], "WIFI_ASSOCIATION_LOST")
        self.assertEqual(data["wifi_radio"], "DISCONNECTED")

    def test_wifi_link_signal_suppresses_ssid_and_bssid(self):
        runner, _ = fixture(wifi=True)
        data = module.snapshot(runner=runner, connect=lambda *_: True)
        self.assertEqual(data["wifi_radio"], "ASSOCIATED")
        self.assertEqual(data["wifi_signal_dbm"], -63)
        self.assertEqual(data["wifi_frequency_mhz"], 5180)
        text = str(data)
        self.assertNotIn("VERY_PRIVATE_WIFI_NAME", text)
        self.assertNotIn("02:01:02:03:04:05", text)

    def test_control_dns_works_but_pfsense_dns_fails_with_ip_reachability(self):
        runner, _ = fixture(pf_dns=False)
        data = module.snapshot(runner=runner, connect=lambda host, port: host == "1.1.1.1")
        self.assertEqual(data["diagnosis"], "PFSENSE_DNS_OR_WIFI_VLAN_POLICY")
        self.assertFalse(data["pfsense_dns_public"])
        self.assertTrue(data["control_dns_public"])
        self.assertTrue(data["external_tcp443"])
        self.assertFalse(data["pfsense_tcp53"])

    def test_dhcp_dns_and_active_dns_are_distinguished(self):
        runner, _ = fixture(active="9.9.9.9 149.112.112.112", dhcp="172.17.0.1")
        data = module.snapshot(runner=runner, connect=lambda *_: True)
        self.assertTrue(data["dns_override_suspected"])
        self.assertEqual(data["dhcp_advertised_dns"], ["172.17.0.1"])
        self.assertEqual(data["active_link_dns"], ["149.112.112.112", "9.9.9.9"])

    def test_system_resolver_failure_is_not_mislabeled_wifi_radio(self):
        runner, _ = fixture(system_dns=False)
        data = module.snapshot(runner=runner, connect=lambda *_: True)
        self.assertEqual(data["diagnosis"], "CLIENT_SYSTEM_DNS_PATH")
        self.assertEqual(data["wifi_radio"], "NOT_OBSERVED")

    def test_invalid_address_not_treated_as_dns_response(self):
        self.assertEqual(module.ipv4_addresses("999.777.123.88 garbage"), [])
        self.assertEqual(module.ipv4_addresses("an1 172.17.0.24:53"), ["172.17.0.24"])

    def test_invalid_arguments_fail_before_running_probes(self):
        for args in (["--check", "--interface", "wlan0;rm"],
                     ["--check", "--samples", "99"], ["--check", "--interval", "100"]):
            with self.subTest(args=args):
                result = subprocess.run([sys.executable, str(SCRIPT), *args],
                                        capture_output=True, check=False)
                self.assertEqual(result.returncode, 2)
        help_result = subprocess.run([sys.executable, str(SCRIPT), "--help"],
                                     capture_output=True, check=False)
        self.assertEqual(help_result.returncode, 0)

    def test_script_is_read_only_and_bounded(self):
        contents = SCRIPT.read_text()
        for forbidden in ("nmcli connection modify", "resolvectl dns eno1",
                          "sudo ", "service unbound restart", "pfctl -F",
                          "scan wifi", "nmcli device wifi rescan",
                          "tcpdump", "shell=True"):
            self.assertNotIn(forbidden, contents)
        self.assertIn("timeout=5", contents)
        self.assertIn("timeout=2", contents)


if __name__ == "__main__":
    unittest.main()
