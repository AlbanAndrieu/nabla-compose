from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/truenas/restore-app-set.sh"
POST_PRA_CORE = ROOT / "config/truenas/restore-post-pra-core-apps.txt"


def test_restore_app_set_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--apps-file" in text
    assert "plan-app-lifecycle-order.py" in text
    assert "verify-app-runtime-health.sh" in text
    assert "--states __NONE__" in text
    assert "start_waves" in text
    assert "refusing blind restart" in text
    assert "dependency barrier" in text
    assert "NABLA_APP_START_WAIT_OVERRIDES" in text
    assert "repair-opensearch-security-permissions.sh" in text
    assert "ensure-docker-socket-proxy-intranet.sh" in text
    assert "verify-pihole-dns-sync.sh" in text
    assert "PREPARE %s storage ownership" in text
    assert "PREPARE %s shared intranet attachment" in text
    assert "VERIFY %s DNS sync dependency contract" in text
    assert "midclt call -j app.start" in text

    assert "systemctl restart docker" not in text
    assert "systemctl restart containerd" not in text
    assert "docker kill" not in text
    assert "pkill" not in text


def test_post_pra_core_restore_set_is_catalog_driven_and_excludes_runtime_drift() -> None:
    active = [
        line.strip()
        for line in POST_PRA_CORE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert set(active) == {"vaultwarden"}
    for native_or_pending in (
        "adguard-home", "grafana", "prometheus", "uptime-kuma", "autokuma"
    ):
        assert native_or_pending not in active


OPTIONAL = ROOT / "config/truenas/restore-optional-apps.txt"
OPTIONAL_SCRIPT = ROOT / "scripts/truenas/restore-optional-apps.sh"


def test_light_restore_excludes_optional_apps_by_default() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'INCLUDE_OPTIONAL=false' in script
    assert '--include-optional' in script
    assert '[[ "${INCLUDE_OPTIONAL}" != true ]]' in script
    assert 'APPS=("${filtered_apps[@]}")' in script
    assert 'restore-optional-apps.sh' in script


def test_optional_app_set_does_not_contain_foundation() -> None:
    apps = {
        line.split("#", 1)[0].strip()
        for line in OPTIONAL.read_text(encoding="utf-8").splitlines()
    } - {""}
    assert {"graylog", "zabbix", "transmission", "lidarr", "radarr", "sonarr"} <= apps
    assert not apps & {
        "traefik", "pihole", "postgres", "redis", "clickhouse",
        "docker-socket-proxy", "kafka", "vaultwarden", "garage",
    }
    script = OPTIONAL_SCRIPT.read_text(encoding="utf-8")
    for option in ("--check", "--stop", "--start"):
        assert option in script
    assert 'is_protected()' in script
    assert 'SKIP in-flight deployment' in script
    assert 'midclt call -j app.stop' in script
    assert 'midclt call -j app.start' in script
    assert 'rm -rf' not in script
