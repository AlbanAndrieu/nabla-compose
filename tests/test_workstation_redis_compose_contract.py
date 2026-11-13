from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workstation_redis_refuses_to_start_without_its_password() -> None:
    compose = (ROOT / "compose.redis.yml").read_text(encoding="utf-8")

    # A ${REDIS_AUTH:-...} default is a password committed to git.
    assert "REDIS_AUTH:-" not in compose
    assert "--requirepass ${REDIS_AUTH:?REDIS_AUTH is required}" in compose
    assert 'redis-cli -a "$${REDIS_AUTH}" ping' in compose
    assert '"127.0.0.1:6379:6379"' in compose
