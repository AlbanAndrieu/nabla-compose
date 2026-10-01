"""Unit tests for DSOMM baseline CSV summarization."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "dsomm" / "baseline" / "summarize.py"
SPEC = importlib.util.spec_from_file_location("dsomm_summary", MODULE_PATH)
assert SPEC and SPEC.loader
summary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(summary)


class DsommBaselineSummaryTests(unittest.TestCase):
    def test_classification_matches_upstream_result_semantics(self) -> None:
        self.assertEqual("manual", summary.classify("Not Supported - Manual Process"))
        self.assertEqual("gap", summary.classify("Not detected"))
        self.assertEqual("gap", summary.classify("Error: forbidden"))
        self.assertEqual("detected", summary.classify("Dependabot config found"))

    def test_summary_separates_detected_gaps_and_manual_evidence(self) -> None:
        csv_text = """Security Feature,AlbanAndrieu/nabla-compose
Automated PRs for patches,Dependabot or Renovate PRs detected
SBOM of components,Not detected
Security code review,Not Supported - Manual Process
LEVEL1 Score,3/3
Total Score,16/30
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "baseline.csv"
            md_path = root / "baseline.md"
            csv_path.write_text(csv_text, encoding="utf-8")

            context_path = root / "contexts.yaml"
            context_path.write_text(
                "repositories:\n"
                "  AlbanAndrieu/nabla-compose: Nabla Homelab Platform\n",
                encoding="utf-8",
            )

            summary.summarize(csv_path, md_path, context_path)
            text = md_path.read_text(encoding="utf-8")

        self.assertIn("not an OWASP DSOMM maturity verdict", text)
        self.assertIn("AlbanAndrieu/nabla-compose → Nabla Homelab Platform", text)
        self.assertIn("DSOMM context", text)
        self.assertIn("Detected automated evidence", text)
        self.assertIn("Automated PRs for patches", text)
        self.assertIn("Automated gaps / unavailable evidence", text)
        self.assertIn("SBOM of components", text)
        self.assertIn("Manual DSOMM evidence required", text)
        self.assertIn("Security code review", text)
        self.assertIn("LEVEL1 Score", text)
        self.assertIn("16/30", text)

    def test_invalid_context_map_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context_path = root / "contexts.yaml"
            context_path.write_text("repositories: []\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                summary.load_context_map(context_path)

    def test_invalid_header_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            csv_path = root / "baseline.csv"
            md_path = root / "baseline.md"
            csv_path.write_text("unexpected,value\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                summary.summarize(csv_path, md_path)


if __name__ == "__main__":
    unittest.main()
