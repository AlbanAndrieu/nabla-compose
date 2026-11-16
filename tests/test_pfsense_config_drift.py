from __future__ import annotations

import contextlib
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("config_drift", ROOT / "scripts" / "pfsense" / "config-drift.py")
config_drift = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(config_drift)

BASE = """<?xml version="1.0"?>
<pfsense>
  <revision><time>1</time></revision>
  <system><user><name>admin</name><bcrypt-hash>$2y$10$secretvalue</bcrypt-hash></user></system>
  <filter>
    <rule><tracker>100</tracker><interface>wan</interface><descr>Block untrusted GUI</descr><type>block</type></rule>
    <rule><tracker>200</tracker><interface>wan</interface><descr>Easy Rule</descr><type>pass</type></rule>
  </filter>
  <syslog><remoteserver>172.17.0.24:1514</remoteserver></syslog>
  <interfaces><lan><descr>LAN</descr><ipaddrv6>track6</ipaddrv6></lan></interfaces>
</pfsense>
"""


def run(base: str, current: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as tmp:
        b, c = Path(tmp, "base.xml"), Path(tmp, "cur.xml")
        b.write_text(base, encoding="utf-8")
        c.write_text(current, encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = config_drift.main(["--baseline", str(b), "--current", str(c)])
        return rc, out.getvalue()


class PfSenseConfigDriftTests(unittest.TestCase):
    def test_identical_configs_converge_even_when_revision_differs(self) -> None:
        rc, out = run(BASE, BASE.replace("<time>1</time>", "<time>2</time>"))
        self.assertEqual(rc, 0, out)
        self.assertIn("result=CONVERGED", out)

    def test_fallback_regressions_are_reported_by_topic_without_secrets(self) -> None:
        current = (
            BASE.replace("<rule><tracker>100</tracker><interface>wan</interface><descr>Block untrusted GUI</descr><type>block</type></rule>", "")
            .replace("172.17.0.24:1514", "172.17.0.57:1514")
            .replace("track6", "none")
            .replace("secretvalue", "othersecret")
        )
        rc, out = run(BASE, current)
        self.assertEqual(rc, 2, out)
        self.assertIn("DRIFT: topic=firewall_rules", out)
        self.assertIn("DRIFT: topic=syslog", out)
        self.assertIn("DRIFT: topic=ipv6", out)
        self.assertIn("- filter/rule[100]/type: 'block'", out)
        self.assertIn("system/user[admin]/bcrypt-hash: 'redacted:", out)
        self.assertNotIn("secretvalue", out)
        self.assertNotIn("othersecret", out)
        self.assertIn("result=CONFIG_DRIFT", out)

    def test_added_dhcp_map_hides_mac_and_empty_fields(self) -> None:
        current = BASE.replace(
            "</pfsense>",
            "<dhcpd><lan><staticmap><mac>02:00:00:00:10:01</mac><ipaddr>172.17.0.50</ipaddr>"
            "<hostname>taloscp01</hostname><tftp></tftp></staticmap></lan></dhcpd></pfsense>",
        )
        rc, out = run(BASE, current)
        self.assertEqual(rc, 2, out)
        self.assertIn("ipaddr: '172.17.0.50'", out)
        self.assertIn("mac: 'redacted:", out)
        self.assertNotIn("02:00:00:00:10:01", out)
        self.assertNotIn("tftp", out)

    def test_check_drift_verifies_every_scripted_fix_in_check_mode(self) -> None:
        text = Path(config_drift.__file__).with_name("check-drift.sh").read_text(encoding="utf-8")
        for remote, script in (
            ('"php -- check"', "retire-workstation-targets.php"),
            ('"php -- check"', "restore-dhcp-staticmaps.php"),
            ('"php -- check"', "pfblocker-ip-only.php"),
            ('"/bin/sh -s -- check"', "repair-be-php-generator-mode.sh"),
            ('"/bin/sh -s -- check auto"', "sync-fallback-be-config.sh"),
            ('"php -- check"', "be-drop-own-country.php"),
            ('"php -- check"', "reconcile-pflow.php"),
            ('"/bin/sh -s -- check default_20260824183037"', "exclude-be-from-fallback.sh"),
        ):
            with self.subTest(script=script):
                self.assertIn(f'{remote} "${{here}}/{script}"', text)
        self.assertNotIn("-- apply", text)

    def test_rejects_non_pfsense_input(self) -> None:
        rc, _ = run("<other/>", BASE)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
