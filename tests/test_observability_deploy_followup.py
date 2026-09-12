from __future__ import annotations

import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyroscope_diagnostic_is_read_only_and_executable() -> None:
    path = ROOT / "scripts" / "truenas" / "diagnose-pyroscope.sh"
    script = path.read_text(encoding="utf-8")
    mode = path.stat().st_mode

    assert mode & stat.S_IXUSR
    assert "http://127.0.0.1:4040/ready" in script
    assert "docker inspect" in script
    assert "docker logs --tail 200" in script
    assert "v2/metastore/raft" in script
    assert "v2/metastore/data" in script
    assert "READ-ONLY" in script
    assert "docker restart" not in script
    assert "docker rm" not in script
    assert "app.redeploy" not in script
    assert "rm -rf" not in script


def test_fastapi_deploy_retries_only_transient_buildkit_frontend_failure() -> None:
    script = (ROOT / "scripts" / "truenas" / "update-fastapi-sample.sh").read_text(
        encoding="utf-8",
    )

    assert "build_fastapi_sample" in script
    assert "frontend grpc server closed unexpectedly" in script
    assert "retrying the same cache-preserving build once" in script
    assert "existing runtime was not replaced" in script
    assert "builder prune" not in script
    assert "buildx prune" not in script
    assert "DOCKER_BUILDKIT=0" not in script
    assert script.index("build_fastapi_sample") < script.index(
        "Removing the previous FastAPI Sample container after successful build",
    )
