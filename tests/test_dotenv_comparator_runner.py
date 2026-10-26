"""Hermetic comparator-runner tests: never read TrueNAS secrets or need root."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "scripts" / "truenas" / "bootstrap-repository-env-files.sh"


def comparator_shell_function() -> str:
    text = BOOTSTRAP.read_text(encoding="utf-8")
    start = text.index("env_files_equivalent() {\n")
    end = text.index("\ncanonical_env_file() {", start)
    return text[start:end]


class DotenvComparatorRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.bin_dir = root / "bin"
        self.bin_dir.mkdir()
        self.home = root / "operator-home"
        self.venv_python = self.home / ".cache/nabla-compose/dev-venv/bin/python"
        self.venv_python.parent.mkdir(parents=True)
        self.comparator = root / "comparator.py"
        self.comparator.write_text("# fixture only\n", encoding="utf-8")
        self.left = root / "left.env"
        self.right = root / "right.env"
        self.left.write_text("KEY=left-secret\n", encoding="utf-8")
        self.right.write_text("KEY=right-secret\n", encoding="utf-8")

        # The system python3 cannot import dotenv; the unprivileged user venv can.
        self.make_executable(self.bin_dir / "python3", "#!/bin/sh\nexit 1\n")
        self.make_executable(
            self.bin_dir / "getent",
            "#!/bin/sh\n"
            'printf "fakeuser:x:1001:1001::%s:/bin/sh\\n" "$FAKE_HOME"\n',
        )
        self.make_executable(
            self.bin_dir / "sudo",
            "#!/bin/sh\n"
            '[ "$1" = "-H" ] && [ "$2" = "-u" ] && '
            '[ "$3" = "fakeuser" ] && [ "$4" = "--" ] || exit 55\n'
            'shift 4\nexec "$@"\n',
        )
        self.make_executable(
            self.venv_python,
            "#!/bin/sh\n"
            '[ "$1" = "-c" ] && exit 0\n'
            'exit "${FAKE_COMPARE_RESULT:-0}"\n',
        )

    @staticmethod
    def make_executable(path: Path, payload: str) -> None:
        path.write_text(payload, encoding="utf-8")
        path.chmod(0o700)

    def invoke(
        self,
        expected_comparison_code: int,
        *,
        operator: str = "fakeuser",
        equal_files: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self.bin_dir}:/usr/bin:/bin",
            "SUDO_USER": operator,
            "FAKE_HOME": str(self.home),
            "FAKE_COMPARE_RESULT": str(expected_comparison_code),
        }
        command = (
            "set -euo pipefail\n"
            f"DOTENV_COMPARE={self.comparator}\n"
            f"{comparator_shell_function()}\n"
            f"env_files_equivalent demo {self.left} "
            f"{self.left if equal_files else self.right}\n"
        )
        return subprocess.run(
            ["bash", "-c", command],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_operator_venv_comparator_exit_codes_remain_distinct(self) -> None:
        for code in (0, 1, 2):
            with self.subTest(code=code):
                result = self.invoke(code)
                self.assertEqual(result.returncode, code, result.stderr)
                if code == 2:
                    self.assertIn("BLOCKED", result.stderr)
                else:
                    self.assertNotIn("BLOCKED", result.stderr)
                self.assertNotIn("left-secret", result.stderr)
                self.assertNotIn("right-secret", result.stderr)

    def test_missing_operator_identity_fails_closed(self) -> None:
        result = self.invoke(0, operator="")
        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED", result.stderr)

    def test_byte_identical_files_do_not_need_python(self) -> None:
        result = self.invoke(0, operator="", equal_files=True)
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("BLOCKED", result.stderr)


if __name__ == "__main__":
    unittest.main()
