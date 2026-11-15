#!/usr/bin/env bash
# Interactive workstation-only tenant verification. No Azure mutation.
set -euo pipefail
fail() { printf 'ENTRA_LAB_BLOCKED: %s\n' "$1" >&2; exit 2; }
[[ "${AGENT_EXECUTION_MODE:-offline}" == workstation ]] || fail "verified workstation required"
[[ "${ENTRA_LAB_CONFIRMED:-false}" == true ]] || fail "personal test tenant must be confirmed"
[[ "${ENTRA_LAB_TENANT_ID:-}" =~ ^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$ ]] || fail "invalid tenant GUID"
for cmd in az tofu; do
  command -v "${cmd}" >/dev/null 2>&1 || fail "missing tool: ${cmd}"
done
[[ -z "${ARM_CLIENT_SECRET:-}" && -z "${ARM_ACCESS_KEY:-}" && -z "${ARM_SAS_TOKEN:-}" ]] || fail "static credentials are forbidden"
active_tenant="$(az account show --query tenantId -o tsv 2>/dev/null)" || fail "Azure CLI browser login required"
[[ "${active_tenant}" == "${ENTRA_LAB_TENANT_ID}" ]] || fail "Azure CLI tenant mismatch"
echo "ENTRA_LAB_PREFLIGHT_OK: expected tenant selected; no changes made"
