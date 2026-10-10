"""Smoke contract for read-only full-service runtime diagnostic."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_standalone_service_diagnostic_is_read_only() -> None:
    path = ROOT / "scripts/truenas/check-homelab-services.sh"
    subprocess.run(["bash", "-n", str(path)], check=True)
    script = path.read_text()
    for required in (
        "midclt call app.query",
        "docker ps",
        "check-dsomm-post-reboot.py",
        "diagnose-fastapi-integrations.py",
        "audit-internal-routes.py",
    ):
        assert required in script
    for forbidden in (
        "app.redeploy", "app.stop", "app.start", "docker restart",
        "rm -rf", "NABLA_REBOOT_MAX_MANIFEST_AGE_SECONDS",
    ):
        assert forbidden not in script


def test_model_parser_supports_upstream_meta_version() -> None:
    script = (ROOT / "scripts/truenas/check-dsomm-post-reboot.py").read_text()
    assert "safe_load_all" in script
    assert 'data["meta"].get("version")' in script
