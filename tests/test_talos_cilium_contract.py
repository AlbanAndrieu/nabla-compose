from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/talos/migrate-cni-cilium.sh"


def test_talos_patch_disables_builtin_cni_only() -> None:
    patch = yaml.safe_load((ROOT / "config/talos/patches/cni-none.yaml").read_text(encoding="utf-8"))
    assert patch == {"cluster": {"network": {"cni": {"name": "none"}}}}
    assert "cni-none.yaml" in (ROOT / "scripts/talos/generate-config.sh").read_text(encoding="utf-8")


def test_cilium_values_follow_talos_constraints() -> None:
    values = yaml.safe_load((ROOT / "kubernetes/cilium/values.yaml").read_text(encoding="utf-8"))
    assert values["ipam"]["mode"] == "kubernetes"
    assert values["kubeProxyReplacement"] is False
    assert values["cgroup"] == {"autoMount": {"enabled": False}, "hostRoot": "/sys/fs/cgroup"}
    assert "SYS_MODULE" not in values["securityContext"]["capabilities"]["ciliumAgent"]
    version = (ROOT / "kubernetes/cilium/VERSION").read_text(encoding="utf-8").strip()
    assert version.count(".") == 2 and all(part.isdigit() for part in version.split("."))


def test_apply_requires_explicit_approval() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'MODE="${1:---plan}"' in script
    assert "etcd snapshot" in script
    env = os.environ | {"NABLA_CILIUM_APPLY_APPROVED": ""}
    result = subprocess.run(["bash", str(SCRIPT), "--apply"], cwd=ROOT, env=env,
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "NABLA_CILIUM_APPLY_APPROVED=yes" in result.stdout + result.stderr
