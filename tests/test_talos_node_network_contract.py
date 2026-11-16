"""Talos nodes keep a static LAN address and hostname, never a DHCP lease."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NODES = {
    "taloscp01": ("02:00:00:00:10:01", "172.17.0.50"),
    "taloswk01": ("02:00:00:00:20:01", "172.17.0.51"),
    "taloswk02": ("02:00:00:00:20:02", "172.17.0.52"),
}


def test_each_node_patch_pins_its_mac_address_and_hostname():
    bootstrap = (ROOT / "docs/truenas-talos-bootstrap.md").read_text(encoding="utf-8")
    for name, (mac, address) in NODES.items():
        assert f"{name}  {mac}" in bootstrap
        machine, hostname = yaml.safe_load_all((ROOT / f"config/talos/nodes/{name}.yaml").read_text(encoding="utf-8"))
        [interface] = machine["machine"]["network"]["interfaces"]
        assert interface["deviceSelector"] == {"hardwareAddr": mac}
        assert interface["dhcp"] is False
        assert interface["addresses"] == [f"{address}/24"]
        assert interface["routes"] == [{"network": "0.0.0.0/0", "gateway": "172.17.0.1"}]
        assert hostname == {"apiVersion": "v1alpha1", "kind": "HostnameConfig", "auto": "off", "hostname": name}


def test_recipes_dry_run_every_node_and_apply_workers_first():
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    check = justfile.split("talos-node-network-check:\n", 1)[1].split("\n\n", 1)[0]
    apply = justfile.split("talos-node-network-apply:\n", 1)[1].split("\n\n", 1)[0]
    assert "--dry-run" in check
    assert "--dry-run" not in apply
    for name, (_, address) in NODES.items():
        assert f"{name}:{address}" in check
        assert f"{name}:{address}" in apply
    assert apply.index("taloscp01") > apply.index("taloswk02") > apply.index("taloswk01")
