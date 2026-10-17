#!/usr/bin/env python3
"""Container-side TrueNAS observer identity probe; piped to the FastAPI venv python by verify-truenas-observer-access.sh (read-only)."""
import os

from nabla.integrations.truenas_client import build_truenas_adapter

adapter = build_truenas_adapter()
if adapter is None:
    raise SystemExit("TrueNAS adapter is not configured")

expected_username = os.environ["TRUENAS_OBSERVER_EXPECTED_USERNAME"].strip()
identity = adapter._call("auth.me")
if not isinstance(identity, dict):
    raise SystemExit("auth.me returned an unexpected payload")

authenticated_username = str(identity.get("pw_name") or "")
if authenticated_username != expected_username:
    raise SystemExit(
        f"auth.me identity mismatch: expected {expected_username!r}, got {authenticated_username!r}"
    )

privilege = identity.get("privilege")
if not isinstance(privilege, dict):
    raise SystemExit("auth.me did not expose the expected privilege object")

raw_roles = privilege.get("roles")
if isinstance(raw_roles, dict):
    roles = set(map(str, raw_roles.keys()))
elif isinstance(raw_roles, (list, tuple, set, frozenset)):
    roles = set(map(str, raw_roles))
elif isinstance(raw_roles, str):
    roles = {raw_roles} if raw_roles else set()
else:
    roles = set()

if not roles:
    raise SystemExit(
        "auth.me privilege.roles is present in an unsupported shape: "
        + type(raw_roles).__name__
    )

dangerous_roles = sorted(
    filter(
        lambda role: (
            role in {"FULL_ADMIN", "SHARING_ADMIN", "REPLICATION_ADMIN"}
            or "_WRITE" in role
            or "_DELETE" in role
            or role.endswith("_FULL_CONTROL")
        ),
        roles,
    )
)
if dangerous_roles:
    raise SystemExit(
        "observer has write/admin roles and is not least-privilege: "
        + ",".join(dangerous_roles)
    )

version = adapter.system_version()
apps = adapter.list_apps()
vms = adapter._call("vm.query")
if not isinstance(vms, list):
    raise SystemExit("vm.query returned an unexpected payload")

if "READONLY_ADMIN" not in roles:
    missing_roles = sorted({"APPS_READ", "VM_READ"} - roles)
    if missing_roles:
        raise SystemExit(
            "observer identity is missing required read roles: "
            + ",".join(missing_roles)
            + "; active roles="
            + ",".join(sorted(roles))
        )

expected_talos_vms = {"taloscp01", "taloswk01", "taloswk02"}
observed_talos_vms = {
    str(vm.get("name") or "")
    for vm in vms
    if isinstance(vm, dict) and str(vm.get("name") or "") in expected_talos_vms
}
if observed_talos_vms != expected_talos_vms:
    raise SystemExit(
        "vm.query did not expose the complete Talos VM inventory: "
        + ",".join(sorted(observed_talos_vms))
    )

scope = "broad_readonly" if "READONLY_ADMIN" in roles else "apps_vm_read"

print(f"authenticated_username={authenticated_username}")
print(f"rbac_scope={scope}")
print(f"roles={','.join(sorted(roles))}")
print(f"version={version}")
print(f"apps={len(apps)}")
print(f"talos_vms={len(observed_talos_vms)}")
