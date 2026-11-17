"""Offline contract of the boot-window helpers: eMMC wear reading and the apply sequence."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/pfsense"
EMMC = SCRIPTS / "emmc-health.sh"
WRAPPER = SCRIPTS / "boot-window-apply.sh"
# Shape of `mmc extcsd read` (mmc-utils) for the fields the script keeps.
EXTCSD = """eMMC Life Time Estimation A [EXT_CSD_DEVICE_LIFE_TIME_EST_TYP_A]: {a}
eMMC Life Time Estimation B [EXT_CSD_DEVICE_LIFE_TIME_EST_TYP_B]: {b}
eMMC Pre EOL information [EXT_CSD_PRE_EOL_INFO]: {e}
"""


class EmmcHealthTest(unittest.TestCase):
    def run_emmc(self, mode: str, extcsd: str | None) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="nabla-emmc-") as tmp:
            bin_dir = Path(tmp)
            if extcsd is not None:
                stub = bin_dir / "mmc"
                stub.write_text(f"#!/bin/sh\ncat <<'EOF'\n{extcsd}EOF\n", encoding="utf-8")
                stub.chmod(0o755)
            path = f"{bin_dir}:/usr/bin:/bin" if extcsd is not None else f"{bin_dir}:/nonexistent"
            env = {**os.environ, "PATH": path}
            return subprocess.run([shutil.which("sh") or "/bin/sh", str(EMMC), mode], capture_output=True,
                                  text=True, env=env, check=False)

    def test_healthy_worn_and_eol_readings(self) -> None:
        ok = self.run_emmc("check", EXTCSD.format(a="0x01", b="0x02", e="0x01"))
        self.assertIn("INFO: life_used_A=0x01 life_used_B=0x02 pre_eol=0x01", ok.stdout)
        self.assertIn("OK: wear indicators below warning levels", ok.stdout)
        worn = self.run_emmc("check", EXTCSD.format(a="0x0b", b="0x03", e="0x01"))
        self.assertIn("WARN: over 80 % of rated life used", worn.stdout)
        eol = self.run_emmc("check", EXTCSD.format(a="0x02", b="0x02", e="0x03"))
        self.assertIn("WARN: pre_eol=urgent", eol.stdout)

    def test_check_without_mmc_utils_installs_nothing(self) -> None:
        result = self.run_emmc("check", None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INFO: mmc-utils absent", result.stdout)
        self.assertNotIn("CHANGE", result.stdout)

    def test_unknown_mode_is_refused(self) -> None:
        self.assertEqual(self.run_emmc("install", None).returncode, 2)


class BootWindowWrapperTest(unittest.TestCase):
    def test_wrapper_parses_and_orders_the_steps(self) -> None:
        subprocess.run(["bash", "-n", str(WRAPPER)], check=True)
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("grep -q '^SSH-2.0'", text)
        self.assertIn("StrictHostKeyChecking=yes", text)
        order = [text.index(f'"php -- apply" {name}') for name in
                 ("hold-packages-at-boot.php", "stop-default-pass-logging.php", "disable-rrd-graphing.php")]
        self.assertEqual(order, sorted(order))
        # mmc-utils is installed only after the operator plugs the WAN in and confirms.
        self.assertLess(text.index("read -r -p"), text.index('"/bin/sh -s -- apply" emmc-health.sh'))


if __name__ == "__main__":
    unittest.main()
