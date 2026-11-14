#!/usr/bin/env bash
# Read-only, fail-closed. No token printed; never runs a mutating Azure command.
set -euo pipefail
fail() { printf 'ENTRA_LAB_BLOCKED: %s\n' "$1" >&2; exit 2; }
[[ "${AGENT_EXECUTION_MODE:-offline}" == "workstation" ]] || fail "verified workstation required"
[[ "${ENTRA_LAB_CONFIRMED:-false}" == "true" ]] || fail "personal tenant approval required"
[[ "${ENTRA_LAB_TENANT_ID:-}" =~ ^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$ ]] || fail "invalid tenant GUID"
for cmd in az terragrunt tofu flock; do
  command -v "$cmd" >/dev/null 2>&1 || fail "missing tool: $cmd"
done
active_tenant="$(az account show --query tenantId -o tsv 2>/dev/null)" || fail "Azure CLI login required"
[[ "$active_tenant" == "$ENTRA_LAB_TENANT_ID" ]] || fail "active CLI tenant mismatch"
printf 'ENTRA_LAB_PREFLIGHT_OK: personal tenant matched (read-only)\n'
