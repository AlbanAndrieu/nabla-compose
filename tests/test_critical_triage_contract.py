"""Static/offline contracts for bounded TrueNAS seven-gate triage."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/triage-critical-failures.sh"

GATES = (
    "prometheus-targets",
    "prometheus-config-access",
    "openrag-startup",
    "ai-runtime-recovery",
    "openrag-opensearch-legacy-secret",
    "openrag-backstage-bundle",
    "akvorado-fresh-inserts",
)


class CriticalTriageContract(unittest.TestCase):
    def test_shell_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)], capture_output=True, text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_does_not_probe_truenas(self):
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--check", result.stdout)
        self.assertNotIn("Private evidence:", result.stdout)

    def test_unknown_and_mutating_modes_are_denied(self):
        for args in (("--apply",), ("--check", "--apply"), ("--up",)):
            with self.subTest(args=args):
                result = subprocess.run(
                    ["bash", str(SCRIPT), *args],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Private evidence:", result.stdout)

    def test_color_and_icon_flags_are_wired_without_coloring_tsv(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('source "$UI_LIB"', source)
        self.assertIn('diag_ui_init "$COLOR_MODE" "$ICON_MODE"', source)
        self.assertIn("--no-color)", source)
        self.assertIn("--no-icons)", source)
        self.assertIn("diag_ok \"$gate\"", source)
        self.assertIn("diag_fail \"$gate (see private report)\"", source)
        self.assertIn("diag_unknown \"$gate (no conclusive evidence)\"", source)
        self.assertIn('printf \'%s\\t%s\\t%s\\t%s\\n\' "$gate"', source)

    def test_terminal_colors_can_be_forced_or_disabled_without_a_tty(self):
        ui = ROOT / "scripts/lib/diagnostic-ui.sh"
        source = (
            'source "$1"; diag_ui_init "$2" "$3"; diag_ok "synthetic"'
        )
        for color, icons, no_color, expected_ansi, expected_icon in (
            ("always", "always", False, True, True),
            ("always", "always", True, False, True),
            ("never", "never", False, False, False),
        ):
            with self.subTest(color=color, icons=icons, no_color=no_color):
                import os

                env = os.environ.copy()
                env.pop("NO_COLOR", None)
                if no_color:
                    env["NO_COLOR"] = "1"
                result = subprocess.run(
                    ["bash", "-c", source, "_", str(ui), color, icons],
                    env=env, capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual("\\x1b[" in result.stdout, expected_ansi)
                self.assertEqual("✅" in result.stdout, expected_icon)


    def test_exactly_seven_read_only_checks(self):
        source = SCRIPT.read_text(encoding="utf-8")
        found = re.findall(r"^run_gate ([a-z0-9-]+) ", source, re.M)
        self.assertEqual(tuple(found), GATES)
        self.assertIn("--scope openrag", source)
        self.assertIn("--require-inserts --observe-seconds 30", source)
        self.assertIn("repair-prometheus-config-access.sh --check", source)
        self.assertNotRegex(source, re.compile(r"^\s+(?:midclt call app\.(?:start|redeploy)|docker compose up|rm -rf)", re.M))

    def test_private_evidence_and_unknown_are_not_pass(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("umask 077", source)
        self.assertIn('chmod 0600 -- "$SUMMARY"', source)
        self.assertIn('chmod 0600 -- "$log"', source)
        self.assertIn("2|124) status=UNVERIFIED", source)
        self.assertIn("((failed == 0 && unverified == 0))", source)


if __name__ == "__main__":
    unittest.main()
