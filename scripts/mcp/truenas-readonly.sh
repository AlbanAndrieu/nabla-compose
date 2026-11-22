#!/usr/bin/env bash
# Start the read-only TrueNAS MCP (@profanter-dev/truenas-mcp) for .mcp.json.
#
# The key comes from TRUENAS_MCP_API_KEY or from the private file written by
# scripts/truenas/mcp-readonly-identity.sh apply (Vaultwarden keeps the copy).
# TLS stays verified: truenas.albandrieu.com is pinned to the LAN address for
# this process only (truenas-pin-host.mjs), never TRUENAS_INSECURE=true.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
KEY_FILE="${TRUENAS_MCP_KEY_FILE:-${XDG_CONFIG_HOME:-${HOME}/.config}/nabla/mcp/truenas-readonly.key}"

if [[ -z "${TRUENAS_MCP_API_KEY:-}" ]]; then
  if [[ ! -f "${KEY_FILE}" || -L "${KEY_FILE}" ]]; then
    echo "truenas-readonly: no key; run scripts/truenas/mcp-readonly-identity.sh apply" >&2
    exit 1
  fi
  if [[ "$(stat -c '%a %u' "${KEY_FILE}")" != "600 $(id -u)" ]]; then
    echo "truenas-readonly: ${KEY_FILE} must be yours with mode 600" >&2
    exit 1
  fi
  TRUENAS_MCP_API_KEY="$(<"${KEY_FILE}")"
fi

export TRUENAS_HOST="${TRUENAS_MCP_HOST:-truenas.albandrieu.com:7000}"
export TRUENAS_API_KEY="${TRUENAS_MCP_API_KEY}"
export TRUENAS_INSECURE=false
export NABLA_PIN_HOST="${TRUENAS_HOST%:*}"
export NABLA_PIN_ADDR="${TRUENAS_MCP_ADDR:-172.17.0.24}"
export NODE_OPTIONS="--import=file://${HERE}/truenas-pin-host.mjs"
unset TRUENAS_MCP_API_KEY

# The package loads dotenv from its working directory: start where no .env lives,
# so it never reads the repository secrets.
cd "${HERE}"
exec npx -y @profanter-dev/truenas-mcp@1.0.6
