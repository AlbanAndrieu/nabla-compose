#!/usr/bin/env bash
# Start an HTTP MCP that needs an auth header (Homarr, FastAPI Sample) as stdio.
#
# Usage from .mcp.json: bash scripts/mcp/http-remote.sh NAME URL
# The headers come from the private file NAME.headers ("Header: value" lines).
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/mcp/lib.sh
source "${HERE}/lib.sh"

[[ $# -eq 2 ]] || {
  echo "usage: $0 NAME URL" >&2
  exit 2
}
headers="$(mcp_private_file "$1.headers" "$1")" || exit 1

# Start where no .env lives, so no tool reads the repository secrets.
cd "${HERE}"
exec npx -y "${MCP_REMOTE_PACKAGE}" "$2" --allow-http --header-file "${headers}"
