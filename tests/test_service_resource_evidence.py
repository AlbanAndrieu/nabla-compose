"""Hermetic resource-catalog evidence tests; no Docker, ZFS or GPU required."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "scripts/truenas/collect-service-resource-evidence.py"
SPEC = importlib.util.spec_from_file_location("service_resource_evidence", SOURCE)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

ID_A = "a" * 64
ID_B = "b" * 64
REF_A = "component:default/defectdojo"
REF_B = "resource:default/mongo"


def test_cpu_memory_collected_in_one_bounded_docker_pass():
    from unittest.mock import patch
    raw = "defectdojo-uwsgi\\t512MiB / 60GiB\\t125.4%\\n"
    with patch.object(MODULE, "command", return_value=raw) as call:
        sample = MODULE.memory_stats()
    assert sample["defectdojo-uwsgi"] == 512 * 1024 ** 2
    assert sample.cpu_pct["defectdojo-uwsgi"] == 125.4
    assert "stats" in call.call_args.args[0]
    assert call.call_args.args[0].count("--no-stream") == 1


def test_cpu_unknown_is_not_reported_as_idle():
    one = [{"id": ID_A, "name": "defectdojo-uwsgi", "entityRef": REF_A}]
    with (
        patch.object(MODULE, "catalog", return_value=({REF_A: "DefectDojo"}, {}, "rev")),
        patch.object(MODULE, "docker_containers", return_value=(one, [], {})),
        patch.object(MODULE, "memory_stats", return_value={"defectdojo-uwsgi": 100}),
        patch.object(MODULE, "writable_layers", return_value=None),
        patch.object(MODULE, "datasets", return_value=None),
        patch.object(MODULE, "gpu_processes", return_value=None),
        patch.object(MODULE, "host_memory", return_value={"status": "unverified"}),
    ):
        report = MODULE.collect()
    service = report["services"][0]
    assert service["cpu"]["status"] == "unverified"
    assert service["cpu"]["usage_pct"] is None
    assert report["coverage"]["running_containers_observed"] == 1
    assert report["coverage"]["unmapped_running_containers"] == 0


def test_unmapped_running_containers_are_reported_without_fake_catalog_joins():
    rows = [{"id": ID_A, "name": "legacy-runner", "entityRef": None}]
    with (
        patch.object(MODULE, "catalog", return_value=({REF_A: "DefectDojo"}, {}, "rev")),
        patch.object(MODULE, "docker_containers", return_value=(rows, ["legacy-runner"], {})),
        patch.object(MODULE, "memory_stats", return_value={"legacy-runner": 300}),
        patch.object(MODULE, "writable_layers", return_value=None),
        patch.object(MODULE, "datasets", return_value=None),
        patch.object(MODULE, "gpu_processes", return_value=None),
        patch.object(MODULE, "host_memory", return_value={"status": "unverified"}),
    ):
        report = MODULE.collect()
    assert report["coverage"]["mapped_running_containers"] == 0
    assert report["coverage"]["unmapped_running_containers"] == 1
    assert report["unmapped_running_containers"][0]["container"] == "legacy-runner"
    assert report["unmapped_running_containers"][0]["cpu_pct"] is None
    assert report["services"][0]["runtime"] == "not_observed"


def test_bounded_storage_and_memory_units():
    assert MODULE.parse_size("1.25GiB") == int(1.25 * 1024**3)
    assert MODULE.parse_size("350MB") == 350_000_000
    assert MODULE.parse_size("0B") == 0
    assert MODULE.parse_size("UNKNOWN") is None


def test_catalog_identity_resolution_uses_exact_labels_only():
    out = "\n".join([
        "\t".join([ID_A, "defectdojo-uwsgi", REF_A, "ix-defectdojo", "defectdojo-uwsgi"]),
        "\t".join([ID_B, "ix-mongo-mongo-1", "", "ix-mongo", "mongo"]),
        "\t".join(["c" * 64, "ambiguous-app", "", "ix-other", "web"]),
    ])
    mapping = {("mongo", "mongo"): {REF_B},
               ("other", "web"): {REF_A, REF_B}}
    with patch.object(MODULE, "command", return_value=out):
        containers, unmapped, _ = MODULE.docker_containers(mapping, {
            REF_A: "DefectDojo", REF_B: "Mongo"
        })
    assert containers[0]["entityRef"] == REF_A
    assert containers[1]["entityRef"] == REF_B
    assert containers[2]["entityRef"] is None
    assert unmapped == ["ambiguous-app"]


def test_unavailable_metric_is_null_not_zero():
    one = [{"id": ID_A, "name": "defectdojo-uwsgi", "entityRef": REF_A}]
    with (
        patch.object(MODULE, "catalog", return_value=({REF_A: "DefectDojo"}, {}, "revision-1")),
        patch.object(MODULE, "docker_containers", return_value=(one, [], {})),
        patch.object(MODULE, "memory_stats", return_value=None),
        patch.object(MODULE, "writable_layers", return_value=None),
        patch.object(MODULE, "datasets", return_value=None),
        patch.object(MODULE, "gpu_processes", return_value=None),
        patch.object(MODULE, "host_memory", return_value={"status": "unverified"}),
    ):
        snapshot = MODULE.collect()
    service = snapshot["services"][0]
    assert service["memory"] == {"status": "unverified", "working_set_bytes": None}
    assert service["gpu"] == {"status": "unverified", "process_memory_bytes": None}
    assert service["storage"]["writable_layer_bytes"] is None
    assert snapshot["collection"]["gpu"] == "unavailable"


def test_dataset_shared_is_not_double_counted_as_service_total():
    containers = [
        {"id": ID_A, "name": "defectdojo-uwsgi", "entityRef": REF_A},
        {"id": ID_B, "name": "ix-mongo-mongo-1", "entityRef": REF_B},
    ]
    with (
        patch.object(MODULE, "catalog", return_value=(
            {REF_A: "DefectDojo", REF_B: "Mongo"}, {}, "rev"
        )),
        patch.object(MODULE, "docker_containers", return_value=(containers, [], {})),
        patch.object(MODULE, "memory_stats", return_value={
            "defectdojo-uwsgi": 300, "ix-mongo-mongo-1": 1500
        }),
        patch.object(MODULE, "writable_layers", return_value={
            "defectdojo-uwsgi": 25, "ix-mongo-mongo-1": 60
        }),
        patch.object(MODULE, "datasets", return_value=[
            ("/mnt/cpool/shared", "cpool/shared", 8000)
        ]),
        patch.object(MODULE, "mounted_datasets", return_value={
            ID_A: {"cpool/shared"}, ID_B: {"cpool/shared"}
        }),
        patch.object(MODULE, "gpu_processes", return_value={ID_B: 512 * 1024**2}),
        patch.object(MODULE, "host_memory", return_value={"status": "unverified"}),
    ):
        snapshot = MODULE.collect()
    a, z = snapshot["services"]
    assert a["entityRef"] == REF_A
    assert a["memory"]["working_set_bytes"] == 300
    assert a["gpu"]["process_memory_bytes"] is None
    assert a["storage"]["writable_layer_bytes"] == 25
    assert a["storage"]["datasets"][0]["shared_by_services"] is True
    assert "total_bytes" not in a["storage"]
    assert z["gpu"]["process_memory_bytes"] == 512 * 1024**2
    assert z["storage"]["datasets"][0]["used_bytes_including_children"] == 8000


def test_docker_inspect_reads_only_mounts_not_secrets():
    out = ID_A + "\t" + json.dumps([
        {"Type": "bind", "Source": "/mnt/cpool/shared/defectdojo"},
        {"Type": "volume", "Source": "/mnt/.ix-apps/docker/volumes/random"},
    ])
    with patch.object(MODULE, "command", return_value=out) as command:
        mounts = MODULE.mounted_datasets(
            [{"id": ID_A, "name": "defectdojo-uwsgi", "entityRef": REF_A}],
            [("/mnt/cpool/shared", "cpool/shared", 400)]
        )
    assert mounts[ID_A] == {"cpool/shared"}
    argv = command.call_args.args[0]
    assert argv[:3] == ["docker", "inspect", "--format"]
    assert "{{json .Mounts}}" in argv[3]
    assert ".Config.Env" not in argv[3]


def test_report_private_permissions_and_no_overwrite(tmp_path):
    folder = tmp_path / "report"
    folder.mkdir(mode=0o700)
    folder.chmod(0o700)
    target = folder / "metrics.json"
    MODULE.write_private(target, {"schema": "nabla-service-resources/v1"})
    assert target.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        MODULE.write_private(target, {"unexpected": True})


def test_public_report_directory_rejected(tmp_path):
    folder = tmp_path / "public"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    with pytest.raises(ValueError):
        MODULE.write_private(folder / "report.json", {})


def test_no_sensitive_env_or_runtime_mutations():
    source = SOURCE.read_text()
    assert "docker\", \"stats\", \"--no-stream" in source
    assert ".Config.Env" not in source
    assert "docker restart" not in source
    assert "app.redeploy" not in source
    assert '"docker", "exec"' not in source
