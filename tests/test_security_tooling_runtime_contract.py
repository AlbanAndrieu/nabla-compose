from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "config" / "secrets" / "manifest.json"
DEPLOY = ROOT / "scripts" / "truenas" / "deploy-security-tooling.sh"
PREPARE = ROOT / "scripts" / "truenas" / "prepare-security-tooling-secrets.sh"
POSTGRES = ROOT / "scripts" / "truenas" / "bootstrap-security-tooling-postgres.sh"
HEALTH = ROOT / "scripts" / "truenas" / "verify-app-runtime-health.sh"
RECONCILE = ROOT / "scripts" / "truenas" / "reconcile-reboot-resume.sh"
TRUENAS_LIB = ROOT / "scripts" / "lib" / "truenas.sh"
SECRETS_LIB = ROOT / "scripts" / "lib" / "secrets.sh"
PLANNER = ROOT / "scripts" / "truenas" / "plan-app-lifecycle-order.py"
SERVICES = ROOT / "catalog" / "services.json"
TOPOLOGY = ROOT / "catalog" / "service-topology.json"

PERSISTENT = {"plumber", "netbox", "dependency-track", "defectdojo", "neo4j"}
MANUAL = {"cartography", "scorecard"}


def test_security_tooling_is_in_vaultwarden_manifest() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = {item["app"]: item for item in data["items"]}

    for app in PERSISTENT | MANUAL:
        assert app in items
        assert items[app]["item"] == f"nabla/prod/{app}"
        assert items[app]["secrets"]


def test_runtime_orchestrator_separates_persistent_apps_from_manual_jobs() -> None:
    script = DEPLOY.read_text(encoding="utf-8")

    assert "PERSISTENT_APPS=(plumber netbox dependency-track defectdojo neo4j)" in script
    assert "MANUAL_APPS=(cartography scorecard)" in script
    assert "--profile manual config" in script
    assert "not registered as an always-on TrueNAS App" in script
    assert "truenas_reconcile_custom_app" in script
    assert "verify-app-runtime-health.sh" in script
    assert "bootstrap-security-tooling-postgres.sh" in script


def test_secret_preparation_supports_vaultwarden_parity() -> None:
    script = PREPARE.read_text(encoding="utf-8")
    helpers = SECRETS_LIB.read_text(encoding="utf-8")

    assert "--check | --apply | --verify-vaultwarden | --import-env | --import-env-apply" in script
    assert "render_from_bitwarden.py" in script
    assert "import_env_to_bitwarden.py" in script
    assert "--import-env-apply" in script
    assert 'python3 scripts/secrets/materialize_runtime.py --app "${app}" --verify' in script
    assert 'python3 scripts/secrets/materialize_runtime.py --app "${app}" --install' in script
    assert "/mnt/cpool/secrets/runtime/${app}/.env.secrets" in script
    assert "root:root 600" in script
    assert "dsomm" in script
    assert "Never print secret values" in helpers


def test_postgres_bootstrap_is_shared_and_fail_closed() -> None:
    wrapper = POSTGRES.read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "truenas" / "bootstrap-app-postgres.sh").read_text(encoding="utf-8")
    library = (ROOT / "scripts" / "lib" / "postgres.sh").read_text(encoding="utf-8")

    for app in ("plumber", "netbox", "dependency-track", "defectdojo"):
        assert app in wrapper
        assert app in script
    assert 'exec bash "${SCRIPT_DIR}/bootstrap-app-postgres.sh" "${MODE}" "${APP}"' in wrapper
    assert "com.docker.compose.project=ix-postgres" in library
    assert "CREATE ROLE %I LOGIN PASSWORD %L" in library
    assert "ALTER ROLE %I PASSWORD %L" in library
    assert "CREATE DATABASE %I OWNER %I" in library
    assert "ALTER DATABASE %I OWNER TO %I" in library
    assert "dedicated role cannot authenticate" in script


def test_reboot_resume_requires_container_stability() -> None:
    health = HEALTH.read_text(encoding="utf-8")
    reconcile = RECONCILE.read_text(encoding="utf-8")

    assert "RUNNING with stable containers" in health
    assert "healthy | none" in health
    assert "exited" in health
    assert 'if [[ "${exit_code}" != "0" ]]' in health
    assert "verify-app-runtime-health.sh" in reconcile
    assert "middleware RUNNING but container health did not converge" in reconcile
    assert "RUNNING and container-stable" in reconcile


def test_truenas_shared_helpers_cover_reconcile_and_wait() -> None:
    script = TRUENAS_LIB.read_text(encoding="utf-8")

    assert "truenas_app_state()" in script
    assert "truenas_reconcile_custom_app()" in script
    assert "truenas_wait_app_running()" in script
    assert "custom_compose_config_string" in script
    assert "custom_compose_config" in script


def test_lifecycle_planner_orders_shared_data_before_new_persistent_apps() -> None:
    apps = [
        {"id": "postgres", "state": "RUNNING"},
        {"id": "redis", "state": "RUNNING"},
        {"id": "plumber", "state": "RUNNING"},
        {"id": "netbox", "state": "RUNNING"},
        {"id": "dependency-track", "state": "RUNNING"},
        {"id": "defectdojo", "state": "RUNNING"},
        {"id": "neo4j", "state": "RUNNING"},
    ]
    # plumber, netbox and dependency-track are declared ``planned`` (not
    # deployed on TrueNAS yet): the planner suppresses them unless an operator
    # explicitly includes them for a bounded activation test.
    planned = ("plumber", "netbox", "dependency-track")

    def plan_for(*extra: str) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            apps_file = Path(tmp) / "apps.json"
            apps_file.write_text(json.dumps(apps), encoding="utf-8")
            result = subprocess.run(
                [
                    "python3",
                    str(PLANNER),
                    "--apps",
                    str(apps_file),
                    "--services",
                    str(SERVICES),
                    "--topology",
                    str(TOPOLOGY),
                    *extra,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    default_plan = plan_for()
    for app in planned:
        assert default_plan["suppressed_apps_by_status"].get(app) == "planned"
        assert app not in default_plan["start_order"]

    plan = plan_for("--include-apps", ",".join(planned))
    start = plan["start_order"]
    stop = plan["stop_order"]

    for consumer in ("plumber", "netbox", "defectdojo"):
        assert start.index("postgres") < start.index(consumer)
        assert start.index("redis") < start.index(consumer)
    assert start.index("postgres") < start.index("dependency-track")

    assert stop == list(reversed(start))
