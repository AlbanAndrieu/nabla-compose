"""Runtime dotenv quoting: read like Compose, normalize without changing a value, never print one."""
import ast
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/secrets/audit_dotenv_quoting.py"
spec = importlib.util.spec_from_file_location("audit_dotenv_quoting", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
COPIES = (
    "scripts/truenas/provision-openclaw-litellm-keys.py",
    "scripts/truenas/ensure-openclaw-coder-key.py",
    "scripts/truenas/ensure-litellm-metrics-key.py",
    "scripts/secrets/emergency_revoke.py",
)


def function_source(path, name="dotenv_value"):
    text = path.read_text(encoding="utf-8")
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)


class DotenvValue(unittest.TestCase):
    def test_reads_values_like_compose(self):
        cases = {
            'sk-a': "sk-a", '"sk-a"': "sk-a", "'sk-a'": "sk-a",
            '"sk-a" # rotated 2026-10-30': "sk-a", "'sk-a'   #note": "sk-a",
            "sk-a # note": "sk-a", "sk-a#b": "sk-a#b", "": "", '""': "",
        }
        for raw, value in cases.items():
            self.assertEqual(module.dotenv_value(raw), value, raw)

    def test_ambiguous_lines_fail_closed(self):
        for raw in ('"sk-a', '"sk-a"x', "'let\\'s'", '"a\\"b"'):
            self.assertIsNone(module.dotenv_value(raw), raw)

    def test_inline_copies_stay_identical(self):
        reference = function_source(SCRIPT)
        for copy in COPIES:
            self.assertEqual(function_source(ROOT / copy), reference, copy)


class Normalize(unittest.TestCase):
    def test_moves_comment_and_drops_needless_quotes_only(self):
        text = (
            "# header\n"
            'MAIN="sk-main" # openclaw main\n'
            "PLAIN=sk-plain\n"
            "SPACED='two words'\n"
            'NEEDLESS="sk-x"\n'
            "  export DOMAIN=\"a.example\" # host\n"
            'BROKEN="sk-broken\n'
        )
        new, findings = module.normalize(text)
        self.assertEqual(new, (
            "# header\n"
            "# openclaw main\nMAIN=sk-main\n"
            "PLAIN=sk-plain\n"
            "SPACED='two words'\n"
            "NEEDLESS=sk-x\n"
            "  # host\n  export DOMAIN=a.example\n"
            'BROKEN="sk-broken\n'
        ))
        self.assertEqual(findings, [("MAIN", "inline_comment"), ("NEEDLESS", "unnecessary_quotes"),
                                    ("DOMAIN", "inline_comment"), ("BROKEN", "malformed")])
        self.assertEqual({k: v for k, v in module.values(new).items() if k != "BROKEN"},
                         {k: v for k, v in module.values(text).items() if k != "BROKEN"})

    def test_clean_file_is_untouched(self):
        text = "A=sk-a\nB='x y'\n"
        self.assertEqual(module.normalize(text), (text, []))


class Run(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / "openclaw/.env.secrets"
        self.file.parent.mkdir()
        self.file.write_text('KEY="sk-SYNTHETIC-VALUE" # comment\n')
        self.file.chmod(0o600)
        (self.root / "openclaw/.env.secrets.bak-old").write_text('OLD="x" # skipped\n')

    def run_script(self, apply):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            code = module.run(apply, self.root)
        return code, output.getvalue()

    def test_check_reports_names_only_and_writes_nothing(self):
        before = self.file.read_text()
        code, output = self.run_script(False)
        self.assertEqual(code, 1)
        self.assertIn("KEY inline_comment", output)
        self.assertNotIn("SYNTHETIC", output)
        self.assertNotIn("OLD", output)
        self.assertEqual(self.file.read_text(), before)

    def test_apply_normalizes_with_private_backup(self):
        code, output = self.run_script(True)
        self.assertEqual(code, 0)
        self.assertNotIn("SYNTHETIC", output)
        self.assertEqual(self.file.read_text(), "# comment\nKEY=sk-SYNTHETIC-VALUE\n")
        self.assertEqual(os.stat(self.file).st_mode & 0o777, 0o600)
        backups = [p for p in self.file.parent.iterdir() if p.name.startswith(".env.secrets.bak-2")]
        self.assertEqual(len(backups), 1)
        self.assertEqual(os.stat(backups[0]).st_mode & 0o777, 0o600)
        self.assertEqual(self.run_script(False)[0], 0)


if __name__ == "__main__":
    unittest.main()
