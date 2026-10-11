"""Read-only post-reboot DSOMM contract tests."""

import importlib.util
from pathlib import Path
import subprocess
from unittest.mock import patch
from io import BytesIO
from email.message import Message

import pytest
import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/truenas/check-dsomm-post-reboot.py"
spec = importlib.util.spec_from_file_location("dsomm_post_reboot", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class Response:
    status = 200

    def __init__(self, content: bytes, content_type: str = "") -> None:
        self.buffer = BytesIO(content)
        self.headers = Message()
        if content_type:
            self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, length):
        return self.buffer.read(length)


def fake_yaml(url: str, timeout: float = 8.0):
    name = url.split("/assets/YAML/", 1)[1]
    docs = {
        "meta.yaml": {"teams": ["Nabla Platform", "Nabla Applications"]},
        "default/model.yaml": {"version": "5.0.2"},
        "team-progress.yaml": {"progress": {"uuid-1": {"Nabla Platform": {"Started": "2026-10-04"}, "Nabla Applications": {"Started": "2026-10-04"}}}},
        "team-evidence.yaml": {"evidence": {"uuid-1": [{"id": "example"}]}},
    }
    if name == "default/model.yaml":
        return Response(b"meta:\n  version: 5.0.2\n---\nAgentic AI:\n  Data Protection: {}\n")
    return Response(yaml.safe_dump(docs[name]).encode())


def test_reject_html_fallback() -> None:
    with patch.object(module, "urlopen", return_value=Response(b"<html>SPA</html>", "text/html")):
        with pytest.raises(ValueError, match="HTML fallback"):
            module.probe("http://example.test")


def test_accept_populated_assessment() -> None:
    with patch.object(module, "urlopen", side_effect=fake_yaml):
        module.probe("http://example.test")


def test_reject_empty_progress() -> None:
    def empty_progress(url: str, timeout: float = 8.0):
        if url.endswith("/team-progress.yaml"):
            return Response(b"progress: {}\n")
        return fake_yaml(url, timeout=timeout)

    with patch.object(module, "urlopen", side_effect=empty_progress):
        with pytest.raises(ValueError, match="progression is empty"):
            module.probe("http://example.test")


def test_reboot_hook_keeps_existing_gates() -> None:
    source = (SCRIPT.parent / "reboot-homelab.sh").read_text()
    assert 'DSOMM_POST_REBOOT_CHECK=' in source
    assert 'python3 "${DSOMM_POST_REBOOT_CHECK}"' in source
    assert 'python3 "${FASTAPI_REBOOT_DIAGNOSTIC}"' in source
    assert 'python3 "${INGRESS_ROUTE_AUDIT}" --strict' in source
    assert subprocess.run(["bash", "-n", str(SCRIPT.parent / "reboot-homelab.sh")], check=False).returncode == 0


def test_reject_ambiguous_model_documents() -> None:
    def ambiguous(url: str, timeout: float = 8.0):
        if url.endswith("/default/model.yaml"):
            return Response(b"meta:\n  version: 5.0.2\n---\nmeta:\n  version: 5.0.2\n---\nAgentic AI: {}\n")
        return fake_yaml(url, timeout=timeout)

    with patch.object(module, "urlopen", side_effect=ambiguous):
        with pytest.raises(ValueError, match="exactly one matching"):
            module.probe("http://example.test")
