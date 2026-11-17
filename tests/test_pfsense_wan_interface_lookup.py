"""The Snort posture checks read the WAN device from config.xml instead of hard-coding the 1100's mvneta0.4090."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/pfsense"
CONFIG = """<?xml version="1.0"?>
<pfsense>
\t<interfaces>
\t\t<lan>
\t\t\t<if>{lan}</if>
\t\t</lan>
\t\t<wan>
\t\t\t<enable></enable>
\t\t\t<if>{wan}</if>
\t\t\t<ipaddr>192.0.2.10</ipaddr>
\t\t</wan>
\t</interfaces>
\t<installedpackages><snortglobal><rule><interface>wan</interface><if>wrong0</if></rule></snortglobal></installedpackages>
</pfsense>
"""


@unittest.skipUnless(shutil.which("awk"), "awk is required")
class WanInterfaceLookupTest(unittest.TestCase):
    def test_both_scripts_resolve_the_wan_device(self) -> None:
        for name in ("audit-posture.sh", "diagnose-recover.sh"):
            text = (SCRIPTS / name).read_text(encoding="utf-8")
            self.assertNotIn("mvneta0.4090/snort.conf", text, name)
            program = re.search(r"awk '(/<interfaces>/[^']+)' /conf/config.xml", text)
            self.assertIsNotNone(program, name)
            for lan, wan in (("mvneta0.4091", "mvneta0.4090"), ("igc1", "igc0")):
                with tempfile.NamedTemporaryFile("w", suffix=".xml") as cfg:
                    cfg.write(CONFIG.format(lan=lan, wan=wan))
                    cfg.flush()
                    out = subprocess.run(["awk", program.group(1), cfg.name], capture_output=True, text=True, check=True)
                self.assertEqual(out.stdout.strip(), wan, name)


if __name__ == "__main__":
    unittest.main()
