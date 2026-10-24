"""Pure local regressions for the pfSense workstation color renderer."""
from pathlib import Path
import os
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/pfsense/console.sh"


def render(payload: str, mode="compact", color="never", no_color=None):
    env = os.environ.copy()
    env.update(PFSENSE_OUTPUT=mode, PFSENSE_COLOR=color, TERM="xterm-256color")
    env.pop("NO_COLOR", None)
    if no_color:
        env["NO_COLOR"] = no_color
    return subprocess.run(
        ["bash", "-c", 'source "$1"; pfsense_ui_render', "bash", str(HELPER)],
        input=payload, capture_output=True, text=True, env=env, check=False,
    )


class ConsoleContract(unittest.TestCase):
    def test_all_pfsense_bash_scripts_parse(self):
        for script in (ROOT / "scripts/pfsense").glob("*.sh"):
            if script.name == "check-central-crowdsec-bouncer.sh":
                # FreeBSD native POSIX sh.
                continue
            with self.subTest(script=script.name):
                result = subprocess.run(["bash", "-n", str(script)], capture_output=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_non_tty_is_byte_identical(self):
        payload = '=== Unbound ===\n{"result":"OK","private":"token"}\n'
        for mode in ("raw", "auto"):
            with self.subTest(mode=mode):
                response = render(payload, mode=mode, color="always")
                self.assertEqual(response.returncode, 0)
                self.assertEqual(response.stdout, payload)

    def test_color_and_no_color(self):
        data = "=== DNS ===\nWARN: status unknown\n"
        self.assertIn("\x1b[", render(data, color="always").stdout)
        self.assertNotIn("\x1b[", render(data, color="always", no_color="1").stdout)

    def test_rfc5424_oom_redaction(self):
        log = ("=== OOM ===\n<3>1 2026-10-24T02:10:50.474019+02:00 "
               "kernel - - - failed to reclaim memory token=PRIVATE\n")
        output = render(log)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("02:10:50.474019+02:00", output.stdout)
        self.assertIn("1 OOM mentions", output.stdout)
        self.assertNotIn("PRIVATE", output.stdout)

    def test_snort_unknown_collapse_and_verbose(self):
        payload = "=== Snort ===\n" + "source=snort event=snort_update_start timestamp=unknown\n" * 21
        self.assertIn("21 events with unknown timestamps", render(payload).stdout)
        self.assertIn("source=snort", render(payload, mode="verbose").stdout)

    def test_csv_pretty_tty_but_raw_when_redirected(self):
        csv = ("timestamp,available_mib,free_mib,inactive_mib,wired_mib,active_mib,"
               "unbound_pid,unbound_rss_kib,pfblocker_cron_count,php_fpm_rss_kib\n"
               "2026-10-24T02:09:00+0200,220.3,200,20.3,300,400,21619,132000,0,290000\n")
        self.assertIn("available=220.3 MiB", render(csv).stdout)
        self.assertEqual(render(csv, mode="auto").stdout, csv)

    def test_pipefail_preserves_upstream_failure(self):
        env = os.environ | {"PFSENSE_OUTPUT": "compact", "TERM": "dumb"}
        result = subprocess.run(
            ["bash", "-c", 'set -euo pipefail; source "$1"; (exit 17) | pfsense_ui_render', "bash", str(HELPER)],
            capture_output=True, env=env, check=False,
        )
        self.assertEqual(result.returncode, 17)


if __name__ == "__main__":
    unittest.main()
