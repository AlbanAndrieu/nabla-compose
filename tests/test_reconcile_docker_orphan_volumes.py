"""Offline tests for the orphan Docker volume plan/apply (fakeroot + stubbed docker)."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/reconcile-docker-orphan-volumes.sh"
ANON_SMALL = "a" * 64
ANON_LARGE = "b" * 64
ANON_RECENT = "c" * 64
DAY = 86400


class StaticContractTests(unittest.TestCase):
    def test_never_prunes_or_forces(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("volume prune", source.replace("Never `docker volume prune`", ""))
        self.assertNotIn("system prune", source)
        self.assertNotIn("volume rm -f", source)
        self.assertNotIn("volume rm --force", source)
        self.assertIn("NABLA_VOLUME_PURGE_APPROVED", source)


@unittest.skipUnless(shutil.which("fakeroot"), "fakeroot required")
class ReconcileOrphanVolumesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.log = self.tmp / "docker.log"
        self.volumes = self.tmp / "volumes"
        self.app_configs = self.tmp / "app_configs"
        (self.app_configs / "wazuh").mkdir(parents=True)
        now = 2_000_000_000
        # name, project, volume, bytes, age_days
        rows = [
            (ANON_SMALL, "", "", 4096, 30),
            (ANON_LARGE, "", "", 5 * 1024**3, 30),
            (ANON_RECENT, "", "", 10, 1),
            ("ix-wazuh_wazuh_indexer_data", "ix-wazuh", "wazuh_indexer_data", 10, 30),
            ("ix-wizarr_data", "ix-wizarr-gone", "data", 10, 30),
            ("manual-volume", "", "", 10, 30),
        ]
        listing, sizes, ages = [], [], []
        for name, project, volume, size, age in rows:
            mount = self.volumes / name / "_data"
            listing.append(f"{name}\t{mount}\t{project}\t{volume}")
            sizes.append(f'"{mount}") echo "{size}\t{mount}" ;;')
            ages.append(f'"{mount.parent}") echo {now - age * DAY} ;;')
        (self.tmp / "listing.tsv").write_text("\n".join(listing) + "\n")
        self.stub("date", f'[[ "$1" == "+%s" ]] && echo {now} || /bin/date "$@"')
        self.stub("du", 'case "${@: -1}" in\n' + "\n".join(sizes) + '\n*) echo "1\t${@: -1}" ;;\nesac')
        self.stub("stat", 'case "${@: -1}" in\n' + "\n".join(ages) + "\nesac")
        self.stub(
            "docker",
            textwrap.dedent(
                f"""\
                echo "$*" >> {self.log}
                if [[ "$1 $2" == "volume ls" && "$*" == *--format* ]]; then cat {self.tmp}/listing.tsv; exit 0; fi
                if [[ "$1 $2" == "volume ls" ]]; then cut -f1 {self.tmp}/listing.tsv; exit 0; fi
                if [[ "$1 $2" == "volume rm" ]]; then exit 0; fi
                exit 1
                """
            ),
        )
        self.plan = self.tmp / "plan.tsv"

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash\n" + body + "\n")
        path.chmod(0o755)

    def run_script(self, *args: str, approved: bool = False) -> subprocess.CompletedProcess:
        env = {
            **os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}",
            "NO_COLOR": "1",
            "NABLA_APP_CONFIGS_DIR": str(self.app_configs),
        }
        if approved:
            env["NABLA_VOLUME_PURGE_APPROVED"] = "yes"
        return subprocess.run(
            ["fakeroot", "bash", str(SCRIPT), *args],
            env=env, text=True, capture_output=True, timeout=30, check=False,
        )

    def plan_rows(self) -> dict[str, str]:
        return {line.split("\t")[1]: line.split("\t")[0] for line in self.plan.read_text().splitlines()}

    def test_plan_classifies_and_removes_nothing(self):
        result = self.run_script("--plan", str(self.plan))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.plan_rows(),
            {
                ANON_SMALL: "candidate:anonymous",
                ANON_LARGE: "review:large",
                ANON_RECENT: "review:recent",
                "ix-wazuh_wazuh_indexer_data": "keep:installed-app",
                "ix-wizarr_data": "candidate:removed-app",
                "manual-volume": "review:named",
            },
        )
        self.assertEqual(oct(self.plan.stat().st_mode & 0o777), "0o600")
        self.assertNotIn("volume rm", self.log.read_text())

    def test_plan_larger_than_a_pipe_buffer_exits_zero(self):
        # 10/11 on TrueNAS: 725 rows made `sort | head -15` die of SIGPIPE under pipefail.
        extra = "".join(f"{i:064x}\t{self.volumes}/{i:064x}/_data\t\t\n" for i in range(1, 901))
        with (self.tmp / "listing.tsv").open("a") as listing:
            listing.write(extra)
        result = self.run_script("--plan", str(self.plan))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing removed", result.stdout + result.stderr)
        self.assertEqual(len(self.plan.read_text().splitlines()), 906)

    def test_apply_requires_approval(self):
        self.run_script("--plan", str(self.plan))
        result = self.run_script("--apply", str(self.plan))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NABLA_VOLUME_PURGE_APPROVED=yes", result.stdout + result.stderr)
        self.assertNotIn("volume rm", self.log.read_text())

    def test_apply_removes_only_candidates_without_force(self):
        self.run_script("--plan", str(self.plan))
        result = self.run_script("--apply", str(self.plan), approved=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        removed = [line for line in self.log.read_text().splitlines() if line.startswith("volume rm")]
        self.assertEqual(removed, [f"volume rm -- {ANON_SMALL}", "volume rm -- ix-wizarr_data"])
        self.assertIn("removed=2 skipped=0 failed=0", result.stdout)


if __name__ == "__main__":
    unittest.main()
