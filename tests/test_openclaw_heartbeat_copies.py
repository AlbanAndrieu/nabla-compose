"""Private metadata-only heartbeat backup recovery contracts."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/workstation/inspect-openclaw-heartbeat-copies.py"
spec = importlib.util.spec_from_file_location("copies", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class HeartbeatCopiesTests(unittest.TestCase):
    def test_archive_is_not_extracted_or_read(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            paths = [root / "before", root / "old", root / "archive.tar.gz"]
            for file in paths:
                file.write_bytes(b"synthetic-secret-not-to-print")
                file.chmod(0o600)
            report = mod.inventory(*paths)
            self.assertTrue(all(x["state"] == "present" for x in report["sources"]))
            self.assertTrue(all(x["permission_class"] == "private" for x in report["sources"]))
            self.assertNotIn("synthetic-secret", json.dumps(report))
            self.assertFalse(report["archive_extracted"])
            self.assertFalse(report["content_read"])

    def test_archive_0644_is_reported_as_readable_by_others(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "old.tar.gz"
            path.write_bytes(b"non-sensitive fixture")
            path.chmod(0o644)
            record = mod.inspect(path, "archive")
            self.assertEqual(record["permission_class"], "readable_by_others")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(mod.main([
                    "--check", "--before-fix", str(Path(td) / "missing"),
                    "--legacy", str(Path(td) / "missing-legacy"),
                    "--archive", str(path)]), 2)

    def test_symlink_and_missing_safe(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "old"
            link = Path(td) / "link"
            path.write_text("private")
            link.symlink_to(path)
            self.assertEqual(mod.inspect(link, "legacy")["state"], "unsafe_type_or_link")
            self.assertEqual(mod.inspect(Path(td) / "missing", "legacy")["state"], "missing")

    def test_no_copies_is_not_green(self):
        with tempfile.TemporaryDirectory() as td, contextlib.redirect_stdout(io.StringIO()):
            root = Path(td)
            self.assertEqual(mod.main(["--check", "--legacy", str(root / "a"),
                                      "--before-fix", str(root / "b"),
                                      "--archive", str(root / "c")]), 2)

if __name__ == "__main__":
    unittest.main()
