#!/usr/bin/env bash
# Start the read-only Grafana MCP in a throwaway container (stdio).
#
# The service account token comes from the private file grafana.env
# (GRAFANA_SERVICE_ACCOUNT_TOKEN=...), passed with --env-file so it never shows
# in a command line.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/mcp/lib.sh
source "${HERE}/lib.sh"

env_file="$(mcp_private_file grafana.env grafana)" || exit 1

exec docker run --rm -i --read-only --cap-drop=ALL --security-opt=no-new-privileges \
  -e "GRAFANA_URL=${GRAFANA_MCP_URL:-http://172.17.0.24:30037}" \
  --env-file "${env_file}" \
  grafana/mcp-grafana:1.2.0-alpine -t stdio --disable-write
