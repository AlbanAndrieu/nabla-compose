"""The TrueNAS FastAPI Sample build stamps the exact commit it deploys."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_local_build_passes_the_target_commit_as_build_revision() -> None:
    script = (ROOT / "scripts/truenas/update-fastapi-sample.sh").read_text(encoding="utf-8")
    assert 'export FASTAPI_SAMPLE_BUILD_REVISION="${target}"' in script
    build = yaml.safe_load((ROOT / "apps/sample/compose.yml").read_text(encoding="utf-8"))
    args = build["services"]["fastapi-sample"]["build"]["args"]
    # Without it /v2/version reports build_revision=null on TrueNAS (fastapi-sample pass, 21/11).
    assert args["BUILD_REVISION"] == "${FASTAPI_SAMPLE_BUILD_REVISION:-}"
