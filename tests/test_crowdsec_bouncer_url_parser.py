"""Hermetic pfSense AWK parser tests: do not confuse quoted YAML with URL drift."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/workstation/verify-crowdsec-pfsense.sh"


def parser_program():
    source = SCRIPT.read_text(encoding="utf-8")
    start = "api_url=\"$(\n    awk '\n"
    end = "\n    ' "
    assert source.count(start) == 1, "pfSense api_url awk block moved"
    return source.split(start, 1)[1].split(end, 1)[0]


class CrowdsecBouncerUrlParserTests(unittest.TestCase):
    def parse(self, yaml_line):
        process = subprocess.run(
            ["awk", parser_program()],
            input=yaml_line + "\n",
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        return process.stdout.strip()

    def test_double_quoted_local_url(self):
        self.assertEqual(self.parse('api_url: "http://172.17.0.1:8089"'), "http://172.17.0.1:8089")

    def test_single_quoted_local_url(self):
        self.assertEqual(self.parse("api_url: 'http://172.17.0.1:8089'"), "http://172.17.0.1:8089")

    def test_unquoted_central_url(self):
        self.assertEqual(self.parse("api_url: http://172.17.0.24:8084"), "http://172.17.0.24:8084")

    def test_indented_url_with_trailing_spaces(self):
        self.assertEqual(self.parse("  api_url: 'http://172.17.0.24:8084'   "), "http://172.17.0.24:8084")

    def test_missing_url_stays_empty(self):
        self.assertEqual(self.parse("api_key: REDACTED"), "")


if __name__ == "__main__":
    unittest.main()
