"""DNS-as-code contract of terraform/cloudflare (offline).

The tunnel route list is the single source of tunnel CNAMEs, retired names are
removed through two reviewed OpenTofu plans, and the capture script is
read-only and never prints record contents.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "terraform" / "cloudflare"
SCRIPT = ROOT / "scripts" / "cloudflare" / "capture-dns-records.py"
MEDIA_NAMES = {
    f"{name}.albandrieu.com"
    for name in ("emby", "lidarr", "prowlarr", "radarr", "sabnzbd", "sonarr", "transmission")
}


def load_capture():
    spec = importlib.util.spec_from_file_location("capture_dns_records", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_retired_and_media_names_are_never_routed_nor_recorded() -> None:
    policy = yaml.safe_load((MODULE / "dns-policy.yaml").read_text(encoding="utf-8"))
    retired = set(policy["retired_hostnames"])
    tunnel = (MODULE / "tunnel.tofu").read_text(encoding="utf-8")
    routed = set(re.findall(r'hostname\s*=\s*"([^"]+)"', tunnel))
    assert not routed & (retired | MEDIA_NAMES), "a retired hostname is still routed by the tunnel"
    # The media names were destroyed on 10/11/2026: their ids must not come back.
    ids = (MODULE / "dns-record-ids.auto.tfvars").read_text(encoding="utf-8")
    assert not [name for name in MEDIA_NAMES if f'"{name}' in ids]
    assert not [h for h in routed if h.endswith(".int.albandrieu.com")]
    assert policy["forbidden_public_suffixes"] == [".int.albandrieu.com"]


def test_tunnel_routes_drive_dns_records_and_imports() -> None:
    tunnel = (MODULE / "tunnel.tofu").read_text(encoding="utf-8")
    assert "ingress = local.tunnel_ingress" in tunnel
    root = (MODULE / "dns-records.tofu").read_text(encoding="utf-8")
    assert "for rule in local.tunnel_ingress" in root
    assert 'source = "./modules/dns-records"' in root
    imports = (MODULE / "imports.tofu").read_text(encoding="utf-8")
    assert "to = module.dns_records.cloudflare_dns_record.tunnel[each.key]" in imports
    assert "to = module.dns_records.cloudflare_dns_record.retired[each.key]" in imports
    module = (MODULE / "modules" / "dns-records" / "main.tofu").read_text(encoding="utf-8")
    assert "has no import id" in module, "import-first precondition must refuse blind creates"
    assert "ignore_changes = all" in module


def test_capture_script_is_read_only_and_redacts_contents() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'method="GET"' in text
    for verb in ("DELETE", "POST", "PUT", "PATCH"):
        assert f'method="{verb}"' not in text
    assert "print(token" not in text and "{token}" not in text.replace('f"Bearer {token}"', "")


def test_capture_classification() -> None:
    capture = load_capture()
    facts = {
        "tunnel_hostnames": ["grafana.albandrieu.com", "gatus.albandrieu.com", "new.albandrieu.com"],
        "tunnel_target": "tid.cfargotunnel.com",
        "zone_id": "z",
        "retired": {"radarr.albandrieu.com"},
        "new_tunnel_hostnames": {"new.albandrieu.com"},
        "forbidden_suffixes": (".int.albandrieu.com",),
    }
    records = [
        {"id": "1", "name": "grafana.albandrieu.com", "type": "CNAME", "content": "tid.cfargotunnel.com", "proxied": True},
        {"id": "2", "name": "radarr.albandrieu.com", "type": "A", "content": "198.51.100.7", "proxied": True},
        {"id": "3", "name": "old.albandrieu.com", "type": "CNAME", "content": "tid.cfargotunnel.com", "proxied": True},
        {"id": "4", "name": "s3.int.albandrieu.com", "type": "A", "content": "198.51.100.7", "proxied": False},
        {"id": "5", "name": "albandrieu.com", "type": "MX", "content": "mx.example.net", "proxied": False},
        {"id": "6", "name": "fastapi-sample.albandrieu.com", "type": "CNAME", "content": "tid.cfargotunnel.com", "proxied": True},
    ]
    report = capture.classify(records, facts)
    classes = {row["name"]: row["class"] for row in report["rows"]}
    assert classes == {
        "grafana.albandrieu.com": "tunnel",
        "radarr.albandrieu.com": "retired",
        "old.albandrieu.com": "orphan-tunnel",
        "s3.int.albandrieu.com": "private-namespace",
        "albandrieu.com": "unmanaged",
        "fastapi-sample.albandrieu.com": "fastapi-sample",
    }
    assert report["dns_tunnel_record_ids"] == {"grafana.albandrieu.com": "1"}
    assert report["dns_retired_record_ids"] == {"radarr.albandrieu.com/A": "2"}
    assert report["missing_tunnel_records"] == ["gatus.albandrieu.com"]
    assert all("content" not in row for row in report["rows"]), "contents are never reported"


def test_written_ids_are_hcl_with_scanner_markers() -> None:
    text = load_capture().render_tfvars(
        {"dns_tunnel_record_ids": {"keycloak.albandrieu.com": "a" * 32, "ha.albandrieu.com": "b" * 32},
         "dns_retired_record_ids": {}}
    )
    assert text == (
        "dns_tunnel_record_ids = {\n"
        f'  "keycloak.albandrieu.com" = "{"a" * 32}" # gitleaks:allow\n'
        f'  "ha.albandrieu.com"       = "{"b" * 32}" # gitleaks:allow\n'
        "}\n\n"
        "dns_retired_record_ids = {}\n"
    )
    committed = (MODULE / "dns-record-ids.auto.tfvars").read_text(encoding="utf-8")
    ids = [line for line in committed.splitlines() if re.search(r'= "[0-9a-f]{32}"', line)]
    assert ids and all(line.endswith("# gitleaks:allow") for line in ids)


@pytest.mark.skipif(shutil.which("tofu") is None, reason="OpenTofu not installed")
def test_dns_records_module_offline_contract() -> None:
    module = MODULE / "modules" / "dns-records"
    subprocess.run(["tofu", f"-chdir={module}", "init", "-backend=false", "-input=false"],
                   check=True, capture_output=True)
    result = subprocess.run(["tofu", f"-chdir={module}", "test"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
