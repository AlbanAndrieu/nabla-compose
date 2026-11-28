#!/usr/bin/env python3
"""Read-only Kubara/Talos integration audit; no bootstrap or infrastructure writes.

Static mode validates the reviewed *candidate*, not an installed Kubara stack.
Runtime mode requires --ack-cluster-readonly and a confirmed Talos API server.
Never expose kubectl output or authentication material in error messages.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_API = "https://172.17.0.50:6443"
EXPECTED_SERVICES = {
    "traefik": "enabled",
    "metallb": "disabled",
    "longhorn": "disabled",
    "external-dns": "disabled",
    "external-secrets": "disabled",
    "cert-manager": "disabled",
    "oauth2-proxy": "disabled",
    "kube-prometheus-stack": "disabled",
    "loki": "disabled",
    "metrics-server": "disabled",
    "kyverno": "disabled",
    "kyverno-policies": "disabled",
    "kyverno-policy-reporter": "disabled",
    "velero": "disabled",
    "homer-dashboard": "disabled",
}
CANDIDATE = "config/kubara/config.candidate.yaml"
BRIDGE = "apps/traefik/examples/talos-kubara-bridge.example.yml"


def document(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{relative}: MISSING_OR_SYMLINK")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{relative}: INVALID_DOCUMENT")
    return data


def static_check(root: Path) -> dict[str, Any]:
    config = document(root, CANDIDATE)
    version = (root / "config/kubara/VERSION").read_text(encoding="utf-8").strip()
    if version != "0.14.0":
        raise ValueError("KUBARA_PIN_CHANGED_REVIEW_REQUIRED")
    clusters = config.get("clusters")
    if not isinstance(clusters, list) or len(clusters) != 1:
        raise ValueError("KUBARA_CLUSTER_SCOPE_INVALID")
    cluster = clusters[0]
    if not isinstance(cluster, dict):
        raise ValueError("KUBARA_CLUSTER_INVALID")
    for field, expected in {
        "name": "nabla-talos",
        "stage": "homelab",
        "type": "hub",
        "dnsName": "talos.int.albandrieu.com",
        "ssoOrg": "none",
        "ssoTeam": "none",
    }.items():
        if cluster.get(field) != expected:
            raise ValueError(f"KUBARA_{field.upper()}_DRIFT")
    if config.get("bootstrapCatalog") != (
        "oci://ghcr.io/kubara-io/catalogs/bootstrap:2.0.0"
    ):
        raise ValueError("KUBARA_BOOTSTRAP_CATALOG_DRIFT")
    if cluster.get("catalogs") != ["oci://ghcr.io/kubara-io/catalogs/general:2.0.0"]:
        raise ValueError("KUBARA_GENERAL_CATALOG_DRIFT")
    services = cluster.get("services")
    if not isinstance(services, dict) or set(services) != set(EXPECTED_SERVICES):
        raise ValueError("KUBARA_SERVICE_SET_UNREVIEWED")
    for name, status in EXPECTED_SERVICES.items():
        if services.get(name) != {"status": status}:
            raise ValueError(f"KUBARA_SERVICE_DRIFT_{name}")

    cilium = document(root, "kubernetes/cilium/values.yaml")
    if cilium.get("kubeProxyReplacement") is not False:
        raise ValueError("CILIUM_KPR_REVIEW_REQUIRED")
    if cilium.get("ipam", {}).get("mode") != "kubernetes":
        raise ValueError("CILIUM_IPAM_REVIEW_REQUIRED")
    storage = document(root, "kubernetes/truenas-csi/storageclass-nfs.yaml")
    if storage.get("kind") != "StorageClass":
        raise ValueError("TRUENAS_CSI_STORAGECLASS_MISSING")
    if storage.get("metadata", {}).get("name") != "nabla-truenas-nfs":
        raise ValueError("TRUENAS_CSI_STORAGECLASS_DRIFT")
    if storage.get("provisioner") != "csi.truenas.io":
        raise ValueError("TRUENAS_CSI_PROVISIONER_DRIFT")

    edge = document(root, BRIDGE)
    http = edge.get("http", {})
    routers = http.get("routers", {})
    router = routers.get("talos-private-canary", {})
    if router.get("rule") != "Host(`test.int.albandrieu.com`)":
        raise ValueError("TRAEFIK_EDGE_HOST_DRIFT")
    if router.get("entryPoints") != ["websecure"]:
        raise ValueError("TRAEFIK_EDGE_ENTRYPOINT_DRIFT")
    if router.get("middlewares") != ["talos-bridge-lan-only"]:
        raise ValueError("TRAEFIK_EDGE_AUTHZ_MISSING")
    middleware = http.get("middlewares", {}).get("talos-bridge-lan-only", {})
    if middleware.get("ipAllowList", {}).get("sourceRange") != ["172.17.0.0/24"]:
        raise ValueError("TRAEFIK_EDGE_LAN_RESTRICTION_DRIFT")
    upstream = (
        http.get("services", {}).get("talos-kubara-canary", {}).get("loadBalancer", {})
    )
    if upstream.get("serversTransport") != "talos-kubara-verified":
        raise ValueError("TRAEFIK_EDGE_UPSTREAM_TRANSPORT_DRIFT")
    if upstream.get("servers") != [
        {"url": "https://REPLACE_WITH_RESERVED_TALOS_LB_IP"}
    ]:
        raise ValueError("TRAEFIK_BRIDGE_CANDIDATE_MUST_NOT_BE_LIVE")
    transport = http.get("serversTransports", {}).get("talos-kubara-verified", {})
    if (
        transport.get("insecureSkipVerify") is not False
        or transport.get("serverName") != "test.int.albandrieu.com"
        or transport.get("rootCAs")
        != ["/etc/traefik/certs/REPLACE_WITH_PRIVATE_CA_CERT.pem"]
    ):
        raise ValueError("TRAEFIK_UPSTREAM_TLS_VERIFICATION_MISSING")
    if (root / "apps/traefik/dynamic/talos-kubara-bridge.yml").exists():
        raise ValueError("TRAEFIK_BRIDGE_WAS_ACTIVATED_WITHOUT_REVIEW")
    return {
        "schema": "nabla-kubara-talos-audit/v1",
        "status": "CANDIDATE_READY_FOR_SCHEMA_VALIDATION",
        "cli_pin": version,
        "cilium": "PRESERVE_KPR_FALSE",
        "storage": "PRESERVE_TRUENAS_NFS",
        "metal_lb": "DISABLED_CANDIDATE",
        "longhorn": "DISABLED_CANDIDATE",
        "truenas_traefik_bridge": "EXAMPLE_NOT_LOADED",
        "kubara_bootstrap": "NOT_RUN",
    }


def kube_json(*args: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["kubectl", *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("KUBECTL_UNAVAILABLE_OR_TIMEOUT") from exc
    if completed.returncode != 0 or len(completed.stdout) > 1024 * 1024:
        raise ValueError("KUBECTL_READ_FAILED_OR_OVERSIZED")
    try:
        value = json.loads(completed.stdout)
    except ValueError as exc:
        raise ValueError("KUBECTL_INVALID_JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("KUBECTL_INVALID_RESPONSE")
    return value


def runtime_check(expected_api: str) -> dict[str, Any]:
    context = kube_json("config", "view", "--minify", "-o", "json")
    servers = [
        item.get("cluster", {}).get("server")
        for item in context.get("clusters", [])
    ]
    if servers != [expected_api]:
        raise ValueError("TALOS_API_SERVER_MISMATCH")
    nodes = kube_json("get", "nodes", "-o", "json")
    ready = sum(
        1
        for node in nodes.get("items", [])
        if any(
            c.get("type") == "Ready" and c.get("status") == "True"
            for c in node.get("status", {}).get("conditions", [])
        )
    )
    if ready < 3:
        raise ValueError("TALOS_NODES_NOT_READY")
    cilium = kube_json("-n", "kube-system", "get", "daemonset", "cilium", "-o", "json")
    desired = cilium.get("status", {}).get("desiredNumberScheduled", 0)
    actual = cilium.get("status", {}).get("numberReady", 0)
    if desired < 3 or actual != desired:
        raise ValueError("CILIUM_DAEMONSET_NOT_READY")
    driver = kube_json("get", "csidriver", "csi.truenas.io", "-o", "json")
    storage = kube_json("get", "storageclass", "nabla-truenas-nfs", "-o", "json")
    if driver.get("metadata", {}).get("name") != "csi.truenas.io":
        raise ValueError("TRUENAS_CSI_DRIVER_NOT_FOUND")
    if storage.get("provisioner") != "csi.truenas.io":
        raise ValueError("TRUENAS_CSI_STORAGECLASS_NOT_FOUND")
    ingress = kube_json("get", "ingressclass", "-o", "json")
    if any(
        item.get("metadata", {}).get("name") == "traefik"
        or "traefik" in item.get("spec", {}).get("controller", "").lower()
        for item in ingress.get("items", [])
    ):
        raise ValueError("KUBARA_TRAEFIK_ALREADY_OWNED")
    return {
        "status": "PREBOOTSTRAP_RUNTIME_READONLY_PASS",
        "ready_nodes": ready,
        "cilium_ready": actual,
        "truenas_storageclass": "PRESENT",
        "traefik_ingressclass": "ABSENT",
        "vip_reservation": "NOT_VERIFIED",
        "wan_denial": "NOT_VERIFIED",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--cluster-readonly", action="store_true")
    parser.add_argument("--ack-cluster-readonly", action="store_true")
    parser.add_argument("--expected-api", default=EXPECTED_API)
    args = parser.parse_args()
    if args.cluster_readonly and not args.ack_cluster_readonly:
        parser.error("--cluster-readonly requires --ack-cluster-readonly")
    try:
        result = static_check(args.root)
        if args.cluster_readonly:
            result["cluster"] = runtime_check(args.expected_api)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        code = str(exc)
        if code not in {"KUBARA_PIN_CHANGED_REVIEW_REQUIRED"} and not code.startswith(
            ("KUBARA_", "CILIUM_", "TRUENAS_", "TRAEFIK_", "TALOS_", "KUBECTL_")
        ):
            code = "INTEGRATION_CHECK_FAILED"
        print(
            json.dumps(
                {
                    "schema": "nabla-kubara-talos-audit/v1",
                    "status": "BLOCKED",
                    "reason": code,
                }
            )
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
