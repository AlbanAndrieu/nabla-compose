"""Offline contract test of the pfSense freeze flight recorder."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/pfsense"
WRAPPER = SCRIPTS / "freeze-capture.sh"
REMOTE = SCRIPTS / "freeze-capture-remote.sh"


class FreezeCaptureTest(unittest.TestCase):
    def test_both_parts_parse(self) -> None:
        subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
        if shutil.which("sh"):
            subprocess.run(["sh", "-n", str(REMOTE)], check=True)

    def test_remote_part_is_read_only(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        # A write on pfSense or a syslog call could block exactly like the processes under study.
        self.assertNotRegex(code, r"(?<![0-9|])>{1,2}\s*[/\w$]")
        # Process names such as php_pfb or php-fpm are only read; running any of these commands is not.
        self.assertNotRegex(code, r"(?m)(^|[\s;&|(])(logger|rm|kill|pkill|php|pfctl|service|reboot|shutdown)(\s|$)")

    def test_remote_commands_are_bounded(self) -> None:
        code = REMOTE.read_text(encoding="utf-8")
        for command in ("ps -axo", "procstat -kk", "netstat -f unix", "sysctl vm.stats", "iostat -x", "dmesg", "mmc extcsd read"):
            self.assertRegex(code, rf"timeout 10 {re.escape(command)}")

    def test_wrapper_waits_for_a_real_banner_and_streams_to_the_workstation(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("grep -q '^SSH-2.0'", text)
        self.assertIn('< "${here}/freeze-capture-remote.sh" | tee -a "${out}"', text)
        self.assertIn("StrictHostKeyChecking=yes", text)


if __name__ == "__main__":
    unittest.main()
