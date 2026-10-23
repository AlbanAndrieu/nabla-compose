"""Offline safety and concurrency contracts for fast cluster upgrade."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
m = runpy.run_path(str(ROOT / "scripts/talos/fast-batch-upgrade.py"))
make_plan = m["plan"]
NODES = m["NODES"]
IMAGE = "factory.talos.dev/metal-installer/" + "a" * 64 + ":v1.14.4"


def test_talos_upgrade_plan_is_explicit_complete_and_stable():
    item = make_plan(IMAGE)
    assert item["parallelTalos"] == 3
    assert item["nodes"] == ["172.17.0.50", "172.17.0.51", "172.17.0.52"]
    assert item["talosTarget"] == "v1.14.4"
    assert item["kubernetesTarget"] == "v1.37.1"
    assert item["etcdBackup"] == "not-required-at-operator-request"
    assert len(item["planHash"]) == 64
    assert make_plan(IMAGE)["planHash"] == item["planHash"]


@pytest.mark.parametrize("image", [
    "ghcr.io/siderolabs/installer:v1.14.4",
    "factory.talos.dev/metal-installer/" + "b" * 64 + ":v1.13.9",
    "factory.talos.dev/metal-installer/unknown:v1.14.4",
    "factory.talos.dev/metal-installer/" + "a" * 64 + ":latest",
    "factory.talos.dev/metal-installer/" + "a" * 64 + ":v1.14.4;echo",
])
def test_talos_factory_image_must_be_exact_target(image):
    with pytest.raises(ValueError):
        make_plan(image)


@pytest.mark.parametrize("args", [
    ["--apply", "--installer-image", IMAGE],
    ["--apply", "--installer-image", IMAGE, "--acknowledge", "wrong"],
    ["--apply", "--installer-image", IMAGE, "--expected-plan-hash", "wrong",
     "--acknowledge", m["ACK"]],
])
def test_talos_apply_refuses_missing_exact_ack_or_fingerprint(args, monkeypatch):
    monkeypatch.setitem(m["main"].__globals__, "canonical_checkout",
                        lambda: pytest.fail("unauthorized apply attempted"))
    with pytest.raises(SystemExit) as err:
        m["main"](args)
    assert err.value.code == 2


def test_read_only_plan_never_contacts_cluster(monkeypatch, capsys):
    g = m["main"].__globals__
    monkeypatch.setitem(g, "preflight", lambda: pytest.fail("network preflight called"))
    monkeypatch.setitem(g, "parallel_nodes", lambda *args:
                        pytest.fail("Talos mutation called"))
    assert m["main"](["--check", "--installer-image", IMAGE]) == 0
    output = capsys.readouterr().out
    assert '"parallelTalos": 3' in output
    assert '"planHash"' in output


def test_three_talos_nodes_submitted_without_serial_wait(monkeypatch):
    g = m["parallel_nodes"].__globals__
    submissions = []
    completed = set()

    def fake_upgrade(ip, image):
        submissions.append(ip)
        assert image == IMAGE
        completed.add(ip)

    def fake_wait(ip, timeout):
        # Waiting starts only after every upgrade has been submitted.
        assert set(submissions) == set(NODES)
        assert set(completed) == set(NODES)

    monkeypatch.setitem(g, "upgrade_node", fake_upgrade)
    monkeypatch.setitem(g, "wait_node", fake_wait)
    m["parallel_nodes"](IMAGE, 120)
    assert set(submissions) == set(NODES)


def test_any_failed_talos_node_blocks_kubernetes(monkeypatch):
    g = m["parallel_nodes"].__globals__
    monkeypatch.setitem(g, "upgrade_node",
                        lambda ip, image: (_ for _ in ()).throw(
                            RuntimeError("failed")) if ip == NODES[0] else None)
    monkeypatch.setitem(g, "wait_node",
                        lambda ip, timeout: pytest.fail("should not wait or upgrade k8s"))
    with pytest.raises(RuntimeError, match="Talos upgrades failed"):
        m["parallel_nodes"](IMAGE, 120)


def test_talos_server_version_required_even_if_client_is_new(monkeypatch):
    from types import SimpleNamespace

    wait = m["wait_node"]
    g = wait.__globals__
    monkeypatch.setitem(g, "run", lambda *a, **kw:
                        "Client:\\n  Tag: v1.14.4\\nServer:\\n  Tag: v1.13.9\\n")
    ticks = iter([0.0, 1.0, 20.0])
    monkeypatch.setitem(g, "time", SimpleNamespace(
        monotonic=lambda: next(ticks),
        sleep=lambda sec: None,
    ))
    with pytest.raises(RuntimeError, match="did not recover"):
        wait("172.17.0.50", timeout=10)


def test_talos_server_version_unlocks_recovery(monkeypatch):
    wait = m["wait_node"]
    g = wait.__globals__
    monkeypatch.setitem(g, "run", lambda *a, **kw:
                        "Client:\\n  Tag: v1.14.4\\nServer:\\n  NODE: 172.17.0.50\\n  Tag: v1.14.4\\n")
    wait("172.17.0.50", timeout=10)


def test_offline_no_force_or_reset_code_path():
    source = (ROOT / "scripts/talos/fast-batch-upgrade.py").read_text()
    assert '["talosctl", "--nodes", ip, "upgrade", "--image", image]' in source
    assert '"--force"' not in source
    assert '["talosctl", "--nodes", NODES[0], "upgrade-k8s"' in source
    assert '"--dry-run"' in source
