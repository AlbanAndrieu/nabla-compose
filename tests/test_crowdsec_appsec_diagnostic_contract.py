"""Contract: AppSec diagnostic is read-only and distinguishes metrics from blocking."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/diagnose-crowdsec-appsec.sh"


def test_appsec_runtime_diagnostic_is_non_mutating_and_has_clear_limitations():
    script = SCRIPT.read_text(encoding="utf-8")
    assert "docker exec crowdsec cscli collections list" in script
    assert "docker exec crowdsec cscli metrics show appsec" in script
    assert "docker port crowdsec 7422/tcp" in script
    assert "appsec_waf_request_block=NOT_VERIFIED_REQUIRES_CONTROLLED_CANARY_TEST" in script
    for unsafe in ("docker run ", "cscli decisions add", "cscli decisions delete",
                   "docker exec crowdsec cscli collections install",
                   "docker compose up", "docker restart", "curl -k"):
        assert unsafe not in script
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, check=False).returncode == 0
