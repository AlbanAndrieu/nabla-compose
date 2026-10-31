from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/audit-zfs-snapshot-retention.sh"
MUTATING = re.compile(
    r"zfs\s+(destroy|snapshot|set|rollback|rename|promote)"
    r"|midclt\s+call\s+\S+\.(create|update|delete|run)",
)


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text("#!/usr/bin/env bash\n" + textwrap.dedent(body))
    path.chmod(0o755)


class ZfsSnapshotRetentionContractTests(unittest.TestCase):
    def test_script_is_read_only(self) -> None:
        self.assertIsNone(MUTATING.search(SCRIPT.read_text(encoding="utf-8")))

    @unittest.skipUnless(shutil.which("fakeroot") and shutil.which("jq"), "fakeroot and jq required")
    def test_reports_uncovered_critical_and_stale_datasets(self) -> None:
        now = int(time.time())
        tasks = [
            {
                "dataset": "cpool/media",
                "recursive": True,
                "enabled": True,
                "lifetime_value": 2,
                "lifetime_unit": "WEEK",
                "schedule": {"minute": "0", "hour": "0", "dom": "*", "month": "*", "dow": "*"},
                "exclude": [],
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp)
            _stub(
                bin_dir,
                "midclt",
                f"""\
                case "$2" in
                  pool.snapshottask.query) echo '{json.dumps(tasks)}' ;;
                  replication.query) echo '[]' ;;
                esac
                """,
            )
            _stub(
                bin_dir,
                "zfs",
                f"""\
                if [[ " $* " == *" snapshot "* ]]; then
                  printf 'cpool/media/photo@a\\t{now - 3600}\\n'
                  printf 'cpool/media/music@a\\t{now - 5 * 86400}\\n'
                else
                  printf 'cpool/backup\\t0\\n'
                  printf 'cpool/media/photo\\t1024\\n'
                  printf 'cpool/media/music\\t2048\\n'
                  printf 'cpool/ix-apps/docker\\t0\\n'
                fi
                """,
            )
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "NO_COLOR": "1"}
            result = subprocess.run(
                ["fakeroot", "bash", str(SCRIPT)],
                capture_output=True,
                text=True,
                env=env,
                check=True,
            )
        output = result.stdout + result.stderr
        self.assertIn("no replication task", output)
        self.assertIn("cpool/backup: CRITICAL dataset without snapshot task", output)
        self.assertIn("cpool/media/photo: 1 snapshots, newest 1 h old", output)
        self.assertIn("cpool/media/music: newest snapshot is 120 h old", output)
        self.assertNotIn("ix-apps", output)
        self.assertIn("3 finding(s)", output)


if __name__ == "__main__":
    unittest.main()
